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

"""Base RightScale API Access Object.

This package provides access to the RightScale API via Tornado-style
@gen.coroutine wrapped methods. These methods are, however, just wrappers
for threads that are being fired off in the background to make the API
calls.


## Async vs Threads

In the future, this will get re-factored to use a native Tornado
AsyncHTTPClient object. The methods themselves will stay the same, but the
underlying private methods will change.

The methods in this object are specifically designed to support common
operations that the RightScale Actor objects need to do. Operations like
'find server array', 'launch server array', etc. This is not meant as a pure
one-to-one mapping of the RightScale API, but rather a mapping of conceptual
operations that the Actors need.

## Method Design Note

RightScale mixes and matches their API calls... some of them you pass in a
major method and then supply a resource ID to act on. Others you pass in the
resource_id and get back a list of methods that you can execute.

For consistency in our programming model, this class relies o you passing in
rightscale.Resource objects everywhere, and it does the resource->ID
translation.
"""

from os import path
import logging
import time

from tornado import ioloop
from tornado import gen
import requests

from rightscale import util as rightscale_util
import rightscale

from kingpin import utils


log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


DEFAULT_ENDPOINT = 'https://my.rightscale.com'


class ServerArrayException(Exception):

    """Raised when an operation on or looking for a ServerArray fails"""


class RightScale(object):

    def __init__(self, token, endpoint=DEFAULT_ENDPOINT):
        """Initializes the RightScaleOperator Object for a RightScale Account.

        Args:
            token: A RightScale RefreshToken
            api: API URL Endpoint
        """
        self._token = token
        self._endpoint = endpoint
        self._client = rightscale.RightScale(refresh_token=self._token,
                                             api_endpoint=self._endpoint)

        # Quiet down the urllib requests library, its noisy even in
        # INFO mode and muddies up the logs.
        r_log = logging.getLogger('requests.packages.urllib3.connectionpool')
        r_log.setLevel(logging.WARNING)

        log.debug('%s initialized (token=<hidden>, endpoint=%s)' %
                  (self.__class__.__name__, endpoint))

    def get_res_id(self, resource):
        """Returns the Resource ID of a given RightScale Resource object.

        Args:
            rightscale.Resource object

        Returns:
            Integer of Resource ID
        """
        return int(path.split(resource.self.path)[-1])

    @gen.coroutine
    def login(self):
        """Logs into RightScale and populates the object properties.

        This method is not strictly required -- but it helps asynchronously
        pre-populate the object attributes/methods.
        """
        yield utils.thread_coroutine(self._client.login)
        raise gen.Return()

    @gen.coroutine
    def find_server_arrays(self, name, exact=True):
        """Search for a list of ServerArray by name and return the resources.

        Args:
            name: RightScale ServerArray Name
            exact: Return a single exact match, or multiple matching resources.

        Raises:
            gen.Return(rightscale.Resource object(s))
        """
        log.debug('Searching for ServerArrays matching: %s (exact match: %s)' %
                  (name, exact))

        found_arrays = yield utils.thread_coroutine(
            rightscale_util.find_by_name,
            self._client.server_arrays, name, exact=exact)

        if not found_arrays:
            msg = 'ServerArray matching name not found: %s' % name
            log.debug(msg)

        log.debug('Got ServerArray: %s' % found_arrays)

        raise gen.Return(found_arrays)

    @gen.coroutine
    def clone_server_array(self, array):
        """Clone a Server Array.

        Clones an existing Server Array into a new array. Requires the
        source template array ID number. Returns the newly cloned array.

        Args:
            array: Source ServerArray Resource Object

        Raises:
            gen.Return(rightscale.Resource object)
        """
        log.debug('Cloning ServerArray %s' % array.soul['name'])
        source_id = self.get_res_id(array)
        new_array = yield utils.thread_coroutine(
            self._client.server_arrays.clone, res_id=source_id)
        log.debug('New ServerArray %s created!' % new_array.soul['name'])
        raise gen.Return(new_array)

    @gen.coroutine
    def destroy_server_array(self, array):
        """Destroys a Server Array.

        Makes this API Call:

            http://reference.rightscale.com/api1.5/resources/
            ResourceServerArrays.html#destroy

        Args:
            array: ServerArray Resource Object
        """
        log.debug('Destroying ServerArray %s' % array.soul['name'])
        array_id = self.get_res_id(array)
        yield utils.thread_coroutine(
            self._client.server_arrays.destroy, res_id=array_id)
        log.debug('Array Destroyed')
        raise gen.Return()

    @gen.coroutine
    def update_server_array(self, array, params):
        """Updates a ServerArray with the supplied parameters.

        Valid parameters can be found at the following URL:

            http://reference.rightscale.com/api1.5/resources/
            ResourceServerArrays.html#update

        Args:
            array: rightscale.Resource object to update.
            params: The parameters to update. eg:
                { 'server_array[name]': 'new name' }

        Raises:
            gen.Return(<updated rightscale array object>)
        """

        log.debug('Patching ServerArray (%s) with new params: %s' %
                  (array.soul['name'], params))
        yield utils.thread_coroutine(array.self.update, params=params)
        updated_array = yield utils.thread_coroutine(array.self.show)
        raise gen.Return(updated_array)

    @gen.coroutine
    @utils.retry(excs=requests.exceptions.HTTPError, retries=3)
    def launch_server_array(self, array):
        """Launches an instance of a ServerArray..

        Makes this API Call:

            http://reference.rightscale.com/api1.5/resources/
            ResourceServerArrays.html#launch

        Note: Repeated simultaneous calls to this method on the same array will
        return 422 errors from RightScale. It is advised that you make this
        call synchronously on a particular array as many times as you need.
        This method is wrapped in a retry block though to help handle these
        errors anyways.

        Args:
            array: ServerArray Resource Object

        Raises:
            gen.Return(<rightscale.Resource of the newly launched instance>)
        """
        log.debug('Launching a new instance of ServerArray %s' %
                  array.soul['name'])
        array_id = self.get_res_id(array)
        ret = yield utils.thread_coroutine(
            self._client.server_arrays.launch, res_id=array_id)
        raise gen.Return(ret)

    @gen.coroutine
    def get_server_array_current_instances(
            self, array, filter='state!=terminated'):
        """Returns a list of ServerArray current running instances.

        Makes this API Call:

            http://reference.rightscale.com/api1.5/resources/
            ResourceServerArrays.html#current_instances

        Args:
            array: rightscale.Resource object to count
            filter: Filter string to use to find instances.

        Raises:
            gen.Return([<list of rightscale.Resource objects>])
        """
        log.debug('Searching for current instances of ServerArray (%s)' %
                  array.soul['name'])
        params = {'filter[]': [filter]}
        current_instances = yield utils.thread_coroutine(
            array.current_instances.index, params=params)
        raise gen.Return(current_instances)

    @gen.coroutine
    def terminate_server_array_instances(self, array):
        """Executes a terminate on all of the current running instances.

        Makes this API Call:

            http://reference.rightscale.com/api1.5/resources/
            ResourceServerArrays.html#multi_terminate

        Returns as soon as RightScale claims that the operation is completed --
        but this only means that the servers have been 'told' to shut down, not
        that they are actually terminated yet.

        Args:
            array: ServerArray Resource Object

        Raises:
            gen.Return(<action execution resource>)
        """
        log.debug('Terminating all instances of ServerArray (%s)' %
                  array.soul['name'])
        array_id = self.get_res_id(array)
        try:
            task = yield utils.thread_coroutine(
                self._client.server_arrays.multi_terminate, res_id=array_id)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 422:
                # There are no instances to terminate.
                raise gen.Return()

        # We don't care if it succeeded -- the multi-terminate job fails
        # all the time when there are hosts still in a 'terminated state'
        # when this call is made. Just wait for it to finish.
        yield self.wait_for_task(task)

        raise gen.Return()

    @gen.coroutine
    def wait_for_task(self, task, sleep=5):
        """Monitors a RightScale task for completion.

        RightScale tasks are provided as URLs that we can query for the
        run-status of the task. This method repeatedly queries a task for
        completion (every 5 seconds), and returns when the task has finished.

        TODO: Add a task-timeout option.

        Args:
            sleep: Integer of time to wait between status checks

        Raises:
            gen.Return(<booelan>)
        """
        while True:
            # Get the task status
            output = yield utils.thread_coroutine(task.self.show)
            summary = output.soul['summary']
            log.debug('Got updated task: %s' % output.soul)

            if 'success' in summary or 'completed' in summary:
                status = True
                break

            if 'failed' in summary:
                status = False
                break

            if 'queued' not in summary and '%' not in summary:
                status = False
                break

            log.debug('Task waiting: %s' % output.soul['summary'])
            yield gen.Task(ioloop.IOLoop.current().add_timeout,
                           time.time() + sleep)

        log.debug('Task finished, return value: %s, summary: %s' %
                  (status, summary))

        raise gen.Return(status)
