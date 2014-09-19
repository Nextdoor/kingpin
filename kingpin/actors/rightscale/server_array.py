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

from tornado import gen
import mock
import requests

from kingpin import utils
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

        self.log.debug(msg)
        array = yield self._client.find_server_arrays(array_name, exact=True)

        if not array and self._dry and allow_mock:
            # Create a fake ServerArray object thats mocked up to help with
            # execution of the rest of the code.
            self.log.info('Array "%s" not found -- creating a mock.' %
                          array_name)
            array = mock.MagicMock(name=array_name)
            # Give the mock a real identity and give it valid elasticity
            # parameters so the Launch() actor can behave properly.
            array.soul = {
                'name': '<mocked array %s>' % array_name,
                'elasticity_params': {'bounds': {'min_count': 4}}
            }
            array.self.path = '/fake/array/%s' % randint(10000, 20000)
            array.self.show.return_value = array

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

    @gen.coroutine
    def _execute(self):
        # First things first, login to RightScale asynchronously to
        # pre-populate the API attributes that are dynamically generated. This
        # is a hack, and in the future should likely turn into a smart
        # decorator.
        yield self._client.login()

        # First, find the array we're copying from.
        source_array = yield self._find_server_arrays(self._options['source'],
                                                      allow_mock=False)

        # Sanity-check -- make sure that the destination server array doesn't
        # already exist. If it does, bail out!
        yield self._find_server_arrays(self._options['dest'],
                                       raise_on='found',
                                       allow_mock=False)

        # Now, clone the array!
        self.log.info('Cloning array "%s"' % source_array.soul['name'])
        if not self._dry:
            # We're really doin this!
            new_array = yield self._client.clone_server_array(source_array)
        else:
            # In dry run mode. Don't really clone the array, just return back
            # 'True' as if the array-clone worked.
            new_array = mock.MagicMock(name=self._options['dest'])
            new_array.soul = {
                'name': '<mocked clone of %s>' % self._options['source']}

        # Lastly, rename the array
        params = self._generate_rightscale_params(
            'server_array', {'name': self._options['dest']})
        self.log.info('Renaming array "%s" to "%s"' % (new_array.soul['name'],
                                                       self._options['dest']))
        yield self._client.update_server_array(new_array, params)

        raise gen.Return(True)


class Update(ServerArrayBaseActor):

    """Patch a RightScale Server Array.

    Note, the Array name is required. The params and inputs options are
    optional -- but if you want the actor to actually make any changes, you
    need to supply one of these.

    Args:
        desc: String description of the action being executed.
        options: Dictionary with the following example settings:
          { 'array': <server array name>,
            'params': { 'description': 'foo bar',
                        'state': 'enabled' },
            'inputs': { 'ELB_NAME': 'foo bar' } }
    """

    required_options = ['array']

    @gen.coroutine
    def _check_array_inputs(self, array, inputs):
        all_inputs = yield self._client.get_server_array_inputs(array)
        all_input_names = [i.soul['name'] for i in all_inputs]

        success = True
        for input_name, _ in inputs.items():
            # Inputs have to be there. If not -- it's a problem.
            if input_name not in all_input_names:
                self.log.error('Input not found: "%s"' % input_name)
                success = False

        raise gen.Return(success)

    @gen.coroutine
    def _execute(self):
        # First things first, login to RightScale asynchronously to
        # pre-populate the API attributes that are dynamically generated. This
        # is a hack, and in the future should likely turn into a smart
        # decorator.
        yield self._client.login()

        # First, find the array we're going to be patching.
        array = yield self._find_server_arrays(self._options['array'])

        # In dry run, just comment that we would have made the change.
        if self._dry:
            ok = True
            self.log.info('Not making any changes.')
            if 'params' in self._options:
                self.log.info('New params: %s' % self._options['params'])
            if 'inputs' in self._options:
                self.log.info('New inputs: %s' % self._options['inputs'])

                if isinstance(array, mock.Mock):
                    self.log.warning(
                        'Cannot check inputs for non-existent array.')
                    inputs_ok = True
                else:
                    inputs_ok = yield self._check_array_inputs(
                        array, self._options['inputs'])

                ok = ok and inputs_ok

            raise gen.Return(ok)

        # Update the ServerArray Parameters
        if 'params' in self._options:
            params = self._generate_rightscale_params(
                'server_array', self._options['params'])
            self.log.info('Updating array "%s" with params: %s' %
                          (array.soul['name'], params))
            try:
                yield self._client.update_server_array(array, params)
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 422:
                    msg = ('Invalid parameters supplied to patch array "%s"' %
                           self._options['array'])
                    raise exceptions.UnrecoverableActionFailure(msg)

        # Update the ServerArray Next-Instane Inputs
        if 'inputs' in self._options:
            inputs = self._generate_rightscale_params(
                'inputs', self._options['inputs'])
            self.log.info('Updating array "%s" with inputs: %s' %
                          (array.soul['name'], inputs))
            yield self._client.update_server_array_inputs(array, inputs)

        raise gen.Return(True)


class Terminate(ServerArrayBaseActor):

    """Terminate all instances in a RightScale Server Array."""

    required_options = ['array']

    @gen.coroutine
    def _terminate_all_instances(self, array):
        if self._dry:
            self.log.info('Would have terminated all array "%s" instances.' %
                          array.soul['name'])
            raise gen.Return()

        self.log.info('Terminating all instances in array "%s"' %
                      array.soul['name'])
        task = yield self._client.terminate_server_array_instances(array)
        # We don't care if it succeeded -- the multi-terminate job
        # fails all the time when there are hosts still in a
        # 'terminated state' when this call is made. Just wait for it to
        # finish.
        yield self._client.wait_for_task(task)

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
                self.log.info('Pretending that array %s instances '
                              'are terminated.' % array.soul['name'])
                raise gen.Return()

        while True:
            instances = yield self._client.get_server_array_current_instances(
                array)
            count = len(instances)
            self.log.info('%s instances found' % count)

            if count < 1:
                raise gen.Return()

            # At this point, sleep
            self.log.debug('Sleeping..')
            yield utils.tornado_sleep(sleep)

    @gen.coroutine
    def _execute(self):
        # First things first, login to RightScale asynchronously to
        # pre-populate the API attributes that are dynamically generated. This
        # is a hack, and in the future should likely turn into a smart
        # decorator.
        yield self._client.login()

        # First, find the array we're going to be terminating.
        self.array = yield self._find_server_arrays(self._options['array'])

        # Disable the array so that no new instances launch. Ignore the result
        # of this opertaion -- as long as it succeeds, we're happy. No need to
        # store the returned server array object.
        self.log.info('Disabling Array "%s"' % self._options['array'])
        params = self._generate_rightscale_params(
            'server_array', {'state': 'disabled'})
        yield self._client.update_server_array(self.array, params)

        # Optionally terminate all of the instances in the array first.
        yield self._terminate_all_instances(self.array)

        # Wait...
        yield self._wait_until_empty(self.array)

        raise gen.Return(True)


class Destroy(ServerArrayBaseActor):

    """Destroy the array"""

    required_options = ['array']

    @gen.coroutine
    def _destroy_array(self, array):
        """
        TODO: Handle exceptions if the array is not terminatable.
        """
        if self._dry:
            self.log.info('Pretending to destroy array "%s"' %
                          array.soul['name'])
            raise gen.Return()

        self.log.info('Destroying array "%s"' % array.soul['name'])
        yield self._client.destroy_server_array(array)
        raise gen.Return()

    @gen.coroutine
    def _terminate(self):
        """Create and execute Terminator actor

        Returns: the Terminate actor object
        """
        helper = Terminate(
            desc=self._desc + ' (terminate)',
            options={'array': self._options['array']},
            dry=self._dry)

        yield helper._execute()

        raise gen.Return(helper)

    @gen.coroutine
    def _execute(self):

        # Terminate all instances
        self.log.info('Terminating array before destroying it.')
        helper = yield self._terminate()

        # Can grab the array object from the helper instead of re-searching
        array = helper.array

        yield self._destroy_array(array)

        raise gen.Return(True)


class Launch(ServerArrayBaseActor):

    """Launches the min_instances in a RightScale Server Array.

    Actor Options: {
        'array': <server array name>,
        'count': <optional number to launch. Default array's "min" count>,
        'enable': bool - if true - will enable the autoscaling of the array.
    }
    """

    required_options = ['array']

    def __init__(self, *args, **kwargs):
        """Check Actor prerequisites."""

        # Base class does everything to set up a generic class
        super(Launch, self).__init__(*args, **kwargs)

        # Either enable the array (and launch min_count) or
        # specify the exact count of instances to launch.
        enabled = self._options.get('enable', False)
        count_specified = self._options.get('count', False)
        if not (enabled or count_specified):
            raise exceptions.InvalidOptions(
                'Either set the `enable` flag to true, or '
                'specify an integer for `count`.')

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
            self.log.info('Pretending that array %s instances are launched.'
                          % array.soul['name'])
            raise gen.Return()

        # Get the current min_count setting from the ServerArray object
        min_count = int(array.soul['elasticity_params']['bounds']['min_count'])

        while True:
            instances = yield self._client.get_server_array_current_instances(
                array, filters=['state==operational'])
            count = len(instances)
            self.log.info('%s instances found' % count)

            if min_count <= count:
                raise gen.Return()

            # At this point, sleep
            self.log.debug('Sleeping..')
            yield utils.tornado_sleep(sleep)

#        **DO NOT USE async=True METHOD**
#
#        NOTE: The smart thing to do here is to simultaneously click 'launch'
#        for every necessary instance so they all launch at once. These API
#        calls take 5-7 seconds to complete, so this would be much faster than
#        doing these calls synchronously.
#
#        Unfortunately, RightScales ServerArray API only allows a single call
#        to /launch at any time on a single ServerArray. This means that these
#        calls must be synchronous for now.
    @gen.coroutine
    def _launch_instances(self, array, count=None, async=False):
        """Launch new instances in a specified array.

        Instructs RightScale to launch instances, specified amount, or array's
        autoscaling 'min' value, in a syncronous or async way.

        Args:
            array - rightscale ServerArray object
            count - `None` to use array's _min_ value
                    `int` to launch a specific number of instances
            async - Boolean, launch all and wait, or launch one at a time.
        """
        if count is None:
            # Get the current min_count setting from the ServerArray object
            count = int(array.soul['elasticity_params']['bounds']['min_count'])

        if self._dry:
            self.log.info('Would have launched %s instances of array %s' % (
                          count, array.soul['name']))
            raise gen.Return()

        self.log.info('Launching %s instances of array %s' % (
                      count, array.soul['name']))

        if async:
            tasks = []
            for i in xrange(0, count):
                # Make all the launch calls quickly
                tasks.append(self._client.launch_server_array(array))

            # Wait for all of them to finish.
            yield tasks

        if not async:
            for i in xrange(0, count):
                # Launch one server at a time
                yield self._client.launch_server_array(array)

        self.log.info('Launched %s instances for array %s' % (
                      count, array.soul['name']))

        raise gen.Return()

    @gen.coroutine
    def _execute(self):
        # First things first, login to RightScale asynchronously to
        # pre-populate the API attributes that are dynamically generated. This
        # is a hack, and in the future should likely turn into a smart
        # decorator.
        yield self._client.login()

        # First, find the array we're going to be launching....
        array = yield self._find_server_arrays(self._options['array'])

        # This means that RightScale will auto-scale-up the array as soon as
        # their next scheduled auto-scale run hits (usually 60s). Store the
        # newly updated array.
        if self._options.get('enable', False):
            if not self._dry:
                self.log.info('Enabling Array "%s"' % array.soul['name'])
                params = self._generate_rightscale_params(
                    'server_array', {'state': 'enabled'})
                array = yield self._client.update_server_array(array, params)
            else:
                self.log.info('Would enable array "%s"' % array.soul['name'])

        # Launch all of the instances we want as quickly as we can. Note, we
        # don't actually store the result here because we don't care about the
        # returned instances themselves. If we launch 10, and 1 fails, we will
        # rely on RightScale to re-launch that 1 host, rather than handing it
        # in-code. Instead, our 'launch clicking' here is just a way to get the
        # ball rolling as quickly as possible before rightscales
        # auto-array-scaling kicks in.
        self.log.info(
            'Launching Array "%s" instances' % self._options['array'])

        # If count is None, then _launch_instances will use array's `min`.
        count = self._options.get('count')
        yield self._launch_instances(array, count=count)

        # Now, wait until the number of healthy instances in the array matches
        # the min_count (or is greater than) of that array.
        yield self._wait_until_healthy(array)

        raise gen.Return(True)


class Execute(ServerArrayBaseActor):

    """Executes a RightScript or Recipe on a ServerArray.

    # TODO: Add a 'wait timer' that allows the execution to fail if it
    # takes too long to launch the instances.

    Args:
        desc: String description of the action being executed.
        options: Dictionary with the following example settings:
          { 'array': <server array name> }
    """

    required_options = ['array', 'script', 'inputs']

    @gen.coroutine
    def _get_operational_instances(self, array):
        """Gets a list of Operational instances and returns it.

        Warns on any non-Operational instances to let the operator know that
        their script may not execute there.

        Args:
            array: rightscale.Resource ServerArray Object
        """
        # Get all non-terminated instances
        all_instances = yield self._client.get_server_array_current_instances(
            array, filters=['state<>terminated'])

        # Filter out the Operational ones from the Non-Operational (booting,
        # etc) instances.
        op = [inst for inst in all_instances if inst.soul['state'] ==
              'operational']
        non_op = [inst for inst in all_instances if inst.soul['state'] !=
                  'operational']

        # Warn that there are Non-Operational instances and move on.
        non_op_count = len(non_op)
        if non_op_count > 0:
            self.log.warning(
                'Found %s instances in a non-Operational state, will not '
                'execute on these hosts!' % non_op_count)

        self.log.info('Found %s instances in the Operational state.' %
                      len(op))
        raise gen.Return(op)

    @gen.coroutine
    def _check_script(self, script_name):
        if '::' in script_name:
            script = yield self._client.find_cookbook(script_name)
        else:
            script = yield self._client.find_right_script(script_name)

        raise gen.Return(bool(script))

    @gen.coroutine
    def _execute(self):
        # First things first, login to RightScale asynchronously to
        # pre-populate the API attributes that are dynamically generated. This
        # is a hack, and in the future should likely turn into a smart
        # decorator.
        yield self._client.login()

        # First, find the array we're going to be launching. Get a list back of
        # the 'operational' instances that we are able to execute scripts
        # against.
        array = yield self._find_server_arrays(self._options['array'])
        instances = yield self._get_operational_instances(array)

        # Munge our inputs into something that RightScale likes
        inputs = self._generate_rightscale_params(
            'inputs', self._options['inputs'])

        # Theres no way to 'test' the actual execution of the rightscale
        # scripts, so we'll just check that it exists.
        if self._dry:
            script_found = yield self._check_script(self._options['script'])

            if not script_found:
                self.log.error(
                    'Script "%s" not found!' % self._options['script'])
                raise gen.Return(False)

            self.log.info(
                'Would have executed "%s" with inputs "%s" on "%s".'
                % (self._options['script'], inputs, array.soul['name']))
            raise gen.Return(True)

        # Execute the script on all of the servers in the array and store the
        # task status resource records.
        self.log.info(
            'Executing "%s" on %s instances in the array "%s"' %
            (self._options['script'], len(instances), array.soul['name']))
        tasks = yield self._client.run_executable_on_instances(
            self._options['script'], inputs, instances)

        # Finally, monitor all of the tasks for completion.
        actions = []
        for task in tasks:
            actions.append(self._client.wait_for_task(task))
        self.log.info('Waiting for %s tasks to finish.' % len(tasks))
        ret = yield actions

        raise gen.Return(all(ret))
