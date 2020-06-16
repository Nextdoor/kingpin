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
:mod:`kingpin.actors.aws.elb`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
"""

import logging
import math

from boto.exception import BotoServerError
from tornado import concurrent
from tornado import gen

from kingpin import utils
from kingpin.actors import exceptions
from kingpin.actors.aws import base
from kingpin.actors.utils import dry
from kingpin.constants import REQUIRED

log = logging.getLogger(__name__)

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'


# This executor is used by the tornado.concurrent.run_on_executor()
# decorator. We would like this to be a class variable so its shared
# across RightScale objects, but we see testing IO errors when we
# do this.
EXECUTOR = concurrent.futures.ThreadPoolExecutor(10)


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
        'region': (str, REQUIRED, 'AWS region (or zone) name, like us-west-2')
    }


class WaitUntilHealthy(ELBBaseActor):

    """Wait indefinitely until a specified ELB is considered "healthy".

    This actor will loop infinitely until a healthy threshold of the ELB is
    met.  The threshold can be reached when the ``count`` as specified in the
    options is less than or equal to the number of InService instances in the
    ELB.

    Another situation is for ``count`` to be a string specifying a percentage
    (see examples). In this case the percent of InService instances has to be
    greater than the ``count`` percentage.

    **Options**

    :name:
      The name of the ELB to operate on

    :count:
      Number, or percentage of InService instance to consider this ELB healthy

    :region:
      AWS region (or zone) name, such as us-east-1 or us-west-2

    **Examples**

    .. code-block:: json

       { "actor": "aws.elb.WaitUntilHealthy",
         "desc": "Wait until production-frontend has 16 hosts",
         "options": {
           "name": "production-frontend",
           "count": 16,
           "region": "us-west-2"
         }
       }

    .. code-block:: json

       { "actor": "aws.elb.WaitUntilHealthy",
         "desc": "Wait until production-frontend has 85% of hosts in-service",
         "options": {
           "name": "production-frontend",
           "count": "85%",
           "region": "us-west-2"
         }
       }

    **Dry Mode**

    This actor performs the finding of the ELB as well as calculating its
    health at all times. The only difference in dry mode is that it will not
    re-count the instances if the ELB is not healthy. A log message will be
    printed indicating that the run is dry, and the actor will exit with
    success.
    """

    desc = "Waiting until {name} is healthy ({count} in-service)"

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

    @gen.coroutine
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
        instance_list = yield self.api_call(elb.get_instance_health)
        total_count = len(instance_list)

        self.log.debug('All instances: %s' % instance_list)
        in_service_count = [
            i.state for i in instance_list].count('InService')

        expected_count = self._get_expected_count(count, total_count)

        healthy = (in_service_count >= expected_count)
        self.log.debug('ELB "%s" healthy state: %s' % (elb.name, healthy))

        raise gen.Return(healthy)

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

    """Find a server cert in IAM and use it for a specified ELB.

    **Options**

    :region:
      (str) AWS region (or zone) name, like us-west-2

    :name:
      (str) Name of the ELB

    :cert_name:
      (str) Unique IAM certificate name, or ARN

    :port:
      (int) Port associated with the cert.
      (default: 443)

    **Example**

    .. code-block:: json

       { "actor": "aws.elb.SetCert",
         "desc": "Run SetCert",
         "options": {
           "cert_name": "new-cert",
           "name": "some-elb",
           "region": "us-west-2"
         }
       }

    **Dry run**

    Will check that ELB and Cert names are existent, and will also check that
    the credentials provided for AWS have access to the new cert for ssl.
    """

    all_options = {
        'name': (str, REQUIRED, 'Name of the ELB'),
        'port': (int, 443, 'Port associated with the cert'),
        'region': (str, REQUIRED, 'AWS region (or zone) name, like us-west-2'),
        'cert_name': (str, REQUIRED, 'Unique IAM certificate name, or ARN'),
    }

    @gen.coroutine
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
            yield self.api_call(
                elb.set_listener_SSL_certificate,
                self.option('port'),
                '')
        except BotoServerError as e:
            if e.error_code == 'AccessDenied':
                raise exceptions.InvalidCredentials(e)

    @gen.coroutine
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
            cert = yield self.api_call(
                self.iam_conn.get_server_certificate, name)
        except BotoServerError as e:
            raise CertNotFound(
                'Could not find cert %s. Reason: %s' % (name, e))

        # Get the ARN of this cert
        arn = cert['get_server_certificate_response'].get(
            'get_server_certificate_result').get(
            'server_certificate').get(
            'server_certificate_metadata').get('arn')

        raise gen.Return(arn)

    @gen.coroutine
    @dry('Would instruct {elb} to use cert: {arn}')
    def _use_cert(self, elb, arn):
        """Assign an ssl cert to a given ELB.

        Args:
            elb: boto elb object.
            arn: ARN for server certificate to use.
        """

        self.log.info('Setting ELB "%s" to use cert arn: %s' % (elb, arn))
        try:
            yield self.api_call(
                elb.set_listener_SSL_certificate, self.option('port'), arn)
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

        yield self._use_cert(elb=elb, arn=cert_arn)


class RegisterInstance(base.AWSBaseActor):

    """Add an EC2 instance to a load balancer or target group.

    **Options**

    :elb:
      (str) Name of the ELB or the Target Group ARN

    :instances:
      (str, list) Instance id, or list of ids. Default "self" id.

    :region:
      (str) AWS region (or zone) name, like us-west-2

    :enable_zones:
      (bool) add all available AZ to the elb. Default: True

    **Example**

    .. code-block:: json

       { "actor": "aws.elb.RegisterInstance",
         "desc": "Run RegisterInstance",
         "options": {
           "elb": "prod-loadbalancer",
           "instances": "i-123456",
           "region": "us-east-1",
         }
       }

    .. code-block:: yaml

       ---
       actor: aws.elb.RegisterInstance
       desc: Run RegisterInstance
       options:
         elb: prod-loadbalancer
         instances: i-123456
         region: us-east-1

    **Dry run**

    Will find the specified ELB, but not take any actions regarding instances.
    """

    all_options = {
        'elb': (str, REQUIRED, 'Name of the ELB'),
        'region': (str, REQUIRED, 'AWS region (or zone) name, like us-west-2'),
        'instances': ((str, list), None, (
            'Instance id, or list of ids. If no value is specified then '
            'the instance id of the executing machine is used.')),
        'enable_zones': ((str, bool), True, 'Enable all zones for this ELB.')
    }

    @gen.coroutine
    @dry('Would add {instances} to {elb}')
    def _add(self, elb, instances):
        """Invoke elb.register_instances

        Args:
            elb: boto Loadbalancer object
            instances: list of instance ids.
        """
        yield self.api_call(elb.register_instances, instances)

    @gen.coroutine
    @dry('Would ensure {elb} is a member of all AZs')
    def _check_elb_zones(self, elb):
        """Ensure that `elb` has all available zones."""
        zones = yield self.api_call(self.ec2_conn.get_all_zones)
        zone_names = {z.name for z in zones}

        enabled_zones = set(elb.availability_zones)

        if not zone_names.issubset(enabled_zones):
            self.log.warning('ELB "%s" is missing some AZ.' % elb.name)
            self.log.info('Enabling all zones: %s' % zone_names)
            yield self.api_call(elb.enable_zones, zone_names)

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
        yield self._add(elb=elb, instances=instances)

        if self.str2bool(self.option('enable_zones')):
            yield self._check_elb_zones(elb=elb)


class DeregisterInstance(base.AWSBaseActor):

    """Remove EC2 instance(s) from an ELB.

    **Options**

    :elb:
      (str) Name of the ELB. Optionally this may also be a `*`.

    :instances:
      (str, list) Instance id, or list of ids

    :region:
      (str) AWS region (or zone) name, like us-west-2

    :wait_on_draining:
      (bool) Whether or not to wait for connection draining

    **Example**

    .. code-block:: json

       { "actor": "aws.elb.DeregisterInstance",
         "desc": "Run DeregisterInstance",
         "options": {
           "elb": "my-webserver-elb",
           "instances": "i-abcdeft",
           "region": "us-west-2"
         }
       }

    .. code-block:: yaml

       ---
       actor: aws.elb.DeregisterInstance
       desc: Run DeregisterInstance
       options:
         elb: prod-loadbalancer
         instances: i-123456
         region: us-east-1

    Extremely simple way to remove the local instance running this code from
    all ELBs its been joined to:

    .. code-block:: json

       { "actor": "aws.elb.DeregisterInstance",
         "desc": "Run DeregisterInstance",
         "options": {
           "elb": "*",
           "region": "us-west-2"
         }
       }

    **Dry run**

    Will find the ELB but not take any actions regarding the instances.
    """

    all_options = {
        'elb': (str, REQUIRED, 'Name of the ELB'),
        'region': (str, REQUIRED, 'AWS region (or zone) name, like us-west-2'),
        'instances': ((str, list), None, (
            'Instance id, or list of ids. If no value is specified then '
            'the instance id of the executing machine is used.')),
        'wait_on_draining': ((str, bool), True, (
            'Whether or not to wait for the ELB to drain connections '
            'before returning from the actor.'))
    }

    @gen.coroutine
    @dry('Would remove instances from {elb}: {instances}')
    def _remove(self, elb, instances):
        """Invoke elb.deregister_instances

        Args:
            elb: boto Loadbalancer object
            instances: list of instance ids.
        """
        self.log.info(('Removing instances from %s: %s'
                      % (elb, ', '.join(instances))))

        yield self.api_call(elb.deregister_instances, instances)
        yield self._wait_on_draining(elb)

    @gen.coroutine
    def _wait_on_draining(self, elb):
        """Waits for the ELB Connection Draining to occur.

        ELB Connection Draining is a configured-setting on the ELB that will
        continue to allow existing connections to be handeled before finally
        cutting them off at the timeout. This method will detect if connection
        draining is enabled, and optionally "sleep" for that time period before
        returning from the actor.

        Args:
            elb: boto Loadbalancer object
        """
        if not self.str2bool(self.option('wait_on_draining')):
            self.log.warning('Not waiting for connections to drain!')

        attrs = yield self.api_call(elb.get_attributes)
        if attrs.connection_draining.enabled:
            timeout = attrs.connection_draining.timeout

            self.log.info('Connection Draining Enabled, waiting %s(s)'
                          % timeout)
            yield utils.tornado_sleep(timeout)

    @gen.coroutine
    def _find_instance_elbs(self, instances):
        """Finds all ELBs that Instances are members of.

        Searches through all of the ELBs in a particular region and looks for
        which ones have any of the instances supplied in them. Creates a list
        of the ELBs, and returns the entire list.

        Args:
            instances: A list of Instance IDs

        Returns:
            a list of LoadBalancer objects
        """
        all_elbs = yield self.api_call(self.elb_conn.get_all_load_balancers)
        elbs_with_members = []

        for instance in instances:
            elbs = [lb for lb in all_elbs
                    if instance in [i.id for i in lb.instances]]
            self.log.debug('%s is a member of %s' % (instance, elbs))
            elbs_with_members.extend(elbs)

        raise gen.Return(elbs_with_members)

    @gen.coroutine
    def _execute(self):
        instances = self.option('instances')

        if not instances:
            self.log.debug('No instance provided. Using current instance id.')
            iid = yield self._get_meta_data('instance-id')
            instances = [iid]
            self.log.debug('Instances is: %s' % instances)

        if type(instances) is not list:
            instances = [instances]

        if self.option('elb') == '*':
            elbs = yield self._find_instance_elbs(instances)
        else:
            elb = yield self._find_elb(self.option('elb'))
            elbs = [elb]

        tasks = []
        for elb in elbs:
            tasks.append(self._remove(elb=elb, instances=instances))

        yield tasks
