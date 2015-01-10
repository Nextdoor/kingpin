"""Simple integration tests for the AWS CloudFormation actors."""

from nose.plugins.attrib import attr
import logging

from tornado import testing

from kingpin import utils
from kingpin.actors import exceptions
from kingpin.actors.aws import elb

__author__ = 'Matt Wise <matt@nextdoor.com>'

log = logging.getLogger(__name__)
logging.getLogger('boto').setLevel(logging.INFO)


class IntegrationCreate(testing.AsyncTestCase):

    """High Level CloudFormation Testing.

    These tests will check two things:
    * Create a super-simple CloudFormation stack
    * Delete that same stack

    Requirements:
        Your AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must have access to
        create CF stacks. The stack we create is extremely simple, and should
        impact none of your AWS resources.

    Note, these tests must be run in-order. The order is defined by
    their definition order in this file. Nose follows this order according
    to its documentation:

        http://nose.readthedocs.org/en/latest/writing_tests.html
    """

    integration = True

    region = 'us-east-1'

#    @attr('integration')
#    @testing.gen_test(timeout=60)
#    def integration_01a_check_elb_health(self):
#        actor = elb.WaitUntilHealthy(
#            'Test',
#            {'name': self.elb_name,
#             'count': 0,
#             'region': self.region})
#
#        done = yield actor.execute()
#
#        self.assertEquals(done, None)
#
#    @attr('integration')
#    @testing.gen_test
#    def integration_01b_check_elb_not_found(self):
#        actor = elb.WaitUntilHealthy(
#            'Test',
#            {'name': 'Not-Found-ELB',
#             'count': 50,
#             'region': self.region})
#
#        with self.assertRaises(exceptions.RecoverableActorFailure):
#            yield actor.execute()
#
#    @attr('integration')
#    @testing.gen_test(timeout=60)
#    def integration_02_wait_for_elb_health(self):
#        actor = elb.WaitUntilHealthy(
#            'Test',
#            {'name': self.elb_name,
#             'count': 1,
#             'region': self.region})
#
#        # NOTE: We are not "yielding" the execution here, but the task
#        # goes on top of the IOLoop. The sleep statement below allows
#        # the wait_task's actions to get executed by tornado's loop.
#        wait_task = actor.execute()
#        yield utils.tornado_sleep(1)
#
#        # Expected count is 1, so this should not be done yet...
#        self.assertFalse(wait_task.done())
#
#        # Not going to add any instances in this test, so let's abort
#        wait_task.cancel()
#        yield utils.tornado_sleep(3)
#        self.assertTrue(wait_task.done())
