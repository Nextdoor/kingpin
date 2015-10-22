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

"""
:mod:`kingpin.actors.rightscale.base`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The RightScale Actors allow you to interact with resources inside your
Rightscale account. These actors all support dry runs properly, but each
actor has its own caveats with ``dry=True``. Please read the instructions
below for using each actor.

**Required Environment Variables**

:RIGHTSCALE_TOKEN:
  RightScale API Refresh Token
  (from the *Account Settings/API Credentials* page)

:RIGHTSCALE_ENDPOINT:
  Your account-specific API Endpoint
  (defaults to https://my.rightscale.com)
"""

from random import randint
import collections
import logging
import os

from tornado import gen
import mock

from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.actors.rightscale import api

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


TOKEN = os.getenv('RIGHTSCALE_TOKEN', None)
ENDPOINT = os.getenv('RIGHTSCALE_ENDPOINT', 'https://my.rightscale.com')


class ArrayNotFound(exceptions.RecoverableActorFailure):

    """Raised when a ServerArray could not be found."""


class ArrayAlreadyExists(exceptions.RecoverableActorFailure):

    """Raised when a ServerArray already exists by a given name."""


class RightScaleBaseActor(base.BaseActor):

    """Abstract class for creating RightScale cloud actors."""

    def __init__(self, *args, **kwargs):
        """Initializes the Actor."""
        super(RightScaleBaseActor, self).__init__(*args, **kwargs)

        if not TOKEN:
            raise exceptions.InvalidCredentials(
                'Missing the "RIGHTSCALE_TOKEN" environment variable.')

        self._client = api.RightScale(token=TOKEN, endpoint=ENDPOINT)

    @gen.coroutine
    def _find_server_arrays(self, array_name,
                            raise_on='notfound',
                            allow_mock=True,
                            exact=True):
        """Find a ServerArray by name and return it.

        Args:
            array_name: String name of the ServerArray to find.
            raise_on: Either None, 'notfound' or 'found'
            allow_mock: Boolean whether or not to allow a Mock object to be
                        returned instead.
            exact: Boolean whether or not to allow multiple arrays to be
                   returned.

        Raises:
            gen.Return(<rightscale.Resource of Server Array>)
            ArrayNotFound()
            ArrayAlreadyExists()
        """
        if raise_on == 'notfound':
            msg = 'Verifying that array "%s" exists' % array_name
        elif raise_on == 'found':
            msg = 'Verifying that array "%s" does not exist' % array_name
        elif not raise_on:
            msg = 'Searching for array named "%s"' % array_name
        else:
            raise exceptions.UnrecoverableActorFailure(
                'Invalid "raise_on" setting in actor code.')

        self.log.debug(msg)
        array = yield self._client.find_server_arrays(array_name, exact=exact)

        if not array and self._dry and allow_mock:
            # Create a fake ServerArray object thats mocked up to help with
            # execution of the rest of the code.
            self.log.info('Array "%s" not found -- creating a mock.' %
                          array_name)
            array = mock.MagicMock(name=array_name)
            # Give the mock a real identity and give it valid elasticity
            # parameters so the Launch() actor can behave properly.
            array.soul = {
                # Used elsewhere to know whether we're working on a mock
                'fake': True,

                # Fake out common server array object properties
                'name': '<mocked array %s>' % array_name,
                'elasticity_params': {'bounds': {'min_count': 4}}
            }
            array.self.path = '/fake/array/%s' % randint(10000, 20000)
            array.self.show.return_value = array

        if array and raise_on == 'found':
            raise ArrayAlreadyExists('Array "%s" already exists!' % array_name)

        if not array and raise_on == 'notfound':
            raise ArrayNotFound('Array "%s" not found!' % array_name)

        # Quick note. If many arrays were returned, lets make sure we throw a
        # note to the user so they know whats going on.
        if isinstance(array, list):
            for a in array:
                self.log.info('Matching array found: %s' % a.soul['name'])

        raise gen.Return(array)

    def _generate_rightscale_params(self, prefix, params):
        """Utility function for creating RightScale-style parameters.

        RightScale takes inputs in the form of a hash of key/value pairs, but
        these pairs are in a strange pseudo-dict form. This method takes a
        standard hash and converts it into a rightscale-compatible form.

        For example, take this dict:

            {'name': 'unittest-name',
             'bounds': { 'min_count': 3}

        We return:

            [ ('server_array[name]', 'unittest-name'),
              ('server_array[bounds][min_count]', '3) ]

        For more examples, see our unit tests.

        Args:
            prefix: The key-prefix to use (ie, 'server_array')
            params: The dictionary to squash

        Returns:
            A list of tuples of key/value pairs.
        """
        if not type(params) == dict:
            raise exceptions.InvalidOptions(
                'Parameters passed in must be in the form of a dict.')

        # Nested loop that compresses a multi level dictinary into a flat
        # array of key=value strings.
        def flatten(d, parent_key=prefix, sep='_'):
            items = []

            if isinstance(d, collections.MutableMapping):
                # If a dict is passed in, break it into its items and
                # then iterate over them.
                for k, v in d.items():
                    new_key = parent_key + '[' + k + ']' if parent_key else k
                    items.extend(flatten(v, new_key))
            elif isinstance(d, list):
                # If an array was passed in, then iterate over the array
                new_key = parent_key + '[]' if parent_key else k
                for item in d:
                    items.extend(flatten(item, new_key))
            else:
                items.append((parent_key, d))

            return items

        return sorted(flatten(params))
