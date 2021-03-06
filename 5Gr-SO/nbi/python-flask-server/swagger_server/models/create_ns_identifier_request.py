# Copyright (C) 2018 CTTC/CERCA
# License: To be defined. Currently use is restricted to partners of the 5G-Transformer project,
#          http://5g-transformer.eu/, no use or redistribution of any kind outside the 5G-Transformer project is
#          allowed.
# Disclaimer: this software is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
# either express or implied.

# coding: utf-8

from __future__ import absolute_import
from datetime import date, datetime  # noqa: F401

from typing import List, Dict  # noqa: F401

from swagger_server.models.base_model_ import Model
from swagger_server import util


class CreateNsIdentifierRequest(Model):
    """NOTE: This class is auto generated by the swagger code generator program.

    Do not edit the class manually.
    """

    def __init__(self, nsd_id: str=None, ns_name: str=None, ns_description: str=None):  # noqa: E501
        """CreateNsIdentifierRequest - a model defined in Swagger

        :param nsd_id: The nsd_id of this CreateNsIdentifierRequest.  # noqa: E501
        :type nsd_id: str
        :param ns_name: The ns_name of this CreateNsIdentifierRequest.  # noqa: E501
        :type ns_name: str
        :param ns_description: The ns_description of this CreateNsIdentifierRequest.  # noqa: E501
        :type ns_description: str
        """
        self.swagger_types = {
            "nsd_id": str,
            "ns_name": str,
            "ns_description": str
        }

        self.attribute_map = {
            "nsd_id": "nsdId",
            "ns_name": "nsName",
            "ns_description": "nsDescription"
        }

        self._nsd_id = nsd_id
        self._ns_name = ns_name
        self._ns_description = ns_description

    @classmethod
    def from_dict(cls, dikt) -> "CreateNsIdentifierRequest":
        """Returns the dict as a model

        :param dikt: A dict.
        :type: dict
        :return: The CreateNsIdentifierRequest of this CreateNsIdentifierRequest.  # noqa: E501
        :rtype: CreateNsIdentifierRequest
        """
        return util.deserialize_model(dikt, cls)

    @property
    def nsd_id(self) -> str:
        """Gets the nsd_id of this CreateNsIdentifierRequest.


        :return: The nsd_id of this CreateNsIdentifierRequest.
        :rtype: str
        """
        return self._nsd_id

    @nsd_id.setter
    def nsd_id(self, nsd_id: str):
        """Sets the nsd_id of this CreateNsIdentifierRequest.


        :param nsd_id: The nsd_id of this CreateNsIdentifierRequest.
        :type nsd_id: str
        """
        if nsd_id is None:
            raise ValueError("Invalid value for `nsd_id`, must not be `None`")  # noqa: E501

        self._nsd_id = nsd_id

    @property
    def ns_name(self) -> str:
        """Gets the ns_name of this CreateNsIdentifierRequest.


        :return: The ns_name of this CreateNsIdentifierRequest.
        :rtype: str
        """
        return self._ns_name

    @ns_name.setter
    def ns_name(self, ns_name: str):
        """Sets the ns_name of this CreateNsIdentifierRequest.


        :param ns_name: The ns_name of this CreateNsIdentifierRequest.
        :type ns_name: str
        """
        if ns_name is None:
            raise ValueError("Invalid value for `ns_name`, must not be `None`")  # noqa: E501

        self._ns_name = ns_name

    @property
    def ns_description(self) -> str:
        """Gets the ns_description of this CreateNsIdentifierRequest.


        :return: The ns_description of this CreateNsIdentifierRequest.
        :rtype: str
        """
        return self._ns_description

    @ns_description.setter
    def ns_description(self, ns_description: str):
        """Sets the ns_description of this CreateNsIdentifierRequest.


        :param ns_description: The ns_description of this CreateNsIdentifierRequest.
        :type ns_description: str
        """

        self._ns_description = ns_description
