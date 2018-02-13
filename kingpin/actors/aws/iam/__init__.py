# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Copyright 2018 Nextdoor.com, Inc

"""
:mod:`kingpin.actors.aws.iam`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: User
   :noindex:

.. autoclass:: Group
   :noindex:

.. autoclass:: Role
   :noindex:

.. autoclass:: InstanceProfile
   :noindex:

.. autoclass:: UploadCert
   :noindex:

.. autoclass:: DeleteCert
   :noindex:
"""

import logging

# Bring in our sub class actors into the iam namespace
from kingpin.actors.aws.iam.certs import UploadCert, DeleteCert
from kingpin.actors.aws.iam.entities import User, Group, Role, InstanceProfile

log = logging.getLogger(__name__)

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'

# Quiet down PyFlakes
User
Group
Role
InstanceProfile
UploadCert
DeleteCert
