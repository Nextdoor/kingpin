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
from kingpin.constants import REQUIRED

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


class ArrayNotFound(exceptions.RecoverableActorFailure):

    """Raised when a ServerArray could not be found."""


class ArrayAlreadyExists(exceptions.RecoverableActorFailure):

    """Raised when a ServerArray already exists by a given name."""


class InvalidInputs(exceptions.InvalidOptions):

    """Raised when supplied inputs are invalid for a ServerArray."""


class TaskExecutionFailed(exceptions.RecoverableActorFailure):

    """Raised when one or more RightScale Task executions fail."""


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

        raise gen.Return(array)


class Clone(ServerArrayBaseActor):

    """Clones a RightScale Server Array."""

    all_options = {
        'source': (str, REQUIRED, 'Name of the ServerArray to clone.'),
        'dest': (str, REQUIRED, 'Name to give the cloned ServerArray.')
    }

    @gen.coroutine
    def _execute(self):
        # First things first, login to RightScale asynchronously to
        # pre-populate the API attributes that are dynamically generated. This
        # is a hack, and in the future should likely turn into a smart
        # decorator.
        yield self._client.login()

        # Find the array we're copying from
        source_array = yield self._find_server_arrays(self.option('source'),
                                                      allow_mock=False)

        # Sanity-check -- make sure that the destination server array doesn't
        # already exist. If it does, bail out!
        yield self._find_server_arrays(self.option('dest'),
                                       raise_on='found',
                                       allow_mock=False)

        # Now, clone the array!
        self.log.info('Cloning array "%s"' % source_array.soul['name'])
        if not self._dry:
            # We're really doin this!
            new_array = yield self._client.clone_server_array(source_array)
        else:
            # In dry run mode. Don't really clone the array, instead we create
            # a mock object and pass that back as if its the new array.
            new_array = mock.MagicMock(name=self.option('dest'))
            new_array_name = '<mocked clone of %s>' % self.option('source')
            new_array.soul = {'name': new_array_name}

        # Lastly, rename the array
        params = self._generate_rightscale_params(
            'server_array', {'name': self.option('dest')})
        self.log.info('Renaming array "%s" to "%s"' % (new_array.soul['name'],
                                                       self.option('dest')))
        yield self._client.update_server_array(new_array, params)
        raise gen.Return()


class Update(ServerArrayBaseActor):

    """Patch a RightScale Server Array.

    Note, the Array name is required. The params and inputs options are
    optional -- but if you want the actor to actually make any changes, you
    need to supply one of these.

    Actor Options (example):
          { 'array': <server array name>,
            'params': { 'description': 'foo bar',
                        'state': 'enabled' },
            'inputs': { 'ELB_NAME': 'foo bar' } }
    """

    all_options = {
        'array': (str, REQUIRED, 'ServerArray name to Update'),
        'params': (dict, {}, 'ServerArray RightScale parameters'),
        'inputs': (dict, {}, 'ServerArray inputs for launching.')
    }

    @gen.coroutine
    def _check_array_inputs(self, array, inputs):
        """Checks the inputs supplied against the ServerArray being updated.

        Verifies that the supplied inputs are actually found in the ServerArray
        that we are going to be updating.

        Raises:
            InvalidInputs()
        """
        # Quick sanity check, make sure we weren't handed a mock object created
        # by the _find_server_array() method. If we were, then the inputs are
        # not checkable. Just warn, and move on.
        if 'fake' in array.soul:
            self.log.warning('Cannot check inputs for non-existent array.')
            raise gen.Return()

        all_inputs = yield self._client.get_server_array_inputs(array)
        all_input_names = [i.soul['name'] for i in all_inputs]

        success = True
        for input_name, _ in inputs.items():
            # Inputs have to be there. If not -- it's a problem.
            if input_name not in all_input_names:
                self.log.error('Input not found: "%s"' % input_name)
                success = False

        if not success:
            raise InvalidInputs('Some inputs supplied were incorrect.')

        raise gen.Return()

    @gen.coroutine
    def _execute(self):
        # First things first, login to RightScale asynchronously to
        # pre-populate the API attributes that are dynamically generated. This
        # is a hack, and in the future should likely turn into a smart
        # decorator.
        yield self._client.login()

        # First, find the array we're going to be patching.
        array = yield self._find_server_arrays(self.option('array'))

        # In dry run, just comment that we would have made the change.
        if self._dry:
            self.log.debug('Not making any changes.')
            if self.option('params'):
                self.log.info('Params would be: %s' % self.option('params'))
            if self.option('inputs'):
                self.log.info('Inputs would be: %s' % self.option('inputs'))
                yield self._check_array_inputs(array, self.option('inputs'))

            raise gen.Return()

        # Update the ServerArray Parameters
        if self.option('params'):
            params = self._generate_rightscale_params(
                'server_array', self.option('params'))
            self.log.info('Updating array "%s" with params: %s' %
                          (array.soul['name'], params))
            try:
                yield self._client.update_server_array(array, params)
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 422:
                    msg = ('Invalid parameters supplied to patch array "%s"' %
                           self.option('array'))
                    raise exceptions.RecoverableActorFailure(msg)

        # Update the ServerArray Next-Instance Inputs
        if self.option('inputs'):
            inputs = self._generate_rightscale_params(
                'inputs', self.option('inputs'))
            self.log.info('Updating array "%s" with inputs: %s' %
                          (array.soul['name'], inputs))
            yield self._client.update_server_array_inputs(array, inputs)

        raise gen.Return()


class Terminate(ServerArrayBaseActor):

    """Terminate all instances in a RightScale Server Array."""

    all_options = {
        'array': (str, REQUIRED, 'ServerArray name to Terminate')
    }

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
        self.array = yield self._find_server_arrays(self.option('array'),
                                                    raise_on='notfound',
                                                    allow_mock=False)

        # Disable the array so that no new instances launch. Ignore the result
        # of this opertaion -- as long as it succeeds, we're happy. No need to
        # store the returned server array object.
        params = self._generate_rightscale_params(
            'server_array', {'state': 'disabled'})
        if not self._dry:
            self.log.info('Disabling Array "%s"' % self.option('array'))
            yield self._client.update_server_array(self.array, params)
        else:
            self.log.info('Would have updated array "%s" with params: %s' %
                          (self.option('array'), params))

        # Optionally terminate all of the instances in the array first.
        yield self._terminate_all_instances(self.array)

        # Wait...
        yield self._wait_until_empty(self.array)

        raise gen.Return()


class Destroy(ServerArrayBaseActor):

    """Destroy a ServerArray.

    First terminates all of the running instances, then destroys the actual
    ServerArray in RightScale."""

    all_options = {
        'array': (str, REQUIRED, 'ServerArray name to Destroy')
    }

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

        Raises: <the Terminate actor object>
        """
        helper = Terminate(
            desc=self._desc + ' (terminate)',
            options={'array': self.option('array')},
            warn_on_failure=self._warn_on_failure,
            dry=self._dry)

        yield helper._execute()
        raise gen.Return(helper)

    @gen.coroutine
    def _execute(self):
        # Terminate all instances. If it fails, catch and log the error, then
        # re-raise it.
        try:
            self.log.info('Terminating array before destroying it.')
            helper = yield self._terminate()
        except exceptions.ActorException as e:
            self.log.critical('Termination failed, cannot destroy: %s' % e)
            raise

        # Can grab the array object from the helper instead of re-searching
        yield self._destroy_array(helper.array)
        raise gen.Return()


class Launch(ServerArrayBaseActor):

    """Launches the min_instances in a RightScale Server Array."""

    all_options = {
        'array': (str, REQUIRED, 'ServerArray name to launch'),
        'count': (
            int, False,
            "Number of server to launch. Default: up to array's min count"),
        'enable': (bool, False, 'Enable autoscaling?')
    }

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

        # Get the current min_count setting from the ServerArray object, or get
        # the min_count from the count number supplied to the actor (if it
        # was).
        min_count = self._options.get('count', False)
        if not min_count:
            min_count = int(array.soul['elasticity_params']
                            ['bounds']['min_count'])

        while True:
            instances = yield self._client.get_server_array_current_instances(
                array, filters=['state==operational'])
            count = len(instances)
            self.log.info('%s instances found, waiting for %s' %
                          (count, min_count))

            if min_count <= count:
                raise gen.Return()

            # At this point, sleep
            self.log.debug('Sleeping..')
            yield utils.tornado_sleep(sleep)

    @gen.coroutine
    def _launch_instances(self, array, count=False):
        """Launch new instances in a specified array.

        Instructs RightScale to launch instances, specified amount, or array's
        autoscaling 'min' value, in a syncronous or async way.

        TODO: Ensure that if 'count' is supplied, its *added* to the current
        array 'server instance count'. This allows the actor to launch 10 new
        servers in an already existing array, and wait until all 10 + the
        original group of servers are Operational.

        Args:
            array - rightscale ServerArray object
            count - `False` to use array's _min_ value
                    `int` to launch a specific number of instances
        """
        if not count:
            # Get the current min_count setting from the ServerArray object
            min_count = int(
                array.soul['elasticity_params']['bounds']['min_count'])

            instances = yield self._client.get_server_array_current_instances(
                array, filters=['state==operational'])
            current_count = len(instances)

            # Launch *up to* min_count. Not *new* min_count.
            count = min_count - current_count

        if self._dry:
            self.log.info('Would have launched %s instances of array %s' % (
                          count, array.soul['name']))
            raise gen.Return()

        if count < 0:
            self.log.warning((
                'This array already has %s instances, and '
                'min_count is set to %s') % (current_count, min_count))
            raise gen.Return()

        self.log.info('Launching %s instances of array %s' % (
                      count, array.soul['name']))

        # Note, RightScale does not support asynchronously calling the launch
        # API method multiple times. Must do this sycnhronously.
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
        array = yield self._find_server_arrays(self.option('array'))

        # This means that RightScale will auto-scale-up the array as soon as
        # their next scheduled auto-scale run hits (usually 60s). Store the
        # newly updated array.
        if self.option('enable'):
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
            'Launching Array "%s" instances' % self.option('array'))

        # If count is None, then _launch_instances will use array's `min`.
        count = self.option('count')
        yield self._launch_instances(array, count=count)

        # Now, wait until the number of healthy instances in the array matches
        # the min_count (or is greater than) of that array.
        yield self._wait_until_healthy(array)

        raise gen.Return()


class Execute(ServerArrayBaseActor):

    """Executes a RightScript or Recipe on a ServerArray.

    # TODO: Add a 'wait timer' that allows the execution to fail if it
    # takes too long to launch the instances.
    """

    all_options = {
        'array': (str, REQUIRED,
                  'ServerArray name on which to execute a script.'),
        'script': (str, REQUIRED,
                   'RightScale RightScript or Recipe to execute.'),
        'expected_runtime': (int, 5, 'Expected number of seconds to execute.'),
        'inputs': (dict, {}, (
            'Inputs needed by the script. Read _generate_rightscale_params.'))
    }

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

    def _check_inputs(self):
        """Check that rightscale inputs are formatted properly.

        For more information read:
        http://reference.rightscale.com/api1.5/resources/ResourceInputs.html

        Raises:
            InvalidOptions
        """
        inputs = self.option('inputs')
        issues = False
        types = ('text', 'ignore', 'env', 'cred', 'key', 'array')
        for key, value in inputs.items():
            if value.split(':')[0] not in types:
                issues = True
                self.log.error('Value for %s needs to begin with %s'
                               % (key, types))

        if issues:
            raise exceptions.InvalidOptions('One or more inputs has a problem')

    @gen.coroutine
    def _wait_for_all_tasks(self, task_pairs):
        """Wait for all instances to succeed, or print audit entry if failed.

        Args:
            task_pairs: list of tuples produced by run_executable_on_instances
                [(instance, task), (instance, task)]

        Returns:
            boolean: All tasks succeeded. If at least 1 failed - this is False
        """

        task_count = len(task_pairs)
        self.log.info('Queueing %s tasks' % task_count)
        task_waiting = []

        for instance, task in task_pairs:
            task_name = 'Executing "%s" on instance: %s' % (
                self.option('script'), instance.soul['name'])

            task_waiting.append(self._client.wait_for_task(
                task=task,
                task_name=task_name,
                sleep=self.option('expected_runtime'),
                loc_log=self.log,
                instance=instance
            ))

        self.log.info('Waiting for %s tasks to finish...' % task_count)
        statuses = yield task_waiting

        raise gen.Return(all(statuses))

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
        array = yield self._find_server_arrays(self.option('array'))
        instances = yield self._get_operational_instances(array)

        # Munge our inputs into something that RightScale likes
        inputs = self._generate_rightscale_params(
            'inputs', self.option('inputs'))

        # Theres no way to 'test' the actual execution of the rightscale
        # scripts, so we'll just check that it exists.
        if self._dry:
            script_found = yield self._check_script(self.option('script'))

            if not script_found:
                msg = 'Script "%s" not found!' % self.option('script')
                raise exceptions.InvalidOptions(msg)

            self._check_inputs()

            self.log.info(
                'Would have executed "%s" with inputs "%s" on "%s".'
                % (self.option('script'), inputs, array.soul['name']))
            raise gen.Return()

        count = len(instances)
        # Execute the script on all of the servers in the array and store the
        # task status resource records.
        self.log.info(
            'Executing "%s" on %s instances in the array "%s"' %
            (self.option('script'), count, array.soul['name']))
        try:
            task_pairs = yield self._client.run_executable_on_instances(
                self.option('script'), inputs, instances)
        except api.ServerArrayException as e:
            self.log.critical('Script execution error: %s' % e)
            raise exceptions.RecoverableActorFailure(
                'Invalid parameters supplied to execute script.')

        # Finally, monitor all of the tasks for completion.
        successful = yield self._wait_for_all_tasks(task_pairs)

        # If not all of the executions succeeded, raise an exception.
        if not successful:
            self.log.critical('One or more tasks failed.')
            raise TaskExecutionFailed()
        else:
            self.log.info('Completed %s tasks.' % count)

        raise gen.Return()
