# coding: utf-8

from __future__ import absolute_import
from datetime import date, datetime  # noqa: F401

from typing import List, Dict  # noqa: F401

from swagger_server.models.base_model_ import Model
from swagger_server.models.vnf import VNF  # noqa: F401,E501
from swagger_server.models.vnf_link import VNFLink  # noqa: F401,E501
from swagger_server import util


class NetworkService(Model):
    """NOTE: This class is auto generated by the swagger code generator program.

    Do not edit the class manually.
    """

    def __init__(self, id=None, name=None, vn_fs=None, vnf_links=None, max_latency=None, target_availability=None, max_cost=None):  # noqa: E501
        """NetworkService - a model defined in Swagger

        :param id: The id of this NetworkService.  # noqa: E501
        :type id: str
        :param name: The name of this NetworkService.  # noqa: E501
        :type name: str
        :param vn_fs: The vn_fs of this NetworkService.  # noqa: E501
        :type vn_fs: List[VNF]
        :param vnf_links: The vnf_links of this NetworkService.  # noqa: E501
        :type vnf_links: List[VNFLink]
        :param max_latency: The max_latency of this NetworkService.  # noqa: E501
        :type max_latency: float
        :param target_availability: The target_availability of this NetworkService.  # noqa: E501
        :type target_availability: float
        :param max_cost: The max_cost of this NetworkService.  # noqa: E501
        :type max_cost: float
        """
        self.swagger_types = {
            'id': str,
            'name': str,
            'vn_fs': List[VNF],
            'vnf_links': List[VNFLink],
            'max_latency': float,
            'target_availability': float,
            'max_cost': float
        }

        self.attribute_map = {
            'id': 'id',
            'name': 'name',
            'vn_fs': 'VNFs',
            'vnf_links': 'VNFLinks',
            'max_latency': 'max_latency',
            'target_availability': 'target_availability',
            'max_cost': 'max_cost'
        }

        self._id = id
        self._name = name
        self._vn_fs = vn_fs
        self._vnf_links = vnf_links
        self._max_latency = max_latency
        self._target_availability = target_availability
        self._max_cost = max_cost

    @classmethod
    def from_dict(cls, dikt):
        """Returns the dict as a model

        :param dikt: A dict.
        :type: dict
        :return: The NetworkService of this NetworkService.  # noqa: E501
        :rtype: NetworkService
        """
        return util.deserialize_model(dikt, cls)

    @property
    def id(self):
        """Gets the id of this NetworkService.

        Network service identifier  # noqa: E501

        :return: The id of this NetworkService.
        :rtype: str
        """
        return self._id

    @id.setter
    def id(self, id):
        """Sets the id of this NetworkService.

        Network service identifier  # noqa: E501

        :param id: The id of this NetworkService.
        :type id: str
        """
        if id is None:
            raise ValueError("Invalid value for `id`, must not be `None`")  # noqa: E501

        self._id = id

    @property
    def name(self):
        """Gets the name of this NetworkService.

        Name of the network service  # noqa: E501

        :return: The name of this NetworkService.
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this NetworkService.

        Name of the network service  # noqa: E501

        :param name: The name of this NetworkService.
        :type name: str
        """
        if name is None:
            raise ValueError("Invalid value for `name`, must not be `None`")  # noqa: E501

        self._name = name

    @property
    def vn_fs(self):
        """Gets the vn_fs of this NetworkService.

        VNFs composing the service  # noqa: E501

        :return: The vn_fs of this NetworkService.
        :rtype: List[VNF]
        """
        return self._vn_fs

    @vn_fs.setter
    def vn_fs(self, vn_fs):
        """Sets the vn_fs of this NetworkService.

        VNFs composing the service  # noqa: E501

        :param vn_fs: The vn_fs of this NetworkService.
        :type vn_fs: List[VNF]
        """
        if vn_fs is None:
            raise ValueError("Invalid value for `vn_fs`, must not be `None`")  # noqa: E501

        self._vn_fs = vn_fs

    @property
    def vnf_links(self):
        """Gets the vnf_links of this NetworkService.

        Edges of the VNFFG  # noqa: E501

        :return: The vnf_links of this NetworkService.
        :rtype: List[VNFLink]
        """
        return self._vnf_links

    @vnf_links.setter
    def vnf_links(self, vnf_links):
        """Sets the vnf_links of this NetworkService.

        Edges of the VNFFG  # noqa: E501

        :param vnf_links: The vnf_links of this NetworkService.
        :type vnf_links: List[VNFLink]
        """
        if vnf_links is None:
            raise ValueError("Invalid value for `vnf_links`, must not be `None`")  # noqa: E501

        self._vnf_links = vnf_links

    @property
    def max_latency(self):
        """Gets the max_latency of this NetworkService.

        End-to-end latency constraint.  # noqa: E501

        :return: The max_latency of this NetworkService.
        :rtype: float
        """
        return self._max_latency

    @max_latency.setter
    def max_latency(self, max_latency):
        """Sets the max_latency of this NetworkService.

        End-to-end latency constraint.  # noqa: E501

        :param max_latency: The max_latency of this NetworkService.
        :type max_latency: float
        """

        self._max_latency = max_latency

    @property
    def target_availability(self):
        """Gets the target_availability of this NetworkService.

        Target service availability.  # noqa: E501

        :return: The target_availability of this NetworkService.
        :rtype: float
        """
        return self._target_availability

    @target_availability.setter
    def target_availability(self, target_availability):
        """Sets the target_availability of this NetworkService.

        Target service availability.  # noqa: E501

        :param target_availability: The target_availability of this NetworkService.
        :type target_availability: float
        """

        self._target_availability = target_availability

    @property
    def max_cost(self):
        """Gets the max_cost of this NetworkService.

        Cost/budget constraint  # noqa: E501

        :return: The max_cost of this NetworkService.
        :rtype: float
        """
        return self._max_cost

    @max_cost.setter
    def max_cost(self, max_cost):
        """Sets the max_cost of this NetworkService.

        Cost/budget constraint  # noqa: E501

        :param max_cost: The max_cost of this NetworkService.
        :type max_cost: float
        """

        self._max_cost = max_cost
