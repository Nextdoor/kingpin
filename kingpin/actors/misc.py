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
import tempfile
import urllib

from tornado import gen
from tornado import httpclient
import demjson
from kingpin.actors import utils as actor_utils
from kingpin import exceptions as kingpin_exceptions

from kingpin import utils
from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin import schema

log = logging.getLogger(__name__)

__author__ = ('Matt Wise <matt@nextdoor.com>',
              'Mikhail Simin <mikhail@nextdoor.com>')


class Macro(base.BaseActor):

    """Execute a kingpin JSON file."""

    all_options = {
        'macro': (str, None,
            "Path to a Kingpin JSON file. http(s)://, file:///, "
            "absolute or relative file paths.")),
        'tokens': (dict, {}, "Tokens passed into the JSON file.")
    }

    def __init__(self, *args, **kwargs):
        """Pre-parse the json file and compile actors."""

        super(Macro, self).__init__(*args, **kwargs)

        self.log.info('Preparing actors from %s' % self.option('macro'))

        # `urlretrieve` can handle http, https, file, and ftp equivalently it
        # also handles relative file paths! For now we are limiting the
        # functionality to file only.
        allowed_starts = ('file://', '/', '.')
        if not self.option('macro').startswith(allowed_starts):
            raise exceptions.UnrecoverableActorFailure(
                'Macro actor only supports file processing at the moment')

        # Download / Copy the macro into a temp file.
        (_, tmp_json) = tempfile.mkstemp('.json')
        self.log.debug("Downloading %s to %s" % (self.option('macro'),
                                                 tmp_json))
        try:
            urllib.urlretrieve(self.option('macro'), tmp_json)
        except IOError as e:
            raise exceptions.UnrecoverableActorFailure(e)

        # Run the JSON dictionary through our environment parser and return
        # back a dictionary with all of the %XX% keys swapped out with
        # environment variables.
        self.log.debug('Parsing %s' % tmp_json)
        try:
            config = utils.convert_json_to_dict(
                json_file=tmp_json,
                tokens=self.option('tokens'))
        except kingpin_exceptions.InvalidEnvironment as e:
            self.log.critical('Invalid Configuration Detected.')
            raise exceptions.UnrecoverableActorFailure(e)
        except demjson.JSONDecodeError as e:
            self.log.critical('Invalid JSON Syntax.')
            raise exceptions.UnrecoverableActorFailure(e)

        # Run the dict through our schema validator quickly
        self.log.debug('Validating schema for %s' % tmp_json)
        try:
            schema.validate(config)
        except kingpin_exceptions.InvalidJSON as e:
            self.log.critical('Invalid JSON Schema.')
            raise exceptions.UnrecoverableActorFailure(e)

        # Instantiate the first actor, but don't execute it. By doing this, we
        # can do a pre-flight-check of all of the actors to make sure they
        # instantiate properly.
        # Any errors raised by this actor should be attributed to it, and not
        # this Macro actor. No try/catch here
        initial_actor = actor_utils.get_actor(config, dry=self._dry)

        self.initial_actor = initial_actor

    @gen.coroutine
    def _execute(self):
        # initial_actor is configured with same dry parameter as this actor.
        # Just execute it and the rest will be handled internally.
        yield self.initial_actor.execute()


class Sleep(base.BaseActor):

    """Simple actor that just sleeps for an arbitrary amount of time."""

    all_options = {
        'sleep': ((int, float), None, 'Number of seconds to do nothing.')
    }

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished."""

        self.log.debug('Sleeping for %s seconds' % self.option('sleep'))

        if not self._dry:
            yield utils.tornado_sleep(seconds=self.option('sleep'))


class GenericHTTP(base.HTTPBaseActor):

    """Simple HTTP get/post sending actor."""

    all_options = {
        'url': (str, None, 'Domain name + query string to fetch'),
        'data': (dict, {}, 'Data to attach as a POST query'),
        'username': (str, '', 'HTTPAuth username'),
        'password': (str, '', 'HTTPAuth password')
    }

    @gen.coroutine
    def _execute_dry(self):
        is_post = bool(self.option('data'))
        method = ['POST', 'GET'][is_post]

        self.log.info("Would do a %s request to %s"
                      % (method, self.option('url')))
        raise gen.Return()

    @gen.coroutine
    def _execute(self):

        if self._dry:
            raise gen.Return(self._execute_dry())

        escaped_post = urllib.urlencode(self.option('data')) or None

        try:
            yield self._fetch(self.option('url'),
                              post=escaped_post,
                              auth_username=self.option('username'),
                              auth_password=self.option('password'))
        except httpclient.HTTPError as e:
            if e.code == 401:
                raise exceptions.InvalidCredentials(e.message)
