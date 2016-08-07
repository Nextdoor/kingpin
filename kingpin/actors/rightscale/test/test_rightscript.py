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
                'commit': 'yeah',
                'description': 'test description',
                'packages': ['curl'],
                'source': 'examples/rightscale.rightscript/script1.sh',
            }
        )

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock()
        self.actor._client = self.client_mock

    def test_read_source(self):
        # Should work fine
        ret = self.actor._read_source()
        self.assertEquals('echo script1\n', ret)

        # Should throw a token exc
        self.actor._options['source'] = (
            'examples/rightscale.rightscript/script2.sh')
        with self.assertRaises(exceptions.InvalidOptions):
            self.actor._read_source()
        self.actor._init_tokens = {'TEST': 'test'}
        ret = self.actor._read_source()
        self.assertEquals('echo script2: test\n', ret)

        # Should throw exc
        self.actor._options['source'] = 'junk'
        with self.assertRaises(exceptions.InvalidOptions):
            self.actor._read_source()

    @testing.gen_test
    def test_get_script(self):
        fake_script = mock.MagicMock(name='FakeScript')
        fake_script.soul = {'name': 'FakeScript'}

        # Now create a fake Rightscale resource collection object and make sure
        with mock.patch.object(self.actor._client,
                               'find_by_name_and_keys') as u_mock:
            # Try a search with no exact matching
            u_mock.return_value = helper.tornado_value([fake_script])
            ret = yield self.actor._get_script('FakeScript')
            self.assertEquals(ret[0].soul['name'], 'FakeScript')

    @testing.gen_test
    def test_get_script_empty_result(self):
        # Now create a fake Rightscale resource collection object and make sure
        with mock.patch.object(self.actor._client,
                               'find_by_name_and_keys') as u_mock:
            # Try a search with no exact matching
            u_mock.return_value = helper.tornado_value(None)
            ret = yield self.actor._get_script('FakeScript')
            self.assertEquals(ret, None)

    @testing.gen_test
    def test_create_script(self):
        with mock.patch.object(self.actor._client,
                               'create_resource') as u_mock:
            u_mock.return_value = helper.tornado_value(1)
            ret = yield self.actor._create_script(name='test')
            self.assertTrue(self.actor.changed)
            self.assertEquals(1, ret)

    @testing.gen_test
    def test_ensure_script_creates_if_missing(self):
        self.actor._options['state'] = 'present'
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(None)]

        fake_script = mock.MagicMock(name='script')

        self.actor._create_script = mock.MagicMock()
        self.actor._create_script.side_effect = [
            helper.tornado_value(fake_script)]

        ret = yield self.actor._ensure_script()
        self.assertEquals(fake_script, ret)
        self.assertTrue(self.actor._create_script.called)

    @testing.gen_test
    def test_ensure_script_does_nothing_if_existing(self):
        self.actor._options['state'] = 'present'
        fake_script = mock.MagicMock(name='script')
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(fake_script)]

        ret = yield self.actor._ensure_script()
        self.assertEquals(fake_script, ret)

    @testing.gen_test
    def test_ensure_script_deletes_if_exists(self):
        self.actor._options['state'] = 'absent'
        fake_script = mock.MagicMock(name='script')
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(fake_script)]

        self.actor._delete_script = mock.MagicMock()
        self.actor._delete_script.side_effect = [
            helper.tornado_value(None)]

        ret = yield self.actor._ensure_script()
        self.assertEquals(None, ret)
        self.assertTrue(self.actor._delete_script.called)

    @testing.gen_test
    def test_ensure_script_does_nothing_if_absent(self):
        self.actor._options['state'] = 'absent'
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(None)]

        ret = yield self.actor._ensure_script()
        self.assertEquals(None, ret)
