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
Main entry-point script for zk_mnonitor.
"""

__author__ = 'Matt Wise (matt@nextdoor.com)'

from tornado import ioloop
import logging
import optparse

from deployer import utils
from deployer.version import __version__ as VERSION

log = logging.getLogger(__name__)


# Initial option handler to set up the basic application environment.
usage = 'usage: %prog <options>'
parser = optparse.OptionParser(usage=usage, version=VERSION,
                               add_help_option=True)
parser.set_defaults(verbose=True)


# Path to the Zookeeper node list to monitor.
# This file should be in YAML format.
parser.add_option('-f', '--file', dest='file',
                  default=None,
                  help='Path to JSON file with znodes to monitor.')

# Web Server Config Settings
parser.add_option('-l', '--level', dest="level", default='warn',
                  help='Set logging level (INFO|WARN|DEBUG|ERROR)')
parser.add_option('-s', '--syslog', dest='syslog', default=None,
                  help='Log to syslog. Supply facility name. (ie "local0")')

(options, args) = parser.parse_args()


def getRootLogger(level, syslog):
    """Configures our Python stdlib Root Logger"""
    # Convert the supplied log level string
    # into a valid log level constant
    level_string = 'logging.%s' % level.upper()
    level_constant = utils.strToClass(level_string)

    # Set up the logger now
    return utils.setupLogger(level=level_constant, syslog=syslog)


# TODO: Refactor this main() class so its more testable
def main():
    # Set up logging
    getRootLogger(options.level, options.syslog)

if __name__ == '__main__':
    main()
