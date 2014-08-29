"""Simple integration tests for the AWS ELB actors."""

from nose.plugins.attrib import attr
import logging

from tornado import testing

from kingpin import utils
from kingpin.actors.aws import elb

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'

log = logging.getLogger(__name__)
logging.getLogger('boto').setLevel(logging.INFO)


class IntegrationSQS(testing.AsyncTestCase):
    """High level ELB Actor testing.

    Note, these tests must be run in-order. The order is defined by
    their definition order in this file. Nose follows this order according
    to its documentation:

        http://nose.readthedocs.org/en/latest/writing_tests.html
    """

    integration = True

    elb_name = 'kingpin-integration-test-useast1'

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_01_check_elb_health(self):
        actor = elb.WaitUntilHealthy(
            'Test',
            {'name': self.elb_name,
             'count': 0,
             'region': 'us-east-1'})

        yield utils.tornado_sleep(0.01)  # Prevents IOError close() errors
        done = yield actor.execute()
        yield utils.tornado_sleep(0.01)  # Prevents IOError close() errors

        self.assertTrue(done)

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_01_wait_for_elb_health(self):
        actor = elb.WaitUntilHealthy(
            'Test',
            {'name': self.elb_name,
             'count': 1,
             'region': 'us-east-1'})

        wait_task = actor.execute()
        yield utils.tornado_sleep(1)

        # Expected count is 1, so this should not be done yet...
        self.assertFalse(wait_task.done())

        # Not going to add any instances in this test, so let's abort
        wait_task.cancel()
        yield utils.tornado_sleep(3)
        self.assertTrue(wait_task.done())
