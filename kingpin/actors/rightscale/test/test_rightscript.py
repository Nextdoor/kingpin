import logging
import mock

from tornado import testing
import requests

from kingpin.actors import exceptions
from kingpin.actors.rightscale import base
from kingpin.actors.rightscale import rightscript
from kingpin.actors.test import helper

log = logging.getLogger(__name__)


class TestRightScript(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestRightScript, self).setUp()
        base.TOKEN = 'unittest'

        # Create the actor
        self.actor = rightscript.RightScript(
            options={
                'name': 'test-name',
                'commit': True,
                'description': 'test description',
                'packages': ['curl'],
                'source': 'examples/rightscale.rightscript/script1.sh',
            }
        )

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock()
        self.actor._client = self.client_mock

    @testing.gen_test
    def test_find_rightscript(self):
        fake_script = mock.MagicMock(name='FakeScript')
        fake_script.soul = {'name': 'FakeScript'}

        # Now create a fake Rightscale resource collection object and make sure
        with mock.patch.object(self.actor._client,
                               'find_by_name_and_keys') as u_mock:
            # Try a search with no exact matching
            u_mock.return_value = helper.tornado_value([fake_script])
            ret = yield self.actor._find_rightscript('FakeScript')
            self.assertEquals(ret[0].soul['name'], 'FakeScript')

    @testing.gen_test
    def test_find_rightscript_empty_result(self):
        # Now create a fake Rightscale resource collection object and make sure
        with mock.patch.object(self.actor._client,
                               'find_by_name_and_keys') as u_mock:
            # Try a search with no exact matching
            u_mock.return_value = helper.tornado_value(None)
            ret = yield self.actor._find_rightscript('FakeScript')
            self.assertEquals(ret, None)
