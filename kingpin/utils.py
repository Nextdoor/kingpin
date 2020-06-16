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
# Copyright 2013 Nextdoor.com, Inc.

"""
:mod:`kingpin.utils`
^^^^^^^^^^^^^^^^^^^^

Common package for utility functions.
"""

from logging import handlers
import difflib
import datetime
import demjson
import functools
import importlib
import logging
import os
import pprint
import re
import sys
import yaml
import io
from io import IOBase

from tornado import gen
from tornado import ioloop
import http.client
import rainbow_logging_handler

from kingpin import exceptions


__author__ = 'Matt Wise (matt@nextdoor.com)'

log = logging.getLogger(__name__)

# Constants for some of the utilities below
STATIC_PATH_NAME = 'static'

# Disable the global threadpool defined here to try to narrow down the random
# unit test failures regarding the IOError. Instead, instantiating a new
# threadpool object for every thread using the 'with' context below.
#
# # Allow up to 10 threads to be executed at once. This is arbitrary, but we
# # want to prvent the app from going thread-crazy.
# THREADPOOL_SIZE = 10
# THREADPOOL = futures.ThreadPoolExecutor(THREADPOOL_SIZE)


def str_to_class(string):
    """Method that converts a string name into a usable Class name

    This is used to take the 'actor' value from the JSON object and convert it
    into a valid object reference.

    Args:
        cls: String name of the wanted class and package.
             eg: kingpin.actors.foo.bar
             eg: misc.Sleep
             eg: actors.misc.Sleep
             eg: my.private.Actor

    Returns:
        A reference to the actual Class to be instantiated
    """
    # Split the string up. The last element is the Class, the rest is
    # the package name.
    string_elements = string.split('.')
    class_name = string_elements.pop()
    module_name = '.'.join(string_elements)

    m = importlib.import_module(module_name)
    return getattr(m, class_name)


def setup_root_logger(level='warn', syslog=None, color=False):
    """Configures the root logger.

    Args:
        level: Logging level string ('warn' is default)
        syslog: String representing syslog facility to output to.  If empty,
        logs are written to console.
        color: Colorize the log output

    Returns:
        A root Logger object
    """

    # Get the logging level string -> object
    level = 'logging.%s' % level.upper()
    level_obj = str_to_class(level)

    # Get our logger
    logger = logging.getLogger()

    # Set our default logging level
    logger.setLevel(level_obj)

    # Set the default logging handler to stream to console..
    if color:
        # Patch the handler's 'is_tty()' method to return True. If the user
        # asked for color, we give them color. The is_tty() method calls the
        # sys.stdout.isatty() method and then refuses to give color output on
        # platforms like Jenkins, where this code is likely to be run.
        rainbow_logging_handler.RainbowLoggingHandler.is_tty = True

        handler = rainbow_logging_handler.RainbowLoggingHandler(
            sys.stdout,

            # Disable colorization of the 'info' log statements. If the code is
            # run in an environment like Jenkins, the background is white, and
            # we don't want to force these log lines to be white as well.
            color_message_info=(None, None, False)
        )
    else:
        handler = logging.StreamHandler()

    # Get our PID .. used below in the log line format.
    details = ''
    if level_obj <= 10:
        details = str(os.getpid()) + ' [%(name)-40s] [%(funcName)-20s]'

    # If syslog enabled, then override the logging handler to go to syslog.
    asctime = '%(asctime)-10s '
    if syslog is not None:
        asctime = ''
        handler = handlers.SysLogHandler(address=('127.0.0.1', 514),
                                         facility=syslog)

    fmt = asctime + '%(levelname)-8s ' + details + ' %(message)s'
    formatter = logging.Formatter(fmt)

    # Append the formatter to the handler, then set the handler as our default
    # handler for the root logger.
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


def super_httplib_debug_logging():
    """Enables DEBUG logging deep in HTTPLIB.

    HTTPLib by default doens't log out things like the raw HTTP headers,
    cookies, response body, etc -- even when your main logger is in DEBUG mode.
    This is because its a security risk, as well as just highly verbose.

    For the purposes of debugging though, this can be useful. This method
    enables deep debug logging of the HTTPLib web requests. This is highly
    insecure, but very useful when troubleshooting failures with remote API
    endpoints.

    Returns:
        Requests 'logger' object (mainly for unit testing)
    """
    http.client.HTTPConnection.debuglevel = 1
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.propagate = True
    requests_log.setLevel(logging.DEBUG)
    return requests_log


def exception_logger(func):
    """Explicitly log Exceptions then Raise them.

    Logging Exceptions and Tracebacks while inside of a thread is broken in the
    Tornado futures package for Python 2.7. It swallows most of the traceback
    and only gives you the raw exception object. This little helper method
    allows us to throw a log entry with the full traceback before raising the
    exception.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            log.debug('Exception caught in %s(%s, %s): %s' %
                      (func, args, kwargs, e), exc_info=1)
            raise
    return wrapper


def retry(excs, retries=3, delay=0.25):
    """Coroutine-compatible Retry Decorator.

    This decorator provides a simple retry mechanism that looks for a
    particular set of exceptions and retries async tasks in the event that
    those exceptions were caught.

    Example usage:
        >>> @gen.coroutine
        ... @retry(excs=(Exception), retries=3)
        ... def login(self):
        ...     raise gen.Return()

    Args:
        excs: A single (or tuple) exception type to catch.
        retries: The number of times to try the operation in total.
        delay: Time (in seconds) to wait between retries
    """
    def _retry_on_exc(f):
        def wrapper(*args, **kwargs):
            i = 1
            while True:
                try:
                    # Don't log the first time..
                    if i > 1:
                        log.debug('Try (%s/%s) of %s(%s, %s)' %
                                  (i, retries, f, args, kwargs))
                    ret = yield gen.coroutine(f)(*args, **kwargs)
                    log.debug('Result: %s' % ret)
                    raise gen.Return(ret)
                except excs as e:
                    log.error('Exception raised on try %s: %s' % (i, e))

                    if i >= retries:
                        log.debug('Raising exception: %s' % e)
                        raise e

                    i += 1
                    log.debug('Retrying in %s...' % delay)
                    yield tornado_sleep(delay)
                log.debug('Retrying..')
        return wrapper
    return _retry_on_exc


@gen.coroutine
def tornado_sleep(seconds=1.0):
    """Async method equivalent to sleeping.

    Args:
        seconds: Float seconds. Default 1.0
    """
    yield gen.sleep(seconds)


def populate_with_tokens(string, tokens, left_wrapper='%', right_wrapper='%',
                         strict=True, escape_sequence='\\',
                         remove_escape_sequence=True):
    """Insert token variables into the string.

    Will match any token wrapped in '%'s and replace it with the value of that
    token.

    Args:
        string: string to modify.
        tokens: dictionary of key:value pairs to inject into the string.
        left_wrapper: the character to use as the START of a token
        right_wrapper: the character to use as the END of a token
        strict: (bool) whether or not to make sure all tokens were replaced
        escape_sequence: character string to use as the escape sequence for
        left and right wrappers
        remove_escape_sequence: (bool) whether or not to remove the escape
        sequence if it found. For example \\%FOO\\% would turn into %FOO%.
    Example:
        export ME=biz

        string='foo %ME% %bar%'
        populate_with_tokens(string, os.environ)  # 'foo biz %bar%'
    """

    # First things first, swap out all instances of %<str>% with any matching
    # token variables found. If no items are in the hash (none, empty hash,
    # etc), then skip this.
    allowed_types = (str, str, bool, int, float)
    if tokens:
        for k, v in tokens.items():

            if type(v) not in allowed_types:
                log.warning('Token %s=%s is not in allowed types: %s' % (
                    k, v, allowed_types))
                continue

            string = string.replace(
                ('%s%s%s' % (left_wrapper, k, right_wrapper)), str(v))

    tokens_with_default = re.finditer(
        r'{0}(([\w]+)[|]([^{1}]+)){1}'.format(left_wrapper, right_wrapper),
        string)
    for match, key, default in (m.groups() for m in tokens_with_default):
        value = tokens.get(key, default)
        string = string.replace(
            '%s%s%s' % (left_wrapper, match, right_wrapper), str(value))

    # Slashes need to be escaped properly because they are a
    # part of the regex syntax.
    escape_sequence = escape_sequence.replace('\\', '\\\\')
    escape_pattern = r'({0}{1})([\w]+)({0}{2})'.format(
        escape_sequence,
        left_wrapper,
        right_wrapper)

    # If we are strict, we check if we missed anything. If we did, raise an
    # exception.
    if strict:
        missed_tokens = list(set(re.findall(r'%s[\w]+%s' %
                                 (left_wrapper, right_wrapper), string)))

        # Remove the escaped tokens from the missing tokens
        escape_findings = re.finditer(escape_pattern, string)

        escaped_tokens = [m.groups()[1] for m in escape_findings]
        missed_tokens = list(set(missed_tokens) - set(escaped_tokens))

        if missed_tokens:
            raise LookupError(
                'Found un-matched tokens in JSON string: %s' % missed_tokens)

    # Find text that's between the wrappers and escape sequence and
    # replace with just the wrappers and text.
    if remove_escape_sequence:
        string = re.sub(
            escape_pattern,
            r'{0}\2{1}'.format(left_wrapper, right_wrapper),
            string)
    return string


def convert_script_to_dict(script_file, tokens):
    """Converts a JSON file to a config dict.

    Reads in a JSON file, swaps out any environment variables that
    have been used inside the JSON, and then returns a dictionary.

    Args:
        script_file: Path to the JSON/YAML file to import, or file instance.
        tokens: dictionary to pass to populate_with_tokens.

    Returns:
        <Dictonary of Config Data>

    Raises:
        kingpin.exceptions.InvalidScript
    """

    filename = ''
    try:
        if isinstance(script_file, IOBase):
            filename = script_file.name
            instance = script_file
        else:
            filename = script_file
            instance = io.open(script_file)
    except IOError as e:
        raise exceptions.InvalidScript('Error reading script %s: %s' %
                                       (script_file, e))

    log.debug('Reading %s' % filename)
    raw = instance.read()
    parsed = populate_with_tokens(raw, tokens)

    # If the file ends with .json, use demjson to read it. If it ends with
    # .yml/.yaml, use PyYAML. If neither, error.
    suffix = filename.split('.')[-1].strip().lower()

    try:
        if suffix == 'json':
            decoded = demjson.decode(parsed)
        elif suffix in ('yml', 'yaml'):
            decoded = yaml.safe_load(parsed)
            if decoded is None:
                raise exceptions.InvalidScript(
                    'Invalid YAML in `%s`' % filename)
        else:
            raise exceptions.InvalidScriptName(
                'Invalid file extension: %s' % suffix)
    except demjson.JSONError as e:
        # demjson exceptions have `pretty_description()` method with
        # much more useful info.
        raise exceptions.InvalidScript('JSON in `%s` has an error: %s' % (
            filename, e.pretty_description()))
    return decoded


def order_dict(obj):
    """Re-orders a dict into a predictable pattern.

    Used so that you can compare two dicts with the same values, but that were
    created in different orders.

    Stolen from:
      http://stackoverflow.com/questions/25851183/how-to-compare-two-json-
      objects-with-the-same-elements-in-a-different-order-equa

    args:
        obj: Object to order

    returns:
        obj: A sorted version of the object
    """
    if isinstance(obj, dict):
        return sorted((k, order_dict(v)) for k, v in list(obj.items()))
    if isinstance(obj, list):
        return sorted((order_dict(x) for x in obj), key=str)
    else:
        return obj


def create_repeating_log(logger, message, handle=None, **kwargs):
    """Create a repeating log message.

    This function sets up tornado to repeatedly log a message in a way that
    does not need to be `yield`-ed.

    Example::

       >>> yield do_tornado_stuff(1)
       >>> log_handle = create_repeating_log('Computing...')
       >>> yield do_slow_computation_with_insufficient_logging()
       >>> clear_repeating_log(log_handle)

    This is similar to javascript's setInterval() and clearInterval().

    Args:
        message: String to pass to log.info()
        kwargs: values accepted by datetime.timedelta namely seconds, and
        milliseconds.

    Must be cleared via clear_repeating_log()
    Only handles one interval per actor.
    """

    class OpaqueHandle(object):

        """Tornado async io handler."""

        def __init__(self):
            self.timeout_id = None

    if not handle:
        handle = OpaqueHandle()

    def log_and_queue():
        logger(message)
        create_repeating_log(logger, message, handle, **kwargs)

    deadline = datetime.timedelta(**kwargs)
    # Here we only queue the call, we don't want to wait on it!
    timeout_id = ioloop.IOLoop.current().add_timeout(deadline, log_and_queue)
    handle.timeout_id = timeout_id

    return handle


def clear_repeating_log(handle):
    """Stops the timeout function from being called."""
    ioloop.IOLoop.current().remove_timeout(handle.timeout_id)


def diff_dicts(dict1, dict2):
    """Compares two dicts and returns the difference as a string,
    if there is any.

    Sorts two dicts (including sorting of the lists!!) and then diffs them.
    This will ignore string types ('unicode' vs 'string').

    args:
        dict1: First dict
        dict2: Second dict

    returns:
        A diff string if there's any difference, otherwise None.
    """
    dict1 = order_dict(dict1)
    dict2 = order_dict(dict2)

    if dict1 == dict2:
        return

    dict1 = pprint.pformat(dict1).splitlines()
    dict2 = pprint.pformat(dict2).splitlines()

    # Remove unicode identifiers.
    dict1 = [line.replace('u\'', '\'') for line in dict1]
    dict2 = [line.replace('u\'', '\'') for line in dict2]

    return '\n'.join(difflib.unified_diff(dict1, dict2, n=2))
