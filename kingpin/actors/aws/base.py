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

"""AWS Base Actor"""

import logging
import re

from boto import utils as boto_utils
from boto import exception as boto_exception
from tornado import concurrent
from tornado import gen
from tornado import ioloop
from retrying import retry
import boto.cloudformation
import boto.ec2
import boto.ec2.elb
import boto.iam
import boto.sqs

from kingpin import utils
from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.actors.aws import settings as aws_settings

log = logging.getLogger(__name__)

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'

EXECUTOR = concurrent.futures.ThreadPoolExecutor(10)


class ELBNotFound(exceptions.RecoverableActorFailure):

    """Raised when an ELB is not found"""


class InvalidMetaData(exceptions.UnrecoverableActorFailure):

    """Raised when fetching AWS metadata."""


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

        if not (aws_settings.AWS_ACCESS_KEY_ID and
                aws_settings.AWS_SECRET_ACCESS_KEY):
            raise exceptions.InvalidCredentials(
                'AWS settings imported but not all credentials are supplied. '
                'AWS_ACCESS_KEY_ID: %s, AWS_SECRET_ACCESS_KEY: %s' % (
                    aws_settings.AWS_ACCESS_KEY_ID,
                    aws_settings.AWS_SECRET_ACCESS_KEY))

        # Establish connection objects that don't require a region
        self.iam_conn = boto.iam.connection.IAMConnection(
            aws_access_key_id=aws_settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=aws_settings.AWS_SECRET_ACCESS_KEY)

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
            aws_access_key_id=aws_settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=aws_settings.AWS_SECRET_ACCESS_KEY)

        self.elb_conn = boto.ec2.elb.connect_to_region(
            region,
            aws_access_key_id=aws_settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=aws_settings.AWS_SECRET_ACCESS_KEY)

        self.cf_conn = boto.cloudformation.connect_to_region(
            region,
            aws_access_key_id=aws_settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=aws_settings.AWS_SECRET_ACCESS_KEY)

        self.sqs_conn = boto.sqs.connect_to_region(
            region,
            aws_access_key_id=aws_settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=aws_settings.AWS_SECRET_ACCESS_KEY)

    @concurrent.run_on_executor
    @retry(**aws_settings.RETRYING_SETTINGS)
    @utils.exception_logger
    def thread(self, function, *args, **kwargs):
        """Execute `function` in a concurrent thread.

        Example:
            >>> zones = yield thread(ec2_conn.get_all_zones)

        This allows execution of any function in a thread without having
        to write a wrapper method that is decorated with run_on_executor()
        """
        try:
            return function(*args, **kwargs)
        except boto_exception.BotoServerError as e:
            msg = '%s: %s' % (e.error_code, e.message)

            if e.status == 403:
                raise exceptions.InvalidCredentials(msg)

            raise

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
            elbs = yield self.thread(self.elb_conn.get_all_load_balancers,
                                     load_balancer_names=name)
        except boto_exception.BotoServerError as e:
            msg = '%s: %s' % (e.error_code, e.message)
            log.error('Received exception: %s' % msg)

            if e.status == 400:
                raise ELBNotFound(msg)

            raise

        self.log.debug('ELBs found: %s' % elbs)

        if len(elbs) != 1:
            raise ELBNotFound('Expected to find exactly 1 ELB. Found %s: %s'
                              % (len(elbs), elbs))

        raise gen.Return(elbs[0])

    @concurrent.run_on_executor
    @retry(**aws_settings.RETRYING_SETTINGS)
    def _get_meta_data(self, key):
        """Get AWS meta data for current instance.

        http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/
        ec2-instance-metadata.html
        """

        meta = boto_utils.get_instance_metadata(timeout=1, num_retries=2)
        if not meta:
            raise InvalidMetaData('No metadata available. Not AWS instance?')

        data = meta.get(key, None)
        if not data:
            raise InvalidMetaData('Metadata for key `%s` is not available')

        return data
