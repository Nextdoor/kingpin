import logging

from botocore import stub
from tornado import testing
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
        importlib.reload(base)

    def test_region_check(self):
        with self.assertRaises(exceptions.InvalidOptions):
            base.AWSBaseActor('Unit Test Action', {'region': 'fail'})

    def test_zone_check(self):
        actor = base.AWSBaseActor('Unit Test Action',
                                  {'region': 'us-west-1d'})
        self.assertEqual(actor.region, 'us-west-1')

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
