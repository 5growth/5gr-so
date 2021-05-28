# Copyright 2017-2018 Sandvine
# Copyright 2018 Telefonica
#
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
"""
OSM shell/cli
"""

import click
from osmclient import client
from osmclient.common.exceptions import ClientException, NotFound
from prettytable import PrettyTable
import yaml
import json
import time
import pycurl
import os
import textwrap
import pkg_resources
import logging
from datetime import datetime


# Global variables

CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'], max_content_width=160)

def wrap_text(text, width):
    wrapper = textwrap.TextWrapper(width=width)
    lines = text.splitlines()
    return "\n".join(map(wrapper.fill, lines))


def trunc_text(text, length):
   if len(text) > length:
       return text[:(length - 3)] + '...'
   else:
       return text


def check_client_version(obj, what, version='sol005'):
    """
    Checks the version of the client object and raises error if it not the expected.

    :param obj: the client object
    :what: the function or command under evaluation (used when an error is raised)
    :return: -
    :raises ClientError: if the specified version does not match the client version
    """
    logger.debug("")
    fullclassname = obj.__module__ + "." + obj.__class__.__name__
    message = 'The following commands or options are only supported with the option "--sol005": {}'.format(what)
    if version == 'v1':
        message = 'The following commands or options are not supported when using option "--sol005": {}'.format(what)
    if fullclassname != 'osmclient.{}.client.Client'.format(version):
        raise ClientException(message)
    return


@click.group(context_settings=dict(help_option_names=['-h', '--help'], max_content_width=160))
@click.option('--hostname',
              default="127.0.0.1",
              envvar='OSM_HOSTNAME',
              help='hostname of server.  ' +
                   'Also can set OSM_HOSTNAME in environment')
#@click.option('--sol005/--no-sol005',
#              default=True,
#              envvar='OSM_SOL005',
#              help='Use ETSI NFV SOL005 API (default) or the previous SO API. ' +
#                   'Also can set OSM_SOL005 in environment')
@click.option('--user',
              default=None,
              envvar='OSM_USER',
              help='user (defaults to admin). ' +
                   'Also can set OSM_USER in environment')
@click.option('--password',
              default=None,
              envvar='OSM_PASSWORD',
              help='password (defaults to admin). ' +
                   'Also can set OSM_PASSWORD in environment')
@click.option('--project',
              default=None,
              envvar='OSM_PROJECT',
              help='project (defaults to admin). ' +
                   'Also can set OSM_PROJECT in environment')
@click.option('-v', '--verbose', count=True,
              help='increase verbosity (-v INFO, -vv VERBOSE, -vvv DEBUG)')
@click.option('--all-projects',
              default=None,
              is_flag=True,
              help='include all projects')
@click.option('--public/--no-public', default=None,
              help='flag for public items (packages, instances, VIM accounts, etc.)')
@click.option('--project-domain-name', 'project_domain_name',
              default=None,
              envvar='OSM_PROJECT_DOMAIN_NAME',
              help='project domain name for keystone authentication (default to None). ' +
                   'Also can set OSM_PROJECT_DOMAIN_NAME in environment')
@click.option('--user-domain-name', 'user_domain_name',
              default=None,
              envvar='OSM_USER_DOMAIN_NAME',
              help='user domain name for keystone authentication (default to None). ' +
                   'Also can set OSM_USER_DOMAIN_NAME in environment')
#@click.option('--so-port',
#              default=None,
#              envvar='OSM_SO_PORT',
#              help='hostname of server.  ' +
#                   'Also can set OSM_SO_PORT in environment')
#@click.option('--so-project',
#              default=None,
#              envvar='OSM_SO_PROJECT',
#              help='Project Name in SO.  ' +
#                   'Also can set OSM_SO_PROJECT in environment')
#@click.option('--ro-hostname',
#              default=None,
#              envvar='OSM_RO_HOSTNAME',
#              help='hostname of RO server.  ' +
#              'Also can set OSM_RO_HOSTNAME in environment')
#@click.option('--ro-port',
#              default=None,
#              envvar='OSM_RO_PORT',
#              help='hostname of RO server.  ' +
#                   'Also can set OSM_RO_PORT in environment')
@click.pass_context
def cli_osm(ctx, **kwargs):
    global logger
    hostname = kwargs.pop("hostname", None)
    if hostname is None:
        print((
            "either hostname option or OSM_HOSTNAME " +
            "environment variable needs to be specified"))
        exit(1)
    # Remove None values
    kwargs = {k: v for k, v in kwargs.items() if v is not None}
#    if so_port is not None:
#        kwargs['so_port']=so_port
#    if so_project is not None:
#        kwargs['so_project']=so_project
#    if ro_hostname is not None:
#        kwargs['ro_host']=ro_hostname
#    if ro_port is not None:
#        kwargs['ro_port']=ro_port
    sol005 = os.getenv('OSM_SOL005', True)
#    if user is not None:
#        kwargs['user']=user
#    if password is not None:
#        kwargs['password']=password
#    if project is not None:
#        kwargs['project']=project
#    if all_projects:
#        kwargs['all_projects']=all_projects
#    if public is not None:
#        kwargs['public']=public
    ctx.obj = client.Client(host=hostname, sol005=sol005, **kwargs)
    logger = logging.getLogger('osmclient')


####################
# LIST operations
####################

@cli_osm.command(name='ns-list', short_help='list all NS instances')
@click.option('--filter', default=None,
              help='restricts the list to the NS instances matching the filter.')
@click.option('--long', is_flag=True,
              help='get more details of the NS (project, vim, deployment status, configuration status.')
@click.pass_context
def ns_list(ctx, filter, long):
    """list all NS instances

    \b
    Options:
      --filter filterExpr    Restricts the list to the NS instances matching the filter

    \b
    filterExpr consists of one or more strings formatted according to "simpleFilterExpr",
    concatenated using the "&" character:

      \b
      filterExpr := <simpleFilterExpr>["&"<simpleFilterExpr>]*
      simpleFilterExpr := <attrName>["."<attrName>]*["."<op>]"="<value>[","<value>]*
      op := "eq" | "neq" | "gt" | "lt" | "gte" | "lte" | "cont" | "ncont"
      attrName := string
      value := scalar value

    \b
    where:
      * zero or more occurrences
      ? zero or one occurrence
      [] grouping of expressions to be used with ? and *
      "" quotation marks for marking string constants
      <> name separator

    \b
    "AttrName" is the name of one attribute in the data type that defines the representation
    of the resource. The dot (".") character in "simpleFilterExpr" allows concatenation of
    <attrName> entries to filter by attributes deeper in the hierarchy of a structured document.
    "Op" stands for the comparison operator. If the expression has concatenated <attrName>
    entries, it means that the operator "op" is applied to the attribute addressed by the last
    <attrName> entry included in the concatenation. All simple filter expressions are combined
    by the "AND" logical operator. In a concatenation of <attrName> entries in a <simpleFilterExpr>,
    the rightmost "attrName" entry in a "simpleFilterExpr" is called "leaf attribute". The
    concatenation of all "attrName" entries except the leaf attribute is called the "attribute
    prefix". If an attribute referenced in an expression is an array, an object that contains a
    corresponding array shall be considered to match the expression if any of the elements in the
    array matches all expressions that have the same attribute prefix.

    \b
    Filter examples:
       --filter  admin-status=ENABLED
       --filter  nsd-ref=<NSD_NAME>
       --filter  nsd.vendor=<VENDOR>
       --filter  nsd.vendor=<VENDOR>&nsd-ref=<NSD_NAME>
       --filter  nsd.constituent-vnfd.vnfd-id-ref=<VNFD_NAME>
    """
    def summarize_deployment_status(status_dict):
        #Nets
        summary = ""
        if not status_dict:
            return summary
        n_nets = 0
        status_nets = {}
        net_list = status_dict.get('nets',[])
        for net in net_list:
            n_nets += 1
            if net['status'] not in status_nets:
                status_nets[net['status']] = 1
            else:
                status_nets[net['status']] +=1
        message = "Nets: "
        for k,v in status_nets.items():
            message += "{}:{},".format(k,v)
        message += "TOTAL:{}".format(n_nets)
        summary += "{}".format(message)
        #VMs and VNFs
        n_vms = 0
        status_vms = {}
        status_vnfs = {}
        vnf_list = status_dict['vnfs']
        for vnf in vnf_list:
            member_vnf_index = vnf['member_vnf_index']
            if member_vnf_index not in status_vnfs:
                status_vnfs[member_vnf_index] = {}
            for vm in vnf['vms']:
                n_vms += 1
                if vm['status'] not in status_vms:
                    status_vms[vm['status']] = 1
                else:
                    status_vms[vm['status']] +=1
                if vm['status'] not in status_vnfs[member_vnf_index]:
                    status_vnfs[member_vnf_index][vm['status']] = 1
                else:
                    status_vnfs[member_vnf_index][vm['status']] += 1
        message = "VMs: "
        for k,v in status_vms.items():
            message += "{}:{},".format(k,v)
        message += "TOTAL:{}".format(n_vms)
        summary += "\n{}".format(message)
        summary += "\nNFs:"
        for k,v in status_vnfs.items():
            total = 0
            message = "\n  {} VMs: ".format(k)
            for k2,v2 in v.items():
                message += "{}:{},".format(k2,v2)
                total += v2
            message += "TOTAL:{}".format(total)
        summary += message
        return summary
        
    def summarize_config_status(ee_list):
        summary = ""
        if not ee_list:
            return summary
        n_ee = 0
        status_ee = {}
        for ee in ee_list:
            n_ee += 1
            if ee['elementType'] not in status_ee:
                status_ee[ee['elementType']] = {}
                status_ee[ee['elementType']][ee['status']] = 1
                continue
            if ee['status'] in status_ee[ee['elementType']]:
                status_ee[ee['elementType']][ee['status']] += 1
            else:
                status_ee[ee['elementType']][ee['status']] = 1
        for elementType in ["KDU", "VDU", "PDU", "VNF", "NS"]:
            if elementType in status_ee:
                message = ""
                total = 0
                for k,v in status_ee[elementType].items():
                    message += "{}:{},".format(k,v)
                    total += v
                message += "TOTAL:{}\n".format(total)
                summary += "{}: {}".format(elementType, message)
        summary += "TOTAL Exec. Env.: {}".format(n_ee)
        return summary

    logger.debug("")
    if filter:
        check_client_version(ctx.obj, '--filter')
        resp = ctx.obj.ns.list(filter)
    else:
        resp = ctx.obj.ns.list()
    if long:
        table = PrettyTable(
        ['ns instance name',
         'id',
         'date',
         'ns state',
         'current operation',
         'error details',
         'project',
         'vim (inst param)',
         'deployment status',
         'configuration status'])
        project_list = ctx.obj.project.list()
        vim_list = ctx.obj.vim.list()
    else:
        table = PrettyTable(
        ['ns instance name',
         'id',
         'date',
         'ns state',
         'current operation',
         'error details'])
    for ns in resp:
        fullclassname = ctx.obj.__module__ + "." + ctx.obj.__class__.__name__
        if fullclassname == 'osmclient.sol005.client.Client':
            nsr = ns
            logger.debug('NS info: {}'.format(nsr))
            nsr_name = nsr['name']
            nsr_id = nsr['_id']
            date = datetime.fromtimestamp(nsr['create-time']).strftime("%Y-%m-%dT%H:%M:%S")
            ns_state = nsr.get('nsState', nsr['_admin']['nsState'])
            if long:
                deployment_status = summarize_deployment_status(nsr.get('deploymentStatus'))
                config_status = summarize_config_status(nsr.get('configurationStatus'))
                project_id = nsr.get('_admin').get('projects_read')[0]
                project_name = '-'
                for p in project_list:
                    if p['_id'] == project_id:
                        project_name = p['name']
                        break
                #project = '{} ({})'.format(project_name, project_id)
                project = project_name
                vim_id = nsr.get('datacenter')
                vim_name = '-'
                for v in vim_list:
                    if v['uuid'] == vim_id:
                        vim_name = v['name']
                        break
                #vim = '{} ({})'.format(vim_name, vim_id)
                vim = vim_name
            if 'currentOperation' in nsr:
                current_operation = "{} ({})".format(nsr['currentOperation'],nsr['currentOperationID'])
            else:
                current_operation = "{} ({})".format(nsr['_admin'].get('current-operation','-'), nsr['_admin']['nslcmop'])
            error_details = "N/A"
            if ns_state == "BROKEN" or ns_state == "DEGRADED" or \
                ('currentOperation' not in nsr and nsr.get('errorDescription')):
                error_details = "{}\nDetail: {}".format(nsr['errorDescription'], nsr['errorDetail'])
        else:
            nsopdata = ctx.obj.ns.get_opdata(ns['id'])
            nsr = nsopdata['nsr:nsr']
            nsr_name = nsr['name-ref']
            nsr_id = nsr['ns-instance-config-ref']
            date = '-'
            project = '-'
            deployment_status = nsr['operational-status'] if 'operational-status' in nsr else 'Not found'
            ns_state = deployment_status
            config_status = nsr.get('config-status', 'Not found')
            current_operation = "Unknown"
            error_details = nsr.get('detailed-status', 'Not found')
            if config_status == "config_not_needed":
                config_status = "configured (no charms)"

        if long:
            table.add_row(
                 [nsr_name,
                 nsr_id,
                 date,
                 ns_state,
                 current_operation,
                 wrap_text(text=error_details,width=40),
                 project,
                 vim,
                 deployment_status,
                 config_status])
        else:
            table.add_row(
                 [nsr_name,
                 nsr_id,
                 date,
                 ns_state,
                 current_operation,
                 wrap_text(text=error_details,width=40)])
    table.align = 'l'
    print(table)
    print('To get the history of all operations over a NS, run "osm ns-op-list NS_ID"')
    print('For more details on the current operation, run "osm ns-op-show OPERATION_ID"')

def nsd_list(ctx, filter, long):
    logger.debug("")
    if filter:
        check_client_version(ctx.obj, '--filter')
        resp = ctx.obj.nsd.list(filter)
    else:
        resp = ctx.obj.nsd.list()
    # print(yaml.safe_dump(resp))
    fullclassname = ctx.obj.__module__ + "." + ctx.obj.__class__.__name__
    if fullclassname == 'osmclient.sol005.client.Client':
        if long:
            table = PrettyTable(['nsd name', 'id', 'onboarding state', 'operational state',
                                 'usage state', 'date', 'last update'])
        else:
            table = PrettyTable(['nsd name', 'id'])
        for nsd in resp:
            name = nsd.get('name','-')
            if long:
                onb_state = nsd['_admin'].get('onboardingState','-')
                op_state = nsd['_admin'].get('operationalState','-')
                usage_state = nsd['_admin'].get('usageState','-')
                date = datetime.fromtimestamp(nsd['_admin']['created']).strftime("%Y-%m-%dT%H:%M:%S")
                last_update = datetime.fromtimestamp(nsd['_admin']['modified']).strftime("%Y-%m-%dT%H:%M:%S")
                table.add_row([name, nsd['_id'], onb_state, op_state, usage_state, date, last_update])
            else:
                table.add_row([name, nsd['_id']])
    else:
        table = PrettyTable(['nsd name', 'id'])
        for nsd in resp:
            table.add_row([nsd['name'], nsd['id']])
    table.align = 'l'
    print(table)


@cli_osm.command(name='nsd-list', short_help='list all NS packages')
@click.option('--filter', default=None,
              help='restricts the list to the NSD/NSpkg matching the filter')
@click.option('--long', is_flag=True, help='get more details')
@click.pass_context
def nsd_list1(ctx, filter, long):
    """list all NSD/NS pkg in the system"""
    logger.debug("")
    nsd_list(ctx, filter, long)


@cli_osm.command(name='nspkg-list', short_help='list all NS packages')
@click.option('--filter', default=None,
              help='restricts the list to the NSD/NSpkg matching the filter')
@click.option('--long', is_flag=True, help='get more details')
@click.pass_context
def nsd_list2(ctx, filter, long):
    """list all NS packages"""
    logger.debug("")
    nsd_list(ctx, filter, long)


def pkg_repo_list(ctx, pkgtype, filter, repo, long):
    resp = ctx.obj.osmrepo.pkg_list(pkgtype, filter, repo)
    if long:
        table = PrettyTable(['nfpkg name', 'vendor', 'version', 'latest', 'description', 'repository'])
    else:
        table = PrettyTable(['nfpkg name', 'repository'])
    for vnfd in resp:
        name = vnfd.get('name', '-')
        repository = vnfd.get('repository')
        if long:
            vendor = vnfd.get('vendor')
            version = vnfd.get('version')
            description = vnfd.get('description')
            latest = vnfd.get('latest')
            table.add_row([name, vendor, version, latest, description, repository])
        else:
            table.add_row([name, repository])
        table.align = 'l'
    print(table)

def vnfd_list(ctx, nf_type, filter, long):
    logger.debug("")
    if nf_type:
        check_client_version(ctx.obj, '--nf_type')
    elif filter:
        check_client_version(ctx.obj, '--filter')
    if nf_type:
        if nf_type == "vnf":
            nf_filter = "_admin.type=vnfd"
        elif nf_type == "pnf":
            nf_filter = "_admin.type=pnfd"
        elif nf_type == "hnf":
            nf_filter = "_admin.type=hnfd"
        else:
            raise ClientException('wrong value for "--nf_type" option, allowed values: vnf, pnf, hnf')
        if filter:
            filter = '{}&{}'.format(nf_filter, filter)
        else:
            filter = nf_filter
    if filter:
        resp = ctx.obj.vnfd.list(filter)
    else:
        resp = ctx.obj.vnfd.list()
    # print(yaml.safe_dump(resp))
    fullclassname = ctx.obj.__module__ + "." + ctx.obj.__class__.__name__
    if fullclassname == 'osmclient.sol005.client.Client':
        if long:
            table = PrettyTable(['nfpkg name', 'id', 'vendor', 'version', 'onboarding state', 'operational state',
                                  'usage state', 'date', 'last update'])
        else:
            table = PrettyTable(['nfpkg name', 'id'])
        for vnfd in resp:
            name = vnfd['name'] if 'name' in vnfd else '-'
            if long:
                onb_state = vnfd['_admin'].get('onboardingState','-')
                op_state = vnfd['_admin'].get('operationalState','-')
                vendor = vnfd.get('vendor')
                version = vnfd.get('version')
                usage_state = vnfd['_admin'].get('usageState','-')
                date = datetime.fromtimestamp(vnfd['_admin']['created']).strftime("%Y-%m-%dT%H:%M:%S")
                last_update = datetime.fromtimestamp(vnfd['_admin']['modified']).strftime("%Y-%m-%dT%H:%M:%S")
                table.add_row([name, vnfd['_id'], vendor, version, onb_state, op_state, usage_state, date, last_update])
            else:
                table.add_row([name, vnfd['_id']])
    else:
        table = PrettyTable(['nfpkg name', 'id'])
        for vnfd in resp:
            table.add_row([vnfd['name'], vnfd['id']])
    table.align = 'l'
    print(table)


@cli_osm.command(name='vnfd-list', short_help='list all xNF packages (VNF, HNF, PNF)')
@click.option('--nf_type', help='type of NF (vnf, pnf, hnf)')
@click.option('--filter', default=None,
              help='restricts the list to the NF pkg matching the filter')
@click.option('--long', is_flag=True, help='get more details')
@click.pass_context
def vnfd_list1(ctx, nf_type, filter, long):
    """list all xNF packages (VNF, HNF, PNF)"""
    logger.debug("")
    vnfd_list(ctx, nf_type, filter, long)


@cli_osm.command(name='vnfpkg-list', short_help='list all xNF packages (VNF, HNF, PNF)')
@click.option('--nf_type', help='type of NF (vnf, pnf, hnf)')
@click.option('--filter', default=None,
              help='restricts the list to the NFpkg matching the filter')
@click.option('--long', is_flag=True, help='get more details')
@click.pass_context
def vnfd_list2(ctx, nf_type, filter, long):
    """list all xNF packages (VNF, HNF, PNF)"""
    logger.debug("")
    vnfd_list(ctx, nf_type, filter, long)

@cli_osm.command(name='nfpkg-list', short_help='list all xNF packages (VNF, HNF, PNF)')
@click.option('--nf_type', help='type of NF (vnf, pnf, hnf)')
@click.option('--filter', default=None,
              help='restricts the list to the NFpkg matching the filter')
@click.option('--long', is_flag=True, help='get more details')
@click.pass_context
def nfpkg_list(ctx, nf_type, filter, long):
    """list all xNF packages (VNF, HNF, PNF)"""
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    vnfd_list(ctx, nf_type, filter, long)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)

@cli_osm.command(name='vnfpkg-repo-list', short_help='list all xNF from OSM repositories')
@click.option('--filter', default=None,
              help='restricts the list to the NFpkg matching the filter')
@click.option('--repo', default=None,
              help='restricts the list to a particular OSM repository')
@click.option('--long', is_flag=True, help='get more details')
@click.pass_context
def nfpkg_repo_list1(ctx, filter, repo, long):
    """list xNF packages from OSM repositories"""
    pkgtype = 'vnf'
    pkg_repo_list(ctx, pkgtype, filter, repo, long)

@cli_osm.command(name='nfpkg-repo-list', short_help='list all xNF from OSM repositories')
@click.option('--filter', default=None,
              help='restricts the list to the NFpkg matching the filter')
@click.option('--repo', default=None,
              help='restricts the list to a particular OSM repository')
@click.option('--long', is_flag=True, help='get more details')
@click.pass_context
def nfpkg_repo_list2(ctx, filter, repo, long):
    """list xNF packages from OSM repositories"""
    pkgtype = 'vnf'
    pkg_repo_list(ctx, pkgtype, filter, repo, long)

def vnf_list(ctx, ns, filter, long):
    # try:
    if ns or filter:
        if ns:
            check_client_version(ctx.obj, '--ns')
        if filter:
            check_client_version(ctx.obj, '--filter')
        resp = ctx.obj.vnf.list(ns, filter)
    else:
        resp = ctx.obj.vnf.list()
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)
    fullclassname = ctx.obj.__module__ + "." + ctx.obj.__class__.__name__
    if fullclassname == 'osmclient.sol005.client.Client':
        field_names = ['vnf id', 'name', 'ns id', 'vnf member index',
                       'vnfd name', 'vim account id', 'ip address']
        if long:
            field_names = ['vnf id', 'name', 'ns id', 'vnf member index',
                           'vnfd name', 'vim account id', 'ip address',
                           'date', 'last update']
        table = PrettyTable(field_names)
        for vnfr in resp:
            name = vnfr['name'] if 'name' in vnfr else '-'
            new_row = [vnfr['_id'], name, vnfr['nsr-id-ref'],
                       vnfr['member-vnf-index-ref'], vnfr['vnfd-ref'],
                       vnfr['vim-account-id'], vnfr['ip-address']]
            if long:
                date = datetime.fromtimestamp(vnfr['_admin']['created']).strftime("%Y-%m-%dT%H:%M:%S")
                last_update = datetime.fromtimestamp(vnfr['_admin']['modified']).strftime("%Y-%m-%dT%H:%M:%S")
                new_row.extend([date, last_update])
            table.add_row(new_row)
    else:
        table = PrettyTable(
            ['vnf name',
             'id',
             'operational status',
             'config status'])
        for vnfr in resp:
            if 'mgmt-interface' not in vnfr:
                vnfr['mgmt-interface'] = {}
                vnfr['mgmt-interface']['ip-address'] = None
            table.add_row(
                [vnfr['name'],
                 vnfr['id'],
                 vnfr['operational-status'],
                 vnfr['config-status']])
    table.align = 'l'
    print(table)


@cli_osm.command(name='vnf-list', short_help='list all NF instances')
@click.option('--ns', default=None, help='NS instance id or name to restrict the NF list')
@click.option('--filter', default=None,
              help='restricts the list to the NF instances matching the filter.')
@click.option('--long', is_flag=True, help='get more details')
@click.pass_context
def vnf_list1(ctx, ns, filter, long):
    """list all NF instances"""
    logger.debug("")
    vnf_list(ctx, ns, filter, long)

@cli_osm.command(name='nsd-repo-list', short_help='list all NS from OSM repositories')
@click.option('--filter', default=None,
              help='restricts the list to the NS matching the filter')
@click.option('--repo', default=None,
              help='restricts the list to a particular OSM repository')
@click.option('--long', is_flag=True, help='get more details')
@click.pass_context
def nspkg_repo_list(ctx, filter, repo, long):
    """list xNF packages from OSM repositories"""
    pkgtype = 'ns'
    pkg_repo_list(ctx, pkgtype, filter, repo, long)

@cli_osm.command(name='nspkg-repo-list', short_help='list all NS from OSM repositories')
@click.option('--filter', default=None,
              help='restricts the list to the NS matching the filter')
@click.option('--repo', default=None,
              help='restricts the list to a particular OSM repository')
@click.option('--long', is_flag=True, help='get more details')
@click.pass_context
def nspkg_repo_list2(ctx, filter, repo, long):
    """list xNF packages from OSM repositories"""
    pkgtype = 'ns'
    pkg_repo_list(ctx, pkgtype, filter, repo, long)

@cli_osm.command(name='nf-list', short_help='list all NF instances')
@click.option('--ns', default=None, help='NS instance id or name to restrict the NF list')
@click.option('--filter', default=None,
              help='restricts the list to the NF instances matching the filter.')
@click.option('--long', is_flag=True, help='get more details')
@click.pass_context
def nf_list(ctx, ns, filter, long):
    """list all NF instances

    \b
    Options:
      --ns     TEXT           NS instance id or name to restrict the VNF list
      --filter filterExpr     Restricts the list to the VNF instances matching the filter

    \b
    filterExpr consists of one or more strings formatted according to "simpleFilterExpr",
    concatenated using the "&" character:

      \b
      filterExpr := <simpleFilterExpr>["&"<simpleFilterExpr>]*
      simpleFilterExpr := <attrName>["."<attrName>]*["."<op>]"="<value>[","<value>]*
      op := "eq" | "neq" | "gt" | "lt" | "gte" | "lte" | "cont" | "ncont"
      attrName := string
      value := scalar value

    \b
    where:
      * zero or more occurrences
      ? zero or one occurrence
      [] grouping of expressions to be used with ? and *
      "" quotation marks for marking string constants
      <> name separator

    \b
    "AttrName" is the name of one attribute in the data type that defines the representation
    of the resource. The dot (".") character in "simpleFilterExpr" allows concatenation of
    <attrName> entries to filter by attributes deeper in the hierarchy of a structured document.
    "Op" stands for the comparison operator. If the expression has concatenated <attrName>
    entries, it means that the operator "op" is applied to the attribute addressed by the last
    <attrName> entry included in the concatenation. All simple filter expressions are combined
    by the "AND" logical operator. In a concatenation of <attrName> entries in a <simpleFilterExpr>,
    the rightmost "attrName" entry in a "simpleFilterExpr" is called "leaf attribute". The
    concatenation of all "attrName" entries except the leaf attribute is called the "attribute
    prefix". If an attribute referenced in an expression is an array, an object that contains a
    corresponding array shall be considered to match the expression if any of the elements in the
    array matches all expressions that have the same attribute prefix.

    \b
    Filter examples:
       --filter  vim-account-id=<VIM_ACCOUNT_ID>
       --filter  vnfd-ref=<VNFD_NAME>
       --filter  vdur.ip-address=<IP_ADDRESS>
       --filter  vnfd-ref=<VNFD_NAME>,vdur.ip-address=<IP_ADDRESS>
    """
    logger.debug("")
    vnf_list(ctx, ns, filter, long)


@cli_osm.command(name='ns-op-list', short_help='shows the history of operations over a NS instance')
@click.argument('name')
@click.option('--long', is_flag=True,
              help='get more details of the NS operation (date, ).')
@click.pass_context
def ns_op_list(ctx, name, long):
    """shows the history of operations over a NS instance

    NAME: name or ID of the NS instance
    """
    def formatParams(params):
        if params['lcmOperationType']=='instantiate':
            params.pop('nsDescription')
            params.pop('nsName')
            params.pop('nsdId')
            params.pop('nsr_id')
        elif params['lcmOperationType']=='action':
            params.pop('primitive')
        params.pop('lcmOperationType')
        params.pop('nsInstanceId')
        return params

    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    resp = ctx.obj.ns.list_op(name)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)

    if long:
        table = PrettyTable(['id', 'operation', 'action_name', 'operation_params', 'status', 'date', 'last update', 'detail'])
    else:
        table = PrettyTable(['id', 'operation', 'action_name', 'status', 'date', 'detail'])

    #print(yaml.safe_dump(resp))
    for op in resp:
        action_name = "N/A"
        if op['lcmOperationType']=='action':
            action_name = op['operationParams']['primitive']
        detail = "-"
        if op['operationState'] == 'PROCESSING':
            if op['queuePosition'] is not None and op['queuePosition'] > 0:
                detail = "In queue. Current position: {}".format(op['queuePosition'])
            elif op['lcmOperationType'] in ('instantiate', 'terminate'):
                if op['stage']:
                    detail = op['stage']
        elif op['operationState'] in ('FAILED', 'FAILED_TEMP'):
            detail = op.get('errorMessage','-')
        date = datetime.fromtimestamp(op['startTime']).strftime("%Y-%m-%dT%H:%M:%S")
        last_update = datetime.fromtimestamp(op['statusEnteredTime']).strftime("%Y-%m-%dT%H:%M:%S")
        if long:
            table.add_row([op['id'],
                           op['lcmOperationType'],
                           action_name,
                           wrap_text(text=json.dumps(formatParams(op['operationParams']),indent=2),width=50),
                           op['operationState'],
                           date,
                           last_update,
                           wrap_text(text=detail,width=50)])
        else:
            table.add_row([op['id'], op['lcmOperationType'], action_name,
                           op['operationState'], date, wrap_text(text=detail or "",width=50)])
    table.align = 'l'
    print(table)


def nsi_list(ctx, filter):
    """list all Network Slice Instances"""
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    resp = ctx.obj.nsi.list(filter)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)
    table = PrettyTable(
        ['netslice instance name',
         'id',
         'operational status',
         'config status',
         'detailed status'])
    for nsi in resp:
        nsi_name = nsi['name']
        nsi_id = nsi['_id']
        opstatus = nsi['operational-status'] if 'operational-status' in nsi else 'Not found'
        configstatus = nsi['config-status'] if 'config-status' in nsi else 'Not found'
        detailed_status = nsi['detailed-status'] if 'detailed-status' in nsi else 'Not found'
        if configstatus == "config_not_needed":
            configstatus = "configured (no charms)"
        table.add_row(
            [nsi_name,
             nsi_id,
             opstatus,
             configstatus,
             detailed_status])
    table.align = 'l'
    print(table)


@cli_osm.command(name='nsi-list', short_help='list all Network Slice Instances (NSI)')
@click.option('--filter', default=None,
              help='restricts the list to the Network Slice Instances matching the filter')
@click.pass_context
def nsi_list1(ctx, filter):
    """list all Network Slice Instances (NSI)"""
    logger.debug("")
    nsi_list(ctx, filter)


@cli_osm.command(name='netslice-instance-list', short_help='list all Network Slice Instances (NSI)')
@click.option('--filter', default=None,
              help='restricts the list to the Network Slice Instances matching the filter')
@click.pass_context
def nsi_list2(ctx, filter):
    """list all Network Slice Instances (NSI)"""
    logger.debug("")
    nsi_list(ctx, filter)


def nst_list(ctx, filter):
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    resp = ctx.obj.nst.list(filter)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)
    # print(yaml.safe_dump(resp))
    table = PrettyTable(['nst name', 'id'])
    for nst in resp:
        name = nst['name'] if 'name' in nst else '-'
        table.add_row([name, nst['_id']])
    table.align = 'l'
    print(table)


@cli_osm.command(name='nst-list', short_help='list all Network Slice Templates (NST)')
@click.option('--filter', default=None,
              help='restricts the list to the NST matching the filter')
@click.pass_context
def nst_list1(ctx, filter):
    """list all Network Slice Templates (NST) in the system"""
    logger.debug("")
    nst_list(ctx, filter)


@cli_osm.command(name='netslice-template-list', short_help='list all Network Slice Templates (NST)')
@click.option('--filter', default=None,
              help='restricts the list to the NST matching the filter')
@click.pass_context
def nst_list2(ctx, filter):
    """list all Network Slice Templates (NST) in the system"""
    logger.debug("")
    nst_list(ctx, filter)


def nsi_op_list(ctx, name):
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    resp = ctx.obj.nsi.list_op(name)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)
    table = PrettyTable(['id', 'operation', 'status'])
    for op in resp:
        table.add_row([op['id'], op['lcmOperationType'],
                       op['operationState']])
    table.align = 'l'
    print(table)


@cli_osm.command(name='nsi-op-list', short_help='shows the history of operations over a Network Slice Instance (NSI)')
@click.argument('name')
@click.pass_context
def nsi_op_list1(ctx, name):
    """shows the history of operations over a Network Slice Instance (NSI)

    NAME: name or ID of the Network Slice Instance
    """
    logger.debug("")
    nsi_op_list(ctx, name)


@cli_osm.command(name='netslice-instance-op-list', short_help='shows the history of operations over a Network Slice Instance (NSI)')
@click.argument('name')
@click.pass_context
def nsi_op_list2(ctx, name):
    """shows the history of operations over a Network Slice Instance (NSI)

    NAME: name or ID of the Network Slice Instance
    """
    logger.debug("")
    nsi_op_list(ctx, name)


@cli_osm.command(name='pdu-list', short_help='list all Physical Deployment Units (PDU)')
@click.option('--filter', default=None,
              help='restricts the list to the Physical Deployment Units matching the filter')
@click.pass_context
def pdu_list(ctx, filter):
    """list all Physical Deployment Units (PDU)"""
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    resp = ctx.obj.pdu.list(filter)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)
    table = PrettyTable(
        ['pdu name',
         'id',
         'type',
         'mgmt ip address'])
    for pdu in resp:
        pdu_name = pdu['name']
        pdu_id = pdu['_id']
        pdu_type = pdu['type']
        pdu_ipaddress = "None"
        for iface in pdu['interfaces']:
            if iface['mgmt']:
                pdu_ipaddress = iface['ip-address']
                break
        table.add_row(
            [pdu_name,
             pdu_id,
             pdu_type,
             pdu_ipaddress])
    table.align = 'l'
    print(table)


####################
# SHOW operations
####################

def nsd_show(ctx, name, literal):
    logger.debug("")
    # try:
    resp = ctx.obj.nsd.get(name)
    # resp = ctx.obj.nsd.get_individual(name)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)

    if literal:
        print(yaml.safe_dump(resp, indent=4, default_flow_style=False))
        return

    table = PrettyTable(['field', 'value'])
    for k, v in list(resp.items()):
        table.add_row([k, wrap_text(text=json.dumps(v, indent=2),width=100)])
    table.align = 'l'
    print(table)


@cli_osm.command(name='nsd-show', short_help='shows the details of a NS package')
@click.option('--literal', is_flag=True,
              help='print literally, no pretty table')
@click.argument('name')
@click.pass_context
def nsd_show1(ctx, name, literal):
    """shows the content of a NSD

    NAME: name or ID of the NSD/NSpkg
    """
    logger.debug("")
    nsd_show(ctx, name, literal)


@cli_osm.command(name='nspkg-show', short_help='shows the details of a NS package')
@click.option('--literal', is_flag=True,
              help='print literally, no pretty table')
@click.argument('name')
@click.pass_context
def nsd_show2(ctx, name, literal):
    """shows the content of a NSD

    NAME: name or ID of the NSD/NSpkg
    """
    logger.debug("")
    nsd_show(ctx, name, literal)


def vnfd_show(ctx, name, literal):
    logger.debug("")
    # try:
    resp = ctx.obj.vnfd.get(name)
    # resp = ctx.obj.vnfd.get_individual(name)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)

    if literal:
        print(yaml.safe_dump(resp, indent=4, default_flow_style=False))
        return

    table = PrettyTable(['field', 'value'])
    for k, v in list(resp.items()):
        table.add_row([k, wrap_text(text=json.dumps(v, indent=2),width=100)])
    table.align = 'l'
    print(table)


def pkg_repo_show(ctx, pkgtype, name, repo, version, filter, literal):
    logger.debug("")
    # try:
    resp = ctx.obj.osmrepo.pkg_get(pkgtype, name, repo, version, filter)

    if literal:
        print(yaml.safe_dump(resp, indent=4, default_flow_style=False))
        return
    pkgtype += 'd'
    catalog = pkgtype + '-catalog'
    full_catalog = pkgtype + ':' + catalog
    if resp.get(catalog):
        resp = resp.pop(catalog)[pkgtype][0]
    elif resp.get(full_catalog):
        resp = resp.pop(full_catalog)[pkgtype][0]

    table = PrettyTable(['field', 'value'])
    for k, v in list(resp.items()):
        table.add_row([k, wrap_text(text=json.dumps(v, indent=2), width=100)])
    table.align = 'l'
    print(table)

@cli_osm.command(name='vnfd-show', short_help='shows the details of a NF package')
@click.option('--literal', is_flag=True,
              help='print literally, no pretty table')
@click.argument('name')
@click.pass_context
def vnfd_show1(ctx, name, literal):
    """shows the content of a VNFD

    NAME: name or ID of the VNFD/VNFpkg
    """
    logger.debug("")
    vnfd_show(ctx, name, literal)


@cli_osm.command(name='vnfpkg-show', short_help='shows the details of a NF package')
@click.option('--literal', is_flag=True,
              help='print literally, no pretty table')
@click.argument('name')
@click.pass_context
def vnfd_show2(ctx, name, literal):
    """shows the content of a VNFD

    NAME: name or ID of the VNFD/VNFpkg
    """
    logger.debug("")
    vnfd_show(ctx, name, literal)

@cli_osm.command(name='vnfpkg-repo-show', short_help='shows the details of a NF package in an OSM repository')
@click.option('--literal', is_flag=True,
              help='print literally, no pretty table')
@click.option('--repo',
              required=True,
              help='Repository name')
@click.argument('name')
@click.option('--filter',
              help='filter by fields')
@click.option('--version',
              default='latest',
              help='package version')
@click.pass_context
def vnfd_show3(ctx, name, repo, version, literal=None, filter=None):
    """shows the content of a VNFD in a repository

    NAME: name or ID of the VNFD/VNFpkg
    """
    pkgtype = 'vnf'
    pkg_repo_show(ctx, pkgtype, name, repo, version, filter, literal)


@cli_osm.command(name='nsd-repo-show', short_help='shows the details of a NS package in an OSM repository')
@click.option('--literal', is_flag=True,
              help='print literally, no pretty table')
@click.option('--repo',
              required=True,
              help='Repository name')
@click.argument('name')
@click.option('--filter',
              help='filter by fields')
@click.option('--version',
              default='latest',
              help='package version')
@click.pass_context
def nsd_repo_show(ctx, name, repo, version, literal=None, filter=None):
    """shows the content of a VNFD in a repository

    NAME: name or ID of the VNFD/VNFpkg
    """
    pkgtype = 'ns'
    pkg_repo_show(ctx, pkgtype, name, repo, version, filter, literal)

@cli_osm.command(name='nspkg-repo-show', short_help='shows the details of a NS package in an OSM repository')
@click.option('--literal', is_flag=True,
              help='print literally, no pretty table')
@click.option('--repo',
              required=True,
              help='Repository name')
@click.argument('name')
@click.option('--filter',
              help='filter by fields')
@click.option('--version',
              default='latest',
              help='package version')
@click.pass_context
def nsd_repo_show2(ctx, name, repo, version, literal=None, filter=None):
    """shows the content of a VNFD in a repository

    NAME: name or ID of the VNFD/VNFpkg
    """
    pkgtype = 'ns'
    pkg_repo_show(ctx, pkgtype, name, repo, version, filter, literal)

@cli_osm.command(name='nfpkg-show', short_help='shows the details of a NF package')
@click.option('--literal', is_flag=True,
              help='print literally, no pretty table')
@click.argument('name')
@click.pass_context
def nfpkg_show(ctx, name, literal):
    """shows the content of a NF Descriptor

    NAME: name or ID of the NFpkg
    """
    logger.debug("")
    vnfd_show(ctx, name, literal)


@cli_osm.command(name='nfpkg-repo-show', short_help='shows the details of a NF package in an OSM repository')
@click.option('--literal', is_flag=True,
              help='print literally, no pretty table')
@click.option('--repo',
              required=True,
              help='Repository name')
@click.argument('name')
@click.option('--filter',
              help='filter by fields')
@click.option('--version',
              default='latest',
              help='package version')
@click.pass_context
def vnfd_show4(ctx, name, repo, version, literal=None, filter=None):
    """shows the content of a VNFD in a repository

    NAME: name or ID of the VNFD/VNFpkg
    """
    pkgtype = 'vnf'
    pkg_repo_show(ctx, pkgtype, name, repo, version, filter, literal)


@cli_osm.command(name='ns-show', short_help='shows the info of a NS instance')
@click.argument('name')
@click.option('--literal', is_flag=True,
              help='print literally, no pretty table')
@click.option('--filter', default=None)
@click.pass_context
def ns_show(ctx, name, literal, filter):
    """shows the info of a NS instance

    NAME: name or ID of the NS instance
    """
    logger.debug("")
    # try:
    ns = ctx.obj.ns.get(name)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)

    if literal:
        print(yaml.safe_dump(ns, indent=4, default_flow_style=False))
        return

    table = PrettyTable(['field', 'value'])

    for k, v in list(ns.items()):
        if filter is None or filter in k:
            table.add_row([k, wrap_text(text=json.dumps(v, indent=2),width=100)])

    fullclassname = ctx.obj.__module__ + "." + ctx.obj.__class__.__name__
    if fullclassname != 'osmclient.sol005.client.Client':
        nsopdata = ctx.obj.ns.get_opdata(ns['id'])
        nsr_optdata = nsopdata['nsr:nsr']
        for k, v in list(nsr_optdata.items()):
            if filter is None or filter in k:
                table.add_row([k, wrap_text(json.dumps(v, indent=2),width=100)])
    table.align = 'l'
    print(table)


@cli_osm.command(name='vnf-show', short_help='shows the info of a VNF instance')
@click.argument('name')
@click.option('--literal', is_flag=True,
              help='print literally, no pretty table')
@click.option('--filter', default=None, help='restricts the information to the fields in the filter')
@click.option('--kdu', default=None, help='KDU name (whose status will be shown)')
@click.pass_context
def vnf_show(ctx, name, literal, filter, kdu):
    """shows the info of a VNF instance

    NAME: name or ID of the VNF instance
    """
    def print_kdu_status(op_info_status):
        """print KDU status properly formatted
        """
        try:
            op_status = yaml.safe_load(op_info_status)
            if "namespace" in op_status and "info" in op_status and \
            "last_deployed" in op_status["info"] and "status" in op_status["info"] and \
            "code" in op_status["info"]["status"] and "resources" in op_status["info"]["status"] and \
            "seconds" in op_status["info"]["last_deployed"]:
                last_deployed_time = datetime.fromtimestamp(op_status["info"]["last_deployed"]["seconds"]).strftime("%a %b %d %I:%M:%S %Y")
                print("LAST DEPLOYED: {}".format(last_deployed_time))
                print("NAMESPACE: {}".format(op_status["namespace"]))
                status_code = "UNKNOWN"
                if op_status["info"]["status"]["code"]==1:
                    status_code = "DEPLOYED"
                print("STATUS: {}".format(status_code))
                print()
                print("RESOURCES:")
                print(op_status["info"]["status"]["resources"])
                if "notes" in op_status["info"]["status"]:
                    print("NOTES:")
                    print(op_status["info"]["status"]["notes"])
            else:
                print(op_info_status)
        except Exception:
            print(op_info_status)

    logger.debug("")
    if kdu:
        if literal:
            raise ClientException('"--literal" option is incompatible with "--kdu" option')
        if filter:
            raise ClientException('"--filter" option is incompatible with "--kdu" option')

    # try:
    check_client_version(ctx.obj, ctx.command.name)
    resp = ctx.obj.vnf.get(name)

    if kdu:
        ns_id = resp['nsr-id-ref']
        op_data={}
        op_data['member_vnf_index'] = resp['member-vnf-index-ref']
        op_data['kdu_name'] = kdu
        op_data['primitive'] = 'status'
        op_data['primitive_params'] = {}
        op_id = ctx.obj.ns.exec_op(ns_id, op_name='action', op_data=op_data, wait=False)
        t = 0
        while t<30:
            op_info = ctx.obj.ns.get_op(op_id)
            if op_info['operationState'] == 'COMPLETED':
                print_kdu_status(op_info['detailed-status'])
                return
            time.sleep(5)
            t += 5
        print ("Could not determine KDU status")
        return

    if literal:
        print(yaml.safe_dump(resp, indent=4, default_flow_style=False))
        return

    table = PrettyTable(['field', 'value'])

    for k, v in list(resp.items()):
        if filter is None or filter in k:
            table.add_row([k, wrap_text(text=json.dumps(v,indent=2),width=100)])
    table.align = 'l'
    print(table)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


#@cli_osm.command(name='vnf-monitoring-show')
#@click.argument('vnf_name')
#@click.pass_context
#def vnf_monitoring_show(ctx, vnf_name):
#    try:
#        check_client_version(ctx.obj, ctx.command.name, 'v1')
#        resp = ctx.obj.vnf.get_monitoring(vnf_name)
#    except ClientException as e:
#        print(str(e))
#        exit(1)
#
#    table = PrettyTable(['vnf name', 'monitoring name', 'value', 'units'])
#    if resp is not None:
#        for monitor in resp:
#            table.add_row(
#                [vnf_name,
#                 monitor['name'],
#                    monitor['value-integer'],
#                    monitor['units']])
#    table.align = 'l'
#    print(table)


#@cli_osm.command(name='ns-monitoring-show')
#@click.argument('ns_name')
#@click.pass_context
#def ns_monitoring_show(ctx, ns_name):
#    try:
#        check_client_version(ctx.obj, ctx.command.name, 'v1')
#        resp = ctx.obj.ns.get_monitoring(ns_name)
#    except ClientException as e:
#        print(str(e))
#        exit(1)
#
#    table = PrettyTable(['vnf name', 'monitoring name', 'value', 'units'])
#    for key, val in list(resp.items()):
#        for monitor in val:
#            table.add_row(
#                [key,
#                 monitor['name'],
#                    monitor['value-integer'],
#                    monitor['units']])
#    table.align = 'l'
#    print(table)


@cli_osm.command(name='ns-op-show', short_help='shows the info of a NS operation')
@click.argument('id')
@click.option('--filter', default=None)
@click.option('--literal', is_flag=True,
              help='print literally, no pretty table')
@click.pass_context
def ns_op_show(ctx, id, filter, literal):
    """shows the detailed info of a NS operation

    ID: operation identifier
    """
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    op_info = ctx.obj.ns.get_op(id)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)

    if literal:
        print(yaml.safe_dump(op_info, indent=4, default_flow_style=False))
        return

    table = PrettyTable(['field', 'value'])
    for k, v in list(op_info.items()):
        if filter is None or filter in k:
            table.add_row([k, wrap_text(json.dumps(v, indent=2), 100)])
    table.align = 'l'
    print(table)


def nst_show(ctx, name, literal):
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    resp = ctx.obj.nst.get(name)
    #resp = ctx.obj.nst.get_individual(name)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)

    if literal:
        print(yaml.safe_dump(resp, indent=4, default_flow_style=False))
        return

    table = PrettyTable(['field', 'value'])
    for k, v in list(resp.items()):
        table.add_row([k, wrap_text(json.dumps(v, indent=2), 100)])
    table.align = 'l'
    print(table)


@cli_osm.command(name='nst-show', short_help='shows the content of a Network Slice Template (NST)')
@click.option('--literal', is_flag=True,
              help='print literally, no pretty table')
@click.argument('name')
@click.pass_context
def nst_show1(ctx, name, literal):
    """shows the content of a Network Slice Template (NST)

    NAME: name or ID of the NST
    """
    logger.debug("")
    nst_show(ctx, name, literal)


@cli_osm.command(name='netslice-template-show', short_help='shows the content of a Network Slice Template (NST)')
@click.option('--literal', is_flag=True,
              help='print literally, no pretty table')
@click.argument('name')
@click.pass_context
def nst_show2(ctx, name, literal):
    """shows the content of a Network Slice Template (NST)

    NAME: name or ID of the NST
    """
    logger.debug("")
    nst_show(ctx, name, literal)


def nsi_show(ctx, name, literal, filter):
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    nsi = ctx.obj.nsi.get(name)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)

    if literal:
        print(yaml.safe_dump(nsi, indent=4, default_flow_style=False))
        return

    table = PrettyTable(['field', 'value'])

    for k, v in list(nsi.items()):
        if filter is None or filter in k:
            table.add_row([k, json.dumps(v, indent=2)])

    table.align = 'l'
    print(table)


@cli_osm.command(name='nsi-show', short_help='shows the content of a Network Slice Instance (NSI)')
@click.argument('name')
@click.option('--literal', is_flag=True,
              help='print literally, no pretty table')
@click.option('--filter', default=None)
@click.pass_context
def nsi_show1(ctx, name, literal, filter):
    """shows the content of a Network Slice Instance (NSI)

    NAME: name or ID of the Network Slice Instance
    """
    logger.debug("")
    nsi_show(ctx, name, literal, filter)


@cli_osm.command(name='netslice-instance-show', short_help='shows the content of a Network Slice Instance (NSI)')
@click.argument('name')
@click.option('--literal', is_flag=True,
              help='print literally, no pretty table')
@click.option('--filter', default=None)
@click.pass_context
def nsi_show2(ctx, name, literal, filter):
    """shows the content of a Network Slice Instance (NSI)

    NAME: name or ID of the Network Slice Instance
    """
    logger.debug("")
    nsi_show(ctx, name, literal, filter)


def nsi_op_show(ctx, id, filter):
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    op_info = ctx.obj.nsi.get_op(id)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)

    table = PrettyTable(['field', 'value'])
    for k, v in list(op_info.items()):
        if filter is None or filter in k:
            table.add_row([k, json.dumps(v, indent=2)])
    table.align = 'l'
    print(table)


@cli_osm.command(name='nsi-op-show', short_help='shows the info of an operation over a Network Slice Instance(NSI)')
@click.argument('id')
@click.option('--filter', default=None)
@click.pass_context
def nsi_op_show1(ctx, id, filter):
    """shows the info of an operation over a Network Slice Instance(NSI)

    ID: operation identifier
    """
    logger.debug("")
    nsi_op_show(ctx, id, filter)


@cli_osm.command(name='netslice-instance-op-show', short_help='shows the info of an operation over a Network Slice Instance(NSI)')
@click.argument('id')
@click.option('--filter', default=None)
@click.pass_context
def nsi_op_show2(ctx, id, filter):
    """shows the info of an operation over a Network Slice Instance(NSI)

    ID: operation identifier
    """
    logger.debug("")
    nsi_op_show(ctx, id, filter)


@cli_osm.command(name='pdu-show', short_help='shows the content of a Physical Deployment Unit (PDU)')
@click.argument('name')
@click.option('--literal', is_flag=True,
              help='print literally, no pretty table')
@click.option('--filter', default=None)
@click.pass_context
def pdu_show(ctx, name, literal, filter):
    """shows the content of a Physical Deployment Unit (PDU)

    NAME: name or ID of the PDU
    """
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    pdu = ctx.obj.pdu.get(name)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)

    if literal:
        print(yaml.safe_dump(pdu, indent=4, default_flow_style=False))
        return

    table = PrettyTable(['field', 'value'])

    for k, v in list(pdu.items()):
        if filter is None or filter in k:
            table.add_row([k, json.dumps(v, indent=2)])

    table.align = 'l'
    print(table)


####################
# CREATE operations
####################

def nsd_create(ctx, filename, overwrite, skip_charm_build, repo, vendor, version):
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    if repo:
        filename = ctx.obj.osmrepo.get_pkg('ns', filename, repo, vendor, version)
    ctx.obj.nsd.create(filename, overwrite=overwrite, skip_charm_build=skip_charm_build)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='nsd-create', short_help='creates a new NSD/NSpkg')
@click.argument('filename')
@click.option('--overwrite', 'overwrite', default=None,  # hidden=True,
              help='Deprecated. Use override')
@click.option('--override', 'overwrite', default=None,
              help='overrides fields in descriptor, format: '
                   '"key1.key2...=value[;key3...=value;...]"')
@click.option('--skip-charm-build', default=False, is_flag=True,
              help='The charm will not be compiled, it is assumed to already exist')
@click.option('--repo', default=None,
              help='[repository]: Repository name')
@click.option('--vendor', default=None,
              help='[repository]: filter by vendor]')
@click.option('--version', default='latest',
              help='[repository]: filter by version. Default: latest')
@click.pass_context
def nsd_create1(ctx, filename, overwrite, skip_charm_build, repo, vendor, version):
    """onboards a new NSpkg (alias of nspkg-create) (TO BE DEPRECATED)

    \b
    FILENAME: NF Package tar.gz file, NF Descriptor YAML file or NF Package folder
              If FILENAME is a file (NF Package tar.gz or NF Descriptor YAML), it is onboarded.
              If FILENAME is an NF Package folder, it is built and then onboarded.
    """
    logger.debug("")
    nsd_create(ctx, filename, overwrite=overwrite, skip_charm_build=skip_charm_build, repo=repo, vendor=vendor,
               version=version)


@cli_osm.command(name='nspkg-create', short_help='creates a new NSD/NSpkg')
@click.argument('filename')
@click.option('--overwrite', 'overwrite', default=None,  # hidden=True,
              help='Deprecated. Use override')
@click.option('--override', 'overwrite', default=None,
              help='overrides fields in descriptor, format: '
                   '"key1.key2...=value[;key3...=value;...]"')
@click.option('--skip-charm-build', default=False, is_flag=True,
              help='The charm will not be compiled, it is assumed to already exist')
@click.option('--repo', default=None,
              help='[repository]: Repository name')
@click.option('--vendor', default=None,
              help='[repository]: filter by vendor]')
@click.option('--version', default='latest',
              help='[repository]: filter by version. Default: latest')
@click.pass_context
def nsd_pkg_create(ctx, filename, overwrite, skip_charm_build, repo, vendor, version):
    """onboards a new NSpkg
    \b
    FILENAME: NF Package tar.gz file, NF Descriptor YAML file or NF Package folder
              If FILENAME is a file (NF Package tar.gz or NF Descriptor YAML), it is onboarded.
              If FILENAME is an NF Package folder, it is built and then onboarded.
    """
    logger.debug("")
    nsd_create(ctx, filename, overwrite=overwrite, skip_charm_build=skip_charm_build, repo=repo, vendor=vendor,
               version=version)


def vnfd_create(ctx, filename, overwrite, skip_charm_build, override_epa, override_nonepa, override_paravirt,
                repo, vendor, version):
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    if repo:
        filename = ctx.obj.osmrepo.get_pkg('vnf', filename, repo, vendor, version)
    ctx.obj.vnfd.create(filename, overwrite=overwrite, skip_charm_build=skip_charm_build,
                        override_epa=override_epa, override_nonepa=override_nonepa,
                        override_paravirt=override_paravirt)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='vnfd-create', short_help='creates a new VNFD/VNFpkg')
@click.argument('filename')
@click.option('--overwrite', 'overwrite', default=None,
              help='overwrite deprecated, use override')
@click.option('--override', 'overwrite', default=None,
              help='overrides fields in descriptor, format: '
                   '"key1.key2...=value[;key3...=value;...]"')
@click.option('--skip-charm-build', default=False, is_flag=True,
              help='The charm will not be compiled, it is assumed to already exist')
@click.option('--override-epa', required=False, default=False, is_flag=True,
              help='adds guest-epa parameters to all VDU')
@click.option('--override-nonepa', required=False, default=False, is_flag=True,
              help='removes all guest-epa parameters from all VDU')
@click.option('--override-paravirt', required=False, default=False, is_flag=True,
              help='overrides all VDU interfaces to PARAVIRT')
@click.option('--repo', default=None,
              help='[repository]: Repository name')
@click.option('--vendor', default=None,
              help='[repository]: filter by vendor]')
@click.option('--version', default='latest',
              help='[repository]: filter by version. Default: latest')
@click.pass_context
def vnfd_create1(ctx, filename, overwrite, skip_charm_build, override_epa, override_nonepa, override_paravirt,
                 repo,vendor, version):
    """creates a new VNFD/VNFpkg
    \b
    FILENAME: NF Package tar.gz file, NF Descriptor YAML file or NF Package folder
              If FILENAME is a file (NF Package tar.gz or NF Descriptor YAML), it is onboarded.
              If FILENAME is an NF Package folder, it is built and then onboarded.
    """
    logger.debug("")
    vnfd_create(ctx, filename, overwrite=overwrite, skip_charm_build=skip_charm_build,
                override_epa=override_epa, override_nonepa=override_nonepa, override_paravirt=override_paravirt,
                repo=repo, vendor=vendor, version=version)


@cli_osm.command(name='vnfpkg-create', short_help='creates a new VNFD/VNFpkg')
@click.argument('filename')
@click.option('--overwrite', 'overwrite', default=None,  # hidden=True,
              help='Deprecated. Use override')
@click.option('--override', 'overwrite', default=None,
              help='overrides fields in descriptor, format: '
                   '"key1.key2...=value[;key3...=value;...]"')
@click.option('--skip-charm-build', default=False, is_flag=True,
              help='The charm will not be compiled, it is assumed to already exist')
@click.option('--override-epa', required=False, default=False, is_flag=True,
              help='adds guest-epa parameters to all VDU')
@click.option('--override-nonepa', required=False, default=False, is_flag=True,
              help='removes all guest-epa parameters from all VDU')
@click.option('--override-paravirt', required=False, default=False, is_flag=True,
              help='overrides all VDU interfaces to PARAVIRT')
@click.option('--repo', default=None,
              help='[repository]: Repository name')
@click.option('--vendor', default=None,
              help='[repository]: filter by vendor]')
@click.option('--version', default='latest',
              help='[repository]: filter by version. Default: latest')
@click.pass_context
def vnfd_create2(ctx, filename, overwrite, skip_charm_build, override_epa, override_nonepa, override_paravirt,
                 repo, vendor, version):
    """creates a new VNFD/VNFpkg
    \b
    FILENAME: NF Package tar.gz file, NF Descriptor YAML file or NF Package folder
              If FILENAME is a file (NF Package tar.gz or NF Descriptor YAML), it is onboarded.
              If FILENAME is an NF Package folder, it is built and then onboarded.
    """
    logger.debug("")
    vnfd_create(ctx, filename, overwrite=overwrite, skip_charm_build=skip_charm_build,
                override_epa=override_epa, override_nonepa=override_nonepa, override_paravirt=override_paravirt,
                repo=repo, vendor=vendor, version=version)

@cli_osm.command(name='nfpkg-create', short_help='creates a new NFpkg')
@click.argument('filename')
@click.option('--overwrite', 'overwrite', default=None,  # hidden=True,
              help='Deprecated. Use override')
@click.option('--override', 'overwrite', default=None,
              help='overrides fields in descriptor, format: '
                   '"key1.key2...=value[;key3...=value;...]"')
@click.option('--skip-charm-build', default=False, is_flag=True,
              help='The charm will not be compiled, it is assumed to already exist')
@click.option('--override-epa', required=False, default=False, is_flag=True,
              help='adds guest-epa parameters to all VDU')
@click.option('--override-nonepa', required=False, default=False, is_flag=True,
              help='removes all guest-epa parameters from all VDU')
@click.option('--override-paravirt', required=False, default=False, is_flag=True,
              help='overrides all VDU interfaces to PARAVIRT')
@click.option('--repo', default=None,
              help='[repository]: Repository name')
@click.option('--vendor', default=None,
              help='[repository]: filter by vendor]')
@click.option('--version', default='latest',
              help='[repository]: filter by version. Default: latest')
@click.pass_context
def nfpkg_create(ctx, filename, overwrite, skip_charm_build, override_epa, override_nonepa, override_paravirt,
                 repo, vendor, version):
    """creates a new NFpkg

    \b
    FILENAME: NF Package tar.gz file, NF Descriptor YAML file or NF Package folder
              If FILENAME is a file (NF Package tar.gz or NF Descriptor YAML), it is onboarded.
              If FILENAME is an NF Package folder, it is built and then onboarded.
    """
    logger.debug("")
    vnfd_create(ctx, filename, overwrite=overwrite, skip_charm_build=skip_charm_build,
                override_epa=override_epa, override_nonepa=override_nonepa, override_paravirt=override_paravirt,
                repo=repo, vendor=vendor, version=version)


@cli_osm.command(name='ns-create', short_help='creates a new Network Service instance')
@click.option('--ns_name',
              prompt=True, help='name of the NS instance')
@click.option('--nsd_name',
              prompt=True, help='name of the NS descriptor')
@click.option('--vim_account',
              prompt=True, help='default VIM account id or name for the deployment')
@click.option('--admin_status',
              default='ENABLED',
              help='administration status')
@click.option('--ssh_keys',
              default=None,
              help='comma separated list of public key files to inject to vnfs')
@click.option('--config',
              default=None,
              help='ns specific yaml configuration')
@click.option('--config_file',
              default=None,
              help='ns specific yaml configuration file')
@click.option('--wait',
              required=False,
              default=False,
              is_flag=True,
              help='do not return the control immediately, but keep it '
                   'until the operation is completed, or timeout')
@click.pass_context
def ns_create(ctx,
              nsd_name,
              ns_name,
              vim_account,
              admin_status,
              ssh_keys,
              config,
              config_file,
              wait):
    """creates a new NS instance"""
    logger.debug("")
    # try:
    if config_file:
        check_client_version(ctx.obj, '--config_file')
        if config:
            raise ClientException('"--config" option is incompatible with "--config_file" option')
        with open(config_file, 'r') as cf:
            config=cf.read()
    ctx.obj.ns.create(
        nsd_name,
        ns_name,
        config=config,
        ssh_keys=ssh_keys,
        account=vim_account,
        wait=wait)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)

################################################ create2 operation

@cli_osm.command(name='ns-create2', short_help='creates a new Network Service instance allowing distribution')
@click.option('--ns_name',
              prompt=True, help='name of the NS instance')
@click.option('--nsd_name',
              prompt=True, help='name of the NS descriptor')
#@click.option('--vim_account',
#              prompt=True, help='default VIM account id or name for the deployment')
@click.option('--admin_status',
              default='ENABLED',
              help='administration status')
@click.option('--ssh_keys',
              default=None,
              help='comma separated list of public key files to inject to vnfs')
@click.option('--distribution',
              default=None,
              help='distribution of the vnfs in the different available vims')
@click.option('--config',
              default=None,
              help='ns specific yaml configuration')
@click.option('--config_file',
              default=None,
              help='ns specific yaml configuration file')
@click.option('--wait',
              required=False,
              default=False,
              is_flag=True,
              help='do not return the control immediately, but keep it '
                   'until the operation is completed, or timeout')
@click.pass_context
def ns_create2(ctx,
              nsd_name,
              ns_name,
              #vim_account,
              admin_status,
              ssh_keys,
              distribution,
              config,
              config_file,
              wait):
    """creates a new NS instance accepting a VNF distribution"""
    logger.debug("")
    # try:
    if config_file:
        check_client_version(ctx.obj, '--config_file')
        if config:
            raise ClientException('"--config" option is incompatible with "--config_file" option')
        with open(config_file, 'r') as cf:
            config=cf.read()
    ctx.obj.ns.create2(
        nsd_name,
        ns_name,
        distribution=distribution,
        config=config,
        ssh_keys=ssh_keys,
        #account=vim_account,
        wait=wait)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)

###################################################################


def nst_create(ctx, filename, overwrite):
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    ctx.obj.nst.create(filename, overwrite)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='nst-create', short_help='creates a new Network Slice Template (NST)')
@click.argument('filename')
@click.option('--overwrite', 'overwrite', default=None,  # hidden=True,
              help='Deprecated. Use override')
@click.option('--override', 'overwrite', default=None,
              help='overrides fields in descriptor, format: '
                   '"key1.key2...=value[;key3...=value;...]"')
@click.pass_context
def nst_create1(ctx, filename, overwrite):
    """creates a new Network Slice Template (NST)

    FILENAME: NST package folder, NST yaml file or NSTpkg tar.gz file
    """
    logger.debug("")
    nst_create(ctx, filename, overwrite)


@cli_osm.command(name='netslice-template-create', short_help='creates a new Network Slice Template (NST)')
@click.argument('filename')
@click.option('--overwrite', 'overwrite', default=None,  # hidden=True,
              help='Deprecated. Use override')
@click.option('--override', 'overwrite', default=None,
              help='overrides fields in descriptor, format: '
                   '"key1.key2...=value[;key3...=value;...]"')
@click.pass_context
def nst_create2(ctx, filename, overwrite):
    """creates a new Network Slice Template (NST)

    FILENAME: NST yaml file or NSTpkg tar.gz file
    """
    logger.debug("")
    nst_create(ctx, filename, overwrite)


def nsi_create(ctx, nst_name, nsi_name, vim_account, ssh_keys, config, config_file, wait):
    """creates a new Network Slice Instance (NSI)"""
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    if config_file:
        if config:
            raise ClientException('"--config" option is incompatible with "--config_file" option')
        with open(config_file, 'r') as cf:
            config=cf.read()
    ctx.obj.nsi.create(nst_name, nsi_name, config=config, ssh_keys=ssh_keys,
                       account=vim_account, wait=wait)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='nsi-create', short_help='creates a new Network Slice Instance')
@click.option('--nsi_name', prompt=True, help='name of the Network Slice Instance')
@click.option('--nst_name', prompt=True, help='name of the Network Slice Template')
@click.option('--vim_account', prompt=True, help='default VIM account id or name for the deployment')
@click.option('--ssh_keys', default=None,
              help='comma separated list of keys to inject to vnfs')
@click.option('--config', default=None,
              help='Netslice specific yaml configuration:\n'
              'netslice_subnet: [\n'
                'id: TEXT, vim_account: TEXT,\n'
                'vnf: [member-vnf-index: TEXT, vim_account: TEXT]\n'
                'vld: [name: TEXT, vim-network-name: TEXT or DICT with vim_account, vim_net entries]\n'
                'additionalParamsForNsi: {param: value, ...}\n'
                'additionalParamsForsubnet: [{id: SUBNET_ID, additionalParamsForNs: {}, additionalParamsForVnf: {}}]\n'
              '],\n'
              'netslice-vld: [name: TEXT, vim-network-name: TEXT or DICT with vim_account, vim_net entries]'
              )
@click.option('--config_file',
              default=None,
              help='nsi specific yaml configuration file')
@click.option('--wait',
              required=False,
              default=False,
              is_flag=True,
              help='do not return the control immediately, but keep it '
                   'until the operation is completed, or timeout')
@click.pass_context
def nsi_create1(ctx, nst_name, nsi_name, vim_account, ssh_keys, config, config_file, wait):
    """creates a new Network Slice Instance (NSI)"""
    logger.debug("")
    nsi_create(ctx, nst_name, nsi_name, vim_account, ssh_keys, config, config_file, wait=wait)


@cli_osm.command(name='netslice-instance-create', short_help='creates a new Network Slice Instance')
@click.option('--nsi_name', prompt=True, help='name of the Network Slice Instance')
@click.option('--nst_name', prompt=True, help='name of the Network Slice Template')
@click.option('--vim_account', prompt=True, help='default VIM account id or name for the deployment')
@click.option('--ssh_keys', default=None,
              help='comma separated list of keys to inject to vnfs')
@click.option('--config', default=None,
              help='Netslice specific yaml configuration:\n'
              'netslice_subnet: [\n'
                'id: TEXT, vim_account: TEXT,\n'
                'vnf: [member-vnf-index: TEXT, vim_account: TEXT]\n'
                'vld: [name: TEXT, vim-network-name: TEXT or DICT with vim_account, vim_net entries]'
              '],\n'
              'netslice-vld: [name: TEXT, vim-network-name: TEXT or DICT with vim_account, vim_net entries]'
              )
@click.option('--config_file',
              default=None,
              help='nsi specific yaml configuration file')
@click.option('--wait',
              required=False,
              default=False,
              is_flag=True,
              help='do not return the control immediately, but keep it '
                   'until the operation is completed, or timeout')
@click.pass_context
def nsi_create2(ctx, nst_name, nsi_name, vim_account, ssh_keys, config, config_file, wait):
    """creates a new Network Slice Instance (NSI)"""
    logger.debug("")
    nsi_create(ctx, nst_name, nsi_name, vim_account, ssh_keys, config, config_file, wait=wait)


@cli_osm.command(name='pdu-create', short_help='adds a new Physical Deployment Unit to the catalog')
@click.option('--name', help='name of the Physical Deployment Unit')
@click.option('--pdu_type', help='type of PDU (e.g. router, firewall, FW001)')
@click.option('--interface',
              help='interface(s) of the PDU: name=<NAME>,mgmt=<true|false>,ip-address=<IP_ADDRESS>'+
                   '[,type=<overlay|underlay>][,mac-address=<MAC_ADDRESS>][,vim-network-name=<VIM_NET_NAME>]',
              multiple=True)
@click.option('--description', help='human readable description')
@click.option('--vim_account', help='list of VIM accounts (in the same VIM) that can reach this PDU', multiple=True)
@click.option('--descriptor_file', default=None,
              help='PDU descriptor file (as an alternative to using the other arguments')
@click.pass_context
def pdu_create(ctx, name, pdu_type, interface, description, vim_account, descriptor_file):
    """creates a new Physical Deployment Unit (PDU)"""
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    pdu = {}
    if not descriptor_file:
        if not name:
            raise ClientException('in absence of descriptor file, option "--name" is mandatory')
        if not pdu_type:
            raise ClientException('in absence of descriptor file, option "--pdu_type" is mandatory')
        if not interface:
            raise ClientException('in absence of descriptor file, option "--interface" is mandatory (at least once)')
        if not vim_account:
            raise ClientException('in absence of descriptor file, option "--vim_account" is mandatory (at least once)')
    else:
        with open(descriptor_file, 'r') as df:
            pdu = yaml.safe_load(df.read())
    if name: pdu["name"] = name
    if pdu_type: pdu["type"] = pdu_type
    if description: pdu["description"] = description
    if vim_account: pdu["vim_accounts"] = vim_account
    if interface:
        ifaces_list = []
        for iface in interface:
            new_iface={k:v for k,v in [i.split('=') for i in iface.split(',')]}
            new_iface["mgmt"] = (new_iface.get("mgmt","false").lower() == "true")
            ifaces_list.append(new_iface)
        pdu["interfaces"] = ifaces_list
    ctx.obj.pdu.create(pdu)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


####################
# UPDATE operations
####################

def nsd_update(ctx, name, content):
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    ctx.obj.nsd.update(name, content)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='nsd-update', short_help='updates a NSD/NSpkg')
@click.argument('name')
@click.option('--content', default=None,
              help='filename with the NSD/NSpkg replacing the current one')
@click.pass_context
def nsd_update1(ctx, name, content):
    """updates a NSD/NSpkg

    NAME: name or ID of the NSD/NSpkg
    """
    logger.debug("")
    nsd_update(ctx, name, content)


@cli_osm.command(name='nspkg-update', short_help='updates a NSD/NSpkg')
@click.argument('name')
@click.option('--content', default=None,
              help='filename with the NSD/NSpkg replacing the current one')
@click.pass_context
def nsd_update2(ctx, name, content):
    """updates a NSD/NSpkg

    NAME: name or ID of the NSD/NSpkg
    """
    logger.debug("")
    nsd_update(ctx, name, content)


def vnfd_update(ctx, name, content):
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    ctx.obj.vnfd.update(name, content)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='vnfd-update', short_help='updates a new VNFD/VNFpkg')
@click.argument('name')
@click.option('--content', default=None,
              help='filename with the VNFD/VNFpkg replacing the current one')
@click.pass_context
def vnfd_update1(ctx, name, content):
    """updates a VNFD/VNFpkg

    NAME: name or ID of the VNFD/VNFpkg
    """
    logger.debug("")
    vnfd_update(ctx, name, content)


@cli_osm.command(name='vnfpkg-update', short_help='updates a VNFD/VNFpkg')
@click.argument('name')
@click.option('--content', default=None,
              help='filename with the VNFD/VNFpkg replacing the current one')
@click.pass_context
def vnfd_update2(ctx, name, content):
    """updates a VNFD/VNFpkg

    NAME: VNFD yaml file or VNFpkg tar.gz file
    """
    logger.debug("")
    vnfd_update(ctx, name, content)


@cli_osm.command(name='nfpkg-update', short_help='updates a NFpkg')
@click.argument('name')
@click.option('--content', default=None,
              help='filename with the NFpkg replacing the current one')
@click.pass_context
def nfpkg_update(ctx, name, content):
    """updates a NFpkg

    NAME: NF Descriptor yaml file or NFpkg tar.gz file
    """
    logger.debug("")
    vnfd_update(ctx, name, content)


def nst_update(ctx, name, content):
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    ctx.obj.nst.update(name, content)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='nst-update', short_help='updates a Network Slice Template (NST)')
@click.argument('name')
@click.option('--content', default=None,
              help='filename with the NST/NSTpkg replacing the current one')
@click.pass_context
def nst_update1(ctx, name, content):
    """updates a Network Slice Template (NST)

    NAME: name or ID of the NSD/NSpkg
    """
    logger.debug("")
    nst_update(ctx, name, content)


@cli_osm.command(name='netslice-template-update', short_help='updates a Network Slice Template (NST)')
@click.argument('name')
@click.option('--content', default=None,
              help='filename with the NST/NSTpkg replacing the current one')
@click.pass_context
def nst_update2(ctx, name, content):
    """updates a Network Slice Template (NST)

    NAME: name or ID of the NSD/NSpkg
    """
    logger.debug("")
    nst_update(ctx, name, content)


####################
# DELETE operations
####################

def nsd_delete(ctx, name, force):
    logger.debug("")
    # try:
    if not force:
        ctx.obj.nsd.delete(name)
    else:
        check_client_version(ctx.obj, '--force')
        ctx.obj.nsd.delete(name, force)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='nsd-delete', short_help='deletes a NSD/NSpkg')
@click.argument('name')
@click.option('--force', is_flag=True, help='forces the deletion bypassing pre-conditions')
@click.pass_context
def nsd_delete1(ctx, name, force):
    """deletes a NSD/NSpkg

    NAME: name or ID of the NSD/NSpkg to be deleted
    """
    logger.debug("")
    nsd_delete(ctx, name, force)


@cli_osm.command(name='nspkg-delete', short_help='deletes a NSD/NSpkg')
@click.argument('name')
@click.option('--force', is_flag=True, help='forces the deletion bypassing pre-conditions')
@click.pass_context
def nsd_delete2(ctx, name, force):
    """deletes a NSD/NSpkg

    NAME: name or ID of the NSD/NSpkg to be deleted
    """
    logger.debug("")
    nsd_delete(ctx, name, force)


def vnfd_delete(ctx, name, force):
    logger.debug("")
    # try:
    if not force:
        ctx.obj.vnfd.delete(name)
    else:
        check_client_version(ctx.obj, '--force')
        ctx.obj.vnfd.delete(name, force)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='vnfd-delete', short_help='deletes a VNFD/VNFpkg')
@click.argument('name')
@click.option('--force', is_flag=True, help='forces the deletion bypassing pre-conditions')
@click.pass_context
def vnfd_delete1(ctx, name, force):
    """deletes a VNFD/VNFpkg

    NAME: name or ID of the VNFD/VNFpkg to be deleted
    """
    logger.debug("")
    vnfd_delete(ctx, name, force)


@cli_osm.command(name='vnfpkg-delete', short_help='deletes a VNFD/VNFpkg')
@click.argument('name')
@click.option('--force', is_flag=True, help='forces the deletion bypassing pre-conditions')
@click.pass_context
def vnfd_delete2(ctx, name, force):
    """deletes a VNFD/VNFpkg

    NAME: name or ID of the VNFD/VNFpkg to be deleted
    """
    logger.debug("")
    vnfd_delete(ctx, name, force)


@cli_osm.command(name='nfpkg-delete', short_help='deletes a NFpkg')
@click.argument('name')
@click.option('--force', is_flag=True, help='forces the deletion bypassing pre-conditions')
@click.pass_context
def nfpkg_delete(ctx, name, force):
    """deletes a NFpkg

    NAME: name or ID of the NFpkg to be deleted
    """
    logger.debug("")
    vnfd_delete(ctx, name, force)


@cli_osm.command(name='ns-delete', short_help='deletes a NS instance')
@click.argument('name')
@click.option('--force', is_flag=True, help='forces the deletion bypassing pre-conditions')
@click.option('--config', default=None,
              help="specific yaml configuration for the termination, e.g. '{autoremove: False, timeout_ns_terminate: "
                   "600, skip_terminate_primitives: True}'")
@click.option('--wait',
              required=False,
              default=False,
              is_flag=True,
              help='do not return the control immediately, but keep it '
                   'until the operation is completed, or timeout')
@click.pass_context
def ns_delete(ctx, name, force, config, wait):
    """deletes a NS instance

    NAME: name or ID of the NS instance to be deleted
    """
    logger.debug("")
    # try:
    if not force:
        ctx.obj.ns.delete(name, config=config, wait=wait)
    else:
        check_client_version(ctx.obj, '--force')
        ctx.obj.ns.delete(name, force, config=config, wait=wait)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


def nst_delete(ctx, name, force):
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    ctx.obj.nst.delete(name, force)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='nst-delete', short_help='deletes a Network Slice Template (NST)')
@click.argument('name')
@click.option('--force', is_flag=True, help='forces the deletion bypassing pre-conditions')
@click.pass_context
def nst_delete1(ctx, name, force):
    """deletes a Network Slice Template (NST)

    NAME: name or ID of the NST/NSTpkg to be deleted
    """
    logger.debug("")
    nst_delete(ctx, name, force)


@cli_osm.command(name='netslice-template-delete', short_help='deletes a Network Slice Template (NST)')
@click.argument('name')
@click.option('--force', is_flag=True, help='forces the deletion bypassing pre-conditions')
@click.pass_context
def nst_delete2(ctx, name, force):
    """deletes a Network Slice Template (NST)

    NAME: name or ID of the NST/NSTpkg to be deleted
    """
    logger.debug("")
    nst_delete(ctx, name, force)


def nsi_delete(ctx, name, force, wait):
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    ctx.obj.nsi.delete(name, force, wait=wait)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='nsi-delete', short_help='deletes a Network Slice Instance (NSI)')
@click.argument('name')
@click.option('--force', is_flag=True, help='forces the deletion bypassing pre-conditions')
@click.option('--wait',
              required=False,
              default=False,
              is_flag=True,
              help='do not return the control immediately, but keep it '
                   'until the operation is completed, or timeout')
@click.pass_context
def nsi_delete1(ctx, name, force, wait):
    """deletes a Network Slice Instance (NSI)

    NAME: name or ID of the Network Slice instance to be deleted
    """
    logger.debug("")
    nsi_delete(ctx, name, force, wait=wait)


@cli_osm.command(name='netslice-instance-delete', short_help='deletes a Network Slice Instance (NSI)')
@click.argument('name')
@click.option('--force', is_flag=True, help='forces the deletion bypassing pre-conditions')
@click.pass_context
def nsi_delete2(ctx, name, force, wait):
    """deletes a Network Slice Instance (NSI)

    NAME: name or ID of the Network Slice instance to be deleted
    """
    logger.debug("")
    nsi_delete(ctx, name, force, wait=wait)


@cli_osm.command(name='pdu-delete', short_help='deletes a Physical Deployment Unit (PDU)')
@click.argument('name')
@click.option('--force', is_flag=True, help='forces the deletion bypassing pre-conditions')
@click.pass_context
def pdu_delete(ctx, name, force):
    """deletes a Physical Deployment Unit (PDU)

    NAME: name or ID of the PDU to be deleted
    """
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    ctx.obj.pdu.delete(name, force)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


#################
# VIM operations
#################

@cli_osm.command(name='vim-create', short_help='creates a new VIM account')
@click.option('--name',
              prompt=True,
              help='Name to create datacenter')
@click.option('--user',
              prompt=True,
              help='VIM username')
@click.option('--password',
              prompt=True,
              hide_input=True,
              confirmation_prompt=True,
              help='VIM password')
@click.option('--auth_url',
              prompt=True,
              help='VIM url')
@click.option('--tenant',
              prompt=True,
              help='VIM tenant name')
@click.option('--config',
              default=None,
              help='VIM specific config parameters')
@click.option('--account_type',
              default='openstack',
              help='VIM type')
@click.option('--description',
              default=None,
              help='human readable description')
@click.option('--sdn_controller', default=None, help='Name or id of the SDN controller associated to this VIM account')
@click.option('--sdn_port_mapping', default=None, help="File describing the port mapping between compute nodes' ports and switch ports")
@click.option('--wait',
              required=False,
              default=False,
              is_flag=True,
              help='do not return the control immediately, but keep it '
                   'until the operation is completed, or timeout')
@click.pass_context
def vim_create(ctx,
               name,
               user,
               password,
               auth_url,
               tenant,
               config,
               account_type,
               description,
               sdn_controller,
               sdn_port_mapping,
               wait):
    """creates a new VIM account"""
    logger.debug("")
    # try:
    if sdn_controller:
        check_client_version(ctx.obj, '--sdn_controller')
    if sdn_port_mapping:
        check_client_version(ctx.obj, '--sdn_port_mapping')
    vim = {}
    vim['vim-username'] = user
    vim['vim-password'] = password
    vim['vim-url'] = auth_url
    vim['vim-tenant-name'] = tenant
    vim['vim-type'] = account_type
    vim['description'] = description
    vim['config'] = config
    if sdn_controller or sdn_port_mapping:
        ctx.obj.vim.create(name, vim, sdn_controller, sdn_port_mapping, wait=wait)
    else:
        ctx.obj.vim.create(name, vim, wait=wait)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='vim-update', short_help='updates a VIM account')
@click.argument('name')
@click.option('--newname', help='New name for the VIM account')
@click.option('--user', help='VIM username')
@click.option('--password', help='VIM password')
@click.option('--auth_url', help='VIM url')
@click.option('--tenant', help='VIM tenant name')
@click.option('--config', help='VIM specific config parameters')
@click.option('--account_type', help='VIM type')
@click.option('--description', help='human readable description')
@click.option('--sdn_controller', default=None, help='Name or id of the SDN controller to be associated with this VIM'
                                                     'account. Use empty string to disassociate')
@click.option('--sdn_port_mapping', default=None, help="File describing the port mapping between compute nodes' ports and switch ports")
@click.option('--wait',
              required=False,
              default=False,
              is_flag=True,
              help='do not return the control immediately, but keep it '
                   'until the operation is completed, or timeout')
@click.pass_context
def vim_update(ctx,
               name,
               newname,
               user,
               password,
               auth_url,
               tenant,
               config,
               account_type,
               description,
               sdn_controller,
               sdn_port_mapping,
               wait):
    """updates a VIM account

    NAME: name or ID of the VIM account
    """
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    vim = {}
    if newname: vim['name'] = newname
    if user: vim['vim_user'] = user
    if password: vim['vim_password'] = password
    if auth_url: vim['vim_url'] = auth_url
    if tenant: vim['vim-tenant-name'] = tenant
    if account_type: vim['vim_type'] = account_type
    if description: vim['description'] = description
    if config: vim['config'] = config
    ctx.obj.vim.update(name, vim, sdn_controller, sdn_port_mapping, wait=wait)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='vim-delete', short_help='deletes a VIM account')
@click.argument('name')
@click.option('--force', is_flag=True, help='forces the deletion bypassing pre-conditions')
@click.option('--wait',
              required=False,
              default=False,
              is_flag=True,
              help='do not return the control immediately, but keep it '
                   'until the operation is completed, or timeout')
@click.pass_context
def vim_delete(ctx, name, force, wait):
    """deletes a VIM account

    NAME: name or ID of the VIM account to be deleted
    """
    logger.debug("")
    # try:
    if not force:
        ctx.obj.vim.delete(name, wait=wait)
    else:
        check_client_version(ctx.obj, '--force')
        ctx.obj.vim.delete(name, force, wait=wait)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='vim-list', short_help='list all VIM accounts')
#@click.option('--ro_update/--no_ro_update',
#              default=False,
#              help='update list from RO')
@click.option('--filter', default=None,
              help='restricts the list to the VIM accounts matching the filter')
@click.option('--long', is_flag=True,
              help='get more details of the NS (project, vim, deployment status, configuration status.')
@click.pass_context
def vim_list(ctx, filter, long):
    """list all VIM accounts"""
    logger.debug("")
    if filter:
        check_client_version(ctx.obj, '--filter')
#    if ro_update:
#        check_client_version(ctx.obj, '--ro_update', 'v1')
    fullclassname = ctx.obj.__module__ + "." + ctx.obj.__class__.__name__
    if fullclassname == 'osmclient.sol005.client.Client':
        resp = ctx.obj.vim.list(filter)
#    else:
#        resp = ctx.obj.vim.list(ro_update)
    if long:
        table = PrettyTable(['vim name', 'uuid', 'project', 'operational state', 'error details'])
    else:
        table = PrettyTable(['vim name', 'uuid'])
    for vim in resp:
        if long:
            vim_details = ctx.obj.vim.get(vim['uuid'])
            if 'vim_password' in vim_details:
                vim_details['vim_password']='********'
            logger.debug('VIM details: {}'.format(yaml.safe_dump(vim_details)))
            vim_state = vim_details['_admin'].get('operationalState', '-')
            error_details = 'N/A'
            if vim_state == 'ERROR':
                error_details = vim_details['_admin'].get('detailed-status', 'Not found')
            project_list = ctx.obj.project.list()
            vim_project_list = vim_details.get('_admin').get('projects_read')
            project_id = 'None'
            project_name = 'None'
            if vim_project_list:
                project_id = vim_project_list[0]
                for p in project_list:
                    if p['_id'] == project_id:
                        project_name = p['name']
                        break
            table.add_row([vim['name'], vim['uuid'], '{} ({})'.format(project_name, project_id),
                          vim_state, wrap_text(text=error_details, width=80)])
        else:
            table.add_row([vim['name'], vim['uuid']])
    table.align = 'l'
    print(table)


@cli_osm.command(name='vim-show', short_help='shows the details of a VIM account')
@click.argument('name')
@click.pass_context
def vim_show(ctx, name):
    """shows the details of a VIM account

    NAME: name or ID of the VIM account
    """
    logger.debug("")
    # try:
    resp = ctx.obj.vim.get(name)
    if 'vim_password' in resp:
        resp['vim_password']='********'
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)

    table = PrettyTable(['key', 'attribute'])
    for k, v in list(resp.items()):
        table.add_row([k, wrap_text(text=json.dumps(v, indent=2),width=100)])
    table.align = 'l'
    print(table)


####################
# WIM operations
####################

@cli_osm.command(name='wim-create', short_help='creates a new WIM account')
@click.option('--name',
              prompt=True,
              help='Name for the WIM account')
@click.option('--user',
              help='WIM username')
@click.option('--password',
              help='WIM password')
@click.option('--url',
              prompt=True,
              help='WIM url')
# @click.option('--tenant',
#               help='wIM tenant name')
@click.option('--config',
              default=None,
              help='WIM specific config parameters')
@click.option('--wim_type',
              help='WIM type')
@click.option('--description',
              default=None,
              help='human readable description')
@click.option('--wim_port_mapping', default=None,
              help="File describing the port mapping between DC edge (datacenters, switches, ports) and WAN edge "
                   "(WAN service endpoint id and info)")
@click.option('--wait',
              required=False,
              default=False,
              is_flag=True,
              help='do not return the control immediately, but keep it '
                   'until the operation is completed, or timeout')
@click.pass_context
def wim_create(ctx,
               name,
               user,
               password,
               url,
               # tenant,
               config,
               wim_type,
               description,
               wim_port_mapping,
               wait):
    """creates a new WIM account"""
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    # if sdn_controller:
    #     check_client_version(ctx.obj, '--sdn_controller')
    # if sdn_port_mapping:
    #     check_client_version(ctx.obj, '--sdn_port_mapping')
    wim = {}
    if user: wim['user'] = user
    if password: wim['password'] = password
    if url: wim['wim_url'] = url
    # if tenant: wim['tenant'] = tenant
    wim['wim_type'] = wim_type
    if description: wim['description'] = description
    if config: wim['config'] = config
    ctx.obj.wim.create(name, wim, wim_port_mapping, wait=wait)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='wim-update', short_help='updates a WIM account')
@click.argument('name')
@click.option('--newname', help='New name for the WIM account')
@click.option('--user', help='WIM username')
@click.option('--password', help='WIM password')
@click.option('--url', help='WIM url')
@click.option('--config', help='WIM specific config parameters')
@click.option('--wim_type', help='WIM type')
@click.option('--description', help='human readable description')
@click.option('--wim_port_mapping', default=None,
              help="File describing the port mapping between DC edge (datacenters, switches, ports) and WAN edge "
                   "(WAN service endpoint id and info)")
@click.option('--wait',
              required=False,
              default=False,
              is_flag=True,
              help='do not return the control immediately, but keep it until the operation is completed, or timeout')
@click.pass_context
def wim_update(ctx,
               name,
               newname,
               user,
               password,
               url,
               config,
               wim_type,
               description,
               wim_port_mapping,
               wait):
    """updates a WIM account

    NAME: name or ID of the WIM account
    """
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    wim = {}
    if newname: wim['name'] = newname
    if user: wim['user'] = user
    if password: wim['password'] = password
    if url: wim['url'] = url
    # if tenant: wim['tenant'] = tenant
    if wim_type: wim['wim_type'] = wim_type
    if description: wim['description'] = description
    if config: wim['config'] = config
    ctx.obj.wim.update(name, wim, wim_port_mapping, wait=wait)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='wim-delete', short_help='deletes a WIM account')
@click.argument('name')
@click.option('--force', is_flag=True, help='forces the deletion bypassing pre-conditions')
@click.option('--wait',
              required=False,
              default=False,
              is_flag=True,
              help='do not return the control immediately, but keep it until the operation is completed, or timeout')
@click.pass_context
def wim_delete(ctx, name, force, wait):
    """deletes a WIM account

    NAME: name or ID of the WIM account to be deleted
    """
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    ctx.obj.wim.delete(name, force, wait=wait)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='wim-list', short_help='list all WIM accounts')
@click.option('--filter', default=None,
              help='restricts the list to the WIM accounts matching the filter')
@click.pass_context
def wim_list(ctx, filter):
    """list all WIM accounts"""
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    resp = ctx.obj.wim.list(filter)
    table = PrettyTable(['wim name', 'uuid'])
    for wim in resp:
        table.add_row([wim['name'], wim['uuid']])
    table.align = 'l'
    print(table)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='wim-show', short_help='shows the details of a WIM account')
@click.argument('name')
@click.pass_context
def wim_show(ctx, name):
    """shows the details of a WIM account

    NAME: name or ID of the WIM account
    """
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    resp = ctx.obj.wim.get(name)
    if 'password' in resp:
        resp['wim_password']='********'
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)

    table = PrettyTable(['key', 'attribute'])
    for k, v in list(resp.items()):
        table.add_row([k, json.dumps(v, indent=2)])
    table.align = 'l'
    print(table)


####################
# SDN controller operations
####################

@cli_osm.command(name='sdnc-create', short_help='creates a new SDN controller')
@click.option('--name',
              prompt=True,
              help='Name to create sdn controller')
@click.option('--type',
              prompt=True,
              help='SDN controller type')
@click.option('--sdn_controller_version',  # hidden=True,
              help='Deprecated. Use --config {version: sdn_controller_version}')
@click.option('--url',
              help='URL in format http[s]://HOST:IP/')
@click.option('--ip_address',  # hidden=True,
              help='Deprecated. Use --url')
@click.option('--port',  # hidden=True,
              help='Deprecated. Use --url')
@click.option('--switch_dpid',  # hidden=True,
              help='Deprecated. Use --config {switch_id: DPID}')
@click.option('--config',
              help='Extra information for SDN in yaml format, as {switch_id: identity used for the plugin (e.g. DPID: '
             'Openflow Datapath ID), version: version}')
@click.option('--user',
              help='SDN controller username')
@click.option('--password',
              hide_input=True,
              confirmation_prompt=True,
              help='SDN controller password')
@click.option('--description', default=None, help='human readable description')
@click.option('--wait',
              required=False,
              default=False,
              is_flag=True,
              help="do not return the control immediately, but keep it until the operation is completed, or timeout")
@click.pass_context
def sdnc_create(ctx, **kwargs):
    """creates a new SDN controller"""
    logger.debug("")
    sdncontroller = {x: kwargs[x] for x in kwargs if kwargs[x] and
                     x not in ("wait", "ip_address", "port", "switch_dpid")}
    if kwargs.get("port"):
        print("option '--port' is deprecated, use '--url' instead")
        sdncontroller["port"] = int(kwargs["port"])
    if kwargs.get("ip_address"):
        print("option '--ip_address' is deprecated, use '--url' instead")
        sdncontroller["ip"] = kwargs["ip_address"]
    if kwargs.get("switch_dpid"):
        print("option '--switch_dpid' is deprecated, use '--config={switch_id: id|DPID}' instead")
        sdncontroller["dpid"] = kwargs["switch_dpid"]
    if kwargs.get("sdn_controller_version"):
        print("option '--sdn_controller_version' is deprecated, use '--config={version: SDN_CONTROLLER_VERSION}'"
              " instead")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    ctx.obj.sdnc.create(kwargs["name"], sdncontroller, wait=kwargs["wait"])
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)

@cli_osm.command(name='sdnc-update', short_help='updates an SDN controller')
@click.argument('name')
@click.option('--newname', help='New name for the SDN controller')
@click.option('--description',  default=None, help='human readable description')
@click.option('--type', help='SDN controller type')
@click.option('--url', help='URL in format http[s]://HOST:IP/')
@click.option('--config', help='Extra information for SDN in yaml format, as '
                               '{switch_id: identity used for the plugin (e.g. DPID: '
                               'Openflow Datapath ID), version: version}')
@click.option('--user', help='SDN controller username')
@click.option('--password', help='SDN controller password')
@click.option('--ip_address', help='Deprecated. Use --url')  # hidden=True
@click.option('--port', help='Deprecated. Use --url')  # hidden=True
@click.option('--switch_dpid', help='Deprecated. Use --config {switch_dpid: DPID}')  # hidden=True
@click.option('--sdn_controller_version', help='Deprecated. Use --config {version: VERSION}')  # hidden=True
@click.option('--wait', required=False, default=False, is_flag=True,
              help='do not return the control immediately, but keep it until the operation is completed, or timeout')
@click.pass_context
def sdnc_update(ctx, **kwargs):
    """updates an SDN controller

    NAME: name or ID of the SDN controller
    """
    logger.debug("")
    sdncontroller = {x: kwargs[x] for x in kwargs if kwargs[x] and
                     x not in ("wait", "ip_address", "port", "switch_dpid", "new_name")}
    if kwargs.get("newname"):
        sdncontroller["name"] = kwargs["newname"]
    if kwargs.get("port"):
        print("option '--port' is deprecated, use '--url' instead")
        sdncontroller["port"] = int(kwargs["port"])
    if kwargs.get("ip_address"):
        print("option '--ip_address' is deprecated, use '--url' instead")
        sdncontroller["ip"] = kwargs["ip_address"]
    if kwargs.get("switch_dpid"):
        print("option '--switch_dpid' is deprecated, use '--config={switch_id: id|DPID}' instead")
        sdncontroller["dpid"] = kwargs["switch_dpid"]
    if kwargs.get("sdn_controller_version"):
        print("option '--sdn_controller_version' is deprecated, use '---config={version: SDN_CONTROLLER_VERSION}'"
              " instead")

    # try:
    check_client_version(ctx.obj, ctx.command.name)
    ctx.obj.sdnc.update(kwargs["name"], sdncontroller, wait=kwargs["wait"])
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='sdnc-delete', short_help='deletes an SDN controller')
@click.argument('name')
@click.option('--force', is_flag=True, help='forces the deletion bypassing pre-conditions')
@click.option('--wait', required=False, default=False, is_flag=True,
              help='do not return the control immediately, but keep it until the operation is completed, or timeout')
@click.pass_context
def sdnc_delete(ctx, name, force, wait):
    """deletes an SDN controller

    NAME: name or ID of the SDN controller to be deleted
    """
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    ctx.obj.sdnc.delete(name, force, wait=wait)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='sdnc-list', short_help='list all SDN controllers')
@click.option('--filter', default=None,
              help="restricts the list to the SDN controllers matching the filter with format: 'k[.k..]=v[&k[.k]=v2]'")
@click.pass_context
def sdnc_list(ctx, filter):
    """list all SDN controllers"""
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    resp = ctx.obj.sdnc.list(filter)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)
    table = PrettyTable(['sdnc name', 'id'])
    for sdnc in resp:
        table.add_row([sdnc['name'], sdnc['_id']])
    table.align = 'l'
    print(table)


@cli_osm.command(name='sdnc-show', short_help='shows the details of an SDN controller')
@click.argument('name')
@click.pass_context
def sdnc_show(ctx, name):
    """shows the details of an SDN controller

    NAME: name or ID of the SDN controller
    """
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    resp = ctx.obj.sdnc.get(name)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)

    table = PrettyTable(['key', 'attribute'])
    for k, v in list(resp.items()):
        table.add_row([k, json.dumps(v, indent=2)])
    table.align = 'l'
    print(table)


###########################
# K8s cluster operations
###########################

@cli_osm.command(name='k8scluster-add', short_help='adds a K8s cluster to OSM')
@click.argument('name')
@click.option('--creds',
              prompt=True,
              help='credentials file, i.e. a valid `.kube/config` file')
@click.option('--version',
              prompt=True,
              help='Kubernetes version')
@click.option('--vim',
              prompt=True,
              help='VIM target, the VIM where the cluster resides')
@click.option('--k8s-nets',
              prompt=True,
              help='list of VIM networks, in JSON inline format, where the cluster is accessible via L3 routing, e.g. "{(k8s_net1:vim_network1) [,(k8s_net2:vim_network2) ...]}"')
@click.option('--description',
              default=None,
              help='human readable description')
@click.option('--namespace',
              default='kube-system',
              help='namespace to be used for its operation, defaults to `kube-system`')
@click.option('--cni',
              default=None,
              help='list of CNI plugins, in JSON inline format, used in the cluster')
#@click.option('--skip-init',
#              is_flag=True,
#              help='If set, K8s cluster is assumed to be ready for its use with OSM')
#@click.option('--wait',
#              is_flag=True,
#              help='do not return the control immediately, but keep it until the operation is completed, or timeout')
@click.pass_context
def k8scluster_add(ctx,
               name,
               creds,
               version,
               vim,
               k8s_nets,
               description,
               namespace,
               cni):
    """adds a K8s cluster to OSM

    NAME: name of the K8s cluster
    """
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    cluster = {}
    cluster['name'] = name
    with open(creds, 'r') as cf:
        cluster['credentials'] = yaml.safe_load(cf.read())
    cluster['k8s_version'] = version
    cluster['vim_account'] = vim
    cluster['nets'] = yaml.safe_load(k8s_nets)
    if description:
        cluster['description'] = description
    if namespace: cluster['namespace'] = namespace
    if cni: cluster['cni'] = yaml.safe_load(cni)
    ctx.obj.k8scluster.create(name, cluster)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='k8scluster-update', short_help='updates a K8s cluster')
@click.argument('name')
@click.option('--newname', help='New name for the K8s cluster')
@click.option('--creds', help='credentials file, i.e. a valid `.kube/config` file')
@click.option('--version', help='Kubernetes version')
@click.option('--vim', help='VIM target, the VIM where the cluster resides')
@click.option('--k8s-nets', help='list of VIM networks, in JSON inline format, where the cluster is accessible via L3 routing, e.g. "{(k8s_net1:vim_network1) [,(k8s_net2:vim_network2) ...]}"')
@click.option('--description', help='human readable description')
@click.option('--namespace', help='namespace to be used for its operation, defaults to `kube-system`')
@click.option('--cni', help='list of CNI plugins, in JSON inline format, used in the cluster')
@click.pass_context
def k8scluster_update(ctx,
               name,
               newname,
               creds,
               version,
               vim,
               k8s_nets,
               description,
               namespace,
               cni):
    """updates a K8s cluster

    NAME: name or ID of the K8s cluster
    """
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    cluster = {}
    if newname: cluster['name'] = newname
    if creds:
        with open(creds, 'r') as cf:
            cluster['credentials'] = yaml.safe_load(cf.read())
    if version: cluster['k8s_version'] = version
    if vim: cluster['vim_account'] = vim
    if k8s_nets: cluster['nets'] = yaml.safe_load(k8s_nets)
    if description: cluster['description'] = description
    if namespace: cluster['namespace'] = namespace
    if cni: cluster['cni'] = yaml.safe_load(cni)
    ctx.obj.k8scluster.update(name, cluster)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='k8scluster-delete', short_help='deletes a K8s cluster')
@click.argument('name')
@click.option('--force', is_flag=True, help='forces the deletion from the DB (not recommended)')
#@click.option('--wait',
#              is_flag=True,
#              help='do not return the control immediately, but keep it until the operation is completed, or timeout')
@click.pass_context
def k8scluster_delete(ctx, name, force):
    """deletes a K8s cluster

    NAME: name or ID of the K8s cluster to be deleted
    """
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    ctx.obj.k8scluster.delete(name, force=force)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='k8scluster-list')
@click.option('--filter', default=None,
              help='restricts the list to the K8s clusters matching the filter')
@click.option('--literal', is_flag=True,
              help='print literally, no pretty table')
@click.pass_context
def k8scluster_list(ctx, filter, literal):
    """list all K8s clusters"""
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    resp = ctx.obj.k8scluster.list(filter)
    if literal:
        print(yaml.safe_dump(resp, indent=4, default_flow_style=False))
        return
    table = PrettyTable(['Name', 'Id', 'Version', 'VIM', 'K8s-nets', 'Operational State', 'Description'])
    for cluster in resp:
        table.add_row([cluster['name'], cluster['_id'], cluster['k8s_version'], cluster['vim_account'],
                       json.dumps(cluster['nets']), cluster["_admin"]["operationalState"],
                       trunc_text(cluster.get('description') or '', 40)])
    table.align = 'l'
    print(table)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='k8scluster-show', short_help='shows the details of a K8s cluster')
@click.argument('name')
@click.option('--literal', is_flag=True,
              help='print literally, no pretty table')
@click.pass_context
def k8scluster_show(ctx, name, literal):
    """shows the details of a K8s cluster

    NAME: name or ID of the K8s cluster
    """
    # try:
    resp = ctx.obj.k8scluster.get(name)
    if literal:
        print(yaml.safe_dump(resp, indent=4, default_flow_style=False))
        return
    table = PrettyTable(['key', 'attribute'])
    for k, v in list(resp.items()):
        table.add_row([k, wrap_text(text=json.dumps(v, indent=2),width=100)])
    table.align = 'l'
    print(table)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)



###########################
# Repo operations
###########################

@cli_osm.command(name='repo-add', short_help='adds a repo to OSM')
@click.argument('name')
@click.argument('uri')
@click.option('--type',
              type=click.Choice(['helm-chart', 'juju-bundle', 'osm']),
              default='osm',
              help='type of repo (helm-chart for Helm Charts, juju-bundle for Juju Bundles, osm for OSM Repositories)')
@click.option('--description',
              default=None,
              help='human readable description')
@click.option('--user',
              default=None,
              help='OSM repository: The username of the OSM repository')
@click.option('--password',
              default=None,
              help='OSM repository: The password of the OSM repository')
#@click.option('--wait',
#              is_flag=True,
#              help='do not return the control immediately, but keep it until the operation is completed, or timeout')
@click.pass_context
def repo_add(ctx, **kwargs):
    """adds a repo to OSM

    NAME: name of the repo
    URI: URI of the repo
    """
    # try:
    kwargs = {k: v for k, v in kwargs.items() if v is not None}
    repo = kwargs
    repo["url"] = repo.pop("uri")
    if repo["type"] in ['helm-chart', 'juju-bundle']:
        ctx.obj.repo.create(repo['name'], repo)
    else:
        ctx.obj.osmrepo.create(repo['name'], repo)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='repo-update', short_help='updates a repo in OSM')
@click.argument('name')
@click.option('--newname', help='New name for the repo')
@click.option('--uri', help='URI of the repo')
@click.option('--description', help='human readable description')
#@click.option('--wait',
#              is_flag=True,
#              help='do not return the control immediately, but keep it until the operation is completed, or timeout')
@click.pass_context
def repo_update(ctx,
             name,
             newname,
             uri,
             description):
    """updates a repo in OSM

    NAME: name of the repo
    """
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    repo = {}
    if newname:
        repo['name'] = newname
    if uri:
        repo['uri'] = uri
    if description: repo['description'] = description
    try:
        ctx.obj.repo.update(name, repo)
    except NotFound:
        ctx.obj.osmrepo.update(name, repo)

    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='repo-index', short_help='Index a repository from a folder with artifacts')
@click.option('--origin', default='.', help='origin path where the artifacts are located')
@click.option('--destination', default='.', help='destination path where the index is deployed')
@click.pass_context
def repo_index(ctx, origin, destination):
    """Index a repository

    NAME: name or ID of the repo to be deleted
    """
    check_client_version(ctx.obj, ctx.command.name)
    ctx.obj.osmrepo.repo_index(origin, destination)


@cli_osm.command(name='repo-delete', short_help='deletes a repo')
@click.argument('name')
@click.option('--force', is_flag=True, help='forces the deletion from the DB (not recommended)')
#@click.option('--wait',
#              is_flag=True,
#              help='do not return the control immediately, but keep it until the operation is completed, or timeout')
@click.pass_context
def repo_delete(ctx, name, force):
    """deletes a repo

    NAME: name or ID of the repo to be deleted
    """
    logger.debug("")
    try:
        ctx.obj.repo.delete(name, force=force)
    except NotFound:
        ctx.obj.osmrepo.delete(name, force=force)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='repo-list')
@click.option('--filter', default=None,
              help='restricts the list to the repos matching the filter')
@click.option('--literal', is_flag=True,
              help='print literally, no pretty table')
@click.pass_context
def repo_list(ctx, filter, literal):
    """list all repos"""
    # try:
    # K8s Repositories
    check_client_version(ctx.obj, ctx.command.name)
    resp = ctx.obj.repo.list(filter)
    resp += ctx.obj.osmrepo.list(filter)
    if literal:
        print(yaml.safe_dump(resp, indent=4, default_flow_style=False))
        return
    table = PrettyTable(['Name', 'Id', 'Type', 'URI', 'Description'])
    for repo in resp:
        #cluster['k8s-nets'] = json.dumps(yaml.safe_load(cluster['k8s-nets']))
        table.add_row([repo['name'], repo['_id'], repo['type'], repo['url'], trunc_text(repo.get('description') or '',40)])
    table.align = 'l'
    print(table)

    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='repo-show', short_help='shows the details of a repo')
@click.argument('name')
@click.option('--literal', is_flag=True,
              help='print literally, no pretty table')
@click.pass_context
def repo_show(ctx, name, literal):
    """shows the details of a repo

    NAME: name or ID of the repo
    """
    try:
        resp = ctx.obj.repo.get(name)
    except NotFound:
        resp = ctx.obj.osmrepo.get(name)

    if literal:
        if resp:
            print(yaml.safe_dump(resp, indent=4, default_flow_style=False))
        return
    table = PrettyTable(['key', 'attribute'])
    if resp:
        for k, v in list(resp.items()):
            table.add_row([k, json.dumps(v, indent=2)])

    table.align = 'l'
    print(table)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)



####################
# Project mgmt operations
####################

@cli_osm.command(name='project-create', short_help='creates a new project')
@click.argument('name')
#@click.option('--description',
#              default='no description',
#              help='human readable description')
@click.option('--domain-name', 'domain_name',
              default=None,
              help='assign to a domain')
@click.option('--quotas', 'quotas', multiple=True, default=None,
              help="provide quotas. Can be used several times: 'quota1=number[,quota2=number,...]'. Quotas can be one "
                   "of vnfds, nsds, nsts, pdus, nsrs, nsis, vim_accounts, wim_accounts, sdns, k8sclusters, k8srepos")
@click.pass_context
def project_create(ctx, name, domain_name, quotas):
    """Creates a new project

    NAME: name of the project
    DOMAIN_NAME: optional domain name for the project when keystone authentication is used
    QUOTAS: set quotas for the project
    """
    logger.debug("")
    project = {'name': name}
    if domain_name:
        project['domain_name'] = domain_name
    quotas_dict = _process_project_quotas(quotas)
    if quotas_dict:
        project['quotas'] = quotas_dict

    # try:
    check_client_version(ctx.obj, ctx.command.name)
    ctx.obj.project.create(name, project)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


def _process_project_quotas(quota_list):
    quotas_dict = {}
    if not quota_list:
        return quotas_dict
    try:
        for quota in quota_list:
            for single_quota in quota.split(","):
                k, v = single_quota.split("=")
                quotas_dict[k] = None if v in ('None', 'null', '') else int(v)
    except (ValueError, TypeError):
        raise ClientException("invalid format for 'quotas'. Use 'k1=v1,v1=v2'. v must be a integer or null")
    return quotas_dict


@cli_osm.command(name='project-delete', short_help='deletes a project')
@click.argument('name')
#@click.option('--force', is_flag=True, help='forces the deletion bypassing pre-conditions')
@click.pass_context
def project_delete(ctx, name):
    """deletes a project

    NAME: name or ID of the project to be deleted
    """
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    ctx.obj.project.delete(name)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='project-list', short_help='list all projects')
@click.option('--filter', default=None,
              help='restricts the list to the projects matching the filter')
@click.pass_context
def project_list(ctx, filter):
    """list all projects"""
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    resp = ctx.obj.project.list(filter)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)
    table = PrettyTable(['name', 'id'])
    for proj in resp:
        table.add_row([proj['name'], proj['_id']])
    table.align = 'l'
    print(table)


@cli_osm.command(name='project-show', short_help='shows the details of a project')
@click.argument('name')
@click.pass_context
def project_show(ctx, name):
    """shows the details of a project

    NAME: name or ID of the project
    """
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    resp = ctx.obj.project.get(name)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)

    table = PrettyTable(['key', 'attribute'])
    for k, v in resp.items():
        table.add_row([k, json.dumps(v, indent=2)])
    table.align = 'l'
    print(table)


@cli_osm.command(name='project-update', short_help='updates a project (only the name can be updated)')
@click.argument('project')
@click.option('--name', default=None,
              help='new name for the project')
@click.option('--quotas', 'quotas', multiple=True, default=None,
              help="change quotas. Can be used several times: 'quota1=number|empty[,quota2=...]' "
                   "(use empty to reset quota to default")
@click.pass_context
def project_update(ctx, project, name, quotas):
    """
    Update a project name

    :param ctx:
    :param project: id or name of the project to modify
    :param name:  new name for the project
    :param quotas:  change quotas of the project
    :return:
    """
    logger.debug("")
    project_changes = {}
    if name:
        project_changes['name'] = name
    quotas_dict = _process_project_quotas(quotas)
    if quotas_dict:
        project_changes['quotas'] = quotas_dict

    # try:
    check_client_version(ctx.obj, ctx.command.name)
    ctx.obj.project.update(project, project_changes)
    # except ClientException as e:
    #     print(str(e))


####################
# User mgmt operations
####################

@cli_osm.command(name='user-create', short_help='creates a new user')
@click.argument('username')
@click.option('--password',
              prompt=True,
              hide_input=True,
              confirmation_prompt=True,
              help='user password')
@click.option('--projects',
              # prompt="Comma separate list of projects",
              multiple=True,
              callback=lambda ctx, param, value: ''.join(value).split(',') if all(len(x)==1 for x in value) else value,
              help='list of project ids that the user belongs to')
@click.option('--project-role-mappings', 'project_role_mappings',
              default=None, multiple=True,
              help="assign role(s) in a project. Can be used several times: 'project,role1[,role2,...]'")
@click.option('--domain-name', 'domain_name',
              default=None,
              help='assign to a domain')
@click.pass_context
def user_create(ctx, username, password, projects, project_role_mappings, domain_name):
    """Creates a new user

    \b
    USERNAME: name of the user
    PASSWORD: password of the user
    PROJECTS: projects assigned to user (internal only)
    PROJECT_ROLE_MAPPING: roles in projects assigned to user (keystone)
    DOMAIN_NAME: optional domain name for the user when keystone authentication is used
    """
    logger.debug("")
    user = {}
    user['username'] = username
    user['password'] = password
    user['projects'] = projects
    user['project_role_mappings'] = project_role_mappings
    if domain_name:
        user['domain_name'] = domain_name

    # try:
    check_client_version(ctx.obj, ctx.command.name)
    ctx.obj.user.create(username, user)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='user-update', short_help='updates user information')
@click.argument('username')
@click.option('--password',
              # prompt=True,
              # hide_input=True,
              # confirmation_prompt=True,
              help='user password')
@click.option('--set-username', 'set_username',
              default=None,
              help='change username')
@click.option('--set-project', 'set_project',
              default=None, multiple=True,
              help="create/replace the roles for this project: 'project,role1[,role2,...]'")
@click.option('--remove-project', 'remove_project',
              default=None, multiple=True,
              help="removes project from user: 'project'")
@click.option('--add-project-role', 'add_project_role',
              default=None, multiple=True,
              help="assign role(s) in a project. Can be used several times: 'project,role1[,role2,...]'")
@click.option('--remove-project-role', 'remove_project_role',
              default=None, multiple=True,
              help="remove role(s) in a project. Can be used several times: 'project,role1[,role2,...]'")
@click.pass_context
def user_update(ctx, username, password, set_username, set_project, remove_project,
                add_project_role, remove_project_role):
    """Update a user information

    \b
    USERNAME: name of the user
    PASSWORD: new password
    SET_USERNAME: new username
    SET_PROJECT: creating mappings for project/role(s)
    REMOVE_PROJECT: deleting mappings for project/role(s)
    ADD_PROJECT_ROLE: adding mappings for project/role(s)
    REMOVE_PROJECT_ROLE: removing mappings for project/role(s)
    """
    logger.debug("")
    user = {}
    user['password'] = password
    user['username'] = set_username
    user['set-project'] = set_project
    user['remove-project'] = remove_project
    user['add-project-role'] = add_project_role
    user['remove-project-role'] = remove_project_role
    
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    ctx.obj.user.update(username, user)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='user-delete', short_help='deletes a user')
@click.argument('name')
#@click.option('--force', is_flag=True, help='forces the deletion bypassing pre-conditions')
@click.pass_context
def user_delete(ctx, name):
    """deletes a user

    \b
    NAME: name or ID of the user to be deleted
    """
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    ctx.obj.user.delete(name)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='user-list', short_help='list all users')
@click.option('--filter', default=None,
              help='restricts the list to the users matching the filter')
@click.pass_context
def user_list(ctx, filter):
    """list all users"""
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    resp = ctx.obj.user.list(filter)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)
    table = PrettyTable(['name', 'id'])
    for user in resp:
        table.add_row([user['username'], user['_id']])
    table.align = 'l'
    print(table)


@cli_osm.command(name='user-show', short_help='shows the details of a user')
@click.argument('name')
@click.pass_context
def user_show(ctx, name):
    """shows the details of a user

    NAME: name or ID of the user
    """
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    resp = ctx.obj.user.get(name)
    if 'password' in resp:
        resp['password']='********'
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)

    table = PrettyTable(['key', 'attribute'])
    for k, v in resp.items():
        table.add_row([k, json.dumps(v, indent=2)])
    table.align = 'l'
    print(table)


####################
# Fault Management operations
####################

@cli_osm.command(name='ns-alarm-create')
@click.argument('name')
@click.option('--ns', prompt=True, help='NS instance id or name')
@click.option('--vnf', prompt=True,
              help='VNF name (VNF member index as declared in the NSD)')
@click.option('--vdu', prompt=True,
              help='VDU name (VDU name as declared in the VNFD)')
@click.option('--metric', prompt=True,
              help='Name of the metric (e.g. cpu_utilization)')
@click.option('--severity', default='WARNING',
              help='severity of the alarm (WARNING, MINOR, MAJOR, CRITICAL, INDETERMINATE)')
@click.option('--threshold_value', prompt=True,
              help='threshold value that, when crossed, an alarm is triggered')
@click.option('--threshold_operator', prompt=True,
              help='threshold operator describing the comparison (GE, LE, GT, LT, EQ)')
@click.option('--statistic', default='AVERAGE',
              help='statistic (AVERAGE, MINIMUM, MAXIMUM, COUNT, SUM)')
@click.pass_context
def ns_alarm_create(ctx, name, ns, vnf, vdu, metric, severity,
                    threshold_value, threshold_operator, statistic):
    """creates a new alarm for a NS instance"""
    # TODO: Check how to validate threshold_value.
    # Should it be an integer (1-100), percentage, or decimal (0.01-1.00)?
    logger.debug("")
    # try:
    ns_instance = ctx.obj.ns.get(ns)
    alarm = {}
    alarm['alarm_name'] = name
    alarm['ns_id'] = ns_instance['_id']
    alarm['correlation_id'] = ns_instance['_id']
    alarm['vnf_member_index'] = vnf
    alarm['vdu_name'] = vdu
    alarm['metric_name'] = metric
    alarm['severity'] = severity
    alarm['threshold_value'] = int(threshold_value)
    alarm['operation'] = threshold_operator
    alarm['statistic'] = statistic
    check_client_version(ctx.obj, ctx.command.name)
    ctx.obj.ns.create_alarm(alarm)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


#@cli_osm.command(name='ns-alarm-delete')
#@click.argument('name')
#@click.pass_context
#def ns_alarm_delete(ctx, name):
#    """deletes an alarm
#
#    NAME: name of the alarm to be deleted
#    """
#    try:
#        check_client_version(ctx.obj, ctx.command.name)
#        ctx.obj.ns.delete_alarm(name)
#    except ClientException as e:
#        print(str(e))
#        exit(1)


####################
# Performance Management operations
####################

@cli_osm.command(name='ns-metric-export', short_help='exports a metric to the internal OSM bus, which can be read by other apps')
@click.option('--ns', prompt=True, help='NS instance id or name')
@click.option('--vnf', prompt=True,
              help='VNF name (VNF member index as declared in the NSD)')
@click.option('--vdu', prompt=True,
              help='VDU name (VDU name as declared in the VNFD)')
@click.option('--metric', prompt=True,
              help='name of the metric (e.g. cpu_utilization)')
#@click.option('--period', default='1w',
#              help='metric collection period (e.g. 20s, 30m, 2h, 3d, 1w)')
@click.option('--interval', help='periodic interval (seconds) to export metrics continuously')
@click.pass_context
def ns_metric_export(ctx, ns, vnf, vdu, metric, interval):
    """exports a metric to the internal OSM bus, which can be read by other apps"""
    # TODO: Check how to validate interval.
    # Should it be an integer (seconds), or should a suffix (s,m,h,d,w) also be permitted?
    logger.debug("")
    # try:
    ns_instance = ctx.obj.ns.get(ns)
    metric_data = {}
    metric_data['ns_id'] = ns_instance['_id']
    metric_data['correlation_id'] = ns_instance['_id']
    metric_data['vnf_member_index'] = vnf
    metric_data['vdu_name'] = vdu
    metric_data['metric_name'] = metric
    metric_data['collection_unit'] = 'WEEK'
    metric_data['collection_period'] = 1
    check_client_version(ctx.obj, ctx.command.name)
    if not interval:
        print('{}'.format(ctx.obj.ns.export_metric(metric_data)))
    else:
        i = 1
        while True:
            print('{} {}'.format(ctx.obj.ns.export_metric(metric_data),i))
            time.sleep(int(interval))
            i+=1
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


####################
# Other operations
####################

@cli_osm.command(name='version', short_help='shows client and server versions')
@click.pass_context
def get_version(ctx):
    """shows client and server versions"""
    # try:
    check_client_version(ctx.obj, "version")
    print ("Server version: {}".format(ctx.obj.get_version()))
    print ("Client version: {}".format(pkg_resources.get_distribution("osmclient").version))
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)

@cli_osm.command(name='upload-package', short_help='uploads a VNF package or NS package')
@click.argument('filename')
@click.option('--skip-charm-build', default=False, is_flag=True,
              help='the charm will not be compiled, it is assumed to already exist')
@click.pass_context
def upload_package(ctx, filename, skip_charm_build):
    """uploads a vnf package or ns package

    filename: vnf or ns package folder, or vnf or ns package file (tar.gz)
    """
    logger.debug("")
    # try:
    ctx.obj.package.upload(filename, skip_charm_build=skip_charm_build)
    fullclassname = ctx.obj.__module__ + "." + ctx.obj.__class__.__name__
    if fullclassname != 'osmclient.sol005.client.Client':
        ctx.obj.package.wait_for_upload(filename)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


#@cli_osm.command(name='ns-scaling-show')
#@click.argument('ns_name')
#@click.pass_context
#def show_ns_scaling(ctx, ns_name):
#    """shows the status of a NS scaling operation
#
#    NS_NAME: name of the NS instance being scaled
#    """
#    try:
#        check_client_version(ctx.obj, ctx.command.name, 'v1')
#        resp = ctx.obj.ns.list()
#    except ClientException as e:
#        print(str(e))
#        exit(1)
#
#    table = PrettyTable(
#        ['group-name',
#         'instance-id',
#         'operational status',
#         'create-time',
#         'vnfr ids'])
#
#    for ns in resp:
#        if ns_name == ns['name']:
#            nsopdata = ctx.obj.ns.get_opdata(ns['id'])
#            scaling_records = nsopdata['nsr:nsr']['scaling-group-record']
#            for record in scaling_records:
#                if 'instance' in record:
#                    instances = record['instance']
#                    for inst in instances:
#                        table.add_row(
#                            [record['scaling-group-name-ref'],
#                             inst['instance-id'],
#                                inst['op-status'],
#                                time.strftime('%Y-%m-%d %H:%M:%S',
#                                              time.localtime(
#                                                  inst['create-time'])),
#                                inst['vnfrs']])
#    table.align = 'l'
#    print(table)


#@cli_osm.command(name='ns-scale')
#@click.argument('ns_name')
#@click.option('--ns_scale_group', prompt=True)
#@click.option('--index', prompt=True)
#@click.option('--wait',
#              required=False,
#              default=False,
#              is_flag=True,
#              help='do not return the control immediately, but keep it \
#              until the operation is completed, or timeout')
#@click.pass_context
#def ns_scale(ctx, ns_name, ns_scale_group, index, wait):
#    """scales NS
#
#    NS_NAME: name of the NS instance to be scaled
#    """
#    try:
#        check_client_version(ctx.obj, ctx.command.name, 'v1')
#        ctx.obj.ns.scale(ns_name, ns_scale_group, index, wait=wait)
#    except ClientException as e:
#        print(str(e))
#        exit(1)


#@cli_osm.command(name='config-agent-list')
#@click.pass_context
#def config_agent_list(ctx):
#    """list config agents"""
#    try:
#        check_client_version(ctx.obj, ctx.command.name, 'v1')
#    except ClientException as e:
#        print(str(e))
#        exit(1)
#    table = PrettyTable(['name', 'account-type', 'details'])
#    for account in ctx.obj.vca.list():
#        table.add_row(
#            [account['name'],
#             account['account-type'],
#             account['juju']])
#    table.align = 'l'
#    print(table)


#@cli_osm.command(name='config-agent-delete')
#@click.argument('name')
#@click.pass_context
#def config_agent_delete(ctx, name):
#    """deletes a config agent
#
#    NAME: name of the config agent to be deleted
#    """
#    try:
#        check_client_version(ctx.obj, ctx.command.name, 'v1')
#        ctx.obj.vca.delete(name)
#    except ClientException as e:
#        print(str(e))
#        exit(1)


#@cli_osm.command(name='config-agent-add')
#@click.option('--name',
#              prompt=True)
#@click.option('--account_type',
#              prompt=True)
#@click.option('--server',
#              prompt=True)
#@click.option('--user',
#              prompt=True)
#@click.option('--secret',
#              prompt=True,
#              hide_input=True,
#              confirmation_prompt=True)
#@click.pass_context
#def config_agent_add(ctx, name, account_type, server, user, secret):
#    """adds a config agent"""
#    try:
#        check_client_version(ctx.obj, ctx.command.name, 'v1')
#        ctx.obj.vca.create(name, account_type, server, user, secret)
#    except ClientException as e:
#        print(str(e))
#        exit(1)


#@cli_osm.command(name='ro-dump')
#@click.pass_context
#def ro_dump(ctx):
#    """shows RO agent information"""
#    check_client_version(ctx.obj, ctx.command.name, 'v1')
#    resp = ctx.obj.vim.get_resource_orchestrator()
#    table = PrettyTable(['key', 'attribute'])
#    for k, v in list(resp.items()):
#        table.add_row([k, json.dumps(v, indent=2)])
#    table.align = 'l'
#    print(table)


#@cli_osm.command(name='vcs-list')
#@click.pass_context
#def vcs_list(ctx):
#    check_client_version(ctx.obj, ctx.command.name, 'v1')
#    resp = ctx.obj.utils.get_vcs_info()
#    table = PrettyTable(['component name', 'state'])
#    for component in resp:
#        table.add_row([component['component_name'], component['state']])
#    table.align = 'l'
#    print(table)


@cli_osm.command(name='ns-action', short_help='executes an action/primitive over a NS instance')
@click.argument('ns_name')
@click.option('--vnf_name', default=None, help='member-vnf-index if the target is a vnf instead of a ns)')
@click.option('--kdu_name', default=None, help='kdu-name if the target is a kdu)')
@click.option('--vdu_id', default=None, help='vdu-id if the target is a vdu')
@click.option('--vdu_count', default=None, type=int, help='number of vdu instance of this vdu_id')
@click.option('--action_name', prompt=True, help='action name')
@click.option('--params', default=None, help='action params in YAML/JSON inline string')
@click.option('--params_file', default=None, help='YAML/JSON file with action params')
@click.option('--timeout', required=False, default=None, type=int, help='timeout in seconds')
@click.option('--wait',
              required=False,
              default=False,
              is_flag=True,
              help='do not return the control immediately, but keep it until the operation is completed, or timeout')
@click.pass_context
def ns_action(ctx,
              ns_name,
              vnf_name,
              kdu_name,
              vdu_id,
              vdu_count,
              action_name,
              params,
              params_file,
              timeout,
              wait):
    """executes an action/primitive over a NS instance

    NS_NAME: name or ID of the NS instance
    """
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    op_data = {}
    if vnf_name:
        op_data['member_vnf_index'] = vnf_name
    if kdu_name:
        op_data['kdu_name'] = kdu_name
    if vdu_id:
        op_data['vdu_id'] = vdu_id
    if vdu_count is not None:
        op_data['vdu_count_index'] = vdu_count
    if timeout:
        op_data['timeout_ns_action'] = timeout
    op_data['primitive'] = action_name
    if params_file:
        with open(params_file, 'r') as pf:
            params = pf.read()
    if params:
        op_data['primitive_params'] = yaml.safe_load(params)
    else:
        op_data['primitive_params'] = {}
    print(ctx.obj.ns.exec_op(ns_name, op_name='action', op_data=op_data, wait=wait))

    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='vnf-scale', short_help='executes a VNF scale (adding/removing VDUs)')
@click.argument('ns_name')
@click.argument('vnf_name')
@click.option('--scaling-group', prompt=True, help="scaling-group-descriptor name to use")
@click.option('--scale-in', default=False, is_flag=True, help="performs a scale in operation")
@click.option('--scale-out', default=False, is_flag=True, help="performs a scale out operation (by default)")
@click.option('--timeout', required=False, default=None, type=int, help='timeout in seconds')
@click.option('--wait', required=False, default=False, is_flag=True,
              help='do not return the control immediately, but keep it until the operation is completed, or timeout')
@click.pass_context
def vnf_scale(ctx,
              ns_name,
              vnf_name,
              scaling_group,
              scale_in,
              scale_out,
              timeout,
              wait):
    """
    Executes a VNF scale (adding/removing VDUs)

    \b
    NS_NAME: name or ID of the NS instance.
    VNF_NAME: member-vnf-index in the NS to be scaled.
    """
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    if not scale_in and not scale_out:
        scale_out = True
    ctx.obj.ns.scale_vnf(ns_name, vnf_name, scaling_group, scale_in, scale_out, wait, timeout)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


##############################
# Role Management Operations #
##############################

@cli_osm.command(name='role-create', short_help='creates a new role')
@click.argument('name')
@click.option('--permissions',
              default=None,
              help='role permissions using a dictionary')
@click.pass_context
def role_create(ctx, name, permissions):
    """
    Creates a new role.

    \b
    NAME: Name or ID of the role.
    DEFINITION: Definition of grant/denial of access to resources.
    """
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    ctx.obj.role.create(name, permissions)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='role-update', short_help='updates a role')
@click.argument('name')
@click.option('--set-name',
              default=None,
              help='change name of rle')
# @click.option('--permissions',
#               default=None,
#               help='provide a yaml format dictionary with incremental changes. Values can be bool or None to delete')
@click.option('--add',
              default=None,
              help='yaml format dictionary with permission: True/False to access grant/denial')
@click.option('--remove',
              default=None,
              help='yaml format list to remove a permission')
@click.pass_context
def role_update(ctx, name, set_name, add, remove):
    """
    Updates a role.

    \b
    NAME: Name or ID of the role.
    DEFINITION: Definition overwrites the old definition.
    ADD: Grant/denial of access to resource to add.
    REMOVE: Grant/denial of access to resource to remove.
    """
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    ctx.obj.role.update(name, set_name, None, add, remove)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='role-delete', short_help='deletes a role')
@click.argument('name')
# @click.option('--force', is_flag=True, help='forces the deletion bypassing pre-conditions')
@click.pass_context
def role_delete(ctx, name):
    """
    Deletes a role.

    \b
    NAME: Name or ID of the role.
    """
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    ctx.obj.role.delete(name)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)


@cli_osm.command(name='role-list', short_help='list all roles')
@click.option('--filter', default=None,
              help='restricts the list to the projects matching the filter')
@click.pass_context
def role_list(ctx, filter):
    """
    List all roles.
    """
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    resp = ctx.obj.role.list(filter)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)
    table = PrettyTable(['name', 'id'])
    for role in resp:
        table.add_row([role['name'], role['_id']])
    table.align = 'l'
    print(table)


@cli_osm.command(name='role-show', short_help='show specific role')
@click.argument('name')
@click.pass_context
def role_show(ctx, name):
    """
    Shows the details of a role.

    \b
    NAME: Name or ID of the role.
    """
    logger.debug("")
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    resp = ctx.obj.role.get(name)
    # except ClientException as e:
    #     print(str(e))
    #     exit(1)

    table = PrettyTable(['key', 'attribute'])
    for k, v in resp.items():
        table.add_row([k, json.dumps(v, indent=2)])
    table.align = 'l'
    print(table)


@cli_osm.command(name='package-create',
             short_help='Create a package descriptor')
@click.argument('package-type')
@click.argument('package-name')
@click.option('--base-directory',
              default='.',
              help=('(NS/VNF/NST) Set the location for package creation. Default: "."'))
@click.option('--image',
              default="image-name",
              help='(VNF) Set the name of the vdu image. Default "image-name"')
@click.option('--vdus',
              default=1,
              help='(VNF) Set the number of vdus in a VNF. Default 1')
@click.option('--vcpu',
              default=1,
              help='(VNF) Set the number of virtual CPUs in a vdu. Default 1')
@click.option('--memory',
              default=1024,
              help='(VNF) Set the memory size (MB) of the vdu. Default 1024')
@click.option('--storage',
              default=10,
              help='(VNF) Set the disk size (GB) of the vdu. Default 10')
@click.option('--interfaces',
              default=0,
              help='(VNF) Set the number of additional interfaces apart from the management interface. Default 0')
@click.option('--vendor',
              default="OSM",
              help='(NS/VNF) Set the descriptor vendor. Default "OSM"')
@click.option('--override',
              default=False,
              is_flag=True,
              help='(NS/VNF/NST) Flag for overriding the package if exists.')
@click.option('--detailed',
              is_flag=True,
              default=False,
              help='(NS/VNF/NST) Flag for generating descriptor .yaml with all possible commented options')
@click.option('--netslice-subnets',
              default=1,
              help='(NST) Number of netslice subnets. Default 1')
@click.option('--netslice-vlds',
              default=1,
              help='(NST) Number of netslice vlds. Default 1')
@click.pass_context
def package_create(ctx,
                   package_type,
                   base_directory,
                   package_name,
                   override,
                   image,
                   vdus,
                   vcpu,
                   memory,
                   storage,
                   interfaces,
                   vendor,
                   detailed,
                   netslice_subnets,
                   netslice_vlds):
    """
    Creates an OSM NS, VNF, NST package

    \b
    PACKAGE_TYPE: Package to be created: NS, VNF or NST.
    PACKAGE_NAME: Name of the package to create the folder with the content.
    """

    # try:
    check_client_version(ctx.obj, ctx.command.name)
    print("Creating the {} structure: {}/{}".format(package_type.upper(), base_directory, package_name))
    resp = ctx.obj.package_tool.create(package_type,
                                       base_directory,
                                       package_name,
                                       override=override,
                                       image=image,
                                       vdus=vdus,
                                       vcpu=vcpu,
                                       memory=memory,
                                       storage=storage,
                                       interfaces=interfaces,
                                       vendor=vendor,
                                       detailed=detailed,
                                       netslice_subnets=netslice_subnets,
                                       netslice_vlds=netslice_vlds)
    print(resp)
    # except ClientException as inst:
    #     print("ERROR: {}".format(inst))
    #     exit(1)

@cli_osm.command(name='package-validate',
             short_help='Validate a package descriptor')
@click.argument('base-directory',
                default=".",
                required=False)
@click.option('--recursive/--no-recursive',
              default=True,
              help='The activated recursive option will validate the yaml files'
                   ' within the indicated directory and in its subdirectories')
@click.pass_context
def package_validate(ctx,
                     base_directory,
                     recursive):
    """
    Validate descriptors given a base directory.

    \b
    BASE_DIRECTORY: Stub folder for NS, VNF or NST package.
    """
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    results = ctx.obj.package_tool.validate(base_directory, recursive)
    table = PrettyTable()
    table.field_names = ["TYPE", "PATH", "VALID", "ERROR"]
    # Print the dictionary generated by the validation function
    for result in results:
        table.add_row([result["type"], result["path"], result["valid"], result["error"]])
    table.sortby = "VALID"
    table.align["PATH"] = "l"
    table.align["TYPE"] = "l"
    table.align["ERROR"] = "l"
    print(table)
    # except ClientException as inst:
    #     print("ERROR: {}".format(inst))
    #     exit(1)

@cli_osm.command(name='package-build',
             short_help='Build the tar.gz of the package')
@click.argument('package-folder')
@click.option('--skip-validation',
              default=False,
              is_flag=True,
              help='skip package validation')
@click.option('--skip-charm-build', default=False, is_flag=True,
              help='the charm will not be compiled, it is assumed to already exist')
@click.pass_context
def package_build(ctx,
                  package_folder,
                  skip_validation,
                  skip_charm_build):
    """
    Build the package NS, VNF given the package_folder.

    \b
    PACKAGE_FOLDER: Folder of the NS, VNF or NST to be packaged
    """
    # try:
    check_client_version(ctx.obj, ctx.command.name)
    results = ctx.obj.package_tool.build(package_folder,
                                         skip_validation=skip_validation,
                                         skip_charm_build=skip_charm_build)
    print(results)
    # except ClientException as inst:
    #     print("ERROR: {}".format(inst))
    #     exit(1)


def cli():
    try:
        cli_osm()
        exit(0)
    except pycurl.error as exc:
        print(exc)
        print('Maybe "--hostname" option or OSM_HOSTNAME environment variable needs to be specified')
    except ClientException as exc:
        print("ERROR: {}".format(exc))
    except (FileNotFoundError, PermissionError) as exc:
        print("Cannot open file: {}".format(exc))
    except yaml.YAMLError as exc:
        print("Invalid YAML format: {}".format(exc))
    exit(1)
    # TODO capture other controlled exceptions here
    # TODO remove the ClientException captures from all places, unless they do something different


if __name__ == '__main__':
    cli()

