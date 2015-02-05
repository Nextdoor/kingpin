"""Tests for the actors.slack package"""

from tornado import testing

from kingpin.actors import slack
from kingpin.actors import exceptions


__author__ = 'Matt Wise <matt@nextdoor.com>'


class IntegrationSlackMessage(testing.AsyncTestCase):

    """Simple high level integration tests agains the Slack API.

    These tests actually hit the Slack API and test that the code
    works, as well as validate that the API token is working properly.

    Require SLACK_TOKEN environment variable to be set.
    """

    integration = True
    message = 'Unit test message'
    channel = '#kingpin-integration'

    @testing.gen_test(timeout=2)
    def integration_test_init_without_environment_creds(self):
        # Un-set the token now and make sure the init fails
        slack.TOKEN = None
        with self.assertRaises(exceptions.InvalidCredentials):
            slack.Message(
                'Unit Test Action',
                {'message': self.message,
                 'channel': self.channel}, dry=True)

        # Reload the slack library to re-get the token
        reload(slack)

    @testing.gen_test(timeout=2)
    def integration_test_execute_with_invalid_creds(self):
        # Un-set the token now and make sure the init fails
        slack.TOKEN = 'unittest'
        actor = slack.Message(
            'Unit Test Action',
            {'message': self.message,
             'channel': self.channel}, dry=True)

        # Valid response test
        actor._token = 'Invalid'
        with self.assertRaises(exceptions.InvalidCredentials):
            yield actor.execute()

        # Reload the slack library to re-get the token
        reload(slack)

    @testing.gen_test(timeout=60)
    def integration_test_execute_invalid_room(self):
        actor = slack.Message(
            'Unit Test Action',
            {'message': self.message,
             'channel': "#bad_channel"})
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield actor.execute()

    @testing.gen_test(timeout=60)
    def integration_test_execute_dry(self):
        actor = slack.Message(
            'Unit Test Action',
            {'message': self.message,
             'channel': self.channel}, dry=True)
        res = yield actor.execute()
        self.assertEquals(res, None)

    @testing.gen_test(timeout=60)
    def integration_test_execute_real(self):
        actor = slack.Message(
            'Unit Test Action',
            {'message': self.message,
             'channel': self.channel})
        res = yield actor.execute()
        self.assertEquals(res, None)
