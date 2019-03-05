import logging

from boto.exception import BotoServerError
from tornado import testing
import mock

from kingpin import utils
from kingpin.actors import exceptions
from kingpin.actors.aws import elb as elb_actor
from kingpin.actors.aws import settings
from kingpin.actors.test import helper
import importlib

log = logging.getLogger(__name__)


class TestRegisterInstance(testing.AsyncTestCase):

    def setUp(self):
        super(TestRegisterInstance, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        importlib.reload(elb_actor)

    @testing.gen_test
    def test_add(self):
        act = elb_actor.RegisterInstance('UTA', {
            'elb': 'test',
            'region': 'us-east-1',
            'instances': 'test'})

        elb = mock.Mock()
        instance = 'i-un173s7'
        yield act._add(elb=elb, instances=[instance])

        elb.register_instances.assert_called_with([instance])

    @testing.gen_test
    def test_add_zones(self):
        act = elb_actor.RegisterInstance('UTA', {
            'elb': 'test',
            'region': 'us-east-1',
            'instances': 'test'})
        act.ec2_conn = mock.Mock()
        zone = mock.Mock()
        zone.name = 'unit-test-zone'
        act.ec2_conn.get_all_zones.return_value = [zone]

        elb = mock.Mock()
        elb.availability_zones = []

        yield act._check_elb_zones(elb=elb)

        elb.enable_zones.assert_called_with(set(['unit-test-zone']))

    @testing.gen_test
    def test_add_zones_noop(self):
        act = elb_actor.RegisterInstance('UTA', {
            'elb': 'test',
            'region': 'us-east-1',
            'instances': 'test'})
        act.ec2_conn = mock.Mock()
        zone = mock.Mock()
        zone.name = 'unit-test-zone'
        act.ec2_conn.get_all_zones.return_value = [zone]

        elb = mock.Mock()
        elb.availability_zones = ['unit-test-zone']

        yield act._check_elb_zones(elb=elb)

        self.assertEqual(elb.enable_zones.call_count, 0)

    @testing.gen_test
    def test_execute(self):
        act = elb_actor.RegisterInstance('UTA', {
            'elb': 'elb-test',
            'region': 'us-east-1',
            'instances': 'i-test'})

        act._find_elb = mock.Mock()
        act._find_elb.return_value = helper.tornado_value(mock.Mock())
        act._check_elb_zones = mock.Mock()
        act._check_elb_zones.return_value = helper.tornado_value(mock.Mock())
        act._add = mock.Mock()
        act._add.return_value = helper.tornado_value(mock.Mock())
        yield act._execute()

        act._find_elb.assert_called_with('elb-test')
        lb = yield act._find_elb()
        act._add.assert_called_with(elb=lb, instances=['i-test'])

    @testing.gen_test
    def test_execute_self(self):
        # No instance id specified
        act = elb_actor.RegisterInstance('UTA', {
            'elb': 'elb-test',
            'region': 'us-east-1'})

        act._find_elb = mock.Mock()
        act._find_elb.return_value = helper.tornado_value(mock.Mock())
        act._check_elb_zones = mock.Mock()
        act._check_elb_zones.return_value = helper.tornado_value(mock.Mock())
        act._add = mock.Mock()
        act._add.return_value = helper.tornado_value(mock.Mock())
        act._get_meta_data = helper.mock_tornado('i-test')
        yield act._execute()

        act._find_elb.assert_called_with('elb-test')
        lb = yield act._find_elb()
        act._add.assert_called_with(elb=lb, instances=['i-test'])


class TestDeregisterInstance(testing.AsyncTestCase):

    def setUp(self):
        super(TestDeregisterInstance, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        importlib.reload(elb_actor)

    @testing.gen_test
    def test_remove(self):
        act = elb_actor.DeregisterInstance('UTA', {
            'elb': 'test',
            'region': 'us-east-1',
            'instances': 'test'})

        elb = mock.Mock()
        instance = 'i-un173s7'

        act._wait_on_draining = mock.Mock()
        act._wait_on_draining.return_value = helper.tornado_value(mock.Mock())
        yield act._remove(elb=elb, instances=[instance])

        elb.deregister_instances.assert_called_with([instance])

    @testing.gen_test
    def test_wait_on_draining(self):
        act = elb_actor.DeregisterInstance('UTA', {
            'elb': 'test',
            'region': 'us-east-1',
            'isntances': 'test'})

        # Quick test with draining enabled
        fake_elb_attrs = mock.Mock(name='attrs')
        fake_elb_attrs.connection_draining.enabled = True
        fake_elb_attrs.connection_draining.timeout = 0.1
        elb = mock.Mock()
        elb.get_attributes.return_value = fake_elb_attrs
        yield act._wait_on_draining(elb)
        elb.get_attributes.assert_called_with()

        # Quick re-test with draining disabled
        act._options['wait_on_draining'] = False
        elb.reset_mock()
        yield act._wait_on_draining(elb)
        elb.get_attributes.assert_not_called()

        # Quick re-test with draining disabled
        act._options['wait_on_draining'] = True
        fake_elb_attrs.connection_draining.enabled = False
        elb.reset_mock()
        yield act._wait_on_draining(elb)
        elb.get_attributes.assert_called_with()

    @testing.gen_test
    def test_execute(self):
        act = elb_actor.DeregisterInstance('UTA', {
            'elb': 'elb-test',
            'region': 'us-east-1',
            'instances': 'i-test'})

        act._find_elb = mock.Mock()
        act._find_elb.return_value = helper.tornado_value(mock.Mock())
        act._remove = mock.Mock()
        act._remove.return_value = helper.tornado_value(mock.Mock())
        yield act._execute()

        act._find_elb.assert_called_with('elb-test')
        lb = yield act._find_elb()
        act._remove.assert_called_with(elb=lb, instances=['i-test'])

    @testing.gen_test
    def test_execute_wildcard(self):
        act = elb_actor.DeregisterInstance('UTA', {
            'elb': '*',
            'region': 'us-east-1',
            'instances': 'i-test'})

        act._find_instance_elbs = mock.Mock()
        act._find_instance_elbs.return_value = helper.tornado_value(
            [mock.Mock()])
        act._remove = mock.Mock()
        act._remove.return_value = helper.tornado_value(mock.Mock())

        yield act._execute()

        act._find_instance_elbs.assert_called_with(['i-test'])

    @testing.gen_test
    def test_find_instance_elbs(self):
        act = elb_actor.DeregisterInstance('UTA', {
            'elb': '*',
            'region': 'us-east-1',
            'instances': 'i-test'})

        fake_instance_1 = mock.Mock(name='i-1234567')
        fake_instance_1.id = 'i-1234567'
        fake_instance_2 = mock.Mock(name='i-test')
        fake_instance_2.id = 'i-test'

        fake_elb_1 = mock.Mock(name='elb_1')
        fake_elb_1.instances = [fake_instance_1]
        fake_elb_2 = mock.Mock(name='elb_2')
        fake_elb_2.instances = [fake_instance_1, fake_instance_2]
        fake_elbs = [fake_elb_1, fake_elb_2]

        act.elb_conn.get_all_load_balancers = mock.Mock()
        act.elb_conn.get_all_load_balancers.return_value = fake_elbs

        ret = yield act._find_instance_elbs(['i-test'])

        self.assertEqual(ret, [fake_elb_2])

    @testing.gen_test
    def test_execute_self(self):
        # No instance id specified
        act = elb_actor.DeregisterInstance('UTA', {
            'elb': 'elb-test',
            'region': 'us-east-1'})

        act._find_elb = mock.Mock()
        act._find_elb.return_value = helper.tornado_value(mock.Mock())
        act._remove = mock.Mock()
        act._remove.return_value = helper.tornado_value(mock.Mock())
        act._get_meta_data = helper.mock_tornado('i-test')
        yield act._execute()

        act._find_elb.assert_called_with('elb-test')
        lb = yield act._find_elb()
        act._remove.assert_called_with(elb=lb, instances=['i-test'])

    @testing.gen_test
    def test_execute_dry(self):
        act = elb_actor.DeregisterInstance('UTA', {
            'elb': 'elb-test',
            'region': 'us-east-1',
            'instances': 'i-test'},
            dry=True)

        act._find_elb = mock.Mock()
        act._find_elb.return_value = helper.tornado_value(mock.Mock())
        yield act._execute()


class TestWaitUntilHealthy(testing.AsyncTestCase):

    def setUp(self):
        super(TestWaitUntilHealthy, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        importlib.reload(elb_actor)

    @testing.gen_test
    def test_execute(self):

        actor = elb_actor.WaitUntilHealthy(
            'Unit Test Action', {'name': 'unit-test-queue',
                                 'region': 'us-west-2',
                                 'count': 3})

        actor._find_elb = mock.Mock(return_value=helper.tornado_value('ELB'))
        actor._is_healthy = mock.Mock(return_value=helper.tornado_value(True))

        val = yield actor._execute()
        self.assertEqual(actor._find_elb.call_count, 1)
        self.assertEqual(actor._is_healthy.call_count, 1)
        self.assertEqual(val, None)

    @testing.gen_test
    def test_execute_retry(self):

        actor = elb_actor.WaitUntilHealthy(
            'Unit Test Action', {'name': 'unit-test-queue',
                                 'region': 'us-west-2',
                                 'count': 3})

        actor._find_elb = mock.Mock(return_value=helper.tornado_value('ELB'))
        actor._is_healthy = mock.Mock(
            side_effect=[helper.tornado_value(False),
                         helper.tornado_value(True)])

        # Optional mock -- making the test quicker.
        short_sleep = utils.tornado_sleep(0)
        with mock.patch('kingpin.utils.tornado_sleep') as ts:
            ts.return_value = short_sleep
            val = yield actor._execute()

        self.assertEqual(actor._find_elb.call_count, 1)  # Don't refetch!
        self.assertEqual(actor._is_healthy.call_count, 2)  # Retry!
        self.assertEqual(val, None)

    @testing.gen_test
    def test_execute_dry(self):

        actor = elb_actor.WaitUntilHealthy(
            'Unit Test Action', {'name': 'unit-test-queue',
                                 'region': 'us-west-2',
                                 'count': 3},
            dry=True)

        actor._find_elb = mock.Mock(return_value=helper.tornado_value('ELB'))
        # NOTE: this is false, but assertion is True!
        actor._is_healthy = mock.Mock(return_value=helper.tornado_value(False))

        val = yield actor._execute()
        self.assertEqual(actor._find_elb.call_count, 1)
        self.assertEqual(actor._is_healthy.call_count, 1)
        self.assertEqual(val, None)

    @testing.gen_test
    def test_execute_fail(self):

        actor = elb_actor.WaitUntilHealthy(
            'Unit Test Action', {'name': 'unit-test-queue',
                                 'region': 'us-west-2',
                                 'count': 7})
        # ELB not found...
        actor.elb_conn.get_all_load_balancers = mock.Mock(
            side_effect=BotoServerError(400, 'LoadBalancerNotFound'))

        with self.assertRaises(elb_actor.base.ELBNotFound):
            yield actor.execute()

    def test_get_expected_count(self):
        actor = elb_actor.WaitUntilHealthy(
            'Unit Test Action', {'name': 'unit-test-queue',
                                 'region': 'us-west-2',
                                 'count': 3})

        self.assertEqual(actor._get_expected_count(5, 1), 5)
        self.assertEqual(actor._get_expected_count('50%', 20), 10)

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


class TestSetCert(testing.AsyncTestCase):

    def setUp(self):
        super(TestSetCert, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        importlib.reload(elb_actor)

    @testing.gen_test
    def test_check_access(self):
        elb = mock.Mock()
        botoerror = BotoServerError('Fail', 'Unit test')
        botoerror.error_code = 'AccessDenied'
        elb.set_listener_SSL_certificate = mock.Mock(
            side_effect=botoerror)

        actor = elb_actor.SetCert(
            'Unit Test', {'name': 'unit-test',
                          'region': 'us-east-1',
                          'cert_name': 'unit-cert'}
        )

        # AccessDenied means check has failed.
        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            yield actor._check_access(elb)

        # Anything else means the check has passed.
        botoerror.error_code = 'Cert Not Found'
        yield actor._check_access(elb)

    @testing.gen_test
    def test_get_cert_arn(self):
        cert = {
            'get_server_certificate_response': {
                'get_server_certificate_result': {
                    'server_certificate': {
                        'server_certificate_metadata': {
                            'arn': 'unit-test-arn-value'}}}}}

        actor = elb_actor.SetCert(
            'Unit Test', {'name': 'unit-test',
                          'region': 'us-east-1',
                          'cert_name': 'unit-cert'}
        )
        actor.iam_conn = mock.Mock()
        actor.iam_conn.get_server_certificate = mock.Mock(return_value=cert)

        arn = yield actor._get_cert_arn('test')

        self.assertEqual(actor.iam_conn.get_server_certificate.call_count, 1)
        self.assertEqual(arn, 'unit-test-arn-value')

        yield actor._get_cert_arn('test-new')
        # New name supplied, call count should be 2
        self.assertEqual(actor.iam_conn.get_server_certificate.call_count, 2)

    @testing.gen_test
    def test_get_cert_arn_fail(self):
        actor = elb_actor.SetCert(
            'Unit Test', {'name': 'unit-test',
                          'region': 'us-east-1',
                          'cert_name': 'unit-cert'}
        )

        actor.iam_conn = mock.Mock()
        error = BotoServerError(400, 'test')
        actor.iam_conn.get_server_certificate.side_effect = error

        with self.assertRaises(elb_actor.CertNotFound):
            yield actor._get_cert_arn('test')

    @testing.gen_test
    def test_use_cert(self):
        actor = elb_actor.SetCert(
            'Unit Test', {'name': 'unit-test',
                          'region': 'us-east-1',
                          'cert_name': 'unit-cert'}
        )
        elb = mock.Mock()

        yield actor._use_cert(elb=elb, arn='test')
        self.assertEqual(elb.set_listener_SSL_certificate.call_count, 1)

        error = BotoServerError(400, 'test')
        elb.set_listener_SSL_certificate.side_effect = error
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield actor._use_cert(elb=elb, arn='test')

    @testing.gen_test
    def test_execute(self):
        actor = elb_actor.SetCert(
            'Unit Test', {'name': 'unit-test',
                          'region': 'us-east-1',
                          'cert_name': 'unit-cert'}
        )
        elb = mock.Mock()
        elb.listeners = [
            (443, 443, 'HTTPS', 'HTTPS',
             'arn:aws:iam::12345:server-certificate/nextdoor.com')]
        actor._find_elb = helper.mock_tornado(elb)
        actor._get_cert_arn = helper.mock_tornado('arn')
        actor._check_access = helper.mock_tornado()
        actor._use_cert = helper.mock_tornado()

        yield actor._execute()

        self.assertEqual(actor._check_access._call_count, 0)
        self.assertEqual(actor._use_cert._call_count, 1)

        # Check quick exit if the cert is already in use
        actor._get_cert_arn = helper.mock_tornado(elb.listeners[0][4])
        yield actor._execute()

        # Function calls should remain unchanged
        self.assertEqual(actor._check_access._call_count, 0)
        self.assertEqual(actor._use_cert._call_count, 1)

    @testing.gen_test
    def test_execute_dry(self):
        actor = elb_actor.SetCert(
            'Unit Test', {'name': 'unit-test',
                          'region': 'us-east-1',
                          'cert_name': 'unit-cert'},
            dry=True)

        elb = mock.Mock()
        elb.listeners = [
            (443, 443, 'HTTPS', 'HTTPS',
             'arn:aws:iam::12345:server-certificate/nextdoor.com')]

        actor._find_elb = helper.mock_tornado(elb)
        actor._get_cert_arn = helper.mock_tornado('arn')
        actor._check_access = helper.mock_tornado()

        yield actor._execute()

        self.assertEqual(actor._check_access._call_count, 1)
