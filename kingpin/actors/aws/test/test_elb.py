import logging

from boto.exception import BotoServerError
from tornado import testing
import mock

from kingpin import utils
from kingpin.actors import exceptions
from kingpin.actors.aws import elb as elb_actor
from kingpin.actors.aws import settings
from kingpin.actors.test import helper

log = logging.getLogger(__name__)


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
            'instances': 'test'})

        elb = mock.Mock()
        instance = 'i-un173s7'
        yield act._add(elb, [instance])

        elb.register_instances.assert_called_with([instance])

    @testing.gen_test
    def test_execute(self):
        act = elb_actor.RegisterInstance('UTA', {
            'elb': 'elb-test',
            'region': 'region-test',
            'instances': 'i-test'})

        act._find_elb = mock.Mock()
        act._find_elb.return_value = helper.tornado_value(mock.Mock())
        act._add = mock.Mock()
        act._add.return_value = helper.tornado_value(mock.Mock())
        yield act._execute()

        act._find_elb.assert_called_with('elb-test')
        lb = yield act._find_elb()
        act._add.assert_called_with(lb, ['i-test'])

    @testing.gen_test
    def test_execute_self(self):
        # No instance id specified
        act = elb_actor.RegisterInstance('UTA', {
            'elb': 'elb-test',
            'region': 'region-test'})

        act._find_elb = mock.Mock()
        act._find_elb.return_value = helper.tornado_value(mock.Mock())
        act._add = mock.Mock()
        act._add.return_value = helper.tornado_value(mock.Mock())
        act._get_meta_data = helper.mock_tornado('i-test')
        yield act._execute()

        act._find_elb.assert_called_with('elb-test')
        lb = yield act._find_elb()
        act._add.assert_called_with(lb, ['i-test'])

    @testing.gen_test
    def test_execute_dry(self):
        act = elb_actor.RegisterInstance('UTA', {
            'elb': 'elb-test',
            'region': 'region-test',
            'instances': 'i-test'},
            dry=True)

        act._find_elb = mock.Mock()
        act._find_elb.return_value = helper.tornado_value(mock.Mock())
        act._add = mock.Mock()
        act._add.return_value = helper.tornado_value(mock.Mock())
        yield act._execute()

        act._find_elb.assert_called_with('elb-test')
        yield act._find_elb()
        self.assertEquals(0, act._add.call_count)


class TestDeregisterInstance(testing.AsyncTestCase):

    def setUp(self):
        super(TestDeregisterInstance, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'

    @testing.gen_test
    def test_remove(self):
        act = elb_actor.DeregisterInstance('UTA', {
            'elb': 'test',
            'region': 'test',
            'instances': 'test'})

        elb = mock.Mock()
        instance = 'i-un173s7'
        yield act._remove(elb, [instance])

        elb.deregister_instances.assert_called_with([instance])

    @testing.gen_test
    def test_execute(self):
        act = elb_actor.DeregisterInstance('UTA', {
            'elb': 'elb-test',
            'region': 'region-test',
            'instances': 'i-test'})

        act._find_elb = mock.Mock()
        act._find_elb.return_value = helper.tornado_value(mock.Mock())
        act._remove = mock.Mock()
        act._remove.return_value = helper.tornado_value(mock.Mock())
        yield act._execute()

        act._find_elb.assert_called_with('elb-test')
        lb = yield act._find_elb()
        act._remove.assert_called_with(lb, ['i-test'])

    @testing.gen_test
    def test_execute_self(self):
        # No instance id specified
        act = elb_actor.DeregisterInstance('UTA', {
            'elb': 'elb-test',
            'region': 'region-test'})

        act._find_elb = mock.Mock()
        act._find_elb.return_value = helper.tornado_value(mock.Mock())
        act._remove = mock.Mock()
        act._remove.return_value = helper.tornado_value(mock.Mock())
        act._get_meta_data = helper.mock_tornado('i-test')
        yield act._execute()

        act._find_elb.assert_called_with('elb-test')
        lb = yield act._find_elb()
        act._remove.assert_called_with(lb, ['i-test'])

    @testing.gen_test
    def test_execute_dry(self):
        act = elb_actor.DeregisterInstance('UTA', {
            'elb': 'elb-test',
            'region': 'region-test',
            'instances': 'i-test'},
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

        actor._find_elb = mock.Mock(return_value=helper.tornado_value('ELB'))
        actor._is_healthy = mock.Mock(return_value=helper.tornado_value(True))

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

        actor._find_elb = mock.Mock(return_value=helper.tornado_value('ELB'))
        actor._is_healthy = mock.Mock(
            side_effect=[helper.tornado_value(False),
                         helper.tornado_value(True)])

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

        actor._find_elb = mock.Mock(return_value=helper.tornado_value('ELB'))
        # NOTE: this is false, but assertion is True!
        actor._is_healthy = mock.Mock(return_value=helper.tornado_value(False))

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
            side_effect=BotoServerError(400, 'LoadBalancerNotFound'))

        with self.assertRaises(elb_actor.base.ELBNotFound):
            yield actor.execute()

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


class TestSetCert(testing.AsyncTestCase):

    def setUp(self):
        super(TestSetCert, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'

    @testing.gen_test
    def test_check_access(self):
        elb = mock.Mock()
        botoerror = BotoServerError('Fail', 'Unit test')
        botoerror.error_code = 'AccessDenied'
        elb.set_listener_SSL_certificate = mock.Mock(
            side_effect=botoerror)

        actor = elb_actor.SetCert(
            'Unit Test', {'name': 'unit-test',
                          'region': 'unit-region',
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
                          'region': 'unit-region',
                          'cert_name': 'unit-cert'}
            )
        actor.iam_conn = mock.Mock()
        actor.iam_conn.get_server_certificate = mock.Mock(return_value=cert)

        arn = yield actor._get_cert_arn('test')

        self.assertEquals(actor.iam_conn.get_server_certificate.call_count, 1)
        self.assertEquals(arn, 'unit-test-arn-value')

        yield actor._get_cert_arn('test-new')
        # New name supplied, call count should be 2
        self.assertEquals(actor.iam_conn.get_server_certificate.call_count, 2)

    @testing.gen_test
    def test_get_cert_arn_fail(self):
        actor = elb_actor.SetCert(
            'Unit Test', {'name': 'unit-test',
                          'region': 'unit-region',
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
                          'region': 'unit-region',
                          'cert_name': 'unit-cert'}
            )
        elb = mock.Mock()

        yield actor._use_cert(elb, 'test')
        self.assertEquals(elb.set_listener_SSL_certificate.call_count, 1)

        error = BotoServerError(400, 'test')
        elb.set_listener_SSL_certificate.side_effect = error
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield actor._use_cert(elb, 'test')

    @testing.gen_test
    def test_execute(self):
        actor = elb_actor.SetCert(
            'Unit Test', {'name': 'unit-test',
                          'region': 'unit-region',
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

        self.assertEquals(actor._check_access._call_count, 0)
        self.assertEquals(actor._use_cert._call_count, 1)

        # Check quick exit if the cert is already in use
        actor._get_cert_arn = helper.mock_tornado(elb.listeners[0][4])
        yield actor._execute()

        # Function calls should remain unchanged
        self.assertEquals(actor._check_access._call_count, 0)
        self.assertEquals(actor._use_cert._call_count, 1)

    @testing.gen_test
    def test_execute_dry(self):
        actor = elb_actor.SetCert(
            'Unit Test', {'name': 'unit-test',
                          'region': 'unit-region',
                          'cert_name': 'unit-cert'},
            dry=True)

        elb = mock.Mock()
        elb.listeners = [
            (443, 443, 'HTTPS', 'HTTPS',
             'arn:aws:iam::12345:server-certificate/nextdoor.com')]

        actor._find_elb = helper.mock_tornado(elb)
        actor._get_cert_arn = helper.mock_tornado('arn')
        actor._check_access = helper.mock_tornado()
        actor._use_cert = helper.mock_tornado()

        yield actor._execute()

        self.assertEquals(actor._check_access._call_count, 1)
        self.assertEquals(actor._use_cert._call_count, 0)
