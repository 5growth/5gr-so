# Copyright 2020 CTTC www.cttc.es
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
PNF Catalogue.
DB structure:
pnfdId: string
pnfdName: string
pnfdDescrition: string
pnfdJson: IFA014 json descriptor
"""


# mongodb imports
from bson import ObjectId
from pymongo import MongoClient

# project imports
from db import db_ip, db_port
from nbi import log_queue

# create the 5gtso db
pnfd_client = MongoClient(db_ip, db_port)
fgtso_db = pnfd_client.fgtso

# create pnfd catalogue
pnfd_coll = fgtso_db.pnfd


####### SO methods
def exists_pnfd(pnfdId, version=None):
    """
    Function to check if an pnfd with identifier "pnfdId" exists.
    Parameters
    ----------
    pnfdId: string
        Identifier of the Physical Network Function Descriptor
    Returns
    -------
    boolean
        returns True if a pnfd with Id "pnfdId" exists in "pnfd_coll". Returns False otherwise.
    """
    pnfd_json = None
    if version is None:
        pnfd_json = pnfd_coll.find_one({"pnfdId": pnfdId})
    else:
        pnfd_json = pnfd_coll.find_one({"pnfdId": pnfdId, "pnfdVersion": version})
    if pnfd_json is None:
        return False
    return True


def insert_pnfd(pnfd_record):
    """
    Inserts a pnfd record in the DB
    Parameters
    ----------
    pnfd_record: json
        json containing the pnfd information, format:
            pnfdId: string
            pnfdVersion: string
            pnfdName: string
            pnfdJson: dict (IFA014 json descriptor)
    Returns
    -------
    None
    """

    pnfd_coll.insert_one(pnfd_record)


def get_pnfd_json(pnfdId, version=None):
    """
    Returns the json descriptor of the pnfd referenced by pnfdId.
    Parameters
    ----------
    pnfdId: string
        Identifier of the pnfd
    version: string
        Version of the pnfd
    Returns
    -------
    dictionary with the pnfd json saved in the catalogue that correspond to the pnfdId/version
    """
    if (version is not None and version !="NONE"):
        pnfd_json = pnfd_coll.find_one({"pnfdId": pnfdId, "pnfdVersion": version})
        if pnfd_json is None:
            return None
        return pnfd_json["pnfdJson"]
    else:
        pnfd_json = pnfd_coll.find_one({"pnfdId": pnfdId})
        if pnfd_json is None:
            return None
        return pnfd_json["pnfdJson"]

def delete_pnfd_json(pnfdId, version=None):
    """
    Returns True if the referenced descriptor has been deleted from the catalog.
    Parameters
    ----------
    pnfdId: string
        Identifier of the Physical Network Function Descriptor
    version: string
        Version of the PNFD
    Returns
    -------
    boolean
    """
    pnfd_query = None
    if (version is not None and version != "NONE"):
        pnfd_query = {"pnfdId": pnfdId, "pnfdVersion": version}
    else:
        pnfd_query= {"pnfdId": pnfdId}        
    if pnfd_query is None:
        return False
    else:
        pnfd_coll.delete_one(pnfd_query)
        return True


def empty_pnfd_collection():
    """
    deletes all documents in the pnfd_coll
    Parameters
    ----------
    None
    Returns
    -------
    None
    """
    pnfd_coll.delete_many({})


####### GUI methods
def get_all_pnfd():
    """
    Returns all the pnfds in the collection
    Parameters
    ----------
    Returns
    -------
    list of dict
    """
    return list(pnfd_coll.find())


def update_pnfd(id, body):
    """
    Update a pnfd from the collection filtered by the id parameter
    Parameters
    ----------
    id: _id of pnfd
    body: body to update
    Returns
    -------
    ???
    """
    output = pnfd_coll.update({"_id": ObjectId(id)}, {"$set": body})
    # print(output)
    return output


def remove_pnfd_by_id(id):
    """
    Remove a pnfd from the collection filtered by the id parameter
    Parameters
    ----------
    id: _id of pnfd
    Returns
    -------
    dict
    """
    output = pnfd_coll.remove({"_id": ObjectId(id)})
    # print(output)
