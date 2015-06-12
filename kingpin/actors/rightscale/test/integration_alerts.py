"""Simple integration tests for the RightScale Server_Array actors."""

from nose.plugins.attrib import attr
import uuid

from tornado import testing

from kingpin.actors import exceptions
from kingpin.actors.rightscale import alerts


__author__ = 'Matt Wise <matt@nextdoor.com>'


# Generate a common UUID for this particular set of tests
UUID = uuid.uuid4().hex


class IntegrationAlerts(testing.AsyncTestCase):

    """High level RightScale Server Array Actors Testing.

    These tests rely on you having a Alerts in RightScale named
      'kingpin-integration-testing'
    that can be cloned, launched, terminated, etc.

    Note, these tests must be run in-order. The order is defined by
    their definition order in this file. Nose follows this order according
    to its documentation:

        http://nose.readthedocs.org/en/latest/writing_tests.html


    NOTE: At this point, you need to self-clean-up after yourself
          once you've run these tests. Future tests and features will
          allow for these tests to self-clean-up.
    """

    integration = True

    def setUp(self, *args, **kwargs):
        super(IntegrationAlerts, self).setUp(*args, **kwargs)
        self.template_array = 'kingpin-integration-testing'
