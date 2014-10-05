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

"""Librato Actor objects"""

import logging
import os
import urllib

from tornado import gen
from tornado import httpclient

from kingpin.actors import base
from kingpin.actors import exceptions

log = logging.getLogger(__name__)

__author__ = 'Charles McLaughlin <charles@nextdoor.com>'

API_CONTENT_TYPE = 'application/x-www-form-urlencoded'
API_URL = 'https://metrics-api.librato.com/v1/annotations/'
TOKEN = os.getenv('LIBRATO_TOKEN', None)
EMAIL = os.getenv('LIBRATO_EMAIL', None)


class Annotation(base.HTTPBaseActor):

    """Simple Librato Message sending actor using their API:
    http://dev.librato.com/v1/post/annotations/:name"""

    required_options = ['title', 'description']

    def __init__(self, *args, **kwargs):
        """Initializes the Actor.

        Args:
            desc: String description of the action being executed.
            options: Dictionary with the following settings:
              { 'title': <annotation title>,
                'description': <annotation description>,
                'metric': <metric to annotate>}
        """
        super(Annotation, self).__init__(*args, **kwargs)

        if not TOKEN:
            raise exceptions.InvalidCredentials(
                'Missing the "LIBRATO_TOKEN" environment variable.')

    @gen.coroutine
    def _fetch_wrapper(self, *args, **kwargs):
        """Wrap the superclass _fetch method to catch known Librato errors."""
        try:
            res = yield self._fetch(*args, **kwargs)
        except httpclient.HTTPError as e:
            if e.code == 401:
                # "The authentication you provided is invalid."
                raise exceptions.InvalidCredentials(
                    'The "LIBRATO_TOKEN" supplied is invalid.')
            raise

        raise gen.Return(res)

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        raises: gen.Return(True)
        """
        self.log.info('Annotating "%s"' % self._options['title'])
        url = API_URL + self._options['metric']
        args = urllib.urlencode({'title': self._options['title'],
                                 'description': self._options['description']})
        if self._dry:
            # TODO test credentials
            self.log.info('Skipping annotation')
            res = True
        else:
            res = yield self._fetch_wrapper(
                url, post=args, auth_username=EMAIL, auth_password=TOKEN)
        raise gen.Return(res)
