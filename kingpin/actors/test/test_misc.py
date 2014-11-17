import logging

from tornado import httpclient
from tornado import testing
import demjson
import mock

from kingpin import exceptions as kingpin_exceptions
from kingpin.actors import exceptions
from kingpin.actors import misc
from kingpin.actors.test.helper import mock_tornado

log = logging.getLogger(__name__)


class TestMacro(testing.AsyncTestCase):

    def test_init(self):

        with mock.patch('kingpin.utils.convert_json_to_dict') as j2d, \
                mock.patch('kingpin.schema.validate') as schema_validate, \
                mock.patch('kingpin.actors.utils.get_actor') as get_actor:

            j2d.return_value = {
                'desc': 'unit test',
                'actor': 'unit test',
                'options': {}
                }

            actor = misc.Macro('Unit Test', {'file': 'test.json',
                                             'tokens': {}})

            j2d.assert_called_with(json_file='test.json', tokens={})
            self.assertEquals(schema_validate.call_count, 1)
            self.assertEquals(actor.initial_actor, get_actor())

    def test_init_dry(self):

        with mock.patch('kingpin.utils.convert_json_to_dict') as j2d, \
                mock.patch('kingpin.schema.validate'), \
                mock.patch('kingpin.actors.utils.get_actor'):
            j2d.return_value = {
                'desc': 'unit test',
                'actor': 'unit test',
                'options': {}
                }

            actor = misc.Macro('Unit Test', {'file': 'test.json',
                                             'tokens': {}},
                               dry=True)

            self.assertTrue(actor.initial_actor._dry)

    def test_init_with_errors(self):

        with mock.patch('kingpin.utils.convert_json_to_dict') as j2d, \
                mock.patch('kingpin.actors.utils.get_actor'):
            j2d.return_value = {
                'desc': 'unit test',
                'options': {}  # `actor` keyword is missing
                }

            with self.assertRaises(exceptions.UnrecoverableActorFailure):
                misc.Macro('Unit Test', {'file': 'test.json',
                                         'tokens': {}})

            j2d.side_effect = kingpin_exceptions.InvalidEnvironment('test')

            with self.assertRaises(exceptions.UnrecoverableActorFailure):
                misc.Macro('Unit Test', {'file': 'test.json',
                                         'tokens': {}})

            j2d.side_effect = demjson.JSONDecodeError('test')

            with self.assertRaises(exceptions.UnrecoverableActorFailure):
                misc.Macro('Unit Test', {'file': 'test.json',
                                         'tokens': {}})

    @testing.gen_test
    def test_execute(self):

        with mock.patch('kingpin.utils.convert_json_to_dict') as j2d, \
                mock.patch('kingpin.schema.validate'), \
                mock.patch('kingpin.actors.utils.get_actor') as get_actor:
            j2d.return_value = {
                'desc': 'unit test',
                'actor': 'unit test',
                'options': {}
                }

            actor = misc.Macro('Unit Test', {'file': 'test.json',
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
