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
    def __init__(self):
        """Initializes the Actor."""
        log.debug('[%s] Actor initializing...' % self.__class__.__name__)

    @gen.coroutine
    def execute(self, desc, options):
        """Executes an actor and yields the results when its finished.

        args:
            desc: String description of the action being executed.
            options: Dictionary of Key/Value pairs that have the options
                     for this action.

        raises: gen.Return
        """
        log.debug('[%s] Beginning execution...' % desc)
        result = yield self._execute(desc, options)
        raise gen.Return(result)
