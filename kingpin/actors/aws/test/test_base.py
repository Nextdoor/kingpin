import logging

from boto import utils
from boto.exception import BotoServerError
from tornado import testing
import mock

from kingpin.actors.aws import base
from kingpin.actors.aws import settings

log = logging.getLogger(__name__)


class TestBase(testing.AsyncTestCase):

    def setUp(self):
        super(TestBase, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'

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

        # Now pretend the request failed
        actor.elb_conn.get_all_load_balancers = mock.Mock(
            side_effect=BotoServerError(400, 'LoadBalancerNotFound'))
        with self.assertRaises(base.ELBNotFound):
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
