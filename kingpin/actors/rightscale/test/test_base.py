import logging
import mock

from tornado import testing
import requests

from kingpin.actors import exceptions
from kingpin.actors.rightscale import base

log = logging.getLogger(__name__)


class TestRightScaleBaseActor(testing.AsyncTestCase):
    def setUp(self, *args, **kwargs):
        super(TestRightScaleBaseActor, self).setUp()
        base.TOKEN = 'unittest'

    @testing.gen_test
    def test_init_without_environment_creds(self):
        # Un-set the token and make sure the init fails
        base.TOKEN = None
        with self.assertRaises(exceptions.InvalidCredentials):
            base.RightScaleBaseActor('Unit Test Action', {})

