"""
:mod:`kingpin.actors.exceptions`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

All common Actor exceptions
"""

from kingpin import exceptions


class ActorException(exceptions.KingpinException):
    """Base Kingpin Actor Exception"""


class RecoverableActorFailure(ActorException):
    """Base exception that allows script executions to continue on failure.

    This exception class is used to throw an error when an Actor fails, but
    it was an expected and/or acceptable failure.

    This should be used for exceptions that are somewhat normal ... for
    example, trying to delete a ServerArray thats already gone.
    """


class UnrecoverableActorFailure(ActorException):
    """Base exception for unrecoverable failures.

    This exception class should be used for critical failures that should
    always stop a set of Kingpin actors in-place, regardless of the actors
    `warn_on_failure` setting.

    Examples would be when credentials are incorrect, or an unexpected
    exception is caught and there is no known recovery point.
    """


class ActorTimedOut(RecoverableActorFailure):
    """Raised when an Actor takes too long to execute"""


class InvalidActor(UnrecoverableActorFailure):
    """Raised when an invalid Actor name was supplied"""


class InvalidOptions(UnrecoverableActorFailure):
    """Invalid option arguments passed into the Actor object.

    This can be used both for the actual options dict passed into the actor,
    as well as if a the wrong options were used when connecting to a remote
    API.
    """


class InvalidCredentials(UnrecoverableActorFailure):
    """Invalid or missing credentials required for Actor object."""


class UnparseableResponseFromEndpoint(UnrecoverableActorFailure):
    """Invalid response returned from a remote REST endpoint."""


class BadRequest(RecoverableActorFailure):
    """An action failed due to a HTTP 400 error likely due to bad input."""
