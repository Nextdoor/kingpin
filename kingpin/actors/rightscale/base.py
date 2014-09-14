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

import collections
import logging
import os

from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.actors.rightscale import api

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


TOKEN = os.getenv('RIGHTSCALE_TOKEN', None)
ENDPOINT = os.getenv('RIGHTSCALE_ENDPOINT', 'https://my.rightscale.com')


class RightScaleBaseActor(base.BaseActor):

    """Abstract class for creating RightScale cloud actors."""

    def __init__(self, *args, **kwargs):
        """Initializes the Actor."""
        super(RightScaleBaseActor, self).__init__(*args, **kwargs)

        if not TOKEN:
            raise exceptions.InvalidCredentials(
                'Missing the "RIGHTSCALE_TOKEN" environment variable.')

        self._client = api.RightScale(token=TOKEN, endpoint=ENDPOINT)

    def _generate_rightscale_params(self, prefix, params):
        """Utility function for creating RightScale-style parameters.

        RightScale takes inputs in the form of a hash of key/value pairs, but
        these pairs are in a strange pseudo-dict form. This method takes a
        standard hash and converts it into a rightscale-compatible form.

        For example, take this dict:

            {'name': 'unittest-name',
             'bounds': { 'min_count': 3}

        We return:

            {'server_array[name]': 'unittest-name',
             'server_array[bounds][min_count]': 3}

        Args:
            prefix: The key-prefix to use (ie, 'server_array')
            params: The dictionary to squash

        Returns:
            A single-level dictionary of key/value pairs.
        """
        if not type(params) == dict:
            raise exceptions.InvalidOptions(
                'Parameters passed in must be in the form of a dict.')

        # Nested loop that compresses a multi level dictinary into a flat
        # dict of key/value pairs.
        def flatten(d, parent_key=prefix, sep='_'):
            items = []
            for k, v in d.items():
                new_key = parent_key + '[' + k + ']' if parent_key else k
                if isinstance(v, collections.MutableMapping):
                    items.extend(flatten(v, new_key).items())
                else:
                    items.append((new_key, v))
            return dict(items)
        return flatten(params)
