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
Small script to load descriptors into the SO NSD/VNFD catalogues.
"""

# python imports
from json import load
import hashlib

# project imports
import sys
sys.path.append("../../../5Gr-SO")
from nbi import log_process
from db.user_db.user_db import insert_user, empty_user_collection


def main():

    # empty database
    empty_user_collection()

    # insert the the admin user (password 'admin' and role 'Admin')
    default_user = 'admin'
    default_password = 'admin'
    default_role = 'Admin'
    user_record = {"username": default_user,
                   "password": hashlib.md5(default_password.encode()).hexdigest(),
                   "role": default_role}

    insert_user(user_record)

    log_process.terminate()


if __name__ == "__main__":
    main()
