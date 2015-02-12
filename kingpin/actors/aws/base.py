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

from boto import utils
from boto.exception import BotoServerError
from concurrent import futures
from tornado import concurrent
from tornado import gen
from tornado import ioloop
import boto.ec2.elb
import boto.iam

from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.actors.aws import settings as aws_settings

from kingpin.actors.support import api as support

log = logging.getLogger(__name__)

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'

EXECUTOR = futures.ThreadPoolExecutor(10)


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
        'region': (str, None, 'AWS Region to connect to.')
    }

    _EXCEPTIONS = {
        BotoServerError: {
            'LoadBalancerNotFound': ELBNotFound
        },
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
        if region:
            self.elb_conn = boto.ec2.elb.connect_to_region(
                region,
                aws_access_key_id=aws_settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=aws_settings.AWS_SECRET_ACCESS_KEY)

    @concurrent.run_on_executor
    def _get_all_load_balancers(self, name):
        """Thread wrapper for Boto get_all_load_balancers.

        All the retry logic should go into the calling function to properly
        parse the message inside of BotoServerError exception.
        """
        return self.elb_conn.get_all_load_balancers(load_balancer_names=name)

    @gen.coroutine
    @support._retry
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

        elbs = yield self._get_all_load_balancers(name)

        self.log.debug('ELBs found: %s' % elbs)

        if len(elbs) != 1:
            raise ELBNotFound('Expected to find exactly 1 ELB. Found %s: %s'
                              % (len(elbs), elbs))

        raise gen.Return(elbs[0])

    @concurrent.run_on_executor
    def _get_meta_data(self, key):
        """Get AWS meta data for current instance.

        http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/
        ec2-instance-metadata.html
        """

        meta = utils.get_instance_metadata(timeout=1, num_retries=2)
        if not meta:
            raise InvalidMetaData('No metadata available. Not AWS instance?')

        data = meta.get(key, None)
        if not data:
            raise InvalidMetaData('Metadata for key `%s` is not available')

        return data
