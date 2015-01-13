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

"""AWS.CloudFormation Actors"""

import logging

from boto import cloudformation
from boto.exception import BotoServerError
from concurrent import futures
from retrying import retry
from tornado import concurrent
from tornado import gen
from tornado import ioloop

from kingpin import utils
from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.actors.aws import settings as aws_settings
from kingpin.constants import REQUIRED

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


# This executor is used by the tornado.concurrent.run_on_executor()
# decorator. We would like this to be a class variable so its shared
# across RightScale objects, but we see testing IO errors when we
# do this.
EXECUTOR = futures.ThreadPoolExecutor(10)


# Used by the retrying.retry decorator
def retry_if_transient_error(exception):
    return isinstance(exception, BotoServerError)


class CloudFormationError(exceptions.RecoverableActorFailure):

    """Raised on any generic CloudFormation error."""


class InvalidTemplate(exceptions.UnrecoverableActorFailure):

    """An invalid CloudFormation template was supplied."""


class StackAlreadyExists(exceptions.RecoverableActorFailure):

    """The requested CloudFormation stack already exists."""


class StackNotFound(exceptions.RecoverableActorFailure):

    """The requested CloudFormation stack does not exist."""


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


class CloudFormationBaseActor(base.BaseActor):

    """Base Actor for CloudFormation tasks"""

    # Get references to existing objects that are used by the
    # tornado.concurrent.run_on_executor() decorator.
    ioloop = ioloop.IOLoop.current()

    executor = EXECUTOR

    # Used mainly for unit testing..
    all_options = {
        'region': (str, REQUIRED, 'AWS region name, like us-west-2')
    }

    def __init__(self, *args, **kwargs):
        """Create the connection object."""
        super(CloudFormationBaseActor, self).__init__(*args, **kwargs)

        if not (aws_settings.AWS_ACCESS_KEY_ID and
                aws_settings.AWS_SECRET_ACCESS_KEY):
            raise exceptions.InvalidCredentials(
                'AWS settings imported but not all credentials are supplied. '
                'AWS_ACCESS_KEY_ID: %s, AWS_SECRET_ACCESS_KEY: %s' % (
                    aws_settings.AWS_ACCESS_KEY_ID,
                    aws_settings.AWS_SECRET_ACCESS_KEY))

        self.conn = cloudformation.connect_to_region(
            self.option('region'),
            aws_access_key_id=aws_settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=aws_settings.AWS_SECRET_ACCESS_KEY)

    @concurrent.run_on_executor
    @retry(retry_on_exception=retry_if_transient_error,
           stop_max_attempt_number=5,
           wait_exponential_multiplier=500,
           wait_exponential_max=aws_settings.CF_WAIT_MAX)
    @utils.exception_logger
    def _get_stacks(self):
        """Gets a list of existing CloudFormation stacks.

        Gets a list of all of the stacks currently in the account, that are not
        in the status 'DELETE_COMPLETE'.

        Returns:
            A list of boto.cloudformation.stack.StackSummary objects.
        """
        # Get the list of all possible stack statuses from the Boto module,
        # then pull out the few that indicate a stack is no longer in
        # existence.
        self.log.debug('Getting list of stacks from Amazon..')
        statuses = list(self.conn.valid_states)
        statuses.remove('DELETE_COMPLETE')
        return self.conn.list_stacks(stack_status_filters=statuses)

    @gen.coroutine
    def _get_stack(self, stack):
        """Returns a cloudformation.Stack object of the requested stack.

        Args:
            stack: String name

        Returns
            <Stack Object> or <None>
        """
        stacks = yield self._get_stacks()
        self.log.debug('Checking whether stack %s exists.' % stack)
        new_list = [s for s in stacks if s.stack_name == stack]

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

            self.log.debug('Got stack %s status: %s' %
                           (stack.stack_name, stack.stack_status))

            # First, lets see if the stack is still in progress (either
            # creation, deletion, or rollback .. doesn't really matter)
            if stack.stack_status in IN_PROGRESS:
                self.log.info('Stack is in %s, waiting %s(s)...' %
                              (stack.stack_status, sleep))
                yield utils.tornado_sleep(sleep)
                continue

            # If the stack is in the desired state, then return
            if stack.stack_status in desired_states:
                self.log.info('Stack execution completed, final state: %s' %
                              stack.stack_status)
                raise gen.Return()

            # Lastly, if we get here, then something is very wrong and we got
            # some funky status back. Throw an exception.
            msg = 'Unxpected stack state received (%s)' % stack.stack_status
            raise CloudFormationError(msg)


class Create(CloudFormationBaseActor):

    """Creates an Amazon CF Stack.

    http://boto.readthedocs.org/en/latest/ref/cloudformation.html
    #boto.cloudformation.connection.CloudFormationConnection.create_stack

    """

    all_options = {
        'capabilities': (list, [],
                         'The list of capabilities that you want to allow '
                         'in the stack'),
        'disable_rollback': (bool, False,
                             'Set to `True` to disable rollback of the stack '
                             'if stack creation failed.'),
        'name': (str, REQUIRED, 'Name of the stack'),
        'parameters': (dict, {}, 'Parameters passed into the CF '
                                 'template execution'),
        'region': (str, REQUIRED, 'AWS region name, like us-west-2'),
        'template': (str, REQUIRED,
                     'Path to the AWS CloudFormation File. http(s)://, '
                     'file:///, absolute or relative file paths.'),
        'timeout_in_minutes': (int, 60,
                               'The amount of time that can pass before the '
                               'stack status becomes CREATE_FAILED'),
    }

    def __init__(self, *args, **kwargs):
        """Initialize our object variables."""
        super(Create, self).__init__(*args, **kwargs)

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
            return (None, template)

        try:
            # TODO: leverage self.readfile()
            return (open(template, 'r').read(), None)
        except IOError as e:
            raise InvalidTemplate(e)

    @concurrent.run_on_executor
    @retry(retry_on_exception=retry_if_transient_error,
           stop_max_attempt_number=5,
           wait_exponential_multiplier=500,
           wait_exponential_max=aws_settings.CF_WAIT_MAX)
    @utils.exception_logger
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

        try:
            self.conn.validate_template(
                template_body=self._template_body,
                template_url=self._template_url)
        except BotoServerError as e:
            msg = '%s: %s' % (e.error_code, e.message)

            if e.status == 403:
                raise exceptions.InvalidCredentials(msg)

            if e.status == 400:
                raise InvalidTemplate(msg)

            raise

    @concurrent.run_on_executor
    @retry(retry_on_exception=retry_if_transient_error,
           stop_max_attempt_number=5,
           wait_exponential_multiplier=500,
           wait_exponential_max=aws_settings.CF_WAIT_MAX)
    @utils.exception_logger
    def _create_stack(self):
        """Executes the stack creation."""
        # Create the stack, and get its ID.
        self.log.info('Creating stack %s' % self.option('name'))
        try:
            stack_id = self.conn.create_stack(
                self.option('name'),
                template_body=self._template_body,
                template_url=self._template_url,
                parameters=self.option('parameters').items(),
                disable_rollback=self.option('disable_rollback'),
                timeout_in_minutes=self.option('timeout_in_minutes'),
                capabilities=self.option('capabilities'))
        except BotoServerError as e:
            msg = '%s: %s' % (e.error_code, e.message)

            if e.status == 403:
                raise exceptions.InvalidCredentials(msg)

            if e.status == 400:
                raise CloudFormationError(msg)

            raise

        self.log.info('Stack %s created: %s' % (self.option('name'), stack_id))
        return stack_id

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

    """Deletes an Amazon CF Stack.

    http://boto.readthedocs.org/en/latest/ref/cloudformation.html
    #boto.cloudformation.connection.CloudFormationConnection.delete_stack

    """

    all_options = {
        'name': (str, REQUIRED, 'Name of the stack'),
        'region': (str, REQUIRED, 'AWS region name, like us-west-2')
    }

    @concurrent.run_on_executor
    @retry(retry_on_exception=retry_if_transient_error,
           stop_max_attempt_number=5,
           wait_exponential_multiplier=500,
           wait_exponential_max=aws_settings.CF_WAIT_MAX)
    @utils.exception_logger
    def _delete_stack(self):
        """Executes the stack deletion."""
        # Create the stack, and get its ID.
        self.log.info('Deleting stack %s' % self.option('name'))
        try:
            ret = self.conn.delete_stack(self.option('name'))
        except BotoServerError as e:
            msg = '%s: %s' % (e.error_code, e.message)

            if e.status == 403:
                raise exceptions.InvalidCredentials(msg)

            if e.status == 400:
                raise CloudFormationError(msg)

            raise
        self.log.info('Stack %s delete requested: %s' %
                      (self.option('name'), ret))
        return ret

    @gen.coroutine
    def _execute(self):
        stack_name = self.option('name')

        # If the stack doesn't exist, let the user know.
        exists = yield self._get_stack(stack_name)
        if not exists:
            raise StackNotFound('Stack %s does not exist!' % stack_name)

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
