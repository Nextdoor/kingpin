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

:AWS_SESSION_TOKEN:
  Your AWS session token
"""

import logging

from boto3 import exceptions as boto3_exceptions
from botocore import exceptions as botocore_exceptions
from botocore import config as botocore_config
from tornado import concurrent
from tornado import gen
from tornado import ioloop
import boto3

from kingpin import utils
from kingpin import exceptions as kingpin_exceptions
from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.actors.aws import api_call_queue
from kingpin.actors.aws import settings as aws_settings

log = logging.getLogger(__name__)

__author__ = "Mikhail Simin <mikhail@nextdoor.com>"

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

    all_options = {"region": (str, None, "AWS Region (or zone) to connect to.")}

    def __init__(self, *args, **kwargs):
        """Check for required settings."""

        super(AWSBaseActor, self).__init__(*args, **kwargs)

        # By default, we will try to let Boto handle discovering its
        # credentials at instantiation time. This _can_ result in synchronous
        # API calls to the Metadata service, but those should be fast.
        #
        # In the event though that someone has explicitly set the AWS access
        # keys in the environment (either for the purposes of a unit test, or
        # because they wanted to), we use those values.
        boto3_credentials = self.__check_for_environment_credentials()

        # Establish connection objects that don't require a region
        self.iam_conn = self.__build_client("iam", **boto3_credentials)

        # Establish region-specific connection objects.
        self.region = self.option("region")
        if not self.region:
            return

        # Generate our common config options that will be passed into the boto3
        # client constructors...
        boto_config = botocore_config.Config(
            region_name=self.region,
            retries={
                "mode": "adaptive",
            },
        )

        self.ecs_conn = self.__build_client("ecs", boto_config, **boto3_credentials)
        self.cf3_conn = self.__build_client(
            "cloudformation", boto_config, **boto3_credentials
        )
        self.sqs_conn = self.__build_client("sqs", boto_config, **boto3_credentials)
        self.s3_conn = self.__build_client("s3", boto_config, **boto3_credentials)

    def __check_for_environment_credentials(self):
        boto3_credentials_from_environment = {}
        if aws_settings.AWS_ACCESS_KEY_ID:
            boto3_credentials_from_environment[
                "aws_access_key_id"
            ] = aws_settings.AWS_ACCESS_KEY_ID
        if aws_settings.AWS_SECRET_ACCESS_KEY:
            boto3_credentials_from_environment[
                "aws_secret_access_key"
            ] = aws_settings.AWS_SECRET_ACCESS_KEY
        if aws_settings.AWS_SESSION_TOKEN:
            boto3_credentials_from_environment[
                "aws_session_token"
            ] = aws_settings.AWS_SESSION_TOKEN
        return boto3_credentials_from_environment

    def __build_client(self, resource, config=None, **boto3_credentials):
        return boto3.client(resource, config=config, **boto3_credentials)

    @concurrent.run_on_executor
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
        except boto3_exceptions.Boto3Error as e:
            raise self._wrap_boto_exception(e)

    @gen.coroutine
    @utils.exception_logger
    def api_call_with_queueing(self, api_function, queue_name, *args, **kwargs):
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
            NAMED_API_CALL_QUEUES[queue_name] = api_call_queue.ApiCallQueue()
        queue = NAMED_API_CALL_QUEUES[queue_name]
        try:
            result = yield queue.call(api_function, *args, **kwargs)
        except botocore_exceptions.ClientError as e:
            raise self._wrap_boto_exception(e)
        else:
            raise gen.Return(result)

    def _wrap_boto_exception(self, e):
        if isinstance(e, boto3_exceptions.Boto3Error):
            return exceptions.RecoverableActorFailure("Boto3 had a failure: %s" % e)
        return e

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
        self.log.debug("Parsing and validating %s" % policy)

        try:
            p_doc = utils.convert_script_to_dict(
                script_file=policy, tokens=self._init_tokens
            )
        except kingpin_exceptions.InvalidScript as e:
            raise exceptions.UnrecoverableActorFailure(
                "Error parsing %s: %s" % (policy, e)
            )

        return p_doc


class EnsurableAWSBaseActor(AWSBaseActor, base.EnsurableBaseActor):

    """Ensurable version of the AWS Base Actor"""
