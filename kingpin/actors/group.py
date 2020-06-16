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
:mod:`kingpin.actors.group`
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Group a series of other `BaseActor` into either synchronous
or asynchronous stages.
"""

import logging

from tornado import gen
import demjson

from kingpin import utils as kp_utils
from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.actors import utils
from kingpin.constants import REQUIRED

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


class BaseGroupActor(base.BaseActor):

    """Group together a series of other `kingpin.actors.base.BaseActor` objects

    :acts:
      [ <list of `kingpin.actors.base.BaseActor` objects  to execute> ]

    """

    # By default, group actors have no timeout. We rely on the individual
    # actors to expire on their own. This is, of course, overrideable in the
    # JSON.
    default_timeout = None

    all_options = {
        'contexts': ((dict, str, list), [], "List of contextual hashes."),
        'acts': (list, REQUIRED, "Array of actor definitions.")
    }

    # Override the BaseActor strict_init_context setting. Since there may be
    # nested-groups that have their own context tokens, we do not require
    # that all of the {KEY}'s inside of the self._options dict are filled in
    # the moment that this actor is instantiated.
    strict_init_context = False

    # Do not remove remove escape sequence from escaped tokens. This will be
    # done later by another actor. Otherwise we risk remove the escapes and
    # failing because the token isn't found by a sub actor.
    remove_escape_sequence = False

    def __init__(self, *args, **kwargs):
        """Initializes all of the sub actors.

        By actually initializing all of the Actors supplied to us during the
        __init__, we effectively do a full instantiation of every Actor defined
        in the supplied JSON all at once and upfront long before we try to
        execute any code. This greatly increases our chances of catching JSON
        errors because every single object is pre-initialized before we ever
        begin executing any of our steps.

        *Note about init_tokens:*
          The group.BaseActor and misc.Macro actors support the concept of
          externally supplied data (usually os.environ) being used as available
          tokens for %TOKEN% parsing when reading JSON/YAML scripts. By passing
          this data between these three actors, we are able to allow nested
          token passing.

          See `Token-replacement <basicuse.html#token-replacement>` for more
          info.
        """
        super(BaseGroupActor, self).__init__(*args, **kwargs)

        # DEPRECATE IN v0.5.0
        if type(self.option('contexts')) == dict:
            try:
                filename = self.option('contexts').get('file', '')
                open(filename)
            except IOError as e:
                self.log.error('Option `contexts` must have valid `file`. '
                               'Received: %s' % filename)
                raise exceptions.InvalidOptions(e)
        # END DEPRECATION

        # Pre-initialize all of our actions!
        self._actions = self._build_actions()

    def get_orgchart(self, parent=''):
        """Generate an orgchart for all the `acts` specified."""

        ret = super(BaseGroupActor, self).get_orgchart(parent=parent)
        group_id = str(id(self))
        for act in self._actions:
            ret = ret + act.get_orgchart(parent=group_id)

        return ret

    def _build_actions(self):
        """Builds either a single set of actions, or multiple sets.

        If no 'contexts' were passed in, then we simply build the actors that
        are defined in the 'acts' option for the group.

        If any 'contexts' were passed in, then this method will create as many
        groups of actions as there are in the list of contexts. For each dict
        in the 'contexts' list, a new group of actors is created with that
        information.

        Note: Because groups may contain nested group actors, any options
        passed into this actors 'init_context' are also passed into the
        actors that we're intantiating.
        """
        contexts = self.option('contexts')
        if not contexts:
            return self._build_action_group(self._init_context)

        # If the data passed into the 'contexts' is a list of dicts, we take it
        # as is and do nothing to it.
        if type(contexts) == list:
            context_data = self.option('contexts')
        # DEPRECATE IN v0.5.0
        elif type(contexts) == dict:
            context_string = open(contexts['file']).read()
            context_string = kp_utils.populate_with_tokens(
                string=context_string,
                tokens=contexts.get('tokens', {}),
                strict=True)
            context_data = demjson.decode(context_string)
        # END DEPRECATION

        # If the data passed in is a string, it must be a pointer to a file
        # with contexts in it. We read that file, and we parse it for any
        # missing tokens. We use the "init tokens" that made it into this actor
        # as available token substitutions.
        elif isinstance(contexts, str):
            context_data = kp_utils.convert_script_to_dict(
                contexts, self._init_tokens)

        actions = []
        for context in context_data:
            combined_context = dict(list(self._init_context.items()) +
                                    list(context.items()))
            self.log.debug('Inherited context %s' %
                           list(self._init_context.items()))
            self.log.debug('Specified context %s' % list(context.items()))
            self.log.debug('Building acts with parameters: %s' %
                           combined_context)
            for action in self._build_action_group(context=combined_context):
                actions.append(action)

        return actions

    def _build_action_group(self, context=None):
        """Build up all of the actors we need to execute.

        Builds a list of actors to execute and returns the list. The list can
        then either be yielded as a whole (for an async operation), or
        individually (for a synchronous operation).

        Returns:
            A list of references to <actor objects>.
        """
        actions = []
        self.log.debug('Building %s actors' % len(self.option('acts')))
        for act in self.option('acts'):
            act['init_context'] = context.copy()
            act['init_tokens'] = self._init_tokens.copy()
            actor = utils.get_actor(act, dry=self._dry)
            actions.append(actor)
            self.log.debug('Actor %s built' % actor)
        return actions

    def _get_exc_type(self, exc_list):
        """Return Unrecoverable exception if at least one is in exc_list.

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

    """Execute a series of `kingpin.actors.base.BaseActor` synchronously.

    Groups together a series of Actors and executes them synchronously
    in the order that they were defined.

    **Options**

    :acts:
      An array of individual Actor definitions.

    :contexts:

      This variable can be one of two formats:

      * A list of dictionaries with *contextual tokens* to pass into the actors
        at instantiation time. If the list has more than one element, then
        every actor defined in ``acts`` will be instantiated once for each item
        in the ``contexts`` list.
      * A string that points to a file with a list of contexts, just like the
        above dictionary.
      * (_Deprecation warning, this is going away in v0.4.0. Use the 'str'
        method above!_) A dictionary of ``file`` and ``tokens``. The file
        should be a relative path with data formatted same as stated above. The
        tokens need to be the same format as a Macro actor: a dictionary
        passing token data to be used.


    **Timeouts**

    Timeouts are disabled specifically in this actor. The sub-actors can still
    raise their own `kingpin.actors.exceptions.ActorTimedOut` exceptions, but
    since the group actors run an arbitrary number of sub actors, we have
    chosen to not have this actor specifically raise its own
    `kingpin.actors.exceptions.ActorTimedOut` exception unless the user sets
    the ``timeout`` setting.

    **Examples**

    Creates two arrays ... but sleeps 60 seconds between the two, then
    does not sleep at all after the last one:

    .. code-block:: json

       { "desc": "Clone, then sleep ... then clone, then sleep shorter...",
         "actor": "group.Sync",
         "options": {
           "contexts": [
             { "ARRAY": "First", "SLEEP": "60", },
             { "ARRAY": "Second", "SLEEP": "0", }
           ],
           "acts": [
             { "desc": "do something",
               "actor": "server_array.Clone",
               "options": {
                 "source": "template",
                 "dest": "{ARRAY}"
               }
             },
             { "desc": "sleep",
               "actor": "misc.Sleep",
               "options": {
                 "sleep": "{SLEEP}",
               }
             }
           ]
         }
       }

    Alternatively if no `contexts` are needed you can use the `array` syntax.

    .. code-block:: json

       [
         {
           "actor": "server_array.Clone",
           "options": {
             "source": "template",
             "dest": "%ARRAY%"
           }
         },
         {
           "actor": "misc.Sleep",
           "options": { "sleep": 30 }
         }
       ]

    **Dry Mode**

    Passes on the Dry mode setting to the acts that are called. Does **not**
    stop execution when one of the acts fails. Instead Group actor will finish
    all acts with warnings, and raise an error at the end of execution.

    This provides the user with an insight to all the errors that are possible
    to encounter, rather than abort and quit on the first one.

    **Failure**

    In the event that an act fails, this actor will return the failure
    immediately.  Because the acts are executed in-order of definition, the
    failure will prevent any further acts from executing.

    The behavior is different in the dry run (read above.)
    """

    @gen.coroutine
    def _run_actions(self):
        """Synchronously executes all of the Actor.execute() methods.

        If any one actor fails, we prevent execution of the rest of the actors.
        During a dry run - all acts are executed, and a warning is displayed.

        raises:
            In dry run - worst of all the raised errors.
            In real run - the first of the exceptions.
        """

        errors = []

        for act in self._actions:
            self.log.debug('Beginning "%s"..' % act._desc)
            try:
                yield act.execute()
            except exceptions.ActorException as e:
                if self._dry:
                    self.log.error('%s failed: %s' % (act._desc, str(e)))
                    self.log.warning('Continuing since this is a dry run.')
                    errors.append(e)
                else:
                    self.log.error('Aborting sequential execution because '
                                   '"%s" failed' % act._desc)
                    raise

        if errors:
            ExcType = self._get_exc_type(errors)
            raise ExcType('Exceptions raised by %s of %s actors in "%s".' % (
                          len(errors), len(self._actions), self._desc))


class Async(BaseGroupActor):

    """Execute several `kingpin.actors.base.BaseActor` objects asynchronously.

    Groups together a series of Actors and executes them asynchronously -
    waiting until all of them finish before returning.

    **Options**

    :concurrency:
      Max number of concurrent executions. This will fire off N executions
      in parallel, and continue with the remained as soon as the first
      execution is done. This is faster than creating N Sync executions.

    :acts:
      An array of individual Actor definitions.

    :contexts:

      This variable can be one of two formats:

      * A list of dictionaries with *contextual tokens* to pass into the actors
        at instantiation time. If the list has more than one element, then
        every actor defined in ``acts`` will be instantiated once for each item
        in the ``contexts`` list.
      * A dictionary of ``file`` and ``tokens``. The file should be a relative
        path with data formatted same as stated above. The tokens need to be
        the same format as a Macro actor: a dictionary passing token data to be
        used.

    **Timeouts**

    Timeouts are disabled specifically in this actor. The sub-actors can still
    raise their own `kingpin.actors.exceptions.ActorTimedOut` exceptions, but
    since the group actors run an arbitrary number of sub actors, we have
    chosen to not have this actor specifically raise its own
    `kingpin.actors.exceptions.ActorTimedOut` exception unless the user sets
    the ``timeout`` setting.

    **Examples**

    Clone two arrays quickly.

    .. code-block:: json

       { "desc": "Clone two arrays",
         "actor": "group.Async",
         "options": {
           "contexts": [
             { "ARRAY": "NewArray1" },
             { "ARRAY": "NewArray2" }
           ],
           "acts": [
             { "desc": "do something",
               "actor": "server_array.Clone",
               "options": {
                 "source": "template",
                 "dest": "{ARRAY}",
               }
             }
           ]
         }
       }

    **Dry Mode**

    Passes on the Dry mode setting to the sub-actors that are called.

    **Failure**

    In the event that one or more ``acts`` fail in this group, the entire group
    acts will return a failure to Kingpin. Because multiple actors are
    executing all at the same time, the all of these actors will be allowed to
    finish before the failure is returned.
    """

    all_options = {
        'concurrency': (int, 0, "Max number of concurrent executions."),
        'contexts': ((dict, str, list), [], "List of contextual hashes."),
        'acts': (list, REQUIRED, "Array of actor definitions.")
    }

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
        tasks = []

        if self.option('concurrency'):
            self.log.info('Concurrency set to %s' % self.option('concurrency'))

        for act in self._actions:
            tasks.append(act.execute())

            if not self.option('concurrency'):
                # No concurrency limit - continue the loop without checks.
                continue

            running_tasks = len([t for t in tasks if not t.done()])

            if running_tasks < self.option('concurrency'):
                # We can queue more tasks, continue the loop to add one more.
                continue

            self.log.debug('Concurrency saturated. Waiting...')
            while running_tasks >= self.option('concurrency'):
                yield gen.moment
                running_tasks = len([t for t in tasks if not t.done()])

            self.log.debug('Concurrency desaturated: %s<%s. Continuing.' % (
                running_tasks, self.option('concurrency')))

        # Now that we've fired them off, we walk through them one-by-one and
        # check on their status. If they've raised an exception, we catch it
        # and log it into a list for further processing.
        errors = []
        for t in tasks:
            try:
                yield t
            except exceptions.ActorException as e:
                errors.append(e)

        # Now, if there are exceptions in the list, we generate the appropriate
        # exception type (recoverable vs unrecoverable), and raise it up the
        # stack. The individual exceptions are swallowed here, but thats OK
        # because the BaseActor for each of the acts that failed has already
        # handled printing out the log message with the failure.
        if errors:
            ExcType = self._get_exc_type(errors)
            raise ExcType('Exceptions raised by %s of %s actors in "%s".' % (
                          len(errors), len(self._actions), self._desc))
