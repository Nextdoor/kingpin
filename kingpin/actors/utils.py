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

"""
:mod:`kingpin.actors.utils`
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Misc methods for dealing with Actors.
"""

import logging
import time

from tornado import gen

from kingpin import utils
from kingpin.actors import exceptions

log = logging.getLogger(__name__)


__author__ = 'Matt Wise <matt@nextdoor.com>'


def dry(dry_message):
    """Coroutine-compatible decorator to dry-run a method.

    Note: this must act on a :py:mod:`~kingpin.actors.base.BaseActor` object.

    Example usage as decorator:

        >>> @gen.coroutine
        ... @dry('Would have done that {thing}')
        ... def do_thing(self, thing):
        ...     yield api.do_thing(thing)
        ...
        >>> yield do_thing(thing="yeah man, that thing")

    Args:
        dry_message: The message to print out instead of doing the actual
        function call. This string is passed through format(kwargs), so any
        variables you'd like can be substituted as long as they're passed to
        the method being wrapped.
    """
    # TODO: Bring these back when we have log.trace
    # log.debug('Creating _skip_on_dry decorator with "%s"' % dry_message)

    def _skip_on_dry(f):
        # TODO: Bring these back when we have log.trace
        # log.debug('Decorating function "%s" with _skip_on_dry' % f)

        def wrapper(self, *args, **kwargs):
            # _Always_ compile the message we'd use in the event of a Dry run.
            # This ensures that our test cases catch any time invalid **kwargs
            # are passed in.
            msg = dry_message.format(*args, **kwargs)

            if self._dry:
                self.log.warning(msg)
                raise gen.Return()
            ret = yield gen.coroutine(f)(self, *args, **kwargs)
            raise gen.Return(ret)

        return wrapper
    return _skip_on_dry


def timer(f):
    """Coroutine-compatible function timer.

    Records statistics about how long a given function took, and logs them
    out in debug statements. Used primarily for tracking Actor execute()
    methods, but can be used elsewhere as well.

    Note: this must act on a :py:mod:`~kingpin.actors.base.BaseActor` object.

    Example usage:
        >>> @gen.coroutine
        ... @timer()
        ... def execute(self):
        ...     raise gen.Return()
    """

    def _wrap_in_timer(self, *args, **kwargs):
        # Log the start time
        start_time = time.time()

        # Begin the execution
        ret = yield gen.coroutine(f)(self, *args, **kwargs)

        # Log the finished execution time
        exec_time = "%.2f" % (time.time() - start_time)
        self.log.debug('%s.%s() execution time: %ss' %
                       (self._type, f.__name__, exec_time))

        raise gen.Return(ret)
    return _wrap_in_timer


def get_actor(config, dry):
    """Returns an initialized Actor object.

    Args:
        config: A dictionary of configuration data that conforms to our v1
                schema in kingpin.schema. Looks like this:

                {
                 'desc': <string description of actor>,
                 'actor': <string name of actor>
                 'options': <dict of options to pass to actor>
                 'warn_on_failure': <bool>
                 'condition': <string or bool>
                 }

        dry: Boolean whether or not in Dry mode
        warn_on_failure: Boolean

    Returns:
        <actor object>
    """
    # Copy the supplied dict before we modify it below
    config = dict(config)

    # Get the name of the actor, and pull it out of the config because its
    # not a valid kwarg for an Actor object.
    actor_string = config.pop('actor')

    # Create a copy of the config dict, but strip out the tokens. They likely
    # contain credentials! This is used purely for this debug message below.
    #
    # Known actors that do this are misc.Macro, group.Sync, group.Async
    clean_config = config.copy()
    clean_config['init_tokens'] = '<hidden>'

    log.debug('Building Actor "%s" with args: %s' %
              (actor_string, clean_config))
    ActorClass = get_actor_class(actor_string)
    return ActorClass(dry=dry, **config)


def get_actor_class(actor):
    """Returns a Class Reference to an Actor by string name.

    Args:
        actor: String name of the actor to find.

    Returns:
        <Class Ref to Actor>
    """
    expected_exceptions = (AttributeError, ImportError, TypeError)

    # Try to load our local actors up first. Assume that the
    # 'kingpin.actors.' prefix was not included in the name.
    for prefix in ['kingpin.actors.', '', 'actors.']:
        full_actor = prefix + actor
        try:
            return utils.str_to_class(full_actor)
        except expected_exceptions as e:
            log.debug('Tried importing "%s" but failed: %s' % (full_actor, e))

    msg = 'Unable to import "%s" as a valid Actor.' % actor
    raise exceptions.InvalidActor(msg)
