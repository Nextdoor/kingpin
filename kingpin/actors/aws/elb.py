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
import os

from tornado import gen
from boto.ec2 import elb

from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin import utils

log = logging.getLogger(__name__)

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'

AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID', None)
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY', None)


# Helper function
def p2f(string):
    """Convert percentage string into float.

    Converts string like '78.9%' into 0.789
    """
    return float(x.strip('%'))/100


class WaitTillNHealthy(base.HTTPBaseActor):
    """Waits till a specified number of instances are "InService"."""

    required_options = ['name', 'count']

    def __init__(self, *args, **kwargs):
        """Initializes the Actor.

        Args:
            desc: String description of the action being executed.
            options: Dictionary with the following settings:
              { 'name': ELB name,
                'count': Integer count, or string like '80%' }
        """
        super(WaitTillNHealthy, self).__init__(*args, **kwargs)

        self._elb_name = self._options['name']

    @gen.coroutine
    def _wait(self):
        # boto pools connections
        conn = yield utils.thread_coroutine(
            elb.ELBConnection,
            AWS_SECRET_ACCESS_KEY,
            AWS_ACCESS_KEY_ID)

        self._log(logging.INFO, 'Searching for ELB "%s"' % self._elb_name)
        found_elb = yield utils.thread_coroutine(
            conn.get_all_loadbalancer(load_balancer_names=self._elb_name))
        self._log(logging.INFO, 'ELBs found: %s' % found_elb)

        if not found_elb:
            raise exceptions.UnrecoverableActionFailure(
                'Could not find an ELB to operate on "%s"' % self._elb_name)


        recount = True
        while recount:
            self._log(logging.INFO, 'Counting ELB InService instances for : %s' % self._elb_name)
            # Get all instances for this ELB
            instance_list = yield utils.thread_coroutine(found_elb.get_instance_health)
            total_count = len(instance_list)

            if not self._dry:
                # Count ones with "state" = "InService"
                in_service_count = [i.state for i in instance_list].count('InService')
            else:
                self._log(logging.INFO, ('Assuming that %s instances in %s are healthy.' %
                                         (self._count, self._elb_name)))
                in_service_count = total_count

            if '%' in self._count:
                # Expecting a percentage of healthy instances.
                healthy_ratio = in_service_count / total_count
                expected_ratio = p2f(self._count)

                healthy_enough = healthy_ratio >= expected_ratio
                if not healthy_enough:
                    reason = 'Health ratio %s is below required %s' % (
                             healthy_ratio, expected_ratio)
            else:
                healthy_enough = in_service_count >= self._count

                if not healthy_enough:
                    reason = 'Health count %s is below required %s' % (
                             in_service_count, self._count)

            if not healthy_enough:
                self._log(logging.INFO, reason)
                self._log(logging.INFO, 'Retrying in 3 seconds.')
                utils.tornado_sleep(seconds=3)

        raise gen.Return(True)

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        raises: gen.Return(True)
        """

        yield self._wait()

        raise gen.Return(True)
