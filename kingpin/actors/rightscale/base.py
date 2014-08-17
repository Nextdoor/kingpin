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
import os

from tornado import gen

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

#    @gen.coroutine
#    def _fetch_wrapper(self, *args, **kwargs):
#        """Wrap the superclass _fetch method to catch known Hipchat errors."""
#        try:
#            res = yield self._fetch(*args, **kwargs)
#        except httpclient.HTTPError as e:
#            if e.code == 401:
#                # "The authentication you provided is invalid."
#                raise exceptions.InvalidCredentials(
#                    'The "HIPCHAT_TOKEN" supplied is invalid.')
#            if e.code == 403:
#                # "You have exceeded the rate limit"
#                #
#                # TODO: Build a retry mechanism in here with a sleep timer.
#                log.error('Hit the HipChat API Rate Limit. Try again later.')
#                raise
#            raise
#
#  _      raise gen.Return(res)
