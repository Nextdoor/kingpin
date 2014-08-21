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

from random import randint
import logging
import mock
import time

from tornado import gen
from tornado import ioloop
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
            array.self.path = '/fake/array/%s' % randint(10000, 20000)

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

        # Now, clone the array!
        self._log(logging.INFO, 'Cloning array "%s"' %
                  source_array.soul['name'])
        if not self._dry:
            # We're really doin this!
            new_array = yield self._client.clone_server_array(source_array)
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


class Destroy(ServerArrayBaseActor):

    """Destroy a RightScale Server Array."""

    required_options = ['array', 'terminate']

    def __init__(self, *args, **kwargs):
        """Initializes the Actor.

        # TODO: Add a 'wait timer' that allows the execution to fail if it
        # takes too long to terminate the instances.

        Args:
            desc: String description of the action being executed.
            options: Dictionary with the following example settings:
              { 'array': <server array name>,
                'terminate': <boolean, whether or not to terminate all running
                instances first. If false, and instances are running, this
                action will fail.> }
        """
        super(Destroy, self).__init__(*args, **kwargs)

        self._array = self._options['array']
        self._terminate = self._options['terminate']

    @gen.coroutine
    def _terminate_all_instances(self, array):
        if not self._terminate:
            self._log(logging.DEBUG, 'Not terminating instances')
            raise gen.Return()

        if self._dry:
            self._log(logging.WARNING,
                      'Would have terminated all array "%s" instances.' %
                      array.soul['name'])
            raise gen.Return()

        self._log(logging.INFO,
                  'Terminating all instances in array "%s"' %
                  array.soul['name'])
        yield self._client.terminate_server_array_instances(array)
        raise gen.Return()

    @gen.coroutine
    def _wait_until_empty(self, array, sleep=60):
        """Sleep until all array instances are terminated.

        This loop monitors the server array for its current live instance count
        and waits until the count hits zero before progressing.

        TODO: Add a timeout setting.

        Args:
            array: rightscale.Resource array object
            sleep: Integer time to sleep between checks (def: 60)
        """
        if self._dry:
                self._log(logging.WARNING,
                          'Pretending that array %s instances are terminated.'
                          % array.soul['name'])
                raise gen.Return()

        while True:
            instances = yield self._client.get_server_array_current_instances(
                array)
            count = len(instances)
            self._log(logging.INFO, '%s instances found' % count)

            if count < 1:
                raise gen.Return()

            # At this point, sleep
            self._log(logging.DEBUG, 'Sleeping..')
            yield gen.Task(ioloop.IOLoop.current().add_timeout,
                           time.time() + sleep)

    @gen.coroutine
    def _destroy_array(self, array):
        """
        TODO: Handle exceptions if the array is not terminatable.
        """
        if self._dry:
            self._log(logging.WARNING,
                      'Pretending to destroy array "%s"' % array.soul['name'])
            raise gen.Return()

        self._log(logging.INFO, 'Destroying array "%s"' % array.soul['name'])
        yield self._client.destroy_server_array(array)
        raise gen.Return()

    @gen.coroutine
    def _execute(self):
        # First things first, login to RightScale asynchronously to
        # pre-populate the API attributes that are dynamically generated. This
        # is a hack, and in the future should likely turn into a smart
        # decorator.
        yield self._client.login()

        # First, find the array we're going to be terminating.
        array = yield self._find_server_arrays(self._array)

        # Disable the array so that no new instances launch
        self._log(logging.INFO, 'Disabling Array "%s"' % self._array)
        params = self._generate_rightscale_params(
            'server_array', {'state': 'disabled'})
        yield self._client.update_server_array(array, params)

        # Optionally terminate all of the instances in the array first.
        yield self._terminate_all_instances(array)

        # Wait...
        yield self._wait_until_empty(array)

        # Wait for al lthe instances to die, and destroy the array
        yield self._destroy_array(array)

        raise gen.Return(True)


class Launch(ServerArrayBaseActor):

    """Launches the min_instances in a RightScale Server Array."""

    required_options = ['array']

    def __init__(self, *args, **kwargs):
        """Initializes the Actor.

        # TODO: Add a 'wait timer' that allows the execution to fail if it
        # takes too long to launch the instances.

        Args:
            desc: String description of the action being executed.
            options: Dictionary with the following example settings:
              { 'array': <server array name> }
        """
        super(Launch, self).__init__(*args, **kwargs)

        self._array = self._options['array']

    @gen.coroutine
    def _wait_until_healthy(self, array, sleep=60):
        """Sleep until a server array has its min_count servers running.

        This loop monitors the server array for its current live instance count
        and waits until the count hits zero before progressing.

        TODO: Add a timeout setting.

        Args:
            array: rightscale.Resource array object
            sleep: Integer time to sleep between checks (def: 60)
        """
        if self._dry:
            self._log(logging.WARNING,
                      'Pretending that array %s instances are launched.'
                      % array.soul['name'])
            raise gen.Return()

        # Get the current min_count setting from the ServerArray object
        min = int(array.soul['elasticity_params']['bounds']['min_count'])

        while True:
            instances = yield self._client.get_server_array_current_instances(
                array, filter='state==operational')
            count = len(instances)
            self._log(logging.INFO, '%s instances found' % count)

            if min <= count:
                raise gen.Return()

            # At this point, sleep
            self._log(logging.DEBUG, 'Sleeping..')
            yield gen.Task(ioloop.IOLoop.current().add_timeout,
                           time.time() + sleep)

#    @gen.coroutine
#    def _async_launch_min_instances(self, array):
#        """Asynchronously launch all the instances in an array.
#
#        **DO NOT USE THIS METHOD**
#
#        NOTE: The smart thing to do here is to simultaneously click 'launch'
#        for every necessary instance so they all launch at once. These API
#        calls take 5-7 seconds to complete, so this would be much faster than
#        doing these calls synchronously.
#
#        Unfortunately, RightScales ServerArray API only allows a single call
#        to /launch at any time on a single ServerArray. This means that these
#        calls must be synchronous for now.
#        """
#
#        if self._dry:
#            self._log(logging.WARNING, 'Would have launched instances')
#            raise gen.Return()
#
#        # Get the current min_count setting from the ServerArray object
#        min = int(array.soul['elasticity_params']['bounds']['min_count'])
#
#        actions = []
#        for i in xrange(0, min):
#            actions.append(self._client.launch_server_array(array))
#
#        # Yield them all
#        ret = yield actions
#
#        raise gen.Return(ret)

    @gen.coroutine
    def _launch_min_instances(self, array):
        # Get the current min_count setting from the ServerArray object
        min = int(array.soul['elasticity_params']['bounds']['min_count'])

        if self._dry:
            self._log(logging.WARNING,
                      'Would have launched instances of array %s' %
                      array.soul['name'])
            raise gen.Return()

        # Build 'min' number of launch clicks
        for i in xrange(0, min):
            yield self._client.launch_server_array(array)

        raise gen.Return()

    @gen.coroutine
    def _execute(self):
        # First things first, login to RightScale asynchronously to
        # pre-populate the API attributes that are dynamically generated. This
        # is a hack, and in the future should likely turn into a smart
        # decorator.
        yield self._client.login()

        # First, find the array we're going to be launching....
        array = yield self._find_server_arrays(self._array)

        # Enable the array right away. This means that RightScale will
        # auto-scale-up the array as soon as their next scheduled auto-scale
        # run hits (usually 60s). Store the newly updated array.
        self._log(logging.INFO, 'Enabling Array "%s"' % self._array)
        params = self._generate_rightscale_params(
            'server_array', {'state': 'enabled'})
        array = yield self._client.update_server_array(array, params)

        # Launch all of the instances we want as quickly as we can. Note, we
        # don't actually store the result here because we don't care about the
        # returned instances themselves. If we launch 10, and 1 fails, we will
        # rely on RightScale to re-launch that 1 host, rather than handing it
        # in-code. Instead, our 'launch clicking' here is just a way to get the
        # ball rolling as quickly as possible before rightscales
        # auto-array-scaling kicks in.
        yield self._launch_min_instances(array)

        # Now, wait until the number of healthy instances in the array matches
        # the min_count (or is greater than) of that array.
        yield self._wait_until_healthy(array)

        raise gen.Return(True)
