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
import uuid

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

    The `capability` options currently available are `CAPABILITY_IAM` and
    `CAPABILITY_NAMED_IAM`, either of which can be used to grant a Stack the
    capability to create IAM resources. You must use `CAPABILITY_NAMED_IAM` to
    create IAM resources with custom names.
    """

    SCHEMA = {
        'type': ['array', 'null'],
        'uniqueItems': True,
        'items': {
            'type': 'string',
            'enum': ['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM']
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


# CloudFormation has over a dozen different 'stack states'... but for the
# purposes of these actors, we really only care about a few logical states.
# Here we map the raw states into logical states.
COMPLETE = ('CREATE_COMPLETE', 'UPDATE_COMPLETE', 'UPDATE_ROLLBACK_COMPLETE')
DELETED = ('DELETE_COMPLETE', )
IN_PROGRESS = (
    'CREATE_PENDING', 'CREATE_IN_PROGRESS', 'DELETE_IN_PROGRESS',
    'EXECUTE_IN_PROGRESS', 'ROLLBACK_IN_PROGRESS',
    'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS', 'UPDATE_IN_PROGRESS',
    'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS',
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
            return None, None

        remote_types = ('http://', 'https://')

        if template.startswith(remote_types):
            return None, template

        try:
            return json.dumps(self._parse_policy_json(template)), None
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
                raise InvalidTemplate(str(e))

        if url is not None:
            cfg = {'TemplateURL': url}
            self.log.info('Validating template (%s) with AWS...' % url)
            try:
                yield self.thread(self.cf3_conn.validate_template, **cfg)
            except ClientError as e:
                raise InvalidTemplate(str(e))

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
            A dict like above
        """

        new_params = [
            {'ParameterKey': k,
             'ParameterValue': v}
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
            ret = yield self.thread(self.cf3_conn.get_template,
                                    StackName=stack)
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
            ret = yield self.thread(
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
        self._template_body, self._template_url = self._get_template_body(
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
      * Monitor and update the stack Template and Parameters as necessary.

    **NoEcho Parameters**

    If your CF stack takes a Password as a paremter or any other value thats
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
        self._template_body, self._template_url = self._get_template_body(
            self.option('template'))

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

        # TODO: Implement this
        if self._template_url:
            self.log.warning('Cannot compare against remote template url')
            raise gen.Return()

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
                stack.get('Parameters', {}),
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
            yield self.thread(self.cf3_conn.delete_change_set,
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

        if self._template_body:
            change_opts['TemplateBody'] = self._template_body
        else:
            change_opts['TemplateURL'] = self._template_url

        self.log.info('Generating a stack Change Set...')
        try:
            change_set_req = yield self.thread(self.cf3_conn.create_change_set,
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
                change = yield self.thread(
                    self.cf3_conn.describe_change_set,
                    ChangeSetName=change_set_name)
            except ClientError as e:
                # If we hit an intermittent error, lets just loop around and
                # try again.
                self.log.error('Error receiving change set state: %s' % e)
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
            msg = 'Unxpected stack state received (%s)' % change[status_key]
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
            yield self.thread(self.cf3_conn.execute_change_set,
                              ChangeSetName=change_set_name)
        except ClientError as e:
            raise StackFailed(e)

        change_set = yield self._wait_until_change_set_ready(
            change_set_name, 'ExecutionStatus', 'EXECUTE_COMPLETE')
        yield self._wait_until_state(change_set['StackId'],
                                     (COMPLETE + FAILED + DELETED))

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
