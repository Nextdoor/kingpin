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

from kingpin import exceptions


class ActorException(exceptions.KingpinException):

    """Base Kingpin Actor Exception"""


class InvalidActor(ActorException):

    """Raised when an invalid Actor name was supplied"""


class InvalidOptions(ActorException):

    """Invalid option arguments passed into the Actor object."""


class InvalidCredentials(ActorException):

    """Invalid or missing credentials required for Actor object."""


class UnparseableResponseFromEndpoint(ActorException):

    """Invalid response returned from a remote REST endpoint."""


class UnrecoverableActionFailure(ActorException):

    """An action failed, and is unrecoverable or retryable."""
