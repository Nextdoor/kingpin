
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

"""Group Actors Together into Stages"""

import logging

from tornado import gen

from kingpin.actors import base
from kingpin.actors import utils

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


class BaseGroupActor(base.BaseActor):

    """Group together a series of other Actors

    'acts' option: [ <list of sub-actors to execute> ]

    """

    all_options = {
        'acts': (list, None, "Array of actor definitions.")
    }

    def __init__(self, *args, **kwargs):
        """Initializes all of the sub actors.

        By actually initializing all of the Actors supplied to us during the
        __init__, we effectively do a full instantiation of every Actor defined
        in the supplied JSON all at once and upfront long before we try to
        execute any code. This greatly increases our chances of catching JSON
        errors because every single object is pre-initialized before we ever
        begin executing any of our steps.
        """
        super(BaseGroupActor, self).__init__(*args, **kwargs)

        # Pre-initialize all of our actions!
        self._actions = self._build_actions()

    def _build_actions(self):
        """Build up all of the actors we need to execute.

        Builds a list of actors to execute and returns the list. The list can
        then either be yielded as a whole (for an async operation), or
        individually (for a synchronous operation).

        Returns:
            A list of references to <actor objects>.
        """
        actions = []
        for act in self.option('acts'):
            actions.append(utils.get_actor(act, dry=self._dry))
        return actions

    @gen.coroutine
    def _execute(self):
        """Executes the actions configured, and returns.

        Note: Expects the sub-class to implement self._run_actions()

        If a 'False' is found anywhere in the actions, this returns
        False. Otherwise it returns True to indicate that all Actors
        finished successfully.
        """
        self.log.info('Beginning %s actions' % len(self._actions))
        ret = yield self._run_actions()
        raise gen.Return(all(ret))


class Sync(BaseGroupActor):

    """Synchronously iterates over a series of Actors"""

    @gen.coroutine
    def _run_actions(self):
        """Synchronously executes all of the Actor.execute() methods.

        If any one actor fails, we prevent execution of the rest of the actors
        and return the list of gathered return values.

        raises:
            gen.Return([ <list of return values> ])
        """
        returns = []
        for act in self._actions:
            self.log.debug('Beginning "%s"..' % act._desc)
            ret = yield act.execute()
            self.log.debug('Finished "%s", success?.. %s' % (act._desc, ret))
            returns.append(ret)

            # When an actor fails, it returns False. If we fail any actor, we
            # bail out and do not proceed with any futher acts.
            if not ret:
                break

        raise gen.Return(returns)


class Async(BaseGroupActor):

    """Asynchronously executes all Actors at once"""

    @gen.coroutine
    def _run_actions(self):
        """Asynchronously executes all of the Actor.execute() methods.

        All actors execute asynchronously, so we don't bother checking whether
        they've failed or not here. The BaseGroupActor will return a True/False
        based on whether or not all actors succeeded (True) or if one-or-more
        failed (False).
        """
        executions = []
        for act in self._actions:
            executions.append(act.execute())
        ret = yield executions
        raise gen.Return(ret)
