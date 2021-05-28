# Copyright 2018 CTTC www.cttc.es
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
This file implements the Service Orchestration Engine Parent (soep): for federation purposes.
"""

# python imports
from uuid import uuid4
from multiprocessing import Process, Queue
from pymongo import MongoClient
from json import dumps, loads, load
from six.moves.configparser import RawConfigParser
from http.client import HTTPConnection
from datetime import datetime
import sys
import time
import wget
import tarfile
import os
import copy
import socket

# project imports
from db.ns_db import ns_db
from db.nsd_db import nsd_db
from db.vnfd_db import vnfd_db
from db.appd_db import appd_db
from db.pnfd_db import pnfd_db
from db.operation_db import operation_db
from db.notification_db import notification_db
from sm.soe import soe
from nbi import log_queue
from monitoring import monitoring, alert_configure
from sm.crooe import crooe

# dict to save processes by its nsId
processes_parent = {}

# dict with the IP of the federated domains. Assuming they are using a 5Gr-arch
fed_domain= {}
available_VS = []
config = RawConfigParser()
config.read("../../sm/soe/federation.properties")
number_fed_domains= int(config.get("FEDERATION", "number"))
for i in range (1,number_fed_domains+1):
  domain = "Provider"+str(i)
  try:
    fed_domain[domain] = socket.gethostbyname(config.get("FEDERATION", domain))
  except socket.gaierror:
      print(["Error", "Federation domain was not found %s" % (domain)])
#log_queue.put(["DEBUG", "SOEp reading federated domains: %s" % (fed_domain)])

ewbi_port=config.get("FEDERATION", "ewbi_port")
ewbi_path=config.get("FEDERATION", "ewbi_path")

config.read("../../sm/soe/vs.properties")
number_vs= int(config.get("VS", "number"))
for i in range(1, number_vs+1):
    vs = "VS"+str(i)
    try:
        vs_name = config.get("VS", vs)
        addr = socket.gethostbyname(vs_name)
    except socket.gaierror:
        addr = "127.0.0.1"
        print(["Error",  vs + " with name: %s was not found" % (vs_name)])
        print(["Error", vs + " will be use %s" % (addr)])
    available_VS.append(addr)
# log_queue.put(["DEBUG", "SOEp reading available_VS: %s" % (available_VS)])

# Parameters for HTTP Connection
port = "8080"
headers = {'Content-Type': 'application/json',
           'Accept': 'application/json'}
timeout = 10

########################################################################################################################
# PRIVATE METHODS                                                                                                      #
########################################################################################################################

def check_df_compatibilities(nested_record, composite_nsd_json, body):
    """
    Function description
    Parameters
    ----------
    nested_record: dict
        Record of the nested service that you want to attach you. Extracted from ns_db.Identifier of the service
    composite_nsd_json: dict
        Nsd json of the composite network service .
    body: struct
        Body of the request where we will extract the requested deployment flavour and instantiation level 
    Returns
    -------
    BooleanTrue or False
        True: when the deployment flavour and instantiation level of the nested and the composite are compatible
        False: otherwise
    """
    nested_il = nested_record["nsInstantiationLevelId"]
    composite_df = body.flavour_id
    composite_il = body.ns_instantiation_level_id
    for df in composite_nsd_json["nsd"]["nsDf"]:
        log_queue.put(["DEBUG", "df evaluated: %s"%(df["nsDfId"]) ])
        if (df["nsDfId"] == composite_df):
            for il in df["nsInstantiationLevel"]:
                if (il["nsLevelId"] == composite_il):
                    for nsmap in il["nsToLevelMapping"]:
                        # look for the one that coincides with the nested
                        for nsprof in df["nsProfile"]:
                            if nsprof["nsProfileId"] == nsmap["nsProfileId"]:
                                if (nsprof["nsInstantiationLevelId"] == nested_il):
                                    return True
    return False

def check_new_df_compatibilities_scaling(body, composite_ns_info):
   """
   This function checks the current state of the NS and the desired state after the scaling operation, so 
   it provides the new instantiation levels for each of the involved nested, classifying the information between
   into local or federated nested. It also checks that in the case of existing a reference, it checks that the target_il
   is not disturbing it instantiation level
   Parameters
   ----------
   body: struct
       Body of the request to extract the target il to compare with current state 
   composite_ns_info: list
       Each element of this list is a dict containing the info regarding the different instantiation info parameters of a nested
   Returns
   -------
   local_il_changes_list: list
       This list contains a dict for each local nested to be modified. This dict contains current_df, current_il and target_il, doamin, nested_instance_id
   federation_il_changes_list: list
       This list contains a dict for each federated nested to be modified. This dict contains current_df, current_il and target_il, domain, nested_instance_id
   reference_il_list: list
       This list contains a dict with the reference_df, the reference_il of the NS used as a reference to complement the composite NS
   """

   local_services = []
   federated_services = []
   nested_ns_instance = {}
   reference_nsId = None
   reference_nsdId = None
   reference_il = None
   reference_df = None
   local_il_changes_list = []
   federation_il_changes_list = []
   reference_il_list = []
   if ('nestedNsId' in composite_ns_info):
       #it means it has a reference, we assume only one
       reference_nsId = composite_ns_info["nestedNsId"]
       reference_nsdId = ns_db.get_nsdId(reference_nsId)
       reference_il = ns_db.get_ns_il(reference_nsId)
       reference_df = ns_db.get_ns_flavour_id(reference_nsId)
       reference_il_list.append({reference_nsdId : [reference_df, reference_il, "local", reference_nsId]})
       # creating the variable to next check the pairs
       nested_ns_instance[reference_nsdId] = reference_nsId
   # if we do not enter, it means the composite has been instantiated from scratch
   composite_nsd_json = nsd_db.get_nsd_json(composite_ns_info['nsd_id'], None)
   composite_current_df = composite_ns_info['flavourId']
   composite_current_il = composite_ns_info['nsInstantiationLevelId']
   composite_target_il =  body.scale_ns_data.scale_ns_to_level_data.ns_instantiation_level
   composite_new_profiles = []
   # log_queue.put(["DEBUG", "composite_current_df: %s"%composite_current_df])
   # log_queue.put(["DEBUG", "composite_current_il: %s"%composite_current_il])
   # log_queue.put(["DEBUG", "composite_target_il: %s"%composite_target_il])

   for df in composite_nsd_json["nsd"]["nsDf"]:
       if (df["nsDfId"] == composite_current_df):
           for il in df["nsInstantiationLevel"]:
               # log_queue.put(["DEBUG", "comparando il: %s con target_il: %s"%(il["nsLevelId"],composite_target_il)])
               if (il["nsLevelId"] == composite_target_il):
                    # log_queue.put(["DEBUG", "composite_target_il_2: %s"%composite_target_il])
                    for nsmap in il["nsToLevelMapping"]:
                        composite_new_profiles.append(nsmap["nsProfileId"])
           # log_queue.put(["DEBUG", "Checking composite profiles: %s"%composite_new_profiles])
           for profile in df["nsProfile"]:
               if (profile["nsProfileId"] in composite_new_profiles):
                   if (profile["nsdId"] == reference_nsdId):
                       if (profile["nsInstantiationLevelId"] != reference_il and profile["nsDfId"] == reference_df):
                           # this scaling operation is changing the reference, it is not valid
                           return [None, None, None, None, None, None]
                   else:
                       nested_info = composite_ns_info["nested_service_info"]
                       for nested in range(0, len(nested_info)):
                           if (nested_info[nested]["nested_id"] == profile["nsdId"] and nested_info[nested]["nested_df"] == profile["nsDfId"]):
                               if (nested_info[nested]['domain'] == "local"):
                                   local_services.append({"nsd": nested_info[nested]["nested_id"], "domain": "local"})
                                   # now, we check if the current and the target_il are the same
                                   if (nested_info[nested]['nested_il'] != profile["nsInstantiationLevelId"]):
                                       local_il_changes_list.append({profile["nsdId"] : [nested_info[nested]["nested_df"], nested_info[nested]['nested_il'], profile["nsInstantiationLevelId"], nested_info[nested]['domain'], nested_info[nested]['nested_instance_id']]})
                               else:
                                   federated_services.append({"nsd": nested_info[nested]["nested_id"], "domain": nested_info[nested]['domain']})
                                   # now, we check if the current and the target_il are the same
                                   if (nested_info[nested]['nested_il'] != profile["nsInstantiationLevelId"]):
                                       federation_il_changes_list.append({profile["nsdId"] : [nested_info[nested]["nested_df"], nested_info[nested]['nested_il'], profile["nsInstantiationLevelId"], nested_info[nested]['domain'], nested_info[nested]['nested_instance_id']]})
                           # save the provider, just in case
   # the return variable is a list of dictionary that in local_il and federation_il have the following structure {nsId: [current_df, current_il, target_il, domain, nested_instance_id] }
   # for the reference_il_list, since it cannot change, it is: {nsId: [current_df, current_il, domain]}
   return [local_il_changes_list, federation_il_changes_list, reference_il_list, local_services, federated_services, nested_ns_instance]

def determine_new_il_composite_scaling(body, composite_ns_info, auto_instance_Id):
    # we are in the case of an autoscaling operation either local or federated, but which one? (we use its reference)
    # from the composite we need to 
    local_services = []
    federated_services = []
    nested_ns_instance = {}
    reference_nsId = None
    reference_nsdId = None
    reference_il = None
    reference_df = None
    local_il_changes_list = []
    federation_il_changes_list = []
    reference_il_list = []
    target_il = None
    ref_autoscaling = False
    if ('nestedNsId' in composite_ns_info):
        #it means it has a reference, we assume only one 
        if (composite_ns_info["nestedNsId"] == auto_instance_Id):
            ref_autoscaling = True
            log_queue.put(["DEBUG", "The reference is scaling"])
            # not needed, in the case of autoscaling the reference, we have entered after the 
            # reference is scaled, so its il is updated
            # reference_il = body.scale_ns_data.scale_ns_to_level_data.ns_instantiation_level
        # else:
            # reference_il = ns_db.get_ns_il(reference_nsId)            

        reference_nsId = composite_ns_info["nestedNsId"]
        reference_nsdId = ns_db.get_nsdId(reference_nsId)
        reference_il = ns_db.get_ns_il(reference_nsId)            
        reference_df = ns_db.get_ns_flavour_id(reference_nsId)
        reference_il_list.append({reference_nsdId : [reference_df, reference_il, "local", reference_nsId]})
        # creating the variable to next check the pairs
        nested_ns_instance[reference_nsdId] = reference_nsId

    composite_nsd_json = nsd_db.get_nsd_json(composite_ns_info['nsd_id'], None)
    composite_current_df = composite_ns_info['flavourId']
    composite_current_il = composite_ns_info['nsInstantiationLevelId']
    nested_info={}

    if (ref_autoscaling == True):
        # here I create a nested_info_like variable but with the characteristics of the reference
        nested_info["nested_id"] = reference_nsdId
        nested_info["nested_df"] = reference_df
        nested_info["nested_il"] = reference_il
        nested_info["domain"] = "local" # for the moment, references are local
        nested_info["nested_instance_id"] = composite_ns_info["nestedNsId"]
    else:
        for nested in composite_ns_info["nested_service_info"]:
            if nested["nested_instance_id"] == auto_instance_Id:
                nested_info = nested
                log_queue.put(["DEBUG", "Autoscaling the following NESTED: %s"%(dumps(nested_info))])

    if (nested_info):
        # auto-scaling comes from a nested within a composite, not a reference
        nested_id = nested_info["nested_id"]
        nested_df = nested_info["nested_df"]
        nested_domain = nested_info["domain"]
        current_nested_il = nested_info["nested_il"]
        target_nested_il = body.scale_ns_data.scale_ns_to_level_data.ns_instantiation_level
        for df in composite_nsd_json["nsd"]["nsDf"]:
            if (df["nsDfId"] == composite_current_df):
                for profile in df["nsProfile"]:
                    if ((profile["nsdId"] == nested_id) and (profile["nsDfId"] == nested_df) and (profile["nsInstantiationLevelId"] == target_nested_il)):
                        target_nested_profile = profile["nsProfileId"]
                        log_queue.put(["DEBUG", "The matching is with nsdId: %s"% profile["nsdId"]])
                        if ( (ref_autoscaling == False) or (ref_autoscaling == True and nested_id != reference_nsdId) ):
                        #if (nested_domain == 'local' or (ref_autoscaling == True and profile["nsdId"] !=reference_nsdId) ):
                            if (nested_domain == 'local'):
                                local_il_changes_list.append({nested_id : [nested_df, current_nested_il, target_nested_il, nested_domain, nested_info['nested_instance_id']]})
                        #if (nested_domain != 'local' or (ref_autoscaling == True and profile["nsdId"] !=reference_nsdId) ):
                            else:
                                federation_il_changes_list.append({nested_id : [nested_df, current_nested_il, target_nested_il, nested_domain, nested_info ['nested_instance_id']]})
                        log_queue.put(["DEBUG", "The target nested profile is: %s"%target_nested_profile])
                        break
                break
        # now construct the dict possibleLevelId -> profiles
        nsLevel_to_profile = {}
        for df in composite_nsd_json["nsd"]["nsDf"]:
            if (df["nsDfId"] == composite_current_df):
                for levelId in df["nsInstantiationLevel"]:
                    if levelId["nsLevelId"] not in nsLevel_to_profile:
                        nsLevel_to_profile[levelId["nsLevelId"]] = []
                        found = 0
                    for profile in levelId["nsToLevelMapping"]:
                        nsLevel_to_profile[levelId["nsLevelId"]].append(profile["nsProfileId"])
                        if (profile["nsProfileId"] == target_nested_profile):
                            found = 1
                    if (found == 0):
                        del nsLevel_to_profile[levelId["nsLevelId"]]
        log_queue.put(["DEBUG", "los profiles a investigar son: %s"%dumps(nsLevel_to_profile)])
        if not nsLevel_to_profile:
            # if there are no keys, something wrong happens, not compatible -> however you need to erase composite
            return [None, None, None, None, None, None, None]
        nsLevel_rank={}
        log_queue.put(["DEBUG", "El nested_id: %s, nested_df: %s, target_nested_il: %s"%(nested_id, nested_df, target_nested_il)])
        for df in composite_nsd_json["nsd"]["nsDf"]:
            if (df["nsDfId"] == composite_current_df):
               for level in nsLevel_to_profile.keys():
                   log_queue.put(["DEBUG", "Considered Profile Level: %s"%level])
                   if level not in nsLevel_rank:
                       nsLevel_rank[level] = 0
                   for profile in nsLevel_to_profile[level]:
                     log_queue.put(["DEBUG", "el profile considerado es: %s"% profile])
                     for profile_d in df["nsProfile"]:
                         if (profile_d["nsProfileId"] == profile):
                            candidate_nsdId = profile_d["nsdId"]
                            candidate_df = profile_d["nsDfId"]
                            candidate_il = profile_d["nsInstantiationLevelId"]
                            log_queue.put(["DEBUG", "El nested_id: %s, nested_df: %s, target_nested_il: %s"%(candidate_nsdId, candidate_df, candidate_il)])
                            if ( (nested_id == candidate_nsdId) and ( nested_df == candidate_df) and (target_nested_il == candidate_il) ):
                                # this is the case to check with the one which is auto-scaling
                                log_queue.put(["DEBUG", "Summing ONE AUTOSCALING to level: %s and candidate_il: %s"%(level, candidate_il)])
                                nsLevel_rank[level] = nsLevel_rank[level] + 1
                                if (ref_autoscaling == False):
                                    if (nested_domain == "local"):
                                        if ( ({"nsd": nested_id, "domain": nested_domain}) not in local_services):
                                            local_services.append({"nsd": nested_id, "domain": nested_domain})
                                    else:
                                        if ( ({"nsd": nested_id, "domain": nested_domain}) not in federated_services):
                                            federated_services.append({"nsd": nested_id, "domain": nested_domain})
                            else:
                                for nested_elem in composite_ns_info["nested_service_info"]:
                                    if ( (nested_elem["nested_id"] == candidate_nsdId) and (nested_elem["nested_df"] == candidate_df) \
                                         and (nested_elem["nested_il"] == candidate_il) ):
                                       # this is the case, we compare with the rest of nested in the service 
                                       log_queue.put(["DEBUG", "Summing ONE to level: %s and candidate_il: %s"%(level, candidate_il)])
                                       nsLevel_rank[level] =  nsLevel_rank[level] + 1
                                       # break -> otherwise I cannot populate the variables
                                    # I take profit of this loop to populate local_services and federated_services variables
                                    if ( (ref_autoscaling == False) or (ref_autoscaling == True and nested_elem["nested_id"] != reference_nsdId) ):
                                        if (nested_elem["domain"] == "local"):
                                            if ( ({"nsd": nested_elem["nested_id"], "domain": nested_elem["domain"]}) not in local_services):
                                                local_services.append({"nsd": nested_elem["nested_id"], "domain": nested_elem["domain"]})
                                        else:
                                            if ( ({"nsd": nested_elem["nested_id"], "domain": nested_elem["domain"]}) not in federated_services):
                                                federated_services.append({"nsd": nested_elem["nested_id"], "domain": nested_elem["domain"]}) 
                                # in the case not autoscaling the reference:
                                if (reference_il_list):
                                    if ( (reference_nsdId == candidate_nsdId) and ( reference_df == candidate_df) and ( reference_il == candidate_il) ):
                                        nsLevel_rank[level] = nsLevel_rank[level] + 1
        max_il = -1
        target_il = None
        for level in nsLevel_rank.keys():
           log_queue.put(["DEBUG", "The IL for the COMPOSITE is: %s and its rank is: %s"%(level, nsLevel_rank[level])]) 
           if (nsLevel_rank[level] > max_il):
               max_il = nsLevel_rank[level]
               target_il = level
        if (max_il == 0):
            #it means it is not compatible or it is not a good profile so we must discard it
            return [None, None, None, None, None, None, None]
    else:
        #there is no nested variable, the reference of the auto-scaling service is wrong
        return [None, None, None, None, None, None, None]
    log_queue.put(["DEBUG", "The selecte IL for the COMPOSITE is: %s and its rank is: %s"%(target_il, max_il)]) 
    return [target_il, local_il_changes_list, federation_il_changes_list, reference_il_list, local_services, federated_services, nested_ns_instance]

# local_services.append({"nsd": nested_info[nested]["nested_id"], "domain": "local"})
# federated_services.append({"nsd": nested_info[nested]["nested_id"], "domain": nested_info[nested]['domain']})

def define_new_body_for_composite(nsId, nsdId, body):
    """
    This function creates a new body struct to instantiate the corresponding nested 
    either at consumer or at provider domain
    Parameters
    ----------
    nsId: string
        Identifier of the service
    body: struct
        Object having the deployment flavour and the instantiation level.
    nsdId: string
        Identifier of the nested service to be instantiated, only available when 
    Returns
    -------
    body_tmp: struct
        Object with the appropriate df and il according to the request
    """
    body_tmp = copy.deepcopy(body)
    # get the nsdId that corresponds to nsId
    nsdcId = ns_db.get_nsdId(nsId)
    nsd_json = nsd_db.get_nsd_json(nsdcId, None)
    if "nestedNsdId" not in nsd_json["nsd"].keys():
        # we are delegating a single nested service, so the body is already the passed one
        return body
    flavourId = body_tmp.flavour_id
    nsLevelId = body_tmp.ns_instantiation_level_id
    for df in nsd_json["nsd"]["nsDf"]:
        if (df["nsDfId"] == flavourId):
            for il in df["nsInstantiationLevel"]:
                if (il["nsLevelId"] == nsLevelId):
                    #here we have to distinguish between composite NSD and single NSD
                    for nsProfile in il["nsToLevelMapping"]:
                        nsp = nsProfile["nsProfileId"]
                        for nsprof in df["nsProfile"]:
                            if ( (nsprof["nsProfileId"] == nsp) and (nsprof["nsdId"] == nsdId) ):
                                body_tmp.flavour_id = nsprof["nsDfId"]
                                body_tmp.ns_instantiation_level_id = nsprof["nsInstantiationLevelId"]
                                return body_tmp

def define_new_body_scaling_for_composite(nested, body):
    """
    This function creates a new body struct to scale the corresponding nested 
    either at consumer or at provider domain
    Parameters
    ----------
    nested: dict
        This dict contains (between other elements) the target_il for the corresponding nested
    body: struct
        Object having the target il for the composite NS.
    Returns
    -------
    body_tmp: struct
        Object with the appropriate scaling target il according to the initial request
    """
    body_tmp = copy.deepcopy(body)
    target_il = nested[next(iter(nested))][2]
    body_tmp.scale_ns_data.scale_ns_to_level_data.ns_instantiation_level = target_il
    return body_tmp

def exists_nsd(nsdId):
    """
    Function to check if an NSD with identifier "nsdId" exists.
    Parameters
    ----------
    nsdId: string
        Identifier of the Network Service Descriptor
    Returns
    -------
    boolean
        returns True if a NSD with Id "nsdId" exists in the Service Catalog. Returns False otherwise.
    """
    return nsd_db.exists_nsd(nsdId)

def create_operation_identifier(nsId, operation_type):
    """
    Creates an operation identifierFunction description
    Parameters
    ----------
    param1: type
        param1 description
    Returns
    -------
    name: type
        return description
    """
    operationId = str(uuid4())
    operation_db.create_operation_record(operationId, nsId, operation_type)
    return operationId


def create_operation_identifier_provider(nsd, name, description):
    path = "/5gt/so/v1/ns"
    key = next(iter(nsd["domain"]))
    data = {"nsDescription": "Federating service: " + description,
            "nsName": "Consumer " + key + ": " + name, #check this name, can be an arbitrary one? !!!
            "nsdId": nsd["nsd"]
            }
    # we open here the connection and we will close when the process is finished
    # port, headers and timeout defined previously
    conn = HTTPConnection(nsd["domain"][key], port, timeout=timeout)
    conn.request("POST", path, dumps(data), headers)
    conn.sock.settimeout(timeout)
    rsp = conn.getresponse()
    data = rsp.read().decode()
    data = loads(data)
    nsId = data["nsId"]
    return [nsId, conn]

def instantiate_ns_provider (nsId_n, conn, body, additionalParams=None):
    # instantiate the service
    path = "/5gt/so/v1/ns/" + nsId_n + "/instantiate"
    if additionalParams:
        data = {"flavourId": body.flavour_id, 
                "nsInstantiationLevelId": body.ns_instantiation_level_id,
                "additionalParamForNs" : additionalParams
               }
    else:
        data = {"flavourId": body.flavour_id,
                "nsInstantiationLevelId": body.ns_instantiation_level_id
               }
    conn.request("PUT", path, dumps(data), headers)
    conn.sock.settimeout(timeout)
    rsp = conn.getresponse()
    data = rsp.read().decode()
    data = loads(data)
    operationId = data["operationId"]
    return operationId

def scale_ns_provider (nsId_n, body, domain, additionalParams=None):
    #scale the service
    path = "/5gt/so/v1/ns/" + nsId_n + "/scale"
    target_il = None
    operationId = ""
    conn = ""
    key = next(iter(domain))
    if (body.scale_type == "SCALE_NS"):
        target_il = body.scale_ns_data.scale_ns_to_level_data.ns_instantiation_level
    if not target_il == None:
        data = {  "scaleType": "SCALE_NS",
                  "scaleNsData": {
                      "scaleNsToLevelData": {
                          "nsInstantiationLevel": target_il
                      }
                  }
                }
        conn = HTTPConnection(domain[key], port, timeout=timeout)
        conn.request("PUT", path, dumps(data), headers)
        conn.sock.settimeout(timeout)
        rsp = conn.getresponse()
        data = rsp.read().decode("utf-8")
        data = loads(data)
        log_queue.put(["DEBUG", "Response from 5Gr-SO on Scale request are:"])
        log_queue.put(["DEBUG", dumps(data, indent=4)])
        operationId = data["operationId"]
    return [operationId, conn, target_il]


def scale_ns_consumer(nsId, body, domain, operationId):
    #in case of autoscaling of a federated nested service, trigger the update at the consumer
    path = "/5gt/so/v1/ns/" + nsId + "/scale"
    target_il = body.scale_ns_data.scale_ns_to_level_data.ns_instantiation_level
    scale_request ={
        "scaleType": "SCALE_NS",
        "scaleNsData": {
          "scaleNsToLevelData": {
             "nsInstantiationLevel": target_il
          },
          "additionalParamForNs": {
           "operationId": operationId
          }
        },
        "scaleTime": "0"
    }
    body_def=dumps(scale_request)
    try:
        conn = HTTPConnection(domain, port, timeout=timeout)
        #conn.request("PUT", path, body, headers)
        conn.request("PUT", path, body_def, headers)
        rsp = conn.getresponse()
        resources = rsp.read()
        resp_scale = resources.decode("utf-8")
        resp_scale = loads(resp_scale)
        log_queue.put(["DEBUG", "Response from SO on Scale request are:"])
        log_queue.put(["DEBUG", dumps(resp_scale, indent=4)])
        conn.close()
    except ConnectionRefusedError:
        # the SO on Scale request returned wrong response
        log_queue.put(["ERROR", "SO on Scale request returned wrong response"])


def terminate_ns_provider(nsId, domain):
    # terminate the service
    path = "/5gt/so/v1/ns/" + nsId + "/terminate"
    key = next(iter(domain))
    conn = HTTPConnection(domain[key], port, timeout=timeout)
    conn.request("PUT", path, None, headers)
    conn.sock.settimeout(timeout)
    rsp = conn.getresponse()
    data = rsp.read().decode()
    data = loads(data)
    operationId = data["operationId"]
    return [operationId, conn]

def get_operation_status_provider(operationId, conn=None, domain=None):
    path = "/5gt/so/v1/operation/" + operationId
    if (conn== None):
        # we are in the case of provider auto-scaling case 
        connect = HTTPConnection(domain, port, timeout=timeout)
    else:
        connect = conn
    connect.request("GET", path, None, headers)
    connect.sock.settimeout(timeout)
    rsp = connect.getresponse()
    data = rsp.read().decode()
    log_queue.put(["INFO", "get_operation_status_provider data: %s" % (data)])
    data = loads(data)
    if (conn== None):
        connect.close()
    return data['status']

def get_sap_info_provider(nsId_n, conn=None, domain=None): 
    path = "/5gt/so/v1/ns/" + nsId_n
    if (conn== None):
        # we are in the case of provider auto-scaling case 
        connect = HTTPConnection(domain, port, timeout=timeout)
    else:
        connect = conn
    connect.request("GET", path, None, headers)
    connect.sock.settimeout(timeout)
    rsp = connect.getresponse()
    data = rsp.read().decode()
    data = loads(data)
    sapInfo = data["queryNsResult"][0]["sapInfo"]
    connect.close()
    return sapInfo


def generate_nested_sap_info(nsId, nsd_name):
    """
    Returns the information of the Network Service Instance identified by nsId.
    Parameters
    ----------
    nsId: string
        Identifier of the NS instance to get information.
    nsd_name: string
        Identifier of the NS descriptor to get information
    Returns
    -------
    dict
        Formatted information of the Network Service Instance info.
    """

    nsd_json = nsd_db.get_nsd_json(nsd_name)
    if "sapd" in nsd_json["nsd"]:
        total_sap_info = get_ns_sap_info(nsId,nsd_json["nsd"]["sapd"])
        if total_sap_info is not None:
            return total_sap_info
        else: 
            return None

def transform_nested_sap_info(nested_sap_info): 
    """
    This method gets the nested sap info and returns a dict as if it was the sapInfo from a single NS.
    Parameters
    ----------
    nested_sap_info: dict
        Sap_info registry from a nested NS in a composite process
    Returns
    -------
    dict
        Formatted information of the sapInfo element as it was a single NS.
    """
    # Example of a sap from a single NS:"sapInfo" : { "mgt_vepc_sap" : [ { "HSS_VNF" : "10.20.30.6" }, { "PGW_VNF" : "10.20.30.17" }, { "SECGW_VNF" : "10.20.30.7" },   
    # { "MME_VNF" : "10.20.30.16" }, { "SGW_VNF" : # "10.20.30.21" }, { "SERVER_VNF" : "10.20.30.20" } ] }
    # Example of a sap from a nested NS: [{'sapInstanceId': '0', 'description': 'Mgmt SAP', 'sapdId': 'mgt_vepc_sap', 'address': 'test for future', 'sapName': 'mgt_vepc_sap',
    # 'userAccessInfo': [{'vnfdId': 'MME_VNF', 'sapdId': 'mgt_vepc_sap', 'address': '10.20.30.16'}, {'vnfdId': 'PGW_VNF', 'sapdId': 'mgt_vepc_sap', 'address': '10.20.30.17'},
    # {'vnfdId': 'SERVER_VNF', 'sapdId': 'mgt_vepc_sap', 'address': '10.20.30.20'}, {'vnfdId': 'HSS_VNF', 'sapdId': 'mgt_vepc_sap', 'address': '10.20.30.6'}, {'vnfdId':
    # 'SGW_VNF', 'sapdId': 'mgt_vepc_sap', 'address': '10.20.30.21'}, {'vnfdId': 'SECGW_VNF', 'sapdId': 'mgt_vepc_sap', 'address': '10.20.30.7'}]}]
    sapInfo = {}
    for sapdescription in nested_sap_info:
        if sapdescription["sapdId"] not in sapInfo:
            sapInfo[sapdescription["sapdId"]] = []
            for info in sapdescription["userAccessInfo"]:
                if (info["sapdId"] == sapdescription["sapdId"]):
                    sapInfo[sapdescription["sapdId"]].append({info["vnfdId"] : info["address"]})
    return sapInfo

def instantiate_ns_process(nsId, body, requester):
    """
    The process to instantiate the Network Service associated to the instance identified by "nsId".
    Parameters
    ----------
    nsId: string
        Identifier of the Network Service Instance.
    body: request body
    requester: string
        IP address of the requester, needed for federation purposes
    Returns
    -------
    None
    """
    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp decomposing NS" % (nsId)])
    # get the nsdId that corresponds to nsId
    nsdId = ns_db.get_nsdId(nsId)
    # first get the ns and vnfs descriptors
    nsd_json = nsd_db.get_nsd_json(nsdId, None)
    local_services = []
    federated_services = []
    nested_services = []
    if "nestedNsdId" in nsd_json["nsd"].keys():
        # I have a list of services within the nsd_json: composite
        # currently, not valid the request of a composite in a federated domain
        for nested in nsd_json["nsd"]["nestedNsdId"]:
            nested_services.append(nested)
    else: 
        #two options here:
        # 1) this is a single one that is delegated to other domain, consumer send to provider
        # 2) this is a single nested that is a reques from a consumer domain, provider receiver a consumer request
        nested_services.append(nsd_json["nsd"]["nsdIdentifier"])
    for ns in nested_services:
        domain = nsd_db.get_nsd_domain(ns, None)
        if (domain == "local"):
            local_services.append({"nsd":ns, "domain": domain})
        else:
            federated_services.append({"nsd":ns, "domain": domain})
    log_queue.put(["INFO", "SOEp instantiate_ns_process with nsId %s, body %s" % (nsId, body)])
    index = 0

    # in case we have a nestedId, we need to check its deployment flavour to check if it compatible with the one of the composite
    nested_instance = {}
    if body.nested_ns_instance_id:
        # it has been previously checked if exists and it is in INSTATIATED state and that it can be shared
        nested_record = ns_db.get_ns_record(body.nested_ns_instance_id[0])
        if not (check_df_compatibilities(nested_record, nsd_json, body)):
            return 404
        else:
            # link to possible nested instances we need to update the original registry
            ns_db.set_ns_nested_services_ids(nsId, body.nested_ns_instance_id[0])
            # we need to remove this nested service from the local or federated list
            # for the moment, not contemplated compsition with a nested federated/delegated one
            # then the nested will be in local
            for nsd in local_services:
                if (nsd["nsd"] == nested_record["nsd_id"]):
                    nested_instance[nsd["nsd"]] = body.nested_ns_instance_id[0]
                    local_services.remove(nsd)
    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp finished decomposing NS and checking references" % (nsId)])
    if "nestedNsdId" in nsd_json["nsd"].keys():
        [network_mapping, renaming_networks] = crooe.mapping_composite_networks_to_nested_networks(nsId, nsd_json, body, nested_instance) 
    else:
        # it is a single delegated NS
        network_mapping = {}
        renaming_networks = {}

    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp CROOE finished checking interconnection nested NS and checking references"% (nsId)])
    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp instantiating local nested NSs"% (nsId)])
    for nsd in local_services:
        #log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp instantiating local nested NSs %s"%(nsId,index)])
        if (requester != "local"):
            # in that case, we only iterate once, this is the part of the federated service in the provider domain
            if (body.additional_param_for_ns):
                networkInfo = crooe.get_federated_network_info_request(body.additional_param_for_ns["nsId"], 
                              nsd['nsd'], requester, ewbi_port, ewbi_path)
                log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp received networkInfo from local CROOE for nested with index %s"% (nsId,index)])
                log_queue.put(["INFO", "SOEp getting information of the consumer domain from the EWBI: %s" %networkInfo])
                # we need to save the network_mapping for a next iteration with the ewbi after the federated service has been instantiated
                log_queue.put(["INFO", "SOEp passing info to instantiate_ns_process"])
                log_queue.put(["INFO", dumps({nsd["nsd"]:[loads(body.additional_param_for_ns["network_mapping"]), networkInfo]},indent=4)])
                soe.instantiate_ns_process(nsId, body, {nsd["nsd"]:[loads(body.additional_param_for_ns["network_mapping"]), networkInfo]})
            else:
                # single delegated NS
                soe.instantiate_ns_process(nsId, body)
        else: 
            # new_body = soe.define_new_body_for_composite(nsId, nsd["nsd"], body) #be careful with the pointer
            log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp instantiating local nested NSs %s"%(nsId,index)])
            nested_body = define_new_body_for_composite(nsId, nsd["nsd"], body) #be careful with the pointer
            log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp prepared nested body for local nested NSs %s"%(nsId,index)])
            nsId_nested = nsId + '_' + nsd["nsd"]
            # we have to create the info entry before to have a place where to store the sap_info
            info = { "nested_instance_id": nsId_nested,
                     "domain": "local",
                     "instantiation_order": index,
                     "nested_id": nsd["nsd"],
                     "nested_df": nested_body.flavour_id,
                     "nested_il": nested_body.ns_instantiation_level_id,
                   }   
            ns_db.update_nested_service_info(nsId, info, "push") 
            soe.instantiate_ns_process(nsId, nested_body, {nsd["nsd"]:[network_mapping['nestedVirtualLinkConnectivity'][nsd["nsd"]]]})
            log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp finished instantiating local nested NSs %s"%(nsId,index)])
            # the service is instantiated
            sapInfo = generate_nested_sap_info(nsId, nsd["nsd"])
            if (sapInfo == None):
                # there has been a problem with the nested service and the process failed, we have 
                # to abort the instantiation
                operationId = operation_db.get_operationId(nsId, "INSTANTIATION")
                operation_db.set_operation_status(operationId, "FAILED")
                # set ns status as FAILED
                ns_db.set_ns_status(nsId, "FAILED")
                # remove the reference previously set
                if body.nested_ns_instance_id:
                    ns_db.delete_ns_shared_services_ids(body.nested_ns_instance_id[0], nsId)
                return #stop instantiating: to do: to manage in case of failure

            info = { "status": "INSTANTIATED", #as it is coming back after instantiating
                     "sapInfo": sapInfo
                   }
            # Scaling composite NFV-NS
            # adding monitoring job and alert information, following same approach as with saps
            nested_monitoring_jobs = ns_db.get_monitoring_info(nsId)
            if (len(nested_monitoring_jobs)>0):
                # it means that there is monitoring jobs
                info["nested_monitoring_jobs"] = nested_monitoring_jobs
                nested_alert_info = ns_db.get_alerts_info(nsId)
                if (len(nested_alert_info)>0):
                    info["nested_alert_jobs"] = nested_alert_info
                    # now, we can set to void the alert entry
                    ns_db.set_alert_info(nsId,{})
                # now, we can set to void the monitoring entry
                ns_db.set_monitoring_info(nsId,[])
            log_queue.put(["INFO", "Nested NS service instantiated with info: "])
            log_queue.put(["INFO", dumps(info,indent=4)])
            ns_db.update_nested_service_info(nsId, info, "set", nsId_nested)
            index = index + 1
            # clean the sap_info of the composite service, 
            ns_db.save_sap_info(nsId, "")
            log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp finished updating DBs local nested NSs %s"%(nsId,index)])
            notification_db.create_notification_record({
                "nsId": nsId_nested,
                "type": "fa-send-o",
                "text": nsId_nested + " INSTANTIATED LOCALLY",
                "time": datetime.now().strftime("%d/%m/%Y %H:%M:%S.%f")
              })

        
    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp finished instantiating local nested NSs" % nsId])
    if (requester != "local"):            
    # now I can return since the rest of interaction with the consumer domain will be done through the EWBI interface
        log_queue.put(["INFO", "SOEp instantiate_ns_process returning because the rest of the interactions"])
        log_queue.put(["INFO", "of the federated service are done through the EWBI interface directed by consumer"])
        return

    # federated_instance_info = []
    
    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp instantiating federated nested NSs" % (nsId)])
    for nsd in federated_services:
        log_queue.put(["INFO", "*****Time measure for nsId %s: SOEp SOEp instantiating federated nested NSs %s"% (nsId,index)])
        # steps:
        # 1) ask for an ns identifier to the remote domain
        name = ns_db.get_ns_name(nsId)
        description = ns_db.get_ns_description(nsId)
        [nsId_n, conn] = create_operation_identifier_provider(nsd, name, description)
        # 2) ask for the service with the provided id in step 1)
        nested_body = define_new_body_for_composite(nsId, nsd["nsd"], body)
        log_queue.put(["INFO", "SOEp generating federated nested_body: %s" % (nested_body)])
        log_queue.put(["INFO", "*****Time measure for nsId %s: SOEp SOEp generating request for federated domain for nested %s"% (nsId,index)])
        if (len(nested_services) == 1 and len(federated_services) == 1):
            # it means it is a single delegated NS
            operationId = instantiate_ns_provider (nsId_n, conn, nested_body)
            log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp received operationId of federated nested %s"% (nsId,index)])
        else:
            federated_mapping = {"nsId": network_mapping["nsId"], "network_mapping": dumps(network_mapping["nestedVirtualLinkConnectivity"][nsd["nsd"]])}
            operationId = instantiate_ns_provider (nsId_n, conn, nested_body, federated_mapping)
            log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp received operationId of federated nested %s"%(nsId,index)])
        status = "INSTANTIATING"
        # 3) enter in a loop to wait until service is instantiated, checking with the operationid, that the operation 
        # 4) update the register of nested services instantiated
        while (status != "SUCCESSFULLY_DONE"):		
            status = get_operation_status_provider(operationId, conn)
            if (status == 'FAILED'):
                operationIdglobal = operation_db.get_operationId(nsId, "INSTANTIATION")
                operation_db.set_operation_status(operationIdglobal, "FAILED")
                # set ns status as FAILED
                ns_db.set_ns_status(nsId, "FAILED")
                # remove the reference previously set
                if body.nested_ns_instance_id:
                    ns_db.delete_ns_shared_services_ids(body.nested_ns_instance_id[0], nsId)
                return #stop instantiating: to do: to manage in case of failure
            time.sleep(10)      
        log_queue.put(["DEBUG", "SOEp COMPLETE operationId: %s" % (operationId)])
        # 5) ask the federated domain about its instantiation in case it is not a single delegated NS
        federated_info = {}
        if not (len(nested_services) == 1 and len(federated_services) == 1):
            # it means it is not a single delegated NS
            key = next(iter(nsd["domain"]))
            log_queue.put(["INFO", "SOEp asking instantiation parameters of %s to %s"%(nsd["nsd"],nsd["domain"][key])]) 
            log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp asking instantiation result to federated CROOE of federated nested NSs %s"% (nsId,index)])
            federated_info = crooe.get_federated_network_instance_info_request(nsId_n, nsd["nsd"], nsd["domain"][key], ewbi_port, ewbi_path)
            log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp receiving instantiation result to federated CROOE of federated nested NSs %s"% (nsId,index)])
            log_queue.put(["INFO", "SOEp obtained federatedInfo through EWBI: %s"%federated_info])
        # finally this information is relevant for subsequent instantiations
        # 6) update the local registry about information of the federated nested service
        sap_info =  get_sap_info_provider(nsId_n, conn) # we close here the connection
        info = { "nested_instance_id": nsId_n,
                 "domain": nsd["domain"],
                 "instantiation_order": index,
                 "nested_id": nsd["nsd"],
                 "nested_df": nested_body.flavour_id,
                 "nested_il": nested_body.ns_instantiation_level_id,
                 "status": "INSTANTIATED",
                 "federatedInstanceInfo": federated_info,
                 "sapInfo": sap_info
               }
        # Composite NFV-NS scaling: for the nested NSs in the provider domain, we do not get the monitoring information
        ns_db.update_nested_service_info(nsId, info, "push")
        index = index + 1
        log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp  finished updating DBs federated nested NSs %s"%(nsId, index)])
        notification_db.create_notification_record({
            "nsId": nsId_n,
            "type": "fa-send-o",
            "text": nsId_n + " INSTANTIATED in FEDERATED domain" + nsd["domain"],
            "time": datetime.now().strftime("%d/%m/%Y %H:%M:%S.%f")
          })

    log_queue.put(["DEBUG", "*****Time measure for nsId: %s: SOEp SOEp finishing instantiating federated nested NSs" % (nsId)])
    # interconnecting the different nested between them
    log_queue.put(["DEBUG", "*****Time measure for nsId: %s: SOEp SOEp start interconnecting nested NSs" % (nsId)])
    if (len(nested_services) > 1):
        # in case of one, it means that it is a single delegation and you do not need to connect it
        # at least one of it will be local, so first we connect the local nested services and then we connect them with the federated
        if (len(local_services) > 1 or (len(local_services) == 1 and body.nested_ns_instance_id)):
            log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp-CROOE interconnecting local nested NSs" % (nsId)])
            crooe.connecting_nested_local_services(nsId, nsd_json, network_mapping, local_services, nested_instance, renaming_networks)
            log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp-CROOE finished interconnecting local nested NSs" % (nsId)])
        # once local are connected, connect federated services with the local domain
        if (len(federated_services) > 0):
            log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp-CROOE interconnecting federated nested NSs" % (nsId)])
            crooe.connecting_nested_federated_local_services(nsId, nsd_json, network_mapping, local_services, federated_services, nested_instance, renaming_networks)
            log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp-CROOE finished interconnecting federated nested NSs" % (nsId)])

    # after instantiating all the nested services, update info of the instantiation    
    operationId = operation_db.get_operationId(nsId, "INSTANTIATION")
    ns_record = ns_db.get_ns_record(nsId)
    status = "INSTANTIATED"
    for elem in ns_record["nested_service_info"]:
        log_queue.put(["DEBUG", "SOEp finishing... nested_service_info: %s" % (elem)])
        if not elem["status"] == "INSTANTIATED":
            status = "INSTANTIATING"
            break
    if (status == "INSTANTIATED"):
        log_queue.put(["DEBUG", "NS Instantiation finished correctly"])
        operation_db.set_operation_status(operationId, "SUCCESSFULLY_DONE")
        # set ns status as INSTANTIATED
        ns_db.set_ns_status(nsId, "INSTANTIATED")
 
    # once the service is correctly instantiated, link to possible nested instances
    if (body.nested_ns_instance_id):
        ns_db.set_ns_shared_services_ids(body.nested_ns_instance_id[0], nsId)
    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp finished instantiation composite NS" %(nsId)])
    notification_db.create_notification_record({
        "nsId": nsId,
        "type": "fa-send-o",
        "text": nsId + " INSTANTIATED",
        "time": datetime.now().strftime("%d/%m/%Y %H:%M:%S.%f")
      })

def scale_federated_service(nsId, nested_info, nested_id_instance, body, domain):

    [operation_id, conn, target_il] = scale_ns_provider(nested_id_instance, body, domain)
    nested_info["status"] = "SCALING"
    ns_db.update_nested_service_info(nsId, nested_info, "set", nested_id_instance)
    if not target_il == None:
        # status = "INSTANTIATING"
        status = get_operation_status_provider(operation_id, conn)
        # 3) enter in a loop to wait until service is instantiated, checking with the operationid, that the operation 
        # 4) update the register of nested services instantiated
        while (status != "SUCCESSFULLY_DONE"):		
            #status = get_operation_status_provider(operation_id, conn)
            if (status == 'FAILED'):
                operationIdglobal = operation_db.get_operationId(nsId, "INSTANTIATION")
                operation_db.set_operation_status(operationIdglobal, "FAILED")
                # set ns status as FAILED
                ns_db.set_ns_status(nsId, "FAILED")
                return #stop scaling: to do: to manage in case of failure
            time.sleep(10)   
            status = get_operation_status_provider(operation_id, conn)
        log_queue.put(["INFO", "SOEp COMPLETE scaling operationId: %s" % (operation_id)])
        key = next(iter(domain))
        federated_info = crooe.get_federated_network_instance_info_request(nested_id_instance, nested_info["nested_id"], domain[key], ewbi_port, ewbi_path)
        sap_info =  get_sap_info_provider(nested_id_instance, conn) # we close here the connection
        #update the register in the nested
        nested_info["sap_info"] = sap_info
        nested_info["federatedInstanceInfo"] = federated_info
        nested_info["nested_il"] = target_il
        nested_info["status"] = "INSTANTIATED"
        ns_db.update_nested_service_info(nsId, nested_info, "set", nested_id_instance)
        return target_il

def scale_ns_process(nsId, body, composite_nsIds=None):
    """
    Performs the scaling of the service identified by "nsId" according to the info at body 
    Parameters
    ----------
    nsId: string
        Identifier of the Network Service Instance.
    body: request body including scaling operation
    Returns
    -------
    """
    # We treat here the following cases defined in scale_ns
    # 1.5) considering that this single NS it is being used by a composite
    # 2) scaling of a single delegated NS 
    #    2.5) autoscaling of a single delegated NS
    # 3) scaling of a composite NS 
    #    3.5) scaling of a composite with federated components 
    # 4) autoscaling of a nested NS local 
    #    4.5) autoscaling of nested NS federated -> need to drive connections

    # in the case we have composite_nsIds, we have to wait for the scaling of the nestedNs, 
    # prior to update the connections with the components associated compositeNs
    target_il = body.scale_ns_data.scale_ns_to_level_data.ns_instantiation_level
    # local_services, federated_services, nested_ns_instance are variables populated when needed
    local_services = []
    federated_services = []
    nested_ns_instance = {}
    local_il_nested = []
    federated_il_nested = []
    reference_il = []
    if (composite_nsIds):
        # Case 1.5) considering that this single NS it is being used by a composite
        # we consider that resulting dfs will be compatible, nevertheless, for the sake
        # of compatibility, we check after the scaling of the single NS
        status = ns_db.get_ns_status(nsId)
        # nested_ns_instance[ns_db.get_nsdId(nsId)] = nsId --> it is determined afterwards
        log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp checking the scaling of a reference to update associated composites: case 1.5)" % (nsId)])
        while (status != "INSTANTIATED"):
            status = ns_db.get_ns_status(nsId)
            log_queue.put(["DEBUG", "Scaling a reference"])
            if (status == "FAILED"):
                # we return without doing nothing
                return
            if (status == "INSTANTIATED"):
                break
            time.sleep(10)
        # now that, the reference has been scaled, we pass to the list of composites
        log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp reference scaling finished: case 1.5)" % (nsId)])
        log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp updating associated composite NSs: case 1.5)" % (nsId)])
        for composite_ns in range(0, len(composite_nsIds)):
            log_queue.put(["INFO", "*****Time measure for composite nsId: %s: SOEp SOEp updating composite NSs %s"%(composite_ns, composite_ns)])
            nsId_compo_tmp = composite_nsIds[composite_ns]
            log_queue.put(["DEBUG", "The composite NS to be updated after a reference is scaling: %s"%nsId_compo_tmp])
            ns_info = ns_db.get_ns_record(nsId_compo_tmp)
            ns_db.set_ns_status(nsId_compo_tmp, "SCALING")
            log_queue.put(["DEBUG", "Composite current_il: %s"%ns_db.get_ns_il(nsId_compo_tmp)])
            [target_il, local_il_nested, federated_il_nested, reference_il, local_services, federated_services, nested_ns_instance] = \
            determine_new_il_composite_scaling(body, ns_info, nsId)
            # log_queue.put(["DEBUG", "Composite target_il: %s"%target_il])
            # log_queue.put(["DEBUG", "local_il_nested: "])
            # log_queue.put(["DEBUG", dumps(local_il_nested)])
            # log_queue.put(["DEBUG", "federated_il_nested: "])
            # log_queue.put(["DEBUG", dumps(federated_il_nested)])
            # log_queue.put(["DEBUG", "reference_il:"])
            # log_queue.put(["DEBUG", dumps(reference_il)])
            # log_queue.put(["DEBUG", "local_services:"])
            # log_queue.put(["DEBUG", dumps(local_services)])
            # log_queue.put(["DEBUG", "federated_services:"])
            # log_queue.put(["DEBUG", dumps(federated_services)])
            # log_queue.put(["DEBUG", "nested_ns_instance:"])
            # log_queue.put(["DEBUG", dumps(nested_ns_instance)])
            # we have waited until the reference has been scaled, then the crooe has to update the connections for each composite and update the status
            # update connections with the help of crooe
            # first local nested connections
            nsdId_compo = ns_db.get_nsdId(nsId_compo_tmp)
            nsd_json_compo = nsd_db.get_nsd_json(nsdId_compo, None)
            log_queue.put(["INFO", "*****Time measure: SOEp SOEp determine new_il_composite_scaling composite NSs %s"%composite_ns])
            if ((len(local_il_nested) > 0 and len(local_services)>1) or (len(local_services) > 0 and len(reference_il) > 0)): 
                # the first part of the condition is not needed 
                # here we still consider that the reference is always a local service
                log_queue.put(["INFO", "*****Time measure for composite nsId: %s: SOEp SOEp-CROOE scaling updating local nested NSs interconnections WITH REFERENCE" %(composite_ns)])
                crooe.update_connecting_nested_local_services(nsId_compo_tmp, nsd_json_compo, local_services, nested_ns_instance)
                log_queue.put(["INFO", "*****Time measure for composite nsId: %s: SOEp SOEp-CROOE scaling finishing updating local nested NSs interconnections WITH REFERENCE" %(composite_ns)])
            if (len(federated_services)>0 and (len(federated_il_nested)>0 or len(local_il_nested)>0 or len(reference_il) > 0)):
                log_queue.put(["INFO", "*****Time measure for composite nsId: %s: SOEp SOEp-CROOE scaling updated federated nested NSs interconnections WITH REFERENCE" %(composite_ns)])
                crooe.update_connecting_nested_federated_local_services(nsId_compo_tmp, nsd_json_compo, nested_ns_instance)
                log_queue.put(["INFO", "*****Time measure for composite nsId: %s: SOEp SOEp-CROOE scaling finishing updated federated nested NSs interconnections WITH REFERENCE" %(composite_ns)])      

            # after updating the connections, update info of the instantiation at the composite level    
            status = "INSTANTIATED"
            for elem in ns_info["nested_service_info"]:
                 if not elem["status"] == "INSTANTIATED":
                     status = "INSTANTIATING"
                     break
            if (status == "INSTANTIATED"):
               log_queue.put(["DEBUG", "NS Scaling in the ASSOCIATED COMPOSITE finished correctly"])
               # set the new instantiation level
               ns_db.set_ns_il(nsId_compo_tmp, target_il)
               # set ns status as INSTANTIATED, although it is already
               ns_db.set_ns_status(nsId_compo_tmp, "INSTANTIATED")
        log_queue.put(["DEBUG", "Associated Composite NSs Scaling finished correctly"])
        operationId = operation_db.get_operationId(nsId, "INSTANTIATION")           
        operation_db.set_operation_status(operationId, "SUCCESSFULLY_DONE")
        log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp Associated Composite NSs scaling finished correctly" % (nsId)])
        return
    else:
        # no composite_nsIds to be udpated
        nsdId = ns_db.get_nsdId(nsId)
        if (nsdId == None):
            # case 2.5) autoscaling of a delegated NS 
            # case 4) autoscaling of a nested NS local
            # it means that we are autoscaling a nested NS, we need to call soe for scaling
            # we have modified the SLA module to make the scaling call using the nested_instance_id
            #     case 4.5) autoscaling of a nested NS federated 
            #     in theory, we only need to update connections -> done by consumer domain
            # assuming compatibility in the dfs
            nsId_tmp = nsId.split('_') 
            if (len(nsId_tmp) == 1):
                log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp handling autoscaling delegated" % (nsId)])
                # autoscaling of a delegated, the consumer domain needs to update the info
                # case 2.5) autoscaling of a delegated NS 
                nsId_consumer = ns_db.get_consumer_owner_delegated(nsId)
                delegated_nested_info =ns_db.get_particular_nested_service_info(nsId_consumer, nsId) 
                delegated_nested_info["status"] = "SCALING"
                ns_db.update_nested_service_info(nsId_consumer, delegated_nested_info, "set", nsId)
                domain = delegated_nested_info["domain"]
                opId = None
                for key in body.scale_ns_data.additional_param_for_ns.keys(): 
                    if (key == "operationId"):
                        opId = body.scale_ns_data.additional_param_for_ns[key]
                if (opId):
                    key = next(iter(domain))
                    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp waiting autoscaling delegated" % (nsId)])
                    status = get_operation_status_provider(opId, None, domain[key])
                    while (status != "SUCCESSFULLY_DONE"):
                        if (status == 'FAILED'):
                            operationIdglobal = operation_db.get_operationId(nsId_consumer, "INSTANTIATION")
                            operation_db.set_operation_status(operationIdglobal, "FAILED")
                            ns_db.set_ns_status(nsId_consumer, "FAILED")
                            return #stop scaling: to do: to manage in case of failure
                        time.sleep(10)
                        status = get_operation_status_provider(opId, None, domain[key])
                    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp autoscaling delegated finished scaling" % (nsId)])
                    log_queue.put(["INFO", "Provider domain finished scaling operationId: %s" % (opId)])
                    sap_info = get_sap_info_provider(nsId, None, domain)
                    delegated_nested_info["nested_il"] = body.scale_ns_data.scale_ns_to_level_data.ns_instantiation_level
                    delegated_nested_info["status"] = "INSTANTIATED"
                    ns_db.update_nested_service_info(nsId_consumer, delegated_nested_info, "set", nsId)  
                    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp autoscaling delegated updated databases" %(nsId)])
                    return                           
            else:
                # autoscaling of a nested NS, either local or federated   
                # case 4) and 4.5)     
                if ns_db.get_nsdId(nsId_tmp[0]):
                    # we are auto-scaling a local, because the entry exists in the db, we have to ask the soe to make the actual scaling
                    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp autoscaling nested NS local" % (nsId_tmp[0])])
                    log_queue.put(["DEBUG", "Autoscaling of a nested NS local"])
                    nsdId = ns_db.get_nsdId(nsId_tmp[0])
                    nsd_json = nsd_db.get_nsd_json(nsdId, None)
                    # we need to build the local_il_nested variables, .... to then udpate the connections
                    ns_info = ns_db.get_ns_record(nsId_tmp[0])
                    # target_il of the composite
                    log_queue.put(["DEBUG", "Composite current_il: %s"%ns_db.get_ns_il(nsId_tmp[0])])
                    [target_il, local_il_nested, federated_il_nested, reference_il, local_services, federated_services, nested_ns_instance] = \
                    determine_new_il_composite_scaling(body, ns_info, nsId)
                    # log_queue.put(["DEBUG", "Composite target_il: %s"%target_il])
                    # log_queue.put(["DEBUG", "local_il_nested: "])
                    # log_queue.put(["DEBUG", dumps(local_il_nested)])
                    # log_queue.put(["DEBUG", "federated_il_nested: "])
                    # log_queue.put(["DEBUG", dumps(federated_il_nested)])
                    # log_queue.put(["DEBUG", "reference_il:"])
                    # log_queue.put(["DEBUG", dumps(reference_il)])
                    # log_queue.put(["DEBUG", "local_services:"])
                    # log_queue.put(["DEBUG", dumps(local_services)])
                    # log_queue.put(["DEBUG", "federated_services:"])
                    # log_queue.put(["DEBUG", dumps(federated_services)])
                    # log_queue.put(["DEBUG", "nested_ns_instance:"])
                    # log_queue.put(["DEBUG", dumps(nested_ns_instance)])
                    # log_queue.put(["INFO", "*****Time measure: SOEp SOEp autoscaling nested NS local determined new_il_composite_scaling"])
                    if (target_il == None and local_il_nested == None and federated_il_nested == None and reference_il == None):
                        # it means that we are trying to modify a reference, which we do not allow
                        return 404
                    nested_info = ns_db.get_particular_nested_service_info(nsId_tmp[0], nsId)
                    nested_info["status"] = "SCALING"
                    ns_db.update_nested_service_info(nsId_tmp[0], nested_info, "set", nsId_tmp[1])
                    if ("nested_monitoring_jobs" in nested_info):
                        ns_db.set_monitoring_info(nsId_tmp[0], nested_info["nested_monitoring_jobs"])
                        if ("nested_alert_jobs" in nested_info):
                            ns_db.set_alert_info(nsId_tmp[0], nested_info["nested_alert_jobs"])
                    # create the same nested variable that for case 3) scaling of a composite NS
                    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp autoscaling nested NS local relying SOEc" % (nsId_tmp[0])])
                    soe.scale_ns_process(nsId_tmp[0], body, local_il_nested[0])
                    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp autoscaling nested NS local relying SOEc: scale done" % (nsId_tmp[0])])
                    # update the variables after the service is scaled
                    sapInfo = generate_nested_sap_info(nsId_tmp[0], next(iter(local_il_nested[0])))
                    if (sapInfo == None): 
                        # there has been a problem with the nested service and the process failed, we have 
                        # to abort the scaling operation
                        operationId = operation_db.get_operationId(nsId_tmp[0], "INSTANTIATION")
                        operation_db.set_operation_status(operationId, "FAILED")
                        # set ns status as FAILED
                        ns_db.set_ns_status(nsId_tmp[0], "FAILED")
                        # remove the reference previously set
                        if ns_db.get_ns_nested_services_ids(nsId_tmp[0]):
                              ns_db.delete_ns_shared_services_ids(ns_db.get_ns_nested_services_ids(nsId_tmp[0]), nsId_tmp[0])
                        return #stop scaling: to do: to manage in case of failure
                    # now, after scaling, we update the monitoring/alert information 
                    nested_monitoring_jobs = ns_db.get_monitoring_info(nsId_tmp[0])
                    if (len(nested_monitoring_jobs)>0):
                        # it means that there is monitoring jobs
                        info['nested_monitoring_jobs'] = nested_monitoring_jobs
                        # it is not needed to update the alerts!!!
                        # now, we can set to void the monitoring entry
                        ns_db.set_monitoring_info(nsId_tmp[0],[])
                    #it means the scaling operation finished correctly, so we can update the register
                    nested_info["status"] = "INSTANTIATED"
                    nested_info["sapInfo"] = sapInfo
                    nested_info["nested_il"] = body.scale_ns_data.scale_ns_to_level_data.ns_instantiation_level
                    ns_db.update_nested_service_info(nsId_tmp[0], nested_info, "set", nsId)
                    ns_db.save_sap_info(nsId_tmp[0], "")
                    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp autoscaling nested NS local updated DBs" % (nsId_tmp[0])])
                else:
                    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp autoscaling nested NS FEDERATED" % (nsId_tmp[1])])
                    log_queue.put(["DEBUG", "Autoscaling of a nested NS in provider domain"])
                    log_queue.put(["DEBUG", "waiting for a provider nested NS to finish the scaling"])
                    # we are in the case of auto-scaling a federated, so we have to ask for information to update the pairs
                    # we have to implement the waiting procedure before updating the connections, because it is scaling in the provider domain still
                    # the provider sends a scaling request to the consumer with nsIdprovider_nsIdconsumer(composite), 
                    # and in additional params the operationId to query state
                    # we need to build the local_il_nested variables, .... to then udpate the connections
                    ns_info = ns_db.get_ns_record(nsId_tmp[1])
                    log_queue.put(["DEBUG", "Composite current_il: %s"%ns_db.get_ns_il(nsId_tmp[1])])
                    [target_il, local_il_nested, federated_il_nested, reference_il, local_services, federated_services, nested_ns_instance] = \
                    determine_new_il_composite_scaling(body, ns_info, nsId_tmp[0])
                    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp autoscaling nested NS FEDERATED determined new_il_composite_scaling" % (nsId_tmp[1])])
                    nsdId = ns_db.get_nsdId(nsId_tmp[1])
                    nsd_json = nsd_db.get_nsd_json(nsdId, None)
                    if (target_il == None and local_il_nested == None and federated_il_nested == None and reference_il == None):
                        # it means that we are trying to modify a reference, which we do not allow
                        return 404
                    nested_info = ns_db.get_particular_nested_service_info(nsId_tmp[1], nsId_tmp[0])
                    nested_info["status"] = "SCALING"
                    ns_db.update_nested_service_info(nsId_tmp[1], nested_info, "set", nsId_tmp[0])
                    domain = nested_info["domain"]
                    opId = None
                    for key in body.scale_ns_data.additional_param_for_ns.keys(): 
                        if (key == "operationId"):
                            opId = body.scale_ns_data.additional_param_for_ns[key]
                    if (opId):
                        log_queue.put(["DEBUG", "The operationId in the provider domain is: %s"%opId])
                        key = next(iter(domain))
                        log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp waiting autoscaling nested NS FEDERATED" % (nsId_tmp[1])])
                        status = get_operation_status_provider(opId, None, domain[key])
                        while (status != "SUCCESSFULLY_DONE"):
                            if (status == 'FAILED'):
                                operationIdglobal = operation_db.get_operationIdcomplete(nsId_tmp[1], "INSTANTIATION", "PROCESSING")
                                operation_db.set_operation_status(operationIdglobal, "FAILED")
                                ns_db.set_ns_status(nsId_tmp[1], "FAILED")
                                return #stop scaling: to do: to manage in case of failure
                            time.sleep(10)
                            status = get_operation_status_provider(opId, None, domain[key])
                        log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp autoscaling nested NS FEDERATED finished" % (nsId_tmp[1])])
                        log_queue.put(["INFO", "Provider domain finished scaling operationId: %s" % (opId)])
                        federated_info = crooe.get_federated_network_instance_info_request(nsId_tmp[0], nested_info["nested_id"], domain[key], ewbi_port, ewbi_path)
                        log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp autoscaling nested NS FEDERATED obtain crooe info" % (nsId_tmp[1])])
                        log_queue.put(["INFO", "SOEp obtained federatedInfo after SCALING through EWBI: %s"%federated_info])
                        sap_info = get_sap_info_provider(nsId_tmp[0], None, domain[key])
                        nested_info["federatedInstanceInfo"] = federated_info
                        nested_info["sapInfo"] = sap_info
                        nested_info["nested_il"] = body.scale_ns_data.scale_ns_to_level_data.ns_instantiation_level
                        nested_info["status"] = "INSTANTIATED"
                        ns_db.update_nested_service_info(nsId_tmp[1], nested_info, "set", nsId_tmp[0]) 
                        log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp autoscaling nested NS FEDERATED update DBs" % (nsId_tmp[1])])                        
        else:
            nsd_json = nsd_db.get_nsd_json(nsdId, None)
            ns_info = ns_db.get_ns_record(nsId)
            #nested_service_info = ns_db.get_nested_service_info(nsId)
            log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp scaling a composite NS" % (nsId)])
            log_queue.put(["DEBUG", "SOEp case 3) scaling a compositeNS"])
            log_queue.put(["DEBUG", "SOEp case 3) ns_info: %s"% ns_info])
            if "nestedNsdId" in nsd_json["nsd"].keys():
                # case 3) scaling of a composite NS 
                # this means that we are dealing with a composite NS
                # we get target_il and check which are the nesteds that need to scale -> crooe 
                [local_il_nested, federated_il_nested, reference_il, local_services, federated_services, nested_ns_instance] = \
                check_new_df_compatibilities_scaling(body, ns_info)
                if (local_il_nested == None and federated_il_nested == None and reference_il == None):
                    # it means that we are trying to modify a reference, which we do not allow
                    log_queue.put(["DEBUG", "Not allowed operation, trying to modify a reference, we do not continue"])
                    log_queue.put(["DEBUG", "NS Scaling finished without changes"])
                    operationId = operation_db.get_operationIdcomplete(nsId, "INSTANTIATION", "PROCESSING")
                    operation_db.set_operation_status(operationId, "CANCELLED")
                    # set ns status as INSTANTIATED
                    ns_db.set_ns_status(nsId, "INSTANTIATED")
                    return 404
                # if yes, we iterate over the set of them
                # log_queue.put(["DEBUG", "Scaling COMPOSITE local_il_nested: "])
                # log_queue.put(["DEBUG", dumps(local_il_nested, indent=4)])
                # log_queue.put(["DEBUG", "Scaling COMPOSITE federated_il_nested: "])
                # log_queue.put(["DEBUG", dumps(federated_il_nested, indent=4)])
                # log_queue.put(["DEBUG", "Scaling COMPOSITE reference_il:"])
                # log_queue.put(["DEBUG", dumps(reference_il, indent=4)])
                # log_queue.put(["INFO", "*****Time measure: SOEp SOEp scaling a composite NS determining df_compatibilties scaling"])
                for nested in local_il_nested:
                    # we need to define the new body with the target_il 
                    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp scaling a composite NS, iterating over local nested" % (nsId)])
                    nested_body = define_new_body_scaling_for_composite(nested, body)
                    log_queue.put(["DEBUG", "nested_body: %s"% nested_body])
                    # nsId_nested = nsId + '_' + next(iter(nested))
                    nsId_nested = nested[next(iter(nested))][4]
                    nested_info = ns_db.get_particular_nested_service_info(nsId, nsId_nested)
                    nested_info["status"] = "SCALING"
                    ns_db.update_nested_service_info(nsId, nested_info, "set", nsId_nested)
                    # prior to scale the service, we need to recover the sap info information of the nested so it can be updated
                    # sap_info_tmp = nested_info["sapInfo"]
                    # sap_info = transform_nested_sap_info(sap_info_tmp)
                    # log_queue.put(["DEBUG", "transformed sap_info: %s" % dumps(sap_info,indent=4)])
                    # ns_db.save_sap_info(nsId, sap_info)
                    # prior to scale the service, we need to recover the monitoring/alert information so it can be updated
                    if ("nested_monitoring_jobs" in nested_info):
                        ns_db.set_monitoring_info(nsId, nested_info["nested_monitoring_jobs"])
                        if ("nested_alert_jobs" in nested_info):
                            ns_db.set_alert_info(nsId, nested_info["nested_alert_jobs"])
                    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp scaling a composite NS, relying on SOEc" % (nsId)])
                    soe.scale_ns_process(nsId, nested_body, nested)
                    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp scaling a composite NS, scaling finished at SOEc" % (nsId)])
                    # the service is scaled
                    sapInfo = generate_nested_sap_info(nsId, next(iter(nested)))
                    if (sapInfo == None): 
                        # there has been a problem with the nested service and the process failed, we have 
                        # to abort the scaling operation
                        operationId = operation_db.get_operationId(nsId, "INSTANTIATION")
                        operation_db.set_operation_status(operationId, "FAILED")
                        # set ns status as FAILED
                        ns_db.set_ns_status(nsId, "FAILED")
                        # remove the reference previously set
                        if ns_db.get_ns_nested_services_ids(nsId):
                              ns_db.delete_ns_shared_services_ids(ns_db.get_ns_nested_services_ids(nsId), nsId)
                        return #stop scaling: to do: to manage in case of failure
                    # now, after scaling, we update the monitoring/alert information 
                    nested_monitoring_jobs = ns_db.get_monitoring_info(nsId)
                    if (len(nested_monitoring_jobs)>0):
                        # it means that there is monitoring jobs
                        nested_info['nested_monitoring_jobs'] = nested_monitoring_jobs
                        # it is not needed to update the alerts!!!
                        # now, we can set to void the monitoring entry
                        ns_db.set_monitoring_info(nsId,[])
                    #it means the scaling operation finished correctly, so we can update the register
                    nested_info["status"] = "INSTANTIATED"
                    nested_info["sapInfo"] = sapInfo
                    nested_info["nested_il"] = nested[next(iter(nested))][2]
                    ns_db.update_nested_service_info(nsId, nested_info, "set", nsId_nested)
                    ns_db.save_sap_info(nsId, "")
                    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp scaling a composite NS, updating DBs" % (nsId)])
                for nested in federated_il_nested:
                    # case 3.5) scaling a service with federated parts
                    log_queue.put(["INFO", "*****Time measure: SOEp SOEp scaling a composite NS, iterating over federated nested"])
                    nested_body = define_new_body_scaling_for_composite(nested, body)
                    nsId_nested = nested[next(iter(nested))][4]
                    domain = nested[next(iter(nested))][3]
                    nested_info = ns_db.get_particular_nested_service_info(nsId, nsId_nested)
                    # log_queue.put(["In SOEp SCALING FEDERATED, nested_body: %s"%nested_body])
                    # log_queue.put(["In SOEp SCALING FEDERATED, nsId_nested: %s"%nsId_nested])
                    # log_queue.put(["In SOEp SCALING FEDERATED, domain: %s"%domain])
                    # log_queue.put(["In SOEp SCALING FEDERATED, nested_info: %s"%nested_info])                 
                    # domain = ns["domain"]
                    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp scaling a composite NS, scaling federated nested" % (nsId)])
                    scale_federated_service(nsId, nested_info, nsId_nested, nested_body, domain)
                    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp scaling a composite NS, scaled federated nested" % (nsId)])
                # then, we need to update the internestedlinks -> either add, either remove (jump to #update connections with the help of croe)      
            else:
                # 2) scaling of a single delegated NS
                # this means that we are dealing with a delegated NS, and we do not need to update connections,
                # so after the scaling, we return
                log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp handling scaling delegated" % (nsId)])
                ns = ns_info['nested_service_info'][0]   
                nested_id_instance = ns["nested_instance_id"]
                domain = ns["domain"]
                target_il = scale_federated_service(nsId, ns, nested_id_instance, body, domain)
                log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp handling scaling delegated, delegated scaled"% (nsId)])
                #update the register in the global registry
                operationId = operation_db.get_operationIdcomplete(nsId, "INSTANTIATION", "PROCESSING")
                ns_record = ns_db.get_ns_record(nsId)
                status = "INSTANTIATED"
                for elem in ns_record["nested_service_info"]:
                    if not elem["status"] == "INSTANTIATED":
                        status = "INSTANTIATING"
                        break
                if (status == "INSTANTIATED"):
                    log_queue.put(["DEBUG", "NS Scaling finished correctly"])
                    operation_db.set_operation_status(operationId, "SUCCESSFULLY_DONE")
                    # set the new instantiation level
                    ns_db.set_ns_il(nsId, target_il)
                    # set ns status as INSTANTIATED
                    ns_db.set_ns_status(nsId, "INSTANTIATED")
                    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp handling scaling delegated, updated DBs"% (nsId)])
                    return

    # update connections with the help of crooe
    # first local nested connections
    # we need again to evaluate the case we are, so we provide the correct nsId identifier. 
    # We will enter here for cases 3) and 4) and its subcases
    # the other variables, have been previously created
    log_queue.put(["INFO", "*****Time measure: SOEp SOEp start updating connections (multiple cases)"])
    connection_step_nsdId = ns_db.get_nsdId(nsId)
    if (connection_step_nsdId == None):
        #this means that a nested is autoscaling
        connection_step_nsId_tmp = nsId.split('_')
        if (len(connection_step_nsId_tmp) > 1):
            # the scale request refers to a scaling of a nested service
            if ns_db.get_nsdId(connection_step_nsId_tmp[0]):
                # auto-scaling of a consumer nested service
                connection_nsId = connection_step_nsId_tmp[0]
            else:
                # auto-scaling of a provider nested service
                connection_nsId = connection_step_nsId_tmp[1]
    else:
        # if existing, then the scale request refers to a composite request
        connection_nsId = nsId

    if ((len(local_il_nested) > 0 and len(local_services)>1) or (len(local_services) >0 and len(reference_il) > 0)):  
        # here we still consider that the reference is always a local service
        log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp-CROOE scaling updating local nested NSs interconnections" % (connection_nsId)])
        crooe.update_connecting_nested_local_services(connection_nsId, nsd_json, local_services, nested_ns_instance)
        log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp-CROOE scaling finishing updating local nested NSs interconnections" % (connection_nsId)])
    if (len(federated_services)>0 and (len(federated_il_nested)>0 or len(local_il_nested)>0 or len(reference_il) > 0)):
        log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp-CROOE scaling updated federated nested NSs interconnections" % (connection_nsId)])
        crooe.update_connecting_nested_federated_local_services(connection_nsId, nsd_json, nested_ns_instance)
        log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp-CROOE scaling finishing updated federated nested NSs interconnections" % (connection_nsId)])      

    # after scaling all the nested services, update info of the instantiation at the composite level    
    #operationId = operation_db.get_operationId(connection_nsId, "INSTANTIATION")
    operationId = operation_db.get_operationIdcomplete(connection_nsId, "INSTANTIATION", "PROCESSING")
    log_queue.put(["DEBUG", "Final step validating OperationID and updating DBs"])
    ns_record = ns_db.get_ns_record(connection_nsId)
    status = "INSTANTIATED"
    for elem in ns_record["nested_service_info"]:
        if not elem["status"] == "INSTANTIATED":
            status = "INSTANTIATING"
            break
    if (status == "INSTANTIATED"):
        log_queue.put(["DEBUG", "NS Scaling finished correctly"])
        operation_db.set_operation_status(operationId, "SUCCESSFULLY_DONE")
        # set the new instantiation level
        ns_db.set_ns_il(connection_nsId, target_il)
        # set ns status as INSTANTIATED
        ns_db.set_ns_status(connection_nsId, "INSTANTIATED")
    notification_db.create_notification_record({
        "nsId": nsId,
        "type": "fa-gears",
        "text": nsId + " SCALED",
        "time": datetime.now().strftime("%d/%m/%Y %H:%M:%S.%f")
      })


def terminate_ns_process(nsId, aux):
    """
    Function description
    Parameters
    ----------
    param1: type
        param1 description
    Returns
    -------
    name: type
        return description
    """
    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp starting terminating service" % (nsId)])
    log_queue.put(["DEBUG", "SOEp terminating_ns_process with nsId %s" % (nsId)])
    ns_db.set_ns_status(nsId, "TERMINATING")
    nested_record = ns_db.get_ns_record(nsId)
    nested_info = nested_record["nested_service_info"]
    # we have to remove in reverse order of creation (list are ordered in python)
    #for index in range(0, len(nested_info)):
    for index in range(len(nested_info)-1, -1, -1):
        log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp terminating nested service index %s" % (nsId, index)])
        nested_service = nested_info[index]
        if (nested_service["domain"] == "local"):
            # local service to be terminated
            nested_service["status"] = "TERMINATING"
            log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp terminating LOCAL nested service: %s"% (nsId, nested_service["nested_instance_id"])])
            soe.terminate_ns_process(nested_service["nested_instance_id"], None)
            # update the status
            nested_service["status"] = "TERMINATED"
            log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp terminated LOCAL nested service: %s"% (nsId, nested_service["nested_instance_id"])])

        else:
            # federated service to be terminated
            log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp terminating FEDERATED nested service: %s"% (nsId,nested_service["nested_instance_id"])])
            [operationId, conn] = terminate_ns_provider(nested_service["nested_instance_id"], nested_service["domain"])
            nested_service["status"] = "TERMINATING"
            status = "TERMINATING"
            while (status != "SUCCESSFULLY_DONE"):		
                status = get_operation_status_provider(operationId, conn)
                if (status == 'FAILED'):
                    operationIdglobal = operation_db.get_operationId(nsId, "TERMINATION")
                    operation_db.set_operation_status(operationIdglobal, "FAILED")
                    # set ns status as FAILED
                    ns_db.set_ns_status(nsId, "FAILED")
                    return #stop instantiating: to do: to manage in case of failure
                time.sleep(10)
            # update the status
            nested_service["status"] = "TERMINATED"
            notification_db.create_notification_record({
                "nsId": nested_service["nested_instance_id"],
                "type": "fa-trash-o",
                "text": nested_service["nested_instance_id"] + " TERMINATED in FEDERATED domain" + nested_service["domain"],
                "time": datetime.now().strftime("%d/%m/%Y %H:%M:%S.%f")
              })
            log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp terminated FEDERATED nested service: %s"% (nsId,nested_service["nested_instance_id"])])

    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp terminated ALL nested service" % (nsId)])
    #croe remove the local logical links for this composite service (to be reviewed when federation)
    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp starting removing nested connections" % (nsId)])
    crooe.remove_nested_connections(nsId)
    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp finishing removing nested connections" % (nsId)])

    #now declare the composite service as terminated
    operationId = operation_db.get_operationId(nsId, "TERMINATION")
    status = "TERMINATED"
    for index in range (0, len(nested_info)):
        if not nested_info[index]["status"] == "TERMINATED":
            status = "TERMINATING"
            break
    if (status == "TERMINATED"):
        operation_db.set_operation_status(operationId, "SUCCESSFULLY_DONE")
        log_queue.put(["INFO", "NS Termination finished correctly :)"])
        # set ns status as TERMINATED
        ns_db.set_ns_status(nsId, "TERMINATED")
        # update the possible connections
        if "nestedNsId" in nested_record: 
            nested_instanceId = ns_db.delete_ns_nested_services_ids(nsId)
            ns_db.delete_ns_shared_services_ids(nested_instanceId, nsId)
        # for the 5Gr-VS not to break
        # ns_db.delete_ns_record(nsId)
    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp finished terminating service" % (nsId)])
    notification_db.create_notification_record({
        "nsId": nsId,
        "type": "fa-trash-o",
        "text": nsId + " TERMINATED",
        "time": datetime.now().strftime("%d/%m/%Y %H:%M:%S.%f")
      })


########################################################################################################################
# PUBLIC METHODS                                                                                                       #
########################################################################################################################


def create_ns_identifier(body):
    """
    Creates and returns an Identifier for an instance of the NSD identified in the body by the parameter nsd_id.
    Saves the identifier and the information associated in the Network Service Instances DB and sets the status to "NOT
    INSTANTIATED".
    Parameters
    ----------
    body: request
        includes the following fields:
        "nsd_id", string, ifentifier of the NSD
        "ns_name", string, name to be associated to the NS instance
        "ns_description": string, description to be associated to the NS instance
    Returns
    -------
    nsId: string
        Identifier of the Network Service Instance.
    """

    # check nsd exists, return 404 if it doesn"t exist
    log_queue.put(["INFO", "create_ns_identifier for: %s" % body])

    nsd_id = body.nsd_id
    if not exists_nsd(nsd_id):
        return 404
    # create the identifier
    nsId = str(uuid4())
    # for cloudify compatibility it must start with a letter
    # nsId = 'a' + nsId[1:]
    nsId = 'fgt-' + nsId[1:]

    # save to DB
    ns_db.create_ns_record(nsId, body)

    return nsId

def instantiate_ns(nsId, body, requester):
    """
    Starts a process to instantiate the Network Service associated to the instance identified by "nsId".
    Parameters
    ----------
    nsId: string
        Identifier of the Network Service Instance.
    body: request body
    requester: string
        IP address of the entity making the request
    Returns
    -------
    string
        Id of the operation associated to the Network Service instantiation.
    """
    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp instantiating a NS" % (nsId)])
    log_queue.put(["INFO", "instantiate_ns for nsId %s with body: %s" % (nsId, body)])
    #client = MongoClient()
    #fgtso_db = client.fgtso
    #ns_coll = fgtso_db.ns

    if not ns_db.exists_nsId(nsId):
        return 404

    status = ns_db.get_ns_status(nsId)
    if status != "NOT_INSTANTIATED":
        return 400

    if body.nested_ns_instance_id:
        #as we only are assuming one level of nesting, the nested_ns_instance_id array will be formed by one nsId
        if not ns_db.exists_nsId(body.nested_ns_instance_id[0]):
            return 404
        nested_status = ns_db.get_ns_status(body.nested_ns_instance_id[0])
        if nested_status != "INSTANTIATED":
            return 400
        # can be shared this nested_ns_instance?
        nsd_shareable = nsd_db.get_nsd_shareability(body.nested_ns_instance_id[0])
        if (nsd_shareable == "False"):
           return 404

    validIP = False
    request_origin = "local"
    log_queue.put(["DEBUG", "SOEp receiving request from: %s"%(requester)])
    # check where the request comes from, either local or from a federated domain
    if requester not in available_VS:
        #it comes from a federated domain
        request_origin = requester
        # now, check if it is a validIP, from a registered federated domain
        for domain in fed_domain.keys():
            if (fed_domain[domain] == requester):
                validIP = True
                log_queue.put(["INFO", "SOEp receiving request from a valid federated domain: %s = (%s)"%(domain,fed_domain[domain])])
    else:
        log_queue.put(["INFO", "SOEp receiving request from a valid local domain"])
        validIP = True
        
    if not validIP:
        # the request comes from a non-authorised origin, discard the request
        return 404

    ns_db.save_instantiation_info(nsId, body, requester)
    operationId = create_operation_identifier(nsId, "INSTANTIATION")
    # two options to delegate to soec: if there is not a reference instance 
    # or if the nsd descriptor does not have "nestedNsdId" field
    # get the nsdId that corresponds to nsId
    nsdId = ns_db.get_nsdId(nsId)
    # first get the ns and vnfs descriptors
    nsd_json = nsd_db.get_nsd_json(nsdId, None)
    domain = nsd_db.get_nsd_domain (nsdId)
    if (domain == "local" and not body.additional_param_for_ns): 
        # when you onboard the single nested ones, you specify the provider (either locar or other)
        # composite network services descriptors domain value is set to composite, so SOEp must handle it
        log_queue.put(["INFO", "SOEp delegating the INSTANTIATION to SOEc"])
        ps = Process(target=soe.instantiate_ns_process, args=(nsId, body))
        ps.start()
        # save process
        soe.processes[operationId] = ps
    else:
        # soep should do things: it is a composite, there is a reference, there is delegation, 
        # it is a request coming from a consumer federated domain
        # update: 19/09/17: For the eHealth usecase, it is considered to add UserData key 
        # info in body.additional_para_for_ns, so we need to handle this new case
        if (domain == "local" and body.additional_param_for_ns and ("nsId" not in body.additional_param_for_ns) and ("network_mapping" not in body.additional_param_for_ns) ):
            log_queue.put(["INFO", "SOEp delegating the INSTANTIATION to SOEc"])
            ps = Process(target=soe.instantiate_ns_process, args=(nsId, body))
            ps.start()
            # save process
            soe.processes[operationId] = ps
        else:
            log_queue.put(["INFO", "SOEp taking charge of the instantiation"])
            ps = Process(target=instantiate_ns_process, args=(nsId,body, request_origin))
            ps.start()
            # save process
            processes_parent[operationId] = ps
    # log_queue.put(["INFO", "*****Time measure: finished instantiation at SOEp"])
    return operationId


def scale_ns(nsId, body, requester):
    """
    Starts a process to scale the Network Service associated with the instance identified by "nsId".
    Parameters
    ----------
    nsId: string
        Identifier of the Network Service Instance.
    body: request body
    requester: string
        IP address of the entity making the request
    Returns
    -------
    string
        Id of the operation associated to the Network Service instantiation.
    """
    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp scaling a NS" % (nsId)])
    log_queue.put(["INFO", "scale_ns for nsId %s with body: %s" % (nsId, body)])

    # if not ns_db.exists_nsId(nsId):
    #     return 404

    # status = ns_db.get_ns_status(nsId)
    # if status != "INSTANTIATED":
    #     return 400

    # !!!!!the following line commented for the test case (ns_db, operationId)
    if (len(nsId.split('_')) > 1):
        # here we are in front of two cases: auto-scaling of a local nested
        # or autoscaled of a federated
        nsId_tmp = nsId.split('_')
        if ns_db.exists_nsId(nsId_tmp[0]):
            status = ns_db.get_ns_status(nsId_tmp[0])
            nsId_tmp2 = nsId_tmp[0]
            log_queue.put(["DEBUG", "Scaling a nested NS requested by consumer"])
        elif ns_db.exists_nsId(nsId_tmp[1]):
            status = ns_db.get_ns_status(nsId_tmp[1])
            nsId_tmp2 = nsId_tmp[1]
            log_queue.put(["DEBUG", "Scaling a nested NS requested by provider"])
        else:
            log_queue.put(["DEBUG", "Scale request with wrong nsId"])
            # if neither of those exists, you cannot scale, bad nsId
            return 404
        if status != "INSTANTIATED":
            return 400
        ns_db.set_ns_status(nsId_tmp2, "SCALING")
        operationId = create_operation_identifier(nsId_tmp2, "INSTANTIATION")
        log_queue.put(["DEBUG", "El operation ID START para BIG lengths es: %s y nsId: %s"%(operationId,nsId_tmp2)])        
    else:
        ns_db.set_ns_status(nsId, "SCALING")
        operationId = create_operation_identifier(nsId, "INSTANTIATION")
        log_queue.put(["DEBUG", "El operation ID START es: %s y nsId: %s"%(operationId,nsId)])
    # considered cases for scaling:  
    # 1) local scaling of single NS
    #    1.5) considering that this single NS it is being used by a composite
    # 2) scaling of a single delegated NS 
    #    2.5) auto-scaling of a single delegated NS
    # 3) scaling of a composite NS 
    #    3.5) scaling of a composite with federated components 
    # 4) autoscaling of a nested NS local 
    #    4.5) autoscaling of nested NS federated -> need to drive connections
    # get the nsdId that corresponds to nsId
    validIP = False
    request_origin = "local"
    log_queue.put(["DEBUG", "SOEp receiving SCALING request from: %s"%(requester)])
    # check where the request comes from, either local or from a federated domain
    if requester not in available_VS:
        #it comes from a federated domain
        request_origin = requester
        # now, check if it is a validIP, from a registered federated domain
        for domain in fed_domain.keys():
            if (fed_domain[domain] == requester):
                validIP = True
                log_queue.put(["INFO", "SOEp receiving SCALING request from a valid federated domain: %s = (%s)"%(domain,fed_domain[domain])])
    else:
        log_queue.put(["INFO", "SOEp receiving SCALING request from a valid local domain"])
        validIP = True
        
    if not validIP:
        # the request comes from a non-authorised origin, discard the request
        log_queue.put(["INFO", "SOEp receiving SCALING request from a non-valid requester"])
        return 404

    nsdId = ns_db.get_nsdId(nsId)
    nsId_tmp = None
    if nsdId is None:
        # it means it is auto-scaling of a nested NS local or a nested NS federated, 
        # in case local, we need to extract the json and the domain from the composite entry
        # we assume that we do not find the entry, because a nested has not own entry in the ns_db
        nsId_tmp = nsId.split('_')
        if (request_origin == "local"):
            log_queue.put(["DEBUG", "Scaling a CONSUMER nested NS"])
            nested_service_info = ns_db.get_particular_nested_service_info(nsId_tmp[0], nsId)
        else:
            # it is an auto-scaling request from the federated domain, but it can be from a nested or a single delegated
            if (len(nsId_tmp) >1):
                # auto-scaling of a federated nested NS
                log_queue.put(["DEBUG", "Scaling a PROVIDER nested NS"])
                nested_service_info = ns_db.get_particular_nested_service_info(nsId_tmp[1], nsId_tmp[0])
            else:
                # auto-scaling of a delegated NS
                nsId_consumer = ns_db.get_consumer_owner_delegated(nsId)
                if (nsId_consumer):
                    nested_service_info =ns_db.get_particular_nested_service_info(nsId_consumer, nsId)
                else:
                    log_queue.put(["DEBUG", "This request does not correspond to any ongoing delegated NS"])
                    return 404
        nsd_json = nsd_db.get_nsd_json(nested_service_info["nested_id"], None)
        domain = nested_service_info["domain"]
    else:
        nsd_json = nsd_db.get_nsd_json(nsdId, None)
        domain = nsd_db.get_nsd_domain (nsdId)
    log_queue.put(["DEBUG", "scaling domain: %s"%(domain)])
    if (domain == "local" and nsId_tmp == None):
        log_queue.put(["INFO", "*****Time measure: SOEp SOEp delegating the scaling to SOEc"])
        log_queue.put(["DEBUG", "SOEp delegating the SCALING to SOEc"])
        log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp delegating the SCALING to SOEc" % (nsId)])
        ps = Process(target=soe.scale_ns_process, args=(nsId, body))
        ps.start()
        # save process
        soe.processes[operationId] = ps
        # partial Case 3)
        # this could be also a reference for a composite so you should wait to update the connections
        # with associated composites when possible -> assuming that dfs are compatible
        # we give some time to create the new process, because we need to create 
        # another one waiting to the previous to finish, in case it is a reference 
        if ns_db.get_ns_shared_services_ids(nsId):
            # case we have a reference, the rest of the scaling process, is managed by the SOEp
            # time.sleep(5)
            log_queue.put(["INFO", "We need to UPDATE composite NSs associated to this nested NS"])
            log_queue.put(["INFO", "opening another thread at the SOEp to handle the scaling of associated composites"])
            # again, assuming that dfs are compatible, in this case we need to update connections
            log_queue.put(["INFO", "*****Time measure: SOEp SOEp updating composite NS associated to the nested (reference) NS -> parallel thread"])
            ps2 = Process(target=scale_ns_process, args=(nsId, body, ns_db.get_ns_shared_services_ids(nsId)))
            ps2.start()
            processes_parent[operationId] = ps2
        # Case 4.5)
        # auto-scaling of a nested federated, so you have to trigger the "update procedure" at the consumer domain
        ns_record = ns_db.get_ns_record(nsId)
        # log_queue.put(["DEBUG", "NS_RECORD SCALE_NS: %s"%(ns_record)])
        if ( ("consumerNsId" in ns_record) and (requester in available_VS)):
            # we need to launch/inform about the scaling operation in the consumer domain
            nsId_tmp2 = nsId + '_' + ns_record["consumerNsId"]
            log_queue.put(["INFO", "*****Time measure: SOEp SOEp informing CONSUMER domain of scaling operation at PROVIDER domain FEDERATED SERVICE"])
            scale_ns_consumer(nsId_tmp2, body, ns_record["requester"], operationId)
        if ("Federating service" in ns_record["ns_description"] and not "consumerNsId" in ns_record):
            log_queue.put(["INFO", "*****Time measure: SOEp SOEp informing CONSUMER domain of scaling operation at PROVIDER domain DELEGATED SERVICE"])
            # auto-scaled single delegated NS, to warn about the consumer domain
            scale_ns_consumer(nsId, body, ns_record["requester"], operationId)
    else:
        # soep should do things: there are nested, there is a reference, there is delegation
        # if "nestedNsdId" in nsd_json["nsd"].keys():
            # return 404
        # else:
            # log_queue.put(["DEBUG", "SOEp taking charge of the scaling"])
            # ps = Process(target=scale_ns_process, args=(nsId,body))
            # ps.start()
            # # save process
            # processes_parent[operationId] = ps
        # cases 2), 3), 4) (still to take into account)
        # in both cases, SOEp takes care
        log_queue.put(["INFO", "*****Time measure: SOEp SOEp taking care of the scaling"])
        log_queue.put(["DEBUG", "SOEp taking charge of the scaling"])
        ps = Process(target=scale_ns_process, args=(nsId,body))
        ps.start()
        # save process
        processes_parent[operationId] = ps
    log_queue.put(["DEBUG", "The operation ID for the scaling operation END is: %s"%operationId])
    return operationId


def terminate_ns(nsId, requester):
    """
    Starts a process to terminate the NS instance identified by "nsId".
    Parameters
    ----------
    nsId: string
        Identifier of the NS instance to terminate.
    requester: string
        IP address of the entity making the request
    Returns
    -------
    operationId: string
        Identifier of the operation in charge of terminating the service.
    """
    log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp terminating a NS" % (nsId)])
    if not ns_db.exists_nsId(nsId):
        return 404
    registered_requester = ns_db.get_ns_requester(nsId)
    if (registered_requester != requester):
        return 404
    # check the ns status
    status = ns_db.get_ns_status(nsId)
    log_queue.put(["INFO", "Network service %s is in %s state." % (nsId, status)])

    if status in ["TERMINATING", "TERMINATED", "NOT_INSTANTIATED"]:
        return 400
    # if status is INSTANTIATING, kill the instantiation process
    if status == "INSTANTIATING":
        # set related operation as CANCELLED
        operationId = operation_db.get_operationId(nsId, "INSTANTIATION")
        operation_db.set_operation_status(operationId, "CANCELLED")
        # cancel instantiation process
        process = processes_parent[operationId]
        process.terminate()
        process.join()

    # we need to know if it is a single or a composite service, here we assume that everything is in INSTANTIATED state
    nsdId = ns_db.get_nsdId(nsId)
    domain = nsd_db.get_nsd_domain (nsdId)
    # first we create the operation Id to terminate the service, this will be the one that the 5Gr-VS will poll
    operationId = create_operation_identifier(nsId, "TERMINATION")
    if (domain == "local"):
        # first check if it is possible to remove the service
        sharing_status = ns_db.get_sharing_status(nsId)
        if sharing_status:
            # this single NS is being used by a composite, so 5Gr-SO will 
            # will not process the request
            return 400
        else:
            # this single NS is not being used by other composite/ 
            # or its relations have already finished
            log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp delegating the TERMINATION to SOEc" % (nsId)])
            ps = Process(target=soe.terminate_ns_process, args=(nsId, None))
            ps.start()
            soe.processes[operationId] = ps
    else: 
        log_queue.put(["INFO", "*****Time measure for nsId: %s: SOEp SOEp taking charge of the TERMINATION operation" % (nsId)])
        ps = Process(target=terminate_ns_process, args=(nsId, None))
        ps.start()
        # save process
        processes_parent[operationId] = ps
    # log_queue.put(["INFO", "*****Time measure: finished termination at SOEp"])
    return operationId


def query_ns(nsId):
    """
    Returns the information of the Network Service Instance identified by nsId.
    Parameters
    ----------
    nsId: string
        Identifier of the NS instance to terminate.
    Returns
    -------
    dict
        Information of the Network Service Instance.
    """

    if not ns_db.exists_nsId(nsId):
        # TODO create errors
        return 404
    # TODO: lines below are a stub
    status = ns_db.get_ns_status(nsId)
    vs_status = "FAILED"
    if status in [ "TERMINATED", "INSTANTIATING", "TERMINATING"]:
        vs_status = "NOT_INSTANTIATED"
    elif status == "INSTANTIATED":
        vs_status = "INSTANTIATED"

    nsd_id = ns_db.get_nsdId(nsId)
    domain = nsd_db.get_nsd_domain (nsd_id)
    nsd_json = nsd_db.get_nsd_json(nsd_id)
    info = {}
    if (domain == "local"):
        # single local NS
        info = soe.query_ns(nsId) 
    else:
        # two cases, it is composite or it is delegated 
        ns_name = ns_db.get_ns_name(nsId)
        ns_description = ns_db.get_ns_description(nsId)
        flavour_id = ns_db.get_ns_flavour_id(nsId)
        info = {"nsInstanceId":nsId,
                "nsName": ns_name,
                "description": ns_description,
                "nsdId": nsd_id,
                "flavourId": flavour_id,
                "nsState": vs_status,
             }
        ns_info_record = ns_db.get_nested_service_info(nsId) 
        aggregated_user_access_info = []   
        info["sapInfo"] = []
        if "nestedNsdId" in nsd_json["nsd"]:
            if vs_status == "NOT_INSTANTIATED":
                info["sapInfo"] = []
            else:
                # it is a composite so you need to construct the sap info result
                # first we make a mapping at crooe with the saps and the nsVirtuaLinkDesc
                log_queue.put(["DEBUG", "query_result for nsId: %s" % nsId])
                sap_composite_mapping  = crooe.mapping_composite_saps_to_nested_saps(nsId, nsd_json)
                log_queue.put(["DEBUG", "sap_composite_mapping: %s" % dumps(sap_composite_mapping, indent=4, sort_keys=True)])
                # sap_mapping: {'mgt_ehealth_mon_sap': {'eHealth-vEPC': ['mgt_vepc_sap'], 'eHealth-BE': ['mgt_ehealth_mon_be_sap']}}
                nested_info = ns_db.get_nested_service_info(nsId)
                # now treat the case of a reference
                reference_ns = ns_db.get_ns_nested_services_ids(nsId)
                for sap in sap_composite_mapping.keys():
                    sap_info = {}
                    sap_info["address"] = "test for future"
                    sap_info["description"] = sap_composite_mapping[sap]["info"]["description"]
                    sap_info["sapInstanceId"] = "0"
                    sap_info["sapName"] = sap_composite_mapping[sap]["info"]["cpdId"]
                    sap_info["sapdId" ] = sap_composite_mapping[sap]["info"]["cpdId"]
                    sap_info["userAccessInfo"] = []
                    for nested in nested_info:
                        if nested["nested_id"] in sap_composite_mapping[sap]["nested"].keys():
                            for sap2 in sap_composite_mapping[sap]["nested"][nested["nested_id"]]:
                                for sap3 in nested["sapInfo"]:
                                    if (sap2 == sap3["sapdId"]):
                                       sap_info["userAccessInfo"] = sap_info["userAccessInfo"] +sap3["userAccessInfo"] 
                    info["sapInfo"].append(sap_info)
                if reference_ns:
                    reference_ns = ns_db.get_ns_nested_services_ids(nsId)
                    reference_nsd_id = ns_db.get_nsdId(reference_ns)
                    reference_nsd_json = nsd_db.get_nsd_json(reference_nsd_id)
                    for sap in sap_composite_mapping.keys():
                        for sap2 in sap_composite_mapping[sap]["nested"].keys():
                            if sap2 == reference_nsd_json["nsd"]["nsdIdentifier"]:
                                if "sapd" in reference_nsd_json["nsd"]:
                                    sap_reference_info = get_ns_sap_info(reference_ns, reference_nsd_json["nsd"]["sapd"])
                                    log_queue.put(["DEBUG", "sap_reference_info: %s"% sap_reference_info])
                                    for sap3 in sap_reference_info:
                                        for sap4 in sap_composite_mapping[sap]["nested"][sap2]:
                                            if sap3["sapdId"] == sap4:
                                                for elem in info["sapInfo"]:
                                                    if elem["sapdId"] == sap:
                                                        elem["userAccessInfo"] = elem["userAccessInfo"] + sap3["userAccessInfo"]
        else:
            # it is a delegated one, so we get the info from our databases
            for nested_service in ns_info_record:
                if (nested_service["nested_id"] == nsd_id):
                    info["sapInfo"] = nested_service["sapInfo"]
    log_queue.put(["DEBUG", "query_result: %s"% dumps(info, indent=4, sort_keys=True)])
    return info

def get_ns_sap_info(nsi_id, nsd_saps):
    sap_list = []
    nsi_sap_info = ns_db.get_ns_sap_info(nsi_id)
    for current_sap in nsd_saps:
        if current_sap["cpdId"] in nsi_sap_info:
            sap_address = "test for future"
            user_access_info = []
            for address in nsi_sap_info[current_sap["cpdId"]]: 
                for key in address.keys():
                    user_info_dict = {}
                    user_info_dict['address'] = address[key]
                    user_info_dict['sapdId'] = current_sap["cpdId"]
                    user_info_dict['vnfdId'] = key
                    user_access_info.append(user_info_dict)
                new_sap = {"sapInstanceId": "0",
                           "sapdId": current_sap["cpdId"],
                           "sapName": current_sap["cpdId"],
                           "description": current_sap["description"],
                           "address": sap_address,
                           "userAccessInfo": user_access_info
                       }
            sap_list.append(new_sap)
    # log_queue.put(["INFO", "get_ns_sap_info output nsi_id:%s nsi_sap:%s" % (nsi_id, sap_list)])
    return sap_list

def get_operation_status(operationId):
    """
    Function to get the status of the operation identified by operationId.
    Parameters
    ----------
    operationId
        Identifier of the operation.
    Returns
    -------
    string
        status of the operation.
    """

    if not operation_db.exists_operationId(operationId):
        return 404

    status = operation_db.get_operation_status(operationId)

    return status

def query_nsds():
    """
    Function to get the IFA014 json of all onboarded NSDs
    Parameters
    ----------
    Returns
    -------
    list
        network service IFA014 json descriptors
    """
    list_of_nsds= []
    nsds = nsd_db.get_all_nsd()
    for nsd in nsds:
        list_of_nsds.append(nsd["nsdJson"])
    return list_of_nsds

def query_nsd(nsdId, version):
    """
    Function to get the IFA014 json of the NSD defined by nsdId and version.
    Parameters
    ----------
    nsdId: string
        Identifier of the network service descriptor.
    version: string
        Version of the network service descriptor.

    Returns
    -------
    dict
        network service IFA014 json descriptor
    """
    nsd_json = nsd_db.get_nsd_json(nsdId, version)
    if nsd_json is None:
        return 404
    return nsd_json
    
def query_vnfds():
    """
    Function to get the IFA011 json of all onboarded VNFDs
    Parameters
    ----------
    Returns
    -------
    list
        network service IFA014 json descriptors
    """
    list_of_vnfds= []
    vnfds = vnfd_db.get_all_vnfd()
    for vnfd in vnfds:
        list_of_vnfds.append(vnfd["vnfdJson"])
    return list_of_vnfds

def query_vnfd(vnfdId, version):
    """
    Function to get the IFA011 json of the VNFD defined by vnfdId and version.
    Parameters
    ----------
    vnfdId: string
        Identifier of the virtual network function descriptor.
    version: string
        Version of the virtual network function descriptor.

    Returns
    -------
    dict
        virtual network function IFA014 json descriptor
    """
    vnfd_json = vnfd_db.get_vnfd_json(vnfdId, version)
    if vnfd_json is None:
        return 404
    return vnfd_json

def query_appd(appdId, version):
    """
    Function to get the MEC010-2 json of the MEC app defined by appdId and version.
    Parameters
    ----------
    appdId: string
        Identifier of the MEC application descriptor.
    version: string
        Version of the MEC application descriptor.

    Returns
    -------
    dict
        MEC application MEC010-2 json descriptor
    """
    appd_json = appd_db.get_appd_json(appdId, version)
    if appd_json is None:
        return 404
    return appd_json

def query_pnfd(pnfdId, version):
    """
    Function to get the IFA014 json of the PNFD defined by pnfdId and version.
    Parameters
    ----------
    pnfdId: string
        Identifier of the Physical Network function descriptor.
    version: string
        Version of the Physical Network function descriptor.

    Returns
    -------
    dict
        PNF IFA014 json descriptor
    """
    pnfd_json = pnfd_db.get_pnfd_json(pnfdId, version)
    if pnfd_json is None:
        return 404
    return pnfd_json

def delete_nsd(nsdId, version):
    """
    Function to delete from the catalog the NSD defined by nsdId and version.
    Parameters
    ----------
    nsdId: string
        Identifier of the network service descriptor.
    version: string
        Version of the network service descriptor.

    Returns
    -------
    boolean
    """
    operation_result = nsd_db.delete_nsd_json(nsdId, version)
    return operation_result

def delete_vnfd(vnfdId, version):
    """
    Function to delete from the catalog the VNFD defined by vnfdId and version.
    Parameters
    ----------
    vnfdId: string
        Identifier of the virtual network function descriptor.
    version: string
        Version of the virtual network function service descriptor.

    Returns
    -------
    boolean
    """
    operation_result = vnfd_db.delete_vnfd_json(vnfdId, version)
    return operation_result

def delete_appd(appdId, version):
    """
    Function to delete from the catalog the MEC app defined by vnfdId and version.
    Parameters
    ----------
    appdId: string
        Identifier of the MEC application descriptor.
    version: string
        Version of the MEC application descriptor.

    Returns
    -------
    boolean
    """
    operation_result = appd_db.delete_appd_json(appdId, version)
    return operation_result

def delete_pnfd(pnfdId, version):
    """
    Function to delete from the catalog the PNFD defined by pnfdId and version.
    Parameters
    ----------
    pnfdId: string
        Identifier of the Physical network function descriptor.
    version: string
        Version of the Physical network function descriptor.

    Returns
    -------
    boolean
    """
    operation_result = pnfd_db.delete_pnfd_json(pnfdId, version)
    return operation_result

def onboard_nsd(nsd_json, requester):
    """
    Function to onboard the NSD contained in the input.
    Parameters
    ----------
    nsd_json: dict
        IFA014 network service descriptor.
    requester: string
        IP address of the requester
    Returns
    -------
    nsdInfoId: string
        The identifier assigned in the db
    """
    log_queue.put(["INFO", "Requester Onboard_nsd: %s"% requester])
    domain = None
    shareable = "True"
    #if (requester == "127.0.0.1"):
    if (requester in available_VS):
        #assuming VS in the same machine
        domain = "local"
    else:
        for elem in fed_domain.keys():
            if (fed_domain[elem] == requester):
                #domain = elem
                domain = {elem: requester}
                shareable = "False" # for the moment, we are not going to consider the sharing with federated network services
    if ("nestedNsdId" in nsd_json["nsd"].keys()):
        # it is suppose that the nested ones will be available at the database
        domain = "Composite"
        shareable = "False" #composite network services cannot be shared by others

    if domain is not None:
        nsd_record = {"nsdId": nsd_json["nsd"]["nsdIdentifier"],
                      # "nsdCloudifyId": nsdCloudifyId["eHealth_v01"],
                      "version": nsd_json["nsd"]["version"],
                      "nsdName": nsd_json["nsd"]["nsdName"],
                      "nsdJson": nsd_json,
                      "domain": domain,
                      "shareable": shareable}
        log_queue.put(["DEBUG", "ONBOARD_NSD result: %s"% dumps(nsd_record, indent=4)])
        if nsd_db.exists_nsd(nsd_json["nsd"]["nsdIdentifier"], nsd_json["nsd"]["version"]):
            # it is an update, so remove previously the descriptor
            nsd_db.delete_nsd_json(nsd_json["nsd"]["nsdIdentifier"])
        # then insert it again (creation or "update")
        nsd_db.insert_nsd(nsd_record)
        if (domain == "local"):
            # this descriptor has to be uploaded in the MANO platform
            soe.onboard_nsd_mano(nsd_json)         
        return nsd_record["nsdId"]
    else:
        return 404

def onboard_vnfd(body):
    """
    Function to onboard the VNFD, including the downloading from the url specified in the input.
    Parameters
    ----------
    body: dict
        IFA013 request to onboard a vnfd.
    Returns
    -------
    info: dict
        Dictionary with the IFA013 answer to the vnfd onboarding process
    """
    log_queue.put(["INFO", "vnf_package_path: %s"% body.vnf_package_path])
    filename=wget.download(body.vnf_package_path)
    tf=tarfile.open(filename)
    tf.extractall()
    with tf as _tar:
        for member in _tar:
            if member.isdir():
                continue
            print (member.name)
            if member.name.find("json"):
                fname = member.name
                break
    # upload it in the vnfd_db 
    if (fname):         
         with open(fname) as vnfd_json:
             vnfd_json = load(vnfd_json)
             vnfd_record = {"vnfdId": vnfd_json["vnfdId"],
                            "vnfdVersion": vnfd_json["vnfdVersion"],
                            "vnfdName": vnfd_json["vnfProductName"],
                            "vnfdJson": vnfd_json}
         if vnfd_db.exists_vnfd(vnfd_json["vnfdId"], vnfd_json["vnfdVersion"]):
             vnfd_db.delete_vnfd_json(vnfd_json["vnfdId"])
         # then insert it again (creation or "update")
         vnfd_db.insert_vnfd(vnfd_record)
         # upload the descriptor in the MANO platform
         soe.onboard_vnfd_mano(vnfd_json)
         # create the answer
         info = {"onboardedVnfPkgInfoId": vnfd_record["vnfdId"],
                 "vnfId": vnfd_record["vnfdId"]}
    # remove the tar package and the json file
    os.remove(filename)
    os.remove(fname) 
    return info

def onboard_appd(body):
    """
    Function to onboard the APPD, including the downloading from the url specified in the input.
    Parameters
    ----------
    body: dict
        IFA013 request to onboard an appd.
    Returns
    -------
    info: dict
        Dictionary with the IFA013 answer to the appd onboarding process
    """
    log_queue.put(["INFO", "app_package_path: %s"% body.app_package_path])
    filename=wget.download(body.app_package_path)
    tf=tarfile.open(filename)
    tf.extractall()
    with tf as _tar:
        for member in _tar:
            if member.isdir():
                continue
            print (member.name)
            if member.name.find("json"):
                fname = member.name
                break
    # upload it in the vnfd_db 
    if (fname):         
         with open(fname) as appd_json:
             appd_json = load(appd_json)
             appd_record = {"appdId": appd_json["appDId"],
                            "appdVersion": appd_json["appDVersion"],
                            "appdName": appd_json["appName"],
                            "appdJson": appd_json}
         if appd_db.exists_appd(appd_json["appDId"], appd_json["appDVersion"]):
             appd_db.delete_appd_json(appd_json["appDId"])
         # then insert it again (creation or "update")
         appd_db.insert_appd(appd_record)
         # create the answer
         info = {"onboardedAppPkgId": appd_record["appdId"],
                 "appDId": appd_record["appdId"]}
    # remove the tar package and the json file
    os.remove(filename)
    os.remove(fname) 
    return info

def onboard_pnfd(pnfd_json):
    """
    Function to onboard the PNFD contained in the input.
    Parameters
    ----------
    pnfd_json: dict
        IFA014 network service descriptor.
    Returns
    -------
    pnfdInfoId: string
        The identifier assigned in the db
    """
    pnfd_record = {"pnfdId": pnfd_json["pnfd"]["pnfdId"],
                  "pnfdVersion": pnfd_json["pnfd"]["version"],
                  "pnfdName": pnfd_json["pnfd"]["name"],
                  "pnfdJson": pnfd_json}
    if pnfd_db.exists_pnfd(pnfd_json["pnfd"]["pnfdId"], pnfd_json["pnfd"]["version"]):
        # it is an update, so remove previously the descriptor
        pnfd_db.delete_pnfd_json(pnfd_json["pnfd"]["pnfdId"])
    # then insert it again (creation or "update")    
    pnfd_db.insert_pnfd(pnfd_record)
    # upload the descriptor in the MANO platform...
    return pnfd_record["pnfdId"]
