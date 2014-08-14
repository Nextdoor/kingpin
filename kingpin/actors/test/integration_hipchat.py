"""Tests for the actors.hipchat package"""

from tornado import testing

from kingpin.actors import hipchat
from kingpin.actors import exceptions


__author__ = 'Matt Wise <matt@nextdoor.com>'


class IntegrationHipchatMessage(testing.AsyncTestCase):
    """Simple high level integration tests agains the HipChat API.

    These tests actually hit the HipChat API and test that the code
    works, as well as validate that the API token is working properly.

    Require HIPCHAT_TOKEN environment variable to be set.
    """

    integration = True

    @testing.gen_test
    def integration_test_init_without_environment_creds(self):
        message = 'Unit test message'
        room = 'Operations'

        # Un-set the token now and make sure the init fails
        hipchat.TOKEN = None
        with self.assertRaises(exceptions.InvalidCredentials):
            hipchat.Message(
                'Unit Test Action',
                {'message': message, 'room': room}, dry=True)

    @testing.gen_test
    def integration_test_execute_with_invalid_creds(self):
        message = 'Unit test message'
        room = 'unit_room'
        actor = hipchat.Message(
            'Unit Test Action',
            {'message': message, 'room': room}, dry=True)

        # Valid response test
        actor._token = 'Invalid'
        with self.assertRaises(exceptions.InvalidCredentials):
            yield actor.execute()

    @testing.gen_test
    def integration_test_execute_real(self):
        message = 'Unit test message'
        room = 'Operations'
        actor = hipchat.Message(
            'Unit Test Action',
            {'message': message, 'room': room}, dry=True)
        res = yield actor.execute()
        self.assertEquals(True, res)
