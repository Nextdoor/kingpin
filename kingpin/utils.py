"""
:mod:`kingpin.utils`
^^^^^^^^^^^^^^^^^^^^

Common package for utility functions.
"""

import asyncio
import datetime
import difflib
import functools
import http.client
import importlib
import json
import logging
import os
import pprint
import re
import sys
from io import IOBase
from json.decoder import JSONDecodeError
from logging import handlers

import cfn_tools
import rainbow_logging_handler
from cfn_tools.yaml_loader import CfnYamlLoader
from cfn_tools.yaml_loader import construct_mapping as aws_construct_mapping

from kingpin import exceptions

log = logging.getLogger(__name__)

# Constants for some of the utilities below
STATIC_PATH_NAME = "static"

# Disable the global threadpool defined here to try to narrow down the random
# unit test failures regarding the IOError. Instead, instantiating a new
# threadpool object for every thread using the 'with' context below.
#
# # Allow up to 10 threads to be executed at once. This is arbitrary, but we
# # want to prvent the app from going thread-crazy.
# THREADPOOL_SIZE = 10
# THREADPOOL = futures.ThreadPoolExecutor(THREADPOOL_SIZE)


# https://github.com/yaml/pyyaml/issues/64
# https://github.com/zerwes/hiyapyco/issues/7
#
# The AWS-provided cfn_tools code does not call the `flatten_mapping()`
# function in their constructor_mapping func. Because of this, YAML Merge
# anchors fail to parse. This little hack below overrides the function to make
# sure that the YAML parsing of merged maps works properly.
def construct_mapping(self, node, deep=False):
    self.flatten_mapping(node)
    mapping = aws_construct_mapping(self, node, deep)
    return mapping


# Override the constructor reference for "tag:yaml.org,2002:map" to ours above.
CfnYamlLoader.add_constructor("tag:yaml.org,2002:map", construct_mapping)


def str_to_class(string):
    """Method that converts a string name into a usable Class name

    This is used to take the 'actor' value from the JSON object and convert it
    into a valid object reference.

    Args:
        cls: String name of the wanted class and package. (eg:
            kingpin.actors.foo.bar, misc.Sleep, actors.misc.Sleep,
            my.private.Actor, etc.)

    Returns:
        A reference to the actual Class to be instantiated
    """
    # Split the string up. The last element is the Class, the rest is
    # the package name.
    string_elements = string.split(".")
    class_name = string_elements.pop()
    module_name = ".".join(string_elements)

    m = importlib.import_module(module_name)
    return getattr(m, class_name)


def setup_root_logger(level="warn", syslog=None, color=False):
    """Configures the root logger.

    Args:
        level: Logging level string ('warn' is default)
        syslog: String representing syslog facility to output to. If empty, logs are written to console.
        color: Colorize the log output

    Returns:
        A root Logger object
    """

    # Get the logging level string -> object
    level = f"logging.{level.upper()}"
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
            color_message_info=(None, None, False),
        )
    else:
        handler = logging.StreamHandler()

    # Get our PID .. used below in the log line format.
    details = ""
    if level_obj <= 10:
        details = str(os.getpid()) + " [%(name)-40s] [%(funcName)-20s]"

    # If syslog enabled, then override the logging handler to go to syslog.
    asctime = "%(asctime)-10s "
    if syslog is not None:
        asctime = ""
        handler = handlers.SysLogHandler(address=("127.0.0.1", 514), facility=syslog)

    fmt = asctime + "%(levelname)-8s " + details + " %(message)s"
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

    Logging exceptions and tracebacks while inside of a thread can swallow
    most of the traceback and only give you the raw exception object. This
    helper method logs the full traceback before re-raising the exception.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            log.debug(
                f"Exception caught in {func}({args}, {kwargs}): {e}",
                exc_info=1,
            )
            raise

    return wrapper


def retry(excs, retries=3, delay=0.25):
    """Async-compatible Retry Decorator.

    This decorator provides a simple retry mechanism that looks for a
    particular set of exceptions and retries async tasks in the event that
    those exceptions were caught.

    Args:
        excs: A single (or tuple) exception type to catch.
        retries: The number of times to try the operation in total.
        delay: Time (in seconds) to wait between retries
    """

    def _retry_on_exc(f):
        async def wrapper(*args, **kwargs):
            i = 1
            while True:
                try:
                    if i > 1:
                        log.debug(f"Try ({i}/{retries}) of {f}({args}, {kwargs})")
                    ret = await f(*args, **kwargs)
                    log.debug(f"Result: {ret}")
                    return ret
                except excs as e:
                    log.error(f"Exception raised on try {i}: {e}")

                    if i >= retries:
                        log.debug(f"Raising exception: {e}")
                        raise e

                    i += 1
                    log.debug(f"Retrying in {delay}...")
                    await asyncio.sleep(delay)
                log.debug("Retrying..")

        return wrapper

    return _retry_on_exc



def populate_with_tokens(
    string,
    tokens,
    left_wrapper="%",
    right_wrapper="%",
    strict=True,
    escape_sequence="\\",
    remove_escape_sequence=True,
):
    """Insert token variables into the string.

    Will match any token wrapped in '%'s and replace it with the value of that
    token.

    Args:
        string: string to modify.
        tokens: dictionary of key:value pairs to inject into the string.
        left_wrapper: the character to use as the START of a token
        right_wrapper: the character to use as the END of a token
        strict: (bool) whether or not to make sure all tokens were replaced
        escape_sequence: character string to use as the escape sequence for left and right wrappers
        remove_escape_sequence: (bool) whether or not to remove the escape sequence if it found. For example \\%FOO\\% would turn into %FOO%.

    Example:
        export ME=biz

        string='foo %ME% %bar%'
        populate_with_tokens(string, os.environ)  # 'foo biz %bar%'
    """

    # First things first, swap out all instances of %<str>% with any matching
    # token variables found. If no items are in the hash (none, empty hash,
    # etc), then skip this.
    allowed_types = (str, bool, int, float)
    if tokens:
        for k, v in tokens.items():

            if type(v) not in allowed_types:
                log.warning(f"Token {k}={v} is not in allowed types: {allowed_types}")
                continue

            string = string.replace((f"{left_wrapper}{k}{right_wrapper}"), str(v))

    tokens_with_default = re.finditer(
        rf"{left_wrapper}(([\w]+)[|]([^{right_wrapper}]+)){right_wrapper}", string
    )
    for match, key, default in (m.groups() for m in tokens_with_default):
        value = tokens.get(key, default)
        string = string.replace(f"{left_wrapper}{match}{right_wrapper}", str(value))

    # Slashes need to be escaped properly because they are a
    # part of the regex syntax.
    escape_sequence = escape_sequence.replace("\\", "\\\\")
    escape_pattern = (
        rf"({escape_sequence}{left_wrapper})([\w]+)({escape_sequence}{right_wrapper})"
    )

    # If we are strict, we check if we missed anything. If we did, raise an
    # exception.
    if strict:
        missed_tokens = list(
            set(re.findall(rf"{left_wrapper}[\w]+{right_wrapper}", string))
        )

        # Remove the escaped tokens from the missing tokens
        escape_findings = re.finditer(escape_pattern, string)

        escaped_tokens = [m.groups()[1] for m in escape_findings]
        missed_tokens = list(set(missed_tokens) - set(escaped_tokens))

        if missed_tokens:
            raise LookupError(
                f"Found un-matched tokens in JSON string: {missed_tokens}"
            )

    # Find text that's between the wrappers and escape sequence and
    # replace with just the wrappers and text.
    if remove_escape_sequence:
        string = re.sub(escape_pattern, rf"{left_wrapper}\2{right_wrapper}", string)
    return string


def load_json_with_tokens(file_path, tokens):
    """Converts a JSON/YAML file to a Python object.

    Reads in a JSON/YAML file, swaps out any environment variables that
    have been used inside the file, and then returns the parsed object
    (dict, list, or other JSON-compatible type).

    Args:
        file_path: Path to the JSON/YAML file to import, or file instance.
        tokens: dictionary to pass to populate_with_tokens.

    Returns:
        Parsed object (dict, list, or other JSON-compatible type)

    Raises:
        kingpin.exceptions.InvalidScript
        kingpin.exceptions.InvalidScriptName
    """

    filename = ""
    try:
        if isinstance(file_path, IOBase):
            filename = file_path.name
            instance = file_path
        else:
            filename = file_path
            instance = open(file_path)
    except OSError as e:
        raise exceptions.InvalidScript(f"Error reading script {file_path}: {e}") from e

    log.debug(f"Reading {filename}")
    raw = instance.read()
    parsed = populate_with_tokens(raw, tokens)

    # If the file ends with .json, use json to read it. If it ends with
    # .yml/.yaml, use PyYAML. If neither, error.
    suffix = filename.split(".")[-1].strip().lower()

    try:
        if suffix == "json":
            decoded = json.loads(parsed)
        elif suffix in ("yml", "yaml"):
            decoded = cfn_tools.load_yaml(parsed)
            if decoded is None:
                raise exceptions.InvalidScript(f"Invalid YAML in `{filename}`")
        else:
            raise exceptions.InvalidScriptName(f"Invalid file extension: {suffix}")
    except JSONDecodeError as e:
        raise exceptions.InvalidScript(
            f"JSON in `{filename}` has an error: {str(e)}"
        ) from e
    return decoded


def order_dict(obj):
    """Re-orders a dict into a predictable pattern.

    Used so that you can compare two dicts with the same values, but that were
    created in different orders.

    Stolen from: http://stackoverflow.com/questions/25851183/how-to-compare-two-json-objects-with-the-same-elements-in-a-different-order-equa

    Args:
        obj: Object to order

    Returns:
        obj: A sorted version of the object
    """
    if isinstance(obj, dict):
        return sorted((k, order_dict(v)) for k, v in obj.items())
    if isinstance(obj, list):
        return sorted((order_dict(x) for x in obj), key=str)
    else:
        return obj


def create_repeating_log(logger, message, handle=None, **kwargs):
    """Create a repeating log message.

    Similar to JavaScript's setInterval() / clearInterval().
    Must be cleared via clear_repeating_log().

    Args:
        logger: Callable to invoke with message (e.g. log.info)
        message: String to pass to logger
        kwargs: values accepted by datetime.timedelta (seconds, milliseconds)
    """

    class OpaqueHandle:
        def __init__(self):
            self.timer_handle = None

    if not handle:
        handle = OpaqueHandle()

    def log_and_queue():
        logger(message)
        create_repeating_log(logger, message, handle, **kwargs)

    delay = datetime.timedelta(**kwargs).total_seconds()
    loop = asyncio.get_event_loop()
    handle.timer_handle = loop.call_later(delay, log_and_queue)

    return handle


def clear_repeating_log(handle):
    """Stops the repeating log message."""
    handle.timer_handle.cancel()


def diff_dicts(dict1, dict2):
    """Compares two dicts and returns the difference as a string, if there is
    any.

    Sorts two dicts (including sorting of the lists!!) and then diffs them. This
    will ignore string types ('unicode' vs 'string').

    Args:
        dict1: First dict
        dict2: Second dict

    Returns:
        A diff string if there's any difference, otherwise None.
    """
    dict1 = order_dict(dict1)
    dict2 = order_dict(dict2)

    if dict1 == dict2:
        return

    dict1 = pprint.pformat(dict1).splitlines()
    dict2 = pprint.pformat(dict2).splitlines()

    return "\n".join(difflib.unified_diff(dict1, dict2, n=2))


def str2bool(v, strict=False) -> bool:
    """Returns a Boolean from a variety of inputs.

    Args:
        value: String/Bool
        strict: Whether or not to _only_ convert the known words into booleans, or whether to allow "any" word to be considered True other than the known False words.

    Returns:
        A boolean
    """
    false = ("no", "false", "f", "0")
    true = ("yes", "true", "t", "1")

    string = str(v).lower()

    if strict:
        if string not in true and string not in false:
            raise ValueError(f"Expected [{true}, {false}] but got: {string}")

    return string not in false
