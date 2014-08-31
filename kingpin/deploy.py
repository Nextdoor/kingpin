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
"""CLI Script Runner for Kingpin

**NOTE: THIS IS A TOTAL WORK IN PROGRESS. NOT SUITABLE FOR PRODUCTION YET**

"""

__author__ = 'Matt Wise (matt@nextdoor.com)'

from tornado import ioloop
import logging
import optparse
import sys

from tornado import gen

from kingpin import exceptions
from kingpin import schema
from kingpin import utils
from kingpin.actors import utils as actor_utils
from kingpin.version import __version__ as VERSION

log = logging.getLogger(__name__)


# Initial option handler to set up the basic application environment.
usage = 'usage: %prog <options>'
parser = optparse.OptionParser(usage=usage, version=VERSION,
                               add_help_option=True)
parser.set_defaults(verbose=True)

# Job Configuration
parser.add_option('-j', '--json', dest='json',
                  help='Path to JSON Deployment File')
parser.add_option('-d', '--dry', dest='dry', action='store_true',
                  help='Executes a DRY run.')

# Logging Configuration
parser.add_option('-l', '--level', dest="level", default='info',
                  help='Set logging level (INFO|WARN|DEBUG|ERROR)')
parser.add_option('-s', '--syslog', dest='syslog',
                  default=None,
                  help='Log to syslog. Supply facility name. (ie "local0")')

(options, args) = parser.parse_args()


def get_root_logger(level, syslog):
    """Configures our Python stdlib Root Logger"""
    # Convert the supplied log level string
    # into a valid log level constant
    level_string = 'logging.%s' % level.upper()
    level_constant = utils.str_to_class(level_string)

    # Set up the logger now
    return utils.setupLogger(level=level_constant, syslog=syslog)


@gen.coroutine
def main():
    try:
        # Run the JSON dictionary through our environment parser and return
        # back a dictionary with all of the %XX%% keys swapped out with
        # environment variables.
        config = utils.convert_json_to_dict(options.json)
        # Run the dict through our schema validator quickly
        schema.validate(config)
    except exceptions.InvalidEnvironment as e:
        log.error('Invalid Configuration Detected: %s' % e)
        sys.exit(1)

    # TODO: Method-ize-this
    actor = config.pop('actor')
    initial_actor = actor_utils.get_actor_class(actor)(
        dry=options.dry, **config)
    yield initial_actor.execute()

if __name__ == '__main__':
    # Set up logging
    get_root_logger(options.level, options.syslog)
    logging.getLogger('nd_service_registry.shims').setLevel(logging.WARNING)

    try:
        ioloop.IOLoop.instance().run_sync(main)
    except KeyboardInterrupt:
        log.info('CTRL-C Caught, shutting down')
