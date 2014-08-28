
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

"""Meta-Actors"""

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

    required_options = ['acts']

    def _get_actor(self, config):
        """Returns an initialized Actor object.

        Args:
            config: A dictionary of configuration data that conforms to our v1
                    schema in kingpin.schema. Looks like this:

                    {'actor': <string name of actor>
                     'options': <dict of options to pass to actor>
                     'desc': <string description of actor>}

        Returns:
            <actor object>
        """
        # Get the name of the actor, and pull it out of the config because its
        # not a valid kwarg for an Actor object.
        actor_string = config.pop('actor')

        self._log(logging.DEBUG,
                  'Building Actor "%s" with args: %s' % (actor_string, config))
        return utils.get_actor_class(actor_string)(dry=self._dry, **config)

    def _build_actions(self):
        """Build up all of the actors we need to execute.

        Builds a list of actors to execute and returns the list. The list can
        then either be yielded as a whole (for an async operation), or
        individually (for a synchronous operation).

        Returns:
            A list of references to <actor objects>.
        """
        actions = []
        for act in self._options['acts']:
            actions.append(self._get_actor(act))
        return actions

    @gen.coroutine
    def _execute(self):
        """Executes the actions configured, and returns.

        Note: Expects the sub-class to implement self._run_actions()

        If a 'False' is found anywhere in the actions, this returns
        False. Otherwise it returns True to indicate that all Actors
        finished successfully.
        """
        ret = yield self._run_actions()
        raise gen.Return(all(ret))


class Sync(BaseGroupActor):

    """Synchronously iterates over a series of Actors"""

    @gen.coroutine
    def _run_actions(self):
        """Synchronously executes all of the Actor.execute() methods."""
        actions = self._build_actions()
        returns = []
        for act in actions:
            self._log(logging.INFO,
                      'Beginning "%s"..' % act._desc)
            ret = yield act.execute()
            self._log(logging.INFO,
                      'Finished "%s", success?.. %s' % (act._desc, ret))
            returns.append(ret)
        raise gen.Return(returns)


class Async(BaseGroupActor):

    """Asynchronously executes all Actors at once"""

    @gen.coroutine
    def _run_actions(self):
        """Asynchronously executes all of the Actor.execute() methods."""
        actions = self._build_actions()
        executions = []
        for act in actions:
            executions.append(act.execute())
        ret = yield executions
        raise gen.Return(ret)
