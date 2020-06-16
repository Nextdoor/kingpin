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
:mod:`kingpin.actors.base`
^^^^^^^^^^^^^^^^^^^^^^^^^^

Base Actor object class

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

import inspect
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
from kingpin.actors.utils import timer
from kingpin.constants import REQUIRED, STATE

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


# If super-debug logging is enabled, then we turn on the URLLIB3 HTTP
# request logging. This is extremely verbose and insecure, but useful
# for troubleshooting. URLLIB3 is used by several actors (aws, rightscale),
# so we do this setup here in the base actor class.
if os.getenv('URLLIB_DEBUG', None):
    utils.super_httplib_debug_logging()

# Allow the user to override the default_timeout for all actors by setting an
# environment variable
DEFAULT_TIMEOUT = os.getenv('DEFAULT_TIMEOUT', 3600)


class LogAdapter(logging.LoggerAdapter):

    """Simple Actor Logging Adapter.

    Provides a common logging format for actors that uses the actors
    description and dry parameter as a prefix to the supplied log message.
    """

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

    # Default description format
    desc = "{actor}"

    # Set the default timeout for the gen.with_timeout() wrapper that we use to
    # monitor and control the length of execution of a single Actor.
    default_timeout = DEFAULT_TIMEOUT

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

    # Controls whether to remove escape characters from tokens that have been
    # escaped.
    remove_escape_sequence = True

    def __init__(self, desc=None, options={}, dry=False, warn_on_failure=False,
                 condition=True, init_context={}, init_tokens={},
                 timeout=None):
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
            init_tokens: (Dict) Key/Value pairs passed into the actor that can
            be used for token replacement. Typically this is os.environ() plus
            some custom tokens. Set generally by the misc.Macro actor.
            timeout: (Str/Int/Float) Timeout in seconds for the actor.
        """
        self._type = '%s.%s' % (self.__module__, self.__class__.__name__)
        self._options = options
        self._desc = desc
        self._dry = dry
        self._warn_on_failure = warn_on_failure
        self._condition = condition
        self._init_context = init_context
        self._init_tokens = init_tokens

        self._timeout = timeout
        if timeout is None:
            self._timeout = self.default_timeout

        # strict about this -- but in the future, when we have a
        # runtime_context object, we may loosen this restriction).
        self._fill_in_contexts(
            context=self._init_context,
            strict=self.strict_init_context,
            remove_escape_sequence=self.remove_escape_sequence)

        self._setup_log()
        self._setup_defaults()
        self._validate_options()  # Relies on _setup_log() above

        # Fill in any options with the supplied initialization context. Be
        self.log.debug('Initialized (warn_on_failure=%s, '
                       'strict_init_context=%s,'
                       'remove_escape_sequence=%s)' %
                       (warn_on_failure, self.strict_init_context,
                        self.remove_escape_sequence))

    def __repr__(self):
        """Returns a nice name/description of the actor.

        Either the user has supplied a custom desc parameter to the actor,
        giving it a useful description for them. On the other hand, if an actor
        defines a custom ActorClass.desc field, that field is interpreted by
        this method an any variables that can be swapped in dynamically are.

        For example, if misc.Sleep.desc is 'Sleeping {sleep}s', this method
        will fill in the value of the option 'sleep' into the string, and then
        use that for the representation of the object.
        """
        if self._desc:
            return self._desc

        return self.__class__.desc.format(actor=self._type, **self._options)

    def _setup_log(self):
        """Create a customized logging object based on the LogAdapter."""
        name = '%s.%s' % (self.__module__, self.__class__.__name__)
        logger = logging.getLogger(name)
        dry_str = 'DRY: ' if self._dry else ''

        self.log = LogAdapter(logger, {'desc': self, 'dry': dry_str})

    def _setup_defaults(self):
        """Populate options with defaults if they aren't set."""

        for option, definition in list(self.all_options.items()):
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
                    for (opt_name, definition) in
                    list(self.all_options.items())
                    if definition[1] is REQUIRED]

        self.log.debug('Checking for required options: %s' % required)
        option_errors = []
        option_warnings = []
        for opt in required:
            if opt not in self._options:
                description = self.all_options[opt][2]
                option_errors.append('Option "%s" is required: %s' % (
                                     opt, description))

        for opt, value in list(self._options.items()):
            if opt not in self.all_options:
                option_warnings.append('Option "%s" is not expected by %s.' % (
                    opt, self.__class__.__name__))
                continue

            expected_type = self.all_options[opt][0]

            # Unicode is not a `str` but it is a `basestring`
            # Cast the passed value explicitly as a string
            if isinstance(value, str):
                value = str(value)

            # If the expected_type has an attribute 'valid', then verify that
            # the option passed in is one of those valid options.
            if hasattr(expected_type, 'validate'):
                try:
                    expected_type.validate(value)
                    continue
                except exceptions.InvalidOptions as e:
                    option_errors.append(e)

            # If the option type is Bool, try to convert the strings True/False
            # into booleans. If this doesn't work, siletly move on and let the
            # failure get caught below.
            if expected_type is bool:
                try:
                    value = self.str2bool(value, strict=True)
                    self._options[opt] = value
                except exceptions.InvalidOptions as e:
                    self.log.warning(e)

            if not (value is None or isinstance(value, expected_type)):
                message = 'Option "%s" has to be %s and is %s.' % (
                    opt, expected_type, type(value))
                option_errors.append(message)

        for w in option_warnings:
            self.log.warning(w)

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

    @gen.coroutine
    def timeout(self, f, *args, **kwargs):
        """Wraps a Coroutine method in a timeout.

        Used to wrap the self.execute() method in a timeout that will raise an
        ActorTimedOut exception if an actor takes too long to execute.

        *Note, Tornado 4+ does not allow you to actually kill a task on the
        IOLoop.*  This means that all we are doing here is notifying the caller
        (through the raised exception) that a problem has happened.

        Fairly simple Actors should actually 'stop executing' when this
        exception is raised. Complex actors with very unique behaviors though
        (like the rightsacle.server_array.Execute actor) have the ability to
        continue to execute in the background until the Kingpin application
        quits. It is not the job of this method to try to kill these actors,
        but just to let the user know that a failure has happened.
        """

        # Get our timeout setting, or fallback to the default
        self.log.debug('%s.%s() deadline: %s(s)' %
                       (self._type, f.__name__, self._timeout))

        # Get our Future object but don't yield on it yet, This starts the
        # execution, but allows us to wrap it below with the
        # 'gen.with_timeout' function.
        fut = f(*args, **kwargs)

        # If no timeout is set (none, or 0), then we just yield the Future and
        # return its results.
        if not self._timeout:
            ret = yield fut
            raise gen.Return(ret)

        # Generate a timestamp in the future at which point we will raise
        # an alarm if the actor is still executing
        deadline = time.time() + float(self._timeout)

        # Now we yield on the gen_with_timeout function
        try:
            ret = yield gen.with_timeout(
                deadline, fut, quiet_exceptions=(exceptions.ActorTimedOut))
        except gen.TimeoutError:
            msg = ('%s.%s() execution exceeded deadline: %ss' %
                   (self._type, f.__name__, self._timeout))
            self.log.error(msg)
            raise exceptions.ActorTimedOut(msg)

        raise gen.Return(ret)

    def str2bool(self, v, strict=False):
        """Returns a Boolean from a variety of inputs.

        args:
            value: String/Bool
            strict: Whether or not to _only_ convert the known words into
            booleans, or whether to allow "any" word to be considered True
            other than the known False words.

        returns:
            A boolean
        """
        false = ('no', 'false', 'f', '0')
        true = ('yes', 'true', 't', '1')

        string = str(v).lower()

        if strict:
            if string not in true and string not in false:
                raise exceptions.InvalidOptions(
                    'Expected [%s, %s] but got: %s' %
                    (true, false, string))

        return string not in false

    def _check_condition(self):
        """Check if specified condition allows this actor to run.

        Evaluate self._condition to figure out if this actor should run.
        The only exception to simply casting this variable to bool is if
        the value of self._condition is a string "False" or string "0".
        """

        check = self.str2bool(self._condition)
        self.log.debug('Condition %s evaluates to %s' % (
            self._condition, check))
        return check

    def _fill_in_contexts(self, context={}, strict=True,
                          remove_escape_sequence=True):
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
        # Inject contexts into Description
        try:
            self._desc = utils.populate_with_tokens(
                str(self),
                context,
                self.left_context_separator,
                self.right_context_separator,
                strict=strict,
                remove_escape_sequence=remove_escape_sequence)
        except LookupError as e:
            msg = 'Context for description failed: %s' % e
            raise exceptions.InvalidOptions(msg)

        # Inject contexts into condition
        try:
            self._condition = utils.populate_with_tokens(
                str(self._condition),
                context,
                self.left_context_separator,
                self.right_context_separator,
                strict=strict,
                remove_escape_sequence=remove_escape_sequence)
        except LookupError as e:
            msg = 'Context for condition failed: %s' % e
            raise exceptions.InvalidOptions(msg)

        # Convert our self._options dict into a string for fast parsing
        options_string = json.dumps(self._options)

        # Generate a new string with the values parsed out. At this point, if
        # any value is un-matched, an exception is raised and execution fails.
        # This stops execution during a dry run, before any live changes are
        # made.
        try:
            new_options_string = utils.populate_with_tokens(
                options_string,
                context,
                self.left_context_separator,
                self.right_context_separator,
                strict=strict,
                escape_sequence='\\\\',
                remove_escape_sequence=remove_escape_sequence)
        except LookupError as e:
            msg = 'Context for options failed: %s' % e
            raise exceptions.InvalidOptions(msg)

        # Finally, convert the string back into a dict and store it.
        self._options = json.loads(new_options_string)

    def get_orgchart(self, parent=''):
        """Construct organizational chart describing this actor.

        Return a list of actors handled by this actor. Most actors will return
        a list of just one object. Grouping actors will return a list of all
        actors that are called.

        orgchart object:
          id: unique string identifying this actor's instance.
          class: kingpin class name
          desc: actor description
          parent_id: organizational relationship. Same as `id` above.
        """

        return [{
            'id': str(id(self)),
            'desc': self._desc,
            'class': self.__class__.__name__,
            # 'options': self._options,  # May include tokens & ENV vars
            'parent_id': parent,
        }]

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
            result = yield self.timeout(self._execute)
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


class EnsurableBaseActor(BaseActor):

    """Base Class for Actors that "ensure" the state of a resource.

    Many of our actors have a goal of ensuring that a particular resource is in
    a given state. This leads to a ton of boiler plate code to "get" the state
    of something, "compare" that to the desired state, and then maybe "set" the
    state.

    This actor provides a framework allowing the user to simply write the
    getters and setters (and optionally compare), and lets the rest of the
    actor handle the order of operations.

    **Required Methods:**

      :`_set_state`: Creates or destroys the resource depending on
                      the 'state' parameter that was passed in.

                      *Note: The 'state' parameter is automatically added to
                      the options. You do not need to define it.*
      :`_get_state`: Gets the current state of the resource.
      :`_set_[option]`: A 'setter' for each option name passed in.
      :`_get_[option]`: A 'getter' for each option name passed in.

    **Optional Methods:**

      :`_precache`: Called before any setters/getters are triggered. Used
                       to optionally populate a cache of data to make the
                       getters faster. For example, if you can make one API
                       call to get all of the data about a resource, then
                       store that data locally for fast access.

      :`_compare_[option]`: Optionally you can write your own comparison
                               method if you're not doing a pure string
                               comparison between the source and destination.

    **Examples**

    .. code-block:: python

        class MyClass(base.EnsurableBaseActor):

            all_options = {
                'name': (str, REQUIRED, 'Name of thing'),
                'description': (str, None, 'Description of thing')
            }

            unmanaged_options = ['name']

            @gen.coroutine
            def _set_state(self):
                if self.option('state') == 'absent':
                    yield self.conn.delete_resource(
                        name=self.option('name'))
                else:
                    yield self.conn.create_resource(
                        name=self.option('name'),
                        desc=self.option('description'))

            @gen.coroutine
            def _set_description(self):
                yield self.conn.set_desc_of_resource(
                    name=self.option('name'),
                    desc=self.option('description'))

            @gen.coroutine
            def _get_description(self):
                yield self.conn.get_desc_of_resource(
                    name=self.option('name'))
    """

    # A list of option names that are _not_ automatically managed. These are
    # useful if you have special behaviors like 'commit' on change, or if you
    # have parameters that are unmutable ('name').
    unmanaged_options = []

    def __init__(self, *args, **kwargs):
        # The 'state' parameter is a given, so make sure its set,
        self.all_options['state'] = (
            STATE, 'present', 'Desired state: present or absent')

        # Now go ahead and validate all of the user inputs the normal way
        super(EnsurableBaseActor, self).__init__(*args, **kwargs)

        # Generate a list of options that will be ensured ...
        self._ensurable_options = list(self.all_options.keys())
        for option in self.unmanaged_options:
            self._ensurable_options.remove(option)

        # Finally, do a class validation... make sure that we have actual
        # getter/setter methods for each of the options. This populates dicts
        # that provide references to the actual methods for execution later.
        self._gather_methods()

    def _gather_methods(self):
        """Generates pointers to the Getter and Setter methods.

        Walks through the list of options in self.all_options and discovers the
        pointers to the getter/setter methods. If any are missing, throws an
        exception quickly.
        """
        self.setters = {}
        self.getters = {}
        self.comparers = {}
        for option in self._ensurable_options:
            setter = '_set_%s' % option
            getter = '_get_%s' % option
            comparer = '_compare_%s' % option

            if not self._is_method(getter) or not self._is_method(setter):
                raise exceptions.UnrecoverableActorFailure(
                    'Invalid Actor Code Detected in %s: '
                    'Unable to find required methods: %s, %s'
                    % (self.__class__.__name__, setter, getter))

            if not self._is_method(comparer):
                @gen.coroutine
                def _comparer(option=option):
                    existing = yield self.getters[option]()
                    new = self.option(option)
                    raise gen.Return(existing == new)
                setattr(self, comparer, _comparer)
                # self.log.debug('Creating dynamic method %s' % comparer)

            self.setters[option] = getattr(self, setter)
            self.getters[option] = getattr(self, getter)
            self.comparers[option] = getattr(self, comparer)

    def _is_method(self, name):
        return hasattr(self, name) and inspect.ismethod(getattr(self, name))

    @gen.coroutine
    def _precache(self):
        """Override this method to pre-cache data in your actor.

        This method can be overridden to go off and pre-fetch data for your
        actors _set and _get methods. This helps if you can execute a single
        API call that gets most of the data you need, before any of the actual
        get/set operations take place.
        """
        raise gen.Return()

    @gen.coroutine
    def _get_state(self):
        raise NotImplementedError('_get_state is required for Ensurable')

    @gen.coroutine
    def _set_state(self):
        raise NotImplementedError('_set_state is required for Ensurable')

    @gen.coroutine
    def _ensure(self, option):
        """Compares the desired state with the actual state of a resource.

        Uses the getter for a resource option to determine its current state,
        and then compares it with the desired state. Generally does a simple
        string comparison of the states, but user can optionally define their
        own comparison mechanism as well.

        If the states do not match, then the setter method is called.
        """
        equals = yield self.comparers[option]()

        if equals:
            self.log.debug('Option "%s" matches' % option)
            raise gen.Return()

        self.log.debug('Option "%s" DOES NOT match, calling setter' % option)
        yield self.setters[option]()

    @gen.coroutine
    def _execute(self):
        """A pretty simple execution pipeline for the actor.

        Note: An OrderedDict can be used instead of a plain dict when order
        actually matters for the option setting.
        """
        yield self._precache()

        yield self._ensure('state')

        if self.option('state') == 'absent':
            raise gen.Return()

        for option in self._ensurable_options:
            # We've already managed state .. so make sure we skip the state
            # option and only manage the others.
            if option != 'state':
                yield self._ensure(option)


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
        args = dict((k, v) for k, v in args.items() if v)

        # Convert all Bool values to lowercase strings
        for key, value in args.items():
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
