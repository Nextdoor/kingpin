import logging

from boto.exception import BotoServerError
from tornado import gen
from tornado import testing
import mock

from kingpin import utils
from kingpin.actors import exceptions
from kingpin.actors.aws import cloudformation
from kingpin.actors.aws import settings

log = logging.getLogger(__name__)


@gen.coroutine
def tornado_value(*args):
    """Returns whatever is passed in. Used for testing."""
    raise gen.Return(*args)


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

        # Should raise exception
        with self.assertRaises(cloudformation.InvalidTemplateException):
            actor = cloudformation.Create(
                'Unit Test Action',
                {'name': 'unit-test-cf',
                 'region': 'us-west-2',
                 'template': 'missing'})
