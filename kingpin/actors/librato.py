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
API_URL = 'https://metrics-api.librato.com/v1/'
ANNOTATIONS_URL = API_URL + 'annotations/'
METRICS_URL = API_URL + 'metrics'  # Used to test auth

TOKEN = os.getenv('LIBRATO_TOKEN', None)
EMAIL = os.getenv('LIBRATO_EMAIL', None)


class Annotation(base.HTTPBaseActor):

    """Simple Librato Message sending actor using their API:
    http://dev.librato.com/v1/post/annotations/:name"""

    required_options = ['title', 'description', 'name']

    def __init__(self, *args, **kwargs):
        """Initializes the Actor.

        Args:
            desc: String description of the action being executed.
            options: Dictionary with the following settings:
              { 'title': <annotation title>,
                'description': <annotation description>,
                'name': <name of the metric to annotate>}
        """
        super(Annotation, self).__init__(*args, **kwargs)

        if not TOKEN:
            raise exceptions.InvalidCredentials(
                'Missing the "LIBRATO_TOKEN" environment variable.')

        if not EMAIL:
            raise exceptions.InvalidCredentials(
                'Missing the "LIBRATO_EMAIL" environment variable.')

    @gen.coroutine
    def _fetch_wrapper(self, *args, **kwargs):
        """Wrap the superclass _fetch method to catch known Librato errors."""
        try:
            res = yield self._fetch(*args, **kwargs)
        except httpclient.HTTPError as e:
            if e.code == 400:
                # "HTTPError: HTTP 400: Bad Request"
                raise exceptions.BadRequest(
                    'Check your JSON inputs.')
            if e.code == 401:
                # "The authentication you provided is invalid."
                raise exceptions.InvalidCredentials(
                    'Librato authentication failed.')
            raise

        raise gen.Return(res)

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        raises: gen.Return(True)
        """

        if self._dry:
            self.log.info('Testing Librato auth, skipping annotation')
            msg = ("Would have annotated metric "
                   "'%s' with title:'%s', description:'%s'")
            self.log.info(msg % (self._options['name'], self._options['title'],
                                 self._options['description']))
            yield self._fetch_wrapper(
                METRICS_URL, auth_username=EMAIL, auth_password=TOKEN)
        else:
            self.log.info(
                "Annotating metric '%s' with title:'%s', description:'%s'" % (
                    self._options['name'], self._options['title'],
                    self._options['description']))
            url = ANNOTATIONS_URL + self._options['name']
            args = urllib.urlencode(
                {'title': self._options['title'],
                 'description': self._options['description']})

            yield self._fetch_wrapper(url, post=args,
                                      auth_username=EMAIL, auth_password=TOKEN)
        raise gen.Return(True)
