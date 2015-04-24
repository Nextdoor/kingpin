import logging

from boto.exception import BotoServerError
from boto import utils
from tornado import testing
import mock

from kingpin.actors.aws import settings
from kingpin.actors import exceptions
from kingpin.actors.aws import base

log = logging.getLogger(__name__)


class TestBase(testing.AsyncTestCase):

    def setUp(self):
        super(TestBase, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        reload(base)

    def test_region_check(self):
        with self.assertRaises(exceptions.InvalidOptions):
            base.AWSBaseActor('Unit Test Action', {'region': 'fail'})

    def test_zone_check(self):
        actor = base.AWSBaseActor('Unit Test Action',
                                  {'region': 'us-west-1d'})
        self.assertEquals(actor.ec2_conn.region.name, 'us-west-1')

    @testing.gen_test
    def test_thread_exception(self):
        actor = base.AWSBaseActor('Unit Test Action', {})
        actor.elb_conn = mock.Mock()
        actor.elb_conn.get_all_load_balancers = mock.MagicMock()
        exc = BotoServerError(403, 'The security token')
        actor.elb_conn.get_all_load_balancers.side_effect = exc

        with self.assertRaises(exceptions.InvalidCredentials):
            yield actor._find_elb('')

    @testing.gen_test
    def test_find_elb(self):
        actor = base.AWSBaseActor('Unit Test Action', {})
        actor.elb_conn = mock.Mock()
        actor.elb_conn.get_all_load_balancers.return_value = ['test']

        elb = yield actor._find_elb('')

        self.assertEquals(elb, 'test')
        self.assertEquals(actor.elb_conn.get_all_load_balancers.call_count, 1)

        actor.elb_conn.get_all_load_balancers.assert_called_with(
            load_balancer_names='')

    @testing.gen_test
    def test_find_elb_error(self):
        actor = base.AWSBaseActor('Unit Test Action', {})

        # Pretend the request worked, but there are no ELBs
        actor.elb_conn = mock.Mock()
        actor.elb_conn.get_all_load_balancers = mock.Mock(return_value=[])
        with self.assertRaises(base.ELBNotFound):
            yield actor._find_elb('')

    @testing.gen_test
    def test_find_elb_exception_error(self):
        actor = base.AWSBaseActor('Unit Test Action', {})

        # Pretend the request worked, but there are no ELBs
        actor.elb_conn = mock.Mock()
        actor.elb_conn.get_all_load_balancers = mock.MagicMock()
        actor.elb_conn.get_all_load_balancers.side_effect = BotoServerError(
            400, 'LoadBalancerNotFound')
        with self.assertRaises(base.ELBNotFound):
            yield actor._find_elb('')

        # Pretend the request worked, but there are no ELBs
        actor.elb_conn.get_all_load_balancers.side_effect = BotoServerError(
            401, 'SomeOtherError')
        with self.assertRaises(BotoServerError):
            yield actor._find_elb('')

    @testing.gen_test
    def test_get_meta_data(self):
        actor = base.AWSBaseActor('Unit Test Action', {})

        with mock.patch.object(utils, 'get_instance_metadata') as md:
            md.return_value = {'ut-key': 'ut-value'}
            meta = yield actor._get_meta_data('ut-key')

        self.assertEquals(meta, 'ut-value')

    @testing.gen_test
    def test_get_meta_data_error(self):
        actor = base.AWSBaseActor('Unit Test Action', {})

        with mock.patch.object(utils, 'get_instance_metadata') as md:
            md.return_value = {}
            with self.assertRaises(base.InvalidMetaData):
                yield actor._get_meta_data('ut-key')

        with mock.patch.object(utils, 'get_instance_metadata') as md:
            md.return_value = {'key': 'value'}
            with self.assertRaises(base.InvalidMetaData):
                yield actor._get_meta_data('ut-key')
