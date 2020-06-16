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
:mod:`kingpin.actors.rightscale.server_array`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. _ResourceInstances:
   http://reference.rightscale.com/api1.5/resources/
   ResourceInstances.html#update
"""

import logging
import math

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


class InvalidInputs(exceptions.InvalidOptions):

    """Raised when supplied inputs are invalid for a ServerArray."""


class TaskExecutionFailed(exceptions.RecoverableActorFailure):

    """Raised when one or more RightScale Task executions fail."""


class ServerArrayBaseActor(base.RightScaleBaseActor):

    """Abstract ServerArray Actor that provides some utility methods."""

    @gen.coroutine
    def _apply(self, function, arrays, *args, **kwargs):
        """Yield a function on several arrays at once.

        Many of our rightscale.server_array Actors have the ability to act on
        multiple arrays at a time (through the 'exact=False' parameter). This
        method provides a quick and re-usable method for yielding generators on
        an array (or group of arrays). All we do here is queue up a group of
        functions, yield them all at once, and return.

        args:
            function: Reference to the function to execute
            arrays: An array, or list of arrays to execute on.
            *args: Any *args to pass to the function
            **kwargs: Any **kwargs to pass to the function
        """
        if not isinstance(arrays, list):
            arrays = [arrays]

        tasks = []
        for array in arrays:
            self.log.debug('Adding %s(%s, %s, %s) to async call list' %
                           (function.__name__, array.soul['name'],
                            args, kwargs))
            tasks.append(function(array, *args, **kwargs))

        self.log.debug('Calling all functions in async call list')
        ret = yield tasks
        raise gen.Return(ret)


class Clone(ServerArrayBaseActor):

    """Clones a RightScale Server Array.

    Clones a ServerArray in RightScale and renames it to the newly supplied
    name.  By default, this actor is extremely strict about validating that the
    ``source`` array already exists, and that the ``dest`` array does not yet
    exist. This behavior can be overridden though if your Kingpin script
    creates the ``source``, or destroys an existing ``dest`` ServerArray
    sometime before this actor executes.

    **Options**

    :source:
      The name of the ServerArray to clone

    :strict_source:
      Whether or not to fail if the source ServerArray does not exist.
      (default: True)

    :dest:
      The new name for your cloned ServerArray

    :strict_dest:
      Whether or not to fail if the destination ServerArray already exists.
      (default: True)

    **Examples**

    Clone my-template-array to my-new-array:

    .. code-block:: json

       { "desc": "Clone my array",
         "actor": "rightscale.server_array.Clone",
         "options": {
           "source": "my-template-array",
           "dest": "my-new-array"
         }
       }

    Clone an array that was created sometime earlier in the Kingpin JSON,
    and thus does not exist yet during the dry run:

    .. code-block:: json

       { "desc": "Clone that array we created earlier",
         "actor": "rightscale.server_array.Clone",
         "options": {
           "source": "my-template-array",
           "strict_source": false,
           "dest": "my-new-array"
         }
       }

    Clone an array into a destination name that was destroyed sometime
    earlier in the Kingpin JSON:

    .. code-block:: json

       { "desc": "Clone that array we created earlier",
         "actor": "rightscale.server_array.Clone",
         "options": {
           "source": "my-template-array",
           "dest": "my-new-array",
           "strict_dest": false,
         }
       }

    **Dry Mode**

    In Dry mode this actor *does* validate that the ``source`` array exists. If
    it does not, a `kingpin.actors.rightscale.api.ServerArrayException` is
    thrown. Once that has been validated, the dry mode execution pretends to
    copy the array by creating a mocked cloned array resource. This mocked
    resource is then operated on during the rest of the execution of the actor,
    guaranteeing that no live resources are modified.

    Example *dry* output::

        [Copy Test (DRY Mode)] Verifying that array "temp" exists
        [Copy Test (DRY Mode)] Verifying that array "new" does not exist
        [Copy Test (DRY Mode)] Cloning array "temp"
        [Copy Test (DRY Mode)] Renaming array "<mocked clone of temp>" to "new"
    """

    all_options = {
        'source': (str, REQUIRED, 'Name of the ServerArray to clone.'),
        'strict_source': (bool, True, 'Strict Source ServerArray validation.'),
        'strict_dest': (bool, True, 'Strict Dest ServerArray validation.'),
        'dest': (str, REQUIRED, 'Name to give the cloned ServerArray.')
    }

    def __init__(self, *args, **kwargs):
        """Validate the user-supplied parameters at instantiation time."""
        super(Clone, self).__init__(*args, **kwargs)
        # By default, we're strict on our source/dest array validation
        self._source_raise_on = 'notfound'
        self._source_allow_mock = False
        self._dest_raise_on = 'found'
        self._dest_allow_mock = False

        if not self.option('strict_source'):
            self._source_raise_on = None
            self._source_allow_mock = True

        if not self.option('strict_dest'):
            self._dest_raise_on = None
            self._dest_allow_mock = True

    @gen.coroutine
    def _execute(self):
        # Find the array we're copying from
        source_array = yield self._find_server_arrays(
            self.option('source'),
            raise_on=self._source_raise_on,
            allow_mock=self._source_allow_mock)

        # Sanity-check -- make sure that the destination server array doesn't
        # already exist. If it does, bail out!
        yield self._find_server_arrays(
            self.option('dest'),
            raise_on=self._dest_raise_on,
            allow_mock=self._dest_allow_mock)

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
        yield self._client.update(new_array, params)
        raise gen.Return()


class Update(ServerArrayBaseActor):

    """Update ServerArray Settings

    Updates an existing ServerArray in RightScale with the supplied parameters.
    Can update any parameter that is described in the RightScale API docs here:

    Parameters are passed into the actor in the form of a dictionary, and are
    then converted into the RightScale format. See below for examples.

    **Options**

    :array:
      (str) The name of the ServerArray to update

    :exact:
      (bool) whether or not to search for the exact array name.
      (default: `true`)

    :params:
      (dict) Dictionary of parameters to update

    :inputs:
      (dict) Dictionary of next-instance server arryay inputs to update

    **Examples**

    .. code-block:: json

       { "desc": "Update my array",
         "actor": "rightscale.server_array.Update",
         "options": {
           "array": "my-new-array",
           "params": {
             "elasticity_params": {
               "bounds": {
                 "min_count": 4
               },
               "schedule": [
                 {"day": "Sunday", "max_count": 2,
                  "min_count": 1, "time": "07:00" },
                 {"day": "Sunday", "max_count": 2,
                  "min_count": 2, "time": "09:00" }
               ]
             },
             "name": "my-really-new-name"
           }
         }
       }

    .. code-block:: json

       { "desc": "Update my array inputs",
         "actor": "rightscale.server_array.Update",
         "options": {
           "array": "my-new-array",
           "inputs": {
             "ELB_NAME": "text:foobar"
           }
         }
       }

    **Dry Mode**

    In Dry mode this actor *does* search for the ``array``, but allows it to be
    missing because its highly likely that the array does not exist yet. If the
    array does not exist, a mocked array object is created for the rest of the
    execution.

    During the rest of the execution, the code bypasses making any real changes
    and just tells you what changes it would have made.

    *This means that the dry mode cannot validate that the supplied inputs will
    work.*

    Example *dry* output::

       [Update Test (DRY Mode)] Verifying that array "new" exists
       [Update Test (DRY Mode)] Array "new" not found -- creating a mock.
       [Update Test (DRY Mode)] Would have updated "<mocked array new>" with
       params: {'server_array[name]': 'my-really-new-name',
                'server_array[elasticity_params][bounds][min_count]': '4'}
    """

    all_options = {
        'array': (str, REQUIRED, 'ServerArray name to Update'),
        'exact': (bool, True, (
            'Whether to search for multiple ServerArrays and act on them.')),
        'params': (dict, {}, 'ServerArray RightScale parameters'),
        'inputs': (dict, {}, 'ServerArray inputs for launching.')
    }

    def __init__(self, *args, **kwargs):
        """Validate the user-supplied parameters at instantiation time."""
        super(Update, self).__init__(*args, **kwargs)
        self._params = self._generate_rightscale_params(
            'server_array', self.option('params'))
        self._inputs = self._generate_rightscale_params(
            'inputs', self.option('inputs'))

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
        for input_name, _ in list(inputs.items()):
            # Inputs have to be there. If not -- it's a problem.
            if input_name not in all_input_names:
                self.log.error('Input not found: "%s"' % input_name)
                success = False

        if not success:
            raise InvalidInputs('Some inputs supplied were incorrect.')

        raise gen.Return()

    @gen.coroutine
    def _update_params(self, array):
        """Update the parameters on a RightScale ServerArray.

        args:
            array: The array to operate on
        """

        if not self.option('params'):
            raise gen.Return()

        self.log.info('Updating array "%s" with params: %s' %
                      (array.soul['name'], self._params))
        try:
            yield self._client.update(array, self._params)
        except api.RightScaleError as e:
            raise exceptions.RecoverableActorFailure(e)
        except requests.exceptions.HTTPError as e:
            raise exceptions.UnrecoverableActorFailure(e)

        raise gen.Return()

    @gen.coroutine
    def _update_inputs(self, array):
        """Update the inputs on a RightScale ServerArray.

        args:
            array: rightscale.Resource ServerArray Object
        """

        if not self.option('inputs'):
            raise gen.Return()

        self.log.info('Updating array "%s" with inputs: %s' %
                      (array.soul['name'], self._inputs))
        yield self._client.update_server_array_inputs(array, self._inputs)

    @gen.coroutine
    def _execute(self):
        # First, find the arrays we're going to be patching.
        arrays = yield self._find_server_arrays(
            self.option('array'), exact=self.option('exact'))

        # In dry run, just comment that we would have made the change.
        if self._dry:
            self.log.debug('Not making any changes.')
            if self.option('params'):
                self.log.info('Params would be: %s' % self.option('params'))
            if self.option('inputs'):
                self.log.info('Inputs would be: %s' % self.option('inputs'))
                yield self._apply(self._check_array_inputs,
                                  arrays, self.option('inputs'))

            raise gen.Return()

        # Do the real work
        yield self._apply(self._update_params, arrays)
        yield self._apply(self._update_inputs, arrays)
        raise gen.Return()


class UpdateNextInstance(ServerArrayBaseActor):

    """Update the Next Instance parameters for a Server Array

    Updates an existing ServerArray in RightScale with the supplied parameters.
    Can update any parameter that is described in the RightScale
    `ResourceInstances`_ docs.

    **Note about the image_href parameter**

    If you pass in the string `default` to the `image_href` key in your
    `params` dictionary, we will search and find the default image that your
    ServerArray's Multi Cloud Image refers to. This helper is useful if you
    update your ServerArrays to use custom AMIs, and then occasionally want to
    go back to using a stock AMI. For example, if you boot up your instances
    occasionally off a stock AMI, customize the host, and then bake that host
    into a custom AMI.

    Parameters are passed into the actor in the form of a dictionary, and are
    then converted into the RightScale format. See below for examples.

    **Options**

    :array:
      (str) The name of the ServerArray to update

    :exact:
      (bool) whether or not to search for the exact array name.
      (default: `true`)

    :params:
      (dict) Dictionary of parameters to update

    **Examples**

    .. code-block:: json

       { "desc": "Update my array",
         "actor": "rightscale.server_array.UpdateNextInstance",
         "options": {
           "array": "my-new-array",
           "params": {
             "associate_public_ip_address": true,
             "image_href": "/image/href/123",
           }
         }
       }

    .. code-block:: json

       { "desc": "Reset the AMI image to the MCI default",
         "actor": "rightscale.server_array.UpdateNextInstance",
         "options": {
           "array": "my-new-array",
           "params": {
             "image_href": "default",
           }
         }
       }

    **Dry Mode**

    In Dry mode this actor *does* search for the ``array``, but allows it to be
    missing because its highly likely that the array does not exist yet. If the
    array does not exist, a mocked array object is created for the rest of the
    execution.

    During the rest of the execution, the code bypasses making any real changes
    and just tells you what changes it would have made.

    *This means that the dry mode cannot validate that the supplied params will
    work.*

    Example *dry* output::

       [Update my array (DRY Mode)] Verifying that array "new" exists
       [Update my array (DRY Mode)] Array "new" not found -- creating a mock.
       [Update my array (DRY Mode)] Would have updated "<mocked array new>"
       with params: {'server_array[associate_public_ip_address]': true,
                'server_array[image_href]': '/image/href/'}
    """

    all_options = {
        'array': (str, REQUIRED, 'ServerArray name to Update'),
        'exact': (bool, True, (
            'Whether to search for multiple ServerArrays and act on them.')),
        'params': (dict, REQUIRED, 'Next Instance RightScale parameters'),
    }

    def __init__(self, *args, **kwargs):
        """Validate the user-supplied parameters at instantiation time."""
        super(UpdateNextInstance, self).__init__(*args, **kwargs)
        self._params = self._generate_rightscale_params(
            'instance', self.option('params'))

    @gen.coroutine
    def _update_params(self, array):
        """Update the parameters on a RightScale Instance.

        args:
            array: The ServerArray to operate on
        """
        # Get the 'next instance' of the array that we're going to work on
        instance = yield self._client.show(array.next_instance)

        # Get our parameters
        params = self.option('params')

        # Magic: If a user supplies 'default' to the image_href then we do some
        # digging for them and find the 'default' AMI HREF for that server
        # array.
        if ('image_href' in params and params['image_href'] == 'default'):
            params['image_href'] = yield self._find_def_image_href(instance)

        # Second pass at the generating the parameters. We did this at
        # instantiation time as a sanity check to make sure the parameters were
        # half-decent. Now we run it a second time in case any the 'image_href'
        # magic above was executed.
        rs_params = self._generate_rightscale_params(
            'instance', self.option('params'))

        if self._dry:
            self.log.info('Would have updated array\'s next_instance "%s" '
                          'with params: %s' %
                          (instance.soul['name'], rs_params))
            raise gen.Return()

        self.log.info('Updating array\'s next_instance "%s" with params: %s' %
                      (instance.soul['name'], rs_params))

        try:
            yield self._client.update(instance, rs_params)
        except api.RightScaleError as e:
            raise exceptions.RecoverableActorFailure(e)
        except requests.exceptions.HTTPError as e:
            raise exceptions.UnrecoverableActorFailure(e)

        raise gen.Return()

    @gen.coroutine
    def _find_def_image_href(self, instance):
        self.log.debug('Searching for default boot AMI for %s' %
                       instance.soul['name'])

        # Find the MultiCloudImage associated with this 'instance' object, then
        # get the full list of 'settings' for that MCI.
        mci = yield self._client.show(instance.multi_cloud_image)
        self.log.debug('Got MCI: %s' % mci.soul['name'])
        mci_settings = yield self._client.show(mci.settings)
        self.log.debug('Got %s MCI Cloud Settings.' % len(mci_settings))

        # Now, find the 'setting' that matches the cloud of our instance. Note,
        # there should never be more than one returned -- so we take the first
        # one in the list and save it.
        try:
            setting = [s for s in mci_settings if
                       s.cloud.path == instance.cloud.path][0]
            image_href = [l['href'] for l in setting.soul['links']
                          if l['rel'] == 'image'][0]
        except KeyError:
            raise InvalidInputs(
                'Unable to locate default image_href for %s.' % instance.soul)

        raise gen.Return(image_href)

    @gen.coroutine
    def _execute(self):
        # First, find the arrays we're going to be patching.
        arrays = yield self._find_server_arrays(
            self.option('array'), exact=self.option('exact'))

        yield self._apply(self._update_params, arrays)


class Terminate(ServerArrayBaseActor):

    """Terminate all instances in a ServerArray

    Terminates all instances for a ServerArray in RightScale marking the array
    disabled.

    **Options**

    :array:
      (str) The name of the ServerArray to destroy

    :exact:
      (bool) Whether or not to search for the exact array name.
      (default: `true`)

    :strict:
      (bool) Whether or not to fail if the ServerArray does not exist.
      (default: `true`)

    **Examples**

    .. code-block:: json

        { "desc": "Terminate my array",
         "actor": "rightscale.server_array.Terminate",
         "options": {
           "array": "my-array"
         }
       }

    .. code-block:: json

       { "desc": "Terminate many arrays",
         "actor": "rightscale.server_array.Terminate",
         "options": {
           "array": "array-prefix",
           "exact": false,
         }
       }

    **Dry Mode**

    Dry mode still validates that the server array you want to terminate is
    actually gone. If you want to bypass this check, then set the
    ``warn_on_failure`` flag for the actor.
    """

    all_options = {
        'array': (str, REQUIRED, 'ServerArray name to Terminate'),
        'exact': (bool, True, (
            'Whether to search for multiple ServerArrays and act on them.')),
        'strict': (bool, True, 'Strict ServerArray validation.'),
    }

    def __init__(self, *args, **kwargs):
        """Validate the user-supplied parameters at instantiation time."""
        super(Terminate, self).__init__(*args, **kwargs)
        # By default, we're strict on our source/dest array validation
        self._raise_on = 'notfound'
        self._allow_mock = False

        if not self.option('strict'):
            self._raise_on = None
            self._allow_mock = True

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
    def _disable_array(self, array):
        """Prevent the supplied ServerArray from auto scaling.

        args:
            array: rightscale.Resource array object
        """
        params = self._generate_rightscale_params(
            'server_array', {'state': 'disabled'})

        if self._dry:
            self.log.info('Would have updated array "%s" with params: %s' %
                          (array.soul['name'], params))
            raise gen.Return()

        self.log.info('Disabling Array "%s"' % array.soul['name'])
        yield self._client.update(array, params)
        raise gen.Return()

    @gen.coroutine
    def _execute(self):
        # First, find the array we're going to be terminating.
        arrays = yield self._find_server_arrays(self.option('array'),
                                                raise_on=self._raise_on,
                                                allow_mock=self._allow_mock,
                                                exact=self.option('exact'))

        # Disable the array so that no new instances launch. Ignore the result
        # of this opertaion -- as long as it succeeds, we're happy. No need to
        # store the returned server array object.
        yield self._apply(self._disable_array, arrays)

        # Optionally terminate all of the instances in the array first.
        yield self._apply(self._terminate_all_instances, arrays)

        # Wait...
        yield self._apply(self._wait_until_empty, arrays)

        raise gen.Return()


class Destroy(Terminate):

    """Destroy a ServerArray in RightScale

    Destroys a ServerArray in RightScale by first invoking the Terminate actor,
    and then deleting the array as soon as all of the running instances have
    been terminated.

    **Options**

    :array:
      (str) The name of the ServerArray to destroy

    :exact:
      (bool) Whether or not to search for the exact array name.
      (default: `true`)

    :strict:
      (bool) Whether or not to fail if the ServerArray does not exist.
      (default: `true`)

    **Examples**

    .. code-block:: json

       { "desc": "Destroy my array",
         "actor": "rightscale.server_array.Destroy",
         "options": {
           "array": "my-array"
         }
       }

    .. code-block:: json

       { "desc": "Destroy many arrays",
         "actor": "rightscale.server_array.Destroy",
         "options": {
           "array": "array-prefix",
           "exact": false,
         }
       }

    **Dry Mode**

    In Dry mode this actor *does* search for the `array`, but allows it to be
    missing because its highly likely that the array does not exist yet. If the
    array does not exist, a mocked array object is created for the rest of the
    execution.

    During the rest of the execution, the code bypasses making any real changes
    and just tells you what changes it would have made.

    Example *dry* output::

       [Destroy Test (DRY Mode)] Beginning
       [Destroy Test (DRY Mode)] Terminating array before destroying it.
       [Destroy Test (terminate) (DRY Mode)] Array "my-array" not found --
       creating a mock.
       [Destroy Test (terminate) (DRY Mode)] Disabling Array "my-array"
       [Destroy Test (terminate) (DRY Mode)] Would have terminated all array
       "<mocked array my-array>" instances.
       [Destroy Test (terminate) (DRY Mode)] Pretending that array <mocked
       array my-array> instances are terminated.
       [Destroy Test (DRY Mode)] Pretending to destroy array "<mocked array
       my-array>"
       [Destroy Test (DRY Mode)] Finished successfully. Result: True
    """

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
    def _execute(self):
        # Call the Terminate _execute function first
        yield super(Destroy, self)._execute()

        # Find the array we're going to be destroying.
        arrays = yield self._find_server_arrays(self.option('array'),
                                                raise_on=self._raise_on,
                                                allow_mock=self._allow_mock,
                                                exact=self.option('exact'))
        yield self._apply(self._destroy_array, arrays)
        raise gen.Return()


class Launch(ServerArrayBaseActor):

    """Launch instances in a ServerArray

    Launches instances in an existing ServerArray and waits until that array
    has become healthy before returning. *Healthy* means that the array has at
    least the user-specified ``count`` or ``max_count`` number of instances
    running as defined by the array definition in RightScale.

    **Options**

    :array:
      (str) The name of the ServerArray to launch
    :count:
      (str, int) Optional number of instance to launch. Defaults to max_count
      of the array.
    :success_pct':
      (str, int) Optional percent (0-100) to wait for instances to launch
      before exiting this actor as successful. Default: 100.

    :enable:
      (bool) Should the autoscaling of the array be enabled? Settings this to
      `false`, or omitting the parameter will not disable an enabled array.

    :exact:
      (bool) Whether or not to search for the exact array name.
      (default: `true`)

    **Examples**

    .. code-block:: json

       { "desc": "Enable array and launch it",
         "actor": "rightscale.server_array.Launch",
         "options": {
           "array": "my-array",
           "enable": true
         }
       }

    .. code-block:: json

       { "desc": "Enable arrays starting with my-array and launch them",
         "actor": "rightscale.server_array.Launch",
         "options": {
           "array": "my-array",
           "enable": true,
           "exact": false
         }
       }

    .. code-block:: json

       { "desc": "Enable array and launch 1 instance",
         "actor": "rightscale.server_array.Launch",
         "options": {
           "array": "my-array",
           "count": 1
         }
       }

    **Dry Mode**

    In Dry mode this actor *does* search for the ``array``, but allows it to be
    missing because its highly likely that the array does not exist yet. If the
    array does not exist, a mocked array object is created for the rest of the
    execution.

    During the rest of the execution, the code bypasses making any real changes
    and just tells you what changes it would have made.

    Example *dry* output::

       [Launch Array Test #0 (DRY Mode)] Verifying that array "my-array" exists
       [Launch Array Test #0 (DRY Mode)] Array "my-array" not found -- creating
           a mock.
       [Launch Array Test #0 (DRY Mode)] Enabling Array "my-array"
       [Launch Array Test #0 (DRY Mode)] Launching Array "my-array" instances
       [Launch Array Test #0 (DRY Mode)] Would have launched instances of array
           <MagicMock name='my-array.self.show().soul.__getitem__()'
           id='4420453200'>
       [Launch Array Test #0 (DRY Mode)] Pretending that array <MagicMock
           name='my-array.self.show().soul.__getitem__()' id='4420453200'>
           instances are launched.
    """

    all_options = {
        'array': (str, REQUIRED, 'ServerArray name to launch'),
        'count': (
            (int, str), False,
            "Number of server to launch. Default: up to array's max count"),
        'success_pct': (
            (int, str), 100,
            '% of servers to wait for. Default: 100% of `count`.'),
        'enable': (bool, False, 'Enable autoscaling?'),
        'exact': (bool, True, (
            'Whether to search for multiple ServerArrays and act on them.')),
    }

    def __init__(self, *args, **kwargs):
        """Check Actor prerequisites."""

        # Base class does everything to set up a generic class
        super(Launch, self).__init__(*args, **kwargs)

        try:
            int(self._options.get('count', False))
        except ValueError:
            raise exceptions.InvalidOptions('`count` must be an integer.')

    @gen.coroutine
    def _wait_until_healthy(self, array, sleep=60):
        """Sleep until a server array has its max_count servers running.

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

        max_count = int(self.option('count'))
        success_pct = float(self.option('success_pct'))
        if not max_count:
            max_count = int(array.soul['elasticity_params']
                            ['bounds']['max_count'])

        enough_count = int(math.ceil(max_count * (success_pct / 100.0)))

        while True:
            instances = yield self._client.get_server_array_current_instances(
                array, filters=['state==operational'])
            count = len(instances)
            self.log.info('%s instances found, waiting for %s/%s' %
                          (count, enough_count, max_count))

            if count >= enough_count:
                raise gen.Return()

            self.log.debug('Sleeping..')
            yield gen.sleep(sleep)

    @gen.coroutine
    def _launch_instances(self, array, count=False):
        """Launch new instances in a specified array.

        Instructs RightScale to launch instances, specified amount, or array's
        autoscaling 'max' value, in a syncronous or async way.

        TODO: Ensure that if 'count' is supplied, its *added* to the current
        array 'server instance count'. This allows the actor to launch 10 new
        servers in an already existing array, and wait until all 10 + the
        original group of servers are Operational.

        Args:
            array - rightscale ServerArray object
            count - `False` to use array's _max_ value
                    `int` to launch a specific number of instances
        """
        if not count:
            # Get the current max_count setting from the ServerArray object
            max_count = int(
                array.soul['elasticity_params']['bounds']['max_count'])

            instances = yield self._client.get_server_array_current_instances(
                array, filters=['state==operational'])
            current_count = len(instances)

            # Launch *up to* max_count. Not *new* max_count.
            count = max_count - current_count

            # Silly sanity check. If count < 0, set it to 0. There is no
            # concept of launching "negative" instance counts.
            if count < 0:
                count = 0

        if self._dry:
            self.log.info('Would have launched %s instances of array %s' % (
                          count, array.soul['name']))
            raise gen.Return()

        if count < 1:
            self.log.warning((
                'This array already has %s instances, and '
                'max_count is set to %s') % (current_count, max_count))
            raise gen.Return()

        self.log.info('Launching %s instances of array %s' % (
                      count, array.soul['name']))

        # Launch!
        yield self._client.launch_server_array(array, count=count)
        self.log.info('Launched %s instances for array %s' % (
                      count, array.soul['name']))

        raise gen.Return()

    @gen.coroutine
    def _enable_array(self, array):
        """Enable AutoScaling in a SeverArray.

        args:
            array: rightscale.Resource ServerArray Object
        """
        # This means that RightScale will auto-scale-up the array as soon as
        # their next scheduled auto-scale run hits (usually 60s). Store the
        # newly updated array.
        if self.option('enable'):
            if not self._dry:
                self.log.info('Enabling Array "%s"' % array.soul['name'])
                params = self._generate_rightscale_params(
                    'server_array', {'state': 'enabled'})
                array = yield self._client.update(array, params)
            else:
                self.log.info('Would enable array "%s"' % array.soul['name'])

    @gen.coroutine
    def _execute(self):
        # First, find the array we're going to be launching...
        arrays = yield self._find_server_arrays(
            self.option('array'),
            exact=self.option('exact'))

        # Enable the array, then launch it
        yield self._apply(self._enable_array, arrays)
        yield self._apply(self._launch_instances, arrays,
                          int(self.option('count')))

        # Now, wait until the number of healthy instances in the array matches
        # the max_count (or is greater than) of that array.
        yield self._apply(self._wait_until_healthy, arrays)
        raise gen.Return()


class Execute(ServerArrayBaseActor):

    """Executes a RightScale script/recipe on a ServerArray

    Executes a RightScript or Recipe on a set of hosts in a ServerArray in
    RightScale using individual calls to the live running instances. These can
    be found in your RightScale account under *Design -> RightScript* or
    *Design -> Cookbooks*

    The RightScale API offers a *multi_run_executable* method that can be used
    to run a single script on all servers in an array -- but unfortunately this
    API method provides no way to monitor the progress of the individual jobs
    on the hosts. Furthermore, the method often executes on recently terminated
    or terminating hosts, which throws false-negative error results.

    Our actor explicitly retrieves a list of the *operational* hosts in an
    array and kicks off individual execution tasks for every host. It then
    tracks the execution of those tasks from start to finish and returns the
    results.

    **Options**

    :array:
      (str) The name of the ServerArray to operate on

    :script:
      (str) The name of the RightScript or Recipe to execute

    :expected_runtime:
      (str, int) Expected number of seconds to execute.
      (default: `5`)

    :concurrency:
      Max number of concurrent executions. This will fire off N executions
      in parallel, and continue with the remained as soon as the first
      execution is done. This is faster than creating N Sync executions.
      **Note**: When applied to multiple (M) arrays cumulative concurrency
      accross all arrays will remain at N. It will not be M x N.

    :inputs:
      (dict) Dictionary of Key/Value pairs to use as inputs for the script

    :exact:
      (str) Boolean whether or not to search for the exact array name.
      (default: `true`)

    **Examples**

    .. code-block:: json

        { "desc":" Execute script on my-array",
          "actor": "rightscale.server_array.Execute",
          "options": {
            "array": "my-array",
            "script": "connect to elb",
            "expected_runtime": 3,
            "inputs": {
              "ELB_NAME": "text:my-elb"
            }
          }
        }

    **Dry Mode**

    In Dry mode this actor *does* search for the `array`, but allows it to be
    missing because its highly likely that the array does not exist yet. If the
    array does not exist, a mocked array object is created for the rest of the
    execution.

    During the rest of the execution, the code bypasses making any real changes
    and just tells you what changes it would have made.

    Example *dry* output::

        [Destroy Test (DRY Mode)] Verifying that array "my-array" exists
        [Execute Test (DRY Mode)]
            kingpin.actors.rightscale.server_array.Execute Initialized
        [Execute Test (DRY Mode)] Beginning execution
        [Execute Test (DRY Mode)] Verifying that array "my-array" exists
        [Execute Test (DRY Mode)] Would have executed "Connect instance to ELB"
            with inputs "{'inputs[ELB_NAME]': 'text:my-elb'}" on "my-array".
        [Execute Test (DRY Mode)] Returning result: True
    """

    all_options = {
        'array': (str, REQUIRED,
                  'ServerArray name on which to execute a script.'),
        'exact': (bool, True, (
            'Whether to search for multiple ServerArrays and act on them.')),
        'script': (str, REQUIRED,
                   'RightScale RightScript or Recipe to execute.'),
        'expected_runtime': (int, 5, 'Expected number of seconds to execute.'),
        'concurrency': (int, 0, "Max number of concurrent executions."),
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
                'Found %s instances (in %s) in a non-Operational state, '
                'will not execute on these hosts!' %
                (non_op_count, array.soul['name']))

        self.log.info('Found %s instances (in %s) in the Operational state.' %
                      (len(op), array.soul['name']))
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
        for key, value in list(inputs.items()):
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
    def _exec_and_wait(self, name, inputs, instance, sleep=5):
        """Start execution and wait for completion on a single instance.

        This shim combines the api calls for run_executable_on_instances and
        wait_for_task.

        Args:
            name: Recipe or RightScript String Name
            inputs: Dict of Key/Value Input Pairs
            instance: a single instance object of rightscale.Resource
            sleep: number of seconds to wait before the first status check

        Returns:
            success of wait_for_task()
        """
        tasks = yield self._client.run_executable_on_instances(
            name, inputs, instances=[instance])

        # tasks[0][1] is because there's only 1 task and
        # run_executable_on_instances returns (instance, task) tuple
        success = yield self._client.wait_for_task(
            task=tasks[0][1], task_name=name, sleep=sleep, loc_log=self.log,
            instance=instance)

        raise gen.Return(success)

    @gen.coroutine
    def _execute_array_with_concurrency(self, arrays, inputs):
        """Executes a script on many arrays with limited instance-concurrency.

        This method leverages the same rightscale.api methods as the non
        concurrent method, with the exception that it waits for tasks to finish
        after queuing the limit. The method has to know when a task is complete
        in order to cleverly schedule the next task.

        args:
            arrays: A list of, or a single instance of rightscale.Resource
                    ServerArray objects
            inputs: A string of inputs generated by
                    self._generate_rightscale_params()
        """
        if not isinstance(arrays, list):
            arrays = [arrays]

        instances = []
        for array in arrays:
            new_inst = yield self._get_operational_instances(array)
            instances.extend(new_inst)

        count = len(instances)

        if self._dry:
            self.log.info((
                'Would have executed "%s" with inputs "%s" on %s instances '
                'on %s arrays with limited concurrency of %s.') % (
                    self.option('script'), inputs, count, len(arrays),
                    self.option('concurrency')))
            raise gen.Return()

        self.log.info('Concurrency set to %s' % self.option('concurrency'))
        tasks = []
        for i in instances:
            tasks.append(self._exec_and_wait(
                name=self.option('script'),
                inputs=inputs,
                instance=i,
                sleep=self.option('expected_runtime')))

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

        statuses = yield tasks
        raise gen.Return(all(statuses))

    @gen.coroutine
    def _execute_array(self, array, inputs):
        """Executes a script on an array.

        This method does the real work. It gets a list of instances from an
        array, finds a script, executes the script, and then waits for the
        results of the script. Ultimately it raises a failure if the script
        fails, or simply exits cleanly.

        Note: This is separated out from the _execute() method to facilitate
        using the self._apply() function with multiple arrays.

        args:
            array: rightscale.Resource ServerArray
            inputs: A string of inputs generated by
                    self._generate_rightscale_params()
        """
        instances = yield self._get_operational_instances(array)

        if self._dry:
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

    @gen.coroutine
    def _execute(self):
        """Executes the actor.

        Logs into RightScale, validates (if in dry run) that the script
        actually exists, and then executes the script on all of the matched
        server arrays.
        """
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

        # First, find the array we're going to be launching. Get a list back of
        # the 'operational' instances that we are able to execute scripts
        # against.
        arrays = yield self._find_server_arrays(
            self.option('array'), exact=self.option('exact'))
        if self.option('concurrency'):
            yield self._execute_array_with_concurrency(arrays, inputs)
        else:
            yield self._apply(self._execute_array, arrays, inputs)
