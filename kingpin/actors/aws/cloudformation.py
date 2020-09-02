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
:mod:`kingpin.actors.aws.cloudformation`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
"""

import json
import logging
import re
import uuid
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from tornado import concurrent
from tornado import gen
from tornado import ioloop

from kingpin import utils
from kingpin.actors import exceptions
from kingpin.actors.aws import base
from kingpin.actors.utils import dry
from kingpin.constants import REQUIRED, STATE
from kingpin.constants import SchemaCompareBase, StringCompareBase

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


# This executor is used by the tornado.concurrent.run_on_executor()
# decorator. We would like this to be a class variable so its shared
# across RightScale objects, but we see testing IO errors when we
# do this.
EXECUTOR = concurrent.futures.ThreadPoolExecutor(10)


S3_REGEX = re.compile(r's3://(?P<bucket>[a-z0-9.-]+)/(?P<key>.*)')


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

    """Validates the Capabilities option"""

    SCHEMA = {
        'type': ['array', 'null'],
        'uniqueItems': True,
        'items': {
            'type': 'string',
            'enum': ['CAPABILITY_IAM',
                     'CAPABILITY_NAMED_IAM',
                     'CAPABILITY_AUTO_EXPAND']
        }
    }
    valid = '[ "CAPABILITY_IAM", "CAPABILITY_NAMED_IAM" ]'


class OnFailureConfig(StringCompareBase):

    """Validates the On Failure option.

    The `on_failure` option can take one of the following settings:
    `DO_NOTHING`, `ROLLBACK`, `DELETE`

    This option is applied at stack _creation_ time!
    """

    valid = ('DO_NOTHING', 'ROLLBACK', 'DELETE')


class TerminationProtectionConfig(StringCompareBase):

    """Validates the TerminationProtectionConfig option.

    The `enable_termination_protection` option can take one of the following
    settings:
    `'UNCHANGED'`, `False`, `True`

    `UNCHANGED` means on Create Stack it will default to False, however on
     Ensure Stack no changes will be applied.
    """

    valid = ('UNCHANGED', True, False)


# CloudFormation has over a dozen different 'stack states'... but for the
# purposes of these actors, we really only care about a few logical states.
# Here we map the raw states into logical states.
COMPLETE = (
    'CREATE_COMPLETE', 'UPDATE_COMPLETE', 'UPDATE_ROLLBACK_COMPLETE',
    'IMPORT_COMPLETE', 'IMPORT_ROLLBACK_COMPLETE')
DELETED = ('DELETE_COMPLETE', )
IN_PROGRESS = (
    'CREATE_PENDING', 'CREATE_IN_PROGRESS', 'DELETE_IN_PROGRESS',
    'EXECUTE_IN_PROGRESS', 'ROLLBACK_IN_PROGRESS',
    'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS', 'UPDATE_IN_PROGRESS',
    'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS',
    'UPDATE_ROLLBACK_IN_PROGRESS', 'IMPORT_IN_PROGRESS',
    'IMPORT_ROLLBACK_IN_PROGRESS')
FAILED = (
    'CREATE_FAILED', 'DELETE_FAILED', 'ROLLBACK_FAILED',
    'UPDATE_ROLLBACK_FAILED', 'ROLLBACK_COMPLETE',
    'IMPORT_ROLLBACK_FAILED')


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

    def _discover_noecho_params(self, template_body):
        """Scans a CF template for NoEcho parameters.

        Searches through a CloudFormation stack template body for any
        parameters that are defined with the NoEcho flag. If there are any,
        returns a list of those parameter names.

        Args:
            template_body: (Str) CloudFormation Template Body

        Returns:
            A list of parameters that have NoEcho set to True
        """
        template = json.loads(template_body)
        stack_params = template.get('Parameters', {})
        noecho_params = [k for k in stack_params if
                         stack_params[k].get('NoEcho', False) is True]
        return noecho_params

    def _discover_default_params(self, template_body):
        """Scans a CF template for Default parameters.

        Searches through a CloudFormation stack template body for any
        parameters that are defined with the Default flag. If there are any,
        returns a dict of those parameter names mapped to their default values.

        Args:
            template_body: (Str) CloudFormation Template Body

        Returns:
            A dict of parameters with defaults mapped to their default values
        """
        template = json.loads(template_body)
        stack_params = template.get('Parameters', {})
        default_params = {
            k: stack_params[k]['Default'] for k in stack_params if
            stack_params[k].get('Default', None) is not None
        }
        return default_params

    def _get_template_body(self, template: str, s3_region: Optional[str]):
        """Reads in a local template file and returns the contents.

        If the template string supplied is a local file resource (has no
        URI prefix), then this method will return the contents of the file.
        Otherwise, returns None.

        Args:

        Returns:
          (Contents of template file, None)
          (Contents of template downloaded from s3, URL of template)

        Raises:
            InvalidTemplate
        """
        if template is None:
            return None, None

        if template.startswith('s3://'):
            match = S3_REGEX.match(template)
            if match:
                bucket = match.group('bucket')
                key = match.group('key')
            else:
                raise InvalidTemplate()

            # figure out the region the bucket is in
            if s3_region is None:
                log.debug(f'Getting region for bucket {bucket}')
                resp = self.s3_conn.get_bucket_location(Bucket=bucket)
                s3_region = resp['LocationConstraint']
                if s3_region is None:
                    s3_region = 'us-east-1'
            # AWS has a multitude of different s3 url formats, but not all are
            # supported. Use this one.
            url = f'https://{bucket}.s3.{s3_region}.amazonaws.com/{key}'

            s3 = self.get_s3_client(s3_region)
            log.debug('Downloading template stored in s3')
            try:
                resp = s3.get_object(Bucket=bucket, Key=key)
            except ClientError as e:
                raise InvalidTemplate(e)
            remote_template = resp['Body'].read()
            return remote_template, url
        else:
            # The template is provided inline.
            try:
                return json.dumps(self._parse_policy_json(template)), None
            except exceptions.UnrecoverableActorFailure as e:
                raise InvalidTemplate(e)

    def get_s3_client(self, region):
        """Get a boto3 S3 client for a given region.

        If the CFN template is stored in S3, we need to download it.  The
        bucket may be in a different region than self.s3_conn, so get a
        connection that is definitely in the correct region.
        """
        return boto3.client('s3', region_name=region)

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

        if url is not None:
            cfg = {'TemplateURL': url}
            self.log.info('Validating template (%s) with AWS...' % url)
            try:
                yield self.api_call(self.cf3_conn.validate_template, **cfg)
            except ClientError as e:
                raise InvalidTemplate(e)
        elif body is not None:
            cfg = {'TemplateBody': body}
            self.log.info('Validating template with AWS...')
            try:
                yield self.api_call(self.cf3_conn.validate_template, **cfg)
            except ClientError as e:
                raise InvalidTemplate(e)

    def _create_parameters(self, parameters):
        """Converts a simple Key/Value dict into Amazon CF Parameters.

        The Boto3 interface requires that Parameters are passed in like this:

        .. code-block:: python
            Parameters=[
                { 'ParameterKey': 'string',
                  'ParameterValue': 'string',
                },
            ]

        This method takes a simple Dict of Key/Value pairs and converts it into
        the above format.

        Args:
            parameters: A dict of key/values

        Returns:
            A list like above
        """

        new_params = [
            {'ParameterKey': k,
             'ParameterValue': v}
            for k, v in list(parameters.items())]
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
            stacks = yield self.api_call_with_queueing(
                self.cf3_conn.describe_stacks,
                queue_name='describe_stacks',
                StackName=stack)
        except ClientError as e:
            if 'does not exist' in str(e):
                raise gen.Return(None)

            raise CloudFormationError(e)

        raise gen.Return(stacks['Stacks'][0])

    @gen.coroutine
    def _get_stack_template(self, stack):
        """Returns the live policy attached to a CF Stack.

        args:
            stack: Stack name or stack ID
        """
        try:
            ret = yield self.api_call(self.cf3_conn.get_template,
                                      StackName=stack,
                                      TemplateStage='Original')
        except ClientError as e:
            raise CloudFormationError(e)

        raise gen.Return(ret['TemplateBody'])

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
                self.log.info('Stack state is %s, waiting %s(s)...' %
                              (stack['StackStatus'], sleep))
                yield utils.tornado_sleep(sleep)
                continue

            # If the stack is in the desired state, then return
            if stack['StackStatus'] in desired_states:
                self.log.debug('Found Stack state: %s' % stack['StackStatus'])
                raise gen.Return()

            # Lastly, if we get here, then something is very wrong and we got
            # some funky status back. Throw an exception.
            msg = 'Unexpected Stack state (StackStatus) received (%s): %s' % (
                stack['StackStatus'],
                stack.get('StackStatusReason',
                          'StackStatusReason not provided.'))
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
            raw = yield self.api_call(
                self.cf3_conn.describe_stack_events, StackName=stack)
        except ClientError:
            raise gen.Return([])

        # Reverse the list, and iterate through the data
        events = []
        for event in raw['StackEvents'][::-1]:
            # Not every event has a "reason" ... for those, we add a blank
            # reason value just to make string formatting easier below.
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
            ret = yield self.api_call(
                self.cf3_conn.delete_stack, StackName=stack)
        except ClientError as e:
            raise CloudFormationError(str(e))

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

        cfg = dict()
        if self._template_url:
            cfg['TemplateURL'] = self._template_url
        else:
            cfg['TemplateBody'] = self._template_body

        if self.option('role_arn'):
            cfg['RoleARN'] = self.option('role_arn')

        enable_termination_protection = self.option(
            'enable_termination_protection')
        if enable_termination_protection == 'UNCHANGED':
            enable_termination_protection = False

        try:
            stack = yield self.api_call(
                self.cf3_conn.create_stack,
                StackName=stack,
                Parameters=self._parameters,
                OnFailure=self.option('on_failure'),
                TimeoutInMinutes=self.option('timeout_in_minutes'),
                Capabilities=self.option('capabilities'),
                EnableTerminationProtection=enable_termination_protection,
                **cfg)
        except ClientError as e:
            raise CloudFormationError(str(e))

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
      AWS region (or zone) string, like 'us-west-2'.

    :role_arn:
      The Amazon IAM Role to use when executing the stack.

    :template:
      String of path to CloudFormation template. Can either be in the form of a
      local file path (ie, `./my_template.json`) or a URI (ie
      `s3://bucket-name/cf.json`).

    :timeout_in_minutes:
      The amount of time that can pass before the stack status becomes
      CREATE_FAILED.

    :enable_termination_protection:
      Whether termination protection is enabled for the stack.

    **Examples**

    .. code-block:: json

       {
         "actor": "aws.cloudformation.Create",
         "desc": "Create production backend stack",
         "options": {
           "capabilities": [ "CAPABILITY_IAM" ],
           "name": "%CF_NAME%",
           "parameters": {
             "test_param": "%TEST_PARAM_NAME%",
           },
           "region": "us-west-1",
           "role_arn": "arn:aws:iam::123456789012:role/DeployRole",
           "template": "/examples/cloudformation_test.json",
           "timeout_in_minutes": 45,
           "enable_termination_protection": true,
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
        'role_arn': (str, None,
                     'The Amazon IAM Role to use when executing the stack'),
        'template': (str, REQUIRED,
                     'Path to the AWS CloudFormation File. s3://, '
                     'file:///, absolute or relative file paths.'),
        'template_s3_region': (str, None,
                               'Region of the bucket containing template'),
        'timeout_in_minutes': (int, 60,
                               'The amount of time that can pass before the '
                               'stack status becomes CREATE_FAILED'),
        'enable_termination_protection': (TerminationProtectionConfig,
                                          'UNCHANGED',
                                          'Whether termination protection is '
                                          'enabled for the stack.')
    }

    desc = "Creating CloudFormation Stack {name}"

    def __init__(self, *args, **kwargs):
        """Initialize our object variables."""
        super(Create, self).__init__(*args, **kwargs)

        # Convert our supplied parameters into a properly formatted list.
        self._parameters = self._create_parameters(self.option('parameters'))

        # Check if the supplied CF template is a local file. If it is, read it
        # into memory.
        self._template_body, self._template_url = self._get_template_body(
            self.option('template'),
            self.option('template_s3_region'),
        )

    @gen.coroutine
    def _execute(self):
        stack_name = self.option('name')

        yield self._validate_template(self._template_body, self._template_url)

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
      * Monitor and update the stack Template and Parameters as necessary.

    **Default Parameters**

    If your CF stack defines parameters with defaults, Kingpin will use the
    defaults unless the parameters are explicitly specified.

    **NoEcho Parameters**

    If your CF stack takes a Password as a parameter or any other value thats
    secret and you set `NoEcho: True` on that parameter, Kingpin will be unable
    to diff it and compare whether or not the desired setting matches whats in
    Amazon. A warning will be thrown, and the rest of the actor will continue
    to operate as normal.

    If any other difference triggers a Stack Update, the desired value for the
    parameter with `NoEcho: True` will be pushed in addition to all of the
    other stack parameters.

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
      AWS region (or zone) string, like 'us-west-2'.

    :role_arn:
      The Amazon IAM Role to use when executing the stack.

    :template:
      String of path to CloudFormation template. Can either be in the form of a
      local file path (ie, `./my_template.json`) or a URI (ie
      `s3://bucket-name/cf.json`).

    :timeout_in_minutes:
      The amount of time that can pass before the stack status becomes
      CREATE_FAILED.

    :enable_termination_protection:
      Whether termination protection is enabled for the stack.

    **Examples**

    .. code-block:: json

       {
         "actor": "aws.cloudformation.Stack",
         "desc": "Manages the state of a CloudFormation stack",
         "options": {
           "capabilities": [ "CAPABILITY_IAM" ],
           "on_failure": "DELETE",
           "name": "%CF_NAME%",
           "parameters": {
             "test_param": "%TEST_PARAM_NAME%",
           },
           "region": "us-west-1",
           "role_arn": "arn:aws:iam::123456789012:role/DeployRole",
           "state": "present",
           "template": "/examples/cloudformation_test.json",
           "timeout_in_minutes": 45,
           "enable_termination_protection": true,
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
        'role_arn': (str, None,
                     'The Amazon IAM Role to use when executing the stack'),
        'template': (str, REQUIRED,
                     'Path to the AWS CloudFormation File. s3://, '
                     'file:///, absolute or relative file paths.'),
        'template_s3_region': (str, None,
                               'Region of the bucket containing template'),
        'timeout_in_minutes': (int, 60,
                               'The amount of time that can pass before the '
                               'stack status becomes CREATE_FAILED'),
        'enable_termination_protection': (TerminationProtectionConfig,
                                          'UNCHANGED',
                                          'Whether termination protection is '
                                          'enabled for the stack.')
    }

    desc = 'CloudFormation Stack {name}'

    def __init__(self, *args, **kwargs):
        """Initialize our object variables."""
        super(Stack, self).__init__(*args, **kwargs)

        # Check if the supplied CF template is a local file. If it is, read it
        # into memory.
        self._template_body, self._template_url = self._get_template_body(
            self.option('template'),
            self.option('template_s3_region'),
        )

        # Find any Default parameters embedded in the stack.
        _default_params = self._discover_default_params(self._template_body)

        # Convert Default parameters and our supplied parameters into a
        # properly formatted list.
        # Defaults will be overridden by supplied parameters.
        self._parameters = self._create_parameters(
            dict(_default_params, **self.option('parameters')))

        # Discover whether or not there are any NoEcho parameters embedded in
        # the stack. If there are, record them locally and throw a warning to
        # the user about it.
        self._noecho_params = self._discover_noecho_params(self._template_body)
        for p in self._noecho_params:
            self.log.warning('Parameter "%s" has NoEcho set to True. '
                             'Will not use in parameter comparison.' % p)

    @gen.coroutine
    def _update_stack(self, stack):
        self.log.info('Verifying that stack is in desired state')

        # First, check that this stack isn't one that may have failed before
        # and there was attempted to be deleted but failed. If it is, we have a
        # fatal error and we must raise an exception.
        if stack['StackStatus'] == 'DELETE_FAILED':
            msg = 'Stack found in a deleted failed state: %s' % (
                stack['StackStatus'])
            raise StackFailed(msg)

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

        # Compare the live and new EnableTerminationProtection parameter and
        # update it if it is different.
        yield self._ensure_termination_protection(stack)

        # Pull down the live stack template and compare it to the one we have
        # locally.
        yield self._ensure_template(stack)

    @gen.coroutine
    def _ensure_template(self, stack):
        """Compares and updates the state of a CF Stack template

        Compares the current template body against the template body for the
        live running stack. If they're different. Triggers a Change Set
        creation and ultimately executes the change set.

        TODO: Support remote template_url comparison!

        args:
            stack: A Boto3 Stack object
        """
        needs_update = False

        # Get the current template for the stack, and get our local template
        # body. Make sure they're in the same form (dict).
        existing = yield self._get_stack_template(stack['StackId'])
        new = json.loads(self._template_body)

        # Compare the two templates. If they differ at all, log it out for the
        # user and flip the needs_update bit.
        diff = utils.diff_dicts(existing, new)
        if diff:
            self.log.warning('Stack templates do not match.')
            for line in diff.split('\n'):
                self.log.info('Diff: %s' % line)

            # Plan to make a change set!
            needs_update = True

        # Get and compare the parameters we have vs the ones in CF. If they're
        # different, plan to do an update!
        if self._diff_params_safely(
                stack.get('Parameters', []),
                self._parameters):
            needs_update = True

        # If needs_update isn't set, then the templates are the same and we can
        # bail!
        if not needs_update:
            self.log.debug('Stack matches configuration, no changes necessary')
            raise gen.Return()

        # If we're here, the templates have diverged. Generate the change set,
        # log out the changes, and execute them.
        change_set_req = yield self._create_change_set(stack)
        change_set = yield self._wait_until_change_set_ready(
            change_set_req['Id'], 'Status', 'CREATE_COMPLETE')
        self._print_change_set(change_set)

        # Ok run the change set itself!
        try:
            yield self._execute_change_set(
                change_set_name=change_set_req['Id'])
        except (ClientError, StackFailed) as e:
            raise StackFailed(e)

        # In dry mode, delete our change set so we don't leave it around as
        # cruft. THis isn't necessary in the real run, because the changeset
        # cannot be deleted once its been applied.
        if self._dry:
            yield self.api_call(self.cf3_conn.delete_change_set,
                                ChangeSetName=change_set_req['Id'])

        self.log.info('Done updating template')

    def _diff_params_safely(self, remote, local):
        """Safely diffs the CloudFormation parameters.

        Does a comparison of the locally supplied parameters, and the remotely
        discovered (already set) CloudFormation parameters. When they are
        different, shows a clean diff and returns False.

        Takes into account NoEcho parameters which cannot be diff'd, so should
        not be included in the output (likely because they are passwords).

        Args:
            Remote: A list of objects, each having a ParameterKey and
            ParameterValue.
            Local: A list of objects, each having a ParameterKey and
            ParameterValue.

        Returns:
            Boolean
        """
        # If there are any NoEcho parameters, we can't diff them .. Amazon
        # returns them as *****'s and we're unable to compare them. Also, we
        # wouldn't want to print these out in our logs because they're almost
        # certainly passwords. Therefore, we should simply skip them in the
        # diff.
        for p in self._noecho_params:
            self.log.debug(
                'Removing "%s" from parameters before comparison.' % p)
            remote = [pair for pair in remote if pair['ParameterKey'] != p]
            local = [pair for pair in local if pair['ParameterKey'] != p]

        # Remove any resolved parameter values that were inserted by SSM
        # so that only supplied parameter values are compared.
        filtered_remote = []
        for param in remote:
            filtered_param = {}
            for k, v in param.items():
                if k != "ResolvedValue":
                    filtered_param[k] = v
            filtered_remote.append(filtered_param)

        remote = filtered_remote

        diff = utils.diff_dicts(remote, local)
        if diff:
            self.log.warning('Stack parameters do not match.')
            for line in diff.split('\n'):
                self.log.info('Diff: %s' % line)

            return True

        return False

    @gen.coroutine
    def _create_change_set(self, stack, uuid=uuid.uuid4().hex):
        """Generates a Change Set.

        Takes the current settings (template, capabilities, etc) and generates
        a Change Set against the live running stack. Returns back a Change Set
        Request dict, which can be used to poll for a real change set.

        args:
            stack: Boto3 Stack dict

        returns:
            Boto3 Change Set Request dict
        """
        change_opts = {
            'StackName': stack['StackId'],
            'Capabilities': self.option('capabilities'),
            'ChangeSetName': 'kingpin-%s' % uuid,
            'Parameters': self._parameters,
            'UsePreviousTemplate': False,
        }

        if self.option('role_arn'):
            change_opts['RoleARN'] = self.option('role_arn')

        if self._template_url:
            change_opts['TemplateURL'] = self._template_url
        else:
            change_opts['TemplateBody'] = self._template_body

        self.log.info('Generating a stack Change Set...')
        try:
            change_set_req = yield self.api_call(
                self.cf3_conn.create_change_set,
                **change_opts)
        except ClientError as e:
            raise CloudFormationError(e)

        raise gen.Return(change_set_req)

    @gen.coroutine
    def _wait_until_change_set_ready(self, change_set_name, status_key,
                                     desired_state, sleep=5):
        """Waits until a Change Set has hit the desired state.

        This loop waits until a Change Set has reached a desired state by
        comparing the value of the `status_key` with the `desired_state`. This
        allows the method to be used to check the status of the Change Set
        generation itself (status_key=Status) as well as the execution of the
        Change Set (status_key=ExecutionStatus).

        args:
            change_set_name: The Change Set Request Name
            status_key: The key within the Change Set that defines its status
            desired_state: A string of the desired state we're looking for
            sleep: Time to wait between checks in seconds

        returns:
            The final completed change set dictionary
        """
        self.log.info('Waiting for %s to reach %s' %
                      (change_set_name, desired_state))
        while True:
            try:
                change = yield self.api_call(
                    self.cf3_conn.describe_change_set,
                    ChangeSetName=change_set_name)
            except ClientError as e:
                # If we hit an intermittent error, lets just loop around and
                # try again.
                self.log.error('Error receiving Change Set state: %s' % e)
                yield utils.tornado_sleep(sleep)
                continue

            # The Stack State can be 'AVAILABLE', or an IN_PROGRESS string. In
            # either case, we loop and wait.
            if change[status_key] in (('AVAILABLE',) + IN_PROGRESS):
                self.log.info('Change Set state is %s, waiting %s(s)...' %
                              (change[status_key], sleep))
                yield utils.tornado_sleep(sleep)
                continue

            # If the stack is in the desired state, then return
            if change[status_key] == desired_state:
                self.log.debug('Change Set reached desired state: %s'
                               % change[status_key])
                raise gen.Return(change)

            # Lastly, if we get here, then something is very wrong and we got
            # some funky status back. Throw an exception.
            msg = 'Unexpected Change Set state (%s) received (%s): %s' % (
                status_key,
                change[status_key],
                change.get('StatusReason', 'StatusReason not provided.'))
            raise StackFailed(msg)

    def _print_change_set(self, change_set):
        """Logs out the changes a Change Set would make if executed.

        http://docs.aws.amazon.com/AWSCloudFormation/latest/
        APIReference/API_DescribeChangeSet.html

        args:
            change_set: Change Set Object
        """
        self.log.debug('Parsing change set: %s' % change_set)

        # Reverse the list, and iterate through the data
        for change in change_set['Changes']:
            resource = change['ResourceChange']

            if 'PhysicalResourceId' not in resource:
                resource['PhysicalResourceId'] = 'N/A'

            if 'Replacement' not in resource:
                resource['Replacement'] = False

            log_string_fmt = (
                'Change: '
                '{Action} {ResourceType} '
                '{LogicalResourceId}/{PhysicalResourceId} '
                '(Replacement? {Replacement})'
            )

            msg = log_string_fmt.format(**resource)
            self.log.warning(msg)

    @gen.coroutine
    @dry('Would have executed Change Set {change_set_name}')
    def _execute_change_set(self, change_set_name):
        """Executes the Change Set and waits for completion.

        Takes a supplied Change Set name and Stack Name, executes the change
        set, and waits for it to complete sucessfully.

        args:
            change_set_name: The Change Set Name/ARN
        """
        self.log.info('Executing change set %s' % change_set_name)
        try:
            yield self.api_call(self.cf3_conn.execute_change_set,
                                ChangeSetName=change_set_name)
        except ClientError as e:
            raise StackFailed(e)

        change_set = yield self._wait_until_change_set_ready(
            change_set_name, 'ExecutionStatus', 'EXECUTE_COMPLETE')
        yield self._wait_until_state(change_set['StackId'],
                                     (COMPLETE + FAILED + DELETED))

    @gen.coroutine
    def _ensure_termination_protection(self, stack):
        """Ensures that the EnableTerminationProtection is set to the desired
           setting (either True or False).

        Checks to to see if the actor is managing EnableTerminationProtection,
        and if it is, it updates EnableTerminationProtection if the defined
        value is different from the existing one.

        args:
            stack: Boto3 Stack dict
        """
        existing = stack['EnableTerminationProtection']
        new = self.option('enable_termination_protection')

        if new == 'UNCHANGED' or existing == new:
            raise gen.Return()

        yield self._update_termination_protection(stack, new)

    @gen.coroutine
    @dry('Would have updated EnableTerminationProtection')
    def _update_termination_protection(self, stack, new):
        """Updates the EnableTerminationProtection to the new setting.

        args:
            stack: Boto3 Stack dict
            new: boolean of updated value for EnableTerminationProtection
        """
        self.log.info('Updating EnableTerminationProtection to %s' % str(new))

        try:
            yield self.api_call(
                self.cf3_conn.update_termination_protection,
                StackName=stack['StackName'],
                EnableTerminationProtection=new)
        except ClientError as e:
            raise StackFailed(e)

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
        yield self._validate_template(self._template_body, self._template_url)

        # This main method triggers the creation, deletion or update of the
        # stack as necessary.
        yield self._ensure_stack()
