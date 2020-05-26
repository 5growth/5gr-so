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
from swagger_server.models.key_value_pair import KeyValuePair  # noqa: F401,E501
from swagger_server import util


class InlineResponse2002(Model):
    """NOTE: This class is auto generated by the swagger code generator program.

    Do not edit the class manually.
    """

    def __init__(self, instance_info: KeyValuePair=None):  # noqa: E501
        """InlineResponse2002 - a model defined in Swagger

        :param instance_info: The instance_info of this InlineResponse2002.  # noqa: E501
        :type instance_info: KeyValuePair
        """
        self.swagger_types = {
            'instance_info': KeyValuePair
        }

        self.attribute_map = {
            'instance_info': 'instanceInfo'
        }

        self._instance_info = instance_info

    @classmethod
    def from_dict(cls, dikt) -> 'InlineResponse2002':
        """Returns the dict as a model

        :param dikt: A dict.
        :type: dict
        :return: The inline_response_200_2 of this InlineResponse2002.  # noqa: E501
        :rtype: InlineResponse2002
        """
        return util.deserialize_model(dikt, cls)

    @property
    def instance_info(self) -> KeyValuePair:
        """Gets the instance_info of this InlineResponse2002.


        :return: The instance_info of this InlineResponse2002.
        :rtype: KeyValuePair
        """
        return self._instance_info

    @instance_info.setter
    def instance_info(self, instance_info: KeyValuePair):
        """Sets the instance_info of this InlineResponse2002.


        :param instance_info: The instance_info of this InlineResponse2002.
        :type instance_info: KeyValuePair
        """
        if instance_info is None:
            raise ValueError("Invalid value for `instance_info`, must not be `None`")  # noqa: E501

        self._instance_info = instance_info
