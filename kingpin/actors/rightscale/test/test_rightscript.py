import logging
import mock

from tornado import testing

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
                'packages': 'curl',
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
    def test_precache(self):
        fake_script = mock.MagicMock(name='FakeScript')
        fake_script.soul = {'name': 'FakeScript'}

        # Now create a fake Rightscale resource collection object and make sure
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(fake_script)]
        self.client_mock.make_generic_request.side_effect = [
            helper.tornado_value('test script')]
        yield self.actor._precache()
        self.assertEquals(fake_script, self.actor.script)
        self.assertEquals('test script', self.actor.source)

    @testing.gen_test
    def test_compare_source(self):
        self.actor.source = 'cloud source'
        ret = yield self.actor._compare_source()
        self.assertFalse(ret)

    @testing.gen_test
    def test_precache_empty(self):
        fake_script = mock.MagicMock(name='FakeScript')
        fake_script.soul = {'name': 'FakeScript'}

        # Now create a fake Rightscale resource collection object and make sure
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(None)]
        self.client_mock.make_generic_request.side_effect = [
            helper.tornado_value(None)]
        yield self.actor._precache()
        self.assertEquals(None, self.actor.script)
        self.assertEquals(None, self.actor.source)

    @testing.gen_test
    def test_set_state_absent_already_gone(self):
        self.actor.script = None
        self.actor._options['state'] = 'absent'
        yield self.actor._set_state()
        self.assertFalse(self.actor.changed)

    @testing.gen_test
    def test_set_state_absent(self):
        self.actor.script = mock.MagicMock(name='fake_script_object')
        self.actor._options['state'] = 'absent'
        with mock.patch.object(self.actor._client,
                               'destroy_resource') as destroy:
            destroy.return_value = helper.tornado_value(1)
            yield self.actor._set_state()
            self.assertTrue(self.actor.changed)

    @testing.gen_test
    def test_set_state_present(self):
        with mock.patch.object(self.actor._client,
                               'create_resource') as create:
            create.return_value = helper.tornado_value(1)
            yield self.actor._set_state()
            self.assertTrue(self.actor.changed)
            self.assertEquals(self.actor.script, 1)

    @testing.gen_test
    def test_set_state_dry(self):
        self.actor._dry = True
        yield self.actor._set_state()
        self.assertTrue(self.actor.changed)
        self.assertEquals(self.actor.script, None)

    @testing.gen_test
    def test_set_source(self):
        self.actor._update_params = mock.MagicMock()
        self.actor._update_params.side_effect = [
            helper.tornado_value(None)]
        yield self.actor._set_source()
        self.assertTrue(self.actor._update_params.called)

    @testing.gen_test
    def test_set_description(self):
        self.actor._update_params = mock.MagicMock()
        self.actor._update_params.side_effect = [
            helper.tornado_value(None)]
        yield self.actor._set_description()
        self.assertTrue(self.actor._update_params.called)

    @testing.gen_test
    def test_get_description_none(self):
        self.actor.script = None
        ret = yield self.actor._get_description()
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_get_packages_none(self):
        self.actor.script = None
        ret = yield self.actor._get_packages()
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_set_packages(self):
        self.actor._update_params = mock.MagicMock()
        self.actor._update_params.side_effect = [
            helper.tornado_value(None)]
        yield self.actor._set_packages()
        self.assertTrue(self.actor._update_params.called)

    @testing.gen_test
    def test_update_params(self):
        self.actor.script = mock.MagicMock(name='script')
        with mock.patch.object(self.actor._client,
                               'update') as update:
            update.return_value = helper.tornado_value(self.actor.script)
            yield self.actor._update_params()
            self.assertTrue(self.actor.changed)
            update.assert_called_once_with(
                self.actor.script,
                helper.InAnyOrder([('right_script[source]', 'echo script1\n'),
                                   ('right_script[packages]', u'curl'),
                                   ('right_script[description]', u'test description'),
                                   ('right_script[name]', u'test-name')]))

    @testing.gen_test
    def test_commit(self):
        self.actor.script = mock.MagicMock(name='script')
        commit_result = mock.MagicMock(name='script_result')
        commit_result.soul = {'revision': 2}
        self.client_mock.commit_resource.side_effect = [
            helper.tornado_value(commit_result)
        ]
        self.actor.log = mock.MagicMock(name='log')
        yield self.actor._commit()
        self.actor.log.assert_has_calls([
            mock.call.info('Committing a new revision'),
            mock.call.info('Committed revision 2')
        ])

    @testing.gen_test
    def test_execute_present(self):
        self.actor.changed = True

        self.actor.script = mock.MagicMock()
        self.actor.script.soul = {
            'name': 'test-script',
            'description': 'test description',
            'packages': 'curl'
        }
        self.actor.source = 'echo script1\n'
        self.actor._precache = helper.mock_tornado(None)
        self.actor._commit = helper.mock_tornado(None)

        yield self.actor._execute()

    @testing.gen_test
    def test_execute_absent(self):
        self.actor._options['state'] = 'absent'

        self.actor.script = None
        self.actor.source = None
        self.actor._precache = helper.mock_tornado(None)

        yield self.actor._execute()
