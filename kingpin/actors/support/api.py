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
REST APIs. The majority of the work is in the creation of a _CONFIG dictionary
for the class. This dictionary dynamically configures the object at
instantiation time with the appropriate @gen.coroutine wrapped HTTP fetch
methods.

See the documentation in docs/DEVELOPMENT.md for more details on how to use
this package to create your own API client.
"""

import logging
import types
import urllib

from tornado import gen
from tornado import httpclient
from tornado import httputil
import simplejson as json

from kingpin import utils
from kingpin.actors import exceptions

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


def _retry(f):
    """Coroutine-compatible Retry Decorator.

    This decorator provides a simple retry mechanism that compares the
    exceptions it received against a configuration list (self._EXCEPTIONS),
    and then performs the action defined in that list. For example, an
    HTTPError with a '500' code might want to retry 3 times. On the
    otherhand, a 401/403 might want to throw an InvalidCredentials
    exception.
    """
    retries = 3
    delay = 0.25

    def wrapper(self, *args, **kwargs):
        i = 1
        while True:
            # Don't log out the first try as a 'Try' ... just do it
            if i > 0:
                log.debug('Try (%s/%s) of %s(%s, %s)' %
                          (i, retries, f, args, kwargs))

            # Attempt the method. Catch any exception listed in
            # self._EXCEPTIONS.
            try:
                ret = yield gen.coroutine(f)(self, *args, **kwargs)
                raise gen.Return(ret)
            except tuple(self._EXCEPTIONS.keys()) as e:
                log.error('Exception raised on try %s: %s' % (i, e))

                # If we've run out of retry attempts, raise the exception
                if i >= retries:
                    log.debug('Raising exception: %s' % e)
                    raise e

                # Gather the config for this exception-type from
                # self._EXCEPTIONS. Iterate through the data and see if we
                # have a matching exception string.
                exc_conf = self._EXCEPTIONS[type(e)].copy()

                # An empty string for the key is the default exception
                # It's optional, but can match before others match, so we
                # pop it before searching.
                default_exc = exc_conf.pop('', False)
                log.debug('Searching through %s' % exc_conf)
                matched_exc = [exc for key, exc in exc_conf.items()
                               if key in str(e)]

                log.debug('Matched exceptions: %s' % matched_exc)
                if matched_exc and matched_exc[0] is not None:
                    log.debug('Matched exc: %s' % matched_exc)
                    exception = matched_exc[0]
                    raise exception(str(e))
                elif matched_exc and matched_exc[0] is None:
                    log.debug('Exception is retryable!')
                    pass
                elif default_exc is not False:
                    raise default_exc(str(e))

                if default_exc is False:
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


def create_http_method(name, http_method):
    """Creates the get/put/delete/post coroutined-method for a resource.

    This method is called during the __init__ of a RestConsumer object. The
    method creates a custom method thats handles a GET, PUT, POST or DELETE
    through the Tornado HTTPClient class.

    Args:
        http_method: Name of the method (get, put, post, delete)

    Returns:
        A method appropriately configured and named.
    """

    @gen.coroutine
    def method(self, *args, **kwargs):
        # We don't support un-named args. Throw an exception.
        if args:
            raise exceptions.InvalidOptions('Must pass named-args (kwargs)')

        ret = yield self._client.fetch(
            url='%s%s' % (self._ENDPOINT, self._path),
            method=http_method.upper(),
            params=kwargs
        )
        raise gen.Return(ret)

    method.__name__ = http_method
    return method


def create_method(name, config):
    """Creates a RestConsumer object.

    Configures a fresh RestConsumer object with the supplied configuration
    bits. The configuration includes information about the name of the method
    being consumed and the configuration of that method (which HTTP methods it
    supports, etc).

    The final created method accepts any args (*args, **kwargs) and passes them
    on to the RestConsumer object being created. This allows for passing in
    unique resource identifiers (ie, the '%(res)' in
    '/v2/rooms/%(res)/history').

    Args:
        name: The name passed into the RestConsumer object
        config: The config passed into the RestConsumer object

    Returns:
        A method that returns a fresh RestConsumer object
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

    """An abstract object that self-defines its own API access methods.

    At init time, this object reads its `_CONFIG` and pre-defines all of the
    API access methods that have been described. It does not handle actual HTTP
    calls directly, but is passed in a `client` object (anything that
    subclasses the RestClient class) and leverages that for the actual web
    calls.
    """

    _CONFIG = {}
    _ENDPOINT = None

    def __init__(self, name=None, config=None, client=None, *args, **kwargs):
        """Initialize the RestConsumer object.

        The generic RestConsumer object (with no parameters passed in) looks at
        the self.__class__._CONFIG dictionary and dynamically generates access
        methods for the various API methods.

        The GET, PUT, POST and DELETE methods optionally listed in
        CONFIG['http_methods'] represent the possible types of HTTP methods
        that the CONFIG['path'] supports. For each one of these listed, a
        @coroutine wrapped get/put/post/delete() method will be created in the
        RestConsumer that knows how to make the HTTP request.

        For each item listed in CONFIG['attrs'], an access method is created
        that will dynamically create and return a new RestConsumer object thats
        configured for this endpoint. These methods are not asynchronous, but
        are non-blocking.

        Args:
            name: Name of the resource method (default: None)
            config: The dictionary object with the configuration for this API
                    endpoint call.
            client: <TBD>
            *args,**kwargs: <TBD>
        """
        # If these aren't passed in, then get them from the class definition
        name = name or self.__class__.__name__
        config = config or self._CONFIG

        # Get the basic options for this particular REST endpoint access object
        self._path = config.get('path', None)
        self._http_methods = config.get('http_methods', None)
        self._attrs = config.get('attrs', None)
        self._kwargs = kwargs

        # If no client was supplied, then we
        self._client = client or RestClient()

        # Ensure that any tokens that need filling-in in the self._path setting
        # are pulled from the **kwargs passed into this init. This is used on
        # API paths like Hipchats '/v2/room/%(res)/...' URLs.
        self._path = self._replace_path_tokens(self._path, kwargs)

        # Create all of the methods based on the self._http_methods and
        # self._attrs dict.
        self._create_methods()
        self._create_attrs()

        # Log some things
        log.debug('%s/%s initialized' %
                  (self.__class__.__name__, self._client))

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, self)

    def __str__(self):
        return str(self._path)

    def _replace_path_tokens(self, path, tokens):
        """Search and replace %xxx% with values from tokens.

        Used to replace any values of %xxx% with 'xxx' from tokens. Can replace
        one, or many fields at aonce.

        Args:
            path: String of the path
            tokens: A dictionary of tokens to search through.

        Returns:
            path: A modified string
        """
        if not path:
            return

        try:
            path = utils.populate_with_tokens(path, tokens)
        except LookupError as e:
            msg = 'Path (%s) error: %s' % (path, e)
            raise TypeError(msg)

        return path

    def _create_methods(self):
        """Create @gen.coroutine wrapped HTTP methods.

        Iterates through the methods described in self._methods and creates
        @gen.coroutine wrapped access methods that perform these actions.
        """
        if not self._http_methods:
            return

        for name in self._http_methods.keys():
            full_method_name = 'http_%s' % name
            method = create_http_method(full_method_name, name)
            setattr(self,
                    full_method_name,
                    types.MethodType(method, self, self.__class__))

    def _create_attrs(self):
        """Creates access methods to the attributes in self._attrs.

        Iterates through the attributes described in self._attrs and creates
        access methods that return RestConsumer objects for those attributes.
        """
        if not self._attrs:
            return

        for name in self._attrs.keys():
            method = create_method(name, self._attrs[name])
            setattr(self, name, types.MethodType(method, self, self.__class__))


class RestClient(object):

    """Very simple REST client for the RestConsumer. Implements a
    AsyncHTTPClient(), some convinience methods for URL escaping, and a single
    fetch() method that can handle GET/POST/PUT/DELETEs.

    This code is nearly identical to the kingpin.actors.base.BaseHTTPActor
    class, but is not actor-specific.

    Args:
        headers: Headers to pass in on every HTTP request
    """

    _EXCEPTIONS = {
        httpclient.HTTPError: {
            '401': exceptions.InvalidCredentials,
            '403': exceptions.InvalidCredentials,
            '500': None,
            '502': None,
            '503': None,
            '504': None,
            '': exceptions.RecoverableActorFailure,
        }
    }

    def __init__(self, client=None, headers=None):
        self._client = client or httpclient.AsyncHTTPClient()
        self.headers = headers

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
        full_url = httputil.url_concat(url, sorted(args.items()))
        log.debug('Generated URL: %s' % full_url)

        return full_url

    # TODO: Add a retry/backoff timer here. If the remote endpoint returns
    # garbled data (ie, maybe a 500 errror or something else thats not in
    # JSON format, we should back off and try again.
    @gen.coroutine
    @_retry
    def fetch(self, url, method, params={},
              auth_username=None, auth_password=None):
        """Executes a web request asynchronously and yields the body.

        Args:
            url: (Str) The full url path of the API call
            params: (Dict) Arguments (k/v pairs) to submit either as POST data
                    or URL argument options.
            method: (Str) GET/PUT/POST/DELETE
            auth_username: (str) HTTP auth username
            auth_password: (str) HTTP auth password
        """

        # Start with empty post data. If we're doing a PUT/POST, then just pass
        # args directly into the ch() method and let it take care of
        # things. If we're doing a GET/DELETE though, convert kwargs into a
        # modified URL string and pass that into the fetch() method.
        body = None
        if method in ('PUT', 'POST'):
            body = urllib.urlencode(params) or None
        elif method in ('GET', 'DELETE') and params:
            url = self._generate_escaped_url(url, params)

        # Generate the full request URL and log out what we're doing...
        log.debug('Making HTTP request to %s with data: %s' % (url, body))

        # Create the http_request object
        http_request = httpclient.HTTPRequest(
            url=url,
            method=method,
            body=body,
            headers=self.headers,
            auth_username=auth_username,
            auth_password=auth_password,
            follow_redirects=True,
            max_redirects=10)

        # Execute the request and raise any exception. Exceptions are not
        # caught here because they are unique to the API endpoints, and thus
        # should be handled by the individual Actor that called this method.
        log.debug('HTTP Reques): %s' % http_request.__dict__)
        http_response = yield self._client.fetch(http_request)
        log.debug('HTTP Response: %s' % http_response.body)

        try:
            body = json.loads(http_response.body)
        except ValueError:
            raise gen.Return(http_response.body)

        # Receive a successful return
        raise gen.Return(body)


class SimpleTokenRestClient(RestClient):

    """Simple RestClient that appends a 'token' to every web request for
    authentication. Used in most simple APIs where a token is provided to the
    end user.

    Args:
        tokens: (dict) A dict with the token name/value(s) to append to every
                we request.
    """

    def __init__(self, tokens, *args, **kwargs):
        super(SimpleTokenRestClient, self).__init__(*args, **kwargs)
        self._tokens = tokens

    @gen.coroutine
    def fetch(self, *args, **kwargs):
        if 'params' not in kwargs:
            kwargs['params'] = {}

        kwargs['params'].update(self._tokens)
        ret = yield super(SimpleTokenRestClient, self).fetch(*args, **kwargs)
        raise gen.Return(ret)
