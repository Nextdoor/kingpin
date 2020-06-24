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
# Copyright 2018 Nextdoor.com, Inc
"""CLI Script Runner for Kingpin."""

import argparse
import json
import logging
import os
import sys

from tornado import gen
from tornado import ioloop

from kingpin import utils
from kingpin.actors import utils as actor_utils
from kingpin.actors import exceptions as actor_exceptions
from kingpin.actors.misc import Macro
from kingpin.version import __version__


log = logging.getLogger(__name__)

__author__ = 'Matt Wise (matt@nextdoor.com)'


# We handle all the exceptions ourselves, so additional log statements from
# BOTO are not needed.
logging.getLogger('boto').setLevel(logging.CRITICAL)
logging.getLogger('botocore').setLevel(logging.CRITICAL)

# Initial option handler to set up the basic application environment.
parser = argparse.ArgumentParser(description='Kingpin v%s' % __version__)
parser.set_defaults(verbose=True)

# Job Configuration
parser.add_argument('-j', '--json', '-s', '--script', dest='script',
                    help='Path to JSON/YAML Deployment Script')
parser.add_argument('-a', '--actor', dest='actor',
                    help='Name of an Actor to execute (overrides --script)')
parser.add_argument('-E', '--explain', dest='explain', action='store_true',
                    help='Explain how an actor works. Requires --actor.',
                    default=False)
parser.add_argument('-p', '--param', dest='params', action='append',
                    help='Actor Parameter to set (ie, warn_on_failure=true)',
                    default=[])
parser.add_argument('-o', '--option', dest='options', action='append',
                    help='Actor Options to set (ie, elb_name=foobar)',
                    default=[])
parser.add_argument('-d', '--dry', dest='dry', action='store_true',
                    help='Executes a dry run only.')
parser.add_argument('--build-only', dest='build_only', action='store_true',
                    help='Compile the input JSON without executing any runs')
parser.add_argument('--orgchart', dest='orgchart',
                    help='Save the orgchart into file. Requires --build-only')

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


def get_main_actor(dry):
    env_tokens = dict(os.environ)

    # Cannot specify a script file an an actor at the same time.
    if args.script and args.actor:
        kingpin_fail('You may only specify --actor or --script, not both!')

    if args.actor:
        ActorClass = actor_utils.get_actor_class(args.actor)
        parameters = dict([i.split('=') for i in args.params])
        options = dict([i.split('=') for i in args.options])

        return ActorClass(options=options,
                          dry=dry,
                          init_tokens=env_tokens,
                          **parameters)

    # Actor not specified. Process JSON file.
    try:
        script = args.script or sys.argv[1] if sys.argv else None
    except Exception as e:
        kingpin_fail(
            '%s You must specify --script or provide it as first argument.'
            % e)

    return Macro(desc='Kingpin',
                 options={'macro': script, 'tokens': env_tokens},
                 dry=dry)


@gen.coroutine
def main():

    if args.actor and args.explain:
        ActorClass = actor_utils.get_actor_class(args.actor)
        print((ActorClass.__doc__))
        sys.exit(0)

    if args.build_only:
        try:
            actor = get_main_actor(dry=False)
        except Exception as e:
            log.critical(e)
            sys.exit(1)

        if args.orgchart:
            log.info('Creating organizational chart into %s' % args.orgchart)
            try:
                orgdata = actor.get_orgchart()
            except Exception as e:
                log.critical(e)
                sys.exit(2)

            with open(args.orgchart, 'w') as output:
                output.write(json.dumps(orgdata))

        sys.exit(0)

    # Begin doing real stuff!
    if os.environ.get('SKIP_DRY', False):
        log.warning('')
        log.warning('*** You have disabled the dry run.')
        log.warning('*** Execution will begin with no expectation of success.')
        log.warning('')
    elif not args.dry:
        log.info('Rehearsing... Break a leg!')

        try:
            dry_actor = get_main_actor(dry=True)
            yield dry_actor.execute()
        except actor_exceptions.ActorException as e:
            log.critical('Dry run failed. Reason:')
            log.critical(e)
            sys.exit(2)

        log.info('Rehearsal OK! Performing!')

    try:
        runner = get_main_actor(dry=args.dry)

        log.info('')
        log.warning('Lights, camera ... action!')
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
        sys.exit(130)  # Standard KeyboardInterrupt exit code.
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
        sys.exit(3)

if __name__ == '__main__':
    begin()
