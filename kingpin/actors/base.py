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

"""Base Actor object class"""

import logging

from tornado import gen

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


class ActorBase(object):
    """Abstract base class for Actor objects."""
    def __init__(self, desc, options):
        """Initializes the Actor.

        args:
            desc: String description of the action being executed.
            options: Dictionary of Key/Value pairs that have the options
                     for this action.
        """
        self._type = '%s.%s' % (self.__module__, self.__class__.__name__)
        self._desc = desc
        self._options = options
        log.debug('[%s] %s Initialized' % (self._desc, self._type))

    # TODO: Write an execution wrapper that logs the time it takes for
    # steps to finish. Wrap execute() with it.

    @gen.coroutine
    def execute(self):
        """Executes an actor and yields the results when its finished.

        Raises:
            gen.Return(result)
        """
        log.debug('[%s] Beginning execution' % self._desc)
        result = yield self._execute()
        log.debug('[%s] Returning result: %s' % (self._desc, result))
        raise gen.Return(result)
