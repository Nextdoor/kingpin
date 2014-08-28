import logging

from tornado import gen
from tornado import testing
import mock

from kingpin import utils
from kingpin.actors.aws import elb as elb_actor

log = logging.getLogger(__name__)


@gen.coroutine
def tornado_value(*args):
    """Returns whatever is passed in. Used for testing."""
    raise gen.Return(*args)


class TestELBActor(testing.AsyncTestCase):

    @testing.gen_test
    def test_execute(self):

        actor = elb_actor.WaitUntilHealthy(
            'Unit Test Action', {'name': 'unit-test-queue',
                                 'region': 'us-west-2',
                                 'count': 3})

        actor._find_elb = mock.Mock(return_value=tornado_value())
        actor._is_healthy = mock.Mock(return_value=tornado_value(True))

        val = yield actor._execute()
        self.assertEquals(actor._find_elb.call_count, 1)
        self.assertEquals(actor._is_healthy.call_count, 1)
        self.assertTrue(val)

    @testing.gen_test
    def test_execute_retry(self):

        actor = elb_actor.WaitUntilHealthy(
            'Unit Test Action', {'name': 'unit-test-queue',
                                 'region': 'us-west-2',
                                 'count': 3})

        actor._find_elb = mock.Mock(return_value=tornado_value())
        actor._is_healthy = mock.Mock(
            side_effect=[tornado_value(False),
                         tornado_value(True)])

        # Optional mock -- making the test quicker.
        short_sleep = utils.tornado_sleep(0)
        with mock.patch('kingpin.utils.tornado_sleep') as ts:
            ts.return_value = short_sleep
            val = yield actor._execute()

        self.assertEquals(actor._find_elb.call_count, 1)  # Don't refetch!
        self.assertEquals(actor._is_healthy.call_count, 2)  # Retry!
        self.assertTrue(val)

    @testing.gen_test
    def test_execute_dry(self):

        actor = elb_actor.WaitUntilHealthy(
            'Unit Test Action', {'name': 'unit-test-queue',
                                 'region': 'us-west-2',
                                 'count': 3},
            dry=True)

        actor._find_elb = mock.Mock(return_value=tornado_value())
        # NOTE: this is false, but assertion is True!
        actor._is_healthy = mock.Mock(return_value=tornado_value(False))

        val = yield actor._execute()
        self.assertEquals(actor._find_elb.call_count, 1)
        self.assertEquals(actor._is_healthy.call_count, 1)
        self.assertTrue(val)

    def test_get_region(self):
        actor = elb_actor.WaitUntilHealthy(
            'Unit Test Action', {'name': 'unit-test-queue',
                                 'region': 'us-west-2',
                                 'count': 3})

        reg = actor._get_region('us-west-2')
        self.assertEquals(reg.name, 'us-west-2')

    def test_get_region_fail(self):
        with self.assertRaises(Exception):
            elb_actor.WaitUntilHealthy(
                'Unit Test Action', {'name': 'unit-test-queue',
                                     'region': 'non-existent',  # Should fail
                                     'count': 3})

    @testing.gen_test
    def test_find_elb(self):
        actor = elb_actor.WaitUntilHealthy(
            'Unit Test Action', {'name': 'unit-test-queue',
                                 'region': 'us-west-2',
                                 'count': 3})

        actor.conn = mock.Mock()
        actor.conn.get_all_load_balancers = mock.Mock(return_value=['test'])

        elb = yield actor._find_elb('')

        self.assertEquals(elb, 'test')
        self.assertEquals(actor.conn.get_all_load_balancers.call_count, 1)

        actor.conn.get_all_load_balancers.assert_called_with(
            load_balancer_names='')

    @testing.gen_test
    def test_find_elb_error(self):
        actor = elb_actor.WaitUntilHealthy(
            'Unit Test Action', {'name': 'unit-test-queue',
                                 'region': 'us-west-2',
                                 'count': 3})

        actor.conn = mock.Mock()
        # Returning no elbs :(
        actor.conn.get_all_load_balancers = mock.Mock(return_value=[])

        with self.assertRaises(Exception):
            yield actor._find_elb('')

    def test_get_expected_count(self):
        actor = elb_actor.WaitUntilHealthy(
            'Unit Test Action', {'name': 'unit-test-queue',
                                 'region': 'us-west-2',
                                 'count': 3})

        self.assertEquals(actor._get_expected_count(5, 1), 5)
        self.assertEquals(actor._get_expected_count('50%', 20), 10)

    @testing.gen_test
    def test_is_healthy(self):
        actor = elb_actor.WaitUntilHealthy(
            'Unit Test Action', {'name': 'unit-test-queue',
                                 'region': 'us-west-2',
                                 'count': 3})

        elb = mock.Mock()
        elb.get_instance_health.return_value = [
            mock.Mock(state='InService'),
            mock.Mock(state='InService'),
            mock.Mock(state='InService'),
            mock.Mock(state='OutOfService'),
            mock.Mock(state='OutOfService'),
            ]
        val = yield actor._is_healthy(elb, 3)

        self.assertTrue(val)
