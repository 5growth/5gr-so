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
from swagger_server.models.user_defined_datadef import UserDefinedDatadef  # noqa: F401,E501
from swagger_server import util


class AppOnboardingRequest(Model):
    """NOTE: This class is auto generated by the swagger code generator program.

    Do not edit the class manually.
    """

    def __init__(self, name: str=None, version: str=None, provider: str=None, checksum: str=None, app_package_path: str=None, user_defined_data: UserDefinedDatadef=None):  # noqa: E501
        """AppOnboardingRequest - a model defined in Swagger

        :param name: The name of this AppOnboardingRequest.  # noqa: E501
        :type name: str
        :param version: The version of this AppOnboardingRequest.  # noqa: E501
        :type version: str
        :param provider: The provider of this AppOnboardingRequest.  # noqa: E501
        :type provider: str
        :param checksum: The checksum of this AppOnboardingRequest.  # noqa: E501
        :type checksum: str
        :param app_package_path: The app_package_path of this AppOnboardingRequest.  # noqa: E501
        :type app_package_path: str
        :param user_defined_data: The user_defined_data of this AppOnboardingRequest.  # noqa: E501
        :type user_defined_data: UserDefinedDatadef
        """
        self.swagger_types = {
            'name': str,
            'version': str,
            'provider': str,
            'checksum': str,
            'app_package_path': str,
            'user_defined_data': UserDefinedDatadef
        }

        self.attribute_map = {
            'name': 'name',
            'version': 'version',
            'provider': 'provider',
            'checksum': 'checksum',
            'app_package_path': 'appPackagePath',
            'user_defined_data': 'userDefinedData'
        }

        self._name = name
        self._version = version
        self._provider = provider
        self._checksum = checksum
        self._app_package_path = app_package_path
        self._user_defined_data = user_defined_data

    @classmethod
    def from_dict(cls, dikt) -> 'AppOnboardingRequest':
        """Returns the dict as a model

        :param dikt: A dict.
        :type: dict
        :return: The AppOnboardingRequest of this AppOnboardingRequest.  # noqa: E501
        :rtype: AppOnboardingRequest
        """
        return util.deserialize_model(dikt, cls)

    @property
    def name(self) -> str:
        """Gets the name of this AppOnboardingRequest.


        :return: The name of this AppOnboardingRequest.
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name: str):
        """Sets the name of this AppOnboardingRequest.


        :param name: The name of this AppOnboardingRequest.
        :type name: str
        """
        if name is None:
            raise ValueError("Invalid value for `name`, must not be `None`")  # noqa: E501

        self._name = name

    @property
    def version(self) -> str:
        """Gets the version of this AppOnboardingRequest.


        :return: The version of this AppOnboardingRequest.
        :rtype: str
        """
        return self._version

    @version.setter
    def version(self, version: str):
        """Sets the version of this AppOnboardingRequest.


        :param version: The version of this AppOnboardingRequest.
        :type version: str
        """
        if version is None:
            raise ValueError("Invalid value for `version`, must not be `None`")  # noqa: E501

        self._version = version

    @property
    def provider(self) -> str:
        """Gets the provider of this AppOnboardingRequest.


        :return: The provider of this AppOnboardingRequest.
        :rtype: str
        """
        return self._provider

    @provider.setter
    def provider(self, provider: str):
        """Sets the provider of this AppOnboardingRequest.


        :param provider: The provider of this AppOnboardingRequest.
        :type provider: str
        """
        if provider is None:
            raise ValueError("Invalid value for `provider`, must not be `None`")  # noqa: E501

        self._provider = provider

    @property
    def checksum(self) -> str:
        """Gets the checksum of this AppOnboardingRequest.


        :return: The checksum of this AppOnboardingRequest.
        :rtype: str
        """
        return self._checksum

    @checksum.setter
    def checksum(self, checksum: str):
        """Sets the checksum of this AppOnboardingRequest.


        :param checksum: The checksum of this AppOnboardingRequest.
        :type checksum: str
        """
        if checksum is None:
            raise ValueError("Invalid value for `checksum`, must not be `None`")  # noqa: E501

        self._checksum = checksum

    @property
    def app_package_path(self) -> str:
        """Gets the app_package_path of this AppOnboardingRequest.


        :return: The app_package_path of this AppOnboardingRequest.
        :rtype: str
        """
        return self._app_package_path

    @app_package_path.setter
    def app_package_path(self, app_package_path: str):
        """Sets the app_package_path of this AppOnboardingRequest.


        :param app_package_path: The app_package_path of this AppOnboardingRequest.
        :type app_package_path: str
        """
        if app_package_path is None:
            raise ValueError("Invalid value for `app_package_path`, must not be `None`")  # noqa: E501

        self._app_package_path = app_package_path

    @property
    def user_defined_data(self) -> UserDefinedDatadef:
        """Gets the user_defined_data of this AppOnboardingRequest.


        :return: The user_defined_data of this AppOnboardingRequest.
        :rtype: UserDefinedDatadef
        """
        return self._user_defined_data

    @user_defined_data.setter
    def user_defined_data(self, user_defined_data: UserDefinedDatadef):
        """Sets the user_defined_data of this AppOnboardingRequest.


        :param user_defined_data: The user_defined_data of this AppOnboardingRequest.
        :type user_defined_data: UserDefinedDatadef
        """

        self._user_defined_data = user_defined_data
