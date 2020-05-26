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
        vm_agent_id_dict.update({db_vnf_deployed_info["name"]: db_vnf_deployed_info["agent_id"]})
    vm_ip_address_dict = {}
    for elements in deployed_vnfs_info.values():
        for element in elements:
            vm_ip_address_dict.update(element)
    monitoring_jobs={}

    if "monitoredInfo" in nsd["nsd"].keys():
        monitored_params = nsd["nsd"]["monitoredInfo"]
        for param in monitored_params:
            performanceMetric = param["monitoringParameter"]["performanceMetric"]
            vnf_id = performanceMetric.split(".")[1]
            exporter = param["monitoringParameter"]["exporter"]
            vnf_id_exporter = vnf_id + "_" + exporter
            if vnf_id_exporter not in monitoring_jobs.keys():
                pm_job={}
                instance_name = vnf_id
                vnfd_id = instance_name.rsplit("_", 1)[0]
                pm_job['instance'] = vnf_id
                pm_job['name']= "NS-"+ nsId +"-VNF-" + vnf_id
                pm_job['collectionPeriod'] = 15 # agreed 15 seconds as default
                pm_job['address'] = vm_ip_address_dict.get(vnf_id, None)
                pm_job['port'] = "9100"
                pm_job['vnfdId'] = vnf_id
                pm_job['nsId'] = nsId
                pm_job['exporter'] = exporter
                pm_job['agent_id'] = vm_agent_id_dict[vnf_id]
                pm_job['monitoringParameterId'] = []
                pm_job['monitoringParameterId'].append(param["monitoringParameter"]["monitoringParameterId"])
                pm_job['performanceMetric'] = []
                pm_job['performanceMetric'].append(param["monitoringParameter"]["performanceMetric"])
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
    db_vnf_deployed_infos = nsir_db.get_vnf_deployed_info(nsId)
    vm_agent_id_dict = {}
    for db_vnf_deployed_info in db_vnf_deployed_infos:
        vm_agent_id_dict.update({db_vnf_deployed_info["name"]: db_vnf_deployed_info["agent_id"]})

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
                    old_jobs.append(job)
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
                                    new_pm_job['instance'] = vnf
                                    new_pm_job['vnfId'] = job['vnfdId']
                                    new_pm_job['name'] = "NS-"+ new_pm_job['nsId'] +"-VNF-" + vnf
                                    new_pm_job['agent_id'] = vm_agent_id_dict[vnf]
                                    del new_pm_job['exporterId']
                                    new_jobs.append(new_pm_job)
                                    break
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

    body = {"name": job["name"],
            "endpoint": [ {"address": monitoring_pushgateway_ip,
                           "port": monitoring_pushgateway_port}
                        ],
            "vnfdId": job["vnfdId"],
            "nsId": job["nsId"],
            "instance": job["name"],
            "collectionPeriod": job["collectionPeriod"],
            "metrics_path": "/metrics/" + job["name"]
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

    body = {"prometheus_job": job["name"],
            "agent_id": job["agent_id"],
            "exporter": job["exporter"],
            "labels": [
                {"key": "nsId",
                 "value": job["nsId"]},
                {"key": "vnfdId",
                 "value": job["vnfdId"]},
                {"key": "instance",
                 "value": job["name"]}
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


def get_dashboard_query_v2(nsId, vnfdId, pm):
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
    if (pm.find("cpu") !=-1):
        Prometheusquery = "avg((1 - avg by(instance) (irate(node_cpu_seconds_total{mode=\"idle\",nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId + "\"}[1m]))) * 100)"
    if (pm.find("memory") !=-1):
        Prometheusquery =  "avg by (vnfdId)(((node_memory_MemTotal_bytes{nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId + "\"} - node_memory_MemFree_bytes{nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId + "\"}) / node_memory_MemTotal_bytes{nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId + "\"}) * 100)"
    if (pm.find("disk") !=-1):
        Prometheusquery = "((node_filesystem_size_bytes{fstype=~\"ext4|vfat\", nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId + "\"} - node_filesystem_free_bytes{fstype=~\"ext4|vfat\", nsId=\"" + nsId + "\", vnfdId=\"" + vnfdId + "\"}) / node_filesystem_size_bytes{fstype=~\"ext4|vfat\", nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId + "\"}) * 100"
    if (pm.find("Byte") !=-1):
        port = pm.split(".")[2]
        Prometheusquery = "rate(node_network_receive_bytes_total{device=\"" + port + "\",nsId=\"" + nsId + "\",vnfdId=\"" + vnfdId + "\"}[1m])"
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
                "plottedTime": 60,
                "refreshTime": "5s"
               }
        #checking the different labels of the exporters for a network service
        vnfIds = []
        panels_info = []
        for job in jobs:
            if job['vnfdId'] not in vnfIds:
                # in case there are two instances of the same exporter you make the average
                vnfIds.append(job)
        for job in vnfIds:
            for metric in range(0, len(job["performanceMetric"])):
               panel = {}
               panel['title'] = job["monitoringParameterId"][metric] + "(" + job["performanceMetric"][metric] + ")"
               panel['query'] = get_dashboard_query_v2(job['nsId'], job['vnfdId'], job['performanceMetric'][metric])
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
                "plottedTime": 60,
                "refreshTime": "5s"
               }
        #checking the different labels of the exporters for a network service
        vnfIds = []
        for job in jobs:
            if job['vnfdId'] not in vnfIds:
                vnfIds.append(job)
        for job in vnfIds:
            for metric in range(0, len(job["performanceMetric"])):
               panel = {}
               panel['title'] = job["monitoringParameterId"][metric] + "(" + job["performanceMetric"][metric] + ")"
               panel['query'] = get_dashboard_query_v2(job['nsId'], job['vnfdId'], job['performanceMetric'][metric])
               # panel['size'] = "fullscreen"
               panel['size'] = ""
               body['panels'].append(panel)
        try:
            conn = HTTPConnection(monitoring_ip, monitoring_port)
            conn.request("PUT", monitoring_uri, dumps(body), header)
            rsp = conn.getresponse()
            dashboardInfo = rsp.read()
            dashboardInfo = dashboardInfo.decode("utf-8")
            dashboardInfo = loads(dashboardInfo)
            log_queue.put(["DEBUG", "deployed Dashboard info is:"])
            dashboardInfo['url'] = "http://" + monitoring_ip + ":3000" + dashboardInfo['url']
            log_queue.put(["DEBUG", dumps(dashboardInfo, indent = 4)])
        except ConnectionRefusedError:
                log_queue.put(["ERROR", "the Monitoring platform is not running or the connection configuration is wrong"])
        return {"dashboardId" : dashboardInfo["dashboardId"],
                "dashboardUrl" : dashboardInfo["url"] }

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
        for job in jobs:
            job_elem = configure_monitoring_job_prometheus(job)
            job_elem = start_exporters_on_rvm_agent(job_elem)
            job_ids.append(job_elem)

        # for each job request the Monitoring Configuration Manager to configure the job and save the job_id
        # save the list of jobs in the database
        ns_db.set_monitoring_info(nsId, job_ids)
        # create the dashboard for the monitoring jobs
        dashboard_id = configure_dashboard_v2(nsId, jobs)
        ns_db.set_dashboard_info(nsId, dashboard_id)



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
        jobs = ns_db.get_monitoring_info(nsId)
        dashboard_info = ns_db.get_dashboard_info(nsId)
        if "dashboardId" in dashboard_info.keys():
            stop_dashboard(dashboard_info["dashboardId"])
        dashboard_id = configure_dashboard_v2(nsId, jobs)
        # we rewrite the dasboard info
        ns_db.set_dashboard_info(nsId, dashboard_id)
    else:
        new_jobs = [] # result of scale out operations
        old_jobs = [] # result of scale in operations
        job_ids = []
        [new_jobs, old_jobs] = update_pm_jobs_rvm_agents(nsId, deployed_vnfs_info)
        for job in new_jobs:
            job_elem = configure_monitoring_job_prometheus(job)
            job_elem = start_exporters_on_rvm_agent(job_elem)
            job_ids.append(job_elem)
        # update the list of jobs in the database
        old_jobs_ids = []
        for job_id in old_jobs:
                stop_monitoring_job(job_id['exporterId'])
                stop_exporters_on_rvm_agent(job_id)
                delete_rvm_agent(job_id['agent_id'])
                old_jobs_ids.append(job_id['exporterId'])
        ns_db.update_monitoring_info(nsId, job_ids, old_jobs_ids)

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
        job_ids = ns_db.get_monitoring_info(nsId)
        for job_id in job_ids:
            stop_monitoring_job(job_id['exporterId'])
        # delete monitor jobs from database by posting an empty list
        ns_db.set_monitoring_info(nsId, [])
        dashboard_info = ns_db.get_dashboard_info(nsId)
        if "dashboardId" in dashboard_info.keys():
            stop_dashboard(dashboard_info["dashboardId"])
            ns_db.set_dashboard_info(nsId, {})
    else:
        job_ids = ns_db.get_monitoring_info(nsId)
        for job_id in job_ids:
            stop_monitoring_job(job_id['exporterId'])
            stop_exporters_on_rvm_agent(job_id)
            delete_rvm_agent(job_id['agent_id'])
        # delete monitor jobs from database by posting an empty list
        ns_db.set_monitoring_info(nsId, [])
        dashboard_info = ns_db.get_dashboard_info(nsId)
        if "dashboardId" in dashboard_info.keys():
            stop_dashboard(dashboard_info["dashboardId"])
            ns_db.set_dashboard_info(nsId, {})

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

