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

"""Base Actor object class

An Actor object is a class that executes a single logical action
on a resource as part of your deployment structure. For example, you
may have an Actor that launches a server array in RightScale, or you
may have one that sends an email.

Each Actor object should do one thing, and one thing only. Its responsible
for being able to execute the operation in both 'dry' and 'non-dry' modes.

The behavior for 'dry' mode can contain real API calls, but should not make
any live changes. It is up to the developer of the Actor to define what
'dry' mode looks like for that particular action.
"""

import json
import logging
import os

from tornado import gen
from tornado import httpclient
from tornado import httputil

from kingpin import utils
from kingpin.actors import exceptions

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


# If super-debug logging is enabled, then we turn on the URLLIB3 HTTP
# request logging. This is extremely verbose and insecure, but useful
# for troubleshooting. URLLIB3 is used by several actors (aws, rightscale),
# so we do this setup here in the base actor class.
if os.getenv('URLLIB_DEBUG', None):
    utils.super_httplib_debug_logging()


class LogAdapter(logging.LoggerAdapter):

    def process(self, msg, kwargs):
        return ('[%s%s] %s' % (self.extra['dry'], self.extra['desc'], msg),
                kwargs)


class BaseActor(object):

    """Abstract base class for Actor objects."""

    required_options = []

    def __init__(self, desc, options, dry=False):
        """Initializes the Actor.

        Args:
            desc: (Str) description of the action being executed.
            options: (Dict) Key/Value pairs that have the options
                     for this action. Values should be primitives.
            dry: (Bool) or not this Actor will actually make changes.
        """
        self._type = '%s.%s' % (self.__module__, self.__class__.__name__)
        self._desc = desc
        self._options = options
        self._dry = dry

        self._setup_log()
        self._validate_options(options)  # Relies on _setup_log() above

        self.log.debug('Initialized')

    def _setup_log(self):
        """Create a customized logging object based on the LogAdapter."""
        name = '%s.%s' % (self.__module__, self.__class__.__name__)
        logger = logging.getLogger(name)
        dry_str = 'DRY: ' if self._dry else ''

        self.log = LogAdapter(logger, {'desc': self._desc, 'dry': dry_str})

    def _validate_options(self, options):
        """Validate that all the required options were passed in.

        Args:
            options: A dictionary of options.

        Raises:
            exceptionsInvalidOptions
        """
        missing_options = []
        for option in self.required_options:
            if option not in options:
                missing_options.append(option)

        if not missing_options:
            return

        self.log.error('Unable to configure Actor with options: %s' % options)

        raise exceptions.InvalidOptions(
            'Missing options: %s' % ' '.join(missing_options))

    # TODO: Write an execution wrapper that logs the time it takes for
    # steps to finish. Wrap execute() with it.

    @gen.coroutine
    def execute(self):
        """Executes an actor and yields the results when its finished.

        Raises:
            gen.Return(result)
        """
        self.log.info('Beginning')
        result = yield self._execute()

        if result:
            self.log.info('Finished successfully.')
        else:
            self.log.warning('Finished with errors.')

        raise gen.Return(result)


class HTTPBaseActor(BaseActor):

    """Abstract base class for an HTTP-client based Actor object.

    This class provides common methods for getting access to asynchronous
    HTTP clients, wrapping the executions in appropriate try/except blocks,
    timeouts, etc.

    If you're writing an Actor that uses a remote REST API, this is the
    base class you should subclass from.
    """

    headers = None

    def _get_http_client(self):
        """Returns an asynchronous web client object

        The object is actually of type SimpleAsyncHTTPClient
        """
        return httpclient.AsyncHTTPClient()

    def _get_method(self, post):
        """Returns the appropriate HTTP Method based on the supplied Post data.

        Args:
            post: The post body you intend to submit in the URL request

        Returns:
            'GET' or 'POST'
        """
        # If there is no post data, set the request method to GET
        if post is not None:
            return 'POST'
        else:
            return 'GET'

    def _generate_escaped_url(self, url, args):
        """Takes in a dictionary of arguments and returns a URL line.

        Sorts the arguments so that the returned string is predictable and in
        alphabetical order. Effectively wraps the tornado.httputil.url_concat
        method and properly strips out None values, as well as lowercases
        Bool values.

        Args:
            url: (Str) The URL to append the arguments to
            args: (Dict) Key/Value arguments. Values should be primitives.

        Returns:
            A URL encoded string like this: <url>?foo=bar&abc=xyz
        """

        # Remove keys from the arguments where the value is None
        args = dict((k, v) for k, v in args.iteritems() if v)

        # Convert all Bool values to lowercase strings
        for key, value in args.iteritems():
            if type(value) is bool:
                args[key] = str(value).lower()

        # Now generate the URL
        full_url = httputil.url_concat(url, args)
        self.log.debug('Generated URL: %s' % full_url)

        return full_url

    # TODO: Add a retry/backoff timer here. If the remote endpoint returns
    # garbled data (ie, maybe a 500 errror or something else thats not in
    # JSON format, we should back off and try again.
    @gen.coroutine
    def _fetch(self, url, post=None):
        """Executes a web request asynchronously and yields the body.

        Args:
            url: (Str) The full url path of the API call
            post: (Str) POST body data to submit (if any)
        """

        # Generate the full request URL and log out what we're doing...
        self.log.debug('Making HTTP request to %s with data: %s' % (url, post))

        # Create the http_request object
        http_client = self._get_http_client()
        http_request = httpclient.HTTPRequest(
            url=url,
            method=self._get_method(post),
            body=post,
            headers=self.headers,
            auth_username=None,
            auth_password=None,
            follow_redirects=True,
            max_redirects=10)

        # Execute the request and raise any exception. Exceptions are not
        # caught here because they are unique to the API endpoints, and thus
        # should be handled by the individual Actor that called this method.
        http_response = yield http_client.fetch(http_request)

        try:
            body = json.loads(http_response.body)
        except ValueError as e:
            raise exceptions.UnparseableResponseFromEndpoint(
                'Unable to parse response from remote API as JSON: %s' % e)

        # Receive a successful return
        raise gen.Return(body)
