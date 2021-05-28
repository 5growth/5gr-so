# Copyright 2021 CTTC www.cttc.es
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
Database of Notifications
DB structure:
    nsId: string
    type: string
    text: string
    time: string
"""
# python imports
from json import dumps, loads, load

# mongodb imports
from bson import ObjectId
from pymongo import MongoClient

# project imports
from db import db_ip, db_port
from nbi import log_queue

# create the 5gtso db
ns_client = MongoClient(db_ip, db_port)
fgtso_db = ns_client.fgtso

# create notification collection
notification_coll = fgtso_db.notification


# GUI methods
# notification collection functions
def create_notification_record(notification_record):
    """
    Creates an entry in the notification_coll with
    Parameters
    ----------
    notification_record: json
        json containing the notification information, format:
            nsId: string
            type: string
            text: string
            time: string
    Returns
    -------
    None
    """
    output = notification_coll.insert(notification_record)

def get_all_notifications():
    """
    Returns all the notifications in the collection
    Parameters
    ----------
    Returns
    -------
    list of dict
    """
    return list(notification_coll.find())


def remove_notification_by_id(id):
    """
    Remove a Notification from the collection filtered by the id parameter
    Parameters
    ----------
    id: _id of notification
    Returns
    -------
    dict
    """
    output = notification_coll.remove({"_id": ObjectId(id)})


def update_notification(id, body):
    """
    Update a Notification from the collection filtered by the id parameter
    Parameters
    ----------
    id: _id of notification
    Returns
    -------
    ???
    """
    output = notification_coll.update({"_id": ObjectId(id)}, {"$set": body})
    return output


def empty_notification_collection():
    """
    deletes all documents in the notification Collection
    Parameters
    ----------
    None
    Returns
    -------
    None
    """
    notification_coll.delete_many({})