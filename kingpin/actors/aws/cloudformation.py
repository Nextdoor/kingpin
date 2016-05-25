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
from kingpin.actors.aws import base
from kingpin.constants import SchemaCompareBase
from kingpin.constants import REQUIRED

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


# This executor is used by the tornado.concurrent.run_on_executor()
# decorator. We would like this to be a class variable so its shared
# across RightScale objects, but we see testing IO errors when we
# do this.
EXECUTOR = concurrent.futures.ThreadPoolExecutor(10)


class CloudFormationError(exceptions.RecoverableActorFailure):

    """Raised on any generic CloudFormation error."""


class InvalidTemplate(exceptions.UnrecoverableActorFailure):

    """An invalid CloudFormation template was supplied."""


class StackAlreadyExists(exceptions.RecoverableActorFailure):

    """The requested CloudFormation stack already exists."""


class StackNotFound(exceptions.RecoverableActorFailure):

    """The requested CloudFormation stack does not exist."""


class ParametersConfig(SchemaCompareBase):

    """Simple validation that the Parameters are pure Key/Value formatted"""

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


# CloudFormation has over a dozen different 'stack states'... but for the
# purposes of these actors, we really only care about a few logical states.
# Here we map the raw states into logical states.
COMPLETE = ('CREATE_COMPLETE', 'UPDATE_COMPLETE')
DELETED = ('DELETE_COMPLETE', 'ROLLBACK_COMPLETE')
IN_PROGRESS = (
    'CREATE_IN_PROGRESS', 'DELETE_IN_PROGRESS',
    'ROLLBACK_IN_PROGRESS', 'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS',
    'UPDATE_IN_PROGRESS', 'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS',
    'UPDATE_ROLLBACK_IN_PROGRESS')
FAILED = (
    'CREATE_FAILED', 'DELETE_FAILED', 'ROLLBACK_FAILED',
    'UPDATE_ROLLBACK_FAILED')


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
    def _get_stacks(self):
        """Gets a list of existing CloudFormation stacks.

        Gets a list of all of the stacks currently in the account, that are not
        in the status 'DELETE_COMPLETE'.

        Returns:
            A list of Boto S3 Stack Dicts
        """
        # Get the list of all possible stack statuses from the Boto module,
        # then pull out the few that indicate a stack is no longer in
        # existence.
        self.log.debug('Getting list of stacks from Amazon..')
        statuses = COMPLETE + IN_PROGRESS + FAILED
        stacks = yield self.thread(self.cf3_conn.list_stacks,
                                   StackStatusFilter=statuses)
        raise gen.Return(stacks['StackSummaries'])

    @gen.coroutine
    def _get_stack(self, stack):
        """Returns a cloudformation.Stack object of the requested stack.

        Args:
            stack: String name

        Returns
            <Stack Dict> or <None>
        """
        stacks = yield self._get_stacks()
        self.log.debug('Checking whether stack exists')
        new_list = [s for s in stacks if s['StackName'] == stack]

        if len(new_list) > 0:
            raise gen.Return(new_list[0])

        raise gen.Return(None)

    @gen.coroutine
    def _wait_until_state(self, desired_states, sleep=15):
        """Indefinite loop until a stack has finished creating/deleting.

        Whether the stack has failed, suceeded or been rolled back... this
        method loops until the process has finished. If the final status is a
        failure (rollback/failed) then an exception is raised.

        Args:
            desired_states: (tuple/list) States that indicate a successful
                            operation.
            sleep: (int) Time in seconds between stack status checks

        Raises:
            StackNotFound: If the stack doesn't exist.
        """
        while True:
            stack = yield self._get_stack(self.option('name'))

            if not stack:
                msg = 'Stack "%s" not found.' % self.option('name')
                raise StackNotFound(msg)

            self.log.debug('Got stack status: %s' % stack['StackStatus'])

            # First, lets see if the stack is still in progress (either
            # creation, deletion, or rollback .. doesn't really matter)
            if stack['StackStatus'] in IN_PROGRESS:
                self.log.info('Stack is in %s, waiting %s(s)...' %
                              (stack['StackStatus'], sleep))
                yield utils.tornado_sleep(sleep)
                continue

            # If the stack is in the desired state, then return
            if stack['StackStatus'] in desired_states:
                self.log.info('Stack execution completed, final state: %s' %
                              stack['StackStatus'])
                raise gen.Return()

            # Lastly, if we get here, then something is very wrong and we got
            # some funky status back. Throw an exception.
            msg = 'Unxpected stack state received (%s)' % stack['StackStatus']
            raise CloudFormationError(msg)


class Create(CloudFormationBaseActor):

    """Creates a CloudFormation stack.

    Creates a CloudFormation stack from scratch and waits until the stack is
    fully built before exiting the actor.

    **Options**

    :capabilities:
      A list of CF capabilities to add to the stack.

    :disable_rollback:
      Set to True to disable rollback of the stack if creation failed.

    :name:
      The name of the queue to create

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
           "disable_rollback": true,
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
        'disable_rollback': (bool, False,
                             'Set to `True` to disable rollback of the stack '
                             'if stack creation failed.'),
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
        remote_types = ('http://', 'https://')

        if template.startswith(remote_types):
            self.log.error('GOT HERE')
            return (None, template)

        try:
            return (json.dumps(self._parse_policy_json(template)), None)
        except exceptions.UnrecoverableActorFailure as e:
            raise InvalidTemplate(e)

    @gen.coroutine
    def _validate_template(self):
        """Validates the CloudFormation template.

        Raises:
            InvalidTemplate
            exceptions.InvalidCredentials
        """
        if self._template_body is not None:
            self.log.info('Validating template with AWS...')
        else:
            self.log.info('Validating template (%s) with AWS...' %
                          self._template_url)

        if self._template_body:
            cfg = {'TemplateBody': self._template_body}
        else:
            cfg = {'TemplateURL': self._template_url}

        try:
            yield self.thread(self.cf3_conn.validate_template, **cfg)
        except ClientError as e:
            raise InvalidTemplate(e.message)

    @gen.coroutine
    def _create_stack(self):
        """Executes the stack creation."""
        # Create the stack, and get its ID.
        self.log.info('Creating stack %s' % self.option('name'))

        if self._template_body:
            cfg = {'TemplateBody': self._template_body}
        else:
            cfg = {'TemplateURL': self._template_url}

        try:
            stack = yield self.thread(
                self.cf3_conn.create_stack,
                StackName=self.option('name'),
                Parameters=self._parameters,
                DisableRollback=self.option('disable_rollback'),
                TimeoutInMinutes=self.option('timeout_in_minutes'),
                Capabilities=self.option('capabilities'),
                **cfg)
        except ClientError as e:
            raise CloudFormationError(e.message)

        self.log.info('Stack created: %s' % stack['StackId'])
        raise gen.Return(stack['StackId'])

    @gen.coroutine
    def _execute(self):
        stack_name = self.option('name')

        yield self._validate_template()

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
        yield self._create_stack()

        # Now wait until the stack creation has finished
        yield self._wait_until_state(COMPLETE)

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
    def _delete_stack(self):
        """Executes the stack deletion."""
        # Create the stack, and get its ID.
        self.log.info('Deleting stack')
        try:
            ret = yield self.thread(
                self.cf3_conn.delete_stack, StackName=self.option('name'))
        except ClientError as e:
            raise CloudFormationError(e.message)

        req_id = ret['ResponseMetadata']['RequestId']
        self.log.info('Stack delete requested: %s' % req_id)
        raise gen.Return(req_id)

    @gen.coroutine
    def _execute(self):
        stack_name = self.option('name')

        # If the stack doesn't exist, let the user know.
        exists = yield self._get_stack(stack_name)
        if not exists:
            raise StackNotFound('Stack does not exist!')

        # If we're in dry mode, exit at this point. We can't do anything
        # further to validate that the creation process will work.
        if self._dry:
            self.log.info('Skipping CloudFormation Stack deletion.')
            raise gen.Return()

        # Delete
        yield self._delete_stack()

        # Now wait until the stack creation has finished
        try:
            yield self._wait_until_state(DELETED)
        except StackNotFound:
            # Pass here because a stack not found exception is totally
            # reasonable since we're deleting the stack. Sometimes Amazon
            # actually deletes the stack immediately, and othertimes it lists
            # the stack as a 'deleted' state, but we still get that state back.
            # Either case is fine.
            pass

        raise gen.Return()
