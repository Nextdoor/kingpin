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

from boto.exception import BotoServerError
from concurrent import futures
from retrying import retry
from tornado import concurrent
from tornado import gen

from kingpin import utils
from kingpin.actors import exceptions
from kingpin.actors.aws import base
from kingpin.actors.aws import settings as aws_settings
from kingpin.constants import REQUIRED

log = logging.getLogger(__name__)

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'


# This executor is used by the tornado.concurrent.run_on_executor()
# decorator. We would like this to be a class variable so its shared
# across RightScale objects, but we see testing IO errors when we
# do this.
EXECUTOR = futures.ThreadPoolExecutor(10)


class CertNotFound(exceptions.UnrecoverableActorFailure):

    """Raised when an ELB is not found"""


# Helper function
def p2f(string):
    """Convert percentage string into float.

    Converts string like '78.9%' into 0.789
    """
    return float(string.strip('%')) / 100


class ELBBaseActor(base.AWSBaseActor):

    """Base class for ELB actors."""

    all_options = {
        'name': (str, REQUIRED, 'Name of the ELB'),
        'count': ((int, str), REQUIRED,
                  'Specific count, or percentage of instances to wait for.'),
        'region': (str, REQUIRED, 'AWS region name, like us-west-2')
    }


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


class SetCert(ELBBaseActor):

    """Find a server cert in IAM and use it for a specified ELB."""

    all_options = {
        'name': (str, REQUIRED, 'Name of the ELB'),
        'port': (int, 443, 'Port associated with the cert'),
        'region': (str, REQUIRED, 'AWS region name, like us-west-2'),
        'cert_name': (str, REQUIRED, 'Unique IAM certificate name, or ARN'),
    }

    @concurrent.run_on_executor
    @utils.exception_logger
    @retry(retry_on_exception=aws_settings.is_retriable_exception)
    def _check_access(self, elb):
        """Perform a dummy operation to check credential accesss.

        Intended to be used in a dry run, this method attempts to perform an
        invalid set_listener call and monitors the output of the error. If the
        error is anything other than AccessDenied then the provided credentials
        are sufficient and we do nothing.

        Args:
            elb: boto LoadBalancer object.
        """
        try:
            # A blank ARN value should have code 'CertificateNotFound'
            # We're only checking if credentials have sufficient access
            elb.set_listener_SSL_certificate(self.option('port'), '')
        except BotoServerError as e:
            if e.error_code == 'AccessDenied':
                raise exceptions.InvalidCredentials(e)

    @concurrent.run_on_executor
    @utils.exception_logger
    @retry(retry_on_exception=aws_settings.is_retriable_exception)
    def _get_cert_arn(self, name):
        """Return a server_certificate ARN.

        Searches for a certificate object and returns the "ARN" value.

        Args:
            name: certificate name

        Raises:
            CertNotFound - if the name doesn't match an existing cert.

        Returns:
            string: the ARN value of the certificate
        """

        self.log.debug('Searching for cert "%s"...' % name)
        try:
            cert = self.iam_conn.get_server_certificate(name)
        except BotoServerError as e:
            raise CertNotFound(
                'Could not find cert %s. Reason: %s' % (name, e))

        # Get the ARN of this cert
        arn = cert['get_server_certificate_response'].get(
            'get_server_certificate_result').get(
            'server_certificate').get(
            'server_certificate_metadata').get('arn')

        return arn

    @concurrent.run_on_executor
    @utils.exception_logger
    @retry(retry_on_exception=aws_settings.is_retriable_exception)
    def _use_cert(self, elb, arn):
        """Assign an ssl cert to a given ELB.

        Args:
            elb: boto elb object.
            arn: ARN for server certificate to use.
        """

        self.log.info('Setting ELB "%s" to use cert arn: %s' % (elb, arn))
        try:
            elb.set_listener_SSL_certificate(self.option('port'), arn)
        except BotoServerError as e:
            raise exceptions.RecoverableActorFailure(
                'Applying new SSL cert to %s failed: %s' % (elb, e))

    def _compare_certs(self, elb, new_arn):
        """Check if a given ELB is using a provided ARN for its certificate.

        Args:
            elb: boto elb object.
            new_arn: ARN for server certificate to use.

        Returns:
            boolean: used cert is same as the provided one.
        """

        ssl = [lis for lis in elb.listeners
               if lis[0] == self.option('port')][0]

        arn = ssl[4]

        return arn == new_arn

    @gen.coroutine
    def _execute(self):
        """Find ELB, and a Cert, then apply it."""
        elb = yield self._find_elb(self.option('name'))
        cert_arn = yield self._get_cert_arn(self.option('cert_name'))

        same_cert = self._compare_certs(elb, cert_arn)

        if same_cert:
            self.log.warning('ELB %s is already using this cert.' % elb)
            raise gen.Return()

        if self._dry:
            yield self._check_access(elb)
            self.log.info('Would instruct %s to use %s' % (
                self.option('name'), self.option('cert_name')))
        else:
            yield self._use_cert(elb, cert_arn)


class RegisterInstance(base.AWSBaseActor):

    """Add an EC2 instance to a load balancer.

    http://boto.readthedocs.org/en/latest/ref/elb.html
    #boto.ec2.elb.ELBConnection.register_instances
    """

    all_options = {
        'elb': (str, REQUIRED, 'Name of the ELB'),
        'region': (str, REQUIRED, 'AWS region name, like us-west-2'),
        'instances': ((str, list), None, (
            'Instance id, or list of ids. If no value is specified then '
            'the instance id of the executing machine is used.'))
    }

    @concurrent.run_on_executor
    @utils.exception_logger
    @retry
    def _add(self, elb, instances):
        """Invoke elb.register_instances

        This boto function is idempotent, so any retry is OK.

        Args:
            elb: boto Loadbalancer object
            instances: list of instance ids.
        """
        elb.register_instances(instances)

    @gen.coroutine
    def _execute(self):
        elb = yield self._find_elb(self.option('elb'))
        instances = self.option('instances')

        if not instances:
            self.log.debug('No instance provided. Using current instance id.')
            iid = yield self._get_meta_data('instance-id')
            instances = [iid]
            self.log.debug('Instances is: %s' % instances)

        if type(instances) is not list:
            instances = [instances]

        self.log.info(('Adding the following instances to elb: '
                       '%s' % ', '.join(instances)))
        if not self._dry:
            yield self._add(elb, instances)
            self.log.info('Done.')


class DeregisterInstance(base.AWSBaseActor):

    """Remove EC2 instance(s) from an ELB.

    http://boto.readthedocs.org/en/latest/ref/elb.html
    #boto.ec2.elb.loadbalancer.LoadBalancer.deregister_instances
    """

    all_options = {
        'elb': (str, REQUIRED, 'Name of the ELB'),
        'region': (str, REQUIRED, 'AWS region name, like us-west-2'),
        'instances': ((str, list), None, (
            'Instance id, or list of ids. If no value is specified then '
            'the instance id of the executing machine is used.'))
    }

    @concurrent.run_on_executor
    @utils.exception_logger
    @retry
    def _remove(self, elb, instances):
        """Invoke elb.deregister_instances

        This boto function is idempotent, so any retry is OK.

        Args:
            elb: boto Loadbalancer object
            instances: list of instance ids.
        """
        elb.deregister_instances(instances)

    @gen.coroutine
    def _execute(self):
        elb = yield self._find_elb(self.option('elb'))
        instances = self.option('instances')

        if not instances:
            self.log.debug('No instance provided. Using current instance id.')
            iid = yield self._get_meta_data('instance-id')
            instances = [iid]
            self.log.debug('Instances is: %s' % instances)

        if type(instances) is not list:
            instances = [instances]

        self.log.info(('Removing the following instances from elb: '
                       '%s' % ', '.join(instances)))
        if not self._dry:
            yield self._remove(elb, instances)
            self.log.info('Done.')
