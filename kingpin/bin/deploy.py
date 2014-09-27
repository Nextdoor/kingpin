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
from kingpin.actors import exceptions as actor_exceptions
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
parser.add_option('-l', '--level', dest='level', default='info',
                  help='Set logging level (INFO|WARN|DEBUG|ERROR)')

(options, args) = parser.parse_args()


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
    except exceptions.InvalidJSON as e:
        log.error('Invalid JSON Detected')
        log.error(e)
        sys.exit(1)

    # Instantiate the first actor and execute it. It should handle everything
    # from there on out.
    try:
        initial_actor = actor_utils.get_actor(config, dry=options.dry)
    except actor_exceptions.ActorException as e:
        log.error('Invalid Actor Configuration Detected: %s' % e)
        sys.exit(1)

    # Begin doing real stuff!
    if not options.dry:
        # do a dry run first, then do real one
        dry_actor = actor_utils.get_actor(config, dry=True)
        log.info('Rehearsing... Break a leg!')
        message = ''
        try:
            success = yield dry_actor.execute()
            if not success:
                message = ('Some actors broke a leg during rehearsal. Read '
                           'log output for more details.')
        except actor_exceptions.ActorException as e:
            success = False
            message = e

        if not success:
            log.critical('Dry run failed. Reason:')
            log.critical(message)
            sys.exit(2)
        else:
            log.info('Rehearsal OK! Performing!')

    yield initial_actor.execute()


def begin():
    # Set up logging before we do anything else
    utils.setup_root_logger(level=options.level)

    try:
        ioloop.IOLoop.instance().run_sync(main)
    except KeyboardInterrupt:
        log.info('CTRL-C Caught, shutting down')
    except Exception as e:
        # Skip traceback that involves site-packages.
        import traceback
        trace_lines = traceback.format_exc(e).splitlines()
        skip_next = False
        for l in trace_lines:
            if 'site-packages' in l:
                skip_next = True
                continue
            if not skip_next:
                print l
            skip_next = False

if __name__ == '__main__':
    begin()
