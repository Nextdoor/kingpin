"""Tests for the actors.base package."""

import io
import json
import os
import logging

from tornado import gen
from tornado import httpclient
from tornado import simple_httpclient
from tornado import testing
import mock

# Unusual placement -- but we override the environment
# so that we can test that the urllib debugger works
#
# We used to reload(base) this in the test, but that causes
# unpredictable super() behavior:
#
#  http://thomas-cokelaer.info/blog/2011/09/382/
os.environ['URLLIB_DEBUG'] = '1'

from kingpin import utils
from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.actors.test.helper import mock_tornado
from kingpin.constants import REQUIRED, STATE


__author__ = 'Matt Wise <matt@nextdoor.com>'


class FakeHTTPClientClass(object):

    """Fake HTTPClient object for testing"""

    response_value = None

    @gen.coroutine
    def fetch(self, *args, **kwargs):
        self.request = args[0]
        raise gen.Return(self.response_value)


class FakeEnsurableBaseActor(base.EnsurableBaseActor):

    all_options = {
        'name': (str, REQUIRED, 'Name of thing'),
        'description': (str, None, 'Some description'),
        'unmanaged': (str, None, 'some unmanaged option')
    }

    unmanaged_options = ['unmanaged']

    @gen.coroutine
    def _precache(self):
        # Call our parent class precache.. no real need here other than for
        # unit test coverage.
        yield super(FakeEnsurableBaseActor, self)._precache()

        # These do not match -- so we'll trigger the setters
        self.state = 'absent'
        self.name = "Old name"

        # This matches the desired description on purpose.
        self.description = 'Some description'

        # Start out with no calls recorded
        self.set_state_called = False
        self.set_name_called = False
        self.set_description_called = False

        # Make it easy to check that this was called
        self._precache_called = True

    @gen.coroutine
    def _set_state(self):
        self.state = True
        self.set_state_called = True

    @gen.coroutine
    def _get_state(self):
        raise gen.Return(self.state)

    @gen.coroutine
    def _set_name(self):
        self.name = self.option('name')
        self.set_name_called = True

    @gen.coroutine
    def _get_name(self):
        raise gen.Return(self.name)

    @gen.coroutine
    def _compare_name(self):
        exist = yield self._get_name()
        new = self.option('name')
        raise gen.Return(exist == new)

    @gen.coroutine
    def _set_description(self):
        self.set_description_called = True

    @gen.coroutine
    def _get_description(self):
        raise gen.Return(self.description)


class TestBaseActor(testing.AsyncTestCase):

    @gen.coroutine
    def true(self):
        yield utils.tornado_sleep(0.01)
        raise gen.Return(True)

    @gen.coroutine
    def false(self):
        yield utils.tornado_sleep(0.01)
        raise gen.Return(False)

    def setUp(self):
        super(TestBaseActor, self).setUp()

        # Create a BaseActor object
        self.actor = base.BaseActor('Unit Test Action', {})

        # Mock out the actors ._execute() method so that we have something to
        # test
        self.actor._execute = self.true

    @testing.gen_test
    def test_user_defined_desc(self):
        self.assertEqual('Unit Test Action', str(self.actor))

    @testing.gen_test
    def test_default_desc(self):
        self.actor._desc = None
        self.assertEqual('kingpin.actors.base.BaseActor', str(self.actor))

    @testing.gen_test
    def test_timer(self):
        # Create a function and wrap it in our timer
        self.actor._execute = self.true

        # Mock out the logger so we can track it
        self.actor.log = mock.MagicMock()

        # Now call the execute() wrapper that leverages the @timer decorator.
        yield self.actor.execute()

        # Search for a logged message. Don't explicitly set the execution time
        # because some computers and compilers are slow.
        msg = 'kingpin.actors.base.BaseActor.execute() execution time'
        msg_is_in_calls = False
        for call in self.actor.log.debug.mock_calls:
            if msg in str(call):
                msg_is_in_calls = True
        self.assertEqual(msg_is_in_calls, True)

    @testing.gen_test
    def test_timeout(self):
        # Create a quick mock.. so we can track whether or not API calls were
        # actually made.
        tracker = mock.MagicMock(name='tracker')

        # Create a function and wrap it in our timeout
        @gen.coroutine
        def _execute():
            tracker.reset_mock()
            yield gen.sleep(0.2)
            tracker.call_me()

        self.actor._execute = _execute

        # Set our timeout to 2s, test should work
        self.actor._timeout = 1
        yield self.actor.timeout(_execute)
        tracker.assert_has_calls([mock.call.call_me()])

        # Now set our timeout to 500ms. Exception should be raised, and the
        # tracker should NOT be called.
        self.actor._timeout = 0.1
        with self.assertRaises(exceptions.ActorTimedOut):
            yield self.actor.timeout(_execute)

        # Set the timeout to 0, which disables it. No exception should be
        # raised
        self.actor._timeout = 0
        yield self.actor.timeout(_execute)
        self.actor_timeout = None
        yield self.actor.timeout(_execute)

    @testing.gen_test
    def test_httplib_debugging(self):
        # Get the logger now and validate that its level was set right
        requests_logger = logging.getLogger('requests.packages.urllib3')
        self.assertEqual(10, requests_logger.level)

    def test_validate_options(self):
        self.actor.all_options = {'test': (str, REQUIRED, '')}
        self.actor._options = {'a': 'b'}
        with self.assertRaises(exceptions.InvalidOptions):
            ret = self.actor._validate_options()

        self.actor.all_options = {'test': (str, REQUIRED, '')}
        self.actor._options = {'test': 'b'}
        ret = self.actor._validate_options()
        self.assertEqual(None, ret)

        self.actor.all_options = {'test': (bool, REQUIRED, '')}
        self.actor._options = {'test': 'junk_text'}
        with self.assertRaises(exceptions.InvalidOptions):
            self.actor._validate_options()

        self.actor.all_options = {'test': (str, REQUIRED, ''),
                                  'test2': (str, REQUIRED, '')}
        self.actor._options = {'test': 'b', 'test2': 'b'}
        ret = self.actor._validate_options()
        self.assertEqual(None, ret)

        # The STATE type requires either 'present' or 'absent' to be passed in.
        self.actor.all_options = {'test': (STATE, REQUIRED, '')}
        self.actor._options = {'test': 'present'}
        ret = self.actor._validate_options()
        self.assertEqual(None, ret)

        self.actor._options = {'test': 'absent'}
        ret = self.actor._validate_options()
        self.assertEqual(None, ret)

        with self.assertRaises(exceptions.InvalidOptions):
            self.actor._options = {'test': 'abse'}
            ret = self.actor._validate_options()

    def test_validation_issues(self):
        self.actor.all_options = {'needed': (str, REQUIRED, ''),
                                  'optional': (str, '', '')}

        # Requirement not satisfied
        self.actor._options = {'optional': 'b'}
        with self.assertRaises(exceptions.InvalidOptions):
            self.actor._validate_options()

        # Invalid option type:
        self.actor._options = {'needed': 1, 'optional': 'b'}
        with self.assertRaises(exceptions.InvalidOptions):
            self.actor._validate_options()

        # Unexpected option passed
        self.actor._options = {'needed': 'a', 'unexpected': 'b'}
        # Should work w/out raising an exception.
        self.actor._validate_options()

    def test_validate_defaults(self):
        # Default is not a permitted type
        self.actor.all_options = {'name': (str, False, 'String!')}
        self.actor._setup_defaults()
        with self.assertRaises(exceptions.InvalidOptions):
            self.actor._validate_options()

    @testing.gen_test
    def test_option(self):
        self.actor._options['foo'] = 'bar'
        opt = self.actor.option('foo')
        self.assertEqual(opt, 'bar')

    def test_readfile(self):
        with self.assertRaises(exceptions.InvalidOptions):
            self.actor.readfile('notfound')

        open_patcher = mock.patch('%s.open' % self.actor.__module__,
                                  create=True)
        with open_patcher as mock_open:
            self.actor.readfile('somefile')
            self.assertEqual(mock_open.call_count, 1)
            # using __enter__ here because it's opened as a context manager.
            self.assertEqual(mock_open().__enter__().read.call_count, 1)

    @testing.gen_test
    def test_execute(self):
        res = yield self.actor.execute()
        self.assertEqual(res, True)

    def test_str2bool(self):
        self.assertEqual(True, self.actor.str2bool('true'))
        self.assertEqual(True, self.actor.str2bool('junk text'))
        self.assertEqual(True, self.actor.str2bool('1'))
        self.assertEqual(True, self.actor.str2bool(True))
        self.assertEqual(False, self.actor.str2bool('false'))
        self.assertEqual(False, self.actor.str2bool('0'))
        self.assertEqual(False, self.actor.str2bool(False))

    def test_str2bool_strict(self):
        self.assertEqual(True, self.actor.str2bool('true'))
        self.assertEqual(False, self.actor.str2bool(False))
        with self.assertRaises(exceptions.InvalidOptions):
            self.actor.str2bool('Junk', strict=True)

    @testing.gen_test
    def test_check_condition(self):
        conditions = {
            'FOobar': True,
            'True': True,
            'TRUE': True,
            1: True,
            '1': True,
            0: False,
            '0': False,
            'False': False,
            'FALSE': False,
        }
        for value, should_execute in list(conditions.items()):
            self.actor._condition = value
            self.actor._execute = mock_tornado()
            yield self.actor.execute()
            str_value = json.dumps(value)
            if should_execute:
                self.assertEqual(
                    self.actor._execute._call_count, 1,
                    'Value `%s` should allow actor execution' % str_value)
            else:
                self.assertEqual(
                    self.actor._execute._call_count, 0,
                    'Value `%s` should not allow actor execution' % str_value)

    @testing.gen_test
    def test_execute_fail(self):
        self.actor._execute = self.false
        res = yield self.actor.execute()
        self.assertEqual(res, False)

    @testing.gen_test
    def test_execute_catches_expected_exception(self):
        @gen.coroutine
        def raise_exc():
            raise exceptions.ActorException('Test')

        self.actor._execute = raise_exc
        with self.assertRaises(exceptions.ActorException):
            yield self.actor.execute()

    @testing.gen_test
    def test_execute_catches_unexpected_exception(self):
        @gen.coroutine
        def raise_exc():
            raise Exception('Test')

        self.actor._execute = raise_exc
        with self.assertRaises(exceptions.ActorException):
            yield self.actor.execute()

    @testing.gen_test
    def test_execute_with_warn_on_failure(self):
        @gen.coroutine
        def raise_exc():
            raise exceptions.RecoverableActorFailure('should just warn')

        self.actor._execute = raise_exc

        # First test, should raise an exc...
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor.execute()

        # Second test, turn on 'warn_on_failure'
        self.actor._warn_on_failure = True
        res = yield self.actor.execute()
        self.assertEqual(res, None)

    def test_fill_in_contexts_desc(self):
        base.BaseActor.all_options = {
            'test_opt': (str, REQUIRED, 'Test option')
        }

        self.actor = base.BaseActor(
            desc='Unit Test Action - {NAME}',
            options={'test_opt': 'Foo bar'},
            condition='{NAME}',
            init_context={'NAME': 'TEST'})
        self.assertEqual('Unit Test Action - TEST', self.actor._desc)
        self.assertEqual('TEST', self.actor._condition)

        with self.assertRaises(exceptions.InvalidOptions):
            self.actor = base.BaseActor(
                desc='Unit Test Action',
                options={'test_opt': 'Foo {BAZ} bar'},
                init_context={})

        with self.assertRaises(exceptions.InvalidOptions):
            self.actor = base.BaseActor(
                desc='Unit Test Action - {NAME}',
                options={},
                init_context={})

        with self.assertRaises(exceptions.InvalidOptions):
            self.actor = base.BaseActor(
                desc='Unit Test Action',
                options={'test_opt': 'Foo bar'},
                condition='{NAME}',
                init_context={})

        # Reset the all options so we dont break other tests
        base.BaseActor.all_options = {}

    def test_fill_in_contexts_options(self):
        base.BaseActor.all_options = {
            'test_opt': (str, REQUIRED, 'Test option')
        }

        self.actor = base.BaseActor(
            desc='Unit Test Action',
            options={'test_opt': 'Foo bar - {NAME}'},
            init_context={'NAME': 'TEST'})
        self.assertEqual('Foo bar - TEST', self.actor.option('test_opt'))

        # Reset the all options so we dont break other tests
        base.BaseActor.all_options = {}

    def test_fill_in_contexts_options_escape(self):
        base.BaseActor.all_options = {
            'test_opt': (str, REQUIRED, 'Test option')
        }

        self.actor = base.BaseActor(
            desc='Unit Test Action',
            options={'test_opt': 'Foo bar - \{NAME\}'},
            init_context={'NAME': 'TEST'})
        self.assertEqual('Foo bar - {NAME}', self.actor.option('test_opt'))

        # Reset the all options so we dont break other tests
        base.BaseActor.all_options = {}


class TestEnsurableBaseActor(testing.AsyncTestCase):

    def setUp(self):
        super(TestEnsurableBaseActor, self).setUp()
        self.actor = FakeEnsurableBaseActor(
            'Unit Test Actor',
            {'name': 'new name',
             'state': 'present',
             'unmanaged': 'nothing happens with this',
             'description': 'Some description'})

    @testing.gen_test
    def test_precache(self):
        yield self.actor._precache()

    @testing.gen_test
    def test_execute(self):
        yield self.actor._execute()

        # Did the precache execute?
        self.assertTrue(self.actor._precache_called)

        # First test -- the description should have matched, so
        # we should not have called self._set_description().
        self.assertFalse(self.actor.set_description_called)

        # We _should_ have called the setters for the state, and
        # for the name.
        self.assertTrue(self.actor.set_state_called)
        self.assertTrue(self.actor.set_name_called)

    @testing.gen_test
    def test_execute_absent(self):
        self.actor._options['state'] = 'absent'
        yield self.actor._execute()

        # Make sure that the set_name and set_state were NOT called
        self.assertFalse(self.actor.set_state_called)
        self.assertFalse(self.actor.set_name_called)

    @testing.gen_test
    def test_gather_methods_throws_exception(self):
        # Mock out the set_name method by replacing it with an attribute
        self.actor._set_name = False
        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            self.actor._gather_methods()


class TestHTTPBaseActor(testing.AsyncTestCase):

    def setUp(self):
        super(TestHTTPBaseActor, self).setUp()
        self.actor = base.HTTPBaseActor('Unit Test Action', {})

    @testing.gen_test
    def test_get_http_client(self):
        ret = self.actor._get_http_client()
        self.assertEqual(simple_httpclient.SimpleAsyncHTTPClient, type(ret))

    def test_get_method(self):
        self.assertEqual('POST', self.actor._get_method('foobar'))
        self.assertEqual('POST', self.actor._get_method('True'))
        self.assertEqual('POST', self.actor._get_method(''))
        self.assertEqual('GET', self.actor._get_method(None))

    @testing.gen_test
    def test_generate_escaped_url(self):
        result = self.actor._generate_escaped_url('http://unittest',
                                                  {'foo': 'bar'})
        self.assertEqual('http://unittest?foo=bar', result)

        result = self.actor._generate_escaped_url('http://unittest',
                                                  {'foo': True})
        self.assertEqual('http://unittest?foo=true', result)

        result = self.actor._generate_escaped_url(
            'http://unittest',
            {'foo': 'bar', 'xyz': 'abc'})
        self.assertEqual('http://unittest?foo=bar&xyz=abc', result)

        result = self.actor._generate_escaped_url(
            'http://unittest',
            {'foo': 'bar baz', 'xyz': 'abc'})
        self.assertEqual('http://unittest?foo=bar+baz&xyz=abc', result)

    @testing.gen_test
    def test_fetch(self):
        # Test with valid JSON
        response_dict = {'foo': 'asdf'}
        response_body = json.dumps(response_dict)
        http_response = httpclient.HTTPResponse(
            httpclient.HTTPRequest('/'), code=200,
            buffer=io.StringIO(response_body))

        with mock.patch.object(self.actor, '_get_http_client') as m:
            m.return_value = FakeHTTPClientClass()
            m.return_value.response_value = http_response

            response = yield self.actor._fetch('/')
            self.assertEqual(response_dict, response)

        # Test with completely invalid JSON
        response_body = "Something bad happened"
        http_response = httpclient.HTTPResponse(
            httpclient.HTTPRequest('/'), code=200,
            buffer=io.StringIO(response_body))

        with mock.patch.object(self.actor, '_get_http_client') as m:
            m.return_value = FakeHTTPClientClass()
            m.return_value.response_value = http_response

            with self.assertRaises(exceptions.UnparseableResponseFromEndpoint):
                yield self.actor._fetch('/')

    @testing.gen_test
    def test_fetch_with_auth(self):
        response_dict = {'foo': 'asdf'}
        response_body = json.dumps(response_dict)
        http_response = httpclient.HTTPResponse(
            httpclient.HTTPRequest('/'), code=200,
            buffer=io.StringIO(response_body))

        with mock.patch.object(self.actor, '_get_http_client') as m:
            m.return_value = FakeHTTPClientClass()
            m.return_value.response_value = http_response

            yield self.actor._fetch('/', auth_username='foo',
                                    auth_password='bar')
            self.assertEqual(m.return_value.request.auth_username, 'foo')
            self.assertEqual(m.return_value.request.auth_password, 'bar')


class TestActualEnsurableBaseActor(testing.AsyncTestCase):

    def setUp(self):

        super(TestActualEnsurableBaseActor, self).setUp()
        self.actor = base.EnsurableBaseActor(
            'Unit Test Actor',
            {'name': 'new name',
             'state': 'present',
             'unmanaged': 'nothing happens with this',
             'description': 'Some description'})

    @testing.gen_test
    def test_set_state(self):
        with self.assertRaises(NotImplementedError):
            yield self.actor._set_state()

    @testing.gen_test
    def test_get_state(self):
        with self.assertRaises(NotImplementedError):
            yield self.actor._get_state()
