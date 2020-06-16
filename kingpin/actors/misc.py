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

import io
import json
import logging
import urllib.request
import urllib.parse
import urllib.error

from tornado import gen
from tornado import httpclient
from kingpin.actors import utils as actor_utils
from kingpin.actors import group
from kingpin import exceptions as kingpin_exceptions

from kingpin import schema
from kingpin import utils
from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.constants import REQUIRED

log = logging.getLogger(__name__)

__author__ = ('Matt Wise <matt@nextdoor.com>, '
              'Mikhail Simin <mikhail@nextdoor.com>')


class Note(base.BaseActor):

    """Print any message to log."""

    all_options = {
        'message': (str, REQUIRED, 'Message to log.')
    }

    desc = "Info Log"

    @gen.coroutine
    def _execute(self):
        self.log.info(self.option('message'))


class Macro(base.BaseActor):

    """Parses a kingpin script, instantiates and executes it.

    **Parse JSON/YAML**

    Kingpin JSON/YAML has 2 passes at its validity. Script syntax must be
    valid, with the exception of a few useful deviations allowed by `demjson
    <http://deron.meranda.us/python/demjson/>`_ parser. Main
    one being the permission of inline comments via ``/* this */`` syntax.

    The second pass is validating the Schema. The script will be validated
    for schema-conformity as one of the first things that happens at load-time
    when the app starts up. If it fails, you will be notified immediately.

    Lastly after the JSON/YAML is established to be valid, all the tokens are
    replaced with their specified value. Any key/value pair passed in the
    ``tokens`` option will be available inside of the JSON file as ``%KEY%``
    and replaced with the value at this time.

    In a situation where nested Macro executions are invoked the tokens *do
    not* propagate from outter macro into the inner. This allows to reuse token
    names, but forces the user to specify every token needed. Similarly, if
    environment variables are used for token replacement in the main file,
    these tokens are not available in the subsequent macros.

    **Pre-Instantiation**

    In an effort to prevent mid-run errors, we pre-instantiate all Actor
    objects all at once before we ever begin executing code. This ensures that
    major typos or misconfigurations in the JSON/YAML will be caught early on.

    **Execution**

    `misc.Macro` actor simply calls the `execute()` method of the most-outter
    actor; be it a single action, or a group actor.

    **Options**

    :macro:
      String of local path to a JSON/YAML script.

    :tokens:
      Dictionary to search/replace within the file.

    **Examples**

    .. code-block:: json

       { "desc": "Stage 1",
         "actor": "misc.Macro",
         "options": {
           "macro": "deployment/stage-1.json",
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
                  "Path to a Kingpin script. http(s)://, file:///, "
                  "absolute or relative file paths."),
        'tokens': (dict, {}, "Tokens passed into the JSON file.")
    }

    desc = "Macro: {macro}"

    def __init__(self, *args, **kwargs):
        """Pre-parse the script file and compile actors.

        Note, we override the default init_tokens={} from the base class and
        default it to a _copy_ of the os.environ dict.
        """
        super(Macro, self).__init__(*args, **kwargs)

        # Temporary check that macro is a local file.
        self._check_macro()

        self.log.info('Preparing actors from %s' % self.option('macro'))

        # Take the "init tokens" that were supplied to this actor by its parent
        # and merge them with the explicitly defined tokens in the actor
        # definition itself. Give priority to the explicitly defined tokens on
        # any conflicts.
        self._init_tokens.update(self.option('tokens'))

        # Copy the tmp file / download a remote macro
        macro_file = self._get_macro()

        # Parse script, and insert tokens.
        config = self._get_config_from_script(macro_file)

        # Check schema for compatibility
        self._check_schema(config)

        # Instantiate the first actor, but don't execute it.
        # Any errors raised by this actor should be attributed to it, and not
        # this Macro actor. No try/catch here
        if type(config) == list:
            # List is a Sync group actor
            self.initial_actor = group.Sync(options={'acts': config},
                                            dry=self._dry)
        else:
            # After the schema has been checked, pass in whatever tokens _we_
            # got, off to the soon-to-be-created actor.
            config['init_tokens'] = self._init_tokens.copy()

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
            buf = io.StringIO()
            # Set buffer representation for debug printing.
            buf.__repr__ = lambda: (
                'In-memory file from: %s' % self.option('macro'))
            buf.write(R.body)
            buf.seek(0)
            client.close()
            return buf

        try:
            instance = open(self.option('macro'))
        except IOError as e:
            raise exceptions.UnrecoverableActorFailure(e)
        return instance

    def _get_config_from_script(self, script_file):
        """Convert a script into a dict() with inserted ENV vars.

        Run the JSON dictionary through our environment parser and return
        back a dictionary with all of the %XX% keys swapped out with
        environment variables.

        Args:
            script_file: A path string to a file, or an open() file stream.

        Returns:
            Dictionary adhering to our schema.

        Raises:
            UnrecoverableActorFailure -
                if parsing script or inserting env vars fails.
        """
        self.log.debug('Parsing %s' % script_file)
        try:
            return utils.convert_script_to_dict(
                script_file=script_file,
                tokens=self._init_tokens)
        except (kingpin_exceptions.InvalidScript, LookupError) as e:
            raise exceptions.UnrecoverableActorFailure(e)

    def _check_schema(self, config):
        # Run the dict through our schema validator quickly
        self.log.debug('Validating schema for %s' % self.option('macro'))
        try:
            schema.validate(config)
        except kingpin_exceptions.InvalidScript as e:
            self.log.critical('Invalid Schema.')
            raise exceptions.UnrecoverableActorFailure(e)

    def get_orgchart(self, parent=''):
        """Return orgchart including the actor inside of the macro file."""
        ret = super(Macro, self).get_orgchart(parent=parent)
        macro = self.initial_actor.get_orgchart(parent=str(id(self)))
        return ret + macro

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

    desc = "Sleep {sleep}s"

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished."""

        self.log.debug('Sleeping for %s seconds' % self.option('sleep'))

        sleep = self.option('sleep')

        if isinstance(sleep, str):
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
      Optional POST data as a `dict`. Will convert into key=value&key2=value2..
      Exclusive of `data-json` option.

    :data-json:
      Optional POST data as a `dict`. Will stringify and pass as JSON.
      Exclusive of `data` option.

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
        'data-json': (dict, {}, 'JSON data to attach as POST query'),
        'username': (str, '', 'HTTPAuth username'),
        'password': (str, '', 'HTTPAuth password')
    }

    @gen.coroutine
    def _execute_dry(self):
        is_post = bool(self.option('data'))
        method = ['GET', 'POST'][is_post]

        self.log.info("Would do a %s request to %s"
                      % (method, self.option('url')))
        raise gen.Return()

    @gen.coroutine
    def _execute(self):

        if self._dry:
            raise gen.Return(self._execute_dry())

        # Only generate a JSON text string if a populated dict was passed to
        # data-json.
        datajson = None
        if self.option('data-json'):
            datajson = json.dumps(self.option('data-json'))

        escaped_post = (
            urllib.parse.urlencode(self.option('data')) or
            datajson or None)

        try:
            yield self._fetch(self.option('url'),
                              post=escaped_post,
                              auth_username=self.option('username'),
                              auth_password=self.option('password'))
        except httpclient.HTTPError as e:
            if e.code == 401:
                raise exceptions.InvalidCredentials(e.message)
