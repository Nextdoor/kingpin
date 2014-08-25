import logging
import mock

from tornado import testing

from kingpin import utils
from kingpin.actors import exceptions
from kingpin.actors.aws import elb as elb_actor

log = logging.getLogger(__name__)

from boto.ec2 import elb


class TestELBActor(testing.AsyncTestCase):

    @testing.gen_test
    def test_execute_with_number(self):
        self.actor = elb_actor.WaitUntilHealthy(
            'Unit Test Action', {'name': 'unit-test-queue',
                                 'count': 3})

        with mock.patch.object(elb, 'ELBConnection') as elbc:
            elbc().get_all_loadbalancer().get_instance_health.return_value = [
                mock.Mock(state='InService'),
                mock.Mock(state='InService'),
                mock.Mock(state='InService'),
                mock.Mock(state='OutOfService'),
                mock.Mock(state='OutOfService'),
                ]

            yield self.actor.execute()

            self.assertTrue(
                elbc().get_all_loadbalancer().get_instance_health.called)
            self.assertEquals(
                elbc().get_all_loadbalancer().get_instance_health.call_count,
                1)

    @testing.gen_test
    def test_execute_with_percent(self):
        self.actor = elb_actor.WaitUntilHealthy(
            'Unit Test Action', {'name': 'unit-test-queue',
                                 'count': '50%'})

        with mock.patch.object(elb, 'ELBConnection') as elbc:
            elbc().get_all_loadbalancer().get_instance_health.return_value = [
                mock.Mock(state='InService'),
                mock.Mock(state='InService'),
                mock.Mock(state='InService'),
                mock.Mock(state='OutOfService'),
                mock.Mock(state='OutOfService'),
                ]

            yield self.actor.execute()
            self.assertTrue(
                elbc().get_all_loadbalancer().get_instance_health.called)
            self.assertEquals(
                elbc().get_all_loadbalancer().get_instance_health.call_count,
                1)

    @testing.gen_test
    def test_execute_with_retry(self):
        self.actor = elb_actor.WaitUntilHealthy(
            'Unit Test Action', {'name': 'unit-test-queue',
                                 'count': 1})

        with mock.patch.object(elb, 'ELBConnection') as elbc:
            elbc().get_all_loadbalancer().get_instance_health.side_effect = (
                [], [mock.Mock(state='InService')])

            short_sleep = utils.tornado_sleep(0.1)  # Should not yield this!
            with mock.patch('kingpin.utils.tornado_sleep') as ts:
                ts.return_value = short_sleep
                yield self.actor.execute()

            # Test that list of instance healths was fetched twice
            self.assertEqual(
                elbc().get_all_loadbalancer().get_instance_health.call_count,
                2)

    @testing.gen_test
    def test_execute_dry(self):
        self.actor = elb_actor.WaitUntilHealthy(
            'Unit Test Action', {'name': 'unit-test-queue',
                                 'count': 3},
            dry=True)

        with mock.patch.object(elb, 'ELBConnection') as elbc:
            # Note that the count here is NOT 3
            elbc().get_all_loadbalancer().get_instance_health.return_value = []

            yield self.actor.execute()

    @testing.gen_test
    def test_execute_with_errors(self):
        self.actor = elb_actor.WaitUntilHealthy(
            'Unit Test Action', {'name': 'unit-test-queue',
                                 'count': 'fail-me'},
            dry=True)

        with mock.patch.object(elb, 'ELBConnection') as elbc:

            # 'count' should not be parsable right now
            with self.assertRaises(exceptions.InvalidOptions):
                yield self.actor.execute()

            # No elb by this name was found!
            elbc().get_all_loadbalancer.return_value = None
            with self.assertRaises(exceptions.UnrecoverableActionFailure):
                yield self.actor.execute()
