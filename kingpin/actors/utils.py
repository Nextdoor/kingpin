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

"""Misc methods for dealing with Actors"""

import logging

from kingpin import utils
from kingpin.actors import exceptions

log = logging.getLogger(__name__)


__author__ = 'Matt Wise <matt@nextdoor.com>'


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

    log.debug('Building Actor "%s" with args: %s' % (actor_string, config))
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

    try:
        # Try to load our local actors up first. Assume that the
        # 'kingpin.actors.' prefix was not included in the name.
        full_actor = 'kingpin.actors.%s' % actor
        ref = utils.str_to_class(full_actor)
    except expected_exceptions as e:
        log.warning('Could not import %s: %s' % (full_actor, e))
        try:
            ref = utils.str_to_class(actor)
        except expected_exceptions:
            log.critical('Could not import %s: %s' % (actor, e))
            msg = 'Unable to import "%s" as a valid Actor.' % actor
            raise exceptions.InvalidActor(msg)

    return ref
