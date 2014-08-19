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

"""RightScale Actors"""

import logging
import mock

from tornado import gen
import requests

from kingpin.actors import exceptions
from kingpin.actors.rightscale import api
from kingpin.actors.rightscale import base

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


class ServerArrayBaseActor(base.RightScaleBaseActor):

    """Abstract ServerArray Actor that provides some utility methods."""

    @gen.coroutine
    def _find_server_arrays(self, array_name,
                            raise_on='notfound',
                            allow_mock=True):
        """Find a ServerArray by name and return it.

        Args:
            array_name: String name of the ServerArray to find.
            raise_on: Either None, 'notfound' or 'found'
            allow_mock: Boolean whether or not to allow a Mock object to be
                        returned instead.

        Raises:
            gen.Return(<rightscale.Resource of Server Array>)
            api.ServerArrayException()
        """
        if raise_on == 'notfound':
            msg = 'Verifying that array "%s" exists' % array_name
        elif raise_on == 'found':
            msg = 'Verifying that array "%s" does not exist' % array_name
        elif not raise_on:
            msg = 'Searching for array named "%s"' % array_name
        else:
            raise api.ServerArrayException('Invalid "raise_on" setting.')

        self._log(logging.INFO, msg)
        array = yield self._client.find_server_arrays(array_name, exact=True)

        if not array and self._dry and allow_mock:
            self._log(logging.WARNING,
                      'Array "%s" not found -- creating a mock.' % array_name)
            array = mock.MagicMock(name=array_name)
            array.soul = {'name': '<mocked array %s>' % array_name}

        if array and raise_on == 'found':
            raise api.ServerArrayException(
                'Dest array "%s" already exists! Exiting!' % array_name)

        if not array and raise_on == 'notfound':
            raise api.ServerArrayException(
                'Array "%s" not found! Exiting!' % array_name)

        raise gen.Return(array)


class Clone(ServerArrayBaseActor):

    """Clones a RightScale Server Array."""

    required_options = ['source', 'dest']

    def __init__(self, *args, **kwargs):
        """Initializes the Actor.

        Args:
            desc: String description of the action being executed.
            options: Dictionary with the following settings:
              { 'sleep': <int of time to sleep> }
        """
        super(Clone, self).__init__(*args, **kwargs)

        self._source = self._options['source']
        self._dest = self._options['dest']

    @gen.coroutine
    def _execute(self):
        # First things first, login to RightScale asynchronously to
        # pre-populate the API attributes that are dynamically generated. This
        # is a hack, and in the future should likely turn into a smart
        # decorator.
        yield self._client.login()

        # First, find the array we're copying from.
        source_array = yield self._find_server_arrays(self._source,
                                                      allow_mock=False)

        # Sanity-check -- make sure that the destination server array doesn't
        # already exist. If it does, bail out!
        yield self._find_server_arrays(self._dest,
                                       raise_on='found',
                                       allow_mock=False)

        # Next, get the resource ID number for the source array
        source_array_id = self._client.get_res_id(source_array)

        # Now, clone the array!
        self._log(logging.INFO, 'Cloning array "%s"' %
                  source_array.soul['name'])
        if not self._dry:
            # We're really doin this!
            new_array = yield self._client.clone_server_array(source_array_id)
        else:
            # In dry run mode. Don't really clone the array, just return back
            # 'True' as if the array-clone worked.
            new_array = mock.MagicMock(name=self._dest)
            new_array.soul = {'name': '<mocked clone of %s>' % self._source}

        # Lastly, rename the array
        params = self._generate_rightscale_params(
            'server_array', {'name': self._dest})
        self._log(logging.INFO, 'Renaming array "%s" to "%s"' %
                  (new_array.soul['name'], self._dest))
        yield self._client.update_server_array(new_array, params)

        raise gen.Return(True)


class Update(ServerArrayBaseActor):

    """Patch a RightScale Server Array."""

    required_options = ['array', 'params']

    def __init__(self, *args, **kwargs):
        """Initializes the Actor.

        Args:
            desc: String description of the action being executed.
            options: Dictionary with the following example settings:
              { 'array': <server array name>,
                'params': { 'description': 'foo bar',
                            'state': 'enabled' } }
        """
        super(Update, self).__init__(*args, **kwargs)

        self._array = self._options['array']
        self._params = self._options['params']

    @gen.coroutine
    def _execute(self):
        # First things first, login to RightScale asynchronously to
        # pre-populate the API attributes that are dynamically generated. This
        # is a hack, and in the future should likely turn into a smart
        # decorator.
        yield self._client.login()

        # First, find the array we're going to be patching.
        array = yield self._find_server_arrays(self._array)

        # Now, read through our supplied parameters and generate a
        # rightscale-compatible parameter dict.
        params = self._generate_rightscale_params('server_array', self._params)
        self._log(logging.DEBUG, 'Generated RightScale params: %s' % params)

        # In dry run, just comment that we would have made the change.
        if self._dry:
            self._log(logging.WARNING,
                      'Would have updated "%s" with params: %s' %
                      (array.soul['name'], params))
            raise gen.Return(True)

        # We're really doin this!
        msg = ('Updating array "%s" with params: %s' %
               (array.soul['name'], params))
        self._log(logging.INFO, msg)
        try:
            yield self._client.update_server_array(array, params)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 422:
                msg = ('Invalid parameters supplied to patch array "%s"' %
                       self._array)
                raise exceptions.UnrecoverableActionFailure(msg)

        raise gen.Return(True)
