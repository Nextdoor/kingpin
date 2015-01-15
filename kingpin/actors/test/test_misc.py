import logging

from tornado import httpclient
from tornado import testing
import mock

from kingpin.actors import exceptions
from kingpin.actors import misc
from kingpin.actors.test.helper import mock_tornado

log = logging.getLogger(__name__)


class TestMacro(testing.AsyncTestCase):

    def setUp(self):
        super(TestMacro, self).setUp()
        reload(misc)

    def test_init(self):
        misc.Macro._check_macro = mock.Mock()
        misc.Macro._get_macro = mock.Mock(return_value='unit-test-macro')

        with mock.patch('kingpin.utils.convert_json_to_dict') as j2d, \
                mock.patch('kingpin.schema.validate') as schema_validate, \
                mock.patch('kingpin.actors.utils.get_actor') as get_actor:

            j2d.return_value = {
                'desc': 'unit test',
                'actor': 'unit test',
                'options': {}
            }

            actor = misc.Macro('Unit Test', {'macro': 'test.json',
                                             'tokens': {}})

            j2d.assert_called_with(json_file='unit-test-macro', tokens={})
            self.assertEquals(schema_validate.call_count, 1)
            self.assertEquals(actor.initial_actor, get_actor())

    def test_init_remote(self):
        misc.Macro._get_config_from_json = mock.Mock()
        misc.Macro._check_schema = mock.Mock()
        with mock.patch('kingpin.actors.utils.get_actor'):
            with mock.patch.object(httpclient.HTTPClient, 'fetch'):
                misc.Macro('Unit Test', {'macro': 'http://test.json',
                                         'tokens': {}})

    def test_init_dry(self):
        misc.Macro._check_macro = mock.Mock()
        misc.Macro._get_config_from_json = mock.Mock()
        misc.Macro._check_schema = mock.Mock()

        with mock.patch('kingpin.utils.convert_json_to_dict') as j2d, \
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
        with mock.patch('kingpin.utils.convert_json_to_dict') as j2d:
            j2d.return_value = {
                'desc': 'unit test',
                'options': {}  # `actor` keyword is missing
            }

            with self.assertRaises(exceptions.UnrecoverableActorFailure):
                misc.Macro('Unit Test', {'macro': 'test.json',
                                         'tokens': {}})

        # JSON syntax error
        with mock.patch('kingpin.utils.convert_json_to_dict') as j2d:

            j2d.side_effect = Exception('Something failed with JSON')

            with self.assertRaises(exceptions.UnrecoverableActorFailure):
                misc.Macro('Unit Test', {'macro': 'test.json',
                                         'tokens': {}})

    @testing.gen_test
    def test_execute(self):

        misc.Macro._check_macro = mock.Mock()
        misc.Macro._get_macro = mock.Mock()
        misc.Macro._get_config_from_json = mock.Mock()
        misc.Macro._check_schema = mock.Mock()

        with mock.patch('kingpin.actors.utils.get_actor') as get_actor:
            actor = misc.Macro('Unit Test', {'macro': 'test.json',
                                             'tokens': {}},
                               dry=True)

            get_actor().execute = mock_tornado()
            yield actor._execute()

            self.assertEquals(get_actor().execute._call_count, 1)


class TestSleep(testing.AsyncTestCase):

    @testing.gen_test
    def test_execute(self):
        # Call the executor and test it out
        actor = misc.Sleep('Unit Test Action', {'sleep': 0.1})
        res = yield actor.execute()

        # Make sure we fired off an alert.
        self.assertEquals(res, None)

    @testing.gen_test
    def test_execute_with_str(self):
        # Call the executor and test it out
        actor = misc.Sleep('Unit Test Action', {'sleep': '0.5'})
        res = yield actor.execute()

        # Make sure we fired off an alert.
        self.assertEquals(res, None)


class TestGenericHTTP(testing.AsyncTestCase):

    @testing.gen_test
    def test_execute_dry(self):
        actor = misc.GenericHTTP('Unit Test Action',
                                 {'url': 'http://example.com'},
                                 dry=True)

        actor._fetch = mock_tornado()

        yield actor.execute()

        self.assertEquals(actor._fetch._call_count, 0)

    @testing.gen_test
    def test_execute(self):
        actor = misc.GenericHTTP('Unit Test Action',
                                 {'url': 'http://example.com'})
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
