"""
:mod:`kingpin.actors.utils`
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Misc methods for dealing with Actors.
"""

import logging
import time

from kingpin import utils
from kingpin.actors import exceptions

log = logging.getLogger(__name__)


__author__ = "Matt Wise <matt@nextdoor.com>"


def dry(dry_message):
    """Async-compatible decorator to dry-run a method.

    .. note::

        This must act on a :py:mod:`~kingpin.actors.base.BaseActor` object.

    Args:
        dry_message: The message to print out instead of doing the actual
        function call. This string is passed through format(kwargs), so any
        variables you'd like can be substituted as long as they're passed to
        the method being wrapped.
    """

    def _skip_on_dry(f):
        async def wrapper(self, *args, **kwargs):
            # _Always_ compile the message we'd use in the event of a Dry run.
            # This ensures that our test cases catch any time invalid **kwargs
            # are passed in.
            msg = dry_message.format(*args, **kwargs)

            if self._dry:
                self.log.warning(msg)
                return
            return await f(self, *args, **kwargs)

        return wrapper

    return _skip_on_dry


def timer(f):
    """Async-compatible function timer.

    Records statistics about how long a given function took, and logs them
    out in debug statements. Used primarily for tracking Actor execute()
    methods, but can be used elsewhere as well.

    .. note::

        This must act on a :py:mod:`~kingpin.actors.base.BaseActor` object.
    """

    async def _wrap_in_timer(self, *args, **kwargs):
        start_time = time.time()
        ret = await f(self, *args, **kwargs)
        exec_time = f"{time.time() - start_time:.2f}"
        self.log.debug(f"{self._type}.{f.__name__}() execution time: {exec_time}s")
        return ret

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
    actor_string = config.pop("actor")

    # Create a copy of the config dict, but strip out the tokens. They likely
    # contain credentials! This is used purely for this debug message below.
    #
    # Known actors that do this are misc.Macro, group.Sync, group.Async
    clean_config = config.copy()
    clean_config["init_tokens"] = "<hidden>"

    log.debug(f'Building Actor "{actor_string}" with args: {clean_config}')
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
    for prefix in ["kingpin.actors.", "", "actors."]:
        full_actor = prefix + actor
        try:
            return utils.str_to_class(full_actor)
        except expected_exceptions as e:
            log.debug(f'Tried importing "{full_actor}" but failed: {e}')

    msg = f'Unable to import "{actor}" as a valid Actor.'
    raise exceptions.InvalidActor(msg)
