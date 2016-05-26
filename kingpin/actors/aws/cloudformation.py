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
:mod:`kingpin.actors.aws.cloudformation`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
"""

import logging
import json

from botocore.exceptions import ClientError
from tornado import concurrent
from tornado import gen
from tornado import ioloop

from kingpin import utils
from kingpin.actors import exceptions
from kingpin.actors.utils import dry
from kingpin.actors.aws import base
from kingpin.constants import SchemaCompareBase, StringCompareBase
from kingpin.constants import REQUIRED, STATE

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


# This executor is used by the tornado.concurrent.run_on_executor()
# decorator. We would like this to be a class variable so its shared
# across RightScale objects, but we see testing IO errors when we
# do this.
EXECUTOR = concurrent.futures.ThreadPoolExecutor(10)


class CloudFormationError(exceptions.RecoverableActorFailure):

    """Raised on any generic CloudFormation error."""


class StackFailed(exceptions.RecoverableActorFailure):

    """Raised any time a Stack fails to be created or updated."""


class InvalidTemplate(exceptions.UnrecoverableActorFailure):

    """An invalid CloudFormation template was supplied."""


class StackAlreadyExists(exceptions.RecoverableActorFailure):

    """The requested CloudFormation stack already exists."""


class StackNotFound(exceptions.RecoverableActorFailure):

    """The requested CloudFormation stack does not exist."""


class ParametersConfig(SchemaCompareBase):

    """Validates the Parameters option.

    A valid `parameters` option is a dictionary with simple Key/Value pairs of
    strings. No nested dicts, arrays or other objects.
    """

    SCHEMA = {
        'type': ['object', 'null'],
        'uniqueItems': True,
        'patternProperties': {
            '.*': {
                'type': 'string'
            }

        }
    }

    valid = '{ "key", "value", "key2", "value2" }'


class CapabilitiesConfig(SchemaCompareBase):

    """Validates the Capabilities option.

    The only `capability` option available currently is `CAPABILITY_IAM` -- but
    to support forwards compatibility, you must supply this as as a list.
    """

    SCHEMA = {
        'type': ['array', 'null'],
        'uniqueItems': True,
        'items': {
            'type': 'string',
            'enum': ['CAPABILITY_IAM']
        }
    }
    valid = '[ "CAPABILITY_IAM" ]'


class OnFailureConfig(StringCompareBase):

    """Validates the On Failure option.

    The `on_failure` option can take one of the following settings:
      `DO_NOTHING`, `ROLLBACK`, `DELETE`

    This option is applied at stack _creation_ time!
    """

    valid = ('DO_NOTHING', 'ROLLBACK', 'DELETE')


# CloudFormation has over a dozen different 'stack states'... but for the
# purposes of these actors, we really only care about a few logical states.
# Here we map the raw states into logical states.
COMPLETE = ('CREATE_COMPLETE', 'UPDATE_COMPLETE')
DELETED = ('DELETE_COMPLETE', )
IN_PROGRESS = (
    'CREATE_IN_PROGRESS', 'DELETE_IN_PROGRESS',
    'ROLLBACK_IN_PROGRESS', 'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS',
    'UPDATE_IN_PROGRESS', 'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS',
    'UPDATE_ROLLBACK_IN_PROGRESS')
FAILED = (
    'CREATE_FAILED', 'DELETE_FAILED', 'ROLLBACK_FAILED',
    'UPDATE_ROLLBACK_FAILED', 'ROLLBACK_COMPLETE')


class CloudFormationBaseActor(base.AWSBaseActor):

    """Base Actor for CloudFormation tasks"""

    # Get references to existing objects that are used by the
    # tornado.concurrent.run_on_executor() decorator.
    ioloop = ioloop.IOLoop.current()

    executor = EXECUTOR

    # Used mainly for unit testing..
    all_options = {
        'region': (str, REQUIRED, 'AWS region (or zone) name, like us-west-2')
    }

    def _get_template_body(self, template):
        """Reads in a local template file and returns the contents.

        If the template string supplied is a local file resource (has no
        URI prefix), then this method will return the contents of the file.
        Otherwise, returns None.

        Args:
            template: String with a reference to a template location.

        Returns:
            One tuple of:
              (Contents of template file, None)
              (None, URL of template)

        Raises:
            InvalidTemplate
        """
        if template is None:
            return (None, None)

        remote_types = ('http://', 'https://')

        if template.startswith(remote_types):
            return (None, template)

        try:
            return (json.dumps(self._parse_policy_json(template)), None)
        except exceptions.UnrecoverableActorFailure as e:
            raise InvalidTemplate(e)

    @gen.coroutine
    def _validate_template(self, body=None, url=None):
        """Validates the CloudFormation template.

        args:
          body: The body of the template
          url: A URL pointing to a template

        Raises:
            InvalidTemplate
            exceptions.InvalidCredentials
        """

        if body is not None:
            cfg = {'TemplateBody': body}
            self.log.info('Validating template with AWS...')
            try:
                yield self.thread(self.cf3_conn.validate_template, **cfg)
            except ClientError as e:
                raise InvalidTemplate(e.message)

        if url is not None:
            cfg = {'TemplateURL': url}
            self.log.info('Validating template (%s) with AWS...' % url)
            try:
                yield self.thread(self.cf3_conn.validate_template, **cfg)
            except ClientError as e:
                raise InvalidTemplate(e.message)

    def _create_parameters(self, parameters, use_previous_value=False):
        """Converts a simple Key/Value dict into Amazon CF Parameters.

        The Boto3 interface requires that Parameters are passed in like this:

        .. code-block:: python
            Parameters=[
                { 'ParameterKey': 'string',
                  'ParameterValue': 'string',
                  'UsePreviousValue': True|False
                },
            ]

        This method takes a simple Dict of Key/Value pairs and converts it into
        the above format.

        Args:
            parameters: A dict of key/values
            use_previous_value: During a Stack Update, use the New values or
                                the Previous values?

        Returns:
            A dict like above
        """

        new_params = [
            {'ParameterKey': k,
             'ParameterValue': v,
             'UsePreviousValue': use_previous_value}
            for k, v in parameters.items()]
        sorted_params = sorted(new_params, key=lambda k: k['ParameterKey'])
        return sorted_params

    @gen.coroutine
    def _get_stack(self, stack):
        """Returns a cloudformation.Stack object of the requested stack.

        If a "stack name" is supplied, Amazon returns only stacks that are
        "live" -- it does not return deleted stacks. If a "stack id" is used,
        Amazon will return the deleted stack as well.

        Args:
            stack: Stack name or stack ID

        Returns
            <Stack Dict> or <None>
        """
        try:
            stacks = yield self.thread(self.cf3_conn.describe_stacks,
                                       StackName=stack)
        except ClientError as e:
            if 'does not exist' in e.message:
                raise gen.Return(None)

            raise CloudFormationError(e)

        raise gen.Return(stacks['Stacks'][0])

    @gen.coroutine
    def _wait_until_state(self, stack_name, desired_states, sleep=15):
        """Indefinite loop until a stack has finished creating/deleting.

        Whether the stack has failed, suceeded or been rolled back... this
        method loops until the process has finished. If the final status is a
        failure (rollback/failed) then an exception is raised.

        Args:
            stack_name: The stack name or stack ID to watch
            desired_states: (tuple/list) States that indicate a successful
                            operation.
            sleep: (int) Time in seconds between stack status checks

        Raises:
            StackNotFound: If the stack doesn't exist.
        """
        while True:
            stack = yield self._get_stack(stack_name)

            if not stack:
                msg = 'Stack "%s" not found.' % self.option('name')
                raise StackNotFound(msg)

            # First, lets see if the stack is still in progress (either
            # creation, deletion, or rollback .. doesn't really matter)
            if stack['StackStatus'] in IN_PROGRESS:
                self.log.info('Stack is in %s, waiting %s(s)...' %
                              (stack['StackStatus'], sleep))
                yield utils.tornado_sleep(sleep)
                continue

            # If the stack is in the desired state, then return
            if stack['StackStatus'] in desired_states:
                self.log.info('Stack state: %s' % stack['StackStatus'])
                raise gen.Return()

            # Lastly, if we get here, then something is very wrong and we got
            # some funky status back. Throw an exception.
            msg = 'Unxpected stack state received (%s)' % stack['StackStatus']
            raise StackFailed(msg)

    @gen.coroutine
    def _get_stack_events(self, stack):
        """Returns a list of human-readable CF Events.

        Searches for all of the Stack events for a given CF Stack and returns
        them in a human-readable list of strings.

        http://docs.aws.amazon.com/AWSCloudFormation/latest/
        APIReference/API_DescribeStackEvents.html

        args:
            stack: Stack ID or Stack name

        returns:
            [<list of human readable strings>]
        """
        try:
            raw = yield self.thread(
                self.cf3_conn.describe_stack_events, StackName=stack)
        except ClientError:
            raise gen.Return([])

        # Reverse the list, and iterate through the data
        events = []
        for event in raw['StackEvents'][::-1]:
            # Not every event has a "reason" ... for those, we add a blank reason
            # value just to make string formatting easier below.
            if 'ResourceStatusReason' not in event:
                event['ResourceStatusReason'] = ''

            log_string_fmt = (
                '{ResourceType} {LogicalResourceId} '
                '({ResourceStatus}): {ResourceStatusReason}'
            )

            events.append(log_string_fmt.format(**event))

        raise gen.Return(events)

    @gen.coroutine
    @dry('Would have deleted stack {stack}')
    def _delete_stack(self, stack):
        """Executes the stack deletion."""

        exists = yield self._get_stack(stack)
        if not exists:
            raise StackNotFound('Stack does not exist!')

        self.log.info('Deleting stack')
        try:
            ret = yield self.thread(
                self.cf3_conn.delete_stack, StackName=stack)
        except ClientError as e:
            raise CloudFormationError(e.message)

        req_id = ret['ResponseMetadata']['RequestId']
        self.log.info('Stack delete requested: %s' % req_id)

        # Now wait until the stack creation has finished
        try:
            yield self._wait_until_state(exists['StackId'], DELETED)
        except StackNotFound:
            # Pass here because a stack not found exception is totally
            # reasonable since we're deleting the stack. Sometimes Amazon
            # actually deletes the stack immediately, and othertimes it lists
            # the stack as a 'deleted' state, but we still get that state back.
            # Either case is fine.
            pass

    @gen.coroutine
    @dry('Would have created stack {stack}')
    def _create_stack(self, stack):
        """Executes the stack creation."""
        # Create the stack, and get its ID.
        self.log.info('Creating stack %s' % stack)

        if self._template_body:
            cfg = {'TemplateBody': self._template_body}
        else:
            cfg = {'TemplateURL': self._template_url}

        try:
            stack = yield self.thread(
                self.cf3_conn.create_stack,
                StackName=stack,
                Parameters=self._parameters,
                OnFailure=self.option('on_failure'),
                TimeoutInMinutes=self.option('timeout_in_minutes'),
                Capabilities=self.option('capabilities'),
                **cfg)
        except ClientError as e:
            raise CloudFormationError(e.message)

        # Now wait until the stack creation has finished. If the creation
        # fails, get the logs from Amazon for the user.
        try:
            yield self._wait_until_state(stack['StackId'], COMPLETE)
        except StackFailed as e:
            events = yield self._get_stack_events(stack['StackId'])
            for e in events:
                self.log.error(e)
            msg = 'Stack creation failed: %s' % events
            raise StackFailed(msg)

        self.log.info('Stack created: %s' % stack['StackId'])

        raise gen.Return(stack['StackId'])


class Create(CloudFormationBaseActor):

    """Creates a CloudFormation stack.

    Creates a CloudFormation stack from scratch and waits until the stack is
    fully built before exiting the actor.

    **Options**

    :name:
      The name of the queue to create

    :capabilities:
      A list of CF capabilities to add to the stack.

    :on_failure:
     (:py:class:`OnFailureConfig`)

     One of the following strings: `DO_NOTHING`, `ROLLBACK`, `DELETE`

     Default: `DELETE`

    :parameters:
      A dictionary of key/value pairs used to fill in the parameters for the
      CloudFormation template.

    :region:
      AWS region (or zone) string, like 'us-west-2'

    :template:
      String of path to CloudFormation template. Can either be in the form of a
      local file path (ie, `./my_template.json`) or a URI (ie
      `https://my_site.com/cf.json`).

    :timeout_in_minutes:
      The amount of time that can pass before the stack status becomes
      CREATE_FAILED.

    **Examples**

    .. code-block:: json

       { "desc": "Create production backend stack",
         "actor": "aws.cloudformation.Create",
         "options": {
           "capabilities": [ "CAPABILITY_IAM" ],
           "name": "%CF_NAME%",
           "parameters": {
             "test_param": "%TEST_PARAM_NAME%",
           },
           "region": "us-west-1",
           "template": "/examples/cloudformation_test.json",
           "timeout_in_minutes": 45,
         }
       }

    **Dry Mode**

    Validates the template, verifies that an existing stack with that name does
    not exist. Does not create the stack.
    """

    all_options = {
        'capabilities': (list, [],
                         'The list of capabilities that you want to allow '
                         'in the stack'),
        'on_failure': (OnFailureConfig, 'DELETE',
                       'Action to take if the stack fails to be created'),
        'name': (str, REQUIRED, 'Name of the stack'),
        'parameters': (ParametersConfig, {}, 'Parameters passed into the CF '
                                             'template execution'),
        'region': (str, REQUIRED, 'AWS region (or zone) name, like us-west-2'),
        'template': (str, REQUIRED,
                     'Path to the AWS CloudFormation File. http(s)://, '
                     'file:///, absolute or relative file paths.'),
        'timeout_in_minutes': (int, 60,
                               'The amount of time that can pass before the '
                               'stack status becomes CREATE_FAILED'),
    }

    desc = "Creating CloudFormation Stack {name}"

    def __init__(self, *args, **kwargs):
        """Initialize our object variables."""
        super(Create, self).__init__(*args, **kwargs)

        # Convert our supplied parameters into a properly formatted dict
        self._parameters = self._create_parameters(self.option('parameters'))

        # Check if the supplied CF template is a local file. If it is, read it
        # into memory.
        (self._template_body, self._template_url) = self._get_template_body(
            self.option('template'))

    @gen.coroutine
    def _execute(self):
        stack_name = self.option('name')

        yield self._validate_template(
            self._template_body,
            self._template_url)

        # If a stack already exists, we cannot re-create it. Raise a
        # recoverable exception and let the end user decide whether this is bad
        # or not.
        exists = yield self._get_stack(stack_name)
        if exists:
            raise StackAlreadyExists('Stack %s already exists!' % stack_name)

        # If we're in dry mode, exit at this point. We can't do anything
        # further to validate that the creation process will work.
        if self._dry:
            self.log.info('Skipping CloudFormation Stack creation.')
            raise gen.Return()

        # Create the stack
        yield self._create_stack(stack=stack_name)

        raise gen.Return()


class Delete(CloudFormationBaseActor):

    """Deletes a CloudFormation stack

    **Options**

    :name:
      The name of the queue to create

    :region:
      AWS region (or zone) string, like 'us-west-2'

    **Examples**

    .. code-block:: json

       { "desc": "Delete production backend stack",
         "actor": "aws.cloudformation.Create",
         "options" {
           "region": "us-west-1",
           "name": "%CF_NAME%",
         }
       }

    **Dry Mode**

    Validates that the CF stack exists, but does not delete it.
    """

    all_options = {
        'name': (str, REQUIRED, 'Name of the stack'),
        'region': (str, REQUIRED, 'AWS region (or zone) name, like us-west-2')
    }

    desc = "Deleting CloudFormation Stack {name}"

    @gen.coroutine
    def _execute(self):
        stack_name = self.option('name')
        yield self._delete_stack(stack=stack_name)


class Stack(CloudFormationBaseActor):

    """Manages the state of a CloudFormation stack.

    This actor can manage the following aspects of a CloudFormation stack in
    Amazon:

      * Ensure that the Stack is present or absent.
      * Manage the CF Capabilities

    **Options**

    :name:
      The name of the queue to create

    :state:
      (str) Present or Absent. Default: "present"

    :capabilities:
      (:py:class:`CapabilitiesConfig`, None)

      A list of CF capabilities to add to the stack.

    :disable_rollback:
      Set to True to disable rollback of the stack if creation failed.

    :on_failure:
     (:py:class:`OnFailureConfig`, None)

     One of the following strings: `DO_NOTHING`, `ROLLBACK`, `DELETE`

     Default: `DELETE`

    :parameters:
      (:py:class:`ParametersConfig`, None)

      A dictionary of key/value pairs used to fill in the parameters for the
      CloudFormation template.

    :region:
      AWS region (or zone) string, like 'us-west-2'

    :template:
      String of path to CloudFormation template. Can either be in the form of a
      local file path (ie, `./my_template.json`) or a URI (ie
      `https://my_site.com/cf.json`).

    :timeout_in_minutes:
      The amount of time that can pass before the stack status becomes
      CREATE_FAILED.

    **Examples**

    .. code-block:: json

       { "actor": "aws.cloudformation.Create",
         "state": "present",
         "options": {
           "capabilities": [ "CAPABILITY_IAM" ],
           "on_failure": "DELETE",
           "name": "%CF_NAME%",
           "parameters": {
             "test_param": "%TEST_PARAM_NAME%",
           },
           "region": "us-west-1",
           "template": "/examples/cloudformation_test.json",
           "timeout_in_minutes": 45,
         }
       }

    **Dry Mode**

    Validates the template, verifies that an existing stack with that name does
    not exist. Does not create the stack.
    """

    all_options = {
        'name': (str, REQUIRED, 'Name of the stack'),
        'state': (STATE, 'present',
                  'Desired state of the bucket: present/absent'),
        'capabilities': (CapabilitiesConfig, [],
                         'The list of capabilities that you want to allow '
                         'in the stack'),
        'disable_rollback': (bool, False,
                             'Set to `True` to disable rollback of the stack '
                             'if stack creation failed.'),
        'on_failure': (OnFailureConfig, 'DELETE',
                       'Action to take if the stack fails to be created'),
        'parameters': (ParametersConfig, {}, 'Parameters passed into the CF '
                                             'template execution'),
        'region': (str, REQUIRED, 'AWS region (or zone) name, like us-west-2'),
        'template': (str, REQUIRED,
                     'Path to the AWS CloudFormation File. http(s)://, '
                     'file:///, absolute or relative file paths.'),
        'timeout_in_minutes': (int, 60,
                               'The amount of time that can pass before the '
                               'stack status becomes CREATE_FAILED'),
    }

    desc = 'CloudFormation Stack {name}'

    def __init__(self, *args, **kwargs):
        """Initialize our object variables."""
        super(Stack, self).__init__(*args, **kwargs)

        # Convert our supplied parameters into a properly formatted dict
        self._parameters = self._create_parameters(self.option('parameters'))

        # Check if the supplied CF template is a local file. If it is, read it
        # into memory.
        (self._template_body, self._template_url) = self._get_template_body(
            self.option('template'))

    @gen.coroutine
    def _update_stack(self, stack):
        self.log.info('Verifying that stack is in desired state')

        # Upon a stack creation, there are two states the stack can be left in
        # that are both un-fixable -- CREATE_FAILED and ROLLBACK_COMPLETE. In
        # both of these cases, the only possible option is to destroy the stack
        # and re-create it, you cannot fix a broken stack.
        if stack['StackStatus'] in ('CREATE_FAILED', 'ROLLBACK_COMPLETE'):
            self.log.warning(
                'Stack found in a failed state: %s' % stack['StackStatus'])
            yield self._delete_stack(stack=stack['StackId'])
            yield self._create_stack(stack=stack['StackName'])
            raise gen.Return()

    @gen.coroutine
    def _ensure_stack(self):
        state = self.option('state')
        stack_name = self.option('name')

        self.log.info('Ensuring that CF Stack %s is %s' %
                      (stack_name, state))

        # Figure out if the stack already exists or not. In this case, we
        # ignore DELETED stacks because they don't apply or block you from
        # creating a new stack.
        stack = yield self._get_stack(stack_name)

        # Before we figure out what to do, lets make sure the stack isn't in a
        # mutating state.
        if stack:
            yield self._wait_until_state(stack['StackId'],
                                         (COMPLETE + FAILED + DELETED))

        # Determine the current state of the stack vs the desired state
        if state == 'absent' and stack is None:
            self.log.debug('Stack does not exist')
        elif state == 'absent' and stack:
            yield self._delete_stack(stack=stack_name)
        elif state == 'present' and stack is None:
            stack = yield self._create_stack(stack=stack_name)
        elif state == 'present' and stack:
            stack = yield self._update_stack(stack)

        raise gen.Return(stack)

    @gen.coroutine
    def _execute(self):
        # Before we do anything, validate that the supplied template body or
        # url is valid. If its not, an exception is raised.
        yield self._validate_template(
            self._template_body,
            self._template_url)

        # This main method triggers the creation, deletion or update of the
        # stack as necessary.
        yield self._ensure_stack()
