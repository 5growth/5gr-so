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
File description
"""

# mongodb imports
from bson import ObjectId
from pymongo import MongoClient

# project imports
from db import db_ip, db_port
from nbi import log_queue

# create the 5gtso db
operation_client = MongoClient(db_ip, db_port)
fgtso_db = operation_client.fgtso

# create operations collection
# operation_coll structure:
#    operationId: string
#    status: string  (one of: PROCESSING, SUCCESFULLY_DONE, FAILED, CANCELLED)
#    nsId: string
#    operation_type: string  (one of: INSTANTIATION, TERMINATION)
operation_coll = fgtso_db.operation


####### SO methods
# operations collection functions
def create_operation_record(operationId, nsId, operation_type):
    """
    Creates a new operation entry in the DB with the input parameters and status "PROCESSING".
    Parameters
    ----------
    operationId: string
    nsId: string
    operation_type: string (one of "INSTANTIATE, TERMINATE"

    Returns
    -------
    None
    """
    operation = {"operationId": operationId, "nsId": nsId, "operation_type": operation_type, "status": "PROCESSING"}
    operation_coll.insert_one(operation)


def exists_operationId(operationId):
    """
    Function to check if an operation with identifier "operationId" exists.
    Parameters
    ----------
    operationId: string
        Identifier of the operation.
    Returns
    -------
    boolean
        returns True if an operation with Id "operationId" exists. Returns False otherwise.
    """
    operation = operation_coll.find_one({"operationId": operationId})
    if operation is None:
        return False
    return True


def get_nsid(operationId):
    """
    Function to get the Network Service Instance identifier of an operation identified by operationId.
    Parameters
    ----------
    operationId: string
        Identifier of the operation.
    Returns
    -------
    string
        Identifier of the Network Service Instance.

    """
    operation = operation_coll.find_one({"operationId": operationId})
    return operation["nsId"]


def get_operationId(nsId, operation_type):
    """
    Function to get the operation identifier corresponding to the Network Service Instance identified by nsId and with
    operation_type.
    Parameters
    ----------
    nsId: string
        Identifier of the Network Service Instance.
    operation_type: string
        Type of operation.
    Returns
    -------
    string
        Identifier of the operation.
    """
    operation = operation_coll.find_one({"nsId": nsId, "operation_type": operation_type})
    if operation is not None:
        return operation["operationId"]
    else:
        return None

def get_operationIdcomplete(nsId, operation_type, status):
    """
    Function to get the operation identifier corresponding to the Network Service Instance identified by nsId and with
    operation_type.
    Parameters
    ----------
    nsId: string
        Identifier of the Network Service Instance.
    operation_type: string
        Type of operation.
    status: string
        Status of the operation
    Returns
    -------
    string
        Identifier of the operation.
    """
    operation = operation_coll.find_one({"nsId": nsId, "operation_type": operation_type, "status": status})
    return operation["operationId"]


def get_operation_status(operationId):
    """
    Function to get the status of an operation identified by operationId.
    Parameters
    ----------
    operationId: string
        Identifier of the operation.
    Returns
    -------
    string
        Status of the operation.
    """
    operation = operation_coll.find_one({"operationId": operationId})
    return operation["status"]


def set_operation_status(operationId, status):
    """
    Function to set the status of an operation identified by operationId
    Parameters
    ----------
    operationId: string
        Identifier of the operation.
    status: string
        Status of the operation.
    Returns
    -------
    None
    """
    operation_coll.update_one({"operationId": operationId}, {"$set": {"status": status}})


def empty_operation_collection():
    """
    deletes all documents in the operation_coll
    Parameters
    ----------
    None
    Returns
    -------
    None
    """
    operation_coll.delete_many({})


####### GUI methods
def get_all_operation():
    """
    Returns all the operations in che collection
    Parameters
    ----------
    Returns
    -------
    list of dict
    """
    return list(operation_coll.find())

def remove_operation_by_id(id):
    """
    Remove a operation from the collection filtered by the id parameter
    Parameters
    ----------
    id: _id of operation
    Returns
    -------
    dict
    """
    output = operation_coll.remove({"_id": ObjectId(id)})


def update_operation(id, body):
    """
    Update an operation from the collection filtered by the id parameter
    Parameters
    ----------
    id: _id of operation
    body: body to update
    Returns
    -------
    ???
    """
    output = operation_coll.update({"_id": ObjectId(id)}, {"$set": body})
    return output
