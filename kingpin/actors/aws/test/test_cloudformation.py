import datetime
import logging

from botocore.exceptions import ClientError
from tornado import testing
import mock

from kingpin.actors.aws import settings
from kingpin.actors.aws import cloudformation
from kingpin.actors.test.helper import tornado_value

log = logging.getLogger(__name__)


def create_fake_stack(name, status):
    fake_stack = {
        'StackId': 'arn:aws:cloudformation:us-east-1:xxxx:stack/%s/xyz' % name,
        'LastUpdatedTime': datetime.datetime.now(),
        'TemplateDescription': 'Fake Template %s' % name,
        'CreationTime': datetime.datetime.now(),
        'StackName': name,
        'StackStatus': status
    }
    return fake_stack


class TestCloudFormationBaseActor(testing.AsyncTestCase):

    def setUp(self):
        super(TestCloudFormationBaseActor, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        reload(cloudformation)

    def test_create_parameters(self):
        params = {
            'Key1': 'Value1',
            'Key2': 'Value2',
        }

        expected = [
            {'ParameterKey': 'Key1',
             'ParameterValue': 'Value1',
             'UsePreviousValue': False},
            {'ParameterKey': 'Key2',
             'ParameterValue': 'Value2',
             'UsePreviousValue': False},
        ]

        actor = cloudformation.CloudFormationBaseActor(
            'unittest', {'region': 'us-east-1'})

        ret = actor._create_parameters(params)
        self.assertEquals(ret, expected)

    @testing.gen_test
    def test_get_stacks(self):
        actor = cloudformation.CloudFormationBaseActor(
            'unittest', {'region': 'us-east-1'})
        actor.cf3_conn.list_stacks = mock.MagicMock()
        actor.cf3_conn.list_stacks.return_value = {
            'StackSummaries': [
                create_fake_stack('s1', 'UPDATE_COMPLETE'),
                create_fake_stack('s2', 'UPDATE_COMPLETE'),
                create_fake_stack('s3', 'UPDATE_COMPLETE')
            ]
        }
        ret = yield actor._get_stacks()
        self.assertEquals(
            ['s1', 's2', 's3'],
            [ret[0]['StackName'],
             ret[1]['StackName'],
             ret[2]['StackName']])

    @testing.gen_test
    def test_get_stack(self):
        actor = cloudformation.CloudFormationBaseActor(
            'unittest', {'region': 'us-east-1'})
        actor.cf3_conn.list_stacks = mock.MagicMock()
        actor.cf3_conn.list_stacks.return_value = {
            'StackSummaries': [
                create_fake_stack('s1', 'UPDATE_COMPLETE'),
                create_fake_stack('s2', 'UPDATE_COMPLETE'),
                create_fake_stack('s3', 'UPDATE_COMPLETE')
            ]
        }

        ret = yield actor._get_stack('s1')
        self.assertEquals(ret['StackName'], 's1')

        ret = yield actor._get_stack('s5')
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_wait_until_state(self):

        create_in_progress = create_fake_stack('test', 'CREATE_IN_PROGRESS')
        create_complete = create_fake_stack('test', 'CREATE_COMPLETE')

        actor = cloudformation.CloudFormationBaseActor(
            'unittest', {'region': 'us-east-1'})
        actor._get_stack = mock.MagicMock()

        # Make _get_stack() yield back 2 in-progress states, then yield a
        # successfull execution.
        actor._get_stack.side_effect = [
            tornado_value(create_in_progress),
            tornado_value(create_in_progress),
            tornado_value(create_complete)
        ]
        ret = yield actor._wait_until_state(cloudformation.COMPLETE, sleep=0.1)
        self.assertEquals(ret, None)

        # Make sure a cloudformationerror is raised if we ask for a deleted
        # state rather than a created one.
        actor._get_stack.side_effect = [
            tornado_value(create_in_progress),
            tornado_value(create_in_progress),
            tornado_value(create_complete)
        ]
        with self.assertRaises(cloudformation.CloudFormationError):
            yield actor._wait_until_state(cloudformation.DELETED, sleep=0.1)

        # Lastly, test that if wait_until_state returns no actor, we bail
        # appropriately.
        actor._get_stack.side_effect = [tornado_value(None)]
        with self.assertRaises(cloudformation.StackNotFound):
            yield actor._wait_until_state(cloudformation.COMPLETE, sleep=0.1)


class TestCreate(testing.AsyncTestCase):

    def setUp(self):
        super(TestCreate, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        reload(cloudformation)

    def test_get_template_body(self):
        # Should work...
        actor = cloudformation.Create(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2',
             'template': 'examples/test/aws.cloudformation/cf.unittest.json'})
        self.assertNotEquals(actor._template_body, '#BLANK\r\n')
        self.assertEquals(actor._template_url, None)

        # Should return None
        actor = cloudformation.Create(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2',
             'template': 'http://foobar.json'})
        self.assertEquals(actor._template_body, None)
        self.assertEquals(actor._template_url, 'http://foobar.json')

        # Should raise exception
        with self.assertRaises(cloudformation.InvalidTemplate):
            actor = cloudformation.Create(
                'Unit Test Action',
                {'name': 'unit-test-cf',
                 'region': 'us-west-2',
                 'template': 'missing'})

    @testing.gen_test
    def test_validate_template_body(self):
        actor = cloudformation.Create(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2',
             'template': 'examples/test/aws.cloudformation/cf.unittest.json'})
        actor.cf3_conn.validate_template = mock.MagicMock()
        yield actor._validate_template()
        actor.cf3_conn.validate_template.assert_called_with(
            TemplateBody='{"blank": "json"}')

    @testing.gen_test
    def test_validate_template_url(self):
        actor = cloudformation.Create(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2',
             'template': 'http://foobar.json'})
        actor.cf3_conn.validate_template = mock.MagicMock()
        yield actor._validate_template()
        actor.cf3_conn.validate_template.assert_called_with(
            TemplateURL='http://foobar.json')

    @testing.gen_test
    def test_validate_template_raises_boto_error(self):
        actor = cloudformation.Create(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2',
             'template': 'http://foobar.json'})

        fake_exc = {
            'ResponseMetadata': {
                'HTTPStatusCode': 400,
                'RequestId': 'dfc1a12c-22c1-11e6-80b1-8fd4cf167f54'
            },
            'Error': {
                'Message': 'Template format error: JSON not well-formed',
                'Code': 'ValidationError',
                'Type': 'Sender'
            }
        }

        actor.cf3_conn.validate_template = mock.MagicMock()
        actor.cf3_conn.validate_template.side_effect = ClientError(
            fake_exc, 'FakeOperation')
        with self.assertRaises(cloudformation.InvalidTemplate):
            yield actor._validate_template()

    @testing.gen_test
    def test_create_stack_file(self):
        actor = cloudformation.Create(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2',
             'template':
                 'examples/test/aws.cloudformation/cf.integration.json'})
        actor.cf3_conn.create_stack = mock.MagicMock(name='create_stack_mock')
        actor.cf3_conn.create_stack.return_value = {'StackId': 'arn:123'}
        ret = yield actor._create_stack()
        self.assertEquals(ret, 'arn:123')

    @testing.gen_test
    def test_create_stack_url(self):
        actor = cloudformation.Create(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2',
             'template': 'https://www.test.com'})
        actor.cf3_conn.create_stack = mock.MagicMock(name='create_stack_mock')
        actor.cf3_conn.create_stack.return_value = {'StackId': 'arn:123'}
        ret = yield actor._create_stack()
        self.assertEquals(ret, 'arn:123')

    @testing.gen_test
    def test_create_stack_raises_boto_error(self):
        actor = cloudformation.Create(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2',
             'template':
                 'examples/test/aws.cloudformation/cf.integration.json'})
        actor.cf3_conn.create_stack = mock.MagicMock()

        fake_exc = {
            'ResponseMetadata': {
                'HTTPStatusCode': 400,
                'RequestId': 'dfc1a12c-22c1-11e6-80b1-8fd4cf167f54'
            },
            'Error': {
                'Message': 'Something failed',
                'Code': 'ExecutionFailure',
                'Type': 'Sender'
            }
        }

        actor.cf3_conn.create_stack.side_effect = ClientError(
            fake_exc, 'Failure')
        with self.assertRaises(cloudformation.CloudFormationError):
            yield actor._create_stack()

    @testing.gen_test
    def test_execute(self):
        actor = cloudformation.Create(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2',
             'template':
                 'examples/test/aws.cloudformation/cf.integration.json'})

        actor._validate_template = mock.MagicMock()
        actor._validate_template.side_effect = [tornado_value(True)]

        actor._get_stack = mock.MagicMock()
        actor._get_stack.side_effect = [tornado_value(None)]

        actor._create_stack = mock.MagicMock()
        actor._create_stack.side_effect = [tornado_value(None)]

        actor._wait_until_state = mock.MagicMock()
        actor._wait_until_state.side_effect = [tornado_value(None)]
        yield actor._execute()

    @testing.gen_test
    def test_execute_exists(self):
        actor = cloudformation.Create(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2',
             'template':
                 'examples/test/aws.cloudformation/cf.integration.json'})

        actor._validate_template = mock.MagicMock()
        actor._validate_template.side_effect = [tornado_value(True)]

        actor._get_stack = mock.MagicMock()
        actor._get_stack.side_effect = [tornado_value(True)]

        with self.assertRaises(cloudformation.StackAlreadyExists):
            yield actor._execute()

    @testing.gen_test
    def test_execute_dry(self):
        actor = cloudformation.Create(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2',
             'template':
                 'examples/test/aws.cloudformation/cf.integration.json'},
            dry=True)

        actor._validate_template = mock.MagicMock()
        actor._validate_template.side_effect = [tornado_value(True)]

        actor._get_stack = mock.MagicMock()
        actor._get_stack.side_effect = [tornado_value(None)]

        yield actor._execute()


class TestDelete(testing.AsyncTestCase):

    def setUp(self):
        super(TestDelete, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        reload(cloudformation)

    @testing.gen_test
    def test_delete_stack(self):
        actor = cloudformation.Delete(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2'})
        actor.cf3_conn.delete_stack = mock.MagicMock(name='delete_stack_mock')
        actor.cf3_conn.delete_stack.return_value = {
            'ResponseMetadata': {'RequestId': 'req-id-1'}
        }
        ret = yield actor._delete_stack()
        self.assertEquals(ret, 'req-id-1')

    @testing.gen_test
    def test_delete_stack_raises_boto_error(self):
        actor = cloudformation.Delete(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2'})
        actor.cf3_conn.delete_stack = mock.MagicMock()

        fake_exc = {
            'ResponseMetadata': {
                'HTTPStatusCode': 400,
                'RequestId': 'dfc1a12c-22c1-11e6-80b1-8fd4cf167f54'
            },
            'Error': {
                'Message': 'Something failed',
                'Code': 'ExecutionFailure',
                'Type': 'Sender'
            }
        }

        actor.cf3_conn.delete_stack.side_effect = ClientError(
            fake_exc, 'Error')
        with self.assertRaises(cloudformation.CloudFormationError):
            yield actor._delete_stack()

    @testing.gen_test
    def test_execute(self):
        actor = cloudformation.Delete(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2'})
        actor._get_stack = mock.MagicMock()
        actor._get_stack.side_effect = [tornado_value(True)]
        actor._delete_stack = mock.MagicMock()
        actor._delete_stack.side_effect = [tornado_value(None)]
        actor._wait_until_state = mock.MagicMock()
        actor._wait_until_state.side_effect = cloudformation.StackNotFound()
        yield actor._execute()

    @testing.gen_test
    def test_execute_dry(self):
        actor = cloudformation.Delete(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2'}, dry=True)
        actor._get_stack = mock.MagicMock()
        actor._get_stack.side_effect = [tornado_value(True)]
        yield actor._execute()

    @testing.gen_test
    def test_execute_not_exists(self):
        actor = cloudformation.Delete(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2'})
        actor._get_stack = mock.MagicMock()
        actor._get_stack.side_effect = [tornado_value(None)]
        with self.assertRaises(cloudformation.StackNotFound):
            yield actor._execute()
