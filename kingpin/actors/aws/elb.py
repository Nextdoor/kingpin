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

"""Misc Actor objects"""

import logging
import math

from tornado import gen
from boto.ec2 import elb

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

    required_options = ['name', 'count']

    @gen.coroutine
    def _wait(self):
        # boto pools connections
        conn = yield utils.thread_coroutine(
            elb.ELBConnection,
            aws_settings.AWS_SECRET_ACCESS_KEY,
            aws_settings.AWS_ACCESS_KEY_ID)

        self._log(logging.INFO,
                  'Searching for ELB "%s"' % self._options['name'])
        found_elb = yield utils.thread_coroutine(
            conn.get_all_loadbalancer,
            load_balancer_names=self._options['name'])
        self._log(logging.INFO, 'ELBs found: %s' % found_elb)

        if not found_elb:
            raise exceptions.UnrecoverableActionFailure(
                ('Could not find an ELB to operate on "%s"' %
                 self._options['name']))

        while True:
            self._log(logging.INFO,
                      ('Counting ELB InService instances for : %s' %
                       self._options['name']))
            # Get all instances for this ELB
            instance_list = yield utils.thread_coroutine(
                found_elb.get_instance_health)
            total_count = len(instance_list)

            log.debug('All instances: %s' % instance_list)
            if not self._dry:
                # Count ones with "state" = "InService"
                in_service_count = [
                    i.state for i in instance_list].count('InService')
            else:
                self._log(logging.INFO, (
                    'Assuming that %s instances in %s are healthy.' %
                    (self._options['count'], self._options['name'])))
                in_service_count = total_count

            # Since the count can be provided as a number, or percentage
            # figure out the expected count here.
            count = self._options['count']
            if isinstance(count, int):
                expected_count = self._options['count']
            elif '%' in count:
                self._log(logging.INFO, '%s%% of ')
                expected_count = math.ceil(
                    total_count * p2f(self._options['count']))
            else:
                raise exceptions.InvalidOptions(
                    '`count` should be an integer or a string with % in it.')

            healthy_enough = in_service_count >= expected_count

            if not healthy_enough:
                reason = 'Health count %s is below the required %s' % (
                         in_service_count, expected_count)

            if not healthy_enough and not self._dry:
                self._log(logging.INFO, reason)
                self._log(logging.INFO, 'Retrying in 3 seconds.')
                yield utils.tornado_sleep(seconds=3)
            else:
                break  # healthy enough! Break out of the forever loop.

        raise gen.Return(True)

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        raises: gen.Return(True)
        """

        yield self._wait()

        raise gen.Return(True)
