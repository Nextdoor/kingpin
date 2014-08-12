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

"""Misc Actor objects"""

import logging
import time

from tornado import gen
from tornado import ioloop

from deployer.actors import base
from deployer.actors import exceptions

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


class Sleep(base.ActorBase):
    """Simple actor that just sleeps for an arbitrary amount of time."""

    @gen.coroutine
    def _execute(self, desc, options):
        """Executes an actor and yields the results when its finished.

        args:
            desc: String description of the action being executed.
            options: Dictionary with the following settings:
              { 'sleep': <int of time to sleep> }

        raises: gen.Return(True)
        """
        if not 'sleep' in options:
            raise exceptions.InvalidOptions('Missing "sleep" option.')

        sleep = options['sleep']

        log.debug('[%s] Sleeping for %s seconds...' % (desc, sleep))
        yield gen.Task(ioloop.IOLoop.current().add_timeout, time.time() + sleep)

        raise gen.Return(True)
