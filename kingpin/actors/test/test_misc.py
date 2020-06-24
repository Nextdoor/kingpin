import logging

from tornado import httpclient
from tornado import testing
import mock

from kingpin import exceptions as kingpin_exceptions
from kingpin.actors import exceptions
from kingpin.actors import misc
from kingpin.actors.test.helper import mock_tornado
import importlib

log = logging.getLogger(__name__)


class TestNote(testing.AsyncTestCase):

    @testing.gen_test
    def test_log(self):
        note = misc.Note('Test', {'message': 'Hello World'})
        note.log = mock.Mock()
        yield note._execute()
        self.assertEqual(note.log.info.call_count, 1)


class TestMacro(testing.AsyncTestCase):

    def setUp(self):
        super(TestMacro, self).setUp()
        importlib.reload(misc)

    def test_init(self):
        misc.Macro._check_macro = mock.Mock()
        misc.Macro._get_macro = mock.Mock(return_value='unit-test-macro')

        with mock.patch('kingpin.utils.convert_script_to_dict') as j2d, \
                mock.patch('kingpin.schema.validate') as schema_validate, \
                mock.patch('kingpin.actors.utils.get_actor') as get_actor:

            j2d.return_value = {
                'desc': 'unit test',
                'actor': 'unit test',
                'options': {}
            }

            actor = misc.Macro('Unit Test', {'macro': 'test.json',
                                             'tokens': {}},
                               init_tokens={})

            j2d.assert_called_with(script_file='unit-test-macro', tokens={})
            self.assertEqual(schema_validate.call_count, 1)
            self.assertEqual(actor.initial_actor, get_actor())

    def test_init_nested_tokens(self):
        # Quick test to ensure that a series of nested groups and macro actors
        # will pass supplied tokens all the way down to their sub actors.

        # Generate a single outer actor. This actor will create many internal
        # actors.
        init_tokens = {'SLEEP': 0}
        actor = misc.Macro(
            options={'macro': 'examples/misc.macro/outer_group.yaml'},
            init_tokens=init_tokens)

        # Ensure that the initial misc.Macro actor, and the initial actor it
        # created (from outer_group.yaml) both have the appropriate init
        # tokens. This helps ensure that we used .copy() properly a well as the
        # fact that the tokens were passed down appropriately.
        self.assertEqual(actor._init_tokens, init_tokens)
        self.assertEqual(actor.initial_actor._init_tokens, init_tokens)

        # Ensure that the nested misc.Macro actor from outer_macro.yaml got
        # init_tokens, AND the 'FOO' token from outer_group.yaml's own
        # definition.
        self.assertEqual(actor.initial_actor._actions[0]._init_tokens,
                         {'SLEEP': 0, 'FOO': 'weee'})

        # Next ensure that the mostly nested examples/misc.macro/inner.yaml
        # actor got the SLEEP, FOO, and DESC tokens.
        self.assertEqual(
            actor.initial_actor._actions[0].initial_actor._init_tokens,
            {'SLEEP': 0, 'FOO': 'weee', 'DESC': 'Sleeping for a while'})

        # Finally, ensure the super nested
        s = actor.initial_actor._actions[0].initial_actor.initial_actor
        self.assertEqual(
            s._init_tokens,
            {'SLEEP': 0, 'FOO': 'weee', 'DESC': 'Sleeping for a while'})

    def test_init_group(self):
        misc.Macro._check_macro = mock.Mock()
        misc.Macro._get_macro = mock.Mock(return_value='unit-test-macro')

        with mock.patch('kingpin.utils.convert_script_to_dict') as j2d, \
                mock.patch('kingpin.schema.validate') as schema_validate, \
                mock.patch('kingpin.actors.group.Sync') as sync_actor:

            j2d.return_value = [{
                'desc': 'unit test',
                'actor': 'unit test',
                'options': {}
            }]

            actor = misc.Macro('Unit Test', {'macro': 'test.json'})

            j2d.assert_called_with(script_file='unit-test-macro', tokens={})
            self.assertEqual(schema_validate.call_count, 1)
            self.assertEqual(actor.initial_actor, sync_actor())

    def test_init_remote(self):
        misc.Macro._get_config_from_script = mock.Mock()
        misc.Macro._get_config_from_script.return_value = {}
        misc.Macro._check_schema = mock.Mock()
        with mock.patch('kingpin.actors.utils.get_actor'):
            with mock.patch.object(httpclient.HTTPClient, 'fetch') as fetch:
                fetch.return_value.body = "foo"
                misc.Macro('Unit Test', {'macro': 'http://test.json',
                                         'tokens': {}})

    def test_init_dry(self):
        misc.Macro._check_macro = mock.Mock()
        misc.Macro._get_config_from_script = mock.Mock()
        misc.Macro._get_config_from_script.return_value = {}
        misc.Macro._check_schema = mock.Mock()

        with mock.patch('kingpin.utils.convert_script_to_dict') as j2d, \
                mock.patch('kingpin.schema.validate'), \
                mock.patch('kingpin.actors.utils.get_actor'):
            j2d.return_value = {
                'desc': 'unit test',
                'actor': 'unit test',
                'options': {}
            }

            actor = misc.Macro('Unit Test',
                               {'macro': 'examples/test/sleep.json',
                                'tokens': {}},
                               dry=True)

            self.assertTrue(actor.initial_actor._dry)

    def test_init_with_errors(self):

        # Remote files are prohibited for now
        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            misc.Macro('Unit Test', {'macro': 'ftp://fail.test.json',
                                     'tokens': {}})

        # Remote file with bad URL
        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            misc.Macro('Unit Test', {'macro': 'http://fail.test.json',
                                     'tokens': {}})

        # Non-existent file
        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            misc.Macro('Unit Test', {'macro': 'dontcreatethis.json',
                                     'tokens': {}})

        # We don't want the rest of the tests failing on downloading this file.
        misc.Macro._get_macro = mock.Mock(return_value='unit-test-file')

        # Schema failure
        with mock.patch('kingpin.utils.convert_script_to_dict') as j2d:
            j2d.return_value = {
                'desc': 'unit test',
                'options': {}  # `actor` keyword is missing
            }

            with self.assertRaises(exceptions.UnrecoverableActorFailure):
                misc.Macro('Unit Test', {'macro': 'test.json',
                                         'tokens': {}})

        # JSON syntax error
        with mock.patch('kingpin.utils.convert_script_to_dict') as j2d:

            j2d.side_effect = kingpin_exceptions.InvalidScript('Fail!')

            with self.assertRaises(exceptions.UnrecoverableActorFailure):
                misc.Macro('Unit Test', {'macro': 'test.json',
                                         'tokens': {}})

    @testing.gen_test
    def test_execute(self):

        misc.Macro._check_macro = mock.Mock()
        misc.Macro._get_macro = mock.Mock()
        misc.Macro._get_config_from_script = mock.Mock()
        misc.Macro._get_config_from_script.return_value = {}
        misc.Macro._check_schema = mock.Mock()

        with mock.patch('kingpin.actors.utils.get_actor') as get_actor:
            actor = misc.Macro('Unit Test', {'macro': 'test.json',
                                             'tokens': {}},
                               dry=True)

            get_actor().execute = mock_tornado()
            yield actor._execute()

            self.assertEqual(get_actor().execute._call_count, 1)

    @testing.gen_test
    def test_orgchart(self):

        misc.Macro._get_macro = mock.Mock(name='unittestmacro')
        misc.Macro._get_config_from_script = mock.Mock(
            return_value=[{'actor': 'misc.Sleep', 'options': {'sleep': 0}}]
        )
        actor = misc.Macro('Unit test', {'macro': 'test'})

        self.assertEqual(len(actor.get_orgchart()), 3)  # Macro, Group, Sleep
        self.assertEqual(type(actor.get_orgchart()[0]), dict)


class TestSleep(testing.AsyncTestCase):

    @testing.gen_test
    def test_execute(self):
        # Call the executor and test it out
        actor = misc.Sleep('Unit Test Action', {'sleep': 0.1})
        res = yield actor.execute()

        # Make sure we fired off an alert.
        self.assertEqual(res, None)

    @testing.gen_test
    def test_execute_with_str(self):
        # Call the executor and test it out
        actor = misc.Sleep('Unit Test Action', {'sleep': '0.5'})
        res = yield actor.execute()

        # Make sure we fired off an alert.
        self.assertEqual(res, None)


class TestGenericHTTP(testing.AsyncTestCase):

    @testing.gen_test
    def test_execute_dry(self):
        actor = misc.GenericHTTP('Unit Test Action',
                                 {'url': 'http://example.com'},
                                 dry=True)

        actor._fetch = mock_tornado()

        yield actor.execute()

        self.assertEqual(actor._fetch._call_count, 0)

    @testing.gen_test
    def test_execute(self):
        actor = misc.GenericHTTP('Unit Test Action',
                                 {'url': 'http://example.com'})
        actor._fetch = mock_tornado({'success': {'code': 200}})

        yield actor.execute()

    @testing.gen_test
    def test_execute_data_json(self):
        actor = misc.GenericHTTP('Unit Test Action',
                                 {'url': 'http://example.com',
                                  'data-json': {'foo': 'bar'}})
        actor._fetch = mock_tornado({'success': {'code': 200}})

        yield actor.execute()

    @testing.gen_test
    def test_execute_fail(self):
        actor = misc.GenericHTTP('Unit Test Action',
                                 {'url': 'http://example.com'})
        error = httpclient.HTTPError(code=401, response={})
        actor._fetch = mock_tornado(exc=error)

        with self.assertRaises(exceptions.InvalidCredentials):
            yield actor.execute()
