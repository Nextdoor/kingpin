"""Tests for the actors.base package."""
from __future__ import absolute_import
import StringIO
import json
import os
import logging

from tornado import gen
from tornado import httpclient
from tornado import simple_httpclient
from tornado import testing
import mock

from kingpin import utils
from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.actors.test.helper import mock_tornado
from kingpin.constants import REQUIRED


__author__ = 'Matt Wise <matt@nextdoor.com>'


class FakeHTTPClientClass(object):

    """Fake HTTPClient object for testing"""

    response_value = None

    @gen.coroutine
    def fetch(self, *args, **kwargs):
        self.request = args[0]
        raise gen.Return(self.response_value)


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
        self.assertEquals(msg_is_in_calls, True)

    @testing.gen_test
    def test_httplib_debugging(self):
        # Override the environment setting and reload the class
        os.environ['URLLIB_DEBUG'] = '1'
        reload(base)
        # Get the logger now and validate that its level was set right
        requests_logger = logging.getLogger('requests.packages.urllib3')
        self.assertEquals(10, requests_logger.level)

    def test_validate_options(self):
        self.actor.all_options = {'test': (str, REQUIRED, '')}
        self.actor._options = {'a': 'b'}
        with self.assertRaises(exceptions.InvalidOptions):
            ret = self.actor._validate_options()

        self.actor.all_options = {'test': (str, REQUIRED, '')}
        self.actor._options = {'test': 'b'}
        ret = self.actor._validate_options()
        self.assertEquals(None, ret)

        self.actor.all_options = {'test': (str, REQUIRED, ''),
                                  'test2': (str, REQUIRED, '')}
        self.actor._options = {'test': 'b', 'test2': 'b'}
        ret = self.actor._validate_options()
        self.assertEquals(None, ret)

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
        with self.assertRaises(exceptions.InvalidOptions):
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
        self.assertEquals(opt, 'bar')

    def test_readfile(self):
        with self.assertRaises(exceptions.InvalidOptions):
            self.actor.readfile('notfound')

        open_patcher = mock.patch('%s.open' % self.actor.__module__,
                                  create=True)
        with open_patcher as mock_open:
            self.actor.readfile('somefile')
            self.assertEquals(mock_open.call_count, 1)
            # using __enter__ here because it's opened as a context manager.
            self.assertEquals(mock_open().__enter__().read.call_count, 1)

    @testing.gen_test
    def test_execute(self):
        res = yield self.actor.execute()
        self.assertEquals(res, True)

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
        for value, should_execute in conditions.items():
            self.actor._condition = value
            self.actor._execute = mock_tornado()
            yield self.actor.execute()
            str_value = json.dumps(value)
            if should_execute:
                self.assertEquals(
                    self.actor._execute._call_count, 1,
                    'Value `%s` should allow actor execution' % str_value)
            else:
                self.assertEquals(
                    self.actor._execute._call_count, 0,
                    'Value `%s` should not allow actor execution' % str_value)

    @testing.gen_test
    def test_execute_fail(self):
        self.actor._execute = self.false
        res = yield self.actor.execute()
        self.assertEquals(res, False)

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
        self.assertEquals(res, None)

    def test_fill_in_contexts_desc(self):
        base.BaseActor.all_options = {
            'test_opt': (str, REQUIRED, 'Test option')
        }

        self.actor = base.BaseActor(
            desc='Unit Test Action - {NAME}',
            options={'test_opt': 'Foo bar'},
            init_context={'NAME': 'TEST'})
        self.assertEquals('Unit Test Action - TEST', self.actor._desc)

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

        # Reset the all options so we dont break other tests
        base.BaseActor.all_options = {}


class TestHTTPBaseActor(testing.AsyncTestCase):

    def setUp(self):
        super(TestHTTPBaseActor, self).setUp()
        self.actor = base.HTTPBaseActor('Unit Test Action', {})

    @testing.gen_test
    def test_get_http_client(self):
        ret = self.actor._get_http_client()
        self.assertEquals(simple_httpclient.SimpleAsyncHTTPClient, type(ret))

    def test_get_method(self):
        self.assertEquals('POST', self.actor._get_method('foobar'))
        self.assertEquals('POST', self.actor._get_method('True'))
        self.assertEquals('POST', self.actor._get_method(''))
        self.assertEquals('GET', self.actor._get_method(None))

    @testing.gen_test
    def test_generate_escaped_url(self):
        result = self.actor._generate_escaped_url('http://unittest',
                                                  {'foo': 'bar'})
        self.assertEquals('http://unittest?foo=bar', result)

        result = self.actor._generate_escaped_url('http://unittest',
                                                  {'foo': True})
        self.assertEquals('http://unittest?foo=true', result)

        result = self.actor._generate_escaped_url(
            'http://unittest',
            {'foo': 'bar', 'xyz': 'abc'})
        self.assertEquals('http://unittest?foo=bar&xyz=abc', result)

        result = self.actor._generate_escaped_url(
            'http://unittest',
            {'foo': 'bar baz', 'xyz': 'abc'})
        self.assertEquals('http://unittest?foo=bar+baz&xyz=abc', result)

    @testing.gen_test
    def test_fetch(self):
        # Test with valid JSON
        response_dict = {'foo': 'asdf'}
        response_body = json.dumps(response_dict)
        http_response = httpclient.HTTPResponse(
            httpclient.HTTPRequest('/'), code=200,
            buffer=StringIO.StringIO(response_body))

        with mock.patch.object(self.actor, '_get_http_client') as m:
            m.return_value = FakeHTTPClientClass()
            m.return_value.response_value = http_response

            response = yield self.actor._fetch('/')
            self.assertEquals(response_dict, response)

        # Test with completely invalid JSON
        response_body = "Something bad happened"
        http_response = httpclient.HTTPResponse(
            httpclient.HTTPRequest('/'), code=200,
            buffer=StringIO.StringIO(response_body))

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
            buffer=StringIO.StringIO(response_body))

        with mock.patch.object(self.actor, '_get_http_client') as m:
            m.return_value = FakeHTTPClientClass()
            m.return_value.response_value = http_response

            yield self.actor._fetch('/', auth_username='foo',
                                    auth_password='bar')
            self.assertEquals(m.return_value.request.auth_username,
                              'foo')
            self.assertEquals(m.return_value.request.auth_password,
                              'bar')
