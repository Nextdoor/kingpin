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
                               'find_by_name_and_keys') as find:
            # Try a search with no exact matching
            find.return_value = helper.tornado_value([fake_script])
            ret = yield self.actor._get_script('FakeScript')
            self.assertEquals(ret.soul['name'], 'FakeScript')

    @testing.gen_test
    def test_get_script_empty_result(self):
        # Now create a fake Rightscale resource collection object and make sure
        with mock.patch.object(self.actor._client,
                               'find_by_name_and_keys') as find:
            # Try a search with no exact matching
            find.return_value = helper.tornado_value(None)
            ret = yield self.actor._get_script('FakeScript')
            self.assertEquals(ret, None)

    @testing.gen_test
    def test_create_script(self):
        with mock.patch.object(self.actor._client,
                               'create_resource') as create:
            create.return_value = helper.tornado_value(1)
            ret = yield self.actor._create_script(name='test')
            self.assertTrue(self.actor.changed)
            self.assertEquals(1, ret)

    @testing.gen_test
    def test_delete_script_already_gone(self):
        self.actor._get_script = mock.MagicMock(name='get_script')
        self.actor._get_script.side_effect = [helper.tornado_value(None)]

        yield self.actor._delete_script(name='test')
        self.assertFalse(self.actor.changed)

    @testing.gen_test
    def test_delete_script(self):
        fake_scr = mock.MagicMock(name='fake_script_object')
        self.actor._get_script = mock.MagicMock(name='get_script')
        self.actor._get_script.side_effect = [helper.tornado_value(fake_scr)]
        with mock.patch.object(self.actor._client,
                               'destroy_resource') as destroy:
            destroy.return_value = helper.tornado_value(1)
            yield self.actor._delete_script(name='test')
            self.assertTrue(self.actor.changed)

    @testing.gen_test
    def test_update_description(self):
        script = mock.MagicMock(name='script')
        desc = 'test desc'
        with mock.patch.object(self.actor._client,
                               'update') as update:
            update.return_value = helper.tornado_value(script)
            ret = yield self.actor._update_description(
                script=script, description=desc, params={})
            self.assertEquals(ret, script)
            self.assertTrue(self.actor.changed)
            update.assert_has_calls([mock.call(script, {})])

    @testing.gen_test
    def test_ensure_description_matches(self):
        script = mock.MagicMock(name='script')
        script.soul = {'description': 'test description'}
        self.actor._update_description = mock.MagicMock(name='update_desc')
        self.actor._update_description.side_effect = [
            helper.tornado_value(None)
        ]
        yield self.actor._ensure_description(script)
        self.assertFalse(self.actor._update_description.called)

    @testing.gen_test
    def test_ensure_description_not_matches(self):
        script = mock.MagicMock(name='script')
        script.soul = {'description': 'different desc'}
        self.actor._update_description = mock.MagicMock(name='update_desc')
        self.actor._update_description.side_effect = [
            helper.tornado_value(None)
        ]
        yield self.actor._ensure_description(script)
        self.assertTrue(self.actor._update_description.called)

    @testing.gen_test
    def test_commit(self):
        script = mock.MagicMock(name='script')
        commit_result = mock.MagicMock(name='script_result')
        commit_result.soul = {'revision': 2}
        self.client_mock.commit_resource.side_effect = [
            helper.tornado_value(commit_result)
        ]
        self.actor.log = mock.MagicMock(name='log')
        yield self.actor._commit(script, 'message')
        self.actor.log.assert_has_calls([
            mock.call.info('Committing a new revision'),
            mock.call.info('Committed revision 2')
        ])

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
            helper.tornado_value([fake_script])]

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
