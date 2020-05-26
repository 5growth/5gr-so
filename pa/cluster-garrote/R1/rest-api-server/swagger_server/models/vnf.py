# coding: utf-8

from __future__ import absolute_import
from datetime import date, datetime  # noqa: F401

from typing import List, Dict  # noqa: F401

from swagger_server.models.base_model_ import Model
from swagger_server.models.location import Location  # noqa: F401,E501
from swagger_server.models.vnf_requirements import VNFRequirements  # noqa: F401,E501
from swagger_server import util


class VNF(Model):
    """NOTE: This class is auto generated by the swagger code generator program.

    Do not edit the class manually.
    """

    def __init__(self, vn_fid=None, instances=None, location=None, requirements=None, failure_rate=None, processing_latency=None):  # noqa: E501
        """VNF - a model defined in Swagger

        :param vn_fid: The vn_fid of this VNF.  # noqa: E501
        :type vn_fid: str
        :param instances: The instances of this VNF.  # noqa: E501
        :type instances: float
        :param location: The location of this VNF.  # noqa: E501
        :type location: Location
        :param requirements: The requirements of this VNF.  # noqa: E501
        :type requirements: VNFRequirements
        :param failure_rate: The failure_rate of this VNF.  # noqa: E501
        :type failure_rate: float
        :param processing_latency: The processing_latency of this VNF.  # noqa: E501
        :type processing_latency: float
        """
        self.swagger_types = {
            'vn_fid': str,
            'instances': float,
            'location': Location,
            'requirements': VNFRequirements,
            'failure_rate': float,
            'processing_latency': float
        }

        self.attribute_map = {
            'vn_fid': 'VNFid',
            'instances': 'instances',
            'location': 'location',
            'requirements': 'requirements',
            'failure_rate': 'failure_rate',
            'processing_latency': 'processing_latency'
        }

        self._vn_fid = vn_fid
        self._instances = instances
        self._location = location
        self._requirements = requirements
        self._failure_rate = failure_rate
        self._processing_latency = processing_latency

    @classmethod
    def from_dict(cls, dikt):
        """Returns the dict as a model

        :param dikt: A dict.
        :type: dict
        :return: The VNF of this VNF.  # noqa: E501
        :rtype: VNF
        """
        return util.deserialize_model(dikt, cls)

    @property
    def vn_fid(self):
        """Gets the vn_fid of this VNF.

        VNF identifier  # noqa: E501

        :return: The vn_fid of this VNF.
        :rtype: str
        """
        return self._vn_fid

    @vn_fid.setter
    def vn_fid(self, vn_fid):
        """Sets the vn_fid of this VNF.

        VNF identifier  # noqa: E501

        :param vn_fid: The vn_fid of this VNF.
        :type vn_fid: str
        """
        if vn_fid is None:
            raise ValueError("Invalid value for `vn_fid`, must not be `None`")  # noqa: E501

        self._vn_fid = vn_fid

    @property
    def instances(self):
        """Gets the instances of this VNF.

        Number of instances of this VNF to deploy  # noqa: E501

        :return: The instances of this VNF.
        :rtype: float
        """
        return self._instances

    @instances.setter
    def instances(self, instances):
        """Sets the instances of this VNF.

        Number of instances of this VNF to deploy  # noqa: E501

        :param instances: The instances of this VNF.
        :type instances: float
        """

        self._instances = instances

    @property
    def location(self):
        """Gets the location of this VNF.


        :return: The location of this VNF.
        :rtype: Location
        """
        return self._location

    @location.setter
    def location(self, location):
        """Sets the location of this VNF.


        :param location: The location of this VNF.
        :type location: Location
        """

        self._location = location

    @property
    def requirements(self):
        """Gets the requirements of this VNF.


        :return: The requirements of this VNF.
        :rtype: VNFRequirements
        """
        return self._requirements

    @requirements.setter
    def requirements(self, requirements):
        """Sets the requirements of this VNF.


        :param requirements: The requirements of this VNF.
        :type requirements: VNFRequirements
        """
        if requirements is None:
            raise ValueError("Invalid value for `requirements`, must not be `None`")  # noqa: E501

        self._requirements = requirements

    @property
    def failure_rate(self):
        """Gets the failure_rate of this VNF.

        Probability that a VNF instance of this type fails.  # noqa: E501

        :return: The failure_rate of this VNF.
        :rtype: float
        """
        return self._failure_rate

    @failure_rate.setter
    def failure_rate(self, failure_rate):
        """Sets the failure_rate of this VNF.

        Probability that a VNF instance of this type fails.  # noqa: E501

        :param failure_rate: The failure_rate of this VNF.
        :type failure_rate: float
        """

        self._failure_rate = failure_rate

    @property
    def processing_latency(self):
        """Gets the processing_latency of this VNF.

        Latency for a VNF instance with the specific characteristics to process a service request.  # noqa: E501

        :return: The processing_latency of this VNF.
        :rtype: float
        """
        return self._processing_latency

    @processing_latency.setter
    def processing_latency(self, processing_latency):
        """Sets the processing_latency of this VNF.

        Latency for a VNF instance with the specific characteristics to process a service request.  # noqa: E501

        :param processing_latency: The processing_latency of this VNF.
        :type processing_latency: float
        """

        self._processing_latency = processing_latency
