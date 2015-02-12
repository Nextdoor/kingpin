#!/usr/bin/env python
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
"""CLI Script Runner for Kingpin."""

import logging
import optparse
import os
import sys

from tornado import gen
from tornado import ioloop

from kingpin import utils
from kingpin.actors import exceptions as actor_exceptions
from kingpin.actors.misc import Macro
from kingpin.version import __version__


log = logging.getLogger(__name__)

__author__ = 'Matt Wise (matt@nextdoor.com)'


# We handle all the exceptions ourselves, so additional log statements from
# BOTO are not needed.
logging.getLogger('boto').setLevel(logging.CRITICAL)

# Initial option handler to set up the basic application environment.
usage = 'usage: %prog [json file] <options>'
parser = optparse.OptionParser(usage=usage, version=__version__,
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
parser.add_option('-c', '--color', dest='color', default=False,
                  action='store_true', help='Colorize the log output')

(options, args) = parser.parse_args()


def kingpin_fail(message):
    parser.print_help()
    sys.stderr.write('\nError: %s\n' % message)
    sys.exit(1)


@gen.coroutine
def main():

    env_tokens = dict(os.environ)

    try:
        json_file = options.json or sys.argv[1] if sys.argv else None
    except Exception as e:
        kingpin_fail(
            '%s You must specify --json or provide it as first argument.' % e)

    # Begin doing real stuff!
    if not options.dry:
        log.info('Rehearsing... Break a leg!')
        try:
            dry_actor = Macro(desc='Kingpin',
                              options={'macro': json_file,
                                       'tokens': env_tokens},
                              dry=True)
            yield dry_actor.execute()
        except actor_exceptions.ActorException as e:
            log.critical('Dry run failed. Reason:')
            log.critical(e)
            sys.exit(2)
        else:
            log.info('Rehearsal OK! Performing!')

    try:
        log.info('Lights, camera ... action!')
        runner = Macro(desc='Kingpin',
                       options={'macro': json_file,
                                'tokens': env_tokens},
                       dry=options.dry)
        yield runner.execute()
    except actor_exceptions.ActorException as e:
        log.error('Kingpin encountered mistakes during the play.')
        log.error(e)
        sys.exit(2)


def begin():
    # Set up logging before we do anything else
    utils.setup_root_logger(level=options.level, color=options.color)

    try:
        ioloop.IOLoop.instance().run_sync(main)
    except KeyboardInterrupt:
        log.info('CTRL-C Caught, shutting down')
    except Exception as e:
        # Skip traceback that involves tornado's libraries.
        import traceback
        trace_lines = traceback.format_exc(e).splitlines()
        skip_next = False
        for l in trace_lines:
            if 'tornado' in l:
                skip_next = True
                continue
            if not skip_next:
                print(l)
            skip_next = False

if __name__ == '__main__':
    begin()
