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

from datetime import datetime
from os import path
import logging

from concurrent import futures
from retrying import retry as sync_retry
from rightscale import util as rightscale_util
from tornado import concurrent
from tornado import gen
from tornado import ioloop
import requests
import rightscale
import simplejson

from kingpin import utils

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


DEFAULT_ENDPOINT = 'https://my.rightscale.com'

# This executor is used by the tornado.concurrent.run_on_executor()
# decorator. We would like this to be a class variable so its shared
# across RightScale objects, but we see testing IO errors when we
# do this.
EXECUTOR = futures.ThreadPoolExecutor(10)


class ServerArrayException(Exception):

    """Raised when an operation on or looking for a ServerArray fails"""


class RightScale(object):

    # Get references to existing objects that are used by the
    # tornado.concurrent.run_on_executor() decorator.
    ioloop = ioloop.IOLoop.current()
    executor = EXECUTOR

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

    @concurrent.run_on_executor
    @utils.exception_logger
    def login(self):
        """Logs into RightScale and populates the object properties.

        This method is not strictly required -- but it helps asynchronously
        pre-populate the object attributes/methods.
        """
        self._client.login()

    @concurrent.run_on_executor
    @utils.exception_logger
    def find_server_arrays(self, name, exact=True):
        """Search for a list of ServerArray by name and return the resources.

        Args:
            name: RightScale ServerArray Name
            exact: Return a single exact match, or multiple matching resources.

        Returns:
            <rightscale.Resource object(s)>
        """
        log.debug('Searching for ServerArrays matching: %s (exact match: %s)' %
                  (name, exact))

        found_arrays = rightscale_util.find_by_name(
            self._client.server_arrays, name, exact=exact)

        if not found_arrays:
            log.debug('ServerArray matching "%s" not found' % name)
            return

        log.debug('Got ServerArray: %s' % found_arrays)

        return found_arrays

    @concurrent.run_on_executor
    @utils.exception_logger
    def find_cookbook(self, name):
        """Search for a Cookbook by-name and return the resource.

        Args:
            name: Cookbook Name

        Return:
            rightscale.Resource object
        """
        cookbook = name.split('::')[0]

        log.debug('Searching for Cookbooks matching: %s' % name)
        found_cookbooks = self._client.cookbooks.index(
            params={'filter[]': ['name==%s' % cookbook],
                    'view': 'extended'})
        found_recipes = filter(
            lambda r: r.soul['metadata']['recipes'].get(name),
            found_cookbooks)

        if not found_recipes:
            log.debug('Recipe matching "%s" could not be found.' % name)
            log.debug('Found cookbooks %s' % found_cookbooks)
            return

        recipe = found_recipes[0]

        log.debug('Found recipe: %s' % recipe)

        return recipe

    @concurrent.run_on_executor
    @utils.exception_logger
    def find_right_script(self, name):
        """Search for a RightScript by-name and return the resource.

        Args:
            name: RightScale RightScript Name

        Return:
            rightscale.Resource object
        """
        log.debug('Searching for RightScript matching: %s' % name)
        found_script = rightscale_util.find_by_name(
            self._client.right_scripts, name, exact=True)

        if not found_script:
            log.debug('RightScript matching "%s" could not be found.' % name)
            return

        log.debug('Got RightScript: %s' % found_script)

        return found_script

    @concurrent.run_on_executor
    @utils.exception_logger
    def clone_server_array(self, array):
        """Clone a Server Array.

        Clones an existing Server Array into a new array. Requires the
        source template array ID number. Returns the newly cloned array.

        Args:
            array: Source ServerArray Resource Object

        Return:
            <rightscale.Resource object>
        """
        log.debug('Cloning ServerArray %s' % array.soul['name'])
        source_id = self.get_res_id(array)
        new_array = self._client.server_arrays.clone(res_id=source_id)
        log.debug('New ServerArray %s created!' % new_array.soul['name'])
        return new_array

    @concurrent.run_on_executor
    @utils.exception_logger
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
        self._client.server_arrays.destroy(res_id=array_id)
        log.debug('Array Destroyed')

    @concurrent.run_on_executor
    @utils.exception_logger
    def update_server_array(self, array, params):
        """Updates a ServerArray with the supplied parameters.

        Valid parameters can be found at the following URL:

            http://reference.rightscale.com/api1.5/resources/
            ResourceServerArrays.html#update

        Args:
            array: rightscale.Resource object to update.
            params: The parameters to update. eg:
                { 'server_array[name]': 'new name' }

        Returns:
            <updated rightscale array object>
        """

        log.debug('Patching ServerArray (%s) with new params: %s' %
                  (array.soul['name'], params))
        array.self.update(params=params)
        updated_array = array.self.show()
        return updated_array

    @concurrent.run_on_executor
    @utils.exception_logger
    def get_server_array_inputs(self, array):
        """Looks up ServerArray 'Next Instance' inputs.

        Valid parameters can be found at the following URL:

            http://reference.rightscale.com/api1.5/resources/
            ResourceInputs.html#index

        Args: rightscale.Resource array object.
        Returns:
            List of rightscale.Resource input objects.
        """
        instance = array.next_instance.show()
        all_inputs = instance.inputs.index()

        return all_inputs

    @concurrent.run_on_executor
    @utils.exception_logger
    def update_server_array_inputs(self, array, inputs):
        """Updates a ServerArray 'Next Instance' with the supplied inputs.

        Valid parameters can be found at the following URL:

            http://reference.rightscale.com/api1.5/resources/
            ResourceInputs.html#multi_update

        Note: Its impossible to tell whether the update has succeeded because
        the RightScale API always returns a '204 No Content' message on the
        multi_update() call. Therefore, we simply execute the command return.

        Args:
            array: rightscale.Resource object to update.
            inputs: The parameters to update. eg:
                { 'inputs[ELB_NAME]': 'text:foobar' }
        """

        log.debug('Patching ServerArray (%s) with new inputs: %s' %
                  (array.soul['name'], inputs))

        next_inst = array.next_instance.show()
        next_inst.inputs.multi_update(params=inputs)

    @concurrent.run_on_executor
    @sync_retry(stop_max_attempt_number=10,
                wait_exponential_multiplier=5000,
                wait_exponential_max=60000)
    @utils.exception_logger
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

        Returns:
            rightscale.Resource of the newly launched instance>
        """
        log.debug('Launching a new instance of ServerArray %s' %
                  array.soul['name'])
        array_id = self.get_res_id(array)
        return self._client.server_arrays.launch(res_id=array_id)

    @concurrent.run_on_executor
    @sync_retry(stop_max_attempt_number=10,
                wait_exponential_multiplier=1000,
                wait_exponential_max=10000)
    @utils.exception_logger
    def get_server_array_current_instances(
            self, array, filters=['state<>terminated']):
        """Returns a list of ServerArray current running instances.

        Makes this API Call:

            http://reference.rightscale.com/api1.5/resources/
            ResourceServerArrays.html#current_instances

        Valid Filters:

            http://reference.rightscale.com/api1.5/resources/
            ResourceInstances.html#index_filters

        Args:
            array: rightscale.Resource object to count
            filters: List of filters to use to find instances.

        Returns:
            [<list of rightscale.Resource objects>]
        """
        log.debug('Searching for current instances of ServerArray (%s)' %
                  array.soul['name'])
        params = {'filter[]': filters}
        return array.current_instances.index(params=params)

    @concurrent.run_on_executor
    @utils.exception_logger
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

        Return:
            <task object for termination request>
        """
        log.debug('Terminating all instances of ServerArray (%s)' %
                  array.soul['name'])
        array_id = self.get_res_id(array)
        try:
            task = self._client.server_arrays.multi_terminate(res_id=array_id)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 422:
                # There are no instances to terminate.
                return

        return task

    @gen.coroutine
    def wait_for_task(self,
                      task,
                      task_name=None,
                      sleep=5,
                      loc_log=log,
                      instance=None):
        """Monitors a RightScale task for completion.

        RightScale tasks are provided as URLs that we can query for the
        run-status of the task. This method repeatedly queries a task for
        completion (every 5 seconds), and returns when the task has finished.

        TODO: Add a task-timeout option.

        Note: This is a completely retryable operation in the event that an
        intermittent network connection causes any kind of a connection
        failure.

        Args:
            task: RightScale Task resource object.
            task_name: Human-readable name of the task to be executed.
            sleep: Integer of seconds to wait before the first status check.
            loc_log: logging.getLogger() object to be used to log task status.
                    This is useful when this API call is called from a Kingpin
                    actor, and you want to use the actor's specific logger.
                    If nothing is passed - local `log` object is used.
            instance: RightScale instance object on which the task is executed.

        Returns:
            bool: success status
        """

        if not task:
            # If there is no task to wait on - don't wait!
            raise gen.Return(True)

        timeout_id = None
        if task_name:
            timeout_id = utils.create_repeating_log(
                loc_log.info, 'Still waiting on %s' % task_name, seconds=sleep)

        # Tracking when the tasks start so we can search by date later
        # RightScale expects the time to be a string in UTC
        now = datetime.utcnow()
        tasks_start = now.strftime('%Y/%m/%d %H:%M:%S +0000')

        while True:
            # Get the task status
            output = yield self._get_task_info(task)
            summary = output.soul['summary']
            stamp = datetime.now()

            if 'success' in summary or 'completed' in summary:
                status = True
                break

            if 'failed' in summary:
                status = False
                break

            loc_log.debug('Task (%s) status: %s (updated at: %s)' %
                          (output.path, output.soul['summary'], stamp))

            yield utils.tornado_sleep(min(sleep, 5))

        loc_log.debug('Task (%s) status: %s (updated at: %s)' %
                      (output.path, output.soul['summary'], stamp))

        if timeout_id:
            utils.clear_repeating_log(timeout_id)

        if status is True:
            raise gen.Return(True)

        if not instance:
            raise gen.Return(status)

        # If something failed we want to find out why -- get audit logs

        # Contact RightScale for audit logs of this instance.
        now = datetime.utcnow()
        tasks_finish = now.strftime('%Y/%m/%d %H:%M:%S +0000')

        loc_log.error('Task failed. Instance: "%s".' % instance.soul['name'])

        audit_logs = yield self.get_audit_logs(
            instance=instance,
            start=tasks_start,
            end=tasks_finish,
            match='failed')

        # Print every audit log that was obtained (may be 0)
        [loc_log.error(l) for l in audit_logs]

        if not audit_logs:
            loc_log.error('No audit logs for %s' % instance)

        loc_log.debug('Task finished, return value: %s, summary: %s' %
                      (status, summary))

        raise gen.Return(status)

    @concurrent.run_on_executor
    @sync_retry(stop_max_attempt_number=20,
                wait_exponential_multiplier=1000,
                wait_exponential_max=10000)
    @utils.exception_logger
    def _get_task_info(self, task):
        """Fetch data for a particular RightScale task.

        This is a blocking, non-tornado operation. It's separated into its own
        function to be run on a separate thread.
        """
        return task.self.show()

    @concurrent.run_on_executor
    @sync_retry(stop_max_attempt_number=10,
                wait_exponential_multiplier=5000,
                wait_exponential_max=60000)
    @utils.exception_logger
    def get_audit_logs(self, instance, start, end, match=None):
        """Fetch a set of audit logs belonging to an instance.

        http://reference.rightscale.com/api1.5/resources/
        ResourceAuditEntries.html

        Args:
            instance: RightScale instance object.
            start: String as expected by start_date of the API
                   e.g., 2011/06/25 00:00:00 +0000.
            end: String as expected by end_date of the API.
            match: optional string to match the summary of the audit entry.
                   Only audit entries with this string will be returned.

        Returns:
            list of audit entries between the start and end date that match
            a substring in the summary. May return an empty list.

        """

        href = instance.links['self']
        all_entries = self._client.audit_entries.index(params={
            'filter[]': ['auditee_href==%s' % href],
            'limit': 10,
            'start_date': start,
            'end_date': end
        })

        log.debug('Found %s audit logs.' % len(all_entries))

        logs = []
        for entry in all_entries:
            summary = entry.soul['summary']
            if match and match not in summary:
                log.debug('Skipping details for "%s"' % summary)
                continue
            log.debug('Fetching details for "%s"' % summary)

            # grabbing raw output because RightScale doesn't reply via JSON
            # when accessing details of a log.
            detail_res = self._client.client.get(entry.detail.path)
            details = detail_res.raw_response.text

            logs.append(details)

        return logs

    @gen.coroutine
    def run_executable_on_instances(self, name, inputs, instances):
        """Execute a script on a set of RightScale Instances.

        This method bypasses the python-rightscale native properties and
        callable methods because they are broken with regards to running
        individual API calls against instances. See this bug:

            https://github.com/brantai/python-rightscale/issues/6

        Instead, we take in a list of rightscale.Resource objects that point to
        instances. For each instance we iterate over and directly call the
        <instance_path>/run_executable URL. This is done below in the
        make_generic_request() method for us.

        Note, the inputs dictionary should look like this:
            { '' }

        Args:
            name: Recipe or RightScript String Name
            inputs: Dict of Key/Value Input Pairs
            instances: A list of rightscale.Resource instances objects.

        Returns:
            list of tuples - (instance, <rightscale.Resource task object>)
        """
        # Create a new copy of the inputs that were passed in so that we can
        # modify them correctly and safely.
        params = dict(inputs)

        # Determine whether we're looking for a recipe or a rightscript. If its
        # the latter, we have to go and find its href identifier first.
        if '::' in name:
            script_type = 'Recipe'
            params['recipe_name'] = name
        else:
            script_type = 'RightScript'
            script = yield self.find_right_script(name)

            if not script:
                raise ServerArrayException('RightScript Not Found')

            params['right_script_href'] = script.href

        log.debug('Executing %s with params: %s' % (script_type, params))

        # Generate all the tasks and store them in a list so that we can yield
        # them all at once (thus, making it asynchronous)
        task_pairs = []
        tasks = []
        for i in instances:
            log.debug('Executing %s on %s' % (name, i.soul['name']))
            url = '%s/run_executable' % i.links['self']
            req = self.make_generic_request(url, post=params)
            task_pairs.append((i, req))
            tasks.append(req)

        try:
            yield tasks
        except requests.exceptions.HTTPError as e:
            raise ServerArrayException('Script Execution Error: %s' % e)

        # At this point all the tasks are executed, but the reference
        # that we store in task_pairs are still to the Future objects.
        yielded_tasks = []
        for (i, task) in task_pairs:
            result = yield task  # Should be a no-op since it's completed above
            yielded_tasks.append((i, result))

        raise gen.Return(yielded_tasks)

    @concurrent.run_on_executor
    @utils.exception_logger
    def make_generic_request(self, url, post=None):
        """Make a generic API call and return a Resource Object.

        This method is a bit hacky. It manually executes a REST call against
        the RightScale API and then attempts to build a custom
        rightscale.Resource object based on those return results. This allows
        us to support API calls that the current python-rightscale library does
        not currently support (like running an executable on an instance of an
        array).

        Args:
            url: String of the URL to call
            post: Optional POST Body Data

        Returns:
            <rightscale.Resource object>
        """
        # Make the initial web call
        log.debug('Making generic API call: %s (%s)' % (url, post))

        # Here we're reaching into the rightscale client library and getting
        # access directly to its requests client object.
        if post:
            response = self._client.client.post(url, data=post)
        else:
            response = self._client.client.get(url)

        # Now, if a location tag was returned to us, follow it and get the
        # newly returned response data
        loc = response.headers.get('location', None)
        if loc:
            response = self._client.client.get(loc)
            url = loc

        # Try to parse the JSON body. If no body was returned, this fails and
        # thats OK sometimes.
        try:
            soul = response.json()
        except simplejson.scanner.JSONDecodeError:
            log.debug('No JSON found. Returning None')
            return

        # Now dig deep into the python rightscale library itself and create our
        # own Resource object by hand.
        resource = rightscale.rightscale.Resource(
            path=url,
            response=response,
            soul=soul,
            client=self._client.client)

        return resource
