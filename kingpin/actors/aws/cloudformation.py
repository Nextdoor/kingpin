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

# Maximum wait time for any @retry-decorated method. Here for easy overriding
# in the unit tests.
WAIT_EXPONENTIAL_MAX = 30000
MAX_RETRIES = 3


# Used by the retrying.retry decorator
def retry_if_transient_error(exception):
    return isinstance(exception, BotoServerError)


class InvalidTemplateException(exceptions.UnrecoverableActorFailure):

    """An invalid CloudFormation template was supplied."""


class CloudFormationBaseActor(base.BaseActor):

    """Base Actor for CloudFormation tasks"""

    # Get references to existing objects that are used by the
    # tornado.concurrent.run_on_executor() decorator.
    ioloop = ioloop.IOLoop.current()

    executor = EXECUTOR

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


class Create(CloudFormationBaseActor):

    """Creates an Amazon CF Stack.

    http://boto.readthedocs.org/en/latest/ref/cloudformation.html
    #boto.cloudformation.connection.CloudFormationConnection.create_stack

    """

    all_options = {
        'name': (str, REQUIRED, 'Name of the stack'),
        'template': (str, REQUIRED,
                     'Path to the AWS CloudFormation File. http(s)://, '
                     'file:///, absolute or relative file paths.'),
        'parameters': (dict, {}, 'Parameters passed into the CF '
                                 'template execution'),
        'region': (str, REQUIRED, 'AWS region name, like us-west-2')
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
            Tuple with:
              (None/Contents of template file,
               None/URL of template)

        Raises:
            InvalidTemplateException
        """
        remote_types = ('http://', 'https://')

        if self.option('template').startswith(remote_types):
            return (None, template)

        try:
            return (open(template, 'r').read(), None)
        except IOError as e:
            raise InvalidTemplateException(e)

    @concurrent.run_on_executor
    @retry(retry_on_exception=retry_if_transient_error,
           stop_max_attempt_number=MAX_RETRIES,
           wait_exponential_multiplier=500,
           wait_exponential_max=WAIT_EXPONENTIAL_MAX)
    @utils.exception_logger
    def _validate_template(self):
        """Validates the CloudFormation template.

        Raises:
            InvalidTemplateException
        """
        if self._template_body is not None:
            log.debug('Validating template with AWS...')
        else:
            log.debug('Validating template (%s) with AWS...' %
                      self._template_url)

        try:
            self.conn.validate_template(
                template_body=self._template_body,
                template_url=self._template_url)
        except BotoServerError as e:
            if not e.status == 400:
                raise

            msg = '%s: %s' % (e.error_code, e.message)
            raise InvalidTemplateException(msg)

    @gen.coroutine
    def _execute(self):
        yield self._validate_template()
        raise gen.Return()
