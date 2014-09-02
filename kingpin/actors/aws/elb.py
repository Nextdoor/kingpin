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
from concurrent import futures
from tornado import concurrent
from tornado import gen
from tornado import ioloop

from kingpin import utils
from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.actors.aws import settings as aws_settings

log = logging.getLogger(__name__)

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'


# This executor is used by the tornado.concurrent.run_on_executor()
# decorator. We would like this to be a class variable so its shared
# across RightScale objects, but we see testing IO errors when we
# do this.
EXECUTOR = futures.ThreadPoolExecutor(10)


# Helper function
def p2f(string):
    """Convert percentage string into float.

    Converts string like '78.9%' into 0.789
    """
    return float(string.strip('%')) / 100


class WaitUntilHealthy(base.BaseActor):

    """Waits till a specified number of instances are "InService"."""

    required_options = ['name', 'count', 'region']

    # Get references to existing objects that are used by the
    # tornado.concurrent.run_on_executor() decorator.
    ioloop = ioloop.IOLoop.current()
    executor = EXECUTOR

    def __init__(self, *args, **kwargs):
        """Set up connection object.

        Option Arguments:
            name: string - name of the ELB
            count: int, or string with %. (i.e. 4, or '80%')
            region: string - AWS region name, like us-west-2.
        """

        super(WaitUntilHealthy, self).__init__(*args, **kwargs)

        region = self._get_region(self._options['region'])

        if not (aws_settings.AWS_ACCESS_KEY_ID and
                aws_settings.AWS_SECRET_ACCESS_KEY):
            raise exceptions.InvalidCredentials(
                'AWS settings imported but not all credentials are supplied. '
                'AWS_ACCESS_KEY_ID: %s, AWS_SECRET_ACCESS_KEY: %s' % (
                    aws_settings.AWS_ACCESS_KEY_ID,
                    aws_settings.AWS_SECRET_ACCESS_KEY))

        self.conn = aws_elb.ELBConnection(
            aws_settings.AWS_ACCESS_KEY_ID,
            aws_settings.AWS_SECRET_ACCESS_KEY,
            region=region)

    def _get_region(self, region):
        """Return 'region' object used in ELBConnection

        Args:
            region: string - AWS region name, like us-west-2
        Returns:
            RegionInfo object from boto.ec2.elb
        """

        all_regions = aws_elb.regions()
        match = [r for r in all_regions if r.name == region]

        if len(match) != 1:
            raise exceptions.UnrecoverableActionFailure((
                'Expected to find exactly 1 region named %s. '
                'Found: %s') % (region, match))

        return match[0]

    @concurrent.run_on_executor
    @utils.exception_logger
    def _find_elb(self, name):
        """Return an ELB with the matching name.

        Must find exactly 1 match. Zones are limited by the AWS credentials"""
        self._log(logging.INFO, 'Searching for ELB "%s"' % name)

        elbs = self.conn.get_all_load_balancers(load_balancer_names=name)
        self._log(logging.INFO, 'ELBs found: %s' % elbs)

        if len(elbs) != 1:
            raise exceptions.UnrecoverableActionFailure(
                ('Expected to find exactly 1 ELB. Found %s: %s' %
                 (len(elbs), elbs)))

        return elbs[0]

    def _get_expected_count(self, count, total_count):
        """Calculate the expected count for a given percentage.

        Either returns the passed count if it's an integer, or
        calculates the count given an expected percentage."""

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
                   for more information read _get_expected_count()"""
        name = elb.name

        self._log(logging.INFO,
                  ('Counting ELB InService instances for : %s' % name))

        # Get all instances for this ELB
        instance_list = elb.get_instance_health()
        total_count = len(instance_list)

        self._log(logging.DEBUG, 'All instances: %s' % instance_list)
        in_service_count = [
            i.state for i in instance_list].count('InService')

        expected_count = self._get_expected_count(count, total_count)

        healthy = (in_service_count >= expected_count)
        self._log(logging.INFO, 'ELB "%s" healthy: %s' % (elb.name, healthy))
        self._log(logging.INFO, 'InService vs expected: %s / %s' % (
                                in_service_count, expected_count))

        return healthy

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        raises: gen.Return(True)
        """

        elb = yield self._find_elb(name=self._options['name'])

        while True:
            healthy = yield self._is_healthy(elb, count=self._options['count'])

            if healthy is True:
                self._log(logging.INFO, 'ELB is healthy. Exiting.')
                break

            # Not healthy :( continue looping

            if self._dry:
                self._log(logging.INFO, 'Pretending that ELB is healthy.')
                break

            self._log(logging.INFO, 'Retrying in 3 seconds.')
            yield utils.tornado_sleep(3)

        raise gen.Return(True)
