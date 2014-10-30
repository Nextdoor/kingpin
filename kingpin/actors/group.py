
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
from kingpin.actors import exceptions
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

        If an actor execution fails in _run_actions(), then that exception is
        raised up the stack.
        """
        self.log.info('Beginning %s actions' % len(self._actions))
        yield self._run_actions()
        raise gen.Return()


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
        for act in self._actions:
            self.log.debug('Beginning "%s"..' % act._desc)
            try:
                yield act.execute()
            except exceptions.ActorException:
                self.log.error('Act "%s" failed' % act._desc)
                raise

        raise gen.Return()


class Async(BaseGroupActor):

    """Asynchronously executes all Actors at once"""

    def _get_exc_type(self, exc_list):
        """Returns either a Recoverable or UnrecoverableActorFailure obj.

        Takes in a list of exceptions, and returns either a
        RecoverableActorFailure or an UnrecoverableActorFailure based on the
        exceptions that were passed in.

        Args:
            exc_list: List of Exception objects

        Returns:
            RecoverableActorFailure or UnrecoverableActorFailure
        """
        # Start by assuming we're going to be a RecoverableActorFailure
        wrapper_base = exceptions.RecoverableActorFailure
        for exc in exc_list:
            if isinstance(exc, exceptions.UnrecoverableActorFailure):
                wrapper_base = exceptions.UnrecoverableActorFailure
        return wrapper_base

    @gen.coroutine
    def _run_actions(self):
        """Asynchronously executes all of the Actor.execute() methods.

        All actors execute asynchronously, so we don't bother checking whether
        they've failed or not here. The BaseGroupActor will return a True/False
        based on whether or not all actors succeeded (True) or if one-or-more
        failed (False).
        """

        # This is an interesting tornado-ism. Here we generate and fire off
        # each of the acts asynchronously into the IOLoop, and we record
        # references to those tasks. However, we don't yield (wait) on them to
        # finish.
        actor_map = []
        for act in self._actions:
            actor_map.append((act, act.execute()))

        # Now that we've fired them off, we walk through them one-by-one and
        # check on their status. If they've raised an exception, we catch it
        # and log it into a list for further processing.
        to_raise = []
        for (actor, exe) in actor_map:
            try:
                yield exe
            except exceptions.ActorException as e:
                to_raise.append(e)

        # Now, if there are exceptions in the list, we generate the appropriate
        # exception type (recoverable vs unrecoverable), and raise it up the
        # stack. The individual exceptions are swallowed here, but thats OK
        # because the BaseActor for each of the acts that failed has already
        # handled printing out the log message with the failure.
        if to_raise:
            raise self._get_exc_type(to_raise)(
                ('Exceptions raised by %s actors in the group.' %
                 len(to_raise)))
