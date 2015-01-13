import logging

from boto.exception import BotoServerError
from tornado import gen
from tornado import testing
import mock

from kingpin.actors import exceptions
from kingpin.actors.aws import cloudformation
from kingpin.actors.aws import settings

log = logging.getLogger(__name__)

# Make the retry decorator super fast in unit tests
settings.CF_WAIT_MAX = 0
reload(cloudformation)


@gen.coroutine
def tornado_value(*args):
    """Returns whatever is passed in. Used for testing."""
    raise gen.Return(*args)


class TestCloudFormationBaseActor(testing.AsyncTestCase):

    def setUp(self):
        super(TestCloudFormationBaseActor, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'

    def test_init_with_bad_creds(self):
        settings.AWS_ACCESS_KEY_ID = None
        settings.AWS_SECRET_ACCESS_KEY = None
        with self.assertRaises(exceptions.InvalidCredentials):
            cloudformation.CloudFormationBaseActor(
                'unittest', {'region': 'us-east-1'})

    @testing.gen_test
    def test_get_stacks(self):
        actor = cloudformation.CloudFormationBaseActor(
            'unittest', {'region': 'us-east-1'})
        actor.conn.list_stacks = mock.MagicMock()
        actor.conn.list_stacks.return_value = [1, 2, 3]
        ret = yield actor._get_stacks()
        self.assertEquals([1, 2, 3], ret)

    @testing.gen_test
    def test_get_stack(self):
        actor = cloudformation.CloudFormationBaseActor(
            'unittest', {'region': 'us-east-1'})

        actor.conn.list_stacks = mock.MagicMock()
        s1 = mock.MagicMock()
        s1.stack_name = 'stack-1'
        s2 = mock.MagicMock()
        s2.stack_name = 'stack-2'
        s3 = mock.MagicMock()
        s3.stack_name = 'stack-3'
        actor.conn.list_stacks.return_value = [s1, s2, s3]

        ret = yield actor._get_stack('stack-1')
        self.assertEquals(ret, s1)

        ret = yield actor._get_stack('stack-5')
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_wait_until_state(self):
        create_in_progress = mock.MagicMock(name='create_in_progress')
        create_in_progress.stack_status = 'CREATE_IN_PROGRESS'
        create_in_progress.stack_name = 'unittest'

        create_complete = mock.MagicMock(name='CREATE_COMPLETE')
        create_complete.stack_status = 'CREATE_COMPLETE'
        create_complete.stack_name = 'unittest'

        rollback_complete = mock.MagicMock(name='ROLLBACK_COMPLETE')
        rollback_complete.stack_status = 'ROLLBACK_COMPLETE'
        rollback_complete.stack_name = 'unittest'

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

    def test_get_template_body(self):
        # Should work...
        actor = cloudformation.Create(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2',
             'template': 'examples/test/aws.cloudformation/cf.unittest.json'})
        # TODO: Fill this in with some real content
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
        actor.conn.validate_template = mock.MagicMock()
        yield actor._validate_template()
        actor.conn.validate_template.assert_called_with(
            template_body='#BLANK\n', template_url=None)

    @testing.gen_test
    def test_validate_template_url(self):
        actor = cloudformation.Create(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2',
             'template': 'http://foobar.json'})
        actor.conn.validate_template = mock.MagicMock()
        yield actor._validate_template()
        actor.conn.validate_template.assert_called_with(
            template_body=None, template_url='http://foobar.json')

    @testing.gen_test
    def test_validate_template_raises_boto_error(self):
        actor = cloudformation.Create(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2',
             'template': 'http://foobar.json'})
        actor.conn.validate_template = mock.MagicMock()
        actor.conn.validate_template.side_effect = BotoServerError(
            400, 'Invalid template property or properties')
        with self.assertRaises(cloudformation.InvalidTemplate):
            yield actor._validate_template()

        actor.conn.validate_template.side_effect = BotoServerError(
            403, 'Invalid Credentials')
        with self.assertRaises(exceptions.InvalidCredentials):
            yield actor._validate_template()

        actor.conn.validate_template.side_effect = BotoServerError(
            500, 'Some other error')
        with self.assertRaises(BotoServerError):
            yield actor._validate_template()

    @testing.gen_test
    def test_create_stack(self):
        actor = cloudformation.Create(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2',
             'template':
                 'examples/test/aws.cloudformation/cf.integration.json'})
        actor.conn.create_stack = mock.MagicMock(name='create_stack_mock')
        actor.conn.create_stack.return_value = 'arn:123'
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
        actor.conn.create_stack = mock.MagicMock()

        actor.conn.create_stack.side_effect = BotoServerError(
            400, 'Invalid template property or properties')
        with self.assertRaises(cloudformation.CloudFormationError):
            yield actor._create_stack()

        actor.conn.create_stack.side_effect = BotoServerError(
            403, 'Invalid credentials')
        with self.assertRaises(exceptions.InvalidCredentials):
            yield actor._create_stack()

        actor.conn.create_stack.side_effect = BotoServerError(
            500, 'Some unexpected failure')
        with self.assertRaises(BotoServerError):
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

    @testing.gen_test
    def test_delete_stack(self):
        actor = cloudformation.Delete(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2'})
        actor.conn.delete_stack = mock.MagicMock(name='delete_stack_mock')
        actor.conn.delete_stack.return_value = 'req-id-1'
        ret = yield actor._delete_stack()
        self.assertEquals(ret, 'req-id-1')

    @testing.gen_test
    def test_delete_stack_raises_boto_error(self):
        actor = cloudformation.Delete(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2'})
        actor.conn.delete_stack = mock.MagicMock()

        actor.conn.delete_stack.side_effect = BotoServerError(
            400, 'Some error')
        with self.assertRaises(cloudformation.CloudFormationError):
            yield actor._delete_stack()

        actor.conn.delete_stack.side_effect = BotoServerError(
            403, 'Invalid credentials')
        with self.assertRaises(exceptions.InvalidCredentials):
            yield actor._delete_stack()

        actor.conn.delete_stack.side_effect = BotoServerError(
            500, 'Some unexpected failure')
        with self.assertRaises(BotoServerError):
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
