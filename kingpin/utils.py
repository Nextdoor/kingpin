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

log = logging.getLogger(__name__)

# Constants for some of the utilities below
STATIC_PATH_NAME = 'static'


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
