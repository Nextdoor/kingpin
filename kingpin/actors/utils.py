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

log = logging.getLogger(__name__)


__author__ = 'Matt Wise <matt@nextdoor.com>'


class InvalidActorException(Exception):

    """Raised when an invalid Actor name was supplied."""


def get_actor_class(actor):
    """Returns a Class Reference to an Actor by string name.

    Args:
        actor: String name of the actor to find.

    Returns:
        <Class Ref to Actor>
    """
    try:
        # Try to load our local actors up first. Assume that the
        # 'kingpin.actors.' prefix was not included in the name.
        full_actor = 'kingpin.actors.%s' % actor
        ref = utils.str_to_class(full_actor)
    except (ImportError, TypeError):
        try:
            ref = utils.str_to_class(actor)
        except (ImportError, TypeError):
            msg = 'Unable to convert "%s" to a valid Actor class name.' % actor
            raise InvalidActorException(msg)

    return ref
