# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# python imports
import datetime
import json
from http.client import HTTPConnection
from ipaddress import IPv4Address, IPv4Network

from coreMano.cloudify_wrapper_lib.cloudify_rest_client.client import CloudifyClient
from coreMano.cloudify_wrapper_lib.cloudify_rest_client.exceptions import CloudifyClientError
from coreMano.cloudify_wrapper_lib.converter_nsd_mtp_yaml import ConverterNSDMTPYAML
from db.ns_db import ns_db
from db.nsd_db import nsd_db
from db.nsir_db import nsir_db
from db.vnfd_db import vnfd_db
from monitoring.monitoring import stop_monitoring_job, stop_exporters_on_rvm_agent, delete_rvm_agent, \
    wait_commands_execution
from nbi import log_queue
import time
import requests
from coreMano.cloudify_wrapper_lib.converter_nsd_openstack_yaml import *
import os

from requests.auth import HTTPBasicAuth

monitoring_config = RawConfigParser()
monitoring_config.read("../../monitoring/monitoring.properties")
monitoring_pushgateway = monitoring_config.get("MONITORING", "monitoring.pushgateway")
monitoring_ip = monitoring_config.get("MONITORING", "monitoring.ip")
monitoring_port = monitoring_config.get("MONITORING", "monitoring.port")
monitoring_base_path = monitoring_config.get("MONITORING", "monitoring.base_path")
is_install = True
is_terminate = True
is_scale = True



class CloudifyWrapper(object):
    """
    Class description
    """
    __instance = None
    __executions = {}

    ##########################################################################
    # PUBLIC METHODS                                                                                                       #
    ##########################################################################

    def __init__(self, name, host_ip):
        """
        Inits CloudifyWrapper
        Parameters
        ----------
        name: String
            Name of MANO
        host_ip: String
            Ip address of MANO
        """
        # read properties file and get MANO name and IP
        config = RawConfigParser()
        config.read("../../coreMano/coreMano.properties")
        self.__user = config.get("Cloudify", "user")
        self.__password = config.get("Cloudify", "password")
        self.__tenant = config.get("Cloudify", "tenant")
        self.__blueprints_path = "/tmp/CloudifyWrapper"
        self.__wrapper = config.get("Cloudify", "wrapper")
        self.__default_key_name = config.get("Cloudify", "default_key_name")
        self.__install_cloudify_agent = config.get("Cloudify", "install_cloudify_agent")
        self.__install_rvm_agent = config.get("Cloudify", "install_rvm_agent")
        self.__start_vlan = config.get("Cloudify", "vlan", fallback=None)
        self.__nfvo_ip = host_ip
        self.converter_to_yaml = None
        self.ns_descriptor = None
        self.__cloudify_client = CloudifyClient(
            host=self.__nfvo_ip,
            username=self.__user,
            password=self.__password,
            tenant=self.__tenant)

    def instantiate_ns(self, nsi_id, ns_descriptor, vnfds_descriptor, body, placement_info, resources, nestedInfo):
        """
        Instanciates the network service identified by nsi_id, according to the infomation contained in the body and
        placement info.
        Parameters
        ----------
        nsi_id: string
            identifier of the network service instance
        ns_descriptor: dict
            json containing the nsd
        vnfds_descriptor: dict
            json containing vnfd's of the network service retrieved from catalogue
        body: http request body
            contains the flavourId nsInstantiationLevelId parameters
        placement_info: dict
            result of the placement algorithm
        resources: dict
            information from MTP about resources
        nestedInfo: dict
            federation info of a nested Network Service Instance
        Returns
        -------
        converted_output: dict
            Information about floating IP addresses
        {'sapInfo': {'mgtSap': [{'spr1': '192.168.100.92'}],
        'videoSap': [{'webserver': '192.168.100.66'}, {'spr2': '192.168.100.75'}]}}
        """

        instantiationLevel = body.ns_instantiation_level_id
        # for composition/federation
        if nestedInfo:
            nested_descriptor = next(iter(nestedInfo))
            if len(nestedInfo[nested_descriptor]) > 1:
                # nested from a consumer domain
                nsId_tmp = nsi_id
            else:
                # nested local
                nsId_tmp = nsi_id + '_' + nested_descriptor
        else:
            nsId_tmp = nsi_id

        blueprint_name = nsId_tmp + "_" + ns_descriptor['nsd']['nsdIdentifier'] + "_" + instantiationLevel
        blueprints = self.get_blueprints(blueprint_name)

        agent_ids = {}
        if len(blueprints) == 0:
        #if True:
            log_queue.put(["INFO", "CLOUDIFY_WRAPPER: Blueprint %s will be created" % (blueprint_name)])
            # creates tmp folder for blueprint
            if not os.path.exists(self.__blueprints_path + "/" + nsId_tmp):
                os.makedirs(self.__blueprints_path + "/" + nsId_tmp)
            # os.makedirs(self.__blueprints_path + "/" + nsId_tmp)
            currentDT = datetime.datetime.now()
            string_date = currentDT.strftime("%Y_%m_%d_%H_%M_%S")
            path_to_blueprint = self.__blueprints_path + "/" + nsId_tmp + "/" + string_date

            #full path and name for blueprint

            blueprint_yaml_name_with_path = path_to_blueprint + "/" + blueprint_name + ".yaml"
            os.makedirs(path_to_blueprint)

            if self.__wrapper == "openstack":
                # set parameters for blueprint
                self.converter_to_yaml = ConverterNSDOpenstackYAML()
                self.converter_to_yaml.set_placement_info(placement_info)
                self.converter_to_yaml.set_nfvis_pop_info(self.get_nfvi_pop_info())
                self.converter_to_yaml.set_ns_instantiation_level_id(instantiationLevel)
                self.converter_to_yaml.set_ns_descriptor(ns_descriptor)
                self.converter_to_yaml.set_vnfds_descriptor(vnfds_descriptor)
                self.converter_to_yaml.set_ns_service_id(nsi_id)
                self.converter_to_yaml.parse()
                self.converter_to_yaml.sort_networks()
                self.converter_to_yaml.sort_servers()
                self.converter_to_yaml.generate_yaml(blueprint_yaml_name_with_path)

            if self.__wrapper == "mtp":
                self.converter_to_yaml = ConverterNSDMTPYAML()
                self.converter_to_yaml.set_placement_info(placement_info)
                self.converter_to_yaml.set_nested_info(nestedInfo)
                self.converter_to_yaml.set_nfvis_pop_info(self.get_nfvi_pop_info())
                self.converter_to_yaml.set_ns_instantiation_level_id(instantiationLevel)
                self.converter_to_yaml.set_ns_descriptor(ns_descriptor)
                db_vnf_deployed_info = nsir_db.get_vnf_deployed_info(nsId_tmp)
                self.converter_to_yaml.set_vnf_deployed_info(db_vnf_deployed_info)
                self.converter_to_yaml.set_vnfds_descriptor(vnfds_descriptor)
                self.converter_to_yaml.set_ns_service_id(nsId_tmp)
                self.converter_to_yaml.set_start_vlan(self.__start_vlan)
                self.converter_to_yaml.default_key_name(self.__default_key_name)
                self.converter_to_yaml.install_cloudify_agent(self.__install_cloudify_agent)
                self.converter_to_yaml.install_rvm_agent(self.__install_rvm_agent)
                self.converter_to_yaml.parse()
                self.converter_to_yaml.sort_networks()
                self.converter_to_yaml.sort_servers()
                self.converter_to_yaml.generate_yaml(blueprint_yaml_name_with_path)
                agent_ids = self.converter_to_yaml.get_agent_ids()


        # if len(blueprints) == 0:
        if is_install:
            # bluprint upload
            try:
                self.get_cloudify_client().blueprints.upload(blueprint_yaml_name_with_path, blueprint_name)
                log_queue.put(["DEBUG", "CLOUDIFY_WRAPPER: Blueprint %s.yaml upload completed" % (nsId_tmp)])
            #Check if exists blueprint in cloudify
            except CloudifyClientError as e:
                if e.error_code == 'conflict_error':
                    log_queue.put(["INFO", "CLOUDIFY_WRAPPER: Blueprint %s %s" % (blueprint_name, e)])
                else:
                    log_queue.put(["INFO", "CLOUDIFY_WRAPPER: Blueprint %s %s" % (blueprint_name, e)])
            except Exception as e:
                log_queue.put(["ERROR", "CLOUDIFY_WRAPPER: Blueprint %s.yaml upload error %s " % (blueprint_name, e)])
                return None

            # deployment creation

            try:
                self.__cloudify_client.deployments.create(blueprint_name, nsId_tmp)
                log_queue.put(["DEBUG", "CLOUDIFY_WRAPPER: Deployment %s creation started" % (nsId_tmp)])
            except Exception as e:
                log_queue.put(["ERROR", "CLOUDIFY_WRAPPER: Deployment creation error %s " % (e)])
                return None

            try:
                self.wait_for_deployment_execution(nsId_tmp)
                log_queue.put(["DEBUG", "CLOUDIFY_WRAPPER: Deployment %s creation completed" % (nsId_tmp)])
            except Exception as e:
                log_queue.put(["ERROR", "CLOUDIFY_WRAPPER: Deployment creation error %s " % (e)])
                return None

            # deploying
            try:
                self.get_cloudify_client().executions.start(nsId_tmp, "install")
                log_queue.put(["DEBUG", "CLOUDIFY_WRAPPER: Deploying %s started" % (nsId_tmp)])
            except Exception as e:
                log_queue.put(["ERROR", "CLOUDIFY_WRAPPER: Deploying %s error %s " % (nsId_tmp, e)])
                return None

            try:
                self.wait_for_deployment_execution(nsId_tmp)
                log_queue.put(["DEBUG", "CLOUDIFY_WRAPPER: Deploying %s completed" % (nsId_tmp)])
            except Exception as e:
                log_queue.put(["ERROR", "CLOUDIFY_WRAPPER: Deploying %s error %s " % (nsId_tmp, e)])
                return None

        nsi_sap = self.get_cloudify_client().deployments.outputs.get(deployment_id=nsId_tmp)

        instances = self.get_cloudify_client().node_instances.list(deployment_id=nsId_tmp)

        nodes = self.get_cloudify_client().nodes.list(deployment_id=nsId_tmp)

        vnf_deployed_info = self.get_information_of_vnf(instances, agent_ids)
        nsir_db.save_vnf_deployed_info(nsId_tmp, vnf_deployed_info)

        vim_net_info = self.get_information_of_networks(nsId_tmp, instances, nodes, nestedInfo)
        nsir_db.save_vim_networks_info(nsId_tmp, vim_net_info)

        instantiation_output = {}
        instantiation_output["sapInfo"] = nsi_sap["outputs"]

        if self.__install_rvm_agent == "yes":
            rvm_agents_execute_scripts = RvmAgentsExecuteScripts(ns_descriptor)
            rvm_agents_execute_scripts.set_vnfds_descriptor(vnfds_descriptor)
            rvm_agents_execute_scripts.set_placement_info(placement_info)
            rvm_agents_execute_scripts.set_sap_info(instantiation_output)
            rvm_agents_execute_scripts.set_vim_net_info(vim_net_info)
            rvm_agents_execute_scripts.set_vnf_deployed_info(vnf_deployed_info)
            rvm_agents_execute_scripts.set_nsi_id(nsi_id)
            rvm_agents_execute_scripts.excute_script("instantiate", instantiationLevel, None)
            map_reference_ip = rvm_agents_execute_scripts.get_map_reference_ip()
            nsir_db.save_map_reference_ip(nsId_tmp, map_reference_ip)
        converted_output = self.convert_output(instantiation_output)
        return converted_output

    def scale_ns(self, nsi_id, ns_descriptor, vnfds_descriptor, body, current_df, current_il, placement_info, nestedInfo):
        """
        Scales the network service identified by nsi_id, according to the infomation contained in the body and current instantiation level.
        Parameters
        ----------
        nsi_id: string
            identifier of the network service instance
        ns_descriptor: dict
            json containing the nsd
        vnfds_descriptor: array
            jsons of the vnfds
        body: dict
            scaling information
        current_df:
            current deployment flavour
        current il: string
            identifier of the current instantiation level
        placement_info:
            result of the placement algorithm
        Returns: dict
                    Information about floating IP addresses
        {'sapInfo': {'mgtSap': [{'spr1': '192.168.100.92'}],
        'videoSap': [{'webserver': '192.168.100.66'}, {'spr2': '192.168.100.75'}]}}
            scale_ops
            List with the performed scaling operations, on which vnf and which type (scale_in or scale_out)
        [{'vnfName': 'spr2', 'scaleVnfType': 'SCALE_OUT'}]
        -------

        """
        scale_ns_instantiation_level_id = self.extract_target_il(body)

        rvm_agents_execute_scripts = None

        if self.__install_rvm_agent == "yes":
            rvm_agents_execute_scripts = RvmAgentsExecuteScripts(ns_descriptor)
            rvm_agents_execute_scripts.set_nsi_id(nsi_id)
            rvm_agents_execute_scripts.set_vnfds_descriptor(vnfds_descriptor)
            rvm_agents_execute_scripts.set_placement_info(placement_info)
            nsi_sap = self.get_cloudify_client().deployments.outputs.get(deployment_id=nsi_id)
            instantiation_output = {}
            instantiation_output["sapInfo"] = nsi_sap["outputs"]
            rvm_agents_execute_scripts.set_sap_info(instantiation_output)
            vim_net_info = nsir_db.get_vim_networks_info(nsi_id)
            rvm_agents_execute_scripts.set_vim_net_info(vim_net_info)
            vnf_deployed_info = nsir_db.get_vnf_deployed_info(nsi_id)
            rvm_agents_execute_scripts.set_vnf_deployed_info(vnf_deployed_info)
            rvm_agents_execute_scripts.excute_script("scale_delete", current_il,
                                                     scale_ns_instantiation_level_id)

        blueprint_name = nsi_id + "_" + ns_descriptor['nsd']['nsdIdentifier'] + "_" + scale_ns_instantiation_level_id
        blueprints = self.__cloudify_client.blueprints.list(_include=['id'], id=[blueprint_name]).items
        agent_ids = {}
        scale_ops = self.extract_scaling_info(ns_descriptor, current_df, current_il,
                                              scale_ns_instantiation_level_id)

        if len(blueprints) == 0:
            log_queue.put(["INFO", "CLOUDIFY_WRAPPER: Blueprint %s will be created" % (blueprint_name)])

            # creates tmp folder for blueprint

            scale_ops = self.extract_scaling_info(ns_descriptor, current_df, current_il,
                                                  scale_ns_instantiation_level_id)
            log_queue.put(["DEBUG", "scaling target il: %s" % (scale_ns_instantiation_level_id)])
            # placement_info = nsir_db.get_placement_info(nsi_id)
            if not os.path.exists(self.__blueprints_path):
                os.makedirs(self.__blueprints_path)
            os.makedirs(self.__blueprints_path + "/" + nsi_id, exist_ok=True)
            currentDT = datetime.datetime.now()
            string_date = currentDT.strftime("%Y_%m_%d_%H_%M_%S")
            path_to_blueprint = self.__blueprints_path + "/" + nsi_id + "/" + string_date

            # full path and name for blueprint
            blueprint_yaml_name_with_path = path_to_blueprint + "/" + blueprint_name + ".yaml"
            os.makedirs(path_to_blueprint)

            if self.__wrapper == "openstack":
                # set parameters for blueprint
                self.converter_to_yaml = ConverterNSDOpenstackYAML()
                self.converter_to_yaml.set_placement_info(placement_info)
                self.converter_to_yaml.set_nfvis_pop_info(self.get_nfvi_pop_info())
                self.converter_to_yaml.set_ns_instantiation_level_id(scale_ns_instantiation_level_id)
                self.converter_to_yaml.set_ns_descriptor(ns_descriptor)
                self.converter_to_yaml.set_vnfds_descriptor(vnfds_descriptor)
                self.converter_to_yaml.set_ns_service_id(nsi_id)
                self.converter_to_yaml.parse()
                self.converter_to_yaml.sort_networks()
                self.converter_to_yaml.sort_servers()
                self.converter_to_yaml.generate_yaml(blueprint_yaml_name_with_path)

            if self.__wrapper == "mtp":
                self.converter_to_yaml = ConverterNSDMTPYAML()
                self.converter_to_yaml.set_placement_info(placement_info)
                # self.converter_to_yaml.set_nested_info(nestedInfo)
                self.converter_to_yaml.set_nfvis_pop_info(self.get_nfvi_pop_info())
                self.converter_to_yaml.set_ns_instantiation_level_id(scale_ns_instantiation_level_id)
                self.converter_to_yaml.set_ns_descriptor(ns_descriptor)
                db_vnf_deployed_info = nsir_db.get_vnf_deployed_info(nsi_id)
                self.converter_to_yaml.set_vnf_deployed_info(db_vnf_deployed_info)
                self.converter_to_yaml.set_vnfds_descriptor(vnfds_descriptor)
                self.converter_to_yaml.set_ns_service_id(nsi_id)
                self.converter_to_yaml.set_start_vlan(self.__start_vlan)
                self.converter_to_yaml.default_key_name(self.__default_key_name)
                self.converter_to_yaml.install_cloudify_agent(self.__install_cloudify_agent)
                self.converter_to_yaml.install_rvm_agent(self.__install_rvm_agent)
                self.converter_to_yaml.parse()
                self.converter_to_yaml.sort_networks()
                self.converter_to_yaml.sort_servers()
                self.converter_to_yaml.generate_yaml(blueprint_yaml_name_with_path)
                agent_ids = self.converter_to_yaml.get_agent_ids()

            if is_scale:
                # bluprint upload
                try:
                    self.get_cloudify_client().blueprints.upload(blueprint_yaml_name_with_path, blueprint_name)
                    log_queue.put(["DEBUG", "CLOUDIFY_WRAPPER: Blueprint %s.yaml upload completed" % (nsi_id)])
                #Check if exists blueprint in cloudify
                except CloudifyClientError as e:
                    if e.error_code == 'conflict_error':
                        log_queue.put(["INFO", "CLOUDIFY_WRAPPER: Blueprint %s %s" % (blueprint_name, e)])
                except Exception as e:
                    log_queue.put(["ERROR", "CLOUDIFY_WRAPPER: Blueprint %s.yaml upload error %s " % (blueprint_name, e)])
                    return None
        else:
            log_queue.put(["INFO", "CLOUDIFY_WRAPPER: Blueprint %s exists in cloudify" % (blueprint_name)])

        if is_scale:

            # deployment update
            try:
                self.__cloudify_client.deployment_updates.update_with_existing_blueprint(nsi_id, blueprint_name)
                # self.__cloudify_client.deployment_updates.update(nsi_id, blueprint_yaml_name_with_path)
                log_queue.put(["DEBUG", "CLOUDIFY_WRAPPER: Deployment %s update by %s started" % (nsi_id, blueprint_name)])
            except Exception as e:
                log_queue.put(["ERROR", "CLOUDIFY_WRAPPER: Deployment %s update by %s error %s " % (nsi_id, blueprint_name, e)])
                return None

            try:
                self.wait_for_deployment_execution(nsi_id)
                log_queue.put(["DEBUG", "CLOUDIFY_WRAPPER: Scale Deployment %s update by %s completed" % (nsi_id, blueprint_name)])
            except Exception as e:
                log_queue.put(["ERROR", "CLOUDIFY_WRAPPER: Scale Deployment %s update by %s error %s " % (nsi_id, blueprint_name, e)])
                return None

        nsi_sap = self.__cloudify_client.deployments.outputs.get(deployment_id=nsi_id)
        instances = self.__cloudify_client.node_instances.list(deployment_id=nsi_id)
        nodes = self.__cloudify_client.nodes.list(deployment_id=nsi_id)
        vnf_deployed_info = self.get_information_of_vnf(instances, agent_ids)
        nsir_db.save_vnf_deployed_info(nsi_id, vnf_deployed_info)
        vim_net_info = self.get_information_of_networks(nsi_id, instances, nodes, None)
        nsir_db.save_vim_networks_info(nsi_id, vim_net_info)
        instantiation_output = {}
        instantiation_output["sapInfo"] = nsi_sap["outputs"]
        if self.__install_rvm_agent == "yes":
            rvm_agents_execute_scripts.set_sap_info(instantiation_output)
            rvm_agents_execute_scripts.set_vim_net_info(vim_net_info)
            rvm_agents_execute_scripts.set_vnf_deployed_info(vnf_deployed_info)
            rvm_agents_execute_scripts.excute_script("scale_create", current_il, scale_ns_instantiation_level_id)
            map_reference_ip = rvm_agents_execute_scripts.get_map_reference_ip()
            nsir_db.save_map_reference_ip(nsi_id, map_reference_ip)
        converted_output = self.convert_output(instantiation_output)
        return [converted_output, scale_ops]

    def extract_target_il(self, body):
        """
        Returns target instantiation level
        Parameters
        ----------
        body: dict
            scaling information
        Returns
        -------
        target_il: string
            target instantiation level
        """
        if (body.scale_type == "SCALE_NS"):
            return body.scale_ns_data.scale_ns_to_level_data.ns_instantiation_level

    def terminate_ns(self, nsi_id):
        """
        Terminates the network service identified by nsi_id.
        Parameters
        ----------
        nsi_id: string
            identifier of the network service instance
        """

        # undeploying
        if self.__install_rvm_agent == "yes":
            nsdId = ns_db.get_nsdId(nsi_id)
            ns_descriptor = nsd_db.get_nsd_json(nsdId)
            rvm_agents_execute_scripts = RvmAgentsExecuteScripts(ns_descriptor)

            vnfds_json = {}
            # for each vnf in the NSD, get its json descriptor
            vnfdIds = ns_descriptor["nsd"]["vnfdId"]
            vnfds_json = {}
            for vnfdId in vnfdIds:
                vnfds_json[vnfdId] = vnfd_db.get_vnfd_json(vnfdId, None)
            rvm_agents_execute_scripts.set_vnfds_descriptor(vnfds_json)
            placement_info = nsir_db.get_placement_info(nsi_id)
            rvm_agents_execute_scripts.set_placement_info(placement_info)
            nsi_sap = self.get_cloudify_client().deployments.outputs.get(deployment_id=nsi_id)
            instantiation_output = {}
            instantiation_output["sapInfo"] = nsi_sap["outputs"]
            rvm_agents_execute_scripts.set_sap_info(instantiation_output)
            vim_net_info = nsir_db.get_vim_networks_info(nsi_id)
            rvm_agents_execute_scripts.set_vim_net_info(vim_net_info)
            vnf_deployed_info = nsir_db.get_vnf_deployed_info(nsi_id)
            rvm_agents_execute_scripts.set_vnf_deployed_info(vnf_deployed_info)
            current_il = ns_db.get_ns_il(nsi_id)
            rvm_agents_execute_scripts.set_nsi_id(nsi_id)
            rvm_agents_execute_scripts.excute_script("terminate", current_il, None)

            job_ids = ns_db.get_monitoring_info(nsi_id)
            delted_rvm_agents = []
            for job_id in job_ids:
                if job_id['agent_id'] not in delted_rvm_agents:
                    delete_rvm_agent(job_id['agent_id'])
                    delted_rvm_agents.append(job_id['agent_id'])
            ns_db.set_monitoring_info(nsi_id, [])

        if is_terminate:
            try:
                self.__cloudify_client.executions.start(nsi_id, "uninstall")
                log_queue.put(["DEBUG", "CLOUDIFY_WRAPPER: Deployment  %s uninstalling started" % (nsi_id)])
            except Exception as e:
                log_queue.put(["ERROR", "CLOUDIFY_WRAPPER: Deploying %s uninstalling error %s " % (nsi_id, e)])
                return None

            try:
                self.wait_for_deployment_execution(nsi_id)
                log_queue.put(["DEBUG", "CLOUDIFY_WRAPPER: Deployment %s uninstalling completed" % (nsi_id)])
            except Exception as e:
                log_queue.put(["ERROR", "CLOUDIFY_WRAPPER: Deployment %s  uninstalling error %s " % (nsi_id, e)])
                return None

            # deployment deleting
            try:
                self.__cloudify_client.deployments.delete(nsi_id)
                log_queue.put(["DEBUG", "CLOUDIFY_WRAPPER: Deployment %s deleting started" % (nsi_id)])
            except Exception as e:
                log_queue.put(["ERROR", "CLOUDIFY_WRAPPER: Deployment deleting error %s " % (e)])
                return None
            log_queue.put(["DEBUG", "CLOUDIFY_WRAPPER: Deployment %s deleting completed" % (nsi_id)])

    ##########################################################################
    # PRIVATE METHODS                                                                                                      #
    ##########################################################################

    def get_information_of_vnf(self, instances, agent_ids):
        """
        Returns information about vnfs from Cloudify information.
        Parameters
        ----------
        instances: list
            List of instances
        agent_ids: dict
            Dict vnfs' names and rvmagents' ids
        Returns
        -------
        vnf_deployed_info = [{'name': 'spr2',
                            'port_info': [{'ip_address': '192.168.3.12', 'mac_address': 'fa:16:3e:8e:56:4b'},
                            {'ip_address': '192.168.1.13', 'mac_address': 'fa:16:3e:07:dc:cb'}],
                            'dc': '1', 'agent_id': 'vm_agent_51'},
                            {'name': 'webserver', 'port_info': [{'ip_address': '192.168.1.12',
                            'mac_address': 'fa:16:3e:8a:cc:16'}],
                            'dc': '1', 'agent_id': 'vm_agent_52'}]
        """
        return_vnf_deployed_info = []

        for instance in instances:
            if instance.runtime_properties.get('external_type') == "mtp_compute":
                net_interfaces = instance.runtime_properties.get('external_resource')['virtualNetworkInterface']
                vm_name = instance.runtime_properties.get('external_resource')['computeName']
                (vnf_id, inctance_number) = vm_name.rsplit("-",2)[1:3]
                port_info = []
                floating_ips = []
                dc = "1"
                for net_interface in net_interfaces.values():
                    floating_ip = net_interface.get('floatingIP', None)
                    if floating_ip is not None:
                        floating_ips.append({vnf_id: floating_ip})
                    for metadata in net_interface['metadata']:
                        if metadata['key'] == 'dc':
                            dc = str(metadata['value'])
                    port_info.append(
                        {"ip_address": net_interface['ipAddress'][0],
                         "mac_address": net_interface['macAddress']})

                vnf_deployed_info = \
                    {"name": vnf_id,
                     "port_info": port_info,
                     "dc": dc,
                     "instance": inctance_number}

                vnf_deployed_info.update({"agent_id": vm_name})
                vnf_deployed_info.update({"floating_ips": floating_ips})
                return_vnf_deployed_info.append(vnf_deployed_info)
        return return_vnf_deployed_info

    def get_information_of_networks(self, ns_id, instances, nodes, nestedInfo):
        """
        Returns information about networks.
        Parameters
        ----------
        nsi_id: string
            identifier of the network service instance
        instances: instances
            identifier of the network service instance
        nodes: nodes
            identifier of the network service instance
        nestedInfo: nestedInfo
            identifier of the network service instance

        Returns
        -------

        # {"cidr": {"VideoData": "192.168.3.0/24"},
        # "name": {"VideoData": ['1']},
        # "vlan": {"VideoData": "30"},
        # "vlan": {"addressPool": [0]}}
      """

        vim_net_info = {"cidr": {}, "name": {}, "vlan_id": {}, "addressPool": {}}

        for instance in instances:
            # pprint(node)
            if 'external_type' in instance['runtime_properties'].keys():
                if "subnet_vl" in instance['runtime_properties']['external_type']:
                    network_runtime_properties = instance['runtime_properties']
                    net_name = network_runtime_properties['external_resource']['networkData']['networkResourceName']
                    net_name = net_name.replace(ns_id + "_", "")
                    if nestedInfo:
                        nested_descriptor = next(iter(nestedInfo))
                        network_mapping = nestedInfo[nested_descriptor][0]
                        for network_map in network_mapping:
                            for net_value, net_key in network_map.items():
                                if net_name == net_key:
                                    net_name = net_value
                                    break
                    net_cidr = network_runtime_properties['external_resource']['subnetData']['cidr']
                    address_pool = network_runtime_properties['external_resource']['subnetData']['addressPool']
                    vlan = 1
                    if ('SegmentationID' in network_runtime_properties['external_resource']['subnetData']['metadata']):
                        vlan = network_runtime_properties['external_resource']['subnetData']['metadata'][
                            'SegmentationID']
                    vim_net_info["cidr"].update({net_name: net_cidr})
                    vim_net_info["name"].update({net_name: ['1']})
                    vim_net_info["vlan_id"].update({net_name: vlan})
                    vim_net_info["addressPool"].update({net_name: address_pool})

        return vim_net_info

    def extract_scaling_info(self, ns_descriptor, current_df, current_il, target_il):
        """
        We extract the required scaling operations comparing target_il with current_il
        assumption 1: we assume that there will not be new VNFs, so all the keys of target and current are the same
        Parameters
        ----------
        ns_descriptor: dict
            json containing the nsd
        current_df:
            current deployment flavour
        current il: string
            identifier of the current instantiation level
        target_il: string
            identifier of the target instantiation level

        Returns
        -------
            # scale_info: list of dicts {'vnfName': 'spr21', 'scaleVnfType': 'SCALE_OUT', 'vnfIndex': "3"}

        """
        nsd_name = ns_descriptor["nsd"]["nsdIdentifier"] + "_" + current_df + "_" + current_il
        target_il_info = {}
        current_il_info = {}
        for df in ns_descriptor["nsd"]["nsDf"]:
            if (df["nsDfId"] == current_df):
                for il in df["nsInstantiationLevel"]:
                    if (il["nsLevelId"] == target_il):
                        for vnf in il["vnfToLevelMapping"]:
                            for profile in df["vnfProfile"]:
                                if (vnf["vnfProfileId"] == profile["vnfProfileId"]):
                                    target_il_info[profile["vnfdId"]] = int(vnf["numberOfInstances"])
                    if (il["nsLevelId"] == current_il):
                        for vnf in il["vnfToLevelMapping"]:
                            for profile in df["vnfProfile"]:
                                if (vnf["vnfProfileId"] == profile["vnfProfileId"]):
                                    current_il_info[profile["vnfdId"]] = int(vnf["numberOfInstances"])
        log_queue.put(["DEBUG", "Target il %s info: %s" % (target_il, target_il_info)])
        log_queue.put(["DEBUG", "Current il %s info: %s" % (current_il, current_il_info)])
        scaling_il_info = []
        for key in target_il_info.keys():
            scaling_sign = target_il_info[key] - current_il_info[key]
            if (scaling_sign != 0):
                scale_info = {}
                scale_info["vnfName"] = key
                if (scaling_sign > 0):  # SCALE_OUT
                    scale_info["scaleVnfType"] = "SCALE_OUT"
                elif (scaling_sign < 0):  # SCALE_IN
                    scale_info["scaleVnfType"] = "SCALE_IN"
                for ops in range(0, abs(scaling_sign)):
                    # scale_info["instanceNumber"] = str(current_il_info[key] + ops + 1) -> not needed instance number
                    # scaling operation are done one by one
                    # protection for scale_in operation: the final number of VNFs cannot reach 0
                    if not (scale_info["scaleVnfType"] == "SCALE_IN" and (current_il_info[key] - ops > 0)):
                        scaling_il_info.append(scale_info)
        log_queue.put(["DEBUG", "Scale_il_info is: %s" % (scaling_il_info)])
        return scaling_il_info

    def get_nfvi_pop_info(self):
        """
        Returns information about POP from coreMano/vim.properties
        Parameters
        ----------
        Returns
        -------
        nfvipops: dict
            {'1': {'nfviPopId': '1', 'vimId': '1', 'geographicalLocationInfo': 'Castelldefels-Monet', .........
        """

        vim_info = {}
        config = RawConfigParser()
        config.optionxform = str
        config.read("../../coreMano/vim.properties")
        config.keys()
        nfvipops = {}
        vims = {}
        for key in config.keys():
            if str(key).startswith("NFVIPOP"):
                nfvipop_parametes = dict(config.items(key))
                nfvipops.update({nfvipop_parametes['nfviPopId']: nfvipop_parametes})

        number_of_vims = config.getint("VIM", "number")
        for i in range(1, number_of_vims + 1):
            vim = dict(config.items("VIM" + str(i)))
            vims.update({vim['vimId']: vim})

        for key, nfvipop in nfvipops.items():
            vim_id = nfvipop['vimId']
            nfvipops[key]['vim'] = vims[vim_id]
        return nfvipops

    def convert_output(self, param):
        """
        Prepares data for SO.
        Parameters
        ----------
        param: dict
            Contains information about floating ip
            {'sapInfo': {'mgtSap': {'spr1': '192.168.100.95'}, 'videoSap': {'webserver': '192.168.100.82', 'spr2': '192.168.100.66'}}}
        Returns
        -------
        ret_obj: dict
            {'sapInfo': {'mgtSap': [{'spr1': '192.168.100.95'}], 'videoSap': [{'webserver': '192.168.100.82'}, {'spr2': '192.168.100.66'}]}}
        """
        ret_obj = {}
        ret_obj['sapInfo'] = {}
        for level1_key, level2_value in param['sapInfo'].items():
            ret_obj['sapInfo'][level1_key] = []
            for level3_key, level3_value in level2_value.items():
                vnf_id = level3_key.rsplit("-", 2)[1]
                ret_obj['sapInfo'][level1_key].append({vnf_id: level3_value})
        return ret_obj

    def wait_for_deployment_execution(self, deployment_id):
        """
        Waits until Cloudify finishes the deployment.
        Parameters
        ----------
        deployment_id: string
            identifier of cloudify deployment
        """

        # undeploying
        while True:
            time.sleep(2)
            executions = self.__cloudify_client.executions.list(_include=['status'], deployment_id=deployment_id)
            log_queue.put(["DEBUG", "CLOUDIFY_WRAPPER: Checking status of deployment %s" % (deployment_id)])
            pending = False
            for execution in executions:
                if execution['status'] in ["failed"]:
                    log_queue.put(["DEBUG", "CLOUDIFY_WRAPPER: Deployment %s status failed" % (deployment_id)])
                    raise Exception("CLOUDIFY_WRAPPER: Deployment %s status failed" % (deployment_id))
                if execution['status'] in ["pending", "started"]:
                    pending = True
            if pending == False:
                break

    def get_blueprints(self, blueprint_name):
        return self.__cloudify_client.blueprints.list(_include=['id'], id=[blueprint_name]).items

    def get_cloudify_client(self):
        return self.__cloudify_client

    def get_execution(self, execution):
        """
        Retrieves the execution information from cloudify
        ----------
        execution: string
            identifier of the execution
        Returns
        -------
        Dictionary with the execution status
        """

        url = 'http://%s/api/v3.1/executions/%s' % (self.__nfvo_ip, execution)
        log_queue.put(["DEBUG", "CLOUDIFY_WRAPPER: get_execution:%s" % url])
        headers = {'Tenant': self.__tenant}
        response = requests.get(
            url,
            auth=HTTPBasicAuth(self.__user, self.__password),
            headers=headers,
        )
        return response.json()


class RvmAgentsExecuteScripts(object):
    def __init__(self, ns_descriptor):
        """
        Inits  RvmAgentsExecuteScripts.
        Parameters
        ----------
        ns_descriptor: object
            json containing the nsd of the network service retrieved from catalogue
        Returns
        -------
        To be defined
        """
        self.ns_descriptor = ns_descriptor
        self.networks = {}
        self.servers = {}
        self.__vnfds_descriptor = {}
        self.__nsi_id = ""
        self.__map_network_sap = {}
        self.__placement_info = {}
        self.__map_reference_ip = {}
        self.__nested_info = None
        self.sap_info = {}
        self.net_info = None
        self.vnf_deployed_info = None

    def set_nsi_id(self, nsi_id):
        self.__nsi_id = nsi_id

    def __mp_excute_script(self, agent_id, args=[], env={}, type_message="bash_script", cwd="/tmp", body=[],
                           sync=False):
        """
        Contact with the monitoring manager to execute script
        Parameters
        ----------
        agent_id: String
            Agent identifier
        args: list
            arguments for the script
        env: dict
            String environment variables
        type_message: string
            type of script
        cwd: string
            work directory
        body: list
            contains script
        sync: boolean
            True: wait for command execution
            False: don't wait for command execution

        Returns
        -------
        Dictionary
        agent_id: String
            Agent identifier
        args: list
            arguments for the script
        env: dict
            String environment variables
        type_message: string
            type of script
        cwd: string
            work directory
        body: list
            contains script
        sync: boolean
            True: wait for command execution
            False: don't wait for command execution

        """

        timeout = 600

        header = {'Content-Type': 'application/json',
                  'Accept': 'application/json'}
        # create the exporter for the job
        monitoring_uri = "http://" + monitoring_ip + ":" + monitoring_port + monitoring_base_path + "/agent_command"
        body = {
            "agent_id": agent_id,
            "args": args,
            "env": env,
            "type_message": type_message,
            "cwd": cwd,
            "body": body
        }
        command_info = None
        try:
            conn = HTTPConnection(monitoring_ip, monitoring_port)
            conn.request("POST", monitoring_uri, json.dumps(body), header)
            rsp = conn.getresponse()
            command_info = rsp.read()
            command_info = command_info.decode("utf-8")
            command_info = json.loads(command_info)
        except ConnectionRefusedError:
            log_queue.put(["ERROR", "the Monitoring platform is not running or the connection configuration is wrong"])

        if sync == True:
            trequest = time.time()
            get_command_status = None

            while True:
                command_id = command_info['command_id']
                monitoring_uri = "http://" + monitoring_ip + ":" + monitoring_port + monitoring_base_path \
                                 + "/agent_command/" + agent_id + "/" + str(command_id)
                try:
                    conn = HTTPConnection(monitoring_ip, monitoring_port)
                    conn.request("GET", monitoring_uri)
                    rsp = conn.getresponse()
                    get_command_status = rsp.read()
                    get_command_status = get_command_status.decode("utf-8")
                    get_command_status = json.loads(get_command_status)
                    if rsp.code == 200:
                        if get_command_status['returncode'] != "0":
                            raise Exception('Command execution returncode not equal 0 ' \
                                            + json.dumps(get_command_status, indent=4))
                        else:
                            return get_command_status
                except ConnectionRefusedError:
                    log_queue.put(
                        ["ERROR", "the Monitoring platform is not running or the connection configuration is wrong"])
                time.sleep(5)
                if (trequest + 300) < time.time():
                    return "Timeout"
                    # raise Exception('Command execution timeout ' + json.dumps(command_info, indent=4))
        else:
            return command_info

    def excute_script(self, mode, current_il, new_il):
        """
        Terminates the network service identified by nsi_id.
        Parameters
        ----------
        nsi_id: string
            identifier of the network service instance
        Returns
        -------
        To be defined
        """
        if mode == 'instantiate':
            commands = []
            instances = self.parse(current_il)
            for instance in instances.values():
                if 'script' in instance:
                    for script_obj in instance['script']:
                        target = script_obj['target']
                        agent_id = target
                        args = list(script_obj['start']['args'].values())
                        script = script_obj['start']['script']
                        command = self.__mp_excute_script(agent_id, args=args, env={}, type_message="bash_script",
                                                          cwd="/tmp", body=script, sync=False)
                        command.update({"check": True})
                        commands.append(command)
            log_queue.put(["INFO", "CLOUDIFY_WRAPPER: All NSD's scripts are executing"])
            wait_commands_execution(commands)
            log_queue.put(["INFO", "CLOUDIFY_WRAPPER: All NSD's scripts were executed"])

        elif mode == 'scale_delete':
            instances_old = self.parse(current_il)
            instances_new = self.parse(new_il)
            instances_delete = copy.deepcopy(instances_old)
            commands = []
            for inctance_name in instances_new.keys():
                if inctance_name in instances_old.keys():
                    instances_delete.pop(inctance_name)
            for instance in instances_delete.values():
                if 'script' in instance:
                    for script_obj in instance['script']:
                        target = script_obj['target']
                        agent_id = self.vnf_deployed_info[target]['agent_id']
                        args = list(script_obj['stop']['args'].values())
                        script = script_obj['stop']['script']
                        command = self.__mp_excute_script(agent_id, args=args, env={}, type_message="bash_script",
                                                          cwd="/tmp", body=script, sync=False)
                        command.update({"check": True})
                        commands.append(command)
            wait_commands_execution(commands)
            log_queue.put(["INFO", "CLOUDIFY_WRAPPER: All NSD's scripts were executed"])
        elif mode == 'scale_create':
            instances_old = self.parse(current_il)
            instances_new = self.parse(new_il)
            instances_create = copy.deepcopy(instances_new)
            commands = []
            for inctance_name in instances_new.keys():
                if inctance_name in instances_old.keys():
                    instances_create.pop(inctance_name)
            for instance in instances_create.values():
                if 'script' in instance:
                    for script_obj in instance['script']:
                        target = script_obj['target']
                        agent_id = self.vnf_deployed_info[target]['agent_id']
                        args = list(script_obj['start']['args'].values())
                        script = script_obj['start']['script']
                        command = self.__mp_excute_script(agent_id, args=args, env={}, type_message="bash_script",
                                                          cwd="/tmp", body=script, sync=False)

                        command.update({"check": True})
                        commands.append(command)
                    log_queue.put(["INFO", "CLOUDIFY_WRAPPER: All NSD's scripts are executing"])
                    wait_commands_execution(commands)
                    log_queue.put(["INFO", "CLOUDIFY_WRAPPER: All NSD's scripts were executed"])
        elif mode == 'terminate':
            instances = self.parse(current_il)
            commands = []
            for instance in instances.values():
                if 'script' in instance:
                    for script_obj in instance['script']:
                        target = script_obj['target']
                        agent_id = self.vnf_deployed_info[target]['agent_id']
                        args = list(script_obj['stop']['args'].values())
                        script = script_obj['stop']['script']
                        command = self.__mp_excute_script(agent_id, args=args, env={}, type_message="bash_script",
                                                          cwd="/tmp", body=script, sync=False)
                        command.update({"check": True})
                        commands.append(command)
            log_queue.put(["INFO", "CLOUDIFY_WRAPPER: All NSD's scripts are executing"])
            wait_commands_execution(commands)
            log_queue.put(["INFO", "CLOUDIFY_WRAPPER: All NSD's scripts were executed"])

    def parse(self, il):
        """
        Parses NSD and VNFDs for specific instantiate level.
        Parameters
        ----------
        nsi_id: string
            instantiate level
        Returns
        -------
        servers: list
            List of object which contains information about instances
        """
        self.networks = {}
        self.servers = {}
        # Create map network sapd
        sapds = self.ns_descriptor['nsd']['sapd']
        for sapd in sapds:
            self.__map_network_sap.update({sapd['nsVirtualLinkDescId']: sapd['cpdId']})

        # get description for nsInstantiationLevel
        ns_i_ls = self.ns_descriptor['nsd']['nsDf'][0]['nsInstantiationLevel']
        ns_instantiation_level = {}
        for ns_il in ns_i_ls:
            if il == ns_il['nsLevelId']:
                ns_instantiation_level = ns_il
        vnf_to_level_mapping = ns_instantiation_level['vnfToLevelMapping']

        #       Servers
        for vnf in vnf_to_level_mapping:
            vnf_profile_id = vnf['vnfProfileId']
            server = self.__getserver(vnf_profile_id)
            self.servers.update(server)

        #       parse flvavor, sw, ports
        nsd_identifier = self.ns_descriptor['nsd']['nsdIdentifier']
        for server_name in self.servers.keys():
            vnfd = self.__get_vnfd(server_name)
            self.servers[server_name].update({'NFVIPoPID': "1"})
            ports = self.servers[server_name]['relations']['ports']

            for port_name, port_object in ports.items():
                vnfd_ports = vnfd['vnfExtCpd']
                for vnfs_port in vnfd_ports:
                    if vnfs_port['cpdId'] == port_name:
                        floating_ip_activated = vnfs_port['addressData'][0]['floatingIpActivated']
                        self.servers[server_name]['relations']['ports'][port_name]. \
                            update({'floatingIp': floating_ip_activated})
                        network_name = port_object['network']
                        self.networks[network_name].update({'name': network_name})
                        if "pool_start" in self.networks[network_name]:
                            continue
                        self.networks[network_name].update({'connect_to_Router': floating_ip_activated})
                        self.networks[network_name].update({"provider": False})
                        self.networks[network_name].update({'NFVIPoPID': "1"})
                        break

        # PA add interpop network
        new_netwoks = {}

        for server_name, sever_value in self.servers.items():
            server_nfvi_po_pid = sever_value['NFVIPoPID']
            for port_name, port_value in sever_value['relations']['ports'].items():
                for used_ll in self.__placement_info['usedLLs']:
                    if port_value['network'] in used_ll['mappedVLs']:
                        new_network_name = port_value['network'] + "_" + server_nfvi_po_pid
                        new_netwoks[new_network_name] = copy.deepcopy(self.networks[port_value['network']])
                        new_netwoks[new_network_name].update({"provider": True})
                        new_netwoks[new_network_name].update({'NFVIPoPID': server_nfvi_po_pid})
                        port_value['network'] = new_network_name
        self.networks.update(new_netwoks)

        # PA delete old interpop network
        for used_ll in self.__placement_info['usedLLs']:
            for mappedVL in used_ll['mappedVLs']:
                if mappedVL in self.networks.keys():
                    del self.networks[mappedVL]

            # change network name in servers
            for server_name, sever_value in self.servers.items():
                for port_name, port_value in sever_value['relations']['ports'].items():
                    network_name = port_value['network']
                    for network_name_from_nested_info in self.__nested_info[nsd_identifier][0]:
                        if network_name in network_name_from_nested_info.keys():
                            new_network_name = network_name_from_nested_info[network_name]
                            port_value['network'] = new_network_name
                            break

            # change network name in map_network_sap
            for map_network_sap_key, map_network_sap_value in self.__map_network_sap.items():
                for network_name_from_nested_info in self.__nested_info[nsd_identifier][0]:
                    if map_network_sap_key in network_name_from_nested_info.keys():
                        new_network_name = network_name_from_nested_info[map_network_sap_key]
                        self.__map_network_sap.update({new_network_name: map_network_sap_value})
                        del self.__map_network_sap[map_network_sap_key]

            # change change network name in placement_info usedVLs
            for network_name_from_nested_info in self.__nested_info[nsd_identifier][0]:
                for key_nested_info, value_nested_info in network_name_from_nested_info.items():
                    for key_placement_info, value_placement_info in enumerate(self.__placement_info['usedVLs']):
                        for key_mappedVLs, value_mappedVLs in enumerate(value_placement_info['mappedVLs']):
                            if key_nested_info == value_mappedVLs:
                                value_placement_info['mappedVLs'][key_mappedVLs] = value_nested_info

            # change change network name in placement_info usedLLs
            for network_name_from_nested_info in self.__nested_info[nsd_identifier][0]:
                for key_nested_info, value_nested_info in network_name_from_nested_info.items():
                    for key_placement_info, value_placement_info in enumerate(self.__placement_info['usedLLs']):
                        for key_mappedVLs, value_mappedVLs in enumerate(value_placement_info['mappedVLs']):
                            if key_nested_info == value_mappedVLs:
                                value_placement_info['mappedVLs'][key_mappedVLs] = value_nested_info

        #       add instances depent on numberOfInstances
        new_servers = {}
        map_oldname_newname_server = {}
        map_oldname_newname_port = {}
        for server_name in self.servers:
            number_of_instances = 1
            for vnfd_profile in vnf_to_level_mapping:
                if self.servers[server_name]['vnfProfileId'] == vnfd_profile['vnfProfileId']:
                    number_of_instances = vnfd_profile['numberOfInstances']
                    break

            for instance_number in range(1, number_of_instances + 1):
                new_server_name = self.__nsi_id + "-0-" + server_name + "-" + str(instance_number)
                map_oldname_newname_server.update({server_name + "-" + str(instance_number): new_server_name})
                if instance_number == 1:
                    map_oldname_newname_server.update({server_name: new_server_name})
                new_servers.update({new_server_name: copy.deepcopy(self.servers[server_name])})
                new_ports = {}
                for port_name, port_value in new_servers[new_server_name]['relations']['ports'].items():
                    new_port_name = port_name + "_" + str(instance_number)
                    map_oldname_newname_port.update({port_name: new_port_name})
                    # change name in scripts
                    if "script" in new_servers[new_server_name]:
                        for script in new_servers[new_server_name]['script']:
                            for script_name, script_value in script.items():
                                if script_name == "target":
                                    if script_value == server_name:
                                        script['target'] = new_server_name
                                    continue
                                self.__change_script_args(script_value,
                                                          server_name, new_server_name,
                                                          port_name, new_port_name)
                    new_ports[new_port_name] = port_value
                new_servers[new_server_name]['relations']['ports'] = new_ports
        self.servers = new_servers

        #updating params in script args and target
        for server_name, server_value in self.servers.items():
            if "script" in server_value:
                for script in server_value['script']:
                    for script_name, script_value in script.items():
                        if script_name == "target":
                            if script_value in map_oldname_newname_server.keys():
                                script["target"] = map_oldname_newname_server[script_value]
                        elif script_name == "start" or script_name == "stop":
                            for arg, arg_value in script_value['args'].items():
                                arg_parts = arg_value.split(".")
                                if len(arg_parts) > 5:
                                    server_name = arg_parts[1]
                                    port_name = arg_parts[5]
                                    if server_name in map_oldname_newname_server.keys():
                                        server_name = map_oldname_newname_server[server_name]
                                    if port_name in map_oldname_newname_port.keys():
                                        port_name = map_oldname_newname_port[port_name]
                                    arg_parts[1] = server_name
                                    arg_parts[5] = port_name
                                    return_arg = ".".join(arg_parts)
                                    script_value['args'][arg] = return_arg

        # map reference to ip
        for server_name, server_value in self.servers.items():
            instance_id = "-".join(server_name.rsplit("-", 2)[1:3])
            (vnf_id, instance_number) = instance_id.split("-")
            for port_name, port_value in server_value['relations']['ports'].items():
                if 'floatingIp' in port_value:

                    key = "vnf." + instance_id + ".vdu." + vnf_id + "_vdu.intcp." + port_name + ".address"
                    network_object_name = port_value['network']
                    network_name = self.networks[network_object_name]['name']
                    if server_name in self.vnf_deployed_info.keys():
                        value = self.vnf_deployed_info[server_name]['port_info'][network_name]
                    else:
                        value = "Empty"
                    self.__map_reference_ip.update({key: value})
                    key = "vnf." + server_name + ".vdu." + vnf_id + "_vdu.intcp." + port_name + ".address"
                    self.__map_reference_ip.update({key: value})
                    if instance_number == "1":
                        key = "vnf." + vnf_id + ".vdu." + vnf_id + "_vdu.intcp." + port_name.split("_")[0] + ".address"
                        self.__map_reference_ip.update({key: value})
                    if port_value['floatingIp'] == True:

                        if server_name in self.sap_info.keys():
                            value = self.sap_info[server_name]
                            key = "vnf." + server_name + ".vdu." + vnf_id + "_vdu.extcp." + port_name + ".floating"
                            self.__map_reference_ip.update({key: value})
                            key = "vnf." + instance_id + ".vdu." + vnf_id + "_vdu.extcp." + port_name + ".floating"
                            self.__map_reference_ip.update({key: value})
                            if instance_number == "1":
                                key = "vnf." + vnf_id + ".vdu." + vnf_id + "_vdu.extcp." + port_name.split("_")[
                                    0] + ".floating"
                                self.__map_reference_ip.update({key: value})
        #       convert script agruments to cloudify format
        for server_name, server_value in self.servers.items():
            if "script" in server_value:
                for script in server_value['script']:
                    for script_name, script_value in script.items():
                        if script_name == "target":
                            continue
                        for arg_name, arg_value in script_value['args'].items():
                            arg_parts = arg_value.split(".")
                            for server_name_2, server_value_2 in self.servers.items():
                                #                                   find network by port
                                for port_name, port_value in server_value_2['relations']['ports'].items():
                                    if arg_parts[0] == "vnf" and arg_parts[6] == "address":
                                        if arg_parts[5] == port_name:
                                            network_object_name = port_value['network']
                                            network_name = self.networks[network_object_name]['name']
                                            # arg_return = "{ get_attribute: [" + arg_parts[1] + ", external_resource, " + \
                                            #              "virtualNetworkInterface, " + \
                                            #              network_name + ", ipAddress, 0] }"
                                            intances_name = arg_parts[1]
                                            if intances_name in self.vnf_deployed_info.keys():
                                                arg_return = self.vnf_deployed_info[intances_name]['port_info'][
                                                    network_name]
                                            else:
                                                arg_return = "Empty"
                                            script_value['args'][arg_name] = arg_return
                                    if arg_parts[0] == "vnf" and arg_parts[6] == "floating":
                                        if arg_parts[5] == port_name:
                                            network_object_name = port_value['network']
                                            network_name = self.networks[network_object_name]['name']
                                            # arg_return = "{ get_attribute: [" + arg_parts[1] + ", external_resource, " + \
                                            #              "virtualNetworkInterface, " + \
                                            #              network_name + ", floatingIP] }"
                                            intances_name = arg_parts[1]
                                            arg_return = self.sap_info[intances_name]
                                            script_value['args'][arg_name] = arg_return

        return self.servers

    def __getserver(self, vnf_profile_id):
        """
        Parces NSD and VNF for specific vnf_profile_id.
        Parameters
        ----------
        vnf_profile_id: string
            identifier of vnf_profile
        Returns
        -------
        To be defined
        """
        vnf_profiles = self.ns_descriptor['nsd']['nsDf'][0]['vnfProfile']
        vnfp = {}
        for vnf_profile in vnf_profiles:
            if vnf_profile['vnfProfileId'] == vnf_profile_id:
                vnfp = vnf_profile
                break

        # server name
        vnfd_id = vnfp['vnfdId']
        server = {vnfd_id: {"relations": {}}}
        if 'script' in vnfp.keys():
            server[vnfd_id]['script'] = copy.deepcopy(vnfp['script'])
        server[vnfd_id]['relations']['ports'] = {}
        server[vnfd_id]['vnfProfileId'] = vnf_profile_id
        ns_virtual_links = vnfp['nsVirtualLinkConnectivity']
        for ns_virtual_link in ns_virtual_links:
            ports = ns_virtual_link['cpdId']
            virtual_link_profile_id = ns_virtual_link['virtualLinkProfileId']
            network_name = self.__getnetwork(virtual_link_profile_id)
            self.networks.update({network_name: {}})
            for port in ports:
                server[vnfd_id]['relations']['ports'].update({port: {'network': network_name}})
        return server

    def __getnetwork(self, virtual_link_profile_id):
        """
        Returns network by virtual_link_profile_id
        Parameters
        ----------
        virtual_link_profile_id: string
            identifier of virtual link profile
            'vl_profile_VideoDistribution'
        Returns
        -------
        networkname string
            'VideoDistribution'
        """
        virtual_link_profiles = self.ns_descriptor['nsd']['nsDf'][0]['virtualLinkProfile']
        for virtual_link_profile in virtual_link_profiles:
            if virtual_link_profile['virtualLinkProfileId'] == virtual_link_profile_id:
                return virtual_link_profile['virtualLinkDescId']

    def __get_vnfd(self, vnfdid):
        """
        Returns vnf dict by vnfdid.
        Parameters
        ----------
        nsi_id: string
            identifier of the network service instance
            'webserver'
        Returns
        -------
        VNF: dict
            {'vnfProfileId': 'spr2_profile', 'numberOfInstances': 1}
        """
        return self.__vnfds_descriptor[vnfdid]

    def set_vnfds_descriptor(self, vnfds_descriptor):
        """
        Sets the vnf descriptor.
        Parameters
        ----------
        vnfds_descriptor: list
            list of vnfds descriptors
        """
        self.__vnfds_descriptor = vnfds_descriptor

    def set_placement_info(self, placement_info):
        """
        Sets result of the placement algorithm
        Parameters
        ----------
        placement_info: dict
            identifier of the network service instance
        """
        self.__placement_info = copy.deepcopy(placement_info)

    def __change_script_args(self, script, server_name, new_server_name, port_name, new_port_name):
        """
        Changes change script args depend on number instances
        This function is used during scaling
        Parameters
        ----------
        script: string
            Execution script from NSD
        server_name: string
            identifier of the network service instance
            'spr2'
        new_server_name: string
            new identifier of the network service instance
            'spr2_02'
        port_name: string
            port identifier of the network service instance
            'spr2DistExt'
        new_port_name: string
            new port identifier of the network service instance
            'spr2DistExt_02'
        """
        for arg, arg_value in script['args'].items():
            arg_parts = arg_value.split(".")
            if len(arg_parts) > 5:
                if arg_parts[1] == server_name and arg_parts[5] == port_name:
                    arg_parts[1] = new_server_name
                    arg_parts[5] = new_port_name
                    return_arg = ".".join(arg_parts)
                    script['args'][arg] = return_arg

    def set_sap_info(self, in_sap_info):
        """
        Sets floating ip
        Parameters
        ----------
        in_sap_info: dict
            {'sapInfo': {'mgtSap': [{'spr1': '192.168.100.86'}],
            'videoSap': [{'webserver': '192.168.100.88'}, {'spr2': '192.168.100.58'}]}}
        """
        for value in in_sap_info['sapInfo'].values():
            self.sap_info.update(value)

    def set_vim_net_info(self, vim_net_info):
        """
        Sets VIM network information.
        Parameters
        ----------
        vim_net_info['cidr']: dict
            {'mgt': '192.168.2.0/24', 'VideoData': '192.168.3.0/24', 'VideoDistribution': '192.168.1.0/24'}
        """
        self.net_info = vim_net_info['cidr']

    def __get_network_name(self, ip_address):
        """
        Returns network name by ip_address
        Parameters
        ----------
        ip_address: string
            network ip address
        Returns
        -------
        network_name: string
            network name
        """
        for network_name, network_ip in self.net_info.items():
            if IPv4Address(ip_address) in IPv4Network(network_ip):
                return network_name

    def set_vnf_deployed_info(self, in_vnf_deployed_info):
        """
        Sets list of deployed VNFs.
        Parameters
        ----------
        in_vnf_deployed_info: list
            list of deployed VNFs
        """
        self.vnf_deployed_info = {}
        for in_vnf_deployed_info_elem in in_vnf_deployed_info:
            for port_info in in_vnf_deployed_info_elem['port_info']:
                network = self.__get_network_name(port_info['ip_address'])
                instance_name = in_vnf_deployed_info_elem['agent_id']
                if instance_name in self.vnf_deployed_info.keys():
                    self.vnf_deployed_info[instance_name]['port_info'].update({network: port_info['ip_address']})
                else:
                    instance = {
                        "agent_id": in_vnf_deployed_info_elem['agent_id'],
                        "port_info": {network: port_info['ip_address']}
                    }
                    self.vnf_deployed_info.update({instance_name: instance})

    def get_map_reference_ip(self):
        """
        Returns map between references and ip address

        Returns
        -------
        map between references and ip address
        {'vnf.webserver.vdu.webserver_vdu.intcp.webDistExt.address': '192.168.1.3',
        'vnf.webserver.vdu.webserver_vdu.extcp.webDistExt.floating': '192.168.100.58',
        'vnf.spr1.vdu.spr1_vdu.intcp.spr1MgtExt.address': '192.168.2.17',
        'vnf.spr1.vdu.spr1_vdu.extcp.spr1MgtExt.floating': '192.168.100.98',
        'vnf.spr1.vdu.spr1_vdu.intcp.spr1DataExt.address': '192.168.3.10',
        'vnf.spr2.vdu.spr2_vdu.intcp.spr2DistExt.address': '192.168.1.12',
        'vnf.spr2.vdu.spr2_vdu.extcp.spr2DistExt.floating': '192.168.100.97',
        'vnf.spr2.vdu.spr2_vdu.intcp.spr2DataExt.address': '192.168.3.13'}
        """
        return self.__map_reference_ip
