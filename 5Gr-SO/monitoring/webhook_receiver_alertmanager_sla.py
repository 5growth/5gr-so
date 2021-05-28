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
from datetime import timedelta, datetime
import pytz
from flask import request
import json
import iso8601
from flask.views import MethodView
from six.moves.configparser import RawConfigParser
from http.client import HTTPConnection

# project imports
from db.alert_db import alert_db
from db.ns_db import ns_db
from nbi import log_queue
from monitoring import alert_configure, monitoring

config = RawConfigParser()
config.read("../../monitoring/monitoring.properties")
so_ip = config.get("ALERTS", "so_scale_ns.ip")
so_port = config.get("ALERTS", "so_scale_ns.port")
so_scale_ns_base_path = config.get("ALERTS", "so_scale_ns.base_path")

class SLAManagerAPI(MethodView):

    def post(self):
        #data_json = request.data
        # data = json.loads(data_json)
        data = request.get_json(force=True)
        if "alerts" in data:
            alerts = data['alerts']
            for alert in alerts:

                labels = (alert['labels'])
                str_starts_at = str(alert['startsAt'])
                alertname = labels["alertname"]
                log_massage = "Received alert: " + alertname + " startsAt: " + str_starts_at + " status: " + alert['status']
                log_queue.put(["INFO", log_massage])

                if alert['status'] == 'resolved':
                    alert_db.set_timestamp(alertname, "")
                    continue

                if alert_db.exists_alert_id(alertname):
                    if is_problem_resolved(alert) == False:
                        log_queue.put(["DEBUG", "Alert is not resolved= " + alertname + " start date = " + str_starts_at])
                        do_request_for_scaling(alertname)
                    continue
                else:
                    continue

        # checks if this log from elastalert
        if "alertname" in data:
            str_starts_at = str(data['startsAt'])
            date_time_obj = datetime.strptime(str_starts_at, "%a %b %d %H:%M:%S %Z %Y")
            str_starts_at = date_time_obj.isoformat()
            alertname = data["alertname"]
            log_massage = "Received log alert: " + alertname + " startsAt: " + str_starts_at
            log_queue.put(["INFO", log_massage])
            if alert_db.exists_alert_id(alertname):
                alert = {'startsAt': str_starts_at}
                alert.update({"labels":{"alertname": alertname}})
                if is_problem_resolved(alert) == False:
                    log_queue.put(["DEBUG", "Alert is not resolved= " + alertname + " start date = " + str_starts_at])
                    do_request_for_scaling(alertname)

        if "aiml" in data: # added to manage the notifications from the execution of the aiml model
            curent_time = datetime.now(pytz.utc)
            notification = data["aiml"]
            log_queue.put(["DEBUG", "Notification from Spark Job: %s" % notification])
            ns_id = notification["nsID"]
            nsInstantiationLevel = notification["nsInstantiationLevel"]
            # cpu_measurement = notification["cpu_measurement"]
            aiml_scaling_info = ns_db.get_aiml_info(ns_id, "scaling")
            currentIL = ns_db.get_ns_il(ns_id)
            if (aiml_scaling_info and (nsInstantiationLevel != currentIL)):
                curent_time2 = datetime.now(pytz.utc)
                timeout = curent_time2-curent_time
                log_queue.put(["INFO", "*****Time measure: SLAManager SLAManager webhook processing scaling: %s"%timeout])
                log_queue.put(["DEBUG", "Generating a scaling operation for nsId: %s from currentIL: %s to newIL: %s" % (ns_id, currentIL, nsInstantiationLevel)])
                # 1 - stop the spark job
                alert_configure.delete_spark_streaming_job(aiml_scaling_info["streamingJobId"])             
                log_queue.put(["INFO", "*****Time measure: SLAManager SLAManager webhook stopped spark job"])
                # 1.5 - remove the kafka topic
                monitoring.delete_kafka_topic(aiml_scaling_info["topicId"])
                log_queue.put(["INFO", "*****Time measure: SLAManager SLAManager webhook deleted kafka topic"])
                # 2 - generate the scaling request
                scale_request = {
                      "scaleType": "SCALE_NS",
                      "scaleNsData": {
                        "scaleNsToLevelData": {
                          "nsInstantiationLevel": nsInstantiationLevel
                        }
                      },
                      "scaleTime": "0"
                   }
                log_queue.put(["DEBUG", "AIML makes an scaling request for nsId: %s"% ns_id])
                log_queue.put(["DEBUG", "AIML scale request:" ])
                #log_queue.put(["DEBUG", json.dumps(scale_request, indent=4)])
                make_request_to_so_nbi(ns_id, scale_request)
                log_queue.put(["INFO", "*****Time measure: SLAManager SLAManager webhook made scaling request"])

            else:
                log_queue.put(["DEBUG", "Not generating a scaling operation for nsId: %s" % (ns_id)])

        return "OK", 200


    def get(self):
        return "200", 200


def is_problem_resolved(alert):
    str_starts_at = str(alert['startsAt'])
    alertname = alert["labels"]["alertname"]
    curent_time = datetime.now(pytz.utc)
    try:
        time_stamp = iso8601.parse_date(alert_db.get_timestamp(alertname))
    except iso8601.iso8601.ParseError:
        log_queue.put(["ERROR", "Error during parse timestamp"])
        time_stamp = datetime.now(pytz.utc)
        alert_db.set_timestamp(alertname, str(datetime.now(pytz.utc)))

    db_alert = alert_db.get_alert(alertname)
    if db_alert == None:
        log_queue.put(["DEBUG", "Alert: " + alertname + " not found in database"])
        return True

    str_timeout = db_alert['cooldownTime']
    timeout = timedelta(seconds=int(str_timeout))
    if curent_time - time_stamp > timeout:
        log_queue.put(["DEBUG", "Timeout unresolved alert = " + alertname + " start date = " + str_starts_at])
        alert_db.set_timestamp(alertname, str(datetime.now(pytz.utc)))
        return False
    else:
        return True


def do_request_for_scaling(alert_id):
    alert = alert_db.get_alert(alert_id)
    ns_id = alert['ns_id']
    ns_status = ns_db.get_ns_status(ns_id)
    # adding code to allow auto-scaling of nested NSs
    # the alert and the autoscaling rules are defined in the nested descriptors
    nested_info = ns_db.get_nested_service_info(ns_id)
    if nested_info:
        # we need to look for the corresponding nested
        nsdId = alert['nsd_id']
        nsId_tmp = ns_id + '_' + nsdId
        particular_nested_info = ns_db.get_particular_nested_service_info(ns_id, nsId_tmp)
        current_il = particular_nested_info['nested_il']
    else:
        current_il = ns_db.get_ns_il(alert['ns_id'])
    rule_actions = alert['ruleActions']
    for rule_action in rule_actions:
        if rule_action['scaleNsToLevelData']['nsInstantiationLevel'] == current_il:
            log_queue.put(["DEBUG", "Current nsInstantiationLevel for nsId: " + ns_id + 'and Alert nsInstantiationLevel is the same'])
            continue
        if ns_status in ["FAILED", "TERMINATED", "INSTANTIATING", "SCALING"]:
            log_queue.put(["DEBUG","Current Status is " + ns_status + " for nsId: " + ns_id ])
            log_queue.put(["DEBUG", "This status is not fit to scaling actions"])
            continue

        log_queue.put(["DEBUG", "Do scaling request for alert: " + alert_id])
        request_to_so_scale_ns(alert)


def request_to_so_scale_ns(alert):
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

    ns_id = alert['ns_id']
    # adding code to allow auto-scaling of nested NSs
    # the alert and the autoscaling rules are defined in the nested descriptors
    nested_info = ns_db.get_nested_service_info(ns_id)
    if nested_info:
        # we need to look for the corresponding nested
        nsdId = alert['nsd_id']
        ns_id = ns_id + '_' + nsdId   
 
    rule_actions = alert['ruleActions']
    for rule_action in rule_actions:

        scale_request ={
              "scaleType": "SCALE_NS",
              "scaleNsData": {
                "scaleNsToLevelData": {
                  "nsInstantiationLevel": rule_action['scaleNsToLevelData']['nsInstantiationLevel']
                }
              },
              "scaleTime": "0"
            }
        make_request_to_so_nbi(ns_id, scale_request)

def make_request_to_so_nbi(ns_id, scale_request):

    header = {'Content-Type': 'application/json',
              'Accept': 'application/json'}

    scale_uri = "http://" + so_ip + ":" + so_port + so_scale_ns_base_path + "/" + ns_id + "/scale"

    try:
        conn = HTTPConnection(so_ip, so_port, timeout=10)
        conn.request("PUT", scale_uri, body=json.dumps(scale_request), headers=header)
        rsp = conn.getresponse()
        resources = rsp.read()
        resp_scale = resources.decode("utf-8")
        log_queue.put(["DEBUG", "Request from SO on Scale are:"])
        log_queue.put(["DEBUG", scale_request])
        log_queue.put(["DEBUG", "Response from SO on Scale request are:"])
        log_queue.put(["DEBUG", resp_scale])
        resp_scale = json.loads(resp_scale)
        log_queue.put(["DEBUG", "Response from SO on Scale request are:"])
        log_queue.put(["DEBUG", json.dumps(resp_scale, indent=4)])
        conn.close()
    except ConnectionRefusedError:
        # the SO on Scale request returned wrong response
        log_queue.put(["ERROR", "SO on Scale request returned wrong response"])

