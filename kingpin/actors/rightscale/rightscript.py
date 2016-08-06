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
# Copyright 2014 Nextdoor.com, Inc

"""
:mod:`kingpin.actors.rightscale.rightscript`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
"""

import logging

from tornado import gen
import requests

from kingpin.actors import exceptions
from kingpin.actors.rightscale import base
from kingpin.constants import REQUIRED

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


class RightScript(base.RightScaleBaseActor):

    """Manages the state of a RightScale Script

    Options match the documentation in RightScale:
    http://reference.rightscale.com/api1.5/resources/ResourceRightScripts.html

    **Options**

    :name:
      (str) The name of the RightScript.

    :description:
      (str) Optional description of the RightScript.

    :packages:
      (list, str) A list of packages that need to be installed in order to run
      the script.

    :source:

    **Examples**

    Create a high network activity alert on my-array:

    .. code-block:: json

       { "actor": "rightscale.alerts.Create",
         "options": {
           "name": "Set Hostname",
           "ensure": "present",
           "commit": True,
           "description": "Set the hostname to something usable",
           "packages": [ "hostname", "sed" ],
           "source": "./set_hostname.sh"
         }
       }
    """

    all_options = {
        'name': (str, REQUIRED, 'Name of the RightScript to manage'),
        'ensure': (str, 'present',
                   'The condition (operator) in the condition sentence.'),
        'commit': (bool, False, 'Commit the RightScript revision on-change.'),
        'description': (str, None, 'The description of the RightScript.'),
        'packages': (list, [], 'List of packages to install.'),
        'source': (str, REQUIRED, 'File containing the script contents.'),
    }

    def __init__(self, *args, **kwargs):
        """Validate the user-supplied parameters at instantiation time."""
        super(RightScript, self).__init__(*args, **kwargs)

    @gen.coroutine
    def _find_rightscript(self, name):
        """Search for an RightScript by-name and return the resource.

        Note: A non-exact resource match is used below so that we return all of
        the RightSCripts that are matched by name. This method returns the
        resources in a list.

        Args:
            name: RightScale RightScript Name

        Return:
            [<rightcale.Resource objects>]
        """
        log.debug('Searching for RightScript matching: %s' % name)
        found = yield self._client.find_by_name_and_keys(
            self._client._client.right_scripts, name, exact=False)

        if not found:
            log.debug('RightScript matching "%s" could not be found.' % name)
            return

        log.debug('Got RightScript: %s' % found)
        raise gen.Return(found)

    @gen.coroutine
    def _execute(self):
        raise gen.Return()
