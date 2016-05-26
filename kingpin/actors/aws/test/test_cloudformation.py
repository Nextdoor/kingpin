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


def create_fake_stack_event(name, resource, status, reason=None):
    fake_event = {
        'EventId': '264322b0-2426-11e6-aaa1-500c28b32ed2',
        'LogicalResourceId': resource,
        'PhysicalResourceId': 'arn:aws:cf:us-east-1:x:stack/%s/abc' % name,
        'ResourceStatus': status,
        'ResourceType': 'AWS::CloudFormation::Stack',
        'StackId': 'arn:aws:cf:us-east-1:xxx:stack/%s/xyz' % name,
        'StackName': name,
        'Timestamp': datetime.datetime.now(),
    }

    if reason:
        fake_event['ResourceStatusReason'] = reason

    return fake_event


class TestCloudFormationBaseActor(testing.AsyncTestCase):

    def setUp(self):
        super(TestCloudFormationBaseActor, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        reload(cloudformation)

        self.actor = cloudformation.CloudFormationBaseActor(
            'unittest', {'region': 'us-east-1'})
        self.actor.cf3_conn = mock.MagicMock(name='cf3_conn')

    def test_get_template_body(self):
        file = 'examples/test/aws.cloudformation/cf.unittest.json'
        url = 'http://foobar.json'

        # Should work...
        ret = self.actor._get_template_body(file)
        expected = ('{"blank": "json"}', None)
        self.assertEquals(ret, expected)

        # Should return None
        ret = self.actor._get_template_body(None)
        expected = (None, None)
        self.assertEquals(ret, expected)

        # Should return None
        ret = self.actor._get_template_body(url)
        expected = (None, 'http://foobar.json')
        self.assertEquals(ret, expected)

        # Should raise exception
        with self.assertRaises(cloudformation.InvalidTemplate):
            self.actor._get_template_body('missing')

    @testing.gen_test
    def test_validate_template_body(self):
        yield self.actor._validate_template(body='test body')
        self.actor.cf3_conn.validate_template.assert_called_with(
            TemplateBody='test body')

    @testing.gen_test
    def test_validate_template_url(self):
        yield self.actor._validate_template(url='http://foobar.json')
        self.actor.cf3_conn.validate_template.assert_called_with(
            TemplateURL='http://foobar.json')

    @testing.gen_test
    def test_validate_template_raises_boto_error(self):
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

        self.actor.cf3_conn.validate_template.side_effect = ClientError(
            fake_exc, 'FakeOperation')
        with self.assertRaises(cloudformation.InvalidTemplate):
            yield self.actor._validate_template(url='junk')

        with self.assertRaises(cloudformation.InvalidTemplate):
            yield self.actor._validate_template(body='junk')

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
    def test_get_stack(self):
        self.actor.cf3_conn.describe_stacks.return_value = {
            'Stacks': [create_fake_stack('s1', 'UPDATE_COMPLETE')]}

        ret = yield self.actor._get_stack('s1')
        self.assertEquals(ret['StackName'], 's1')

    @testing.gen_test
    def test_get_stack_not_found(self):
        fake_exc = {
            'ResponseMetadata': {
                'HTTPStatusCode': 400,
                'RequestId': 'dfc1a12c-22c1-11e6-80b1-8fd4cf167f54'
            },
            'Error': {
                'Message': 'Stack with id s1 does not exist',
                'Code': 'ExecutionFailure',
                'Type': 'Sender'
            }
        }
        self.actor.cf3_conn.describe_stacks.side_effect = ClientError(
            fake_exc, 'Failure')

        ret = yield self.actor._get_stack('s1')
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_get_stack_exc(self):
        fake_exc = {
            'ResponseMetadata': {
                'HTTPStatusCode': 400,
                'RequestId': 'dfc1a12c-22c1-11e6-80b1-8fd4cf167f54'
            },
            'Error': {
                'Message': 'Some other error',
                'Code': 'ExecutionFailure',
                'Type': 'Sender'
            }
        }
        self.actor.cf3_conn.describe_stacks.side_effect = ClientError(
            fake_exc, 'Failure')

        with self.assertRaises(cloudformation.CloudFormationError):
            yield self.actor._get_stack('s1')

    @testing.gen_test
    def test_wait_until_state_complete(self):
        create_in_progress = create_fake_stack('test', 'CREATE_IN_PROGRESS')
        create_complete = create_fake_stack('test', 'CREATE_COMPLETE')

        # Make _get_stack() yield back 2 in-progress states, then yield a
        # successfull execution.
        self.actor._get_stack = mock.MagicMock(name='FakeStack')
        self.actor._get_stack.side_effect = [
            tornado_value(create_in_progress),
            tornado_value(create_in_progress),
            tornado_value(create_complete)
        ]
        yield self.actor._wait_until_state(
            'test', cloudformation.COMPLETE, sleep=0.01)
        self.actor._get_stack.assert_has_calls(
            [mock.call('test'), mock.call('test'), mock.call('test')])

    @testing.gen_test
    def test_wait_until_state_stack_failed(self):
        create_in_progress = create_fake_stack('test', 'CREATE_IN_PROGRESS')
        create_complete = create_fake_stack('test', 'CREATE_COMPLETE')

        # Make sure a cloudformationerror is raised if we ask for a deleted
        # state rather than a created one.
        self.actor._get_stack = mock.MagicMock(name='FakeStack')
        self.actor._get_stack.side_effect = [
            tornado_value(create_in_progress),
            tornado_value(create_in_progress),
            tornado_value(create_complete)
        ]
        with self.assertRaises(cloudformation.StackFailed):
            yield self.actor._wait_until_state(
                'test', cloudformation.DELETED, sleep=0.1)

    @testing.gen_test
    def test_wait_until_state_stack_not_found(self):
        # Lastly, test that if wait_until_state returns no actor, we bail
        # appropriately.
        self.actor._get_stack = mock.MagicMock(name='FakeStack')
        self.actor._get_stack.return_value = tornado_value(None)
        with self.assertRaises(cloudformation.StackNotFound):
            yield self.actor._wait_until_state(
                'test', cloudformation.COMPLETE, sleep=0.1)

    @testing.gen_test
    def test_get_stack_events(self):
        fake_events = {
            'StackEvents': [
                create_fake_stack_event('test', 'test', 'DELETE_COMPLETE'),
                create_fake_stack_event('test', 's3', 'DELETE_COMPLETE'),
                create_fake_stack_event('test', 's3', 'DELETE_IN_PROGRESS'),
                create_fake_stack_event('test', 's3', 'CREATE_FAILED', 'bad'),
                create_fake_stack_event('test', 's3', 'CREATE_IN_PROGRESS'),
                create_fake_stack_event('test', 'test', 'CREATE_IN_PROGRESS')
            ]
        }
        expected = [
            'AWS::CloudFormation::Stack test (CREATE_IN_PROGRESS): ',
            'AWS::CloudFormation::Stack s3 (CREATE_IN_PROGRESS): ',
            'AWS::CloudFormation::Stack s3 (CREATE_FAILED): bad',
            'AWS::CloudFormation::Stack s3 (DELETE_IN_PROGRESS): ',
            'AWS::CloudFormation::Stack s3 (DELETE_COMPLETE): ',
            'AWS::CloudFormation::Stack test (DELETE_COMPLETE): '
        ]
        self.actor.cf3_conn.describe_stack_events.return_value = fake_events
        ret = yield self.actor._get_stack_events('test')

        self.assertEquals(ret, expected)

    @testing.gen_test
    def test_get_stack_events_exc(self):
        fake_exc = {
            'ResponseMetadata': {
                'HTTPStatusCode': 400,
                'RequestId': 'dfc1a12c-22c1-11e6-80b1-8fd4cf167f54'
            },
            'Error': {
                'Message': 'Some other error',
                'Code': 'ExecutionFailure',
                'Type': 'Sender'
            }
        }
        self.actor.cf3_conn.describe_stack_events.side_effect = ClientError(
            fake_exc, 'Failure')
        ret = yield self.actor._get_stack_events('test')
        self.assertEquals(ret, [])

    @testing.gen_test
    def test_delete_stack(self):
        self.actor.cf3_conn.delete_stack.return_value = {
            'ResponseMetadata': {'RequestId': 'req-id-1'}
        }
        self.actor._wait_until_state = mock.MagicMock(name='_wait_until_state')
        self.actor._wait_until_state.side_effect = cloudformation.StackNotFound()

        yield self.actor._delete_stack(stack='stack')

        self.assertTrue(self.actor.cf3_conn.delete_stack.called)
        self.assertTrue(self.actor._wait_until_state.called)

    @testing.gen_test
    def test_delete_stack_raises_boto_error(self):
        self.actor.cf3_conn.delete_stack = mock.MagicMock(name='delete_stack_mock')

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

        self.actor.cf3_conn.delete_stack.side_effect = ClientError(
            fake_exc, 'Error')
        with self.assertRaises(cloudformation.CloudFormationError):
            yield self.actor._delete_stack(stack='stack')


class TestCreate(testing.AsyncTestCase):

    def setUp(self):
        super(TestCreate, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        reload(cloudformation)

    @testing.gen_test
    def test_create_stack_file(self):
        actor = cloudformation.Create(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2',
             'template':
                 'examples/test/aws.cloudformation/cf.integration.json'})
        actor._wait_until_state = mock.MagicMock(name='_wait_until_state')
        actor._wait_until_state.side_effect = [tornado_value(None)]
        actor.cf3_conn.create_stack = mock.MagicMock(name='create_stack_mock')
        actor.cf3_conn.create_stack.return_value = {'StackId': 'arn:123'}
        ret = yield actor._create_stack(stack='test')
        self.assertEquals(ret, 'arn:123')

    @testing.gen_test
    def test_create_stack_url(self):
        actor = cloudformation.Create(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2',
             'template': 'https://www.test.com'})
        actor._wait_until_state = mock.MagicMock(name='_wait_until_state')
        actor._wait_until_state.side_effect = [tornado_value(None)]
        actor.cf3_conn.create_stack = mock.MagicMock(name='create_stack_mock')
        actor.cf3_conn.create_stack.return_value = {'StackId': 'arn:123'}
        ret = yield actor._create_stack(stack='unit-test-cf')
        self.assertEquals(ret, 'arn:123')

    @testing.gen_test
    def test_create_stack_raises_boto_error(self):
        actor = cloudformation.Create(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2',
             'template':
                 'examples/test/aws.cloudformation/cf.integration.json'})
        actor.cf3_conn.create_stack = mock.MagicMock(name='create_stack_mock')

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
            yield actor._create_stack(stack='test')

    @testing.gen_test
    def test_create_stack_wait_until_raises_boto_error(self):
        actor = cloudformation.Create(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2',
             'template':
                 'examples/test/aws.cloudformation/cf.integration.json'})
        actor.cf3_conn.create_stack = mock.MagicMock(name='create_stack_mock')
        actor.cf3_conn.create_stack.return_value = {'StackId': 'arn:123'}

        actor._wait_until_state = mock.MagicMock(name='_wait_until_state')
        actor._wait_until_state.side_effect = cloudformation.StackFailed()

        actor._get_stack_events = mock.MagicMock(name='_get_stack_events')
        actor._get_stack_events.return_value = tornado_value(
            ['Log Message'])

        with self.assertRaises(cloudformation.StackFailed):
            yield actor._create_stack(stack='test')

    @testing.gen_test
    def test_execute(self):
        actor = cloudformation.Create(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2',
             'template':
                 'examples/test/aws.cloudformation/cf.integration.json'})

        actor._validate_template = mock.MagicMock(name='_validate_template')
        actor._validate_template.return_value = tornado_value(True)

        actor._get_stack = mock.MagicMock(name='_get_stack')
        actor._get_stack.return_value = tornado_value(None)

        actor._create_stack = mock.MagicMock(name='_create_stack')
        actor._create_stack.return_value = tornado_value(None)

        actor._wait_until_state = mock.MagicMock(name='_wait_until_state')
        actor._wait_until_state.return_value = tornado_value(None)
        yield actor._execute()

    @testing.gen_test
    def test_execute_exists(self):
        actor = cloudformation.Create(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2',
             'template':
                 'examples/test/aws.cloudformation/cf.integration.json'})

        actor._validate_template = mock.MagicMock(name='_validate_template')
        actor._validate_template.return_value = tornado_value(True)

        actor._get_stack = mock.MagicMock(name='_get_stack')
        actor._get_stack.return_value = tornado_value(True)

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

        actor._validate_template = mock.MagicMock(name='_validate_template')
        actor._validate_template.return_value = tornado_value(True)

        actor._get_stack = mock.MagicMock(name='_get_stack')
        actor._get_stack.return_value = tornado_value(None)

        yield actor._execute()


class TestDelete(testing.AsyncTestCase):

    def setUp(self):
        super(TestDelete, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        reload(cloudformation)

    @testing.gen_test
    def test_execute(self):
        actor = cloudformation.Delete(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2'})
        actor._get_stack = mock.MagicMock(name='_get_stack')
        actor._get_stack.return_value = tornado_value(True)
        actor._delete_stack = mock.MagicMock(name='_delete_stack')
        actor._delete_stack.return_value = tornado_value(None)
        actor._wait_until_state = mock.MagicMock(name='_wait_until_state')
        actor._wait_until_state.side_effect = cloudformation.StackNotFound()
        yield actor._execute()

    @testing.gen_test
    def test_execute_dry(self):
        actor = cloudformation.Delete(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2'}, dry=True)
        actor._get_stack = mock.MagicMock(name='_get_stack')
        actor._get_stack.return_value = tornado_value(True)
        yield actor._execute()

    @testing.gen_test
    def test_execute_not_exists(self):
        actor = cloudformation.Delete(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2'})
        actor._get_stack = mock.MagicMock(name='_get_stack')
        actor._get_stack.return_value = tornado_value(None)
        with self.assertRaises(cloudformation.StackNotFound):
            yield actor._execute()


class TestStack(testing.AsyncTestCase):

    def setUp(self):
        super(TestStack, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        reload(cloudformation)

        self.actor = cloudformation.Stack(
            options={
                'name': 'unit-test-cf',
                'state': 'present',
                'region': 'us-west-2',
                'template': 'examples/test/aws.cloudformation/cf.unittest.json'
            })
        self.actor.cf3_conn = mock.MagicMock(name='cf3_conn')

    @testing.gen_test
    def test_update_stack(self):
        fake_stack = create_fake_stack('fake', 'CREATE_FAILED')
        self.actor._get_stack = mock.MagicMock(name='_get_stack')
        self.actor._get_stack.return_value = tornado_value(fake_stack)
        self.actor._delete_stack = mock.MagicMock(name='_delete_stack')
        self.actor._delete_stack.return_value = tornado_value(fake_stack)
        self.actor._create_stack = mock.MagicMock(name='_create_stack')
        self.actor._create_stack.return_value = tornado_value(fake_stack)

        yield self.actor._update_stack(fake_stack)

        self.actor._delete_stack.assert_called_with(
            stack='arn:aws:cloudformation:us-east-1:xxxx:stack/fake/xyz')
        self.actor._create_stack.assert_called_with(
            stack='fake')

    @testing.gen_test
    def test_ensure_stack_is_absent_and_wants_absent(self):
        self.actor._options['state'] = 'absent'
        self.actor._get_stack = mock.MagicMock(name='_get_stack')
        self.actor._get_stack.return_value = tornado_value(None)
        self.actor._delete_stack = mock.MagicMock(name='_delete_stack')
        self.actor._delete_stack.return_value = tornado_value(None)
        self.actor._create_stack = mock.MagicMock(name='_create_stack')
        self.actor._create_stack.return_value = tornado_value(None)

        yield self.actor._ensure_stack()

        self.assertFalse(self.actor._create_stack.called)
        self.assertFalse(self.actor._delete_stack.called)

    @testing.gen_test
    def test_ensure_stack_is_present_and_wants_absent(self):
        self.actor._options['state'] = 'absent'
        fake_stack = create_fake_stack('unit-test-cf', 'CREATE_COMPLETE')
        self.actor._get_stack = mock.MagicMock(name='_get_stack')
        self.actor._get_stack.return_value = tornado_value(fake_stack)
        self.actor._delete_stack = mock.MagicMock(name='_delete_stack')
        self.actor._delete_stack.return_value = tornado_value(None)
        self.actor._create_stack = mock.MagicMock(name='_create_stack')
        self.actor._create_stack.return_value = tornado_value(None)

        yield self.actor._ensure_stack()

        self.assertTrue(self.actor._delete_stack.called)
        self.assertFalse(self.actor._create_stack.called)

    @testing.gen_test
    def test_ensure_stack_is_absent_and_wants_present(self):
        self.actor._options['state'] = 'present'
        self.actor._get_stack = mock.MagicMock(name='_get_stack')
        self.actor._get_stack.return_value = tornado_value(None)
        self.actor._delete_stack = mock.MagicMock(name='_delete_stack')
        self.actor._delete_stack.return_value = tornado_value(None)
        self.actor._create_stack = mock.MagicMock(name='_create_stack')
        self.actor._create_stack.return_value = tornado_value(None)

        yield self.actor._ensure_stack()

        self.assertFalse(self.actor._delete_stack.called)
        self.assertTrue(self.actor._create_stack.called)

    @testing.gen_test
    def test_ensure_stack_is_present_and_wants_update_create_failed(self):
        self.actor._options['state'] = 'present'
        fake_stack = create_fake_stack('fake', 'CREATE_FAILED')
        self.actor._get_stack = mock.MagicMock(name='_get_stack')
        self.actor._get_stack.return_value = tornado_value(fake_stack)
        self.actor._delete_stack = mock.MagicMock(name='_delete_stack')
        self.actor._delete_stack.return_value = tornado_value(None)
        self.actor._create_stack = mock.MagicMock(name='_create_stack')
        self.actor._create_stack.return_value = tornado_value(None)
        self.actor._update_stack = mock.MagicMock(name='_update_stack')
        self.actor._update_stack.return_value = tornado_value(None)

        yield self.actor._ensure_stack()

        self.assertFalse(self.actor._delete_stack.called)
        self.assertFalse(self.actor._create_stack.called)
        self.assertTrue(self.actor._update_stack.called)
