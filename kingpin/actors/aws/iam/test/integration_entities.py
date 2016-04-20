"""Simple integration tests for the AWS IAM actors."""

from nose.plugins.attrib import attr
import logging

from tornado import testing

from kingpin.actors.aws import iam

__author__ = 'Matt Wise (matt@nextdoor.com)'

log = logging.getLogger(__name__)
logging.getLogger('boto').setLevel(logging.INFO)


class IntegrationIAMUsers(testing.AsyncTestCase):

    integration = True

    name = 'kingpin-integration-test'
    inline_policies = [
        'examples/aws.iam.user/s3_example.json'
    ]
    region = 'us-east-1'

    # Not really a test - this is just a state cleaner. Ensure that we start
    # without the testig user in place before we begin.
    @attr('aws', 'integration')
    @testing.gen_test(timeout=60)
    def integration_01_ensure_user_absent(self):
        actor = iam.User(
            'Test', {'name': self.name, 'state': 'absent'}, dry=False)
        yield actor.execute()

    @attr('aws', 'integration', 'dry')
    @testing.gen_test(timeout=60)
    def integration_02a_create_user_dry(self):
        actor = iam.User(
            'Test',
            {'name': self.name,
             'state': 'present',
             'inline_policies': self.inline_policies,
             'inline_policies_purge': True},
            dry=True)

        yield actor.execute()

    @attr('aws', 'integration')
    @testing.gen_test(timeout=60)
    def integration_02b_create_user(self):
        actor = iam.User(
            'Test',
            {'name': self.name,
             'inline_policies': self.inline_policies,
             'inline_policies_purge': True},
            dry=False)

        yield actor.execute()

    # Final cleanup -- delete our test user!
    @attr('aws', 'integration')
    @testing.gen_test(timeout=60)
    def integration_09_ensure_user_absent(self):
        actor = iam.User(
            'Test', {'name': self.name, 'state': 'absent'}, dry=False)
        yield actor.execute()


class IntegrationIAMGroups(testing.AsyncTestCase):

    integration = True

    name = 'kingpin-integration-test'
    inline_policies = [
        'examples/aws.iam.user/s3_example.json'
    ]
    region = 'us-east-1'

    # Not really a test - this is just a state cleaner. Ensure that we start
    # without the testig group in place before we begin.
    @attr('aws', 'integration')
    @testing.gen_test(timeout=60)
    def integration_01_ensure_group_absent(self):
        actor = iam.User(
            'Test', {'name': self.name, 'state': 'absent'}, dry=False)
        yield actor.execute()

    @attr('aws', 'integration', 'dry')
    @testing.gen_test(timeout=60)
    def integration_02a_create_group_dry(self):
        actor = iam.User(
            'Test',
            {'name': self.name,
             'state': 'present',
             'inline_policies': self.inline_policies,
             'inline_policies_purge': True},
            dry=True)

        yield actor.execute()

    @attr('aws', 'integration')
    @testing.gen_test(timeout=60)
    def integration_02b_create_group(self):
        actor = iam.User(
            'Test',
            {'name': self.name,
             'inline_policies': self.inline_policies,
             'inline_policies_purge': True},
            dry=False)

        yield actor.execute()

    # Final cleanup -- delete our test group!
    @attr('aws', 'integration')
    @testing.gen_test(timeout=60)
    def integration_09_ensure_group_absent(self):
        actor = iam.User(
            'Test', {'name': self.name, 'state': 'absent'}, dry=False)
        yield actor.execute()
