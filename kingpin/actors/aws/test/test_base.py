import logging
import mock

import six.moves

from boto.exception import NoAuthHandlerFound
from boto.exception import BotoServerError
from boto import utils
from tornado import testing

from kingpin.actors import exceptions
from kingpin.actors.aws import base
from kingpin.actors.aws import settings

log = logging.getLogger(__name__)


class TestBase(testing.AsyncTestCase):

    def setUp(self):
        super(TestBase, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        six.moves.reload_module(base)

    @mock.patch('boto.iam.connection.IAMConnection')
    def test_missing_auth(self, mock_iam):
        mock_iam.side_effect = NoAuthHandlerFound('bad')
        with self.assertRaises(exceptions.InvalidCredentials):
            base.AWSBaseActor('Unit Test Action', {'region': 'fail'})

    def test_region_check(self):
        with self.assertRaises(exceptions.InvalidOptions):
            base.AWSBaseActor('Unit Test Action', {'region': 'fail'})

    def test_zone_check(self):
        actor = base.AWSBaseActor('Unit Test Action',
                                  {'region': 'us-west-1d'})
        self.assertEquals(actor.ec2_conn.region.name, 'us-west-1')

    @testing.gen_test
    def test_thread_400(self):
        actor = base.AWSBaseActor('Unit Test Action', {})
        actor.elb_conn = mock.Mock()
        actor.elb_conn.get_all_load_balancers = mock.MagicMock()
        exc = BotoServerError(400, 'Bad Request')
        actor.elb_conn.get_all_load_balancers.side_effect = exc

        with self.assertRaises(exceptions.InvalidCredentials):
            yield actor._find_elb('')

    @testing.gen_test
    def test_thread_403(self):
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

    @testing.gen_test
    def test_policy_doc_to_dict(self):
        policy_str = ''.join([
            '%7B%22Version%22%3A%20%222012-10-17%22%2C%20',
            '%22Statement%22%3A%20%5B%7B%22Action%22%3A%20%5B',
            '%22s3%3ACreate%2A%22%2C%20%22s3%3AGet%2A%22%2C%20',
            '%22s3%3APut%2A%22%2C%20%22s3%3AList%2A%22%5D%2C%20',
            '%22Resource%22%3A%20%5B',
            '%22arn%3Aaws%3As3%3A%3A%3Akingpin%2A%2F%2A%22%2C%20',
            '%22arn%3Aaws%3As3%3A%3A%3Akingpin%2A%22%5D%2C%20',
            '%22Effect%22%3A%20%22Allow%22%7D%5D%7D'])
        policy_dict = {
            u'Version': u'2012-10-17',
            u'Statement': [
                {u'Action': [
                    u's3:Create*',
                    u's3:Get*',
                    u's3:Put*',
                    u's3:List*'],
                 u'Resource': [
                    u'arn:aws:s3:::kingpin*/*',
                    u'arn:aws:s3:::kingpin*'],
                 u'Effect': u'Allow'}]}

        actor = base.AWSBaseActor('Unit Test Action', {})
        ret = actor._policy_doc_to_dict(policy_str)
        self.assertEqual(ret, policy_dict)

    @testing.gen_test
    def test_parse_policy_json(self):
        actor = base.AWSBaseActor('Unit Test Action', {})

        # Should work fine by default with good data
        ret = actor._parse_policy_json('examples/aws.iam.user/s3_example.json')
        self.assertEquals(ret['Version'], '2012-10-17')

        # If the file doesn't exist, raise an exception
        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            actor._parse_policy_json('junk')

    @testing.gen_test
    def test_parse_policy_json_none(self):
        actor = base.AWSBaseActor('Unit Test Action', {})
        ret = actor._parse_policy_json(None)
        self.assertEquals(ret, None)
