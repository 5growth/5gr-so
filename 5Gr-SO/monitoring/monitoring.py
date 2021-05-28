# Copyright 2019 CTTC www.cttc.es
#
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


"""
File description
"""

# python imports
import copy
import json
import time

from six.moves.configparser import RawConfigParser
from http.client import HTTPConnection
from uuid import uuid4
from json import dumps, loads, load
from confluent_kafka.admin import AdminClient, NewTopic
from confluent_kafka import Producer

# project imports
from db.nsir_db import nsir_db
from nbi import log_queue
from db.ns_db import ns_db

# load monitoring configuration manager properties
config = RawConfigParser()
config.read("../../monitoring/monitoring.properties")
monitoring_ip = config.get("MONITORING", "monitoring.ip")
monitoring_port = config.get("MONITORING", "monitoring.port")
monitoring_base_path = config.get("MONITORING", "monitoring.base_path")
monitoring_pushgateway = config.get("MONITORING", "monitoring.pushgateway")
monitoring_pushgateway_ip = config.get("MONITORING", "monitoring.pushgateway_ip")
monitoring_pushgateway_port = config.get("MONITORING", "monitoring.pushgateway_port")
monitoring_kafka_ip = config.get("MONITORING", "monitoring.kafka_ip")
monitoring_kafka_port = config.get("MONITORING", "monitoring.kafka_port")

#reading Forecasting Functional Block (ffb) properties
config.read("../../monitoring/ffb.properties")
ffb_platform_ip = config.get("FFB", "ffb.ip")
ffb_platform_port = config.get("FFB", "ffb.port")
ffb_platform_base_path = config.get("FFB", "ffb.base_path")

########################################################################################################################
# PRIVATE METHODS                                                                                                      #
########################################################################################################################

###### KAFKA methods

def create_kafka_topic(ns_id, problem):
    """
    Creates a kafka topic to insert info related with the problem
    Parameters
    ----------
    ns_id: string
        Network Service Id
    problem: string
        AIML problem, in this case "scaling"
    Returns
    -------
    String
        string with the name of the created topic, otherwise none
    """
    kafka_client = AdminClient({'bootstrap.servers': monitoring_kafka_ip + ':' + monitoring_kafka_port})
    kafka_topic = ns_id + '_' + problem
    log_queue.put(["DEBUG", "Kafka topic id is %s" % kafka_topic])
    new_topics = []
    new_topics.append(NewTopic(kafka_topic, 1,1))
    fs = kafka_client.create_topics(new_topics)
    log_queue.put(["DEBUG", "Let's see the result of creating the kafka topic"])
    # Wait for each operation to finish.
    for topic, f in fs.items():
        try:
            f.result()  # The result itself is None
            log_queue.put(["DEBUG", "Topic created: %s" % (str(topic))])
            return kafka_topic
        except Exception as e:
            log_queue.put(["DEBUG", "Failed to create topic %s: %s" % (str(topic), str(e))])
            return None

def delete_kafka_topic(kafka_topic):
    """
    Deletes the created kafka topic to insert info related with the problem
    Parameters
    ----------
    kafka_topic: string
        The name of the kafka_topic to apply the operation
    Returns
    -------
    """
    kafka_client = AdminClient({'bootstrap.servers': monitoring_kafka_ip + ':' + monitoring_kafka_port})
    new_topics = []
    new_topics.append(kafka_topic)
    fs = kafka_client.delete_topics(new_topics)
    # Wait for each operation to finish.
    for topic, f in fs.items():
        try:
            f.result()  # The result itself is None
            log_queue.put(["DEBUG", "Topic deleted: %s" %(str(topic))])
        except Exception as e:
            log_queue.put(["DEBUG", "Failed to delete topic %s: %s" % (str(topic), str(e))])

def publish_json_kafka(kafka_topic, info):
    """
    Publish the current instantiation level in the defined kafka_topic
    Parameters
    ----------
    kafka_topic: string
        The name of the kafka_topic to apply the operation
    currentIL: string
        Instantiation level of the instantiated network service
    Returns
    -------
    """
    p = Producer({"bootstrap.servers": monitoring_kafka_ip + ':' + monitoring_kafka_port})
    def delivery_report (err,msg):
        "Called once for each produced message to indicate delivery result"
        if err is not None:
            log_queue.put(["DEBUG", "Message delivery failed: %s" % str(err)])
        else:
            log_queue.put(["DEBUG", "Message delivered to %s [%s]" % (str(msg.topic()), str(msg.partition()))])
    log_queue.put(["DEBUG", "The info to put in the topic: "])
    log_queue.put(["DEBUG", dumps(info, indent=4)])
    json_data = dumps(info)
    p.poll(0)
    p.produce(kafka_topic, json_data.encode('utf-8'), callback=delivery_report)
    p.flush()

 ###### End KAFKA methods #######

def get_pm_jobs(nsd, deployed_vnfs_info, nsId):
    """
    Parses the nsd and vnfd descriptors to find possible monitoring jobs
    Parameters
    ----------
    nsd: json 
        Network service descriptor
    deployed_vnfs_info: json 
        dictionary with connection points of the differents vnfs after instantiating
    nsId:
        String with the Network Service Id 
    Returns
    -------
    List 
        List of dictionaries with info of the monitoring jobs
    """
    monitoring_jobs=[]
    if "monitoredInfo" in nsd["nsd"].keys():
        monitored_params = nsd["nsd"]["monitoredInfo"]
        for param in monitored_params:
            vnf = param["monitoringParameter"]["performanceMetric"]
            for sap in deployed_vnfs_info:
                for elem in deployed_vnfs_info[sap]:
                    for key in elem.keys():
                        if (vnf.find(key) !=-1):
                            # this is the vnf that has a external IP to connect and we can establish an exporter
                            pm_job={}
                            pm_job['name']= "NS-"+ nsId +"-VNF-" + key
                            pm_job['address'] = elem[key]
                            pm_job['port'] = 9100 # assuming that it is always a VM exporter
                            pm_job['collectionPeriod'] = 15 # agreed 15 seconds as default
                            pm_job['monitoringParameterId'] = param["monitoringParameter"]["monitoringParameterId"]
                            pm_job['performanceMetric'] = param["monitoringParameter"]["performanceMetric"]
                            pm_job['vnfdId'] = key
                            pm_job['nsId'] = nsId
                            monitoring_jobs.append(pm_job) 
        log_queue.put(["INFO", "monitoring jobs are: %s"% monitoring_jobs]) 
    return monitoring_jobs

def get_pm_jobs_v2(nsd, deployed_vnfs_info, nsId):
    """
    Parses the nsd and vnfd descriptors to find possible monitoring jobs
    Parameters
    ----------
    nsd: json 
        Network service descriptor
    deployed_vnfs_info: json 
        dictionary with connection points of the differents vnfs after instantiating
    nsId:
        String with the Network Service Id 
    Returns
    -------
    List 
        List of dictionaries with info of the monitoring jobs
    """
    monitoring_jobs=[]
    checked_ips = []
    if "monitoredInfo" in nsd["nsd"].keys():
        monitored_params = nsd["nsd"]["monitoredInfo"]
        for param in monitored_params:
            vnf = param["monitoringParameter"]["performanceMetric"]
            # sapINFO: {'videoSap': [{'webserver': '10.0.150.21'}, {'spr21': '10.0.150.3'}], 'mgtSap': [{'spr1': '10.0.150.15'}]}
            for sap in deployed_vnfs_info:
                for elem in deployed_vnfs_info[sap]:
                    for key in elem.keys():
                        if (vnf.find(key) !=-1):
                            if not elem[key] in checked_ips:
                                # this is a new vnf that has a external IP to connect 
                                # and we have to create a new exporter
                                checked_ips.append(elem[key])
                                pm_job={}
                                pm_job['name']= "NS-"+ nsId +"-VNF-" + key
                                pm_job['address'] = elem[key]
                                pm_job['port'] = 9100 # assuming that it is always a VM exporter
                                pm_job['collectionPeriod'] = 15 # agreed 15 seconds as default
                                pm_job['monitoringParameterId'] = []
                                pm_job['performanceMetric'] = []
                                pm_job['monitoringParameterId'].append(param["monitoringParameter"]["monitoringParameterId"])
                                pm_job['performanceMetric'].append(param["monitoringParameter"]["performanceMetric"])
                                pm_job['vnfdId'] = key
                                pm_job['nsId'] = nsId
                                pm_job['job_create'] = "yes"
                                pm_job['forecasted'] = "no"
                                monitoring_jobs.append(pm_job) 
                            else:
                                # this a vnf, that has a pm_job already defined, so you have to update the monitoringParameterId
                                # and performanceMetric element
                                for job in monitoring_jobs:
                                    if (job['address'] == elem[key]):
                                        job['monitoringParameterId'].append(param["monitoringParameter"]["monitoringParameterId"])
                                        job['performanceMetric'].append(param["monitoringParameter"]["performanceMetric"])
        log_queue.put(["DEBUG", "monitoring jobs are: %s"% monitoring_jobs]) 
    return monitoring_jobs

def nsd_monitored_info_convert_ifa_reference_to_ip(monitored_params, nsId):
    return_monitroring  = copy.deepcopy(monitored_params)
    get_map_reference_ip = nsir_db.get_map_reference_ip(nsId)
    for idx, monitored_param in enumerate(monitored_params):
        if "params" in monitored_param['monitoringParameter'].keys():
            for key, value in monitored_param['monitoringParameter']['params'].items():
                for key2, value2 in get_map_reference_ip.items():
                    if key2 in str(value):
                        value_array = key2.split(".")
                        return_monitroring[idx]['monitoringParameter'].update({"destination_vnf": value_array[1]})
                        return_value = value.replace(key2, value2)
                        return_monitroring[idx]['monitoringParameter']['params'][key] = return_value
                    # value_array = value.split(".")
                    # if "vnf" == value_array[0]:
                    #     return_monitroring[idx]['monitoringParameter'].update({"destination_vnf": value_array[1]})
                    # return_monitroring[idx]['monitoringParameter']['params'][key] = get_map_reference_ip[value]
    return return_monitroring

def get_pm_jobs_rvm_agents(nsd, deployed_vnfs_info, nsId):
    """
    Parses the nsd and vnfd descriptors to find possible monitoring jobs for rvm rvm agents
    Parameters
    ----------
    nsd: json
        Network service descriptor
    deployed_vnfs_info: json
        dictionary with connection points of the differents vnfs after instantiating
    nsId:
        String with the Network Service Id
    Returns
    -------
    List
        List of dictionaries with info of the monitoring jobs
    """
    db_vnf_deployed_infos = nsir_db.get_vnf_deployed_info(nsId)
    vm_agent_id_dict = {}
    for db_vnf_deployed_info in db_vnf_deployed_infos:
        vm_id = db_vnf_deployed_info["name"] + "-" + db_vnf_deployed_info["instance"]
        vm_agent_id_dict.update({vm_id : db_vnf_deployed_info["agent_id"]})
    vm_ip_address_dict = {}
    for elements in deployed_vnfs_info.values():
        for element in elements:
            vm_ip_address_dict.update(element)
    monitoring_jobs={}

    if "monitoredInfo" in nsd["nsd"].keys():
        monitored_params = copy.deepcopy(nsd["nsd"]["monitoredInfo"])
        monitored_params = nsd_monitored_info_convert_ifa_reference_to_ip(monitored_params, nsId)
        log_queue.put(["INFO", "In monitoring, monitored params are:"])
        log_queue.put(["INFO", dumps(monitored_params, indent=4)])
        for param in monitored_params:
            destination_vnf = None
            performanceMetric = param["monitoringParameter"]["performanceMetric"]
            vnf_id = performanceMetric.split(".")[1]
            exporter = param["monitoringParameter"]["exporter"]
            if 'params' in param["monitoringParameter"].keys():
                key_string = ""
                for key, value in param["monitoringParameter"]["params"].items():
                        key_string =  key_string + "_" + str(key) + "_" + str(value)
                vnf_id_exporter = vnf_id + "_" + exporter + key_string
            else:
                vnf_id_exporter = vnf_id + "_" + exporter

            # #delete monitoring jobs with name 'spr2_onewaylatency_exporter' if new job name is
            # # 'spr2_onewaylatency_exporter_ip_192.1ip_192.168.1.17_polling_2'
            temp_monitoring_jobs = copy.deepcopy(monitoring_jobs)
            for key in monitoring_jobs.keys():
                if vnf_id_exporter != key and vnf_id_exporter.startswith(key):
                    del(temp_monitoring_jobs[key])
            monitoring_jobs = temp_monitoring_jobs

            for db_vnf_deployed_info in db_vnf_deployed_infos:
                if db_vnf_deployed_info['name'] == vnf_id:
                    if vnf_id_exporter not in monitoring_jobs.keys():
                        pm_job={}
                        instance_id = "-".join(db_vnf_deployed_info['agent_id'].rsplit("-", 2)[1:3])
                        pm_job['instance'] = instance_id
                        pm_job['name']= db_vnf_deployed_info['agent_id']
                        pm_job['collectionPeriod'] = 15 # agreed 15 seconds as default
                        # pm_job['address'] = vm_ip_address_dict.get(vnf_id, None) # we need here instance id like 'spr2-1' in other case we will have two jobs with same IP
                        pm_job['port'] = "9100"
                        pm_job['vnfdId'] = vnf_id
                        pm_job['nsId'] = nsId
                        pm_job['exporter'] = exporter
                        pm_job['agent_id'] = vm_agent_id_dict[instance_id]
                        pm_job['monitoringParameterId'] = []
                        pm_job['monitoringParameterId'].append(param["monitoringParameter"]["monitoringParameterId"])
                        pm_job['performanceMetric'] = []
                        pm_job['job_create'] = "yes"
                        pm_job['exporter_install'] = "yes"
                        pm_job['performanceMetric'].append(param["monitoringParameter"]["performanceMetric"])
                        pm_job["check"] = True
                        pm_job["node_url_suffix"] = "/metrics"
                        pm_job["type"] = "metric"
                        pm_job["forecasted"] = "no"
                        # vnf_id_exporter = vnf_id + "_" + exporter
                        if 'type' in param["monitoringParameter"].keys():
                            if param["monitoringParameter"]["type"] == "link_metric":
                                if 'params' in param["monitoringParameter"].keys():
                                    pm_job['params'] =  param['monitoringParameter']['params']
                                destination_vnf = param["monitoringParameter"].get("destination_vnf")
                                destination_instance = destination_vnf + "-1"
                                pm_job["destination_vnf"] = destination_vnf
                                if destination_vnf != None:
                                    vnf_id_exporter_dest = destination_vnf + "_" + exporter
                                    pm_job_dest = {}
                                    pm_job_dest['instance'] = destination_instance
                                    pm_job_dest['name'] = vm_agent_id_dict[destination_instance]
                                    pm_job_dest['collectionPeriod'] = 15  # agreed 15 seconds as default
                                    # pm_job_dest['address'] = vm_ip_address_dict.get(destination_vnf, None)
                                    pm_job_dest['port'] = "9100"
                                    pm_job_dest['vnfdId'] = destination_vnf
                                    pm_job_dest['nsId'] = nsId
                                    pm_job_dest['exporter'] = exporter
                                    pm_job_dest['agent_id'] = vm_agent_id_dict[destination_instance]
                                    pm_job_dest['monitoringParameterId'] = []
                                    pm_job_dest['monitoringParameterId'].append(param["monitoringParameter"]["monitoringParameterId"])
                                    pm_job_dest['performanceMetric'] = []
                                    pm_job_dest['performanceMetric'].append(param["monitoringParameter"]["performanceMetric"])
                                    pm_job_dest['job_create'] = "no"
                                    pm_job_dest['exporter_install'] = "yes"
                                    pm_job_dest['params'] = None
                                    pm_job_dest["check"] = True
                                    pm_job_dest["node_url_suffix"] = None
                                    pm_job_dest["type"] = "metric"
                                    pm_job_dest["forecasted"] = "no"
                                    monitoring_jobs.update({vnf_id_exporter_dest: pm_job_dest})
                                    monitoring_jobs.update({vnf_id_exporter: pm_job})
                            elif param["monitoringParameter"]["type"] == "application_metric":
                                destination_vnf = param["monitoringParameter"].get("destination_vnf")
                                pm_job["destination_vnf"] = destination_vnf
                                pm_job["node_url_suffix"] = "/probe"
                                pm_job['params'] = param['monitoringParameter']['params']
                                monitoring_jobs.update({vnf_id_exporter: pm_job})
                                pm_job['type'] = "application_metric"
                            elif param["monitoringParameter"]["type"] == "logs":
                                pm_job['job_create'] = "no"
                                pm_job['exporter_install'] = "yes"
                                pm_job['params'] = param['monitoringParameter']['params']
                                pm_job['type'] = "logs"
                                monitoring_jobs.update({vnf_id_exporter: pm_job})
                            else:
                                pm_job['params'] = None
                                monitoring_jobs.update({vnf_id_exporter: pm_job})
                        else:
                            pm_job['params'] = None
                            monitoring_jobs.update({vnf_id_exporter: pm_job})
                    else:
                        monitoring_jobs[vnf_id_exporter]['monitoringParameterId']\
                            .append(param["monitoringParameter"]["monitoringParameterId"])
                        monitoring_jobs[vnf_id_exporter]['performanceMetric']\
                            .append(param["monitoringParameter"]["performanceMetric"])
    log_queue.put(["DEBUG", "monitoring jobs are: %s"% monitoring_jobs.values()])
    return monitoring_jobs.values()

def update_pm_jobs(nsId, deployed_vnfs_info):
    new_jobs = [] # result of scale out operations
    old_jobs = [] # result of scale in operations
    ips_pms = [] # current ips
    current_jobs = ns_db.get_monitoring_info(nsId)
    for job in current_jobs:
        ips_pms.append(job['address'])
    ips_deployed = [] # target ips
    for sap in deployed_vnfs_info:
        for elem in deployed_vnfs_info[sap]:
            for key in elem.keys():
                ips_deployed.append(elem[key])
    # remove old_jobs
    for ip in ips_pms:
        if (ip not in ips_deployed):
            #after scaling this sap is not available
            for job in current_jobs:
                if (job['address'] == ip):
                    old_jobs.append(job['exporterId'])
    # create new_jobs
    for ip in ips_deployed:
        if (ip not in ips_pms):
            # we need to create a new monitoring job
            for sap in deployed_vnfs_info:
                for elem in deployed_vnfs_info[sap]:
                    for key in elem.keys():
                        if(elem[key] == ip):
                            vnf = key
                            for job in current_jobs:
                                if (vnf.find(job['vnfdId']) !=-1):
                                    new_pm_job = copy.deepcopy(job)
                                    new_pm_job['address'] = ip
                                    del new_pm_job['exporterId']
                                    new_jobs.append(new_pm_job)
                                    break
    return [new_jobs, old_jobs]


def update_pm_jobs_rvm_agents(nsId, deployed_vnfs_info):
    new_jobs = [] # result of scale out operations
    old_jobs = [] # result of scale in operations
    ips_pms = [] # current ips
    log_queue.put(["DEBUG", "In update_pm_jobs_rvm_agents deployedvnfsinfo is:"])
    log_queue.put(["DEBUG", json.dumps(deployed_vnfs_info, indent=4)])
    
    db_vnf_deployed_infos = nsir_db.get_vnf_deployed_info(nsId)
    vm_agent_id_dict = {}
    for db_vnf_deployed_info in db_vnf_deployed_infos:
        instance = db_vnf_deployed_info["name"] + "-" + db_vnf_deployed_info["instance"]
        vm_agent_id_dict.update({instance : db_vnf_deployed_info["agent_id"]})

    current_jobs = ns_db.get_monitoring_info(nsId)
    # log_queue.put(["DEBUG", "In update_pm_jobs_rvm_agents currentjobs are:"])
    # log_queue.put(["DEBUG", json.dumps(current_jobs, indent=4)])

    # remove old_jobs
    for current_job in current_jobs:
        if current_job['instance'] not in vm_agent_id_dict.keys():
            old_jobs.append(current_job)

    # create new_jobs
    for instance in vm_agent_id_dict.keys():
        if_found = False
        for current_job in current_jobs:
            if current_job['instance'] == instance:
                if_found = True
                break
        if if_found == False:
            vnf_id = instance.rsplit("-",2)[0]
            for current_job_source in current_jobs:
                if current_job_source['instance'] == vnf_id + "-1":
                    new_job = copy.deepcopy(current_job_source)
                    new_job['instance'] = instance
                    new_job['name'] = vm_agent_id_dict[instance]
                    new_job['agent_id'] = vm_agent_id_dict[instance]
                    if "exporterId" in new_job.keys():
                        del new_job["exporterId"]
                    if "check" in new_job.keys():
                        del new_job["check"]
                    if "command_id" in new_job.keys():
                        del new_job["command_id"]
                    new_jobs.append(new_job)
    log_queue.put(["DEBUG", "New monitoring jobs to add are:"])
    log_queue.put(["DEBUG", json.dumps(new_jobs, indent=4)])
    return [new_jobs, old_jobs]




def configure_monitoring_job(job):
    """
    Contact with the monitoring manager to create info about the different monitoring jobs in the request
    Parameters
    ----------
    job: Dictionary 
        Dictionary with information about the monitoring job to be created
    Returns
    -------
    List
        List of exporter Ids
    """
    # job_id = str(uuid4())
    header = {'Accept': 'application/json',
              'Content-Type': 'application/json'
              }
    # create the exporter for the job
    monitoring_uri = "http://" + monitoring_ip + ":" + monitoring_port + monitoring_base_path + "/exporter"

    body = {"name": job["name"],
            "endpoint": [ {"address": job["address"],
                           "port": job["port"]}
                        ],
            "vnfdId": job["vnfdId"],
            "nsId": job["nsId"],
            #"forecasted": job["forecasted"],
            "collectionPeriod": job["collectionPeriod"]
           }
    try:
        conn = HTTPConnection(monitoring_ip, monitoring_port)
        conn.request("POST", monitoring_uri, body = dumps(body), headers = header)
        rsp = conn.getresponse()
        exporterInfo = rsp.read()
        exporterInfo = exporterInfo.decode("utf-8")
        exporterInfo = loads(exporterInfo)
        log_queue.put(["INFO", "Deployed exporter info is:"])
        log_queue.put(["INFO", dumps(exporterInfo, indent = 4)])
    except ConnectionRefusedError:
        log_queue.put(["ERROR", "the Monitoring platform is not running or the connection configuration is wrong"])
    job['exporterId'] = exporterInfo["exporterId"]
    return job



def configure_monitoring_job_prometheus(job):
    """
    Contact with the monitoring manager to create info about the different monitoring jobs in the request
    Parameters
    ----------
    job: Dictionary
        Dictionary with information about the monitoring job to be created
    Returns
    -------
    List
        List of exporter Ids
    """
    # job_id = str(uuid4())
    header = {'Accept': 'application/json',
              'Content-Type': 'application/json'
              }
    # create the exporter for the job
    monitoring_uri = "http://" + monitoring_ip + ":" + monitoring_port + monitoring_base_path + "/exporter"
    params_string = ""
    if job['params'] != None:
        for key, value in job['params'].items():
            params_string = params_string + "/" + str(key) + "/" + str(value)
    body = {"name": job["name"],
            "endpoint": [ {"address": monitoring_pushgateway_ip,
                           "port": monitoring_pushgateway_port}
                        ],
            "vnfdId": job["vnfdId"],
            "nsId": job["nsId"],
            "instance": job["instance"],
            "collectionPeriod": job["collectionPeriod"],
            "exporter": job["exporter"],
            #"forecasted": job["forecasted"]
            "metrics_path": "/metrics/" + job["agent_id"] + "/exporter/" + job["exporter"] + params_string
           }
    if "destination_vnf" in job.keys():
        body.update({"params_string": params_string})
        body.update({"destination_vnf": job["destination_vnf"]})

    try:
        conn = HTTPConnection(monitoring_ip, monitoring_port)
        conn.request("POST", monitoring_uri, body = dumps(body), headers = header)
        rsp = conn.getresponse()
        exporterInfo = rsp.read()
        exporterInfo = exporterInfo.decode("utf-8")
        exporterInfo = loads(exporterInfo)
        log_queue.put(["INFO", "Deployed exporter info is:"])
        log_queue.put(["INFO", dumps(exporterInfo, indent = 4)])
    except ConnectionRefusedError:
        log_queue.put(["ERROR", "the Monitoring platform is not running or the connection configuration is wrong"])
    job['exporterId'] = exporterInfo["exporterId"]
    return job


def start_exporters_on_rvm_agent(job):
    """
    Contact with the monitoring manager to create info about the different monitoring jobs in the request
    Parameters
    ----------
    job: Dictionary
        Dictionary with information about the monitoring job to be created
    Returns
    -------
    List
        List of exporter Ids
    """

    header = {'Accept': 'application/json',
              'Content-Type': 'application/json'
              }
    # create the exporter for the job
    monitoring_uri = "http://" + monitoring_ip + ":" + monitoring_port + monitoring_base_path + "/install_exporter"
    converted_params = []
    if job['params'] != None:
        for key, value in job['params'].items():
            converted_params.append({
                "key": str(key),
                "value": str(value)
            })

    body = {"prometheus_job": job["name"],
            "agent_id": job["agent_id"],
            "exporter": job["exporter"],
            "params" : converted_params,
            "node_url_suffix": job["node_url_suffix"],
            "labels": [
                {"key": "nsId",
                 "value": job["nsId"]},
                {"key": "vnfdId",
                 "value": job["vnfdId"]},
                {"key": "instance",
                 "value": job["name"],
                 },
                {"key": "exporter",
                 "value": job["exporter"],
                 }
            ],
            "interval": job["collectionPeriod"]
           }
    try:
        conn = HTTPConnection(monitoring_ip, monitoring_port)
        conn.request("POST", monitoring_uri, body = dumps(body), headers = header)
        rsp = conn.getresponse()
        exporterInfo = rsp.read()
        exporterInfo = exporterInfo.decode("utf-8")
        exporterInfo = loads(exporterInfo)
        log_queue.put(["INFO", "Deployed exporter info is:"])
        log_queue.put(["INFO", dumps(exporterInfo, indent = 4)])
        job["agent_id"] = exporterInfo["agent_id"]
        job["command_id"] = exporterInfo["command_id"]
    except ConnectionRefusedError:
        log_queue.put(["ERROR", "the Monitoring platform is not running or the connection configuration is wrong"])
    return job

def stop_exporters_on_rvm_agent(job_id):
    """
    Contact with the monitoring manager to stop the requested exporter
    Parameters
    ----------
    dashboardId: string
        String identifying the dashboard to be removed
    Returns
    -------
    None
    """
    header = {'Content-Type': 'application/json',
              'Accept': 'application/json'}
    # create the exporter for the job
    monitoring_uri = "http://" + monitoring_ip + ":" + monitoring_port + monitoring_base_path + "/uninstall_exporter"
    try:
        conn = HTTPConnection(monitoring_ip, monitoring_port)
        rvm_agent_id = job_id['agent_id']
        exporter = job_id['exporter']
        conn.request("DELETE", monitoring_uri + "/" + rvm_agent_id + "/" + exporter, None, header)
        rsp = conn.getresponse()
    except ConnectionRefusedError:
        log_queue.put(["ERROR", "the Monitoring platform is not running or the connection configuration is wrong"])

def delete_rvm_agent(agent_id):
    """
    Contact with the monitoring manager to stop the requested exporter
    Parameters
    ----------
    dashboardId: string
        String identifying the dashboard to be removed
    Returns
    -------
    None
    """
    header = {'Content-Type': 'application/json',
              'Accept': 'application/json'}
    # create the exporter for the job
    monitoring_uri = "http://" + monitoring_ip + ":" + monitoring_port + monitoring_base_path + "/agent"
    try:
        conn = HTTPConnection(monitoring_ip, monitoring_port)
        conn.request("DELETE", monitoring_uri + "/" + agent_id, None, header)
        rsp = conn.getresponse()
    except ConnectionRefusedError:
        log_queue.put(["ERROR", "the Monitoring platform is not running or the connection configuration is wrong"])


def stop_exporters_on_rvm_agent(job_id):
    """
    Contact with the monitoring manager to stop the requested exporter
    Parameters
    ----------
    dashboardId: string
        String identifying the dashboard to be removed
    Returns
    -------
    None
    """
    header = {'Content-Type': 'application/json',
              'Accept': 'application/json'}
    # create the exporter for the job
    monitoring_uri = "http://" + monitoring_ip + ":" + monitoring_port + monitoring_base_path + "/uninstall_exporter"
    try:
        conn = HTTPConnection(monitoring_ip, monitoring_port)
        rvm_agent_id = job_id['agent_id']
        exporter = job_id['exporter']
        conn.request("DELETE", monitoring_uri + "/" + rvm_agent_id + "/" + exporter, None, header)
        rsp = conn.getresponse()
    except ConnectionRefusedError:
        log_queue.put(["ERROR", "the Monitoring platform is not running or the connection configuration is wrong"])

def get_ffb_jobs(nsd, nsId):
    """
    Collects the information of the descriptor to prepare information to launch Forecasting jobs
    Parameters
    ----------
    nsd: json
        Network service descriptor
    nsId: string
        String identifying the NS instance id 
    Returns
    -------
    ffb_jobs: dict
        dictionary with the elements required by the FFB API to launch a forecasting job
    """
    # assumption: a forecasting job will be launched by each forecasting element in the descriptor,
    # and the monitoring jobs have already been launched
    ffb_jobs = []
    if "forecastedInfo" in nsd["nsd"].keys():
        forecasted_params = nsd["nsd"]["forecastedInfo"]
        monitored_params = nsd["nsd"]["monitoredInfo"]
        for f_param in forecasted_params:
           mon_param_name = f_param["forecastingParameter"]["monitoringParameterId"]
           for  m_param in monitored_params:
               if (m_param["monitoringParameter"]["monitoringParameterId"] == mon_param_name):
                   # we have found the appropriate monitoring param
                   f_job=dict()
                   f_job["fname"] = f_param["forecastingParameter"]["forecatingParameterId"]
                   f_job["mname"] = mon_param_name
                   f_job["nsId"] = nsId
                   pm_split = m_param["monitoringParameter"]["performanceMetric"].split(".")
                   f_job["vnfdId"] = pm_split[1]
                   f_job["perfomance_metric"] = pm_split[0]
                   f_job["nsdId"] = nsd["nsd"]["nsdIdentifier"]
                   f_job["IL"] = ns_db.get_ns_il(nsId)                  
                   ffb_jobs.append(f_job)
                   break
    return ffb_jobs

def configure_forecasting_job(job):
    """
    Contact with the forecasting platform to create a forecasting job with the info in the provided variable
    Parameters
    ----------
    job: Dictionary 
        Dictionary with information about the forecasting job to be created
    Returns
    -------
    job: Dictionary
        The previous dictionary but adding the forecasting Id provided by the FFB
    """
    header = {'Accept': 'application/json',
              'Content-Type': 'application/json'
              }
    # create the forescasting job
    forecasting_uri = "http://" + ffb_platform_ip + ":" + ffb_platform_port + ffb_base_path + "/Forecasting"

    body = {"nsId": job["nsId"],
            "vnfdId": job["vnfdId"],
            "nsdId": job["nsdId"],
            "Performance_Metric": job["performance_metric"],
            "IL": job["IL"]
           }
    try:
        conn = HTTPConnection(ffb_platform_ip, ffb_platform_port)
        conn.request("POST", forecasting_uri, body = dumps(body), headers = header)
        rsp = conn.getresponse()
        forecasterInfo = rsp.read()
        forecasterInfo = forecasterInfo.decode("utf-8")
        forecasterInfo = loads(forecasterInfo)
        log_queue.put(["INFO", "Deployed forecaster info is:"])
        log_queue.put(["INFO", dumps(forecaterInfo, indent = 4)])
    except ConnectionRefusedError:
        log_queue.put(["ERROR", "the Forecasting platform is not running or the connection configuration is wrong"])
    job['forecastId'] = forecasterInfo["forecastId"]
    return job

def update_forecasting_job(jobId, instantiation_level):
    """
    Contact with the forecasting platform to update a the specified forecasting job after a scaling operation
    Parameters
    ----------
    job: Dictionary 
        Dictionary with information about the forecasting job to be created
    Returns
    -------
    job: Dictionary
        The previous dictionary but adding the forecasting Id provided by the FFB
    """
    header = {'Accept': 'application/json',
              'Content-Type': 'application/json'
              }
    # create the forescasting job
    forecasting_uri = "http://" + ffb_platform_ip + ":" + ffb_platform_port + ffb_base_path + "/Forecasting"

    try:
        conn = HTTPConnection(ffb_platform_ip, ffb_platform_port)
        conn.request("PUT", forecasting_uri + "/" + jobId + "/" + instantiation_level, None, headers = header)
        rsp = conn.getresponse()
    except ConnectionRefusedError:
        log_queue.put(["ERROR", "the Forecasting platform is not running or the connection configuration is wrong"])

def stop_forecasting_job(jobId):
    """
    Contact with the forecasting platform to stop the requested forecaster
    Parameters
    ----------
    jobId: string 
        String identifying the forecasting job to be removed 
    Returns
    -------
    None
    """
    header = {'Content-Type': 'application/json',
              'Accept': 'application/json'}
    # delete the forecaster, we assume everything OK 
    forecasting_uri = "http://" + ffb_platform_ip + ":" + ffb_platform_port + ffb_platform_base_path + "/Forecasting"
    try:
        conn = HTTPConnection(ffb_platform_ip, ffb_platform_port)
        conn.request("DELETE", forecasting_uri + "/" + jobId, None, header)
        rsp = conn.getresponse()
    except ConnectionRefusedError:
        log_queue.put(["ERROR", "the Monitoring platform is not running or the connection configuration is wrong"])

    
def get_dashboard_query(pm, exporterId):
    """
    generate the string to make the prometheus query when creating a dashboard
    Parameters
    ----------
    pm: string
        String with the type of performanceNetwork Service Id
    exporterId:
        String with the exporter Id
    # query: string
    #    Query to show in the dashboard
    Returns
    -------
    Prometheusquery
        string with the prometheus query
    """
    Prometheusquery = ""
    # pm's can be:
                  # VcpuUsageMean.<vnfdId>
                  # VmemoryUsageMean.<vnfdId>
                  # VdiskUsageMean.<vnfdId>
                  # ByteIncoming.<vnfdId>.<vnfExtCpdId>
    if (pm.find("cpu") !=-1):
        Prometheusquery = "sum without (cpu, mode) (rate(node_cpu_seconds_total{mode!=" + "\"idle\"" + ", job=\"" + exporterId + "\"}[1m]))*100"      
    if (pm.find("memory") !=-1):
        Prometheusquery =  "((node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100), {job= \"" + exporterId +"\"}"
    if (pm.find("disk") !=-1):
        Prometheusquery = "((node_filesystem_avail_bytes{mountpoint=" + "\/""} / node_filesystem_size_bytes{mountpoint=" + "\/""}) * 100), {job= \"" + exporterId +"\"}"
    if (pm.find("Byte") !=-1):
        port = pm.split(".")[2]
        Prometheusquery = "rate(node_network_receive_bytes_total{device=" + "\"" + port + "\"" + ",job=\"" + exporterId + "\"}[1m])"
    return Prometheusquery


def get_dashboard_query_v2(job, metric):
    """
    generate the string to make the prometheus query when creating a dashboard
    Parameters
    ----------
    pm: string
        String with the type of performanceNetwork Service Id
    exporterId:
        String with the exporter Id
    # query: string
    #    Query to show in the dashboard
    Returns
    -------
    Prometheusquery
        string with the prometheus query
    """
    nsId = job['nsId']
    vnfdId = job['vnfdId']
    pm = job['performanceMetric'][metric]
    if "exporter" in job:
        exporter = job["exporter"]
    Prometheusquery = ""
    if (pm.find("cpu") !=-1):
        Prometheusquery = "avg((1 - avg by(instance) (irate(node_cpu_seconds_total{mode=\"idle\",nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId + "\"}[1m]))) * 100)"
    if (pm.find("memory") !=-1):
        Prometheusquery =  "avg by (vnfdId)(((node_memory_MemTotal_bytes{nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId + "\"} - node_memory_MemFree_bytes{nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId + "\"}) / node_memory_MemTotal_bytes{nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId + "\"}) * 100)"
    if (pm.find("disk") !=-1):
        Prometheusquery = "((node_filesystem_size_bytes{fstype=~\"ext4|vfat\", nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId + "\"} - node_filesystem_free_bytes{fstype=~\"ext4|vfat\", nsId=\"" + nsId + "\", vnfdId=\"" + vnfdId + "\"}) / node_filesystem_size_bytes{fstype=~\"ext4|vfat\", nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId + "\"}) * 100"
    if (pm.find("Byte") !=-1):
        port = pm.split(".")[2]
        Prometheusquery = "rate(node_network_receive_bytes_total{device=\"" + port + "\",nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId + "\"}[1m])"
    if (pm.find("linklatency")     !=-1):
        exporter = job["exporter"]
        host = job["params"]["ip"]
        Prometheusquery = "linklatency{nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId + "\",exporter=\"" + exporter + "\",host=\"" + host + "\"}"
    if (pm.find("packetLoss")     !=-1):
        exporter = job["exporter"]
        host = job["params"]["ip"]
        Prometheusquery = "packetLoss{nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId + "\",exporter=\"" + exporter + "\",host=\"" + host + "\"}"
    if (pm.find("jitter")     !=-1):
        exporter = job["exporter"]
        host = job["params"]["ip"]
        Prometheusquery = "jitter{nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId + "\",exporter=\"" + exporter + "\",host=\"" + host + "\"}"
    if (pm.find("http_request_latency")     !=-1):
        exporter = job["exporter"]
        destination_vnf = job["destination_vnf"]
        Prometheusquery = "probe_duration_seconds{nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId + "\",exporter=\"" + exporter + "\",destination_vnf=\"" + destination_vnf + "\"}"
    if (pm.find("http_service_probe")     !=-1):
        exporter = job["exporter"]
        destination_vnf = job["destination_vnf"]
        Prometheusquery = "probe_success{nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId + "\",exporter=\"" + exporter + "\",destination_vnf=\"" + destination_vnf + "\"}"
    if (pm.find("http_service_availability")     !=-1):
        exporter = job["exporter"]
        destination_vnf = job["destination_vnf"]
        Prometheusquery = "1 - (count_over_time(probe_success{nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId + "\",exporter=\"" + exporter + "\",destination_vnf=\"" + destination_vnf + "\"}[1y])- sum_over_time(probe_success{nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId + "\",exporter=\"" + exporter + "\",destination_vnf=\"" + destination_vnf + "\"}[1y])) /(31536000 / 15)"
    if (pm.find("client_side_latency_ms")     !=-1):
        Prometheusquery = "latency_ms{exporter=\"peccm_exporter\", nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId +"\"}"
    if (pm.find("client_side_parsing_ms")     !=-1):
        Prometheusquery = "parsing_ms{exporter=\"peccm_exporter\", nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId +"\"}"
    if (pm.find("client_side_buffering_ms")     !=-1):
        Prometheusquery = "buffering_ms{exporter=\"peccm_exporter\", nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId +"\"}"
    if (pm.find("client_side_loading_ms")     !=-1):
        Prometheusquery = "loading_ms{exporter=\"peccm_exporter\", nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId +"\"}"
    if (pm.find("client_side_bw_kbps")     !=-1):
        Prometheusquery = "bw_kbps{exporter=\"peccm_exporter\", nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId +"\"}"


    return Prometheusquery


def configure_dashboard(nsId, jobs):
    """
    Contact with the monitoring manager to create the dashboard with query
    Parameters
    ----------
    nsId: string 
        String with the Network Service Id 
    jobs:
        Array of dictionaries with job information
    Returns
    -------
    Dictionary
        Dashboard Id and url
    """
    if (len(jobs) == 0):
        return {}
    else:
        header = {'Content-Type': 'application/json',
                  'Accept': 'application/json'}
        # create the exporter for the job
        monitoring_uri = "http://" + monitoring_ip + ":" + monitoring_port + monitoring_base_path + "/dashboard"
        body = {"name": "NS_" + nsId,
                "panels": [],
                "users": [nsId], 
                "plottedTime": 60,
                "refreshTime": "5s"
               }
        for job in jobs:
            panel = {}
            panel['title'] = job["monitoringParameterId"] + "(" + job["performanceMetric"] + ")"
            panel['query'] = get_dashboard_query(job['performanceMetric'], job['exporterId'])
            panel['size'] = ""
            body['panels'].append(panel)
        try:
            conn = HTTPConnection(monitoring_ip, monitoring_port)
            conn.request("POST", monitoring_uri, dumps(body), header)
            rsp = conn.getresponse()
            dashboardInfo = rsp.read()
            dashboardInfo = dashboardInfo.decode("utf-8")
            dashboardInfo = loads(dashboardInfo)
            log_queue.put(["INFO", "deployed Dashboard info is:"])
            dashboardInfo['url'] = "http://" + monitoring_ip + ":3000" + dashboardInfo['url']
            log_queue.put(["INFO", dumps(dashboardInfo, indent = 4)])
        except ConnectionRefusedError:
            log_queue.put(["ERROR", "the Monitoring platform is not running or the connection configuration is wrong"])
        return {"dashboardId" : dashboardInfo["dashboardId"],
                "dashboardUrl" : dashboardInfo["url"] }

def configure_dashboard_v2(nsId, jobs):
    """
    Contact with the monitoring manager to create the dashboard with query
    Parameters
    ----------
    nsId: string 
        String with the Network Service Id 
    jobs:
        Array of dictionaries with job information
    Returns
    -------
    Dictionary
        Dashboard Id and url
    """
    if (len(jobs) == 0):
        return {}
    else:
        header = {'Content-Type': 'application/json',
                  'Accept': 'application/json'}
        # create the exporter for the job 
        monitoring_uri = "http://" + monitoring_ip + ":" + monitoring_port + monitoring_base_path + "/dashboard"
        body = {"name": "NS_" + nsId,
                "panels": [],
                "users": [nsId], 
                "plottedTime": 20,
                "refreshTime": "10s"
               }
        #checking the different labels of the exporters for a network service
        vnfIds = []
        panels_info = []
        for job in jobs:
            if job['job_create'] == "yes":
                if job['vnfdId'] not in vnfIds:
                    # in case there are two instances of the same exporter you make the average
                    vnfIds.append(job)
        log_queue.put(["INFO", "when configuring the dashboard the jobs are:"])
        log_queue.put(["INFO", dumps(vnfIds, indent = 4)] )
        for job in vnfIds:
            log_queue.put(["INFO", "configuring job:"])
            log_queue.put(["INFO", dumps(job, indent = 4)] )
            for metric in range(0, len(job["performanceMetric"])):
               panel = {}
               panel['title'] = job["monitoringParameterId"][metric] + "(" + job["performanceMetric"][metric] + ")"
               panel['query'] = get_dashboard_query_v2(job, metric)
               panel['size'] = ""
               body['panels'].append(panel)
               panel_info = {}
               panel_info["performanceMetric"] = job["performanceMetric"][metric]
               panel_info["monitoringParameterId"] = job["monitoringParameterId"][metric]
               panel_info["vnfdId"] = job["vnfdId"]
               panel_info["query"] = panel["query"]
               panel_info["collectionPeriod"] = job["collectionPeriod"]
               panels_info.append(panel_info)

        try:
            conn = HTTPConnection(monitoring_ip, monitoring_port)
            conn.request("POST", monitoring_uri, dumps(body), header)
            rsp = conn.getresponse()
            dashboardInfo = rsp.read()
            dashboardInfo = dashboardInfo.decode("utf-8")
            dashboardInfo = loads(dashboardInfo)
            log_queue.put(["INFO", "deployed Dashboard info is:"])
            dashboardInfo['url'] = "http://" + monitoring_ip + ":3000" + dashboardInfo['url']
            log_queue.put(["INFO", dumps(dashboardInfo, indent = 4)])
        except ConnectionRefusedError:
                log_queue.put(["ERROR", "the Monitoring platform is not running or the connection configuration is wrong"])
        return {"dashboardId" : dashboardInfo["dashboardId"],
                "dashboardUrl" : dashboardInfo["url"],
                "panelsInfo": panels_info}

def update_dashboard(nsId, jobs, current_dashboardInfo):
    """
    Contact with the monitoring manager to upadte the dashboard with query
    Parameters
    ----------
    nsId: string
        String with the Network Service Id
    jobs:
        Array of dictionaries with job information
    Returns
    -------
    Dictionary
        Dashboard Id and url
    """
    if (len(jobs) == 0):
        return {}
    else:
        header = {'Content-Type': 'application/json',
                  'Accept': 'application/json'}
        # create the exporter for the job
        monitoring_uri = "http://" + monitoring_ip + ":" + monitoring_port + monitoring_base_path + "/dashboard/" + current_dashboardInfo["dashboardId"]
        body = {"dashboardId": current_dashboardInfo["dashboardId"],
                "url": current_dashboardInfo["dashboardUrl"].replace("http://" + monitoring_ip + ":3000",""),
                "name": "NS_" + nsId,
                "panels": [],
                "users": [nsId],
                "plottedTime": 20,
                "refreshTime": "10s"
               }
        #checking the different labels of the exporters for a network service
        vnfIds = []
        panels_info = []
        for job in jobs:
            if job['job_create'] == "yes":
                if job['vnfdId'] not in vnfIds:
                    vnfIds.append(job)
        log_queue.put(["INFO", "when updating the dashboard the jobs are:"])
        log_queue.put(["INFO", dumps(vnfIds, indent = 4)] )
        for job in vnfIds:
            for metric in range(0, len(job["performanceMetric"])):
               panel = {}
               panel['title'] = job["monitoringParameterId"][metric] + "(" + job["performanceMetric"][metric] + ")"
               panel['query'] = get_dashboard_query_v2(job, metric)
               panel['size'] = ""
               body['panels'].append(panel)
               panel_info = {}
               panel_info["performanceMetric"] = job["performanceMetric"][metric]
               panel_info["monitoringParameterId"] = job["monitoringParameterId"][metric]
               panel_info["vnfdId"] = job["vnfdId"]
               panel_info["query"] = panel["query"]
               panel_info["collectionPeriod"] = job["collectionPeriod"]
               panels_info.append(panel_info)
        try:
            conn = HTTPConnection(monitoring_ip, monitoring_port)
            conn.request("PUT", monitoring_uri, dumps(body), header)
            rsp = conn.getresponse()
            dashboardInfo = rsp.read()
            dashboardInfo = dashboardInfo.decode("utf-8")
            dashboardInfo = loads(dashboardInfo)
            log_queue.put(["DEBUG", "updated Dashboard info is:"])
            dashboardInfo['url'] = "http://" + monitoring_ip + ":3000" + dashboardInfo['url']
            log_queue.put(["DEBUG", dumps(dashboardInfo, indent = 4)])
        except ConnectionRefusedError:
                log_queue.put(["ERROR", "the Monitoring platform is not running or the connection configuration is wrong"])
        return {"dashboardId" : dashboardInfo["dashboardId"],
                "dashboardUrl" : dashboardInfo["url"],
                "panelsInfo": panels_info}

def stop_monitoring_job(jobId):
    """
    Contact with the monitoring manager to stop the requested exporter
    Parameters
    ----------
    dashboardId: string 
        String identifying the dashboard to be removed 
    Returns
    -------
    None
    """
    header = {'Content-Type': 'application/json',
              'Accept': 'application/json'}
    # create the exporter for the job 
    monitoring_uri = "http://" + monitoring_ip + ":" + monitoring_port + monitoring_base_path + "/exporter"
    try:
        conn = HTTPConnection(monitoring_ip, monitoring_port)
        conn.request("DELETE", monitoring_uri + "/" + jobId, None, header)
        rsp = conn.getresponse()
    except ConnectionRefusedError:
        log_queue.put(["ERROR", "the Monitoring platform is not running or the connection configuration is wrong"])

def stop_dashboard(dashboardId):
    """
    Contact with the monitoring manager to stop the dashboard
    Parameters
    ----------
    dashboardId: string 
        String identifying the dashboard to be removed 
    Returns
    -------
    None
    """
    header = {'Content-Type': 'application/json',
              'Accept': 'application/json'}
    # create the exporter for the job 
    monitoring_uri = "http://" + monitoring_ip + ":" + monitoring_port + monitoring_base_path + "/dashboard"
    try:
        conn = HTTPConnection(monitoring_ip, monitoring_port)
        conn.request("DELETE", monitoring_uri + "/" + dashboardId, None, header)
        rsp = conn.getresponse()
    except ConnectionRefusedError:
        log_queue.put(["ERROR", "the Monitoring platform is not running or the connection configuration is wrong"])


########################################################################################################################
# PUBLIC METHODS                                                                                                       #
########################################################################################################################


def configure_logs_dashboard(nsId, jobs):
    """
    Creates a logs dashboard in ELK stack
    Parameters
    ----------
    nsId: string
        String with the Network Service Id
    jobs:
        List of dictionaries with info of the monitoring jobs
    Returns
    -------
    name: dictionary
        Dashboard Id and url
    """
    if (len(jobs) == 0):
        return {}

    else:
        header = {'Accept': 'application/json',
                  'Content-Type': 'application/json'
                  }

        body = {
            "dashboardTitle": "Logs for ns_" + nsId,
            "ns_id": nsId,
            "dashboard_type": "vm_logs"
        }
        monitoring_uri = "http://" + monitoring_ip + ":" + monitoring_port + monitoring_base_path + "/kibanaDashboard"
        try:
            conn = HTTPConnection(monitoring_ip, monitoring_port)
            conn.request("POST", monitoring_uri, body=dumps(body), headers=header)
            rsp = conn.getresponse()
            resources = rsp.read()
            logs_dashboard_info = resources.decode("utf-8")
            log_queue.put(["DEBUG", "Deployed Logs Dashboard info is:"])
            log_queue.put(["DEBUG", logs_dashboard_info])
            logs_dashboard_info = loads(logs_dashboard_info)
            log_queue.put(["DEBUG", "Deployed Logs Dashboard info is:"])
            log_queue.put(["DEBUG", dumps(logs_dashboard_info, indent=4)])
            conn.close()
        except ConnectionRefusedError:
            # the Config Manager is not running or the connection configuration is wrong
            log_queue.put(["ERROR", "the Config Manager is not running or the connection configuration is wrong"])
        return {"dashboardId" : logs_dashboard_info["dashboardId"],
                "dashboardUrl" : logs_dashboard_info["url"] }

def stop_logs_dashboard(dashboardId):
    """
    Contact with the monitoring manager to delete the logs dashboard
    Parameters
    ----------
    dashboardId: string
        String identifying the logs dashboard to be removed
    Returns
    -------
    None
    """
    header = {'Content-Type': 'application/json',
              'Accept': 'application/json'}
    monitoring_uri = "http://" + monitoring_ip + ":" + monitoring_port + monitoring_base_path + "/kibanaDashboard"
    try:
        conn = HTTPConnection(monitoring_ip, monitoring_port)
        conn.request("DELETE", monitoring_uri + "/" + dashboardId, None, header)
        rsp = conn.getresponse()
        log_queue.put(["DEBUG", "Deleted Logs Dashboard ID is:" + dashboardId])
    except ConnectionRefusedError:
        log_queue.put(["ERROR", "the Monitoring platform is not running or the connection configuration is wrong"])


def jobs_has_logs(jobs):
    """
    Checks jobs if they have jobs with type "logs"
    Parameters
    ----------
    jobs:
        List of dictionaries with info of the monitoring jobs
    Returns
    -------
    True: if list of jobs has a job with type "logs"
    False: if list of jobs doesn't have a job with type "logs"
    """
    for job in jobs:
        if job['type'] == 'logs':
            return True
    return False


def configure_ns_monitoring(nsId, nsd, vnfds, deployed_vnfs_info):
    """
    Contact with the monitoring manager to configure the monitoring jobs and the dashboard
    Parameters
    ----------
    nsId: string 
        String identifying the network service
    nsd: json
        Network service descriptor
    vnfds: json
        VNF descriptor
    deployed_vnfs_info: dict
        Dictionary with information of the saps of the deployed vnfs in a network service
    Returns
    -------
    None
    """
    if monitoring_pushgateway == "no":
        # parse NSD / VNFDs to get the list of monitoring jobs to be configured and its information
        # ! we need the input of the vnfds, to have the endpoints!
        jobs = get_pm_jobs_v2(nsd, deployed_vnfs_info, nsId)
        # for each job request the Monitoring Configuration Manager to configure the job and save the job_id
        job_ids = []
        for job in jobs:
            job_elem = configure_monitoring_job(job)
            job_ids.append(job_elem)
        # save the list of jobs in the database
        ns_db.set_monitoring_info(nsId, job_ids)
        # create the dashboard for the monitoring jobs
        dashboard_id = configure_dashboard_v2(nsId, jobs)
        ns_db.set_dashboard_info(nsId, dashboard_id)
    else:
        # parse NSD / VNFDs to get the list of monitoring jobs to be configured and its information
        # ! we need the input of the vnfds, to have the endpoints!
        jobs = get_pm_jobs_rvm_agents(nsd, deployed_vnfs_info, nsId)
        # for each job request the Monitoring Configuration Manager to configure the job and save the job_id
        job_ids = []
        for job_elem in jobs:
            if job_elem['exporter_install'] == "yes":
                start_exporters_on_rvm_agent(job_elem)
        log_queue.put(["DEBUG", "Waiting Prometheus Exporters installing"])
        wait_commands_execution(jobs)
        log_queue.put(["DEBUG", "Prometheus Exporters were installed"])
        for job_elem in jobs:
            if job_elem['job_create'] == "yes":
                job_elem = configure_monitoring_job_prometheus(job_elem)
            job_ids.append(job_elem)

        wait_commands_execution(job_ids)
        log_queue.put(["DEBUG", "Prometheus Exporters were installed"])
        # for each job request the Monitoring Configuration Manager to configure the job and save the job_id
        # save the list of jobs in the database
        ns_db.set_monitoring_info(nsId, job_ids)
        # create the dashboard for the monitoring jobs
        dashboard_id = configure_dashboard_v2(nsId, jobs)
        ns_db.set_dashboard_info(nsId, dashboard_id)
        if jobs_has_logs(jobs):
            logs_dashboard_id = configure_logs_dashboard(nsId, jobs)
            ns_db.set_logs_dashboard_info(nsId, logs_dashboard_id)
    #after configuring monitoring jobs, forecasting jobs are configured
    # ffb_jobs = get_ffb_jobs(nsd,nsId)
    # log_queue.put(["DEBUG", "ffb_jobs are: %s"%ffb_jobs])   
    # ffb_jobs_ids = []
    #for job in ffb_jobs:
    #    job_elem = configure_forecasting_job(job)
    #    ffb_job_ids.append(job_elem)
    # save the list of forecasting jobs in the database
    # log_queue.put(["DEBUG", "ffb_job_ids are: %s"%ffb_jobs_ids])
    # ns_db.set_forecasting_info(nsId, ffb_jobs_ids)
    

def update_ns_monitoring(nsId, nsd, vnfds, deployed_vnfs_info):
    """
    Contact with the monitoring manager to update the monitoring jobs and the dashboard
    Parameters
    ----------
    nsId: string 
        String identifying the network service
    nsd: json
        Network service descriptor
    vnfds: json
        VNF descriptor
    deployed_vnfs_info: dict
        Dictionary with information of the saps of the deployed vnfs in a network service
    Returns
    -------
    None
    """
    if monitoring_pushgateway == "no":
        new_jobs = [] # result of scale out operations
        old_jobs = [] # result of scale in operations
        job_ids = []
        [new_jobs, old_jobs] = update_pm_jobs(nsId, deployed_vnfs_info)
        for job in new_jobs:
            job_elem = configure_monitoring_job(job)
            job_ids.append(job_elem)
        # update the list of jobs in the database
        for job in old_jobs:
            stop_monitoring_job(job)
        ns_db.update_monitoring_info(nsId, job_ids, old_jobs)
        # update the dashboard for the monitoring jobs: once all required ones have been created or erased
        # "No need to update the dashboard because we average" (210119)
        # jobs = ns_db.get_monitoring_info(nsId)
        # dashboard_info = ns_db.get_dashboard_info(nsId)
        # if "dashboardId" in dashboard_info.keys():
        #    stop_dashboard(dashboard_info["dashboardId"])
        #dashboard_id = configure_dashboard_v2(nsId, jobs)
        ## we rewrite the dasboard info
        #ns_db.set_dashboard_info(nsId, dashboard_id)
    else:
        new_jobs = [] # result of scale out operations
        old_jobs = [] # result of scale in operations
        job_ids = []
        [new_jobs, old_jobs] = update_pm_jobs_rvm_agents(nsId, deployed_vnfs_info)
        for job in new_jobs:
            job_elem = job
            if job_elem['job_create'] == "yes":
                job_elem = configure_monitoring_job_prometheus(job_elem)
            if job_elem['exporter_install'] == "yes":
                job_elem = start_exporters_on_rvm_agent(job_elem)
            job_ids.append(job_elem)
        # update the list of jobs in the database
        old_jobs_ids = []
        delted_rvm_agents = []
        for job_id in old_jobs:
            if job_id['job_create'] == "yes":
                stop_monitoring_job(job_id['exporterId'])
            if job_id['exporter_install'] == "yes":
                stop_exporters_on_rvm_agent(job_id)
            if job_id['agent_id'] not in delted_rvm_agents:
                delete_rvm_agent(job_id['agent_id'])
                delted_rvm_agents.append(job_id['agent_id'])
            if 'exporterId' in job_id.keys():
                old_jobs_ids.append(job_id['exporterId'])
        ns_db.update_monitoring_info(nsId, job_ids, old_jobs_ids)
    # update possible ffb jobs (the new IL is already available)
    # assuming not any vnf_type with a forecasting job will dissapear
    # ffb_jobs = ns_db.get_forecasting_info(nsId)
    # current_IL = ns_db.get_ns_il(nsId)
    # for job in ffb_jobs:
    #    job["IL"] = current_IL
    # ns_db.set_forecasting_info(nsId, ffb_jobs)

def stop_ns_monitoring(nsId):
    """
    Contact with the monitoring manager to delete the monitoring jobs and the dashboard
    Parameters
    ----------
    nsId: string 
        String identifying the network service
    Returns
    -------
    None
    """
    # parse NSD / VNFDs to get the list of montoring jobs to be configured and its information
    if monitoring_pushgateway == "no":
        log_queue.put(["INFO", "*****Time measure: MonManager MonManager deleting monitoring jobs (exporters, dashboard)"])
        job_ids = ns_db.get_monitoring_info(nsId)
        for job_id in job_ids:
            stop_monitoring_job(job_id['exporterId'])
        # delete monitor jobs from database by posting an empty list
        log_queue.put(["INFO", "*****Time measure: MonManager MonManager deleted exporters in Monitoring platform"])
        ns_db.set_monitoring_info(nsId, [])
        log_queue.put(["INFO", "*****Time measure: MonManager MonManager deleted exporter info in DB"])
        dashboard_info = ns_db.get_dashboard_info(nsId)
        if "dashboardId" in dashboard_info.keys():
            stop_dashboard(dashboard_info["dashboardId"])
            log_queue.put(["INFO", "*****Time measure: MonManager MonManager deleted dashboard"])
            ns_db.set_dashboard_info(nsId, {})
            log_queue.put(["INFO", "*****Time measure: MonManager MonManager deleted dashboard info in DB"])
    else:
        # delete monitor jobs from database by posting an empty list
        job_ids = ns_db.get_monitoring_info(nsId)
        if jobs_has_logs(job_ids):
            logs_dashboard_info = ns_db.get_logs_dashboard_info(nsId)
            if "dashboardId" in logs_dashboard_info.keys():
                stop_logs_dashboard(logs_dashboard_info["dashboardId"])
                ns_db.set_logs_dashboard_info(nsId, {})
        for job_id in job_ids:
            if job_id['job_create'] == "yes":
                stop_monitoring_job(job_id['exporterId'])
            if job_id['exporter_install'] == "yes":
                stop_exporters_on_rvm_agent(job_id)
        #     delete_rvm_agent(job_id['agent_id'])
        # ns_db.set_monitoring_info(nsId, [])
    #finish forecasting jobs
    # log_queue.put(["INFO", "*****Time measure for nsId: %s: MonManager MonManager deleted monitoring and dashboard jobs"%nsId])
    # ffb_jobs_ids = ns_db.get_forecasting_info(nsId)
    # for job_id in ffb_jobs_ids:
    #     stop_forecasting_job(job_id["forecastId"])
    # ns_db.set_forecasting_info(nsId, [])
    # log_queue.put(["INFO", "*****Time measure for nsId: %s: MonManager MonManager deleted forecasting jobs"%nsId])
    

def create_prometheus_scraper(nsid, kafka_topic, vnfid, performance_metric, expression, collectionPeriod):
    """
    Parameters
    ----------
    operationId: dict
        Object for creating
    Returns
    -------
    name: type
        return prometheus scraper
    """
    header = {'Accept': 'application/json',
              'Content-Type': 'application/json'
              }

    body = {
        "performanceMetric": performance_metric,
        "nsid": nsid,
        "vnfid": vnfid,
        "interval": collectionPeriod,
        "kafkaTopic": kafka_topic,
        "expression": expression
    }
    monitoring_uri = "http://" + monitoring_ip + ":" + monitoring_port + monitoring_base_path + "/prometheus_scraper"
    try:
        conn = HTTPConnection(monitoring_ip, monitoring_port)
        conn.request("POST", monitoring_uri, body=dumps(body), headers=header)
        rsp = conn.getresponse()
        resources = rsp.read()
        resp_prometheus_scraper = resources.decode("utf-8")
        log_queue.put(["DEBUG", "Prometheus Scraper from Config Manager are:"])
        log_queue.put(["DEBUG", resp_prometheus_scraper])
        resp_prometheus_scraper = loads(resp_prometheus_scraper)
        log_queue.put(["DEBUG", "Prometheus Scraper from Config Manager are:"])
        log_queue.put(["DEBUG", dumps(resp_prometheus_scraper, indent=4)])
        conn.close()
    except ConnectionRefusedError:
        # the Config Manager is not running or the connection configuration is wrong
        log_queue.put(["ERROR", "the Config Manager is not running or the connection configuration is wrong"])
    return resp_prometheus_scraper


def delete_prometheus_scraper(prometheus_scraper_id):
    """
    Parameters
    ----------
    operationId: dict
        Object for creating
    Returns
    -------
    name: type
        return alert
    """
    header = {'Accept': 'application/json'
              }
    monitoring_uri = "http://" + monitoring_ip + ":" + monitoring_port + monitoring_base_path + "/prometheus_scraper/" + str(
        prometheus_scraper_id)
    try:
        conn = HTTPConnection(monitoring_ip, monitoring_port)
        conn.request("DELETE", monitoring_uri, headers=header)
        rsp = conn.getresponse()
        resources = rsp.read()
        resp_alert = resources.decode("utf-8")
        log_queue.put(["DEBUG", "Prometheus Scraper from Config Manager are:"])
        log_queue.put(["DEBUG", resp_alert])
        resp_alert = loads(resp_alert)
        log_queue.put(["DEBUG", "Prometheus Scraper from Config Manager are:"])
        log_queue.put(["DEBUG", dumps(resp_alert, indent=4)])
        conn.close()
    except ConnectionRefusedError:
        # the Config Manager is not running or the connection configuration is wrong
        log_queue.put(["ERROR", "the Config Manager is not running or the connection configuration is wrong"])

def check_command(command):
    """
    Checks currents status of command
    Parameters
    ----------
    command: dict
        Structure contains command parameters
        {'args': ['192.168.100.100'],
        'env': {},
        'cwd': '/tmp',
        'body': ['#/bin/bash', .....],
        'agent_id': 'vm_agent_109',
        'command_id': 1,
        'type_message': 'bash_script',
        'object_type': 'command',
        'check': True}
    """
    monitoring_uri = "http://" + monitoring_ip + ":" + monitoring_port + monitoring_base_path \
                     + "/agent_command/" + command["agent_id"] + "/" + str(command["command_id"])
    try:
        conn = HTTPConnection(monitoring_ip, monitoring_port)
        conn.request("GET", monitoring_uri)
        rsp = conn.getresponse()
        get_command_status = rsp.read()
        get_command_status = get_command_status.decode("utf-8")
        get_command_status = json.loads(get_command_status)
        if rsp.code == 200:
            return get_command_status
    except ConnectionRefusedError:
        log_queue.put(
            ["ERROR", "the Monitoring platform is not running or the connection configuration is wrong"])


def wait_commands_execution(commands):
    """
    Waits until all commands will be executed
    Parameters
    ----------
    commands: list
        List of Commands
    """
    timeout = 1000 #seconds
    tcheck = time.time()
    while True:
        for command in commands:
            if command["check"] == True:
                result = check_command(command)
                if result != None:
                    if result["returncode"] == "0":
                        command["check"] = False
                    else:
                        raise Exception('Command execution error: ' + json.dumps(result, indent=4))
                time.sleep(5)
                if (tcheck + timeout) < time.time():
                    raise Exception('Command execution timeout ' + json.dumps(commands, indent=4))
        all_scripts_executed = True
        for command in commands:
            if command["check"] == True:
                all_scripts_executed = False

        if all_scripts_executed == True:
            break
