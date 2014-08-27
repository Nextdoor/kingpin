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

from tornado import gen
from boto.ec2 import elb as aws_elb

from kingpin.actors.aws import settings as aws_settings
from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin import utils

log = logging.getLogger(__name__)

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'


# Helper function
def p2f(string):
    """Convert percentage string into float.

    Converts string like '78.9%' into 0.789
    """
    return float(string.strip('%'))/100


class WaitUntilHealthy(base.BaseActor):
    """Waits till a specified number of instances are "InService"."""

    required_options = ['name', 'count', 'region']

    def __init__(self, *args, **kwargs):
        """Set up connection object.

        Option Arguments:
            name: string - name of the ELB
            count: int, or string with %. (i.e. 4, or '80%')
            region: string - AWS region name, like us-west-2.
        """

        super(WaitUntilHealthy, self).__init__(*args, **kwargs)

        region = self._get_region(self._options['region'])

        self.conn = aws_elb.ELBConnection(
            aws_settings.AWS_SECRET_ACCESS_KEY,
            aws_settings.AWS_ACCESS_KEY_ID,
            region=region)

    def _get_region(self, region):
        """Return a RegionInfo object from boto.ec2.elb"""

        all_regions = aws_elb.regions()
        match = [r for r in all_regions if r.name == region]
        if len(match) != 1:
            raise exceptions.UnrecoverableActionFailure((
                'Expected to find exactly 1 region named %s. '
                'Found: %s') % (region, match))

        return match[0]

    @gen.coroutine
    def _find_elb(self, name):
        """Return an ELB with the matching name.

        Must find exactly 1 match. Zones are limited by the AWS credentials"""
        self._log(logging.INFO, 'Searching for ELB "%s"' % name)

        elbs = yield utils.thread_coroutine(
            self.conn.get_all_load_balancers,
            load_balancer_names=name)
        self._log(logging.INFO, 'ELBs found: %s' % elbs)

        if len(elbs) != 1:
            raise exceptions.UnrecoverableActionFailure(
                ('Expected to find exactly 1 ELB. Found %s: %s' %
                 (len(elbs), elbs)))

        raise gen.Return(elbs[0])

    def _get_expected_count(self, count, total_count):
        """Calculate the expected count for a given percentage.

        Either returns the passed count if it's an integer, or
        calculates the count given an expected percentage."""

        if isinstance(count, int):
            expected_count = count
        elif '%' in count:
            expected_count = math.ceil(total_count * p2f(count))

        return expected_count

    @gen.coroutine
    def _is_healthy(self, elb, count):
        """Check if there are `count` InService instances for a given elb.

        Args:
            count: integer, or string with % in it.
                   for more information read _get_expected_count()"""
        name = elb.name

        self._log(logging.INFO,
                  ('Counting ELB InService instances for : %s' % name))

        # Get all instances for this ELB
        instance_list = yield utils.thread_coroutine(
            elb.get_instance_health)
        total_count = len(instance_list)

        log.debug('All instances: %s' % instance_list)
        in_service_count = [
            i.state for i in instance_list].count('InService')

        expected_count = self._get_expected_count(count, total_count)

        healthy = in_service_count >= expected_count
        self._log(logging.INFO, 'ELB "%s" healthy: %s' % (elb.name, healthy))
        self._log(logging.INFO, 'InService vs expected: %s / %s' % (
                                in_service_count, expected_count))

        raise gen.Return(healthy)

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
