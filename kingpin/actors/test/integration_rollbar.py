"""Tests for the actors.rollbar package"""

from nose.plugins.attrib import attr

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

    @attr('rollbar', 'integration')
    @testing.gen_test(timeout=60)
    @mock.patch.dict(rollbar, {'TOKEN': None})
    def integration_test_1a_init_without_environment_creds(self):
        # Make sure the init fails
        with self.assertRaises(exceptions.InvalidCredentials):
            rollbar.Deploy(
                'Unit Test Action',
                {'environment': 'kingpin-integration-testing',
                 'revision': version.__version__,
                 'local_username': 'Kingpin Integration Testing',
                 'comment': 'Integration Tests Are Good, MmmKay'})

    @attr('rollbar', 'integration', 'dry')
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

    @attr('rollbar', 'integration', 'dry')
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

    @attr('rollbar', 'integration')
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

    @attr('rollbar', 'integration')
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
