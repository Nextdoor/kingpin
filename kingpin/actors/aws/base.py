"""
:mod:`kingpin.actors.aws.base`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The AWS Actors allow you to interact with the resources (such as SQS and ELB)
inside your Amazon AWS account. These actors all support dry runs properly, but
each actor has its own caveats with ``dry=True``. Please read the instructions
below for using each actor.

**Required Environment Variables**

.. note::

    These can be skipped only if you have a ``.aws/credentials`` file in place.

:AWS_ACCESS_KEY_ID:
    Your AWS access key

:AWS_SECRET_ACCESS_KEY:
    Your AWS secret

:AWS_SESSION_TOKEN:
    Your AWS session token. Only needed if you are using temporary access
    credentials
"""

import logging

import boto3
from boto3 import exceptions as boto3_exceptions
from botocore import config as botocore_config
from botocore import exceptions as botocore_exceptions
from tornado import concurrent, gen, ioloop

from kingpin import exceptions as kingpin_exceptions
from kingpin import utils
from kingpin.actors import base, exceptions
from kingpin.actors.aws import api_call_queue
from kingpin.actors.aws import settings as aws_settings

log = logging.getLogger(__name__)

__author__ = "Matt Wise <matt@nextdoor.com>"

EXECUTOR = concurrent.futures.ThreadPoolExecutor(10)

NAMED_API_CALL_QUEUES = {}


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

        super().__init__(*args, **kwargs)

        # By default, we will try to let Boto handle discovering its
        # credentials at instantiation time. This _can_ result in synchronous
        # API calls to the Metadata service, but those should be fast.
        #
        # In the event though that someone has explicitly set the AWS access
        # keys in the environment (either for the purposes of a unit test, or
        # because they wanted to), we use those values.
        #
        # Note: these get defualted to None in aws_settings if they are not
        # found which will tell boto3 to fallback to default behavior.
        boto3_client_kwargs = {}
        boto3_client_kwargs["aws_access_key_id"] = aws_settings.AWS_ACCESS_KEY_ID
        boto3_client_kwargs["aws_secret_access_key"] = (
            aws_settings.AWS_SECRET_ACCESS_KEY
        )
        boto3_client_kwargs["aws_session_token"] = aws_settings.AWS_SESSION_TOKEN

        # Establish connection objects that don't require a region
        self.iam_conn = boto3.client(
            service_name="iam", config=None, **boto3_client_kwargs
        )

        # Establish region-specific connection objects.
        self.region = self.option("region")
        if not self.region:
            return

        # Generate our common config options that will be passed into the boto3
        # client constructors...
        boto_config = botocore_config.Config(
            region_name=self.region,
            retries={
                "max_attempts": aws_settings.AWS_MAX_ATTEMPTS,
                "mode": aws_settings.AWS_RETRY_MODE,
            },
        )

        self.ecs_conn = boto3.client(
            service_name="ecs", config=boto_config, **boto3_client_kwargs
        )
        self.cfn_conn = boto3.client(
            service_name="cloudformation", config=boto_config, **boto3_client_kwargs
        )
        self.sqs_conn = boto3.client(
            service_name="sqs", config=boto_config, **boto3_client_kwargs
        )
        self.s3_conn = boto3.client(
            service_name="s3", config=boto_config, **boto3_client_kwargs
        )

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
            raise self._wrap_boto_exception(e) from e

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
            raise self._wrap_boto_exception(e) from e
        else:
            raise gen.Return(result)

    def _wrap_boto_exception(self, e):
        if isinstance(e, boto3_exceptions.Boto3Error):
            return exceptions.RecoverableActorFailure(f"Boto3 had a failure: {e}")
        return e

    def _parse_json(self, file_path):
        """Parse a single JSON file.

        Validates that the JSON document can be parsed, strips out any
        comments, and fills in any environmental tokens. Returns a dictionary of
        the contents.

        Args:
            file_path: The JSON file to read.

        Returns:
            A dictionary of the parsed JSON. None if the input is None.
        """
        if file_path is None:
            return None

        # Run through any supplied JSON files and verify that they're
        # not corrupt very early on.
        self.log.debug(f"Parsing and validating {file_path}")

        try:
            p_doc = utils.load_json_with_tokens(
                file_path=file_path, tokens=self._init_tokens
            )
            assert isinstance(p_doc, dict), f"Expected dict but got {type(p_doc)}"
        except kingpin_exceptions.InvalidScript as e:
            raise exceptions.UnrecoverableActorFailure(
                f"Error parsing {file_path}: {e}"
            ) from e

        return p_doc


class EnsurableAWSBaseActor(AWSBaseActor, base.EnsurableBaseActor):
    """Ensurable version of the AWS Base Actor"""
