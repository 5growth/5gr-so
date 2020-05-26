# Author: Jordi Baranda
# Copyright (C) 2019 CTTC/CERCA
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


class PnfExtCpInfoIm(Model):
    """NOTE: This class is auto generated by the swagger code generator program.

    Do not edit the class manually.
    """

    def __init__(self, cpd_id: str=None, address: str=None):  # noqa: E501
        """PnfExtCpInfoIm - a model defined in Swagger

        :param cpd_id: The cpd_id of this PnfExtCpInfoIm.  # noqa: E501
        :type cpd_id: str
        :param address: The address of this PnfExtCpInfoIm.  # noqa: E501
        :type address: str
        """
        self.swagger_types = {
            "cpd_id": str,
            "address": str
        }

        self.attribute_map = {
            "cpd_id": "cpdId",
            "address": "address"
        }

        self._cpd_id = cpd_id
        self._address = address

    @classmethod
    def from_dict(cls, dikt) -> "PnfExtCpInfoIm":
        """Returns the dict as a model

        :param dikt: A dict.
        :type: dict
        :return: The PnfExtCpInfo_im of this PnfExtCpInfoIm.  # noqa: E501
        :rtype: PnfExtCpInfoIm
        """
        return util.deserialize_model(dikt, cls)

    @property
    def cpd_id(self) -> str:
        """Gets the cpd_id of this PnfExtCpInfoIm.


        :return: The cpd_id of this PnfExtCpInfoIm.
        :rtype: str
        """
        return self._cpd_id

    @cpd_id.setter
    def cpd_id(self, cpd_id: str):
        """Sets the cpd_id of this PnfExtCpInfoIm.


        :param cpd_id: The cpd_id of this PnfExtCpInfoIm.
        :type cpd_id: str
        """
        if cpd_id is None:
            raise ValueError("Invalid value for `cpd_id`, must not be `None`")  # noqa: E501

        self._cpd_id = cpd_id

    @property
    def address(self) -> str:
        """Gets the address of this PnfExtCpInfoIm.


        :return: The address of this PnfExtCpInfoIm.
        :rtype: str
        """
        return self._address

    @address.setter
    def address(self, address: str):
        """Sets the address of this PnfExtCpInfoIm.


        :param address: The address of this PnfExtCpInfoIm.
        :type address: str
        """
        if address is None:
            raise ValueError("Invalid value for `address`, must not be `None`")  # noqa: E501

        self._address = address
