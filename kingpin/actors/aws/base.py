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
:mod:`kingpin.actors.aws.base`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The AWS Actors allow you to interact with the resources (such as SQS and ELB)
inside your Amazon AWS account. These actors all support dry runs properly, but
each actor has its own caveats with ``dry=True``. Please read the instructions
below for using each actor.

**Required Environment Variables**

_Note, these can be skipped only if you have a .aws/credentials file in place._

:AWS_ACCESS_KEY_ID:
  Your AWS access key

:AWS_SECRET_ACCESS_KEY:
  Your AWS secret
"""

import json
import logging
import urllib.request
import urllib.parse
import urllib.error
import re

from boto import exception as boto_exception
from boto import utils as boto_utils
from boto3 import exceptions as boto3_exceptions
from botocore import exceptions as botocore_exceptions
from retrying import retry
from tornado import concurrent
from tornado import gen
from tornado import ioloop
import boto.cloudformation
import boto.ec2
import boto.ec2.elb
import boto.iam
import boto.sqs
import boto3

from kingpin import utils
from kingpin import exceptions as kingpin_exceptions
from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.actors.aws import api_call_queue
from kingpin.actors.aws import settings as aws_settings

log = logging.getLogger(__name__)

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'

EXECUTOR = concurrent.futures.ThreadPoolExecutor(10)

NAMED_API_CALL_QUEUES = {}


class ELBNotFound(exceptions.RecoverableActorFailure):
    """Raised when an ELB is not found"""


class InvalidMetaData(exceptions.UnrecoverableActorFailure):
    """Raised when fetching AWS metadata."""


class InvalidPolicy(exceptions.RecoverableActorFailure):
    """Raised when Amazon indicates that policy JSON is invalid."""


class AWSBaseActor(base.BaseActor):
    # Get references to existing objects that are used by the
    # tornado.concurrent.run_on_executor() decorator.
    ioloop = ioloop.IOLoop.current()
    executor = EXECUTOR

    all_options = {
        'region': (str, None, 'AWS Region (or zone) to connect to.')
    }

    def __init__(self, *args, **kwargs):
        """Check for required settings."""

        super(AWSBaseActor, self).__init__(*args, **kwargs)

        # By default, we will try to let Boto handle discovering its
        # credentials at instantiation time. This _can_ result in synchronous
        # API calls to the Metadata service, but those should be fast.
        key = None
        secret = None

        # In the event though that someone has explicitly set the AWS access
        # keys in the environment (either for the purposes of a unit test, or
        # because they wanted to), we use those values.
        if (aws_settings.AWS_ACCESS_KEY_ID and
                aws_settings.AWS_SECRET_ACCESS_KEY):
            key = aws_settings.AWS_ACCESS_KEY_ID
            secret = aws_settings.AWS_SECRET_ACCESS_KEY

        # On our first simple IAM connection, test the credentials and make
        # sure things worked!
        try:
            # Establish connection objects that don't require a region
            self.iam_conn = boto.iam.connection.IAMConnection(
                aws_access_key_id=key,
                aws_secret_access_key=secret)
        except boto.exception.NoAuthHandlerFound:
            raise exceptions.InvalidCredentials(
                'AWS settings imported but not all credentials are supplied. '
                'AWS_ACCESS_KEY_ID: %s, AWS_SECRET_ACCESS_KEY: %s' % (
                    aws_settings.AWS_ACCESS_KEY_ID,
                    aws_settings.AWS_SECRET_ACCESS_KEY))

        # Establish region-specific connection objects.
        region = self.option('region')
        if not region:
            return

        # In case a zone was provided instead of region we can convert
        # it on the fly
        zone_check = re.match(r'(.*[0-9])([a-z]*)$', region)

        if zone_check and zone_check.group(2):
            zone = region  # Only saving this for the log below

            # Set the fixed region
            region = zone_check.group(1)
            self.log.warning('Converting zone "%s" to region "%s".' % (
                zone, region))

        region_names = [r.name for r in boto.ec2.elb.regions()]
        if region not in region_names:
            err = ('Region "%s" not found. Available regions: %s' %
                   (region, region_names))
            raise exceptions.InvalidOptions(err)

        self.ec2_conn = boto.ec2.connect_to_region(
            region,
            aws_access_key_id=key,
            aws_secret_access_key=secret)
        self.ecs_conn = boto3.client(
            'ecs',
            region_name=region,
            aws_access_key_id=key,
            aws_secret_access_key=secret)
        self.elb_conn = boto.ec2.elb.connect_to_region(
            region,
            aws_access_key_id=key,
            aws_secret_access_key=secret)
        self.elbv2_conn = boto3.client(
            'elbv2',
            region_name=region,
            aws_access_key_id=key,
            aws_secret_access_key=secret)
        self.cf3_conn = boto3.client(
            'cloudformation',
            region_name=region,
            aws_access_key_id=key,
            aws_secret_access_key=secret)
        self.sqs_conn = boto.sqs.connect_to_region(
            region,
            aws_access_key_id=key,
            aws_secret_access_key=secret)
        self.s3_conn = boto3.client(
            's3',
            region_name=region,
            aws_access_key_id=key,
            aws_secret_access_key=secret)

    @concurrent.run_on_executor
    @retry(**aws_settings.RETRYING_SETTINGS)
    @utils.exception_logger
    def api_call(self, api_function, *args, **kwargs):
        """Execute `api_function` in a concurrent thread.

        Example:
            >>> zones = yield thread(ec2_conn.get_all_zones)
        This allows execution of any function in a thread without having
        to write a wrapper method that is decorated with run_on_executor()
        """
        try:
            return api_function(*args, **kwargs)
        except (boto_exception.BotoServerError,
                boto3_exceptions.Boto3Error) as e:
            raise self._wrap_boto_exception(e)

    @gen.coroutine
    @utils.exception_logger
    def api_call_with_queueing(self, api_function,
                               queue_name, *args, **kwargs):
        """
        Execute `api_function` in a serialized queue.

        Concurrent calls to this function are serialized into a queue.
        When any api function hits rate throttling, it backs up exponentially.

        The retry loop will always have a pause between sequential calls,
        and the delay between the calls will increase as
        recoverable api failures happen.

        The api function is assumed to be a synchronous function.
        It will be run on a concurrent thread using run_on_executor.

        The queue_identifier argument specifies which queue to use.
        If the queue doesn't exist, it will be created.

        Example:
            >>> zones = yield api_call_with_queueing(
            >>>     ec2_conn.get_all_zones, queue_name='get_all_zones')
        """
        if queue_name not in NAMED_API_CALL_QUEUES:
            NAMED_API_CALL_QUEUES[queue_name] = (
                api_call_queue.ApiCallQueue())
        queue = NAMED_API_CALL_QUEUES[queue_name]
        try:
            result = yield queue.call(api_function, *args, **kwargs)
        except (boto_exception.BotoServerError,
                boto3_exceptions.Boto3Error) as e:
            raise self._wrap_boto_exception(e)
        else:
            raise gen.Return(result)

    def _wrap_boto_exception(self, e):
        if isinstance(e, boto_exception.BotoServerError):
            # If we're using temporary IAM credentials, when those expire we
            # can get back a blank 400 from Amazon. This is confusing, but it
            # happens because of https://github.com/boto/boto/issues/898. In
            # most cases, these temporary IAM creds can be re-loaded by
            # reaching out to the AWS API (for example, if we're using an IAM
            # Instance Profile role), so thats what Boto tries to do. However,
            # if you're using short-term creds (say from SAML auth'd logins),
            # then this fails and Boto returns a blank 400.
            if (e.status == 400 and
                    e.reason == 'Bad Request' and
                    e.error_code is None):
                msg = 'Access credentials have expired'
                return exceptions.InvalidCredentials(msg)

            msg = '%s: %s' % (e.error_code, str(e))
            if e.status == 403:
                return exceptions.InvalidCredentials(msg)
        elif isinstance(e, boto3_exceptions.Boto3Error):
            return exceptions.RecoverableActorFailure(
                'Boto3 had a failure: %s' % e)
        return e

    @gen.coroutine
    def _find_elb(self, name):
        """Return an ELB with the matching name.

        Must find exactly 1 match. Zones are limited by the AWS credentials.

        Args:
            name: String-name of the ELB to search for

        Returns:
            A single ELB reference object

        Raises:
            ELBNotFound
        """
        self.log.info('Searching for ELB "%s"' % name)

        try:
            elbs = yield self.api_call(self.elb_conn.get_all_load_balancers,
                                       load_balancer_names=name)
        except boto_exception.BotoServerError as e:
            msg = '%s: %s' % (e.error_code, str(e))
            log.error('Received exception: %s' % msg)

            if e.status == 400:
                raise ELBNotFound(msg)

            raise

        self.log.debug('ELBs found: %s' % elbs)

        if len(elbs) != 1:
            raise ELBNotFound('Expected to find exactly 1 ELB. Found %s: %s'
                              % (len(elbs), elbs))

        raise gen.Return(elbs[0])

    @gen.coroutine
    def _find_target_group(self, arn):
        """Returns an ELBv2 Target Group with the matching name.

        Args:
            name: String-name of the Target Group to search for

        Returns:
            A single Target Group reference object

        Raises:
            ELBNotFound
        """
        self.log.info('Searching for Target Group "%s"' % arn)

        try:
            trgts = yield self.api_call(self.elbv2_conn.describe_target_groups,
                                        Names=[arn])
        except botocore_exceptions.ClientError as e:
            raise exceptions.UnrecoverableActorFailure(str(e))

        arns = [t['TargetGroupArn'] for t in trgts['TargetGroups']]

        if len(arns) != 1:
            raise ELBNotFound(
                'Expected to find exactly 1 Target Group. Found %s: %s'
                % (len(arns), arns))

        raise gen.Return(arns[0])

    @gen.coroutine
    def _get_meta_data(self, key):
        """Get AWS meta data for current instance.

        http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/
        ec2-instance-metadata.html
        """

        meta = yield self.api_call(boto_utils.get_instance_metadata,
                                   timeout=1, num_retries=2)
        if not meta:
            raise InvalidMetaData('No metadata available. Not AWS instance?')

        data = meta.get(key, None)
        if not data:
            raise InvalidMetaData('Metadata for key `%s` is not available')

        raise gen.Return(data)

    def _policy_doc_to_dict(self, policy):
        """Converts a Boto UUEncoded Policy document to a Dict.

        args:
            policy: The policy string returned by Boto
        """
        return json.loads(urllib.parse.unquote(policy))

    def _parse_policy_json(self, policy):
        """Parse a single JSON file into an Amazon policy.

        Validates that the policy document can be parsed, strips out any
        comments, and fills in any environmental tokens. Returns a dictionary
        of the contents.

        Returns None if the input is None.

        args:
            policy: The Policy JSON file to read.

        returns:
            A dictionary of the parsed policy.
        """
        if policy is None:
            return None

        # Run through any supplied Inline IAM Policies and verify that they're
        # not corrupt very early on.
        self.log.debug('Parsing and validating %s' % policy)

        try:
            p_doc = utils.convert_script_to_dict(script_file=policy,
                                                 tokens=self._init_tokens)
        except kingpin_exceptions.InvalidScript as e:
            raise exceptions.UnrecoverableActorFailure('Error parsing %s: %s' %
                                                       (policy, e))

        return p_doc


class EnsurableAWSBaseActor(AWSBaseActor, base.EnsurableBaseActor):

    """Ensurable version of the AWS Base Actor"""
