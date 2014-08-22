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
Common package for utility functions.
"""

__author__ = 'Matt Wise (matt@nextdoor.com)'

from logging import handlers
import os
import logging
import time

from tornado import gen
from tornado import ioloop
import futures
import requests

log = logging.getLogger(__name__)

# Constants for some of the utilities below
STATIC_PATH_NAME = 'static'

# Allow up to 10 threads to be executed at once. This is arbitrary, but we
# want to prvent the app from going thread-crazy.
THREADPOOL_SIZE = 10
THREADPOOL = futures.ThreadPoolExecutor(THREADPOOL_SIZE)


def strToClass(string):
    """Method that converts a string name into a usable Class name

    This is used to take the 'translator' config value from the
    Config object and convert it into a valid object.

    Args:
        cls: String name of the wanted class and package.
             eg: zk_monitor.foo.bar

    Returns:
        A reference to the actual Class to be instantiated
    """
    # Split the string up. The last element is the Class, the rest is
    # the package name.
    log.debug('Translating "%s" into a Module and Class...' % string)
    string_elements = string.split('.')
    class_name = string_elements.pop()
    module_name = '.'.join(string_elements)
    log.debug('Module: %s, Class: %s' % (module_name, class_name))

    # load the module, will raise ImportError if module cannot be loaded
    m = __import__(module_name, globals(), locals(), class_name)
    # get the class, will raise AttributeError if class cannot be found
    c = getattr(m, class_name)

    log.debug('Class Reference: %s' % c)
    return c


def getRootPath():
    """Returns the fully qualified path to our root package path.

    Returns:
        A string with the fully qualified path of the zk_monitor app
    """
    return os.path.abspath(os.path.dirname(__file__))


def setupLogger(level=logging.WARNING, syslog=None):
    """Configures the root logger.

    Args:
        level: Logging.<LEVEL> object to set logging level
        syslog: String representing syslog facility to output to.
                If empty, logs are written to console.

    Returns:
        A root Logger object
    """
    # Get our logger
    logger = logging.getLogger()

    # Set our default logging level
    logger.setLevel(level)

    # Set the default logging handler to stream to console..
    handler = logging.StreamHandler()

    # Get our PID .. used below in the log line format.
    pid = os.getpid()
    format = '%(asctime)-15s [' + str(pid) + '] [%(name)s] ' \
             '[%(funcName)s]: (%(levelname)s) %(message)s'

    # If syslog enabled, then override the logging handler to go to syslog.
    if syslog is not None:
        handler = handlers.SysLogHandler(address=('127.0.0.1', 514),
                                         facility=syslog)
        format = '[' + str(pid) + '] [%(name)s] ' \
                 '[%(funcName)s]: (%(levelname)s) %(message)s'

    formatter = logging.Formatter(format)

    # Append the formatter to the handler, then set the handler as our default
    # handler for the root logger.
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


@gen.coroutine
def thread_coroutine(func, *args, **kwargs):
    """Simple ThreadPool executor for Tornado.

    This method leverages the back-ported Python futures
    package (https://pypi.python.org/pypi/futures) to spin up
    a ThreadPool and then kick actions off in the thread pool.

    This is a simple and relatively graceful way of handling
    spawning off of synchronous API calls from the RightScale
    client below without having to do a full re-write of anything.

    This should not be used at high volume... but for the
    use case below, its reasonable.

    Example Usage:
        >>> @gen.coroutine
        ... def login(self):
        ...     ret = yield thread_coroutine(self._client.login)
        ...     raise gen.Return(ret)

    Args:
        func: Function reference
    """
    try:
        ret = yield THREADPOOL.submit(func, *args, **kwargs)
    except requests.exceptions.ConnectionError as e:
        # The requests library can fail to fetch sometimes and its almost
        # always OK to re-try the fetch at least once. If the fetch fails a
        # second time, we allow it to be raised.
        #
        # This should be patched in the python-rightscale library so it
        # auto-retries, but until then we have a patch here to at least allow
        # one automatic retry.
        log.debug('Fetch failed. Will retry one time: %s' % e)
        ret = yield THREADPOOL.submit(func, *args, **kwargs)

    raise gen.Return(ret)


def retry(excs, retries=3):
    """Coroutine-compatible Retry Decorator.

    This decorator provides a simple retry mechanism that looks for a
    particular set of exceptions and retries async tasks in the event that
    those exceptions were caught.

    Example usage:
        >>> @gen.coroutine
        ... @retry(excs=(requests.exceptions.HTTPError), retries=3)
        ... def login(self):
        ...     yield thread_coroutine(self._client.login)
        ...     raise gen.Return()

    Args:
        excs: A single (or tuple) exception type to catch.
        retries: The number of times to try the operation in total.
    """
    def _retry_on_exc(f):
        def wrapper(*args, **kwargs):
            i = 1
            while True:
                try:
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

                    log.debug('Retrying in 0.25s..')
                    i += 1
                    yield gen.Task(ioloop.IOLoop.current().add_timeout,
                                   time.time() + 0.25)
                log.debug('Retrying..')
        return wrapper
    return _retry_on_exc

@gen.coroutine
def tornado_sleep(seconds=1.0):
    """Async method equivalent to sleeping.

    Args:
        seconds: Float seconds. Default 1.0
    """
    yield gen.Task(ioloop.IOLoop.current().add_timeout,
                   time.time() + seconds)
