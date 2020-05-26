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
import traceback
import time
from http.client import HTTPConnection
from six.moves.configparser import RawConfigParser
import json
from os import path, remove

# project imports
from nbi import log_queue
from db.ns_db import ns_db
from db.alert_db import alert_db
from monitoring import monitoring

# load monitoring configuration sla manager properties
config = RawConfigParser()
config.read("../../monitoring/monitoring.properties")
monitoring_platform_ip = config.get("ALERTS", "monitoring_platform.ip")
monitoring_platform_port = config.get("ALERTS", "monitoring_platform.port")
monitoring_platform_base_path = config.get("ALERTS", "monitoring_platform.base_path")
alert_target = config.get("ALERTS", "monitoring_platform.alert_target")
kafka_ip = config.get("MONITORING", "monitoring.kafka_ip")
kafka_port = config.get("MONITORING", "monitoring.kafka_port")
expressions = dict(config.items("EXPRESSIONS"))
# reading AIML variables
config.read("../../aiml.properties")
#AIML
aiml_platform_ip = config.get("AIML", "aiml.ip")
aiml_platform_port = config.get("AIML", "aiml.port")
aiml_platform_base_path = config.get("AIML", "aiml.base_path")
#log_queue.put(["DEBUG", "The AIML parameters are: %s, %s, %s" % (aiml_platform_ip, aiml_platform_port, aiml_platform_base_path)])
#SPARK
spark_ip = config.get("SPARK", "spark.ip")
spark_port = config.get("SPARK", "spark.port")
spark_folder = path.realpath(path.join(path.dirname(path.realpath(__file__)), '../spark_streaming_jobs'))
#log_queue.put(["DEBUG", "The spark parameters are: %s, %s, %s" % (spark_ip, spark_port, spark_folder)])


########################################################################################################################
# PRIVATE METHODS                                                                                                      #
########################################################################################################################

def start_spark_streaming_job(nsId, kafka_topic, streaming_class, model_name, time_interval, kafka_ip, alert_target, status_file_location):
    """
    Create a spark job to read data from the kafka topic and process it according to the 
    provided streaming class and model
    Parameters
    ----------
    nsId: string
       The id of the instantiated network service
    kafka_topic: string
        Delete the specified kafka_topic 
    Returns
    -------
    spark_job_id: string
       The id of the created spark job
    """
    header = {'Content-Type': 'application/json',
               'Accept': 'application/json'}
    timeout = 10
    spark_uri = 'http://' + spark_ip + ':' + spark_port + '/batches'
    model_location = spark_folder + "/" + model_name # consider in the future that it will be in a folder
    streaming_location = "local:" + spark_folder + "/" + streaming_class
    log_queue.put(["DEBUG", "Creating Spark streaming job ..."])
    data = { "conf": { "spark.jars.packages":
             "org.apache.spark:spark-streaming-kafka-0-10_2.11:2.4.0,com.typesafe:config:1.3.2,net.liftweb:lift-json_2.11:3.0"},
             "file": streaming_location,
             "className": "com.growth.spark.Streaming", #this could be the same name for all the jars
             "args": ["dev", kafka_ip, kafka_topic, model_location, nsId, time_interval, alert_target, status_file_location]}
    try:
        conn = HTTPConnection(spark_ip, spark_port, timeout = timeout)
        conn.request("POST", spark_uri, body=json.dumps(data), headers=header)
        resp = conn.getresponse().read()
        job = resp.decode("utf-8")
        log_queue.put(["DEBUG", "Spark jobs is:"])
        log_queue.put(["DEBUG", job])
        spark_job = json.loads(job)
        spark_job_id = spark_job['id']
        spark_job_state = spark_job['state']
        log_queue.put(["DEBUG", "Spark jobs id is:"])
        log_queue.put(["DEBUG", spark_job_id])
        log_queue.put(["DEBUG", "Spark jobs state is:"])
        log_queue.put(["DEBUG", spark_job_state])

        # Assuming that the job works, we wait up to 60 secs, sampling every 5 seconds to check that 
        # spark job starts correctly
        time_to_wait = 60
        start_time = time.time()
        current_time = 0
        while ((current_time < time_to_wait) and spark_job_state != "running"):
             spark_job_state = get_spark_streaming_job_status(spark_job_id)
             log_queue.put(["DEBUG", "Starting spark job.... state: %s" % (spark_job_state)])
             if (spark_job_state == "running" or spark_job_state == "dead"):
                 break
             current_time = time.time() - start_time
             time.sleep(5)
        if (spark_job_state != "running"):
            spark_job_id = None             
        conn.close()
    except ConnectionRefusedError:
         # Spark is not running or the connection configuration is wrong
        log_queue.put(["ERROR", "Spark is not running or the connection configuration is wrong"])
        spark_job_id = None   
    return spark_job_id
    
def get_spark_streaming_job_status (spark_job_id):
    """
    Checks the status of the spark job
    Parameters
    ----------
    spark_job_id: string
        The identifier of the spark job to check
    Returns
    -------
    status: string
        The status of the spark job
    """
    header = {'Content-Type': 'application/json',
              'Accept': 'application/json'}
    timeout = 10
    spark_uri = 'http://' + spark_ip + ':' + spark_port + '/batches' + '/' + str (spark_job_id)
    log_queue.put(["DEBUG", "Checking status of Spark streaming job ..."])
    try:
        conn = HTTPConnection(spark_ip, spark_port, timeout = timeout)
        conn.request("GET", spark_uri, None, headers=header)
        resp = conn.getresponse().read()
        job = resp.decode("utf-8")
        log_queue.put(["DEBUG", "Spark job is:"])
        log_queue.put(["DEBUG", job])
        spark_job = json.loads(job)
        spark_job_state = spark_job['state']
        log_queue.put(["DEBUG", "Spark job stat is:"])
        log_queue.put(["DEBUG", spark_job_state])
        conn.close()
    except ConnectionRefusedError:
         # Spark is not running or the connection configuration is wrong
        log_queue.put(["ERROR", "Spark is not running or the connection configuration is wrong"])
        spark_job_state = "dead"   
    return spark_job_state

def delete_spark_streaming_job(spark_job_id):
    """
    Create a spark job to read data from the kafka topic and process it according to the 
    provided streaming class and model
    Parameters
    ----------
    nsId: string
       The id of the instantiated network service
    kafka_topic: string
        Delete the specified kafka_topic 
    Returns
    -------
    """
    header = {'Content-Type': 'application/json',
               'Accept': 'application/json'}
    timeout = 10
    spark_uri = 'http://' + spark_ip + ':' + spark_port + '/batches/' + str(spark_job_id)
    try:
        conn = HTTPConnection(spark_ip, spark_port, timeout=timeout)
        conn.request("DELETE", spark_uri, headers=header)
        rsp = conn.getresponse().read()
        resp = rsp.decode("utf-8")
        # log_queue.put(["DEBUG", "Spark jobs delete answer is:"])
        # log_queue.put(["DEBUG", resp])
        resp = json.loads(resp)
        if (resp["msg"] == "deleted"):
            log_queue.put(["DEBUG", "Spark job (id: %s) deleted correctly" % (str(spark_job_id))])
        else:
            log_queue.put(["DEBUG", "Spark job state: %s"% (resp["msg"])])
        conn.close()
    except ConnectionRefusedError:
        # Spark is not running or the connection configuration is wrong
        log_queue.put(["ERROR", "Spark is not running or the connection configuration is wrong"])

def get_pm_alerts(nsd, deployed_vnfs_info, ns_id):
    """
    Parses the nsd and vnfd descriptors to find possible alerts jobs
    Parameters
    ----------
    nsd: json
        Network service descriptor
    deployed_vnfs_info: json
        dictionary with connection points of the differents vnfs after instantiating
    ns_id:
        String with the Network Service Id
    Returns
    -------
    List
        List of dictionaries with info of the monitoring jobs
    """
    alerts = []
    if "autoScalingRule" in nsd["nsd"].keys():
        auto_scaling_rules = nsd["nsd"]["autoScalingRule"]
        monitored_infos = nsd["nsd"]["monitoredInfo"]
        monitoring_jobs = ns_db.get_monitoring_info(ns_id)


        for auto_scaling_rule in auto_scaling_rules:
            summury_alert_query = ""
            scaling_criterias = auto_scaling_rule['ruleCondition']['scalingCriteria']
            # detect OperationType
            scaling_operation = "OR"
            if 'scaleInOperationType' in auto_scaling_rule:
                scaling_operation = auto_scaling_rule['scaleInOperationType']
            if 'scaleOutOperationType' in auto_scaling_rule:
                scaling_operation = auto_scaling_rule['scaleOutOperationType']

            # parsing scalingCriteria
            for idx_scaling_criterias, scaling_criteria in enumerate(scaling_criterias):
                pm_alert = {}
                # mapping between autoScalingRule -> ruleCondition -> scalingCriteria -> nsMonitoringParamRef and
                # ns -> monitoring_jobs -> monitoringParameterId
                # get nsMonitoringParamRef
                ns_monitoring_param_ref = scaling_criteria['nsMonitoringParamRef']
                performance_metric = ""
                alert_metric = ""
                index_monitor_parameter = -1
                # Get monitored job id from ns
                for idx, monitoring_job in enumerate(monitoring_jobs):
                    if ns_monitoring_param_ref in monitoring_job['monitoringParameterId']:
                        idx_in_monitoring_parameter_id = monitoring_job['monitoringParameterId'].index(ns_monitoring_param_ref)
                        index_monitor_parameter = idx
                        performance_metric = monitoring_job['performanceMetric'][idx_in_monitoring_parameter_id]
                        break

                # Error if Alert parameter wasn't found between monitored parameters
                if index_monitor_parameter == -1:
                    exception_msg = "Alert parameter " + ns_monitoring_param_ref + " is not found in monitored parameters"
                    log_queue.put(["ERROR", exception_msg])
                    raise Exception(exception_msg)

                monitoring_job = monitoring_jobs[index_monitor_parameter]
                # convert expression from IFA to PQL
                alert_query = convert_expresion(performance_metric, monitoring_job['exporterId'], ns_id, monitoring_job['vnfdId'])


                # Creating summary query for request
                if (idx_scaling_criterias == 0) and (len(scaling_criterias) == 1):
                    summury_alert_query = alert_query

                if (idx_scaling_criterias != (len(scaling_criterias) - 1)) and (len(scaling_criterias) > 1):
                    summury_alert_query = summury_alert_query + "(" + alert_query + ") " + scaling_operation + " "

                if (idx_scaling_criterias == (len(scaling_criterias) - 1)) and (len(scaling_criterias) > 1):
                    summury_alert_query = summury_alert_query + "(" + alert_query + ")"

            # collect information for ALERT database and for requests for alert creating
            pm_alert['rule_id'] = auto_scaling_rule['ruleId']
            pm_alert['query'] = summury_alert_query
            pm_alert['label'] = "label"
            pm_alert['severity'] = "warning"
            if 'scaleOutThreshold' in scaling_criteria:
                pm_alert['value'] = scaling_criteria['scaleOutThreshold']
            if 'scaleInThreshold' in scaling_criteria:
                pm_alert['value'] = scaling_criteria['scaleInThreshold']
            if 'scaleOutRelationalOperation' in scaling_criteria:
                pm_alert['kind'] = scaling_criteria['scaleOutRelationalOperation']
            if 'scaleInRelationalOperation' in scaling_criteria:
                pm_alert['kind'] = scaling_criteria['scaleInRelationalOperation']
            try:
                pm_alert['kind'] = convert_relational_operation_from_nsd_to_monitoring_platform(pm_alert['kind'])
            except KeyError as e:
                exception_msg = "Relation operation value for rule " + pm_alert['rule_id'] + " + has wrong format"
                log_queue.put(["ERROR", exception_msg])
                raise Exception(exception_msg)

            pm_alert['enabled'] = auto_scaling_rule['ruleCondition']['enabled']
            pm_alert['cooldownTime'] = auto_scaling_rule['ruleCondition']['cooldownTime']
            pm_alert['thresholdTime'] = auto_scaling_rule['ruleCondition']['thresholdTime']
            pm_alert['target'] = alert_target
            pm_alert['ruleActions'] = auto_scaling_rule['ruleActions']
            alerts.append(pm_alert)
    return alerts

def convert_relational_operation_from_nsd_to_monitoring_platform(operation):
    # this method convert relation operation from NSD format to monitoring platform format
    map_translation = {}
    map_translation['GT'] = 'G'
    map_translation['GE'] = 'GEQ'
    map_translation['LT'] = 'L'
    map_translation['LE'] = 'LEQ'
    map_translation['EQ'] = 'EQ'
    map_translation['NEQ'] = 'NEQ'

    monitoring_platform_operation = map_translation[operation]

    return monitoring_platform_operation

def convert_expresion(performance_metric, job_id, ns_id, vnfd_id):
    performance_metric_parts = performance_metric.split(".")
    try:
        return_expresion = expressions[(performance_metric_parts[0].lower())]
    except KeyError as er:
        exception_msg = "Error to create expressions for the Monitoring platform \n"
        exception_msg += "Can't find key expressions for " + str(er)
        log_queue.put(["ERROR", exception_msg])
        raise Exception(exception_msg)
    return_expresion = return_expresion.replace("{job_id}", 'job="' + str(job_id) + '"')
    return_expresion = return_expresion.replace("{nsId}", 'nsId="' + str(ns_id) + '"')
    return_expresion = return_expresion.replace("{vnfdId}", 'vnfdId="' + str(vnfd_id) + '"')
    if performance_metric_parts[0] == "ByteIncoming":
        return_expresion = return_expresion.replace("{port}", 'device="' + str(performance_metric_parts[2]) + '"')
    return return_expresion

def get_alerts():
    """
    Parameters
    ----------
    Returns
    -------
    name: type
        return alerts
    """
    header = {'Accept': 'application/json'}
    monitoring_uri = "http://" + monitoring_platform_ip + ":" + monitoring_platform_port + monitoring_platform_base_path + "/alert"
    try:
        conn = HTTPConnection(monitoring_platform_ip, monitoring_platform_port)
        conn.request("GET", monitoring_uri, None, header)
        rsp = conn.getresponse()
        resources = rsp.read()
        alerts = resources.decode("utf-8")
        log_queue.put(["DEBUG", "Alerts from Config Manager are:"])
        log_queue.put(["DEBUG", alerts])
        alerts = json.loads(alerts)
        log_queue.put(["DEBUG", "Alerts from Config Manager are:"])
        log_queue.put(["DEBUG", json.dumps(alerts, indent=4)])
        conn.close()
    except ConnectionRefusedError:
        # the Config Manager is not running or the connection configuration is wrong
        log_queue.put(["ERROR", "the Config Manager is not running or the connection configuration is wrong"])
    return alerts

def get_alert(alert_id):
    """
    Parameters
    ----------
    Returns
    -------
    name: type
        return alert
    """
    header = {'Accept': 'application/json'}
    monitoring_uri = "http://" + monitoring_platform_ip + ":" + monitoring_platform_port + monitoring_platform_base_path + "/alert/" + str(
        alert_id)
    try:
        conn = HTTPConnection(monitoring_platform_ip, monitoring_platform_port)
        conn.request("GET", monitoring_uri, None, header)
        rsp = conn.getresponse()
        resources = rsp.read()
        alert = resources.decode("utf-8")
        log_queue.put(["DEBUG", "Alerts from Config Manager are:"])
        log_queue.put(["DEBUG", alert])
        alert = json.loads(alert)
        log_queue.put(["DEBUG", "Alerts from Config Manager are:"])
        log_queue.put(["DEBUG", json.dumps(alert, indent=4)])
        conn.close()
    except ConnectionRefusedError:
        # the Config Manager is not running or the connection configuration is wrong
        log_queue.put(["ERROR", "the Config Manager is not running or the connection configuration is wrong"])
    return alert

def create_alert(alert):
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
    header = {'Accept': 'application/json',
              'Content-Type': 'application/json'
              }
    monitoring_uri = "http://" + monitoring_platform_ip + ":" + monitoring_platform_port + monitoring_platform_base_path + "/alert"
    try:
        conn = HTTPConnection(monitoring_platform_ip, monitoring_platform_port)
        conn.request("POST", monitoring_uri, body=json.dumps(alert), headers=header)
        rsp = conn.getresponse()
        resources = rsp.read()
        resp_alert = resources.decode("utf-8")
        log_queue.put(["DEBUG", "Alert from Config Manager are:"])
        log_queue.put(["DEBUG", resp_alert])
        resp_alert = json.loads(resp_alert)
        log_queue.put(["DEBUG", "Alert from Config Manager are:"])
        log_queue.put(["DEBUG", json.dumps(resp_alert, indent=4)])
        conn.close()
    except ConnectionRefusedError:
        # the Config Manager is not running or the connection configuration is wrong
        log_queue.put(["ERROR", "the Config Manager is not running or the connection configuration is wrong"])
    return resp_alert

def update_alert(alert):
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
    header = {'Accept': 'application/json',
              'Content-Type': 'application/json'
              }
    monitoring_uri = "http://" + monitoring_platform_ip + ":" + monitoring_platform_port + monitoring_platform_base_path + "/alert/" + str(
        alert['alertId'])
    print(monitoring_uri)
    try:
        conn = HTTPConnection(monitoring_platform_ip, monitoring_platform_port)
        conn.request("PUT", monitoring_uri, body=json.dumps(alert), headers=header)
        rsp = conn.getresponse()
        resources = rsp.read()
        resp_alert = resources.decode("utf-8")
        log_queue.put(["DEBUG", "Alert from Config Manager are:"])
        log_queue.put(["DEBUG", resp_alert])
        resp_alert = json.loads(resp_alert)
        log_queue.put(["DEBUG", "Alert from Config Manager are:"])
        log_queue.put(["DEBUG", json.dumps(resp_alert, indent=4)])
        conn.close()
    except ConnectionRefusedError:
        # the Config Manager is not running or the connection configuration is wrong
        log_queue.put(["ERROR", "the Config Manager is not running or the connection configuration is wrong"])
    return resp_alert

def delete_alert(alert_id):
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
    monitoring_uri = "http://" + monitoring_platform_ip + ":" + monitoring_platform_port + monitoring_platform_base_path + "/alert/" + str(
        alert_id)
    try:
        conn = HTTPConnection(monitoring_platform_ip, monitoring_platform_port)
        conn.request("DELETE", monitoring_uri, headers=header)
        rsp = conn.getresponse()
        resources = rsp.read()
        resp_alert = resources.decode("utf-8")
        log_queue.put(["DEBUG", "Alert from Config Manager are:"])
        log_queue.put(["DEBUG", resp_alert])
        resp_alert = json.loads(resp_alert)
        log_queue.put(["DEBUG", "Alert from Config Manager are:"])
        log_queue.put(["DEBUG", json.dumps(resp_alert, indent=4)])
        conn.close()
    except ConnectionRefusedError:
        # the Config Manager is not running or the connection configuration is wrong
        log_queue.put(["ERROR", "the Config Manager is not running or the connection configuration is wrong"])

def configure_ns_alerts(nsId, nsdId, nsd, vnfds, deployed_vnfs_info):
    """
    """
    # parse NSD / VNFDs to get the list of monitoring jobs to be configured and its information
    # ! we need the input of the vnfds, to have the endpoints!
    alerts_dict = {}
    alert_db_entity = {}
    # 5Growth I4 R1: AIML scaling rules have prevalence over autoscaling rules
    auto_scaling = True
    if "aimlRules" in nsd["nsd"].keys():
        for rule in nsd["nsd"]["aimlRules"]:
            if (rule["problem"] == "scaling"):
                auto_scaling = False
                log_queue.put(["DEBUG", "Scaling operation driven by AIML"])
            else:
                auto_scaling = True
                log_queue.put(["DEBUG", "Scaling operation driven by Autoscaling rules"])
    if (auto_scaling):
        log_queue.put(["DEBUG", "Configuring Alerts"])
        alerts = get_pm_alerts(nsd, deployed_vnfs_info, nsId)
        # for each job request the Monitoring Configuration Manager to configure the alert and save the alert_id
        for alert_idx, alert in enumerate(alerts):
            alert_request = {
                "alertName": alert['rule_id'],
                'query': alert['query'],
                "labels": [
                    # {
                    #     "key": "string",
                    #     "value": "string"
                    # }
                ],
                'severity': alert['severity'],
                'value': alert['value'],
                'kind': alert['kind'],
                'for': str(alert['thresholdTime']) + "s",
                'target': alert['target']
            }
            result_alert = create_alert(alert_request)
            # send alert request
            alert_id = result_alert['alertId']
            alerts[alert_idx].update({'alertId': alert_id})
            alerts[alert_idx].update({'nsId': nsId})
            alerts_dict[alert_id] = alerts[alert_idx]
            # create object to save in db alerts
            alert_db_entity = {}
            alert_db_entity['alert_id'] = alert_id
            alert_db_entity['status'] = ""
            alert_db_entity['nsd_id'] = nsdId
            alert_db_entity['ns_id'] = nsId
            alert_db_entity['rule_id'] = alert['rule_id']
            alert_db_entity['thresholdTime'] = alert['thresholdTime']
            alert_db_entity['cooldownTime'] = alert['cooldownTime']
            alert_db_entity['enabled'] = alert['enabled']
            alert_db_entity['ruleActions'] = alert['ruleActions']
            alert_db_entity['target'] = alert['target']
            alert_db_entity['timestamp'] = ""
            alert_db.create_alert_record(alert_db_entity)
    # save the list of alerts in the database
    ns_db.set_alert_info(nsId, alerts_dict)

def configure_ns_aiml_scale_work(nsId, nsdId, nsd_json, vnfds_json, sap_info):
    """
    Parses the nsd to find possible aiml scale work
    Parameters
    ----------
    nsId:
        String with the Network Service Id 
    nsdId: string
        String with the kind of Ns associated to the nsId
    nsd_json: json 
        Network service descriptor
    vnfds_json: dict
        Dict with json of the virtual network functions
    sap_info:  dict
        information with the service access point associated to the deployed vnfs
    Returns
    -------
    """
    aiml_scale_dict = {}
    aiml_scaling = False
    # steps:
    # 1 - check that there is an scaling aiml work. Assuming, there is one:
    if "aimlRules" in nsd_json["nsd"].keys():
        for rule in nsd_json["nsd"]["aimlRules"]:
            if (rule["problem"] == "scaling"):
                aiml_scaling = True
                aiml_element = rule
                log_queue.put(["DEBUG", "Scaling operation driven by AIML"])
                break
    if (aiml_scaling):    
        # 2 - create kafka topic
        problem = aiml_element["problem"]
        kafka_topic = monitoring.create_kafka_topic(nsId, problem)
        log_queue.put(["DEBUG", "The created kafka_topic is: %s" % (kafka_topic)])
        if (kafka_topic):
            # 3 - make a call to config manager to create association between monitoring
            #     parameters and kafka topic, so Prometheus publish the info in kafka topic
            scrape_jobs = get_performance_metric_for_aiml_rule(nsId, aiml_element, nsd_json)
            log_queue.put(["DEBUG", "Scraper jobs: "])
            log_queue.put(["DEBUG", json.dumps(scrape_jobs, indent=4)])
            
            scrapes_dict = {}
            collectionPeriod = 1 # we will choose the biggest one, between those used
            for scrape_job in scrape_jobs:
                scraper = monitoring.create_prometheus_scraper(nsId, kafka_topic, scrape_job['vnf'], scrape_job['metric'], scrape_job['expression'], scrape_job['collectionPeriod'])
                scrapes_dict.update({scraper['scraperId']: scraper})
                if (scrape_job["collectionPeriod"] > collectionPeriod):
                    collectionPeriod = scrape_job["collectionPeriod"]
            # 4 - download the model and the streaming class, save the files in the spark_folder
            # 4.1 - for the streaming class (jar file), we need a common folder and rename the file as class+kafka_topic, but for the model, 
            # 4.2 - we will create a new folder in the spark folder, called like the kafka_topic, for the moment static
            # streaming_class = "5growth_polito_2.11-0.1.jar"
            # model_name = "spark-random-forest-model"            
            streaming_class = "5growth_vCDN_2.11-0.1.jar"
            model_name = "spark-random-forest-model-vCDN"           
            status_file = spark_folder + "/" + kafka_topic + ".txt"            
            log_queue.put(["DEBUG", "Status file: %s"%status_file])
            # 5 - start the spark job
            # spark_job_id = start_spark_streaming_job(nsId, kafka_topic, streaming_class, model_name)
            spark_job_id = start_spark_streaming_job(nsId, kafka_topic, streaming_class, model_name, collectionPeriod, \
                          kafka_ip + ":" + kafka_port, alert_target, status_file)
            if (spark_job_id == None):
                log_queue.put(["DEBUG", "Failure in the creation of the spark streaming job"])
                return
            log_queue.put(["DEBUG", "The created spark_job_id is: %s"% (spark_job_id)])
            # 6 - publish the currentIL in kafka topic
            currentIL = ns_db.get_ns_il(nsId)
            current_IL = [{"type_message": "nsStatusMetrics",
                             "metric": {
                                 "__name__": "nsInstantiationLevel",
                                 "nsId": nsId,
                             },
                          "value": currentIL
                          }]
            monitoring.publish_json_kafka(kafka_topic, current_IL)         
            # 7.1 - create the element to be saved in the database
            aiml_scale_dict["topicId"]= kafka_topic
            aiml_scale_dict["streamingClass"] = streaming_class
            aiml_scale_dict["model"] = model_name
            aiml_scale_dict["streamingJobId"] = spark_job_id
            aiml_scale_dict["collectionPeriod"] = collectionPeriod
            # identifiers returned in step 3
            aiml_scale_dict["scrapperJobs"] = scrapes_dict
    # 7.2 - save the info in ns_db. Since there maybe other aiml job, we save this info as another element    
    # save the list of alerts in the database
    ns_db.set_aiml_info(nsId, "scaling", aiml_scale_dict)
    
def update_ns_aiml_scale_work(nsId, aiml_scaling_info):
    """
    After the scaling produced by the AIML notification, the 
    spark job has to be resubmitted and the new IL published in the kafka topic
    Parameters
    ----------
    nsId:
        String with the Network Service Id 
    aiml_scaling_info: dict
        Dictionary with the information generated when creating the scaling aiml work
    Returns
    -------
    """
    # steps:
    log_queue.put(["DEBUG", "Updating the AIML info after scaling for nsId: %s and info:"% nsId])
    log_queue.put(["DEBUG", json.dumps(aiml_scaling_info,indent=4)])
    kafka_topic = aiml_scaling_info["topicId"]
    streaming_class = aiml_scaling_info["streamingClass"]
    model_name = aiml_scaling_info["model"]
    collectionPeriod = aiml_scaling_info["collectionPeriod"]
    # 1 - restart spark job
    # spark_job_id = start_spark_streaming_job(nsId, kafka_topic, streaming_class, model_name)
    status_file = spark_folder + "/" + kafka_topic + ".txt"
    spark_job_id = start_spark_streaming_job(nsId, kafka_topic, streaming_class, model_name, \
                   collectionPeriod, kafka_ip + ":" + kafka_port, alert_target, status_file)
    aiml_scaling_info["streamingJobId"] = spark_job_id
    # 2 - publish the IL in the kafka topic
    currentIL = ns_db.get_ns_il(nsId)
    #current_IL = { "key": "currentIL",
    #               "value": currentIL}
    current_IL = {"type_message": "nsStatusMetrics",
                     "metric": {
                         "__name__": "nsInstantiationLevel",
                         "nsId": nsId,
                     },
                  "value": currentIL
                 }    
    monitoring.publish_json_kafka(kafka_topic, currentIL)         
    # 3 - update the db
    log_queue.put(["DEBUG","New scaling info: "])
    log_queue.put(["DEBUG", json.dumps(aiml_scaling_info, indent=4)])
    ns_db.set_aiml_info(nsId, "scaling", aiml_scaling_info)
    
def delete_ns_alerts(nsId):
    """
    """
    # parse NSD / VNFDs to get the list of alerts to be configured and its information
    alerts = ns_db.get_alerts_info(nsId)
    for alert in alerts:
        delete_alert(alert)
    # delete monitor jobs from database by posting an empty list
    ns_db.set_alert_info(nsId, [])

def delete_ns_aiml_scale_work(nsId):
    """
    Terminates the aiml scale work
    Parameters
    ----------
    nsId:
        String with the Network Service Id 
    Returns
    -------
    """
    # steps:
    aiml_scaling_info = ns_db.get_aiml_info(nsId, "scaling")
    log_queue.put(["DEBUG", "The info in aiml_scaling_info: "])
    log_queue.put(["DEBUG", json.dumps(aiml_scaling_info, indent=4)])
    if (aiml_scaling_info):
        kafka_topic = aiml_scaling_info["topicId"]
        # 1 - stop the spark job, in addition, remove the spark jar file from the repo
        delete_spark_streaming_job(aiml_scaling_info["streamingJobId"])
        # 2 - delete the association between monitoring parameters and kafka topic
        prometheus_scrapers = aiml_scaling_info["scrapperJobs"]
        for scraper_id in prometheus_scrapers.keys():
            monitoring.delete_prometheus_scraper(scraper_id)
        # 3 - remove the Kafka Topic
        monitoring.delete_kafka_topic(aiml_scaling_info["topicId"])
        # 4 - Remove the jar file and the folder model
        # 4.5 delete status file
        status_file = spark_folder + "/" + kafka_topic + ".txt"
        remove(status_file)
        # 5 - remove the info in ns_db
        ns_db.set_aiml_info(nsId, "scaling", {})

def get_performance_metric_for_aiml_rule(nsId, aiml_element, nsd_json):
    return_list = []
    # monitored_infos = nsd_json['nsd']['monitoredInfo']
    # for param_ref in aiml_element['nsMonitoringParamRef']:
        # for monitored_info in monitored_infos:
            # monitoring_parameter_id = monitored_info['monitoringParameter']['monitoringParameterId']
            # performance_metric = monitored_info['monitoringParameter']['performanceMetric']
            # if monitoring_parameter_id == param_ref:
                # metric, vnf  = performance_metric.split(".")
                # expression = convert_expresion(performance_metric, None, nsId, vnf)
                # return_value = {
                    # "expression": expression,
                    # "vnf": vnf,
                    # "metric": metric
                # }
                # return_list.append(return_value)
            # print(param_ref)
    panels_info = ns_db.get_dashboard_info(nsId)["panelsInfo"]
    for panel in panels_info:
        if (panel["monitoringParameterId"] in aiml_element["nsMonitoringParamRef"]):
            performance_metric = panel["performanceMetric"]
            metric, vnf  = panel["performanceMetric"].split(".")
            expression = convert_expresion(performance_metric, None, nsId, vnf)
            return_value = {
                    "expression": expression,
                    "vnf": vnf,
                    "metric": metric,
                    "collectionPeriod": panel["collectionPeriod"]
                }
            return_list.append(return_value)
            print(panel["monitoringParameterId"])
    return return_list

