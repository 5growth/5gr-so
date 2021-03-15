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


class ScaleInfoIm(Model):
    """NOTE: This class is auto generated by the swagger code generator program.

    Do not edit the class manually.
    """

    def __init__(self, aspect_id: str=None, scale_level: int=None):  # noqa: E501
        """ScaleInfoIm - a model defined in Swagger

        :param aspect_id: The aspect_id of this ScaleInfoIm.  # noqa: E501
        :type aspect_id: str
        :param scale_level: The scale_level of this ScaleInfoIm.  # noqa: E501
        :type scale_level: int
        """
        self.swagger_types = {
            "aspect_id": str,
            "scale_level": int
        }

        self.attribute_map = {
            "aspect_id": "aspectId",
            "scale_level": "scaleLevel"
        }

        self._aspect_id = aspect_id
        self._scale_level = scale_level

    @classmethod
    def from_dict(cls, dikt) -> "ScaleInfoIm":
        """Returns the dict as a model

        :param dikt: A dict.
        :type: dict
        :return: The ScaleInfo_im of this ScaleInfoIm.  # noqa: E501
        :rtype: ScaleInfoIm
        """
        return util.deserialize_model(dikt, cls)

    @property
    def aspect_id(self) -> str:
        """Gets the aspect_id of this ScaleInfoIm.


        :return: The aspect_id of this ScaleInfoIm.
        :rtype: str
        """
        return self._aspect_id

    @aspect_id.setter
    def aspect_id(self, aspect_id: str):
        """Sets the aspect_id of this ScaleInfoIm.


        :param aspect_id: The aspect_id of this ScaleInfoIm.
        :type aspect_id: str
        """
        if aspect_id is None:
            raise ValueError("Invalid value for `aspect_id`, must not be `None`")  # noqa: E501

        self._aspect_id = aspect_id

    @property
    def scale_level(self) -> int:
        """Gets the scale_level of this ScaleInfoIm.


        :return: The scale_level of this ScaleInfoIm.
        :rtype: int
        """
        return self._scale_level

    @scale_level.setter
    def scale_level(self, scale_level: int):
        """Sets the scale_level of this ScaleInfoIm.


        :param scale_level: The scale_level of this ScaleInfoIm.
        :type scale_level: int
        """
        if scale_level is None:
            raise ValueError("Invalid value for `scale_level`, must not be `None`")  # noqa: E501

        self._scale_level = scale_level