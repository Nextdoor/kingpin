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
from kingpin.actors.rightscale import api
from kingpin.actors.rightscale import base

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


class Clone(base.RightScaleBaseActor):
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

        # First, find the array we're copying from. If this fails, even in
        # dry-mode, we exit out because the template array needs to be there!
        self._log(logging.INFO, 'Finding template array "%s"' % self._source)
        source_array = yield self._client.find_server_arrays(
            self._source, exact=True)
        if not source_array:
            raise api.ServerArrayException(
                'Could not find server template to clone.')

        # Sanity-check -- make sure that the destination server array doesn't
        # already exist. If it does, bail out!
        self._log(logging.INFO, 'Verifying that new array "%s" does not '
                  'already exist' % self._dest)
        dest_array = yield self._client.find_server_arrays(
            self._dest, exact=True)
        if dest_array:
            err = 'Dest array "%s" already exists! Exiting!' % dest_array
            raise api.ServerArrayException(err)

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
        params = {'server_array[name]': self._dest}
        self._log(logging.INFO, 'Renaming array "%s" to "%s"' %
                  (new_array.soul['name'], self._dest))
        yield self._client.update_server_array(new_array, params)

        raise gen.Return(True)


class Update(base.RightScaleBaseActor):
    """Patch a RightScale Server Array."""

    required_options = ['array','params']

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

        # First, find the array we're going to be patching. If we're in dry
        # mode, we pretend like we found the array in case its not there. We do
        # throw a big warning though, because this may or may not be an
        # expected behavior, depending on how you're using the actor.
        self._log(logging.INFO, 'Finding template array "%s"' % self._array)
        array = yield self._client.find_server_arrays(self._array, exact=True)

        if not array and self._dry:
            self._log(logging.WARNING,
                      'Array "%s" not found -- creating a mock instead.' %
                      self._array)
            array = mock.MagicMock(name=self._array)
            array.soul = {'name': '<mocked array %s>' % self._array}

        if not array:
            raise api.ServerArrayException(
                'Could not find server template to update.')

        # Now, read through our supplied parameters and generate a
        # rightscale-compatible parameter dict.
        params = self._generate_rightscale_params('server_array', self._params)
        self._log(logging.DEBUG, 'Generated RightScale params: %s' % params)

        # Now, clone the array!
        if not self._dry:
            # We're really doin this!
            self._log(logging.INFO,
                'Updating array "%s" with params: %s' % (array.soul['name'],
                    params))
            yield self._client.update_server_array(array, params)
        else:
            # In dry run, just comment that we would have made
            # the change.
            self._log(logging.WARNING,
                      'Would have updated "%s" with params: %s' %
                      (array.soul['name'], params))

        raise gen.Return(True)
