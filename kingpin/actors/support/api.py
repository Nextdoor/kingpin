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
This package provides a quick way of creating custom API clients for JSON-based
REST APIs. The majority of the work is in the creation of a
:attr:`RestConsumer.CONFIG` dictionary for the class. This dictionary
dynamically configures the object at instantiation time with the appropriate
:func:`~tornado.gen.coroutine` wrapped HTTP fetch methods.

.. autoclass:: RestConsumer
   :members:
   :private-members:
.. autoclass:: RestClient
   :members:
   :private-members:
.. autoclass:: SimpleTokenRestClient
   :members:
   :inherited-members:
   :show-inheritance:
"""

import logging
import types
from urllib.parse import urlencode
import functools

from tornado import gen
from tornado import httpclient
from tornado import httputil
import simplejson as json

from kingpin.actors.support import utils
from kingpin.actors.support import exceptions

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


def retry(func=None, retries=3, delay=0.25):
    """Coroutine-compatible retry decorator.

    This decorator provides a simple retry mechanism that compares the
    exceptions it received against a configuration list stored in the
    calling-object(:attr:`RestClient.EXCEPTIONS`), and then performs the action
    defined in that list. For example, an :exc:`~tornado.httpclient.HTTPError`
    with a '500' code might want to retry 3 times. On the otherhand, a
    `401`/`403` might want to throw an
    :exc:`~tornado_rest_client.exceptions.InvalidCredentials` exception.

    Examples:

    >>> @gen.coroutine
    ... @retry
    ... def some_func(self):
    ...     yield ...

    >>> @gen.coroutine
    ... @retry(retries=5):
    ... def some_func(self):
    ...     yield ...
    """
    def decorate(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # Try #1!
            i = 1

            # Get a list of private kwargs to mask
            private_kwargs = getattr(self, '_private_kwargs', [])

            # For security purposes, create a patched kwargs string that
            # removes passwords from the arguments. This is never guaranteed to
            # work (an API could have 'foo' as their password field, and we
            # just won't know ...), but we make a best effort here.
            safe_kwargs = dict(kwargs)
            remove = [k for k in safe_kwargs if k in private_kwargs]
            for k in remove:
                safe_kwargs[k] = '****'

            while True:
                # Don't log out the first try as a 'Try' ... just do it
                if i > 1:
                    log.debug('Try (%s/%s) of %s(%s, %s)' %
                              (i, retries, func, args, safe_kwargs))

                # Attempt the method. Catch any exception listed in
                # self.EXCEPTIONS.

                try:
                    ret = yield gen.coroutine(func)(self, *args, **kwargs)
                    raise gen.Return(ret)
                except tuple(self.EXCEPTIONS.keys()) as e:
                    error = str(e)
                    if hasattr(e, 'message'):
                        error = e.message
                    log.warning('Exception raised on try %s: %s' % (i, error))

                    # If we've run out of retry attempts, raise the exception
                    if i >= retries:
                        log.debug('Raising exception: %s' % e)
                        raise e

                    # Gather the config for this exception-type from
                    # self.EXCEPTIONS. Iterate through the data and see if we
                    # have a matching exception string.
                    exc_conf = self.EXCEPTIONS[type(e)].copy()

                    # An empty string for the key is the default exception
                    # It's optional, but can match before others match, so we
                    # pop it before searching.
                    default_exc = exc_conf.pop('', False)
                    log.debug('Searching through %s' % exc_conf)
                    matched_exc = [exc for key, exc in exc_conf.items()
                                   if key in str(e)]

                    log.debug('Matched exceptions: %s' % matched_exc)
                    if matched_exc and matched_exc[0] is not None:
                        exception = matched_exc[0]
                        log.debug('Matched exception: %s' % exception)
                        raise exception(e)
                    elif matched_exc and matched_exc[0] is None:
                        log.debug('Exception is retryable!')
                        pass
                    elif default_exc is not False:
                        raise default_exc(str(e))
                    elif default_exc is False:
                        # Reaching this part means no exception was matched
                        # and no default was specified.
                        log.debug('No explicit behavior for this exception'
                                  ' found. Raising.')
                        raise e

                    # Must have been a retryable exception. Retry.
                    i = i + 1
                    log.debug('Retrying in %s...' % delay)
                    yield utils.tornado_sleep(delay)

                log.debug('Retrying..')
        return wrapper

    # http://stackoverflow.com/questions/3888158/
    # python-making-decorators-with-optional-arguments
    if func:
        return decorate(func)

    return decorate


def create_http_method(name, http_method):
    """Creates the *GET*/*PUT*/*DELETE*/*POST* function for a RestConsumer.

    This method is called by :func:`RestConsumer._create_http_methods` to
    create a method for the :class:`RestConsumer` object with the appropriate
    name and HTTP method (:func:`http_get`, :func:`http_put`,
    :func:`http_delete`, :func:`http_post`)

    :param str name: Full name of the function to create (ie, `http_get`)
    :param str http_method: Name of the method (ie, `get`)

    :return: A method appropriately configured and named.
    """

    @gen.coroutine
    def method(self, *args, **kwargs):
        # We don't support un-named args. Throw an exception.
        if args:
            raise exceptions.InvalidOptions('Must pass named-args (kwargs)')

        ret = yield self._client.fetch(
            url='%s%s' % (self.ENDPOINT, self._path),
            method=http_method.upper(),
            params=kwargs,
            auth_username=self.CONFIG.get('auth', {}).get('user'),
            auth_password=self.CONFIG.get('auth', {}).get('pass')
        )
        raise gen.Return(ret)

    method.__name__ = http_method
    return method


def create_consumer_method(name, config):
    """Creates a method that returns a configured RestConsumer object.

    RestConsumer objects themselves can have references to other RestConsumer
    objects. For example, the
    :class:`~tornado_rest_consumer.client.slack.Slack` object has no
    :func:`http_*` methods itself, but it does have methods like
    :func:`~tornadeo_rest_consumer.client.slack.Slack.auth_test` which return a
    fresh :class:`RestConsumer` object that points to the `/api/auth.test` API
    endpoint and provide :func:`http_post` as a function

    The method created here accepts any args (`*args, **kwargs`) and passes
    them on to the :class:`RestConsumer` object being created. This allows for
    passing in unique resource identifiers (ie, the `%res%` in
    `/v2/rooms/%res%/history`).

    :param str name: The name of the method to create (ie, `auth_test`)
    :param dict config: The dictionary of :attr:`~RestConsumer.CONFIG` data
      specific to the API endpoint that we are configuring (should include
      `path` and `http_methods` keys).

    :return: A method that returns a fresh RestConsumer object
    """

    def method(self, *args, **kwargs):
        # Merge the supplied kwargs to the method with any kwargs supplied to
        # the RestConsumer parent object. This ensures that tokens replaced in
        # the 'path' variables are passed all the way down the instantiation
        # chain.
        merged_kwargs = dict(self._kwargs.items() + kwargs.items())

        return self.__class__(
            name=name,
            config=self._attrs[name],
            client=self._client,
            *args, **merged_kwargs)

    method.__name__ = name
    return method


class RestConsumer(object):

    """Async REST API Consumer object.

    The generic RestConsumer object (with no parameters passed in) looks at
    the :attr:`CONFIG` dictionary and dynamically generates access methods
    for the various API methods.

    The *GET*, *PUT*, *POST* and *DELETE* methods optionally listed in
    `CONFIG['http_methods']` represent the possible types of HTTP methods
    that the `CONFIG['path']` supports. For each one of these listed, a
    :func:`~tornado.gen.coroutine` wrapped :func:`http_get`,
    :func:`http_put`, :func:`http_post`, or :func:`http_delete` method will
    be created.

    For each item listed in `CONFIG['attrs']`, an access method is created
    that creates and returns a new RestConsumer object that's configured for
    this endpoint. These methods are not asynchronous, but are non-blocking.

    :param str name: Name of the resource method (default: None)
    :param dict config: The dictionary object with the configuration for this
      API endpoint call.
    :param RestClient client: The `RestClient` compatible object used to
      actually fire off HTTP requests.
    :param dict kwargs: Any named arguments that should be passed along in the
      web request through the :func:`replace_path_tokens` method. This allows
      for string replacement in URL paths, like `/api/%resource_id%/terminate`
      to have the `%resource_id%` token replaced with something you've
      passed in here.
    """

    #: The URL of the API Endpoint.
    #: (for example: http://httpbin.org)
    ENDPOINT = None

    #: The configuration dictionary for the REST API. This dictionary
    #: consists of a root object that has three possible named keys: `path`,
    #: `http_methods` and `attrs`.
    #:
    #: * *path*: The API Endpoint that any of the HTTP methods should talk to.
    #: * *http_methods*: A dictionary of HTTP methods that are supported.
    #: * *attrs*: A dictionary of other methods to create that reference other
    #:   API URLs.
    #: * *new*: Set to True if you want to create an access property rather
    #:   an access method. Only works if your path has no token replacement in
    #:   it.
    #:
    #: This data can be nested as much as you'd like
    #:
    #: >>> CONFIG = {
    #: ...     'path': '/', 'http_methods': {'get': {}},
    #: ...     'new': True,
    #: ...     'attrs': {
    #: ...         'getter': {'path': '/get', 'htpt_methods': {'get': {}}},
    #: ...         'poster': {'path': '/post', 'htpt_methods': {'post': {}}},
    #: ...     }
    #: ... }:
    CONFIG = {}

    def __init__(self, name=None, config=None, client=None, *args, **kwargs):
        """Initializes the RestConsumer."""
        # If these aren't passed in, then get them from the class definition
        name = name or self.__class__.__name__
        config = config or self.CONFIG

        # Get the basic options for this particular REST endpoint access object
        self._path = config.get('path', None)
        self._http_methods = config.get('http_methods', None)
        self._attrs = config.get('attrs', None)
        self._kwargs = kwargs

        # If no client was supplied, then we use our default
        self._client = client or RestClient()

        # Ensure that any tokens that need filling-in in the self._path setting
        # are pulled from the **kwargs passed into this init. This is used on
        # API paths like Hipchats '/v2/room/%(res)/...' URLs.
        self._path = self.replace_path_tokens(self._path, kwargs)

        # Create all of the methods based on the self._http_methods and
        # self._attrs dict.
        self._create_http_methods()
        self._create_consumer_methods()

        # Log some things
        log.debug('%s/%s initialized' %
                  (self.__class__.__name__, self._client))

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, self)

    def __str__(self):
        return str(self._path)

    def replace_path_tokens(self, path, tokens):
        """Search and replace `%xxx%` with values from tokens.

        Used to replace any values of `%xxx%` with `'xxx`' from tokens. Can
        replace one, or many fields at aonce.

        :param str path: String of the path
        :param dict tokens: A dictionary of tokens to search through.
        :return: A modified string
        """
        if not path:
            return

        try:
            path = utils.populate_with_tokens(path, tokens)
        except LookupError as e:
            msg = 'Path (%s), tokens: (%s) error: %s' % (path, tokens, e)
            raise TypeError(msg)

        return path

    def _create_http_methods(self):
        """Create :func:`~tornado.gen.coroutine` wrapped HTTP methods.

        Iterates through the methods described in `self._http_methods` and
        creates :func:`~tornado.gen.coroutine` wrapped access methods that
        perform these actions.
        """
        if not self._http_methods:
            return

        for name in self._http_methods.keys():
            full_method_name = 'http_%s' % name
            method = create_http_method(full_method_name, name)
            setattr(self,
                    full_method_name,
                    types.MethodType(method, self))

    def _create_consumer_methods(self):
        """Creates access methods to the attributes in `self._attrs`.

        Iterates through the attributes described in `self._attrs` and creates
        access methods that return :class:`RestConsumer` objects for those
        attributes.
        """
        if not self._attrs:
            return

        for name in self._attrs.keys():
            method = create_consumer_method(name, self._attrs[name])

            if 'new' in self._attrs[name]:
                try:
                    setattr(self, name, method(self))
                except TypeError:
                    setattr(self, name, types.MethodType(method, self))
            else:
                setattr(self, name, types.MethodType(method, self))


class RestClient(object):

    """Simple Async REST client for the RestConsumer.

    Implements a :class:`~tornado.httpclient.AsyncHTTPClient`, some convinience
    methods for URL escaping, and a single :func:`~RestClient.fetch` method
    that can handle GET/POST/PUT/DELETEs.

    :param dict headers: Headers to pass in on every HTTP request
    """

    #: Dictionary describing the exception handling behavior for HTTP calls.
    #: The dictionary should look like this:
    #:
    #: >>> {
    #: ...     <exception type... aka httpclient.HTTPError>: {
    #: ...         `<string to match in exception.message>`: <raises exc>,
    #: ...         '<this string triggers a retry>': None,
    #: ...         '': <all other strings trigger this exception>
    #: ...     }
    #:
    EXCEPTIONS = {
        httpclient.HTTPError: {
            '401': exceptions.InvalidCredentials,
            '403': exceptions.InvalidCredentials,
            '500': None,
            '502': None,
            '503': None,
            '504': None,

            # Rrepresents a standard HTTP Timeout
            '599': None,

            '': exceptions.RecoverableFailure,
        }
    }

    # Combined Connect and Request Timeout settings. Note, None
    # is the default -- but actually times out after 20s (due to
    # a bug in Tornado). Use a very high number or 0 to indicate no
    # timeout.
    TIMEOUT = None

    # If the APi expects that you send a JSON body with data rather than
    # passing url arguments, set this to true.
    JSON_BODY = False

    def __init__(self, client=None, headers=None, timeout=TIMEOUT,
                 json=None, allow_nonstandard_methods=False):
        self._client = client or httpclient.AsyncHTTPClient()
        self._private_kwargs = ['auth_password']
        self.headers = headers
        self.timeout = timeout
        self.allow_nonstandard_methods = allow_nonstandard_methods
        self.json = json

        if ((self.json is True or self.JSON_BODY) and self.json is not False) \
           and not self.headers:
            self.headers = {
                'Content-Type': 'application/json'
            }

    def _generate_escaped_url(self, url, args):
        """Generates a fully escaped URL string.

        Sorts the arguments so that the returned string is predictable and in
        alphabetical order. Effectively wraps the
        :func:`tornado.httputil.url_concat` method and properly strips out
        `None` values, as well as lowercases `Bool` values.

        :param str url: The URL to append the arguments to
        :param dict args: Key/Value arguments. Values should be primitives.

        :return: URL encoded string like this: `<url>?foo=bar&abc=xyz`
        """

        # Remove keys from the arguments where the value is None
        args = dict((k, v) for k, v in args.iteritems() if v)

        # Convert all Bool values to lowercase strings
        for key, value in args.iteritems():
            if type(value) is bool:
                args[key] = str(value).lower()

        # Now generate the URL
        full_url = httputil.url_concat(url, sorted(args.items()))
        log.debug('Generated URL: %s' % full_url)

        return full_url

    @gen.coroutine
    @retry
    def fetch(self, url, method, params={},
              auth_username=None, auth_password=None, timeout=None):
        """Executes a web request asynchronously and yields the body.

        :param str url: The full url path of the API call
        :param dict params: Arguments (k/v pairs) to submit either as POST data
          or URL argument options.
        :param str method: GET/PUT/POST/DELETE
        :param str auth_username: HTTP auth username
        :param str auth_password: HTTP auth password
        :yields: String of the returned text from the web service.
        """

        # Start with empty post data. If we're doing a PUT/POST, then just pass
        # args directly into the ch() method and let it take care of
        # things. If we're doing a GET/DELETE though, convert kwargs into a
        # modified URL string and pass that into the fetch() method.
        if timeout is None:
            timeout = self.timeout
        body = None
        if method in ('PUT', 'POST'):
            if not ((self.json is True or self.JSON_BODY) and
                    self.json is not False):
                body = urlencode(params)
            else:
                body = json.dumps(params)
        elif method in ('GET', 'DELETE') and params:
            url = self._generate_escaped_url(url, params)

        # Generate the full request URL and log out what we're doing...
        log.debug('Making %s request to %s. Data: %s' % (method, url, body))

        # Create the http_request object
        http_request = httpclient.HTTPRequest(
            url=url,
            method=method,
            body=body,
            headers=self.headers,
            auth_username=auth_username,
            auth_password=auth_password,
            follow_redirects=True,
            request_timeout=timeout,
            connect_timeout=timeout,
            allow_nonstandard_methods=self.allow_nonstandard_methods,
            max_redirects=10)

        # Execute the request and raise any exception. Exceptions are not
        # caught here because they are unique to the API endpoints, and thus
        # should be handled by the individual callers of this method.
        log.debug('HTTP Request: %s' % http_request)
        try:
            http_response = yield self._client.fetch(http_request)
        except httpclient.HTTPError as e:
            log.critical('Request for %s failed: %s' % (url, e))
            raise
        log.debug('HTTP Response: %s' % http_response.body)

        try:
            body = json.loads(http_response.body)
        except ValueError:
            raise gen.Return(http_response.body)

        # Receive a successful return
        raise gen.Return(body)


class SimpleTokenRestClient(RestClient):

    """Simple RestClient with a token for HTTP authentication.

    Used in most simple APIs where a token is provided to the end user.

    :param dict tokens: A dict with the token name/value(s) to append to every
      web request.
    """

    def __init__(self, tokens, *args, **kwargs):
        super(SimpleTokenRestClient, self).__init__(*args, **kwargs)
        self._tokens = tokens
        for key in tokens.keys():
            self._private_kwargs.append(key)

    @gen.coroutine
    def fetch(self, *args, **kwargs):
        if 'params' not in kwargs:
            kwargs['params'] = {}

        kwargs['params'].update(self._tokens)
        ret = yield super(SimpleTokenRestClient, self).fetch(*args, **kwargs)
        raise gen.Return(ret)
