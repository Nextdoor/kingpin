"""Simple integration tests for the AWS Base."""

from nose.plugins.attrib import attr
import logging

from tornado import testing

from kingpin.actors import exceptions
from kingpin.actors.aws import base
from kingpin.actors.aws import settings

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'

log = logging.getLogger(__name__)
logging.getLogger('boto').setLevel(logging.INFO)


class IntegrationBase(testing.AsyncTestCase):
    """High level AWS Base testing."""

    integration = True

    region = 'us-east-1'
    elb_name = 'kingpin-integration-test'

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_01a_check_credentials(self):

        settings.AWS_ACCESS_KEY_ID = 'fake'
        settings.AWS_SECRET_ACCESS_KEY = 'fake'
        actor = base.AWSBaseActor('Test', {'region': self.region})

        # Executing a random function call that is wrapped in _retry.
        # Credentials should fail before "ELB not found" should be raised.
        with self.assertRaises(exceptions.InvalidCredentials):
            yield actor._find_elb('unit-test')

        reload(settings)

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_02a_find_elb(self):

        actor = base.AWSBaseActor('Test', {'region': self.region})

        LB = yield actor._find_elb(self.elb_name)

        self.assertEquals(LB.name, self.elb_name)
