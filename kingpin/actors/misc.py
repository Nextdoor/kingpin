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

"""Misc Actor objects.

These are common utility Actors that don't really need their own
dedicated packages. Things like sleep timers, loggers, etc.
"""

import logging
import urllib

from tornado import gen

from kingpin import utils
from kingpin.actors import base

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


class Sleep(base.BaseActor):

    """Simple actor that just sleeps for an arbitrary amount of time."""

    all_options = {
        'sleep': ((int, float), None, 'Number of seconds to do nothing.')
    }

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        raises: gen.Return(True)
        """
        self.log.debug('Sleeping for %s seconds' % self.option('sleep'))
        if not self._dry:
            yield utils.tornado_sleep(seconds=self.option('sleep'))

        raise gen.Return(True)


class GenericHTTP(base.HTTPBaseActor):

    """Simple HTTP get/post sending actor."""

    all_options = {
        'url': (str, None, 'Domain name + query string to fetch'),
        'data': (dict, {}, 'Data to attach as a POST query'),
        'username': (str, '', 'HTTPAuth username'),
        'password': (str, '', 'HTTPAuth password')
    }

    @gen.coroutine
    def _execute(self):

        escaped_post = urllib.urlencode(self.option('data')) or None

        res = yield self._fetch(self.option('url'),
                                post=escaped_post,
                                auth_username=self.option('username'),
                                auth_password=self.option('password'))

        if 'success' in res and (200 <= res['success']['code'] < 300):
            raise gen.Return(True)

        self.log.error('Request failed.')
        self.log.error('Request url: %s' % self.option('url'))
        self.log.error('Request data: %s' % escaped_post)
        self.log.debug('Response: %s' % res)
        raise gen.Return(False)
