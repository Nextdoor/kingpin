"""Simple integration tests for the AWS CloudFormation actors."""

from nose.plugins.attrib import attr
import uuid
import logging

from tornado import testing

# from kingpin.actors import exceptions
from kingpin.actors.aws import cloudformation

__author__ = 'Matt Wise <matt@nextdoor.com>'

log = logging.getLogger(__name__)
logging.getLogger('boto').setLevel(logging.INFO)

UUID = uuid.uuid4().hex


class IntegrationCreate(testing.AsyncTestCase):

    """High Level CloudFormation Testing.

    These tests will check two things:
    * Create a super-simple CloudFormation stack
    * Delete that same stack

    Requirements:
        Your AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must have access to
        create CF stacks. The stack we create is extremely simple, and should
        impact none of your AWS resources. The stack creates a simple S3
        bucket, so your credentials must have access to create that buckets.

    Note, these tests must be run in-order. The order is defined by
    their definition order in this file. Nose follows this order according
    to its documentation:

        http://nose.readthedocs.org/en/latest/writing_tests.html
    """

    integration = True

    region = 'us-east-1'
    bucket_name = 'kingpin-%s' % UUID

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_01_create_stack(self):
        actor = cloudformation.Create(
            'Create Stack',
            {'region': self.region,
             'name': self.bucket_name,
             'template':
                 'examples/test/aws.cloudformation/cf.integration.json',
             'parameters': {
                 'BucketName': self.bucket_name,
             }})

        done = yield actor.execute()
        self.assertEquals(done, None)

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_02_create_duplicate_stack_should_fail(self):
        actor = cloudformation.Create(
            'Create Stack',
            {'region': self.region,
             'name': self.bucket_name,
             'template':
                 'examples/test/aws.cloudformation/cf.integration.json',
             'parameters': {
                 'BucketName': self.bucket_name,
             }})

        with self.assertRaises(cloudformation.StackAlreadyExists):
            yield actor.execute()

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_03_delete_stack(self):
        actor = cloudformation.Delete(
            'Delete Stack',
            {'region': self.region,
             'name': self.bucket_name})

        done = yield actor.execute()
        self.assertEquals(done, None)

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_04_delete_missing_stack_should_fail(self):
        actor = cloudformation.Delete(
            'Delete Stack',
            {'region': self.region,
             'name': self.bucket_name})

        with self.assertRaises(cloudformation.StackNotFound):
            yield actor.execute()
