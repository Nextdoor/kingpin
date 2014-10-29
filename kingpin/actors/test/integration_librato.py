"""Tests for the actors.librato package"""

from nose.plugins.attrib import attr

from tornado import testing

from kingpin.actors import librato
from kingpin.actors import exceptions


__author__ = 'Charles McLaughlin <charles@nextdoor.com>'


class IntegrationLibratoAnnotation(testing.AsyncTestCase):

    """Integration tests against the Librato API.

    These tests actually hit the Librato API and test that the code
    works, as well as validate that the API credentials are working properly.

    Require LIBRATO_TOKEN and LIBRATO_EMAIL environment variables to be set.
    """

    integration = True

    @attr('integration', 'dry')
    @testing.gen_test
    def integration_test_init_without_token(self):
        # Un-set auth token and make sure the init fails
        librato.TOKEN = None
        with self.assertRaises(exceptions.InvalidCredentials):
            librato.Annotation(
                'Unit Test Action',
                {'title': 'unittest',
                 'description': 'unittest',
                 'name': 'unittest'}, dry=True)

    @attr('integration', 'dry')
    @testing.gen_test
    def integration_test_init_without_email(self):
        # Un-set auth email and make sure the init fails
        librato.EMAIL = None
        with self.assertRaises(exceptions.InvalidCredentials):
            librato.Annotation(
                'Unit Test Action',
                {'title': 'unittest',
                 'description': 'unittest',
                 'name': 'unittest'}, dry=True)

    @attr('integration', 'dry')
    @testing.gen_test
    def integration_test_execute_with_invalid_token(self):
        # Set auth token to invalid value and make sure execute fails
        librato.TOKEN = 'Invalid'

        actor = librato.Annotation(
            'Unit Test Action',
            {'title': 'unittest',
             'description': 'unittest',
             'name': 'unittest'}, dry=True)

        with self.assertRaises(exceptions.InvalidCredentials):
            yield actor.execute()

    @attr('integration', 'dry')
    @testing.gen_test
    def integration_test_execute_with_invalid_email(self):
        # Set auth email to invalid value and make sure execute fails
        librato.EMAIL = 'Invalid'

        actor = librato.Annotation(
            'Unit Test Action',
            {'title': 'unittest',
             'description': 'unittest',
             'name': 'unittest'}, dry=True)

        with self.assertRaises(exceptions.InvalidCredentials):
            yield actor.execute()

    @attr('integration', 'dry')
    @testing.gen_test
    def integration_test_execute_dry(self):
        actor = librato.Annotation(
            'Unit Test Action',
            {'title': 'Kingpin Integration Testing',
             'description': 'Executing integration tests',
             'name': 'kingpin-integration-testing'}, dry=True)

        res = yield actor.execute()
        self.assertEquals(res, None)

    @attr('integration')
    @testing.gen_test
    def integration_test_execute(self):
        actor = librato.Annotation(
            'Unit Test Action',
            {'title': 'Kingpin Integration Testing',
             'description': 'Executing integration tests',
             'name': 'kingpin-integration-testing'})

        res = yield actor.execute()
        self.assertEquals(res, None)
