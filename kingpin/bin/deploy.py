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
import argparse
import os
import sys

from tornado import gen
from tornado import ioloop

from kingpin import utils
from kingpin.actors import exceptions as actor_exceptions
from kingpin.actors import utils as actor_utils
from kingpin.actors.misc import Macro
from kingpin.version import __version__


log = logging.getLogger(__name__)

__author__ = 'Matt Wise (matt@nextdoor.com)'


# We handle all the exceptions ourselves, so additional log statements from
# BOTO are not needed.
logging.getLogger('boto').setLevel(logging.CRITICAL)

# Initial option handler to set up the basic application environment.
parser = argparse.ArgumentParser(description='Kingpin v%s' % __version__)
parser.set_defaults(verbose=True)

# Job Configuration
parser.add_argument('-j', '--json', dest='json',
                    help='Path to JSON Deployment File')
parser.add_argument('-a', '--actor', dest='actor',
                    help='Name of an Actor to execute (overrides --json)')
parser.add_argument('-p', '--param', dest='params', action='append',
                    help='Actor Parameter to set (ie, warn_on_failure=true)')
parser.add_argument('-o', '--option', dest='options', action='append',
                    help='Actor Options to set (ie, elb_name=foobar)')
parser.add_argument('-d', '--dry', dest='dry', action='store_true',
                    help='Executes a dry run only.')

# Logging Configuration
parser.add_argument('-l', '--level', dest='level', default='info',
                    help='Set logging level (INFO|WARN|DEBUG|ERROR)')
parser.add_argument('-D', '--debug', dest='level_debug', default=False,
                    action='store_true', help='Equivalent to --level=DEBUG')
parser.add_argument('-c', '--color', dest='color', default=False,
                    action='store_true', help='Colorize the log output')

args = parser.parse_args()


def kingpin_fail(message):
    parser.print_help()
    sys.stderr.write('\nError: %s\n' % message)
    sys.exit(1)


@gen.coroutine
def main():

    env_tokens = dict(os.environ)

    # Sanity check - did the user supply both a JSON script && an individual
    # actor? If so, print the help!
    if args.json and args.actor:
        kingpin_fail('You may only specify --actor or --json, not both!')

    if args.actor:
        json_file = utils.get_script_from_args(args)
    else:
        try:
            json_file = args.json or sys.argv[1] if sys.argv else None
        except Exception as e:
            kingpin_fail(
                '%s You must specify --json or provide it as first argument.' % e)
    # Begin doing real stuff!
    if os.environ.get('SKIP_DRY', False):
        log.warn('')
        log.warn('*** You have disabled the dry run.')
        log.warn('*** Execution will begin with no expectation of success.')
        log.warn('')
    elif not args.dry:
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
        runner = Macro(desc='Kingpin',
                       options={'macro': json_file,
                                'tokens': env_tokens},
                       dry=args.dry)

        log.info('')
        log.warn('Lights, camera ... action!')
        log.info('')
        yield runner.execute()
    except actor_exceptions.ActorException as e:
        log.error('Kingpin encountered mistakes during the play.')
        log.error(e)
        sys.exit(2)


def begin():
    # Set up logging before we do anything else
    if args.level_debug:
        args.level = 'DEBUG'
    utils.setup_root_logger(level=args.level, color=args.color)

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
