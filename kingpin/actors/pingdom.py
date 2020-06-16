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
:mod:`kingpin.actors.pingdom`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Pingdom actors to pause and unpause checks. These are useful when you are aware
of an expected downtime and don't want to be alerted about it. Also known as
Maintenance mode.

**Required Environment Variables**

:PINGDOM_TOKEN:
  Pingdom API Token

:PINGDOM_USER:
  Pingdom Username (email)

:PINGDOM_PASS:
  Pingdom Password
"""

import logging
import os

from tornado import gen
from tornado import httpclient

from tornado_rest_client import api

from kingpin.constants import REQUIRED
from kingpin.actors import base
from kingpin.actors import exceptions

log = logging.getLogger(__name__)

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'


USER = os.getenv('PINGDOM_USER', None)
PASS = os.getenv('PINGDOM_PASS', None)
TOKEN = os.getenv('PINGDOM_TOKEN', None)


class PingdomAPI(api.RestConsumer):

    _ENDPOINT = 'https://api.pingdom.com'
    _CONFIG = {
        'attrs': {
            'checks': {
                'path': '/api/2.0/checks',
                'http_methods': {'get': {}}
            },
            'check': {
                'path': '/api/2.0/checks/%check_id%',
                'http_methods': {'put': {}}
            },
        },
        'auth': {
            'user': USER,
            'pass': PASS
        }
    }


class PingdomClient(api.RestClient):

    # The default exception handling is fine, but the Pingdom API uses a 599 to
    # represent a timeout on the backend of their service.
    _EXCEPTIONS = dict(api.RestClient.EXCEPTIONS)
    _EXCEPTIONS[httpclient.HTTPError]['599'] = None


class PingdomBase(base.BaseActor):

    """Simple Pingdom Abstract Base Object"""

    all_options = {
        'name': (str, REQUIRED, 'Name of the check'),
    }

    def __init__(self, *args, **kwargs):
        """Check required environment variables."""
        super(PingdomBase, self).__init__(*args, **kwargs)

        rest_client = PingdomClient(
            headers={'App-Key': TOKEN}
        )
        self._pingdom_client = PingdomAPI(client=rest_client)

    @gen.coroutine
    def _get_check(self):
        """Get check data for actor's option "name".

        Pingdom returns an array of all checks. This method finds the check
        with the exact name and returns its contents.

        Raises InvalidOptions if the check does not exist.
        """
        resp = yield self._pingdom_client.checks().http_get()
        all_checks = resp['checks']
        check = [c for c in all_checks
                 if c['name'] == self.option('name')]

        if not check:
            raise exceptions.InvalidOptions(
                'Check name "%s" was not found.' % self.option('name'))

        raise gen.Return(check[0])


class Pause(PingdomBase):

    """Start Pingdom Maintenance.

    Pause a particular "check" on Pingdom.

    **Options**

    :name:
      (Str) Name of the check

    **Example**

    .. code-block:: json

       { "actor": "pingdom.Pause",
         "desc": "Run Pause",
         "options": {
           "name": "fill-in"
         }
       }

    **Dry run**

    Will assert that the check name exists, but not take any action on it.
    """

    desc = "Pausing check {name}"

    @gen.coroutine
    def _execute(self):
        check = yield self._get_check()

        if self._dry:
            self.log.info('Would pause %s (%s) pingdom check.' % (
                check['name'], check['hostname']))
            raise gen.Return()

        self.log.info('Pausing %s' % check['name'])
        yield self._pingdom_client.check(
            check_id=check['id']).http_put(paused='true')


class Unpause(PingdomBase):

    """Stop Pingdom Maintenance.

    Unpause a particular "check" on Pingdom.

    **Options**

    :name:
      (Str) Name of the check

    **Example**

    .. code-block:: json

       { "actor": "pingdom.Unpause",
         "desc": "Run unpause",
         "options": {
           "name": "fill-in"
         }
       }

    **Dry run**

    Will assert that the check name exists, but not take any action on it.
    """

    desc = "Unpausing check {name}"

    @gen.coroutine
    def _execute(self):
        check = yield self._get_check()

        if self._dry:
            self.log.info('Would unpause %s (%s) pingdom check.' % (
                check['name'], check['hostname']))
            raise gen.Return()

        self.log.info('Unpausing %s' % check['name'])
        yield self._pingdom_client.check(
            check_id=check['id']).http_put(paused='false')
