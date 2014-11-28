"""Tests for the actors.rollbar package"""

from tornado import testing

from kingpin import version
from kingpin.actors import rollbar
from kingpin.actors import exceptions


__author__ = 'Matt Wise <matt@nextdoor.com>'


class IntegrationRollbarDeploy(testing.AsyncTestCase):

    """Simple high level integration tests agains the Rollbar API.

    These tests actually hit the Rollbar API and test that the code
    works, as well as validate that the API token is working properly.

    Require ROLLBAR_TOKEN environment variable to be set.
    """

    integration = True

    @testing.gen_test(timeout=60)
    def integration_test_1a_init_without_environment_creds(self):
        # Un-set the token now and make sure the init fails
        rollbar.TOKEN = None
        with self.assertRaises(exceptions.InvalidCredentials):
            rollbar.Deploy(
                'Unit Test Action',
                {'environment': 'kingpin-integration-testing',
                 'revision': version.__version__,
                 'local_username': 'Kingpin Integration Testing',
                 'comment': 'Integration Tests Are Good, MmmKay'})

        # Reload the rollbar package so it gets our environment variable back.
        reload(rollbar)

    @testing.gen_test(timeout=60)
    def integration_test_2a_execute_with_invalid_creds(self):
        actor = rollbar.Deploy(
            'Unit Test Action',
            {'environment': 'kingpin-integration-testing',
             'revision': version.__version__,
             'local_username': 'Kingpin Integration Testing',
             'comment': 'Integration Tests Are Good, MmmKay'}, dry=True)

        # Valid response test
        actor._token = 'Invalid'
        with self.assertRaises(exceptions.InvalidCredentials):
            yield actor.execute()

    @testing.gen_test(timeout=60)
    def integration_test_2b_execute_dry(self):
        actor = rollbar.Deploy(
            'Unit Test Action',
            {'environment': 'kingpin-integration-testing',
             'revision': version.__version__,
             'local_username': 'Kingpin Integration Testing',
             'comment': 'This should never appear in Rollbar'}, dry=True)
        res = yield actor.execute()
        self.assertEquals(res, None)

    @testing.gen_test(timeout=60)
    def integration_test_2c_execute_real(self):
        actor = rollbar.Deploy(
            'Unit Test Action',
            {'environment': 'kingpin-integration-testing',
             'revision': version.__version__,
             'local_username': 'Kingpin Integration Testing',
             'comment': 'Integration Tests Are Good, MmmKay'})

        res = yield actor.execute()
        self.assertEquals(res, None)

    @testing.gen_test(timeout=60)
    def integration_test_2d_execute_real_with_rollbar_username(self):
        actor = rollbar.Deploy(
            'Unit Test Action',
            {'environment': 'kingpin-integration-testing',
             'revision': version.__version__,
             'local_username': 'Kingpin Integration Testing',
             'rollbar_username': 'Kingpin Integration Username',
             'comment': 'Now, with a rollbar_username too!'})

        res = yield actor.execute()
        self.assertEquals(res, None)
