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
This file implements the composite resource orchestrator engine
"""

# python imports
from http.client import HTTPConnection
from six.moves.configparser import RawConfigParser
from uuid import uuid4
from json import dumps, loads, load
import itertools
import sys
import copy
import netaddr


# project imports
from db.ns_db import ns_db
from db.nsd_db import nsd_db
from db.operation_db import operation_db
from db.nsir_db import nsir_db
from db.resources_db import resources_db
from sm.eenet import eenet
from nbi import log_queue
from sbi import sbi

fed_domain= {}
config = RawConfigParser()
config.read("../../sm/soe/federation.properties")
number_fed_domains= int(config.get("FEDERATION", "number"))
for i in range (1,number_fed_domains+1):
  domain = "Provider"+str(i)
  fed_domain[domain] = config.get("FEDERATION", domain)
ewbi_port=config.get("FEDERATION", "ewbi_port")
ewbi_path=config.get("FEDERATION", "ewbi_path")

#################################### CONNECTION VARIABLES #########################################################
headers = {'Content-Type': 'application/json',
           'Accept': 'application/json'}
timeout1 = 10
timeout2 = 300
############################################ AUX FUNCTIONS #########################################################

def purgue_nested_connections (nested_connections):
    """
    This function removes the nested connections that has nothing to connect
    Parameters
    ----------
    nested_connections: dict
        dict with the pairs to be established
    Returns
    -------
    nested_connections: dict
        dict with the final connections to be done
    """
    purgued_nested_connections = {}
    for key in nested_connections.keys():
        if nested_connections[key]['pairs']:
            purgued_nested_connections[key] = nested_connections[key]
    return purgued_nested_connections

def extract_info_vls_nsd (nsd_json, nested_connections_vls, renaming_networks):
    """
    This function extracts from the composite nsd json, the info of the required vls connecting different nested services
    Parameters
    ----------
    nsd_json: json
        NSD descriptor of the composite service
    nested_connections_vls: list
        each elem of the list is the name of the vl used to interconnect nested network services
    renaming_networks: dict
        dict containing how the internested links have to be renamed upon an initial instance
    Returns
    -------
    link_info: dict
        for each requested vl, it is needed the latency and the bandwidth
    """
    link_info = {}
    for vl in nested_connections_vls:
        link_info[vl]={}
        for link in nsd_json["virtualLinkDesc"]:
            if renaming_networks: #if there is something in the dict
                if ( (link["virtualLinkDescId"] in renaming_networks) and (renaming_networks[link["virtualLinkDescId"]] == vl) ) :
                    link_info[vl]["latency"] = link["virtualLinkDf"][0]["qos"]["latency"]
                    link_info[vl]["bw"] = link["virtualLinkDf"][0]["bitrateRequirements"]["root"]
            else:
                if (vl == link["virtualLinkDescId"]):
                    link_info[vl]["latency"] = link["virtualLinkDf"][0]["qos"]["latency"]
                    link_info[vl]["bw"] = link["virtualLinkDf"][0]["bitrateRequirements"]["root"]
    return link_info

def extract_info_vls_nsd_simple(nsd_json, vl_name):
    """
    This function extracts from the composite nsd json, the info of the required vls connecting different nested services
    Parameters
    ----------
    nsd_json: json
        NSD descriptor of the composite service
    vl_name: string
        name of the virtual link descriptor
    Returns
    -------
    link_info: dict
        for the requested vl, it is needed the latency and the bandwidth
    """
    link_info = {}
    for link in nsd_json["virtualLinkDesc"]:
        if (vl_name == link["virtualLinkDescId"]):
            link_info[vl_name] = {}
            link_info[vl_name]["latency"] = link["virtualLinkDf"][0]["qos"]["latency"]
            link_info[vl_name]["bw"] = link["virtualLinkDf"][0]["bitrateRequirements"]["root"]
    return link_info


def simple_lsa (info_links, resources, nested_connections):
    """
    This function performs a simple link selection strategy, takes the ll link that satisfies latency while requiring less bandwdith
    Parameters
    ----------
    info_links: dict
        for each of the required links, it has the information (bw, latency) coming from the NSD with respect to this link
    resources: dict
        resources directly asked to the MTP through the sbi
    Returns
    -------
    link_info: dict
        for each requested vl, it selects a logical link
    """
    # first associate the pop with the GW
    # then get the logical links with the selected gateways
    # select for these logical links the appropriate one: the one with the latency and the minimum bandwidth
    # represent the link
    gw_info = {}
    required_logical_links=[]
    # log_queue.put(["DEBUG", "In SIMPLELSA info links: %s"%info_links])
    for pop in resources["NfviPops"]:
        # this is a federated vim
        if "federatedVimId" in pop["nfviPopAttributes"]:
            if pop["nfviPopAttributes"]["federatedVimId"] not in gw_info:
                gw_info[pop["nfviPopAttributes"]["federatedVimId"]] = pop["nfviPopAttributes"]["networkConnectivityEndpoint"]
        else:     
            if pop["nfviPopAttributes"]["nfviPopId"] not in gw_info:
                gw_info[pop["nfviPopAttributes"]["nfviPopId"]] = pop["nfviPopAttributes"]["networkConnectivityEndpoint"]
    for connections in nested_connections:
        bw = info_links[connections]["bw"]
        latency = info_links[connections]["latency"]
        for pair in range(0, len(nested_connections[connections]["pairs"])):
            srcPop = nested_connections[connections]["pairs"][pair][0][1]
            dstPop = nested_connections[connections]["pairs"][pair][1][1]
            ll_links = []
            for ll in resources["logicalLinkInterNfviPops"]:               
                for aGw in gw_info[srcPop]:
                    for zGw in gw_info[dstPop]:
                        if ( (aGw["netGwIpAddress"] == ll["logicalLinks"]["srcGwIpAddress"]) and (zGw["netGwIpAddress"] == ll["logicalLinks"]["dstGwIpAddress"]) ):
                            if ( ( (ll["logicalLinks"]["networkQoS"]["linkDelayValue"] < int(latency)) and (ll["logicalLinks"]["availableBandwidth"] > int(bw)) ) or
                               ( (int(latency) == 0) and (ll["logicalLinks"]["availableBandwidth"] > int(bw)) ) ):
                                ll_links.append(ll["logicalLinks"]["logicalLinkId"])
            # select the one with the minimum bandwidth
            min_bw = 10000000
            for elem in ll_links:
                for ll in resources["logicalLinkInterNfviPops"]:
                    if (ll["logicalLinks"]["logicalLinkId"] == elem):
                        if (ll["logicalLinks"]["availableBandwidth"] < min_bw):
                            # in case of tie, select the link with the minimum available bw to fill it
                            min_bw = ll["logicalLinks"]["availableBandwidth"]
                            selected_ll = elem
                            delay = ll["logicalLinks"]["networkQoS"]["linkDelayValue"]
            link_attr = {}
            link_attr = {"srcIP": nested_connections[connections]["pairs"][pair][0][0], 
                         "dstIP": nested_connections[connections]["pairs"][pair][1][0],
                         "srcMac": nested_connections[connections]["pairs"][pair][0][2],
                         "dstMac": nested_connections[connections]["pairs"][pair][1][2],
                         "ll_id": selected_ll, 
                         "network_name": nested_connections[connections]["network"],
                         "bw": int(bw),
                         "latency": int(latency)}              
                         
            if "vlanId" in nested_connections[connections]:
                link_attr.update({"vlanId": nested_connections[connections]["vlanId"]})
            required_logical_links.append(link_attr)   

    return required_logical_links

def extract_vls_info_mtp(resources, selected_links):
    """
    This function creates the logical link requests to be passed to the eenet module
    Parameters
    ----------
    resources: dict
        the available resources extracted from MTP
    selected links: dict
        dictionary with the information provided by the link selection algorithm
    nsId: string
        identifier of the service to create the links
    Returns
    -------
    vls_info: dict
        return the information to be passed to the eenet module to establish the links
    """
    # vls_info will be a list of LL to be deployed where each LL is a json
    # according the input body that the mtp expects.
    vls_info = {"interNfviPopNetworkType": "L2-VPN",
                "networkLayer": "VLAN",
                "logicalLinkPathList": [],
                "metaData": []
               }
    for ll in selected_links:
        llId = ll["ll_id"]
        ll_info = { "logicalLinkAttributes": {
                        "dstGwIpAddress": "",
                        "localLinkId": 0,
                        "logicalLinkId": "",
                        "remoteLinkId": 0,
                        "srcGwIpAddress": ""
                        },
                    "reqBandwidth": 0, #the following three elements, changed
                    "reqLatency": 0,
                    "metaData": []
                       }
        ll_info["metaData"] = [{"key": "srcVnfIpAddress", "value": ll["srcIP"]}, 
                               {"key": "dstVnfIpAddress", "value": ll["dstIP"]},
                               {"key": "srcVnfMacAddress", "value": ll["srcMac"]},
                               {"key": "dstVnfMacAddress", "value": ll["dstMac"]},  
                               {"key": "networkName", "value": ll["network_name"]}]
        if "vlanId" in ll:
            ll_info["metaData"].append({"key": "vlanId", "value": str(ll["vlanId"])})
        ll_info["reqBandwidth"] = ll["bw"]
        ll_info["reqLatency"] = ll["latency"]
        for ll_res in resources["logicalLinkInterNfviPops"]:
            if (ll_res["logicalLinks"]["logicalLinkId"] == llId):
                ll_info["logicalLinkAttributes"]["dstGwIpAddress"] = ll_res["logicalLinks"]["dstGwIpAddress"]
                ll_info["logicalLinkAttributes"]["srcGwIpAddress"] = ll_res["logicalLinks"]["srcGwIpAddress"]
                ll_info["logicalLinkAttributes"]["remoteLinkId"] = ll_res["logicalLinks"]["remoteLinkId"]
                ll_info["logicalLinkAttributes"]["localLinkId"] = ll_res["logicalLinks"]["localLinkId"]
                ll_info["logicalLinkAttributes"]["logicalLinkId"] = llId
        vls_info["logicalLinkPathList"].append(ll_info)
    return vls_info

###################### E/WBI API functions ########################################################################

def get_federated_network_info_request(nsId, nsdId, domain, ewbi_port, ewbi_path):
    """
    This function generates the requests towards the local domain to get information how local parts of a federated domain have been created. 
    In particular, CIDR information and used pools of IP addresses
    Parameters
    ----------
    nsId: string
        Identifier of the network service in the local domain
    nsdId: string
        Identifier of the descriptor of the nested service in the federated domain
    domain: string
        IP address of the local domain
    ewbi_port: string
        ewbi port number
    ewbi_path: string
        base path to make queries to the ewbi
    Returns
    -------
    networkInfo: dict
        return the information about used pools and IP addresses for the internested services
    """
    #save the network mapping because we are asking a consumer the mapping
    ewbi_uri = "http://" + domain + ":" + ewbi_port + ewbi_path + nsId + "/federated-network-info"
    ewbi_body = {"nsdId": nsdId}
    try:
        conn = HTTPConnection(domain, ewbi_port)
        conn.request("PUT", ewbi_uri, dumps(ewbi_body), headers)
        # ask pa to calculate the placement - read response and close connection
        conn.sock.settimeout(timeout1)
        rsp = conn.getresponse()
        networkInfo = rsp.read().decode('utf-8')
        networkInfo = loads(networkInfo)
        conn.close()
    except ConnectionRefusedError:
        # the PA server is not running or the connection configuration is wrong
        log_queue.put(["ERROR", "the EWBI server of the federated domain is not running or the connection configuration is wrong"])
    return networkInfo

def get_federated_network_info_reply(nsId, nsdId, domain):
    """
    This function returns information about how local parts of a federated domain have been created.
    In particular, CIDR information and used pools of IP addresses
    Parameters
    ----------
    nsId: string
        Identifier of the network service in the local domain
    nsdId: string
        Identifier of the descriptor of the nested service in the federated domain
    domain: string
        IP address of the federated domain
    Returns
    -------
    networkInfo: dict
        return the information about used pools and IP addresses for the internested services
    """
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE starts replying to get_federated_network_info" % (nsId)])
    networkInfo = {}
    # first check, check if the nsdId request coincides with the domain of the descriptor
    nested_domain_json = nsd_db.get_nsd_domain(nsdId)
    found = 0
    for key in nested_domain_json.keys():
        if (nested_domain_json[key] == domain):
            found = 1
    if not found:
        return 404
    # second, check if the nsdId is in the network mapping, otherwise, it means that there is no need
    # of internested connections
    network_mapping = nsir_db.get_network_mapping(nsId)
    if not nsdId in network_mapping["nestedVirtualLinkConnectivity"]:
        return 404
    networks_to_track = []
    networkInfo["cidr"] = {}
    networkInfo["addressPool"] = {}
    network_mapping = network_mapping["nestedVirtualLinkConnectivity"][nsdId] 
    for elem in network_mapping:
         key = next(iter(elem))
         # log_queue.put(["DEBUG", "network is: %s"%key])
         networkInfo["cidr"][key] = ""
         networkInfo["addressPool"][key] = [] 
    # third get the info from the registry: two sources a) own nested already instantiated or 
    # b) the reference to other element previously instantiated
    # 1) source a)
    for nested in ns_db.get_nested_service_info(nsId):
        if (nested["nested_id"] != nsdId): # in theory it shoudn't happen
            if (nested["domain"] == "local"):
                # check the registry to look for cidrs and pools
                nested_instance_record = nsir_db.get_vim_networks_info(nsId + '_' + nested["nested_id"])
                # get cidrs
                for network in nested_instance_record['cidr']:
                    for elem in network_mapping:
                        key = next(iter(elem))
                        if (network.find(elem[key]) !=-1):            
                            # I need to register the cidr and the addressPool
                            networkInfo["cidr"][key] = nested_instance_record['cidr'][network]
                            networkInfo["addressPool"][key] = networkInfo["addressPool"][key] + nested_instance_record["addressPool"][network]
            else: 
                # this info comes from a nested federated service before you
                # the registry is not coming from the nsir_db but from the ns_db, and you are insterested in the addressPool
                for network in nested["federatedInstanceInfo"]["instanceInfo"]["addressPool"]:
                    # no need to look for CIDR since this has to be in the local nested because the consumer domain
                    # controls the process
                    networkInfo["addressPool"][key] = networkInfo["addressPool"][key] + nested["federatedInstanceInfo"]["instanceInfo"]["addressPool"][network] 
    # 2) source b)
    reference_ns = ns_db.get_ns_nested_services_ids(nsId)
    if reference_ns:
        # is not going to be the same nsdId...
        reference_instance_record = nsir_db.get_vim_networks_info(reference_ns)
        # get cidrs
        for network in reference_instance_record['cidr']:
            for elem in network_mapping:
                key = next(iter(elem))
                if (network.find(elem[key]) !=-1):            
                    # I need to register the cidr and the addressPool
                    networkInfo["cidr"][key] = reference_instance_record['cidr'][network]
                    networkInfo["addressPool"][key] = networkInfo["addressPool"][key] + reference_instance_record["addressPool"][network]
    log_queue.put(["INFO", "CROOE returns networkInfo through EWBI for nsId: %s and info: %s"%(nsId, networkInfo)])
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE finishes replying to get_federated_network_info"%(nsId)])
    return networkInfo

def get_federated_network_instance_info_request(nsId, nsdId, domain, ewbi_port, ewbi_path):
    """
    This function returns information about how the requested federated service has been instantiated. In particular
    IP's and VLAN's are relevant
    Parameters
    ----------
    nsId: string
        Identifier of the nested network service in the federated domain
    nsdId: string
        Identifier of the descriptor of the nested service in the federated domain
    domain: string
        IP address of the federated domain
    ewbi_port: string
        ewbi port number
    ewbi_path: string
        base path to make queries to the ewbi
    Returns
    -------
    InstanceInfo: dict
        return the information about used pools and IP addresses for the internested services
    """
    ewbi_uri = "http://" + domain + ":" + ewbi_port + ewbi_path + nsId + "/federated-instance-info"
    ewbi_body = {"nsdId": nsdId}
    try:
        conn = HTTPConnection(domain, ewbi_port)
        conn.request("PUT", ewbi_uri, dumps(ewbi_body), headers)
        # ask pa to calculate the placement - read response and close connection
        conn.sock.settimeout(timeout1)
        rsp = conn.getresponse()
        instanceInfo = rsp.read().decode('utf-8')
        instanceInfo = loads(instanceInfo)
        conn.close()
    except ConnectionRefusedError:
        # the EWBI server is not running or the connection configuration is wrong
        log_queue.put(["ERROR", "the EWBI server of the federated domain is not running or the connection configuration is wrong"])
    return instanceInfo


def get_federated_network_instance_info_reply(nsId, nsdId, domain):
    """
    This function returns information about how the requested federated service has been instantiated. In particular
    IP's and VLAN's are relevant
    Parameters
    ----------
    nsId: string
        Identifier of the nested network service in the federated domain
    nsdId: string
        Identifier of the descriptor of the nested service in the federated domain
    domain: string
        IP address of the local domain
    Returns
    -------
    InstanceInfo: dict
        return the information about used pools and IP addresses for the internested services
    """
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE starts replying to get_federated_network_instance_info" %(nsId)])
    instanceInfo = {"ip":{}, "vlan":{}, "addressPool":{}}
    # first check that the nsId is referring to a nsdId like the one received
    nsdId = ns_db.get_nsdId(nsId)
    if not nsdId == nsdId:
        return 404
    # second check that the nsId has been invoked by the received domain
    requester_domain = ns_db.get_ns_requester(nsId)
    if not requester_domain == domain:
        return 404
    network_mapping = ns_db.get_ns_federation_info(nsId)
    # network mapping in a federated domain will only contain info about how nested networks maps to composite network
    network_info = nsir_db.get_vim_networks_info(nsId)
    vnf_info = nsir_db.get_vnf_deployed_info(nsId)
    for elem in network_mapping:
        key = next(iter(elem))
        instanceInfo["ip"][key] = []
        instanceInfo["vlan"][key] = ""
        instanceInfo["addressPool"][key] = []
        for network in network_info['cidr']:
            if (network.find(key) !=-1):
                #we have to look for all the IP's in this network
                instanceInfo["vlan"][key] = network_info['vlan_id'][network]
                instanceInfo["addressPool"][key] = network_info['addressPool'][network]
                for vnf in range(0, len(vnf_info)):
                    for port in vnf_info[vnf]['port_info']:
                    # log_queue.put(["DEBUG", "PORT: %s"%port])
                        if netaddr.IPAddress(port["ip_address"]) in netaddr.IPNetwork(network_info['cidr'][network]):
                            instanceInfo["ip"][key].append([port["ip_address"], port["mac_address"]])
    log_queue.put(["INFO", "CROOE returns instanceInfo through EWBI for nsId: %s and info: %s"%(nsId, instanceInfo)])
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE finishes replying to get_federated_network_instance_info" % (nsId)])
    return instanceInfo


def set_federated_internested_connections_request(nsId, nsdId, connected_vnfs, link_characteristics, domain, ewbi_port, ewbi_path):
    """
    This function asks the federated domain to make connections from the federated domain to the local one
    Parameters
    ----------
    nsId: string
        Identifier of the nested network service in the federated domain
    nsdId: string
        Identifier of the descriptor of the nested service in the federated domain
    connected_vnfs: dict
        dict with array containing the IP, MAC pairs of vnf's that need to be connected, in the form [IPlocal, IPfa] or [IPfb, IPfa],
        where IPfa is an IP of a VNF residing at domain
    link_characteristics: dict
        dict containing the characteristics (bw/latency) of the internested links
    domain: string
        IP address of the federated domain
    Returns
    -------
    OK
        return the information about used pools and IP addresses for the internested services
    """
    ewbi_uri = "http://" + domain + ":" + ewbi_port + ewbi_path + nsId + "/federated-internested-connections"
    for key in connected_vnfs.keys():
        connected_vnfs[key] = dumps(connected_vnfs[key])
        link_characteristics[key] = dumps(link_characteristics[key])
    ewbi_body = {"nsdId": nsdId, "connectedVNFs": connected_vnfs, "linkChar": link_characteristics}
    # log_queue.put(["DEBUG", "We ask to the provider: %s"% (dumps(ewbi_body, indent=4))])
    try:
        conn = HTTPConnection(domain, ewbi_port)
        conn.request("POST", ewbi_uri, dumps(ewbi_body), headers)
        # ask pa to calculate the placement - read response and close connection
        conn.sock.settimeout(timeout2)
        rsp = conn.getresponse()
        pathInfo = rsp.read().decode('utf-8')
        pathInfo = loads(pathInfo)
        conn.close()
    except ConnectionRefusedError:
        # the EWBI server is not running or the connection configuration is wrong
        log_queue.put(["ERROR", "the EWBI server of the federated domain is not running or the connection configuration is wrong"])
    return pathInfo['pathInfo']

def determine_nested_connections_federated_reply(nsId, conn_vnfs, link_char, domain):
    connected_vnfs = {}
    nested_connections = {}
    link_characteristics = {}
    for key in conn_vnfs.keys():
        connected_vnfs[key]= loads(conn_vnfs[key])
        link_characteristics[key]= loads(link_char[key])
        nested_connections[key] = {}
        nested_connections[key]['pairs'] = []
        nested_connections[key]['network'] = ""
    vnf_info = nsir_db.get_vnf_deployed_info(nsId)
    network_info = nsir_db.get_vim_networks_info(nsId)
    for key in fed_domain.keys():
        # log_queue.put(["DEBUG", "In CROOE DOMAIN la key es: %s "% (key)])
        if (fed_domain[key] == domain): 
            domain = key
    # log_queue.put(["DEBUG", "In CROOE DOMAIN is: %s "% (domain)])
    for key in connected_vnfs.keys():
        for elem in connected_vnfs[key]:
            elem_l = [elem[0][0], domain, elem[0][1]]
            elem_f = []
            for vnf in vnf_info:
                for port in vnf['port_info']:
                    if (port["ip_address"] == elem[1][0]):
                        elem_f = [port["ip_address"], vnf["dc"], port["mac_address"]]
                        for network in network_info['cidr'].keys():
                            if netaddr.IPAddress(port["ip_address"]) in netaddr.IPNetwork(network_info['cidr'][network]):
                                nested_connections[key]["network"] = network
                        break
                if elem_f:
                    break
            nested_connections[key]['pairs'].append([elem_f, elem_l])
    # log_queue.put(["DEBUG", "In CROOE nested_connections: %s "% dumps(nested_connections, indent=4)])
    # log_queue.put(["DEBUG", "In CROOE nested_connections: %s "% dumps(link_characteristics, indent=4)])
    return [nested_connections, link_characteristics]

def set_federated_internested_connections(nsId, nested_connections, link_characteristics, flag=None):
    resources_federated = sbi.get_mtp_federated_resources()
    resources_local = sbi.get_mtp_resources() 
    total_resources = copy.deepcopy(resources_local)
    for pops in resources_federated["NfviPops"]:
        total_resources["NfviPops"].append(pops)
    for ll in resources_federated["logicalLinkInterNfviPops"]:
        total_resources["logicalLinkInterNfviPops"].append(ll)
    # create connections like variable nested_connections
    # determinate the provider domain

    selected_links = simple_lsa (link_characteristics, total_resources, nested_connections)
    vls_info = extract_vls_info_mtp(total_resources, selected_links)
    if (flag == "update"):
        eenet.update_vls(nsId, vls_info, [])
    else:
        eenet.deploy_vls(vls_info, nsId)

def set_federated_internested_connections_reply(nsId, body, domain):
    """
    This function returns OK when internested links from the federated domain to the consumer domain
    have been established
    Parameters
    ----------
    nsId: string
        Identifier of the nested network service in the federated domain
    body: dict
        Dictionary with the descriptor that we are using, with the pairs to connect and with the characteristics of the internested links
    domain: string
        IP address of the local domain
    Returns
    -------
    InstanceInfo: dict
        return the information about used pools and IP addresses for the internested services
    """
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE starts stablishing connections form the provider to the consumer domain" %(nsId)])
    # first check that the nsId is referring to a nsdId like the one received
    nsdId = ns_db.get_nsdId(nsId)
    if not nsdId == nsdId:
        return 404
    # second reconstruct the incoming datam ask for mtp federated resources and reformat it to pass to the appropriate functions
    connected_vnfs = {}
    link_characteristics = {}
    nested_connections = {}
    [nested_connections, link_characteristics] = determine_nested_connections_federated_reply (nsId, body.connected_vn_fs, body.link_char, domain)
    set_federated_internested_connections(nsId, nested_connections, link_characteristics)
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE finishes stablishing connections from the provider to the consumer domain" %(nsId)])
    return "OK"

def update_federated_internested_connections_request(nsId, nsdId, connected_vnfs_add, connected_vnfs_remove, link_characteristics, domain, ewbi_port, ewbi_path): 

    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE starts updating connections from the provider to the consumer domain" % (nsId)])
    ewbi_uri = "http://" + domain + ":" + ewbi_port + ewbi_path + nsId + "/federated-internested-connections"
    for key in connected_vnfs_add.keys():
        # we assume that we have the same keys for the elements to add and the link characteristics
        connected_vnfs_add[key] = dumps(connected_vnfs_add[key])
        link_characteristics[key] = dumps(link_characteristics[key])
    for key in connected_vnfs_remove.keys():
        connected_vnfs_remove[key] = dumps(connected_vnfs_remove[key])

    ewbi_body = {"nsdId": nsdId, "connectedVNFs_add": connected_vnfs_add, "connectedVNFs_del": connected_vnfs_remove,"linkChar": link_characteristics}
    try:
        conn = HTTPConnection(domain, ewbi_port)
        conn.request("PUT", ewbi_uri, dumps(ewbi_body), headers)
        # ask pa to calculate the placement - read response and close connection
        conn.sock.settimeout(timeout2)
        rsp = conn.getresponse()
        pathInfo = rsp.read().decode('utf-8')
        pathInfo = loads(pathInfo)
        conn.close()
    except ConnectionRefusedError:
        # the EWBI server is not running or the connection configuration is wrong
        log_queue.put(["ERROR", "the EWBI server of the federated domain is not running or the connection configuration is wrong"])
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE starts updated connections from the provider to the consumer domain"% (nsId)])
    return pathInfo['updatedPathInfo']

def update_federated_internested_connections_reply(nsId, body, domain):
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE starts updating SCALED connections from the provider to the consumer domain" % (nsId)])
    # first check that the nsId is referring to a nsdId like the one received
    nsdId = ns_db.get_nsdId(nsId)
    if not nsdId == nsdId:
        return 404
    # second reconstruct the incoming datam ask for mtp federated resources and reformat it to pass to the appropriate functions
    connected_vnfs = {}
    link_characteristics = {}
    nested_connections = {}
    #maybe better remove first and then add
    if body.connected_vn_fs_del:
      # *--* we need to do so!! go through the vl to check the one we need to remove
      # first, we need to do a loads
      connected_vnfs_del = {}
      for key in body.connected_vn_fs_del.keys():
          connected_vnfs_del[key]= loads(body.connected_vn_fs_del[key])
      deleting_connections(nsId, connected_vnfs_del)
      log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE update (removed) SCALED connections from the provider to the consumer domain"% (nsId)])
    if body.connected_vn_fs_add:
        [nested_connections, link_characteristics] = determine_nested_connections_federated_reply (nsId, body.connected_vn_fs_add, body.link_char, domain) 
        # be careful with this denomination of the body.connected_vn_fs_add variable
        set_federated_internested_connections(nsId, nested_connections, link_characteristics, "update")
        log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE update (created) SCALED connections from the provider to the consumer domain"% (nsId)])
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE finishes stablishing SCALING connections from the provider to the consumer domain"% (nsId)])
    return "OK"


############################################ CORE FUNCTIONS ########################################################

def mapping_composite_saps_to_nested_saps(nsId, composite_nsd_json):
    """
    This function extracts from the composite nsd json, how different nested services are connected among them
    Parameters
    ----------
    nsId: string
        Identifier of the service
    composite_nsd_json: dict
        Network service descriptor of the composite NS
    Returns
    -------
    sap_mapping: dict
        dictionary with the sap mapping between composite and nesteds
    """
    sap_mapping = {}
    sap_composite = {}
    network_mapping = nsir_db.get_network_mapping(nsId)
    renaming_network = nsir_db.get_renaming_network_mapping(nsId)
    for sap in composite_nsd_json["nsd"]["sapd"]:
        if (sap["addressData"][0]["floatingIpActivated"] == True):
            sap_composite[sap["cpdId"]] = sap["nsVirtualLinkDescId"]
            sap_mapping[sap["cpdId"]] = {}
            sap_mapping[sap["cpdId"]]["info"] = sap
    for key in sap_composite.keys():
        sap_mapping[key]["nested"] = {}
        for nested in composite_nsd_json["nsd"]["nestedNsdId"]:
            nested_json = nsd_db.get_nsd_json(nested)
            for sap in nested_json["nsd"]["sapd"]:
                if (sap["addressData"][0]["floatingIpActivated"] == True):
                    link_nested = sap["nsVirtualLinkDescId"]
                    for elem in network_mapping["nestedVirtualLinkConnectivity"][nested]:
                        elem_key = next(iter(elem))
                        if (elem_key == link_nested): #data_ehealth_mon_be_vl
                            if renaming_network:
                                for key2 in renaming_network.keys():
                                    if renaming_network[key2] == elem[elem_key]:
                                        comparison_variable = key2
                            else:
                                comparison_variable = elem[elem_key]
                            log_queue.put(["DEBUG", "comparison_variable: %s"%comparison_variable])
                            if ( sap_composite[key] == comparison_variable):
                                sap_mapping[key]["nested"][nested] = []
                                sap_mapping[key]["nested"][nested].append(sap["cpdId"])
    return sap_mapping

def mapping_composite_networks_to_nested_networks(nsId, composite_nsd_json, body, nested_instance):
    """
    This function extracts from the composite nsd json, how different nested services are connected among them
    Parameters
    ----------
    nsId: string
        Identifier of the service
    composite_nsd_json: dict
        Network service descriptor of the composite NS
    body: struct
        instantiation request received at the NBI
    nested_instance: dict
        dictionary having as key the type of service and its associated instance number       
    Returns
    -------
    mapping: dict
        dictionary with the network mapping between composite and nested services 
    renaming_networks: dict
        dictionary with the renaming of networks between composite and nested services due to a referenced service
    """
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE analysing composite NSD"% (nsId)])
    mapping = {}
    map_tmp = {}
    flavourId = body.flavour_id
    nsLevelId = body.ns_instantiation_level_id
    nsd_json = composite_nsd_json["nsd"]
    mapping["nsId"] = nsId
    mapping["nsdId"] = nsd_json["nsdIdentifier"]
    for df in nsd_json["nsDf"]:
        if (df["nsDfId"] == flavourId):
            for il in df["nsInstantiationLevel"]:
                if (il["nsLevelId"] == nsLevelId):
                    #here we have to distinguish between composite NSD and single NSD
                    for nsProfile in il["nsToLevelMapping"]:
                        nsp = nsProfile["nsProfileId"]
                        for nsprof in df["nsProfile"]:
                            if ( (nsprof["nsProfileId"] == nsp) and (nsprof["nsdId"] in nsd_json["nestedNsdId"]) ):
                                if nsprof["nsdId"] not in map_tmp:
                                    map_tmp[nsprof["nsdId"]] = {}
                                vlprofile_tmp = None
                                for link in nsprof["nsVirtualLinkConnectivity"]:
                                    for vlprofile in df["virtualLinkProfile"]:
                                        if (vlprofile["virtualLinkProfileId"] == link["virtualLinkProfileId"]):
                                            vlprofile_tmp = vlprofile["virtualLinkDescId"]
                                            if vlprofile["virtualLinkDescId"] not in map_tmp[nsprof["nsdId"]]:
                                                map_tmp[nsprof["nsdId"]][vlprofile["virtualLinkDescId"]] = []
                                            break
                                    if (vlprofile_tmp != None):
                                        for cpdId in link["cpdId"]:
                                            map_tmp[nsprof["nsdId"]][vlprofile_tmp].append(cpdId)
    map_tmp2 = {}
    for nested in map_tmp:
        map_tmp2[nested] = []
        nested_json = nsd_db.get_nsd_json(nested)
        for link in map_tmp[nested]:
            for nested_sap in map_tmp[nested][link]:
                for sap in nested_json["nsd"]["sapd"]:
                    if (sap["cpdId"] == nested_sap):
                        map_tmp2[nested].append({sap["nsVirtualLinkDescId"]: link})

    renaming_networks = {}
    if (body.nested_ns_instance_id):
        for key in nested_instance.keys():
            if key in map_tmp2:
                #the service is part of the composite
                network_info = nsir_db.get_vim_networks_info(nested_instance[key])
                for elem in map_tmp2[key]:
                    net = next(iter(elem))
                    for name in network_info["cidr"]:
                        if (name.find(net) !=-1):
                            if net not in renaming_networks:
                                renaming_networks[elem[net]] = name
        
        for key in map_tmp2:
            for elem in map_tmp2[key]:
                net = next(iter(elem))
                if elem[net] in renaming_networks:
                    elem[net] = renaming_networks[elem[net]]
        mapping['nestedVirtualLinkConnectivity'] = map_tmp2       
    else:
        mapping['nestedVirtualLinkConnectivity'] = map_tmp2
    #save network mapping in nsir_db
    nsir_db.set_network_mapping(mapping, nsId)
    if renaming_networks:
        nsir_db.set_network_renaming_mapping(renaming_networks,nsId)
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE finishing analysing composite NSD" % (nsId)])
    return [mapping, renaming_networks]

# Composite NFV-NS scaling: decoupling the "connecting_nested_local_services" function in two

def determine_nested_local_pairs(nsId, network_mapping, local_services, nested_ns_instance, renaming_networks):
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE starting determining interconnected nested local services"% (nsId)])
    nested_network = {}
    network_info = {}
    vnf_info = {}
    
    for local_nested_service in local_services:
        network_info[local_nested_service["nsd"]] = nsir_db.get_vim_networks_info(nsId + '_' + local_nested_service["nsd"])
        vnf_info[local_nested_service["nsd"]] = nsir_db.get_vnf_deployed_info(nsId + '_' + local_nested_service["nsd"])
    local_services_tmp = copy.deepcopy(local_services)
    for key in nested_ns_instance:
        network_info[key] = nsir_db.get_vim_networks_info(nested_ns_instance[key])
        vnf_info[key] = nsir_db.get_vnf_deployed_info(nested_ns_instance[key])
        local_services_tmp.append({"nsd":key, "domain": "local"})

    for nested_service in network_mapping['nestedVirtualLinkConnectivity']:
        log_queue.put(["DEBUG", "nested service in CROOE: %s"%nested_service])
        nested_id = nested_service
        for local_nested_service in local_services_tmp:
            if (local_nested_service["nsd"] == nested_service):
                for vl in network_mapping['nestedVirtualLinkConnectivity'][nested_service]:
                    for key in vl.keys():
                        #here for the case of the reference, I think, we will have to do something to remove the dash
                        if vl[key] not in nested_network:
                            nested_network[vl[key]] = {}
                            nested_network[vl[key]]['services'] = {}
                        if nested_service not in nested_network[vl[key]]['services']:
                            nested_network[vl[key]]['services'][nested_service] = []

    for key in nested_network.keys():
        for key2 in nested_network[key]['services'].keys():
            for elem in network_info[key2]['name'].keys():
                if (elem.find(key) !=-1 and (elem in network_info[key2]['cidr'])):
                    cidr = network_info[key2]['cidr'][elem]
                    nested_network[key]['cidr'] = cidr
                    nested_network[key]['name'] = elem
                    break
    # we need to make another time the loop because it is possible that you do not get the cidr because it is not in the info
    # log_queue.put(["DEBUG", "NESTED network 2: %s"% nested_network])
    for key in nested_network.keys():
        for key2 in nested_network[key]['services'].keys():
            for vnf in range(0, len(vnf_info[key2])):
                # log_queue.put(["DEBUG", "VNF: %s"%vnf_info[key2][vnf]])
                for port in vnf_info[key2][vnf]['port_info']:
                    # log_queue.put(["DEBUG", "PORT: %s"%port])
                    if netaddr.IPAddress(port["ip_address"]) in netaddr.IPNetwork(nested_network[key]['cidr']):
                        nested_network[key]['services'][key2].append({vnf_info[key2][vnf]['name']: [port['ip_address'], vnf_info[key2][vnf]['dc'], port['mac_address']]})

    # now that we have the info, we need to create the pairs of vnf's between services connecting, 
    # we have to check also that they are placed in different pop
    nested_connections = {}
    for vl in nested_network.keys():
        if vl not in nested_connections:
            nested_connections[vl] = {}
            nested_connections[vl]['network'] = nested_network[vl]["name"]
            nested_connections[vl]['pairs'] = []
        nested_keys = nested_network[vl]['services'].keys()
        endpoints = list(itertools.combinations(nested_keys, 2))
        for pair in endpoints:
            for elemA in nested_network[vl]['services'][pair[0]]:
                for vnfA in elemA.keys():
                    for elemB in nested_network[vl]['services'][pair[1]]:
                        for vnfB in elemB.keys():
                            if (elemA[vnfA][1] != elemB[vnfB][1]):
                                nested_connections[vl]['pairs'].append([elemA[vnfA], elemB[vnfB]])
    # we only continue if 'pairs' of nested_connections has something to connect, otherwise we have finished
    nested_connections = purgue_nested_connections(nested_connections)
    log_queue.put(["INFO", "Nested connections between local nested NSs determined by CROOE: %s"%nested_connections])
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE finishing determining interconnected nested local services" %(nsId)])
    return nested_connections

def interconnecting_nested_local_pairs(nsId, nested_connections, nsd_json, renaming_networks, flag=None):
    resources = sbi.get_mtp_resources()
    info_links = extract_info_vls_nsd(nsd_json, nested_connections.keys(), renaming_networks)
    selected_links = simple_lsa (info_links, resources, nested_connections)
    vls_info = extract_vls_info_mtp(resources, selected_links)
    if flag == "update":
        log_queue.put(["DEBUG", "CROOE Updating internested local VLs after a scaling operation"])
        eenet.update_vls(nsId, vls_info, [])
    else:
        log_queue.put(["DEBUG", "CROOE setting up internested local VLs in instantiation operation"])
        eenet.deploy_vls(vls_info, nsId)
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE finished connecting nested local services" % (nsId)])

def update_connection_info(old_nested_local_connections, new_nested_local_connections):
# we have the initial local connections and the new, we need to identify the pairs both to be created and
# the pairs to be deleted. The output are two variables with the same structure of connections,
    connections_to_add={}
    connections_to_remove={}
    # we compare the new with the old, if there is an element in the new that it is not in the old -> create
    for vl_new in new_nested_local_connections.keys():
        if vl_new not in old_nested_local_connections.keys():
            # extreme case, complete new connections
            connections_to_add[vl_new] = new_nested_local_connections[vl_new]
        for vl_old in old_nested_local_connections.keys():
            if (vl_new == vl_old):
                new_connections = 0
                for pair_new in new_nested_local_connections[vl_new]['pairs']:
                    new_ip_addresses = [pair_new[0][0],pair_new[1][0]]
                    found = 0
                    for pair_old in old_nested_local_connections[vl_old]['pairs']:
                        old_ip_addresses= [pair_old[0][0],pair_old[1][0]]
                        if (new_ip_addresses[0] in old_ip_addresses and new_ip_addresses[1] in old_ip_addresses):
                            found = 1
                            break
                    if (found == 0):
                        if vl_new not in connections_to_add:
                            connections_to_add[vl_new] = {}
                            connections_to_add[vl_new]['pairs'] = []
                        connections_to_add[vl_new]['pairs'].append(pair_new)
                        new_connections = new_connections + 1
                if (new_connections > 0):
                    connections_to_add[vl_new]['network'] = new_nested_local_connections[vl_new]['network']
    log_queue.put(["DEBUG", "CROOE determining new connections to add for a nested after a scaling operation: %s"%dumps(connections_to_add)])
    # we compare the old with the new, if there is an element in the old that it is not in the new -> delete
    for vl_old in old_nested_local_connections.keys():
        if vl_old not in new_nested_local_connections.keys():
            # extreme case, complete new connections
            connections_to_remove[vl_old] = old_nested_local_connections[vl_old]
        for vl_new in new_nested_local_connections.keys():
            if (vl_old == vl_new):
                old_connections = 0
                for pair_old in old_nested_local_connections[vl_old]['pairs']:
                    old_ip_addresses = [pair_old[0][0],pair_old[1][0]]
                    found = 0
                    for pair_new in new_nested_local_connections[vl_new]['pairs']:
                        new_ip_addresses= [pair_new[0][0],pair_new[1][0]]
                        if (old_ip_addresses[0] in new_ip_addresses and old_ip_addresses[1] in new_ip_addresses):
                            found = 1
                            break
                    if (found == 0):
                        if vl_old not in connections_to_remove:
                            connections_to_remove[vl_old] = {}
                            connections_to_remove[vl_old]['pairs'] = []
                        connections_to_remove[vl_old]['pairs'].append(pair_old)
                        old_connections = old_connections + 1
                if (old_connections > 0):
                    connections_to_remove[vl_old]['network'] = old_nested_local_connections[vl_old]['network']     
    log_queue.put(["DEBUG", "CROOE determining old connections to be removed for a nested after a scaling operation: %s"% dumps(connections_to_remove)])
    return [connections_to_add, connections_to_remove]

def deleting_nested_local_connections(nsId, del_connections):
    # del_connections is a variable containing 
    current_vls = nsir_db.get_vls(nsId)
    # log_queue.put(["DEBUG", "deleting nested local connections: %s"%current_vls])
    # log_queue.put(["DEBUG", "deleting connections: %s"%del_connections])
    ids_to_remove = []
    # dummy variable for eenet.update_vls_method()
    vl_list = {}
    vl_list["logicalLinkPathList"] = []
    for vl in del_connections:
        for pair in del_connections[vl]["pairs"]:
            pair_ip_addresses = [pair[0][0],pair[1][0]]
            for ll in current_vls:
                key = next(iter(ll))
                vl_ip_addresses = []
                for data in ll[key]["metaData"]:
                    if (data["key"] == "srcVnfIpAddress" or data["key"] == "dstVnfIpAddress"):
                        vl_ip_addresses.append(data["value"])
                        if (len(vl_ip_addresses) == 2):
                            break
                if (pair_ip_addresses[0] in vl_ip_addresses and pair_ip_addresses[1] in vl_ip_addresses):
                    # it means this ll has to be removed
                    ids_to_remove.append(key)
    if (len(ids_to_remove)>0):
        eenet.update_vls(nsId, vl_list, ids_to_remove)


def connecting_nested_local_services(nsId, nsd_json, network_mapping, local_services, nested_ns_instance, renaming_networks):
    """
    This function recovers the info from the different local services of a composite service to interconnects those VNFs in different PoPs
    Parameters
    ----------
    nsId: string
        Identifier of the service
    nsd_json: json
        Json descriptor of the composite network service
    network_mapping: dict
        Dictionary on how the different nested network services are interconnected
    local_services: dict
        Dictionary with the list of nested services deployed locally
    nested_ns_instance: list of dicts
        each entry is of the type {nsd_name: instance_id}, references to other NS that are use to composite/federate
    renaming_networks: dict
        dict containing how the internested links have to be renamed upon an initial instance
    Returns
    -------
    """
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE starting connecting nested local services" % (nsId)])
    nested_connections = {}
    nested_connections = determine_nested_local_pairs(nsId, network_mapping, local_services, nested_ns_instance, renaming_networks)
    nsir_db.set_nested_local_connections(nested_connections, nsId)
    log_queue.put(["DEBUG", "Nested connections decoupled and determined"])
    if (nested_connections):
        interconnecting_nested_local_pairs(nsId, nested_connections, nsd_json["nsd"], renaming_networks)
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE finishing connecting nested local services" % (nsId)])

def update_connecting_nested_local_services(nsId, nsd_json, local_services, nested_ns_instance):

# nsId of the composite, nsd_json of the composite, local_il_nested has the info about localnested to be scaled, reference_il has the info about
# the reference in case the composite is using a il (asuming the reference is always local)
# we need network_mapping and renaming_networks
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE starting updating nested local services" % (nsId)])
    network_mapping = nsir_db.get_network_mapping(nsId)
    renaming_networks = nsir_db.get_renaming_network_mapping(nsId)
    old_nested_local_connections = nsir_db.get_nested_local_connections(nsId)
    log_queue.put(["DEBUG", "Old_connections CROOE SCALING: %s"%old_nested_local_connections])
    new_nested_local_connections = determine_nested_local_pairs(nsId, network_mapping, local_services, nested_ns_instance, renaming_networks)
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE determined new set of nested local connected VNFs" % (nsId)])
    log_queue.put(["DEBUG", "New_connections CROOE SCALING: %s"%new_nested_local_connections])
    [new_connections, del_connections] = update_connection_info(old_nested_local_connections, new_nested_local_connections)
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE finishing determining new_connections and connections to delete" % (nsId)])
    # maybe better first remove connections to gain resources for the new connections 
    if del_connections:
        #here I will use the update vls of eenet but with empty vl_list
        deleting_nested_local_connections(nsId, del_connections)
        log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE finishing deleting connections" % (nsId)])
    if new_connections:
        interconnecting_nested_local_pairs(nsId, new_connections, nsd_json["nsd"], renaming_networks, "update")
        log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE finishing creating new connections"% (nsId)])
        
    # update the local connections in the nsir_db entry
    nsir_db.set_nested_local_connections(new_nested_local_connections, nsId)
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE finishing updating nested local services" % (nsId)])

# Composite NFV-NS scaling: refactoring this function, to make it more modular and reuse for scaling purposes
def determine_federated_pairs(local_services, federated_services, nested_ns_instance):
    local_services_tmp = copy.deepcopy(local_services)
    for key in nested_ns_instance:
        # assuming that nested_ns_instance is always local
        local_services_tmp.append({"nsd":key, "domain": "local"})
    # 1) There are to kind of pairs to be created a) local-federated pairs and b) federated-federated
    # For the moment, only implemented a), b) option is when you have more than one federated domain and
    # you use the consumer/local domain to interconnect the federated domains between them
    pairs_a = []
    pairs_b = []
    for local in local_services_tmp:
        for federated in federated_services:
            pairs_a.append([local["nsd"], federated["nsd"]])
    for federated in federated_services:
        pairs_b.append(federated["nsd"])
    pairs_b = list(itertools.combinations(pairs_b, 2))
    return [pairs_a, pairs_b]

def determine_federated_local_connection_info(nsId, pairs_a, nested_ns_instance, network_mapping, renaming_networks):
    nested_connections_info_a = [] 
    for pair in pairs_a:
        nested_connections_info_tmp = {}
        nested_connections_info_tmp['pair'] = pair
        nested_connections_info_tmp['common_networks'] = []
        network_a = network_mapping["nestedVirtualLinkConnectivity"][pair[0]]
        network_b = network_mapping["nestedVirtualLinkConnectivity"][pair[1]]
        for elem_a in network_a:
            akey = next(iter(elem_a))
            # for the case of a reference
            if (elem_a[akey].find('fgt') !=-1):
                for key in renaming_networks.keys():
                    if (renaming_networks[key] == elem_a[akey]):
                        akey = key
                        break
            else:
                akey = elem_a[akey]
            for elem_b in network_b:
                bkey = next(iter(elem_b))
                if (elem_b[bkey].find('fgt') !=-1):
                    for key in renaming_networks.keys():
                        if (renaming_networks[key] == elem_b[bkey]):
                            bkey = key  
                            break
                else:
                    bkey = elem_b[bkey]
                if (akey == bkey):
                    nested_connections_info_tmp['common_networks'].append({akey:[next(iter(elem_a)),next(iter(elem_b))]})
        nested_connections_info_a.append(nested_connections_info_tmp)
    ns_composite_nested_record = ns_db.get_nested_service_info(nsId)
    for pair in nested_connections_info_a:
        for nested_service_f in ns_composite_nested_record:
            #pair[1] is the federated service
            if (pair['pair'][1] == nested_service_f['nested_id']):
                pair['ips']={}
                pair['vlan']={} 
                pair['nsId'] = []
                for key in nested_service_f["federatedInstanceInfo"]["instanceInfo"]["ip"].keys():
                    for key2 in pair['common_networks']:
                        key3 = next(iter(key2))
                        if key in key2[key3]:
                            pair['ips'][key3] = {}                        
                            pair['vlan'][key3] = {}
                            domain = next(iter(nested_service_f['domain']))
                            pair['ips'][key3][domain] = nested_service_f["federatedInstanceInfo"]["instanceInfo"]["ip"][key]
                            ip = nested_service_f["federatedInstanceInfo"]["instanceInfo"]["ip"][key][0][0]  #using /24 addresses, to change
                            cidr = netaddr.IPNetwork(ip).supernet(24)[0]
                            # now get the local IP's
                            nsId_bis = ""
                            for nested_service_l in ns_composite_nested_record:
                                if (pair['pair'][0] == nested_service_l['nested_id']):
                                    # it has been instantiated at the same time that the federated
                                    nsId_bis = nested_service_l["nested_instance_id"]
                                    break
                                if not nsId_bis:
                                    # it is coming from a reference nested_instance: {'eHealth-vEPC': 'fgt-698358f-43f4-4fd3-a537-c4cf3ccaf6b1'}
                                    nsId_bis= nested_ns_instance[pair['pair'][0]]
                            # the order is important
                            if ([nsId_bis,'local'] not in pair['nsId'] and [nested_service_f['nested_instance_id'],domain] not in pair['nsId']):
                                pair['nsId'].append([nsId_bis,'local'])
                                pair['nsId'].append([nested_service_f['nested_instance_id'],domain])
                            local_nsir_record_vnf = nsir_db.get_vnf_deployed_info(nsId_bis)
                            local_nsir_record_network = nsir_db.get_vim_networks_info(nsId_bis)
                            ip_list = []
                            for vnf in local_nsir_record_vnf:
                                for port in vnf['port_info']:
                                    if netaddr.IPAddress(port["ip_address"]) in netaddr.IPNetwork(cidr):
                                        ip_list.append([port["ip_address"], vnf["dc"], port["mac_address"]])
                            pair['ips'][key3]['local'] = ip_list
                            for network in local_nsir_record_network['cidr'].keys():
                                if (local_nsir_record_network['cidr'][network] == str(cidr)):
                                    pair['vlan'][key3]['local'] = local_nsir_record_network['vlan_id'][network]
                            pair['vlan'][key3][domain] = nested_service_f["federatedInstanceInfo"]["instanceInfo"]["vlan"][key]
    return nested_connections_info_a

def connect_federate_local_pairs(nsId, nsd_json, nested_connections_info_a, nested_ns_instance):
    for pair in nested_connections_info_a:
        # we connect local_nested- federation_nested basis operations
        connected_vnfs_f = {}
        connected_vnfs_l = {}
        link_characteristics = {}
        swap_vlan = {}
        for network in pair['ips'].keys():
            ip_list_f = []
            ip_list_l = []
            swap_vlan[network] = pair['vlan'][network][pair['nsId'][1][1]]
            link_info = extract_info_vls_nsd_simple(nsd_json["nsd"], network)
            link_characteristics.update(link_info)
            for ipl in pair['ips'][network][pair['nsId'][0][1]]:
                for ipf in pair['ips'][network][pair['nsId'][1][1]]:
                    ip_list_f.append([[ipl[0],ipl[2]],ipf])
                    ip_list_l.append([ipl,[ipf[0],pair['nsId'][1][1],ipf[1]]])
            connected_vnfs_f[network] = ip_list_f
            connected_vnfs_l[network] = ip_list_l
        # make connections at the federated domain 
        link_chars_tmp = copy.deepcopy(link_characteristics)
        log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE starts requesting connections from provider to consumer for pair %s" % (nsId, index)])
        result = set_federated_internested_connections_request(pair['nsId'][1][0], pair['pair'][1], connected_vnfs_f, 
                                                      link_chars_tmp, fed_domain[pair['nsId'][1][1]], ewbi_port, ewbi_path)
        log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE finished requesting connections from provider to consumer for pair %s" % (nsId, index)])
        if (result == "OK"):
            # it means that the paths have been established in the federated domain, now let's 
            # make the connections at the local domain
            # towards the federated one, with the vlan swapping
            # It is passed, the globla nsId, the local nsId in the provider domain, how vnf's connect, the characterisitic of the link and the vlan  
            log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE starts requesting connections from consumer to provider for pair %s" % (nsId, index)])                 
            set_federated_internested_connections_local(nsId, pair['pair'][0], connected_vnfs_l, link_characteristics, pair['nsId'][1][1], swap_vlan, nested_ns_instance)
            log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE finish requesting connections from consumer to provider" % (nsId, index)]) 
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE finished connecting nested local with federated services" % (nsId)])        
    return

def connecting_nested_federated_local_services(nsId, nsd_json, network_mapping, local_services, federated_services, nested_ns_instance, renaming_networks):
    """
    This function recovers the info from the different nested services of a composite service to interconnects those VNFs in different domains
    Parameters
    ----------
    nsId: string
        Identifier of the service
    nsd_json: json
        Json descriptor of the composite network service
    network_mapping: dict
        Dictionary on how the different nested network services are interconnected
    local_services: dict
        Dictionary with the list of nested services deployed locally
    federated_services: dict
        Dictionary with the list of nested services deployed in a federated domain
    nested_ns_instance: list of dicts
        each entry is of the type {nsd_name: instance_id}, references to other NS that are use to composite/federate
    renaming_networks: dict
         dict with a correspondence between internested network and previously instantiated service
    Returns
    -------
    """  
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE starting interconnecting nested local with federated services" % (nsId)])
    # 1) There are two kind of pairs to be created a) local-federated pairs and b) federated-federated
    # For the moment, only implemented a), b) option is when you have more than one federated domain and
    # you use the consumer/local domain to interconnect the federated domains between them
    pairs_a = []
    pairs_b = []
    [pairs_a, pairs_b] = determine_federated_pairs(local_services, federated_services, nested_ns_instance)
    # save them in ns_db
    ns_db.set_federated_pairs(nsId, pairs_a, pairs_b)
    # assuming that pairs_a are going to be present always
    nested_connections_info_a = []
    nested_connections_info_a = determine_federated_local_connection_info(nsId, pairs_a, nested_ns_instance, network_mapping, renaming_networks)
    # update the info in the db
    ns_db.set_nested_connections_local_federated(nsId, nested_connections_info_a)
    connect_federate_local_pairs(nsId, nsd_json, nested_connections_info_a, nested_ns_instance)
#    if (len(pairs_b)>0):
#        nested_connections_info_b = [] # case not treated now
#        nested_connections_info_b = determine_federated_federated_connection_info(nsId, pairs_b, network_mapping, renaming_networks) # case not treated now
#        connect_federate_federate_pairs(nsId, nsd_json, nested_connections_info_b, nested_ns_instance)
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE finishing interconnecting nested local with federated services" % (nsId)])
    return

def update_connecting_nested_federated_local_services(nsId, nsd_json, nested_ns_instance):
    # we assume that when scaling a service will not dissapear
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE starting updating connections between 1)federated-local, 2)local-federated" % (nsId)])
    network_mapping = nsir_db.get_network_mapping(nsId)
    renaming_networks = nsir_db.get_renaming_network_mapping(nsId)   
    pairs_a = []
    pairs_b = []
    [pairs_a, pairs_b] =  ns_db.get_federated_pairs(nsId)
    nested_connections_info_a = []
    nested_connections_info_a_old = ns_db.get_nested_connections_local_federated(nsId)
    nested_connections_info_a = determine_federated_local_connection_info(nsId, pairs_a, nested_ns_instance, network_mapping, renaming_networks)
    # update the info in the db
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE determined internested connections"% (nsId)])
    ns_db.set_nested_connections_local_federated(nsId, nested_connections_info_a)
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE saved new internested connections in DB"% (nsId)])
    update_connect_federate_local_pairs(nsId, nsd_json, nested_connections_info_a, nested_connections_info_a_old, nested_ns_instance)
#     if (len(pairs_b)>0): # case not treated now
#         nested_connections_info_b = []
#         nested_connections_info_b_old = ns_db.get_nested_connections_federated_federated(nsId)
#         nested_connections_info_b = determine_federated_federated_connection_info(nsId, pairs_b, network_mapping, renaming_networks) 
#         update_connect_federate_federate_pairs(nsId, nsd_json, nested_connections_info_b, nested_connections_info_b_old, nested_ns_instance)
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE finished updating connections between 1)federated-local, 2)local-federated" % (nsId)])
    return


##### functions supporting update_connecting_nested_federated_local_services

def update_connect_federate_local_pairs(nsId, nsd_json, nested_connections_info_a, nested_connections_info_a_old, nested_ns_instance):
    # we connect local_nested- federation_nested basis operations
    log_queue.put(["DEBUG", "In CROOE NEW CONNECTIONS: %s"% dumps(nested_connections_info_a)])
    log_queue.put(["DEBUG", "In CROOE OLD CONNECTIONS: %s"% dumps(nested_connections_info_a_old)])
    
    for pair in nested_connections_info_a:
        nested_ids = []
        nested_ids.append(pair['pair'][0])
        nested_ids.append(pair['pair'][1])
        connected_vnfs_f_new = {}
        connected_vnfs_l_new = {}
        link_characteristics = {}
        swap_vlan = {}
        for network in pair['ips'].keys():
            ip_list_f = []
            ip_list_l = []
            swap_vlan[network] = pair['vlan'][network][pair['nsId'][1][1]]
            link_info = extract_info_vls_nsd_simple(nsd_json["nsd"], network)
            link_characteristics.update(link_info)
            for ipl in pair['ips'][network][pair['nsId'][0][1]]:
                for ipf in pair['ips'][network][pair['nsId'][1][1]]:
                    ip_list_f.append([[ipl[0],ipl[2]],ipf])
                    ip_list_l.append([ipl,[ipf[0],pair['nsId'][1][1],ipf[1]]])
            connected_vnfs_f_new[network] = ip_list_f
            connected_vnfs_l_new[network] = ip_list_l
        # new for the scaling operation -> we generate the connected_vnfs_f and connected_vnfs_l for the previous situation
        # *--* we need to compare to launch to create add, remove variables
        # and then we compare and we launch the update operation on this
        # make connections at the federated domain 
        for pair_old in nested_connections_info_a_old:
            if ((pair_old['pair'][0] in nested_ids) and (pair_old['pair'][1] in nested_ids)): 
                # we are in the same pair
                connected_vnfs_f_old = {}
                connected_vnfs_l_old = {}
                for network in pair_old['ips'].keys():
                    ip_list_f = []
                    ip_list_l = []
                    for ipl in pair_old['ips'][network][pair_old['nsId'][0][1]]:
                        for ipf in pair_old['ips'][network][pair_old['nsId'][1][1]]:
                            ip_list_f.append([[ipl[0],ipl[2]],ipf])
                            ip_list_l.append([ipl,[ipf[0],pair['nsId'][1][1],ipf[1]]])
                    connected_vnfs_f_old[network] = ip_list_f
                    connected_vnfs_l_old[network] = ip_list_l
                break #we find our pair and we can exit the comparison
        # now we compare, we need to remove from link and swap_vlan info the networks that are not in the "add variable"
        # log_queue.put(["DEBUG", "CROOE connections FEDERATED processed OLD: %s"%dumps(connected_vnfs_f_old)])
        # log_queue.put(["DEBUG", "CROOE connections FEDERATED processed NEW: %s"%dumps(connected_vnfs_f_new)])
        # log_queue.put(["DEBUG", "CROOE connections LOCAL processed OLD: %s"%dumps(connected_vnfs_l_old)])
        # log_queue.put(["DEBUG", "CROOE connections LOCAL processed NEW: %s"%dumps(connected_vnfs_l_new)])

        [connected_vnfs_f_add, connected_vnfs_f_remove ] = comparing_federated_connections(connected_vnfs_f_old, connected_vnfs_f_new)
        # log_queue.put(["DEBUG", "PROCESSING LOCAL connections"])
        [connected_vnfs_l_add, connected_vnfs_l_remove ] = comparing_federated_connections(connected_vnfs_l_old, connected_vnfs_l_new)  
        # log_queue.put(["DEBUG", "In CROOE UPDATING CONNECTIONS SCALING:"])
        # log_queue.put(["DEBUG", "connections federated to add: %s"%dumps(connected_vnfs_f_add, indent=4)])
        # log_queue.put(["DEBUG", "connections local to add: %s"%dumps(connected_vnfs_l_add, indent=4)])
        # log_queue.put(["DEBUG", "connections federated to remove: %s"%dumps(connected_vnfs_f_remove, indent=4)])
        # log_queue.put(["DEBUG", "connections local to remove: %s"%dumps(connected_vnfs_l_remove, indent=4)])

        # log_queue.put(["DEBUG", "CROOE the link chars A are: %s"%link_characteristics])       
        link_chars_tmp = copy.deepcopy(link_characteristics)
        swap_vlan_tmp = copy.deepcopy(swap_vlan)
        # log_queue.put(["DEBUG", "CROOE the link chars B are: %s"%link_chars_tmp])
        for network in swap_vlan.keys():
            if network not in connected_vnfs_f_add.keys():
                del swap_vlan_tmp[network]
                del link_chars_tmp[network]
        log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE starts requesting connections from provider to consumer" % (nsId)])
        result = update_federated_internested_connections_request(pair['nsId'][1][0], pair['pair'][1], connected_vnfs_f_add, connected_vnfs_f_remove, 
                                                      link_chars_tmp, fed_domain[pair['nsId'][1][1]], ewbi_port, ewbi_path)
        log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE finish requesting connections from provider to consumer"% (nsId)])
        if (result == "OK"):
            # it means that the paths have been established in the federated domain, now let's 
            # make the connections at the local domain
            # towards the federated one, with the vlan swapping
            # It is passed, the globla nsId, the local nsId in the provider domain, how vnf's connect, the characterisitic of the link and the vlan  
            log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE starts requesting connections from consumer to provider" % (nsId)])                 
            update_federated_internested_connections_local(nsId, pair['pair'][0], connected_vnfs_l_add, connected_vnfs_l_remove, link_characteristics, pair['nsId'][1][1], swap_vlan_tmp, nested_ns_instance)           
            log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE finish requesting connections from consumer to provider" % (nsId)]) 
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE finishing connecting nested local with federated services"% (nsId)])        
    return

def comparing_federated_connections(connected_vnfs_old, connected_vnfs_new):
# we have the initial old and the new, we need to identify the pairs both to be created and
# the pairs to be deleted. The output are two variables with the same structure of connections,
    connections_to_add={}
    connections_to_remove={}
    # we compare the new with the old, if there is an element in the new that it is not in the old -> create
    for vl_new in connected_vnfs_new.keys():
        # log_queue.put(["DEBUG", "CRROOOOEEEE vl_new key: %s"%vl_new])
        if vl_new not in connected_vnfs_old.keys():
            # extreme case, complete new connections
            connections_to_add[vl_new] = connected_vnfs_new[vl_new]
        for vl_old in connected_vnfs_old.keys():
            # log_queue.put(["DEBUG", "CRROOOOEEEE vl_old key: %s"%vl_old])
            if (vl_new == vl_old):
                new_connections = 0
                for pair_new in connected_vnfs_new[vl_new]:
                    new_ip_addresses = [pair_new[0][0],pair_new[1][0]]
                    found = 0
                    for pair_old in connected_vnfs_old[vl_old]:
                        old_ip_addresses= [pair_old[0][0],pair_old[1][0]]
                        if ( (new_ip_addresses[0] in old_ip_addresses) and (new_ip_addresses[1] in old_ip_addresses)):
                            found = 1
                            # log_queue.put(["DEBUG", "Found pair not to add, new: %s, old: %s"%(new_ip_addresses, old_ip_addresses)])
                            break
                    if (found == 0):
                        if vl_new not in connections_to_add:
                            connections_to_add[vl_new] = []
                        connections_to_add[vl_new].append(pair_new)
                        new_connections = new_connections + 1
    log_queue.put(["DEBUG", "CROOE determining new connections PROVIDER-CONSUMER to add for a nested after a scaling operation: %s"%dumps(connections_to_add)])
    # we compare the old with the new, if there is an element in the old that it is not in the new -> delete
    for vl_old in connected_vnfs_old.keys():
        if vl_old not in connected_vnfs_new.keys():
            # extreme case, complete new connections
            connections_to_remove[vl_old] = connected_vnfs_old[vl_old]
        for vl_new in connected_vnfs_new.keys():
            if (vl_old == vl_new):
                old_connections = 0
                for pair_old in connected_vnfs_old[vl_old]:
                    old_ip_addresses = [pair_old[0][0],pair_old[1][0]]
                    found = 0
                    for pair_new in connected_vnfs_new[vl_new]:
                        new_ip_addresses= [pair_new[0][0],pair_new[1][0]]
                        if ((old_ip_addresses[0] in new_ip_addresses) and (old_ip_addresses[1] in new_ip_addresses)):
                            found = 1
                            break
                    if (found == 0):
                        if vl_old not in connections_to_remove:
                            connections_to_remove[vl_old] = []
                        connections_to_remove[vl_old].append(pair_old)
                        old_connections = old_connections + 1
    log_queue.put(["DEBUG", "CROOE determining old connections PROVIDER-CONSUMER to be removed for a nested after a scaling operation: %s"% dumps(connections_to_remove)])
    return [connections_to_add, connections_to_remove]

def deleting_connections(nsId, del_connections):
    # del_connections is a variable containing 
    current_vls = nsir_db.get_vls(nsId)
    # log_queue.put(["DEBUG", "deleting nested local connections: %s"%current_vls])
    # log_queue.put(["DEBUG", "deleting connections: %s"%del_connections])
    ids_to_remove = []
    # dummy variable for eenet.update_vls_method()
    vl_list = {}
    vl_list["logicalLinkPathList"] = []
    for vl in del_connections:
        for pair in del_connections[vl]:
            pair_ip_addresses = [pair[0][0],pair[1][0]]
            for ll in current_vls:
                key = next(iter(ll))
                vl_ip_addresses = []
                for data in ll[key]["metaData"]:
                    if (data["key"] == "srcVnfIpAddress" or data["key"] == "dstVnfIpAddress"):
                        vl_ip_addresses.append(data["value"])
                        if (len(vl_ip_addresses) == 2):
                            break
                if (pair_ip_addresses[0] in vl_ip_addresses and pair_ip_addresses[1] in vl_ip_addresses):
                    # it means this ll has to be removed
                    ids_to_remove.append(key)
    if (len(ids_to_remove)>0):
        eenet.update_vls(nsId, vl_list, ids_to_remove)

    
########################################
# def connecting_nested_federated_local_services(nsId, nsd_json, network_mapping, local_services, federated_services, nested_ns_instance, renaming_networks):
# refactored function to see if we can reuse code for scaling process
########################################

def determine_federated_nested_connections_local(nsId, nsdId, connected_vnfs, nested_ns_instance, swap_vlan):
    nested_connections = {}
    if nsdId in nested_ns_instance:
        vnf_info = nsir_db.get_vnf_deployed_info(nested_ns_instance[nsdId])
        network_info = nsir_db.get_vim_networks_info(nested_ns_instance[nsdId])
    else:
        vnf_info = nsir_db.get_vnf_deployed_info(nsId + '_' + nsdId)
        network_info = nsir_db.get_vim_networks_info(nsId + '_' + nsdId)
    nested_connections = {}
    for key in connected_vnfs.keys():
        nested_connections[key] = {}
        ip_local = connected_vnfs[key][0][0][0] #example of ip, to look for the network name
        nested_connections[key]['network'] = ""
        for network in network_info['cidr'].keys():
            if netaddr.IPAddress(ip_local) in netaddr.IPNetwork(network_info['cidr'][network]):
                nested_connections[key]['network'] = network
        nested_connections[key]['pairs'] = []
        nested_connections[key]['vlanId'] = swap_vlan[key]
        for elem in connected_vnfs[key]:
            nested_connections[key]['pairs'].append([elem[0], elem[1]])
    return nested_connections

def set_connections_local_federated_internested(nsId, nested_connections, link_characteristics, flag=None):
    resources_federated = sbi.get_mtp_federated_resources()
    resources_local = sbi.get_mtp_resources() 
    total_resources = copy.deepcopy(resources_local)
    for pops in resources_federated["NfviPops"]:
        total_resources["NfviPops"].append(pops)
    for ll in resources_federated["logicalLinkInterNfviPops"]:
        total_resources["logicalLinkInterNfviPops"].append(ll)
    # create connections like variable nested_connections
    # determinate the provider domain

    selected_links = simple_lsa(link_characteristics, total_resources, nested_connections)
    vls_info = extract_vls_info_mtp(total_resources, selected_links)
    if (flag == "update"):
        eenet.update_vls(nsId, vls_info, [])
    else:
        eenet.deploy_vls(vls_info, nsId)
        


def set_federated_internested_connections_local(nsId, nsdId, connected_vnfs, link_characteristics, domain, swap_vlan, nested_ns_instance):
    """
    This function instantiate the local part of the internested links, performing the swap change
    Parameters
    ----------
    nsId: string
        Identifier of the service
    nsdId: string
        Identifier of the descriptor of the local nested network service
    connected_vnfs: dict
        Dictionary with the required IP's to connect, from local to federated domain
    link_characteristics: dict
        Dictionary with the latency/bw values of the internested links
    domain: string
        Identifier of the federated domain in the fed domain variable
    swap_vlan: dict
        for each nested link, vlanId of the federated domain for a network name   
    nested_ns_instance: list of dicts
        each entry is of the type {nsd_name: instance_id}, references to other NS that are use to composite/federate
    Returns
    -------
    """
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE starts requesting connections from consumer to provider"% (nsId)]) 
    nested_connections = {}
    nested_connections = determine_federated_nested_connections_local(nsId, nsdId, connected_vnfs, nested_ns_instance, swap_vlan)
    set_connections_local_federated_internested(nsId, nested_connections, link_characteristics)
    log_queue.put(["INFO", "*****Time measure: CROOE CROOE finishes requesting connections from consumer to provider"]) 

def update_federated_internested_connections_local(nsId, nsdId, connected_vnfs_add, connected_vnfs_remove, link_characteristics, domain, swap_vlan, nested_ns_instance):
   log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE starts updating SCALING connections from consumer to provider"% (nsId)]) 
   if (connected_vnfs_remove):
       #*--*identify logical links to see which you have to remove
       deleting_connections(nsId, connected_vnfs_remove)
       log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE removed connections from consumer to provider"% (nsId)])
   if (connected_vnfs_add):
       nested_connections = {}
       nested_connections = determine_federated_nested_connections_local(nsId, nsdId, connected_vnfs_add, nested_ns_instance,swap_vlan)
       set_connections_local_federated_internested(nsId, nested_connections, link_characteristics, "update")
       log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE created connections from consumer to provider" % (nsId)])
   log_queue.put(["INFO", "*****Time measure: CROOE CROOE finishes updating SCALING connections from consumer to provider"]) 

def remove_nested_connections(nsId):
    """
    This function removes the connections between nested services
    Parameters
    ----------
    nsId: string
        Identifier of the service
    Returns
    -------
    """
    log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE starts removing internested connections consumer-provider" % (nsId)])
    log_queue.put(["INFO", "CROOE module removing nested connections"])
    if nsir_db.exists_nsir(nsId):
        # ask network execution engine to deploy the virtual links
        eenet.uninstall_vls(nsId)
        # remove the information from the nsir
        nsir_db.delete_nsir_record(nsId)
        log_queue.put(["INFO", "*****Time measure for nsId: %s: CROOE CROOE finishes removing internested connections consumer-provider"% (nsId)])
