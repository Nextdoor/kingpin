import logging

from boto.exception import BotoServerError
from tornado import gen
from tornado import testing
import mock

from kingpin import utils
from kingpin.actors import exceptions
from kingpin.actors.aws import base
from kingpin.actors.aws import elb as elb_actor
from kingpin.actors.aws import settings
from kingpin.actors.test import helper

log = logging.getLogger(__name__)


@gen.coroutine
def tornado_value(*args):
    """Returns whatever is passed in. Used for testing."""
    raise gen.Return(*args)


class TestRegisterInstance(testing.AsyncTestCase):

    def setUp(self):
        super(TestRegisterInstance, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'

    @testing.gen_test
    def test_add(self):
        act = elb_actor.RegisterInstance('UTA', {
            'elb': 'test',
            'region': 'test',
            'instance_id': 'test'})

        elb = mock.Mock()
        instance = 'i-un173s7'
        yield act._add(elb, [instance])

        elb.register_instances.assert_called_with([instance])

    @testing.gen_test
    def test_execute(self):
        act = elb_actor.RegisterInstance('UTA', {
            'elb': 'elb-test',
            'region': 'region-test',
            'instance_id': 'i-test'})

        act._find_elb = mock.Mock()
        act._find_elb.return_value = helper.tornado_value(mock.Mock())
        act._add = mock.Mock()
        act._add.return_value = helper.tornado_value(mock.Mock())
        yield act._execute()

        act._find_elb.assert_called_with('elb-test')
        lb = yield act._find_elb()
        act._add.assert_called_with(lb, ['i-test'])

    @testing.gen_test
    def test_execute_dry(self):
        act = elb_actor.RegisterInstance('UTA', {
            'elb': 'elb-test',
            'region': 'region-test',
            'instance_id': 'i-test'},
            dry=True)

        act._find_elb = mock.Mock()
        act._find_elb.return_value = helper.tornado_value(mock.Mock())
        act._add = mock.Mock()
        act._add.return_value = helper.tornado_value(mock.Mock())
        yield act._execute()

        act._find_elb.assert_called_with('elb-test')
        yield act._find_elb()
        self.assertEquals(0, act._add.call_count)


class TestRemoveInstance(testing.AsyncTestCase):

    def setUp(self):
        super(TestRemoveInstance, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'

    @testing.gen_test
    def test_remove(self):
        act = elb_actor.RemoveInstance('UTA', {
            'elb': 'test',
            'region': 'test',
            'instance_id': 'test'})

        elb = mock.Mock()
        instance = 'i-un173s7'
        yield act._remove(elb, [instance])

        elb.deregister_instances.assert_called_with([instance])

    @testing.gen_test
    def test_execute(self):
        act = elb_actor.RemoveInstance('UTA', {
            'elb': 'elb-test',
            'region': 'region-test',
            'instance_id': 'i-test'})

        act._find_elb = mock.Mock()
        act._find_elb.return_value = helper.tornado_value(mock.Mock())
        act._remove = mock.Mock()
        act._remove.return_value = helper.tornado_value(mock.Mock())
        yield act._execute()

        act._find_elb.assert_called_with('elb-test')
        lb = yield act._find_elb()
        act._remove.assert_called_with(lb, ['i-test'])

    @testing.gen_test
    def test_execute_dry(self):
        act = elb_actor.RemoveInstance('UTA', {
            'elb': 'elb-test',
            'region': 'region-test',
            'instance_id': 'i-test'},
            dry=True)

        act._find_elb = mock.Mock()
        act._find_elb.return_value = helper.tornado_value(mock.Mock())
        act._remove = mock.Mock()
        act._remove.return_value = helper.tornado_value(mock.Mock())
        yield act._execute()

        act._find_elb.assert_called_with('elb-test')
        yield act._find_elb()
        self.assertEquals(0, act._remove.call_count)


class TestWaitUntilHealthy(testing.AsyncTestCase):

    def setUp(self):
        super(TestWaitUntilHealthy, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'

    @testing.gen_test
    def test_require_env(self):

        settings.AWS_ACCESS_KEY_ID = ''
        with self.assertRaises(exceptions.InvalidCredentials):
            elb_actor.WaitUntilHealthy('Unit Test Action', {
                'name': 'unit-test-queue',
                'region': 'us-west-2',
                'count': 3})

    @testing.gen_test
    def test_execute(self):

        actor = elb_actor.WaitUntilHealthy(
            'Unit Test Action', {'name': 'unit-test-queue',
                                 'region': 'us-west-2',
                                 'count': 3})

        actor._find_elb = mock.Mock(return_value=tornado_value('ELB'))
        actor._is_healthy = mock.Mock(return_value=tornado_value(True))

        val = yield actor._execute()
        self.assertEquals(actor._find_elb.call_count, 1)
        self.assertEquals(actor._is_healthy.call_count, 1)
        self.assertEquals(val, None)

    @testing.gen_test
    def test_execute_retry(self):

        actor = elb_actor.WaitUntilHealthy(
            'Unit Test Action', {'name': 'unit-test-queue',
                                 'region': 'us-west-2',
                                 'count': 3})

        actor._find_elb = mock.Mock(return_value=tornado_value('ELB'))
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
        self.assertEquals(val, None)

    @testing.gen_test
    def test_execute_dry(self):

        actor = elb_actor.WaitUntilHealthy(
            'Unit Test Action', {'name': 'unit-test-queue',
                                 'region': 'us-west-2',
                                 'count': 3},
            dry=True)

        actor._find_elb = mock.Mock(return_value=tornado_value('ELB'))
        # NOTE: this is false, but assertion is True!
        actor._is_healthy = mock.Mock(return_value=tornado_value(False))

        val = yield actor._execute()
        self.assertEquals(actor._find_elb.call_count, 1)
        self.assertEquals(actor._is_healthy.call_count, 1)
        self.assertEquals(val, None)

    @testing.gen_test
    def test_execute_fail(self):

        actor = elb_actor.WaitUntilHealthy(
            'Unit Test ACtion', {'name': 'unit-test-queue',
                                 'region': 'us-west-2',
                                 'count': 7})
        # ELB not found...
        actor.elb_conn.get_all_load_balancers = mock.Mock(
            side_effect=BotoServerError(400, 'Testing'))

        with self.assertRaises(base.ELBNotFound):
            yield actor.execute()

    def test_get_region(self):
        actor = elb_actor.WaitUntilHealthy(
            'Unit Test Action', {'name': 'unit-test-queue',
                                 'region': 'us-west-2',
                                 'count': 3})

        reg = actor._get_region('us-west-2')
        self.assertEquals(reg.name, 'us-west-2')

    def test_get_region_fail(self):
        with self.assertRaises(exceptions.UnrecoverableActorFailure):
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

        actor.elb_conn = mock.Mock()
        actor.elb_conn.get_all_load_balancers.return_value = ['test']

        elb = yield actor._find_elb('')

        self.assertEquals(elb, 'test')
        self.assertEquals(actor.elb_conn.get_all_load_balancers.call_count, 1)

        actor.elb_conn.get_all_load_balancers.assert_called_with(
            load_balancer_names='')

    @testing.gen_test
    def test_find_elb_error(self):
        actor = elb_actor.WaitUntilHealthy(
            'Unit Test Action', {'name': 'unit-test-queue',
                                 'region': 'us-west-2',
                                 'count': 3})

        # Pretend the request worked, but there are no ELBs
        actor.elb_conn = mock.Mock()
        actor.elb_conn.get_all_load_balancers = mock.Mock(return_value=[])
        with self.assertRaises(base.ELBNotFound):
            yield actor._find_elb('')

        # Now pretend the request failed
        actor.elb_conn.get_all_load_balancers = mock.Mock(
            side_effect=BotoServerError(400, 'Testing'))
        with self.assertRaises(base.ELBNotFound):
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
