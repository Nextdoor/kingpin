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
import sys
import time

from tornado import gen
from tornado import httpclient
from tornado import httputil

from kingpin import utils
from kingpin.actors import exceptions
from kingpin.constants import REQUIRED

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

    # {
    #     'option_name': (type, default, "Long description of the option"),
    # }
    #
    # If `default` is REQUIRED then the option requires user specified input
    #
    # Example:
    # {
    #    'room': (str, REQUIRED, 'Hipchat room to notify'),
    #    'from': (str, 'Kingpin', 'User that sends the message')
    # }
    all_options = {}

    # Context separators. These define the left-and-right identifiers of a
    # 'contextual token' in the actor. By default this is { and }, so a
    # contextual token looks like '{KEY}'.
    left_context_separator = '{'
    right_context_separator = '}'

    # Ensure that at __init__ time, if the self._options dict is not completely
    # filled in properly (meaning there are no left-over {KEY}'s), we throw an
    # exception. This will change in the future when we have some concept of a
    # second 'global runtime context object'.
    strict_init_context = True

    def __init__(self, desc, options, dry=False, warn_on_failure=False,
                 condition=True, init_context={}):
        """Initializes the Actor.

        Args:
            desc: (Str) description of the action being executed.
            options: (Dict) Key/Value pairs that have the options
                     for this action. Values should be primitives.
            dry: (Bool) or not this Actor will actually make changes.
            warn_on_failure: (Bool) Whether this actor ignores its return
                             value and always succeeds (but warns).
            condition: (Bool) Whether to run this actor.
            init_context: (Dict) Key/Value pairs used at instantiation
                time to replace {KEY} strings in the actor definition.
                This is usually driven by the group.Sync/Async actors.
        """
        self._type = '%s.%s' % (self.__module__, self.__class__.__name__)
        self._desc = desc
        self._options = options
        self._dry = dry
        self._warn_on_failure = warn_on_failure
        self._condition = condition
        self._init_context = init_context

        # strict about this -- but in the future, when we have a
        # runtime_context object, we may loosen this restriction).
        self._fill_in_contexts(context=self._init_context,
                               strict=self.strict_init_context)

        self._setup_log()
        self._setup_defaults()
        self._validate_options()  # Relies on _setup_log() above

        # Fill in any options with the supplied initialization context. Be
        self.log.debug('Initialized (warn_on_failure=%s, '
                       'strict_init_context=%s)' %
                       (warn_on_failure, self.strict_init_context))

    def _setup_log(self):
        """Create a customized logging object based on the LogAdapter."""
        name = '%s.%s' % (self.__module__, self.__class__.__name__)
        logger = logging.getLogger(name)
        dry_str = 'DRY: ' if self._dry else ''

        self.log = LogAdapter(logger, {'desc': self._desc, 'dry': dry_str})

    def _setup_defaults(self):
        """Populate options with defaults if they aren't set."""

        for option, definition in self.all_options.items():
            if option not in self._options:
                default = definition[1]
                if default is not REQUIRED:
                    self._options.update({option: default})

    def _validate_options(self):
        """Validate that all the required options were passed in.

        Args:
            options: A dictionary of options.

        Raises:
            exceptions.InvalidOptions
        """

        # Loop through all_options, and find the required ones
        required = [opt_name
                    for (opt_name, definition) in self.all_options.items()
                    if definition[1] is REQUIRED]

        self.log.debug('Checking for required options: %s' % required)
        option_errors = []
        for opt in required:
            if opt not in self._options:
                description = self.all_options[opt][2]
                option_errors.append('Option "%s" is required: %s' % (
                                     opt, description))

        for opt, value in self._options.items():
            if opt not in self.all_options:
                option_errors.append('Option "%s" is not expected.' % opt)
                continue

            expected_type = self.all_options[opt][0]

            # Unicode is not a `str` but it is a `basestring`
            # Cast the passed value explicitly as a string
            if isinstance(value, basestring):
                value = str(value)

            if not (value is None or isinstance(value, expected_type)):
                message = 'Option "%s" has to be %s and is %s.' % (
                    opt, expected_type, type(value))
                option_errors.append(message)

        if option_errors:
            for e in option_errors:
                self.log.critical(e)
            raise exceptions.InvalidOptions(
                'Found %s issue(s) with passed options.' % len(option_errors))

    def option(self, name):
        """Return the value for a given Actor option."""

        return self._options.get(name)

    def readfile(self, path):
        """Return file contents as a string.

        Raises:
            InvalidOptions if file is not found, or readable.
        """

        try:
            with open(path) as f:
                contents = f.read()
        except IOError as e:
            raise exceptions.InvalidOptions(e)

        return contents

    def timer(f):
        """Coroutine-compatible function timer.

        Records statistics about how long a given function took, and logs them
        out in debug statements. Used primarily for tracking Actor execute()
        methods, but can be used elsewhere as well.

        Example usage:
            >>> @gen.coroutine
            ... @timer()
            ... def execute(self):
            ...     raise gen.Return()
        """

        def _wrap_in_timer(self, *args, **kwargs):
            # Log the start time
            start_time = time.time()

            # Begin the execution
            ret = yield gen.coroutine(f)(self, *args, **kwargs)

            # Log the finished execution time
            exec_time = "%.2f" % (time.time() - start_time)
            self.log.debug('%s.%s() execution time: %ss' %
                           (self._type, f.__name__, exec_time))

            raise gen.Return(ret)
        return _wrap_in_timer

    def _check_condition(self):
        """Check if specified condition allows this actor to run.

        Evaluate self._condition to figure out if this actor should run.
        The only exception to simply casting this variable to bool is if
        the value of self._condition is a string "False" or string "0".
        """

        try:  # Treat as string
            value = self._condition.lower()
            check = (value not in ('false', '0'))
        except AttributeError:  # Not a string
            value = self._condition
            check = bool(value)

        return check

    def _fill_in_contexts(self, context={}, strict=True):
        """Parses self._options and updates it with the supplied context.

        Parses the objects self._options dict (by converting it into a JSON
        string, substituting, and then turning it back into a dict) and the
        self._desc string and replaces any {KEY}s with the valoues from the
        context dict that was supplied.

        Args:
            strict: bool whether or not to allow missing context keys to be
                    skipped over.

        Raises:
            exceptions.InvalidOptions
        """
        try:
            self._desc = utils.populate_with_tokens(
                self._desc,
                context,
                self.left_context_separator,
                self.right_context_separator,
                strict=strict)
        except LookupError as e:
            msg = 'Context for description failed: %s' % e
            raise exceptions.InvalidOptions(msg)

        # Convert our self._options dict into a string for fast parsing
        options_string = json.dumps(self._options)

        # Generate a new string with the values parsed out. At this point, if
        # any value is un-matched, an exception is raised and execution fails.
        # This stops execution during a DRY run, before any live changes are
        # made.
        try:
            new_options_string = utils.populate_with_tokens(
                options_string,
                context,
                self.left_context_separator,
                self.right_context_separator,
                strict=strict)
        except LookupError as e:
            msg = 'Context for options failed: %s' % e
            raise exceptions.InvalidOptions(msg)

        # Finally, convert the string back into a dict and store it.
        self._options = json.loads(new_options_string)

    @gen.coroutine
    @timer
    def execute(self):
        """Executes an actor and yields the results when its finished.

        Calls an actors private _execute() method and either returns the result
        (through gen.Return) or handles any exceptions that are raised.

        RecoverableActorFailure exceptions are potentially swallowed up (and
        warned) if the self._warn_on_failure flag is set. Otherwise, they're
        logged and re-raised. All other ActorException exceptions are caught,
        logged and re-raised.

        We have a generic catch-all exception handling block as well, because
        third party Actor classes may or may not catch all appropriate
        exceptions. This block is mainly here to prevent the entire app from
        failing due to a poorly written Actor.

        Raises:
            gen.Return(result)
        """
        self.log.debug('Beginning')

        # Any exception thats raised by an actors _execute() method will
        # automatically cause actor failure and we return right away.
        result = None

        if not self._check_condition():
            self.log.warning('Skipping execution. Condition: %s' %
                             self._condition)
            raise gen.Return()

        try:
            result = yield self._execute()
        except exceptions.ActorException as e:
            # If exception is not RecoverableActorFailure
            # or if warn_on_failure is not set, then escalate.
            recover = isinstance(e, exceptions.RecoverableActorFailure)
            if not recover or not self._warn_on_failure:
                self.log.critical(e)
                raise

            # Otherwise - flag this failure as a warning, and continue
            self.log.warning(e)
            self.log.warning(
                'Continuing execution even though a failure was '
                'detected (warn_on_failure=%s)' % self._warn_on_failure)
        except Exception as e:
            # We don't like general exception catch clauses like this, but
            # because actors can be written by third parties and automatically
            # imported, its impossible for us to catch every exception
            # possible. This is a failsafe thats meant to throw a strong
            # warning.
            log.critical('Unexpected exception caught! '
                         'Please contact the author (%s) and provide them '
                         'with this stacktrace' %
                         sys.modules[self.__module__].__author__)
            self.log.exception(e)
            raise exceptions.ActorException(e)
        else:
            self.log.debug('Finished successfully, return value: %s' % result)

        # If we got here, we're exiting the actor cleanly and moving on.
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
        full_url = httputil.url_concat(url, sorted(args.items()))
        self.log.debug('Generated URL: %s' % full_url)

        return full_url

    # TODO: Add a retry/backoff timer here. If the remote endpoint returns
    # garbled data (ie, maybe a 500 errror or something else thats not in
    # JSON format, we should back off and try again.
    @gen.coroutine
    def _fetch(self, url, post=None, auth_username=None, auth_password=None):
        """Executes a web request asynchronously and yields the body.

        Args:
            url: (Str) The full url path of the API call
            post: (Str) POST body data to submit (if any)
            auth_username: (str) HTTP auth username
            auth_password: (str) HTTP auth password
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
            auth_username=auth_username,
            auth_password=auth_password,
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
