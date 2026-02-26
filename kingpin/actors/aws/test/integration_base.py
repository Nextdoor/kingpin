import unittest

"""Simple integration tests for the AWS Base."""

import importlib
import logging

from nose.plugins.attrib import attr

from kingpin.actors import exceptions
from kingpin.actors.aws import base, settings

__author__ = "Mikhail Simin <mikhail@nextdoor.com>"

log = logging.getLogger(__name__)
logging.getLogger("boto").setLevel(logging.INFO)


class IntegrationBase(unittest.IsolatedAsyncioTestCase):
    """High level AWS Base testing."""

    integration = True

    region = "us-east-1"
    elb_name = "kingpin-integration-test"

    @attr("aws", "integration")
    def integration_01a_check_credentials(self):

        settings.AWS_ACCESS_KEY_ID = "fake"
        settings.AWS_SECRET_ACCESS_KEY = "fake"
        settings.AWS_SESSION_TOKEN = "fake"
        actor = base.AWSBaseActor("Test", {"region": self.region})

        # Executing a random function call that is wrapped in _retry.
        # Credentials should fail before "ELB not found" should be raised.
        with self.assertRaises(exceptions.InvalidCredentials):
            yield actor._find_elb("unit-test")

        importlib.reload(settings)

    @attr("aws", "integration")
    def integration_02a_find_elb(self):

        actor = base.AWSBaseActor("Test", {"region": self.region})

        LB = yield actor._find_elb(self.elb_name)

        self.assertEqual(LB.name, self.elb_name)
