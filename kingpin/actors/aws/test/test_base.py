import logging

from boto.exception import NoAuthHandlerFound
from boto.exception import BotoServerError
from boto import utils
from tornado import testing
import botocore.exceptions
import mock

from kingpin.actors import exceptions
from kingpin.actors.aws import base
from kingpin.actors.aws import settings
import importlib

log = logging.getLogger(__name__)

# STATIC VALUES FOR TESTS
TARGET_GROUP_RESPONSE = {
    'ResponseMetadata': {
        'HTTPHeaders': {
            'content-length': '1228',
            'content-type': 'text/xml',
            'date': 'Tue, 13 Feb 2018 17:50:56 GMT',
            'x-amzn-requestid': '123-123-123-123-123'
        },
        'HTTPStatusCode': 200,
        'RequestId': '123-123-123-123-123',
        'RetryAttempts': 0
    },
    'TargetGroups': [{
        'HealthCheckIntervalSeconds': 30,
        'HealthCheckPath': '/',
        'HealthCheckPort': 'traffic-port',
        'HealthCheckProtocol': 'HTTP',
        'HealthCheckTimeoutSeconds': 5,
        'HealthyThresholdCount': 5,
        'LoadBalancerArns': [],
        'Matcher': {'HttpCode': '200'},
        'Port': 80,
        'Protocol': 'HTTP',
        'TargetGroupArn':
            'arn:aws:elb:us-east-1:123:targetgroup/unittest/123',
        'TargetGroupName': 'kingpin-integration-test',
        'UnhealthyThresholdCount': 2,
        'VpcId': 'vpc-123'
    }]
}


class TestBase(testing.AsyncTestCase):

    def setUp(self):
        super(TestBase, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        importlib.reload(base)

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
        self.assertEqual(actor.ec2_conn.region.name, 'us-west-1')

    @testing.gen_test
    def test_api_call_400(self):
        actor = base.AWSBaseActor('Unit Test Action', {})
        actor.elb_conn = mock.Mock()
        actor.elb_conn.get_all_load_balancers = mock.MagicMock()
        exc = BotoServerError(400, 'Bad Request')
        actor.elb_conn.get_all_load_balancers.side_effect = exc

        with self.assertRaises(exceptions.InvalidCredentials):
            yield actor._find_elb('')

    @testing.gen_test
    def test_api_call_403(self):
        actor = base.AWSBaseActor('Unit Test Action', {})
        actor.elb_conn = mock.Mock()
        actor.elb_conn.get_all_load_balancers = mock.MagicMock()
        exc = BotoServerError(403, 'The security token')
        actor.elb_conn.get_all_load_balancers.side_effect = exc

        with self.assertRaises(exceptions.InvalidCredentials):
            yield actor._find_elb('')

    @testing.gen_test
    def test_api_call_queue_400(self):
        actor = base.AWSBaseActor('Unit Test Action', {})
        actor.elb_conn = mock.Mock()
        actor.elb_conn.get_all_load_balancers = mock.MagicMock()
        exc = BotoServerError(400, 'Bad Request')
        actor.elb_conn.get_all_load_balancers.side_effect = exc

        with self.assertRaises(exceptions.InvalidCredentials):
            yield actor.api_call_with_queueing(
                actor.elb_conn.get_all_load_balancers,
                queue_name='get_all_load_balancers')

    @testing.gen_test
    def test_api_call_queue_403(self):
        actor = base.AWSBaseActor('Unit Test Action', {})
        actor.elb_conn = mock.Mock()
        actor.elb_conn.get_all_load_balancers = mock.MagicMock()
        exc = BotoServerError(403, 'The security token')
        actor.elb_conn.get_all_load_balancers.side_effect = exc

        with self.assertRaises(exceptions.InvalidCredentials):
            yield actor.api_call_with_queueing(
                actor.elb_conn.get_all_load_balancers,
                queue_name='get_all_load_balancers')

    @testing.gen_test
    def test_find_elb(self):
        actor = base.AWSBaseActor('Unit Test Action', {})
        actor.elb_conn = mock.Mock()
        actor.elb_conn.get_all_load_balancers.return_value = ['test']

        elb = yield actor._find_elb('')

        self.assertEqual(elb, 'test')
        self.assertEqual(actor.elb_conn.get_all_load_balancers.call_count, 1)

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
    def test_find_target_group(self):
        actor = base.AWSBaseActor('Unit Test Action', {})
        c_mock = mock.Mock()
        c_mock.describe_target_groups.return_value = TARGET_GROUP_RESPONSE
        actor.elbv2_conn = c_mock

        target = yield actor._find_target_group('123')
        self.assertEqual(
            target,
            'arn:aws:elb:us-east-1:123:targetgroup/unittest/123')
        c_mock.describe_target_groups.assert_called_with(
            Names=['123'])

    @testing.gen_test
    def test_find_target_group_too_many_results(self):
        actor = base.AWSBaseActor('Unit Test Action', {})
        c_mock = mock.Mock()
        resp = TARGET_GROUP_RESPONSE.copy()
        resp['TargetGroups'] = [
            TARGET_GROUP_RESPONSE['TargetGroups'][0],
            TARGET_GROUP_RESPONSE['TargetGroups'][0],
            TARGET_GROUP_RESPONSE['TargetGroups'][0],
        ]
        c_mock.describe_target_groups.return_value = resp
        actor.elbv2_conn = c_mock

        with self.assertRaises(base.ELBNotFound):
            yield actor._find_target_group('123')

    @testing.gen_test
    def test_find_target_group_exception_error(self):
        actor = base.AWSBaseActor('Unit Test Action', {})
        c_mock = mock.Mock()
        exc = botocore.exceptions.ClientError({'Error': {'Code': ''}}, 'Test')
        c_mock.describe_target_groups.side_effect = exc
        actor.elbv2_conn = c_mock

        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            yield actor._find_target_group('123')

    @testing.gen_test
    def test_get_meta_data(self):
        actor = base.AWSBaseActor('Unit Test Action', {})

        with mock.patch.object(utils, 'get_instance_metadata') as md:
            md.return_value = {'ut-key': 'ut-value'}
            meta = yield actor._get_meta_data('ut-key')

        self.assertEqual(meta, 'ut-value')

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
            'Version': '2012-10-17',
            'Statement': [
                {'Action': [
                    's3:Create*',
                    's3:Get*',
                    's3:Put*',
                    's3:List*'],
                 'Resource': [
                    'arn:aws:s3:::kingpin*/*',
                    'arn:aws:s3:::kingpin*'],
                 'Effect': 'Allow'}]}

        actor = base.AWSBaseActor('Unit Test Action', {})
        ret = actor._policy_doc_to_dict(policy_str)
        self.assertEqual(ret, policy_dict)

    @testing.gen_test
    def test_parse_policy_json(self):
        actor = base.AWSBaseActor('Unit Test Action', {})

        # Should work fine by default with good data
        ret = actor._parse_policy_json('examples/aws.iam.user/s3_example.json')
        self.assertEqual(ret['Version'], '2012-10-17')

        # If the file doesn't exist, raise an exception
        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            actor._parse_policy_json('junk')

    @testing.gen_test
    def test_parse_policy_json_none(self):
        actor = base.AWSBaseActor('Unit Test Action', {})
        ret = actor._parse_policy_json(None)
        self.assertEqual(ret, None)
