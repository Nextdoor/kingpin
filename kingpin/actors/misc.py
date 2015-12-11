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
:mod:`kingpin.actors.misc`
^^^^^^^^^^^^^^^^^^^^^^^^^^

These are common utility Actors that don't really need their own
dedicated packages. Things like sleep timers, loggers, etc.

**Optional Environment Variables**

:URLLIB_DEBUG:
  Set this variable to enable extreme debug logging of the URLLIB requests made
  by the RightScale/AWS actors.  *Note, this is very insecure as
  headers/cookies/etc. are exposed*
"""

import StringIO
import logging
import urllib

from tornado import gen
from tornado import httpclient
from kingpin.actors import utils as actor_utils
from kingpin import exceptions as kingpin_exceptions

from kingpin import schema
from kingpin import utils
from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.constants import REQUIRED

log = logging.getLogger(__name__)

__author__ = ('Matt Wise <matt@nextdoor.com>, '
              'Mikhail Simin <mikhail@nextdoor.com>')


class Macro(base.BaseActor):

    """Parses a kingpin JSON file, instantiates and executes it.

    **Parse JSON**

    Kingpin JSON has 2 passes at its validity. JSON syntax must be valid, with
    the exception of a few useful deviations allowed by `demjson
    <http://deron.meranda.us/python/demjson/>`_ parser. Main
    one being the permission of inline comments via ``/* this */`` syntax.

    The second pass is validating the Schema. The JSON file will be validated
    for schema-conformity as one of the first things that happens at load-time
    when the app starts up. If it fails, you will be notified immediately.

    Lastly after JSON is established to be valid, all the tokens are replaced
    with their specified value. Any key/value pair passed in the ``tokens``
    option will be available inside of the JSON file as ``%KEY%`` and replaced
    with the value at this time.

    In a situation where nested Macro executions are invoked the tokens *do
    not* propagate from outter macro into the inner. This allows to reuse token
    names, but forces the user to specify every token needed. Similarly, if
    environment variables are used for token replacement in the main file,
    these tokens are not available in the subsequent macros.

    **Pre-Instantiation**

    In an effort to prevent mid-run errors, we pre-instantiate all Actor
    objects all at once before we ever begin executing code. This ensures that
    major typos or misconfigurations in the JSON will be caught early on.

    **Execution**

    `misc.Macro` actor simply calls the `execute()` method of the most-outter
    actor; be it a single action, or a group actor.

    **Options**

    :file:
      String of local path to a JSON file.

    :tokens:
      Dictionary to search/replace within the file.

    **Examples**

    .. code-block:: json

       { "desc": "Stage 1",
         "actor": "misc.Macro",
         "options": {
           "file": "deployment/stage-1.json",
           "tokens": {
             "TIMEOUT": 360,
             "RELEASE": "%RELEASE%"
           }
         }
       }

    **Dry Mode**

    Fully supported -- instantiates the actor inside of JSON with dry=True. The
    behavior of the consecutive actor is unique to each; read their description
    for more information on dry mode.
    """

    # By default, group actors have no timeout. We rely on the individual
    # actors to expire on their own. This is, of course, overrideable in the
    # JSON.
    default_timeout = None

    all_options = {
        'macro': (str, REQUIRED,
                  "Path to a Kingpin JSON file. http(s)://, file:///, "
                  "absolute or relative file paths."),
        'tokens': (dict, {}, "Tokens passed into the JSON file.")
    }

    def __init__(self, *args, **kwargs):
        """Pre-parse the json file and compile actors."""

        super(Macro, self).__init__(*args, **kwargs)

        # Temporary check that macro is a local file.
        self._check_macro()

        self.log.info('Preparing actors from %s' % self.option('macro'))

        # Copy the tmp file / download a remote macro
        macro_file = self._get_macro()

        # Parse json, and insert tokens.
        config = self._get_config_from_json(macro_file)

        # Check schema for compatibility
        self._check_schema(config)

        # Instantiate the first actor, but don't execute it.
        # Any errors raised by this actor should be attributed to it, and not
        # this Macro actor. No try/catch here
        self.initial_actor = actor_utils.get_actor(config, dry=self._dry)

    def _check_macro(self):
        """For now we are limiting the functionality."""

        prohibited = ('ftp://',)
        if self.option('macro').startswith(prohibited):
            raise exceptions.UnrecoverableActorFailure(
                'Macro actor is cannot handle ftp fetching yet..')

    def _get_macro(self):
        """Return a buffer to the macro file.

        Will download a remote file in-memory and return a buffer, or
        open the local file and return a buffer to that file.
        """

        remote = ('http://', 'https://')
        if self.option('macro').startswith(remote):
            client = httpclient.HTTPClient()
            try:
                R = client.fetch(self.option('macro'))
            except Exception as e:
                raise exceptions.UnrecoverableActorFailure(e)
            finally:
                client.close()
            buf = StringIO.StringIO()
            # Set buffer representation for debug printing.
            buf.__repr__ = lambda: (
                '<In-memory file from "%s">' % self.option('macro'))
            buf.write(R.body)
            buf.seek(0)
            client.close()
            return buf

        try:
            instance = open(self.option('macro'))
        except IOError as e:
            raise exceptions.UnrecoverableActorFailure(e)
        return instance

    def _get_config_from_json(self, json_file):
        """Convert a json file into a dict() with inserted ENV vars.

        Run the JSON dictionary through our environment parser and return
        back a dictionary with all of the %XX% keys swapped out with
        environment variables.

        Args:
            json_file: A path string to a file, or an open() file stream.

        Returns:
            Dictionary adhering to our schema.

        Raises:
            UnrecoverableActorFailure -
                if parsing json or inserting env vars fails.
        """

        self.log.debug('Parsing %s' % json_file)
        try:
            config = utils.convert_json_to_dict(
                json_file=json_file,
                tokens=self.option('tokens'))
        except Exception as e:
            raise exceptions.UnrecoverableActorFailure(e)

        return config

    def _check_schema(self, config):
        # Run the dict through our schema validator quickly
        self.log.debug('Validating schema for %s' % self.option('macro'))
        try:
            schema.validate(config)
        except kingpin_exceptions.InvalidJSON as e:
            self.log.critical('Invalid JSON Schema.')
            raise exceptions.UnrecoverableActorFailure(e)

    @gen.coroutine
    def _execute(self):
        # initial_actor is configured with same dry parameter as this actor.
        # Just execute it and the rest will be handled internally.
        yield self.initial_actor.execute()


class Sleep(base.BaseActor):

    """Sleeps for an arbitrary number of seconds.

    **Options**

    :sleep:
      Integer of seconds to sleep.

    **Examples**

    .. code-block:: json

       { "actor": "misc.Sleep",
         "desc": "Sleep for 60 seconds",
         "options": {
           "sleep": 60
         }
       }

    **Dry Mode**

    Fully supported -- does not actually sleep, just pretends to.
    """

    all_options = {
        'sleep': ((int, float, str), REQUIRED,
                  'Number of seconds to do nothing.')
    }

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished."""

        self.log.debug('Sleeping for %s seconds' % self.option('sleep'))

        sleep = self.option('sleep')

        if isinstance(sleep, basestring):
            sleep = float(sleep)

        if not self._dry:
            yield utils.tornado_sleep(seconds=sleep)


class GenericHTTP(base.HTTPBaseActor):

    """A very simple actor that allows GET/POST methods over HTTP.

    Does a GET or a POST to a specified URL.

    **Options**

    :url:
      Destination URL

    :data:
      Optional POST data as a `dict`

    :username:
      Optional for HTTPAuth.

    :password:
      Optional for HTTPAuth.

    **Examples**

    .. code-block:: json

       { "actor": "misc.GenericHTTP",
         "desc": "Make a simple web call",
         "options": {
           "url": "http://example.com/rest/api/v1?id=123&action=doit",
           "username": "secret",
           "password": "%SECRET_PASSWORD%"
         }
       }

    **Dry Mode**

    Will not do anything in dry mode except print a log statement.
    """

    all_options = {
        'url': (str, REQUIRED, 'Domain name + query string to fetch'),
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
