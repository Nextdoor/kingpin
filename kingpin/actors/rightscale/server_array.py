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

"""RightScale Actors"""

import logging

from tornado import gen
from tornado import ioloop

from kingpin.actors import exceptions
from kingpin.actors.rightscale import api
from kingpin.actors.rightscale import base

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


class Clone(base.RightScaleBaseActor):
    """Clones a RightScale Server Array."""

    def __init__(self, *args, **kwargs):
        """Initializes the Actor.

        Args:
            desc: String description of the action being executed.
            options: Dictionary with the following settings:
              { 'sleep': <int of time to sleep> }
        """
        super(Clone, self).__init__(*args, **kwargs)

        if 'source' not in self._options:
            raise exceptions.InvalidOptions('Missing "source" array name.')
        if 'dest' not in self._options:
            raise exceptions.InvalidOptions('Missing "dest" array name.')

        self._source = self._options['source']
        self._dest = self._options['dest']

    @gen.coroutine
    def _execute(self):
        log.debug('[%s] Finding template Array: %s' %
                  (self._desc, self._source))

        # First, find the array we're copying from. If this fails, even in
        # dry-mode, we exit out because the template array needs to be there!
        try:
            source_array = yield self._client.find_server_arrays(
                self._source, exact=True)
        except api.ServerArrayException as e:
            log.error('[%s] Error: Could not find server template to clone'
                      ' from. Exiting operation.' % self._desc)
            raise

        # Next, get the resource ID number for the source array
        source_array_id = self._client.get_res_id(source_array)

        # Now, clone the array!
        new_array = yield self._client.clone_server_array(
            source_array_id, 'foo')

        raise gen.Return(new_array)
