import logging

from boto.exception import BotoServerError
from tornado import gen
from tornado import testing
import mock

from kingpin.actors.aws import cloudformation
from kingpin.actors.aws import settings

log = logging.getLogger(__name__)

# Make the retry decorator super fast in unit tests
#
# ## NOTE: THIS DOES NOT WORK RIGHT NOW. NOT SURE WHY.
cloudformation.WAIT_EXPONENTIAL_MAX = 1
cloudformation.MAX_RETRIES = 3
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

    @testing.gen_test
    def test_get_stacks(self):
        actor = cloudformation.CloudFormationBaseActor(
            'unittest', {'region': 'us-east-1'})
        actor.conn.list_stacks = mock.MagicMock()
        actor.conn.list_stacks.return_value = [1, 2, 3]
        ret = yield actor._get_stacks()
        self.assertEquals([1, 2, 3], ret)

    @testing.gen_test
    def test_does_stack_exist(self):
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

        ret = yield actor._does_stack_exist('stack-1')
        self.assertEquals(ret, True)

        ret = yield actor._does_stack_exist('stack-5')
        self.assertEquals(ret, False)


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
        self.assertEquals(actor._template_body, '')
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
        with self.assertRaises(cloudformation.InvalidTemplateException):
            actor = cloudformation.Create(
                'Unit Test Action',
                {'name': 'unit-test-cf',
                 'region': 'us-west-2',
                 'template': 'missing'})

    @testing.gen_test()
    def test_validate_template_body(self):
        actor = cloudformation.Create(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2',
             'template': 'examples/test/aws.cloudformation/cf.unittest.json'})
        actor.conn.validate_template = mock.MagicMock()
        yield actor._validate_template()
        actor.conn.validate_template.assert_called_with(
            template_body='', template_url=None)

    @testing.gen_test()
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

    @testing.gen_test()
    def test_validate_template_raises_boto_error(self):
        actor = cloudformation.Create(
            'Unit Test Action',
            {'name': 'unit-test-cf',
             'region': 'us-west-2',
             'template': 'http://foobar.json'})
        actor.conn.validate_template = mock.MagicMock()
        actor.conn.validate_template.side_effect = BotoServerError(
            400, 'Invalid template property or properties')
        with self.assertRaises(cloudformation.InvalidTemplateException):
            yield actor._validate_template()

        actor.conn.validate_template.side_effect = BotoServerError(
            500, 'Some other error')
        with self.assertRaises(BotoServerError):
            yield actor._validate_template()
