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

    @attr('aws', 'integration')
    @testing.gen_test(timeout=600)
    def integration_01_create_stack(self):
        actor = cloudformation.Create(
            'Create Stack',
            {'region': self.region,
             'name': self.bucket_name,
             'template':
                 'examples/test/aws.cloudformation/cf.integration.json',
             'parameters': {
                 'BucketName': self.bucket_name,
                 'BucketPassword': UUID,
                 'Metadata': UUID,
             }})

        done = yield actor.execute()
        self.assertEqual(done, None)

    @attr('aws', 'integration')
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
                 'BucketPassword': UUID,
                 'Metadata': UUID,
             }})

        with self.assertRaises(cloudformation.StackAlreadyExists):
            yield actor.execute()

    @attr('aws', 'integration')
    @testing.gen_test(timeout=600)
    def integration_03_delete_stack(self):
        actor = cloudformation.Delete(
            'Delete Stack',
            {'region': self.region,
             'name': self.bucket_name})

        done = yield actor.execute()
        self.assertEqual(done, None)


class IntegrationStack(testing.AsyncTestCase):

    """High Level CloudFormation Stack Testing.

    These tests will check two things:
    * Create a super-simple CloudFormation stack
    * Update the stack
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
    bucket_name = 'kingpin-stack-%s' % UUID

    @attr('aws', 'integration')
    @testing.gen_test(timeout=600)
    def integration_01a_ensure_stack(self):
        actor = cloudformation.Stack(
            options={
                'region': self.region,
                'state': 'present',
                'name': self.bucket_name,
                'template':
                    'examples/test/aws.cloudformation/cf.integration.json',
                'parameters': {
                    'BucketName': self.bucket_name,
                    'BucketPassword': UUID,
                    'Metadata': UUID
                }})

        done = yield actor.execute()
        self.assertEqual(done, None)

    @attr('aws', 'integration')
    @testing.gen_test(timeout=600)
    def integration_01b_ensure_stack_still_there(self):
        actor = cloudformation.Stack(
            options={
                'region': self.region,
                'state': 'present',
                'name': self.bucket_name,
                'template':
                    'examples/test/aws.cloudformation/cf.integration.json',
                'parameters': {
                    'BucketName': self.bucket_name,
                    'BucketPassword': UUID,
                    'Metadata': UUID
                }})

        done = yield actor.execute()
        self.assertEqual(done, None)

    @attr('aws', 'integration')
    @testing.gen_test(timeout=600)
    def integration_02_changing_password_should_be_a_noop(self):
        #  This should pretty much do nothing.. if it did trigger a ChangeSet,
        #  we would actually fail because we're issuing a ChangeSet where no
        #  resources are actually modified. Thus, if this succeeds, we know
        #  that no stack change was made.
        actor = cloudformation.Stack(
            options={
                'region': self.region,
                'state': 'present',
                'name': self.bucket_name,
                'template':
                    'examples/test/aws.cloudformation/cf.integration.json',
                'parameters': {
                    'BucketName': self.bucket_name,
                    'BucketPassword': 'test',
                    'Metadata': UUID
                }})

        done = yield actor.execute()
        self.assertEqual(done, None)

    @attr('aws', 'integration')
    @testing.gen_test(timeout=600)
    def integration_03_update_by_overriding_default(self):
        actor = cloudformation.Stack(
            options={
                'region': self.region,
                'state': 'present',
                'name': self.bucket_name,
                'template':
                    'examples/test/aws.cloudformation/cf.integration.json',
                'parameters': {
                    'BucketName': self.bucket_name,
                    'BucketPassword': UUID,
                    'DefaultParam': 'OverriddenValue',
                    'Metadata': UUID
                }})

        done = yield actor.execute()
        self.assertEqual(done, None)

    @attr('aws', 'integration')
    @testing.gen_test(timeout=600)
    def integration_04a_update_bucket_name(self):
        actor = cloudformation.Stack(
            options={
                'region': self.region,
                'state': 'present',
                'name': self.bucket_name,
                'template':
                    'examples/test/aws.cloudformation/cf.integration.json',
                'parameters': {
                    'BucketName': '%s-updated' % self.bucket_name,
                    'BucketPassword': UUID,
                    'Metadata': UUID
                }})

        done = yield actor.execute()
        self.assertEqual(done, None)

    @attr('aws', 'integration')
    @testing.gen_test(timeout=600)
    def integration_04b_update_bucket_name_second_time_should_work(self):
        actor = cloudformation.Stack(
            options={
                'region': self.region,
                'state': 'present',
                'name': self.bucket_name,
                'template':
                    'examples/test/aws.cloudformation/cf.integration.json',
                'parameters': {
                    'BucketName': '%s-updated' % self.bucket_name,
                    'BucketPassword': UUID,
                    'Metadata': UUID
                }})

        done = yield actor.execute()
        self.assertEqual(done, None)

    @attr('aws', 'integration')
    @testing.gen_test(timeout=600)
    def integration_05a_delete_stack(self):
        actor = cloudformation.Stack(
            options={
                'region': self.region,
                'state': 'absent',
                'name': self.bucket_name,
                'template':
                    'examples/test/aws.cloudformation/cf.integration.json',
                'parameters': {
                    'BucketName': '%s-updated' % self.bucket_name,
                    'BucketPassword': UUID,
                    'Metadata': UUID
                }})

        done = yield actor.execute()
        self.assertEqual(done, None)

    @attr('aws', 'integration')
    @testing.gen_test(timeout=600)
    def integration_05b_ensure_stack_absent(self):
        actor = cloudformation.Stack(
            options={
                'region': self.region,
                'state': 'absent',
                'name': self.bucket_name,
                'template':
                    'examples/test/aws.cloudformation/cf.integration.json',
                'parameters': {
                    'BucketName': '%s-updated' % self.bucket_name,
                    'BucketPassword': UUID,
                    'Metadata': UUID
                }})

        done = yield actor.execute()
        self.assertEqual(done, None)
