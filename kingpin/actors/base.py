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

import asyncio
import base64
import functools
import inspect
import json
import logging
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from kingpin import utils
from kingpin.actors import exceptions
from kingpin.actors.utils import timer
from kingpin.constants import REQUIRED, STATE

log = logging.getLogger(__name__)

__author__ = "Matt Wise <matt@nextdoor.com>"


# If super-debug logging is enabled, then we turn on the URLLIB3 HTTP
# request logging. This is extremely verbose and insecure, but useful
# for troubleshooting. URLLIB3 is used by several actors (aws, rightscale),
# so we do this setup here in the base actor class.
if os.getenv("URLLIB_DEBUG", None):
    utils.super_httplib_debug_logging()

# Allow the user to override the default_timeout for all actors by setting an
# environment variable
DEFAULT_TIMEOUT = os.getenv("DEFAULT_TIMEOUT", 3600)


class LogAdapter(logging.LoggerAdapter):
    """Simple Actor Logging Adapter.

    Provides a common logging format for actors that uses the actors
    description and dry parameter as a prefix to the supplied log message.
    """

    def process(self, msg, kwargs):
        return (f"[{self.extra['dry']}{self.extra['desc']}] {msg}", kwargs)


class BaseActor:
    """Abstract base class for Actor objects."""

    # {
    #     'option_name': (type, default, "Long description of the option"),
    # }
    #
    # If `default` is REQUIRED then the option requires user specified input
    #
    # Example:
    # {
    #    'name': (str, REQUIRED, 'Name of the resource'),
    #    'timeout': (int, 300, 'Timeout in seconds')
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
    left_context_separator = "{"
    right_context_separator = "}"

    # Ensure that at __init__ time, if the self._options dict is not completely
    # filled in properly (meaning there are no left-over {KEY}'s), we throw an
    # exception. This will change in the future when we have some concept of a
    # second 'global runtime context object'.
    strict_init_context = True

    # Controls whether to remove escape characters from tokens that have been
    # escaped.
    remove_escape_sequence = True

    def __init__(
        self,
        desc=None,
        options={},
        dry=False,
        warn_on_failure=False,
        condition=True,
        init_context={},
        init_tokens={},
        timeout=None,
    ):
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
        self._type = f"{self.__module__}.{self.__class__.__name__}"
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
            remove_escape_sequence=self.remove_escape_sequence,
        )

        self._setup_log()
        self._setup_defaults()
        self._validate_options()  # Relies on _setup_log() above

        # Fill in any options with the supplied initialization context. Be
        self.log.debug(
            f"Initialized (warn_on_failure={warn_on_failure}, "
            f"strict_init_context={self.strict_init_context},"
            f"remove_escape_sequence={self.remove_escape_sequence})"
        )

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
        name = f"{self.__module__}.{self.__class__.__name__}"
        logger = logging.getLogger(name)
        dry_str = "DRY: " if self._dry else ""

        self.log = LogAdapter(logger, {"desc": self, "dry": dry_str})

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
        required = [
            opt_name
            for (opt_name, definition) in self.all_options.items()
            if definition[1] is REQUIRED
        ]

        self.log.debug(f"Checking for required options: {required}")
        option_errors = []
        option_warnings = []
        for opt in required:
            if opt not in self._options:
                description = self.all_options[opt][2]
                option_errors.append(f'Option "{opt}" is required: {description}')

        for opt, value in self._options.items():
            if opt not in self.all_options:
                option_warnings.append(
                    f'Option "{opt}" is not expected by {self.__class__.__name__}.'
                )
                continue

            expected_type = self.all_options[opt][0]

            if isinstance(value, str):
                value = str(value)

            # If the expected_type has an attribute 'valid', then verify that
            # the option passed in is one of those valid options.
            if hasattr(expected_type, "validate"):
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
                    value = utils.str2bool(value, strict=True)
                    self._options[opt] = value
                except ValueError as e:
                    self.log.warning(exceptions.InvalidOptions(e.args))

            if not (value is None or isinstance(value, expected_type)):
                message = (
                    f'Option "{opt}" has to be {expected_type} and is {type(value)}.'
                )
                option_errors.append(message)

        for w in option_warnings:
            self.log.warning(w)

        if option_errors:
            for e in option_errors:
                self.log.critical(e)
            raise exceptions.InvalidOptions(
                f"Found {len(option_errors)} issue(s) with passed options."
            )

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
        except OSError as e:
            raise exceptions.InvalidOptions(e) from e

        return contents

    async def timeout(self, f, *args, **kwargs):
        """Wraps a Coroutine method in a timeout.

        Used to wrap the self.execute() method in a timeout that will raise an
        ActorTimedOut exception if an actor takes too long to execute.

        .. note::

            This method intentionally does NOT cancel the underlying task on
            timeout. The coroutine continues running in the background — we
            only notify the caller (via ActorTimedOut) that the deadline was
            exceeded. This preserves the original gen.with_timeout() contract
            and is important for long-running actors (e.g. CloudFormation
            stack operations) that should be allowed to finish even after the
            caller has moved on. asyncio.shield() prevents asyncio.wait_for()
            from cancelling the inner future.
        """

        # Get our timeout setting, or fallback to the default
        self.log.debug(f"{self._type}.{f.__name__}() deadline: {self._timeout}(s)")

        fut = f(*args, **kwargs)

        # If no timeout is set (none, or 0), just await directly.
        if not self._timeout:
            ret = await fut
            return ret

        try:
            ret = await asyncio.wait_for(
                asyncio.shield(fut), timeout=float(self._timeout)
            )
        except TimeoutError:
            msg = f"{self._type}.{f.__name__}() execution exceeded deadline: {self._timeout}s"
            self.log.error(msg)
            raise exceptions.ActorTimedOut(msg) from None

        return ret

    def _check_condition(self):
        """Check if specified condition allows this actor to run.

        Evaluate self._condition to figure out if this actor should run.
        The only exception to simply casting this variable to bool is if
        the value of self._condition is a string "False" or string "0".
        """

        check = utils.str2bool(self._condition)
        self.log.debug(f"Condition {self._condition} evaluates to {check}")
        return check

    def _fill_in_contexts(self, context={}, strict=True, remove_escape_sequence=True):
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
                remove_escape_sequence=remove_escape_sequence,
            )
        except LookupError as e:
            msg = f"Context for description failed: {e}"
            raise exceptions.InvalidOptions(msg) from e

        # Inject contexts into condition
        try:
            self._condition = utils.populate_with_tokens(
                str(self._condition),
                context,
                self.left_context_separator,
                self.right_context_separator,
                strict=strict,
                remove_escape_sequence=remove_escape_sequence,
            )
        except LookupError as e:
            msg = f"Context for condition failed: {e}"
            raise exceptions.InvalidOptions(msg) from e

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
                escape_sequence="\\\\",
                remove_escape_sequence=remove_escape_sequence,
            )
        except LookupError as e:
            msg = f"Context for options failed: {e}"
            raise exceptions.InvalidOptions(msg) from e

        # Finally, convert the string back into a dict and store it.
        self._options = json.loads(new_options_string)

    def get_orgchart(self, parent=""):
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

        return [
            {
                "id": str(id(self)),
                "desc": self._desc,
                "class": self.__class__.__name__,
                # 'options': self._options,  # May include tokens & ENV vars
                "parent_id": parent,
            }
        ]

    @timer
    async def execute(self):
        """Executes an actor and returns the results when its finished.

        Calls an actors private _execute() method and either returns the result
        or handles any exceptions that are raised.

        RecoverableActorFailure exceptions are potentially swallowed up (and
        warned) if the self._warn_on_failure flag is set. Otherwise, they're
        logged and re-raised. All other ActorException exceptions are caught,
        logged and re-raised.

        We have a generic catch-all exception handling block as well, because
        third party Actor classes may or may not catch all appropriate
        exceptions. This block is mainly here to prevent the entire app from
        failing due to a poorly written Actor.

        Returns:
            The result from _execute(), or None if skipped/warned.
        """
        self.log.debug("Beginning")

        # Any exception thats raised by an actors _execute() method will
        # automatically cause actor failure and we return right away.
        result = None

        if not self._check_condition():
            self.log.warning(f"Skipping execution. Condition: {self._condition}")
            return

        try:
            result = await self.timeout(self._execute)
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
                f"Continuing execution even though a failure was "
                f"detected (warn_on_failure={self._warn_on_failure})"
            )
        except ExceptionGroup as eg:
            # asyncio.TaskGroup wraps child task exceptions in ExceptionGroup.
            # Log all errors for full observability, then unwrap and apply the
            # same recovery logic as the ActorException handler above so that
            # warn_on_failure is respected.
            for i, exc in enumerate(eg.exceptions):
                if i == 0:
                    self.log.critical(exc)
                else:
                    self.log.error(f"Additional concurrent failure: {exc}")

            first = eg.exceptions[0]
            recover = isinstance(first, exceptions.RecoverableActorFailure)
            if recover and self._warn_on_failure:
                self.log.warning(
                    f"Continuing execution even though a failure was "
                    f"detected (warn_on_failure={self._warn_on_failure})"
                )
            else:
                raise first from eg
        except Exception as e:
            # We don't like general exception catch clauses like this, but
            # because actors can be written by third parties and automatically
            # imported, its impossible for us to catch every exception
            # possible. This is a failsafe thats meant to throw a strong
            # warning.
            log.critical(
                f"Unexpected exception caught! "
                f"Please contact the author ({sys.modules[self.__module__].__author__}) and provide them "
                f"with this stacktrace"
            )
            self.log.exception(e)
            raise exceptions.ActorException(e) from e
        else:
            self.log.debug(f"Finished successfully, return value: {result}")

        # If we got here, we're exiting the actor cleanly and moving on.
        return result


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

        :`_set_state`: Creates or destroys the resource depending on the 'state' parameter that was passed in. Note: The 'state' parameter is automatically added to the options. You do not need to define it.
        :`_get_state`: Gets the current state of the resource.
        :`_set_[option]`: A 'setter' for each option name passed in.
        :`_get_[option]`: A 'getter' for each option name passed in.

    **Optional Methods:**

        :`_precache`: Called before any setters/getters are triggered. Used to optionally populate a cache of data to make the getters faster. For example, if you can make one API call to get all of the data about a resource, then store that data locally for fast access.
        :`_compare_[option]`: Optionally you can write your own comparison method if you're not doing a pure string comparison between the source and destination.

    **Examples**

    .. code-block:: python

        class MyClass(base.EnsurableBaseActor):

            all_options = {
                'name': (str, REQUIRED, 'Name of thing'),
                'description': (str, None, 'Description of thing')
            }

            unmanaged_options = ['name']

            async def _set_state(self):
                if self.option('state') == 'absent':
                    await self.conn.delete_resource(
                        name=self.option('name'))
                else:
                    await self.conn.create_resource(
                        name=self.option('name'),
                        desc=self.option('description'))

            async def _set_description(self):
                await self.conn.set_desc_of_resource(
                    name=self.option('name'),
                    desc=self.option('description'))

            async def _get_description(self):
                await self.conn.get_desc_of_resource(
                    name=self.option('name'))
    """

    # A list of option names that are _not_ automatically managed. These are
    # useful if you have special behaviors like 'commit' on change, or if you
    # have parameters that are unmutable ('name').
    unmanaged_options = []

    def __init__(self, *args, **kwargs):
        # The 'state' parameter is a given, so make sure its set,
        self.all_options["state"] = (
            STATE,
            "present",
            "Desired state: present or absent",
        )

        # Now go ahead and validate all of the user inputs the normal way
        super().__init__(*args, **kwargs)

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
            setter = f"_set_{option}"
            getter = f"_get_{option}"
            comparer = f"_compare_{option}"

            if not self._is_method(getter) or not self._is_method(setter):
                raise exceptions.UnrecoverableActorFailure(
                    f"Invalid Actor Code Detected in {self.__class__.__name__}: "
                    f"Unable to find required methods: {setter}, {getter}"
                )

            if not self._is_method(comparer):

                async def _comparer(option=option):
                    existing = await self.getters[option]()
                    new = self.option(option)
                    return existing == new

                setattr(self, comparer, _comparer)
                # self.log.debug('Creating dynamic method %s' % comparer)

            self.setters[option] = getattr(self, setter)
            self.getters[option] = getattr(self, getter)
            self.comparers[option] = getattr(self, comparer)

    def _is_method(self, name):
        return hasattr(self, name) and inspect.ismethod(getattr(self, name))

    async def _precache(self):
        """Override this method to pre-cache data in your actor.

        This method can be overridden to go off and pre-fetch data for your
        actors _set and _get methods. This helps if you can execute a single
        API call that gets most of the data you need, before any of the actual
        get/set operations take place.
        """
        return

    async def _get_state(self):
        raise NotImplementedError("_get_state is required for Ensurable")

    async def _set_state(self):
        raise NotImplementedError("_set_state is required for Ensurable")

    async def _ensure(self, option):
        """Compares the desired state with the actual state of a resource.

        Uses the getter for a resource option to determine its current state,
        and then compares it with the desired state. Generally does a simple
        string comparison of the states, but user can optionally define their
        own comparison mechanism as well.

        If the states do not match, then the setter method is called.
        """
        equals = await self.comparers[option]()

        if equals:
            self.log.debug(f'Option "{option}" matches')
            return

        self.log.debug(f'Option "{option}" DOES NOT match, calling setter')
        await self.setters[option]()

    async def _execute(self):
        """A pretty simple execution pipeline for the actor.

        .. note::

            An OrderedDict can be used instead of a plain dict when order
            actually matters for the option setting.
        """
        await self._precache()

        await self._ensure("state")

        if self.option("state") == "absent":
            return

        for option in self._ensurable_options:
            # We've already managed state .. so make sure we skip the state
            # option and only manage the others.
            if option != "state":
                await self._ensure(option)


class HTTPBaseActor(BaseActor):
    """Abstract base class for an HTTP-client based Actor object.

    This class provides common methods for getting access to asynchronous
    HTTP clients, wrapping the executions in appropriate try/except blocks,
    timeouts, etc.

    If you're writing an Actor that uses a remote REST API, this is the
    base class you should subclass from.
    """

    headers = None
    _http_executor = ThreadPoolExecutor(10)

    def _get_method(self, post):
        """Returns the appropriate HTTP Method based on the supplied Post data.

        Args:
            post: The post body you intend to submit in the URL request

        Returns:
            'GET' or 'POST'
        """
        # If there is no post data, set the request method to GET
        if post is not None:
            return "POST"
        else:
            return "GET"

    def _generate_escaped_url(self, url, args):
        """Takes in a dictionary of arguments and returns a URL line.

        Sorts the arguments so that the returned string is predictable and in
        alphabetical order. Strips out None values and lowercases Bool values.

        Args:
            url: (Str) The URL to append the arguments to
            args: (Dict) Key/Value arguments. Values should be primitives.

        Returns:
            A URL encoded string like this: <url>?foo=bar&abc=xyz
        """
        args = {k: v for k, v in args.items() if v}

        for key, value in args.items():
            if isinstance(value, bool):
                args[key] = str(value).lower()

        parsed = urllib.parse.urlsplit(url)
        existing_params = urllib.parse.parse_qsl(
            parsed.query, keep_blank_values=True
        )
        existing_params.extend(sorted(args.items()))
        query = urllib.parse.urlencode(existing_params)
        full_url = urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment)
        )
        self.log.debug(f"Generated URL: {full_url}")

        return full_url

    async def _fetch(self, url, post=None, auth_username=None, auth_password=None):
        """Executes a web request asynchronously and returns the parsed body.

        Args:
            url: (Str) The full url path of the API call
            post: (Str) POST body data to submit (if any)
            auth_username: (str) HTTP auth username
            auth_password: (str) HTTP auth password
        """
        self.log.debug(f"Making HTTP request to {url} with data: {post}")

        method = self._get_method(post)
        data = post.encode("utf-8") if post else None
        req = urllib.request.Request(url, data=data, method=method)

        if self.headers:
            for k, v in self.headers.items():
                req.add_header(k, v)

        if auth_username and auth_password:
            credentials = base64.b64encode(
                f"{auth_username}:{auth_password}".encode()
            ).decode()
            req.add_header("Authorization", f"Basic {credentials}")

        loop = asyncio.get_event_loop()
        http_response = await loop.run_in_executor(
            self._http_executor,
            functools.partial(urllib.request.urlopen, req),
        )

        try:
            body = json.loads(http_response.read())
        except ValueError as e:
            raise exceptions.UnparseableResponseFromEndpoint(
                f"Unable to parse response from remote API as JSON: {e}"
            ) from e

        return body
