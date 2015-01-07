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

"""AWS.ELB Actors"""

import logging
import math

from boto.ec2 import elb as aws_elb
from boto.exception import BotoServerError
from concurrent import futures
from tornado import concurrent
from tornado import gen
from tornado import ioloop
import boto.iam.connection

from kingpin import utils
from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.actors.aws import settings as aws_settings
from kingpin.constants import REQUIRED

log = logging.getLogger(__name__)

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'


# This executor is used by the tornado.concurrent.run_on_executor()
# decorator. We would like this to be a class variable so its shared
# across RightScale objects, but we see testing IO errors when we
# do this.
EXECUTOR = futures.ThreadPoolExecutor(10)


class ELBNotFound(exceptions.UnrecoverableActorFailure):

    """Raised when an ELB is not found"""


class CertNotFound(exceptions.UnrecoverableActorFailure):

    """Raised when an ELB is not found"""


# Helper function
def p2f(string):
    """Convert percentage string into float.

    Converts string like '78.9%' into 0.789
    """
    return float(string.strip('%')) / 100


class ELBBaseActor(base.BaseActor):

    """Base class for ELB actors."""

    all_options = {
        'name': (str, REQUIRED, 'Name of the ELB'),
        'count': ((int, str), REQUIRED,
                  'Specific count, or percentage of instances to wait for.'),
        'region': (str, REQUIRED, 'AWS region name, like us-west-2')
    }

    # Get references to existing objects that are used by the
    # tornado.concurrent.run_on_executor() decorator.
    ioloop = ioloop.IOLoop.current()
    executor = EXECUTOR

    def __init__(self, *args, **kwargs):
        """Set up connection object.

        Expected Arguments: region
        """

        super(ELBBaseActor, self).__init__(*args, **kwargs)

        if not (aws_settings.AWS_ACCESS_KEY_ID and
                aws_settings.AWS_SECRET_ACCESS_KEY):
            raise exceptions.InvalidCredentials(
                'AWS settings imported but not all credentials are supplied. '
                'AWS_ACCESS_KEY_ID: %s, AWS_SECRET_ACCESS_KEY: %s' % (
                    aws_settings.AWS_ACCESS_KEY_ID,
                    aws_settings.AWS_SECRET_ACCESS_KEY))

        self.conn = aws_elb.connect_to_region(
            self.option('region'),
            aws_access_key_id=aws_settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=aws_settings.AWS_SECRET_ACCESS_KEY)

    @concurrent.run_on_executor
    @utils.exception_logger
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
        self.log.debug('Searching for ELB "%s"' % name)

        try:
            elbs = self.conn.get_all_load_balancers(load_balancer_names=name)
        except BotoServerError as e:
            raise ELBNotFound(e)

        self.log.debug('ELBs found: %s' % elbs)

        if len(elbs) != 1:
            raise ELBNotFound('Expected to find exactly 1 ELB. Found %s: %s'
                              % (len(elbs), elbs))

        return elbs[0]


class WaitUntilHealthy(ELBBaseActor):

    """Waits till a specified number of instances are "InService"."""

    def _get_expected_count(self, count, total_count):
        """Calculate the expected count for a given percentage.

        Either returns the passed count if it's an integer, or
        calculates the count given an expected percentage.

        Args:
            count: Minimum count (int) or percentage (int) of hosts that must
                   be healthy.
            total_count: The total number of instances in the ELB.

        Returns:
            Number of instances required to be 'healthy'
        """

        if '%' in str(count):
            expected_count = math.ceil(total_count * p2f(count))
        else:
            expected_count = int(count)

        return expected_count

    @concurrent.run_on_executor
    @utils.exception_logger
    def _is_healthy(self, elb, count):
        """Check if there are `count` InService instances for a given elb.

        Args:
            count: integer, or string with % in it.
                   for more information read _get_expected_count()

        Returns:
            Boolean whether or not the ELB is healthy enough.
        """
        name = elb.name

        self.log.debug('Counting ELB InService instances for : %s' % name)

        # Get all instances for this ELB
        instance_list = elb.get_instance_health()
        total_count = len(instance_list)

        self.log.debug('All instances: %s' % instance_list)
        in_service_count = [
            i.state for i in instance_list].count('InService')

        expected_count = self._get_expected_count(count, total_count)

        healthy = (in_service_count >= expected_count)
        self.log.debug('ELB "%s" healthy state: %s' % (elb.name, healthy))

        return healthy

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        raises: gen.Return(True)
        """

        elb = yield self._find_elb(name=self.option('name'))

        repeating_log = utils.create_repeating_log(
            self.log.info,
            'Still waiting for %s to become healthy' % self.option('name'),
            seconds=30)
        while True:
            healthy = yield self._is_healthy(elb, count=self.option('count'))

            if healthy is True:
                self.log.info('ELB is healthy.')
                break

            # In dry mode, fake it
            if self._dry:
                self.log.info('Pretending that ELB is healthy.')
                break

            # Not healthy :( continue looping
            self.log.debug('Retrying in 3 seconds.')
            yield utils.tornado_sleep(3)

        utils.clear_repeating_log(repeating_log)

        raise gen.Return()


class UseCert(ELBBaseActor):

    """Find a server cert in IAM and use it for a specified ELB."""

    all_options = {
        'name': (str, REQUIRED, 'Name of the ELB'),
        'region': (str, REQUIRED, 'AWS region name, like us-west-2'),
        'cert_name': (str, REQUIRED, 'Unique IAM certificate name, or ARN'),
    }

    def __init__(self, *args, **kwargs):
        """Set up additional IAM connection."""
        super(UseCert, self).__init__(*args, **kwargs)
        self.iam_conn = boto.iam.connection.IAMConnection()

    @concurrent.run_on_executor
    @utils.exception_logger
    def _find_cert(self, name):
        """Return a boto IAM object for a certificate."""
        self.log.debug('Searching for cert "%s"...' % name)
        try:
            cert = self.iam_conn.get_server_certificate(name)
        except BotoServerError as e:
            raise CertNotFound(
                'Could not find cert %s. Reason: %s' % (name, e))
        return cert

    @concurrent.run_on_executor
    @utils.exception_logger
    def _use_cert(self, elb, cert):
        """Assign an ssl cert to a given ELB.

        Args:
            elb: boto elb object
            cert: boto iam server_certificate object
        """

        arn = cert['get_server_certificate_response'].get(
            'get_server_certificate_result').get(
            'server_certificate').get(
            'server_certificate_metadata').get('arn')
        self.log.info('Setting ELB "%s" to use cert arn: %s' % (elb, arn))
        elb.set_listener_SSL_certificate(443, cert.arn)

    @gen.coroutine
    def _execute(self):
        """Find ELB, and a Cert, then apply it."""
        elb = yield self._find_elb(self.option('name'))
        cert = yield self._find_cert(self.option('cert_name'))

        if self._dry:
            self.log.info('Would instruct %s to use %s' % (
                self.option('name'), self.option('cert_name')))
        else:
            yield self._use_cert(elb, cert)
