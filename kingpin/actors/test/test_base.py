"""Tests for the actors.base package."""
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
    def test_httplib_debugging(self):
        # Override the environment setting and reload the class
        os.environ['URLLIB_DEBUG'] = '1'
        reload(base)
        # Get the logger now and validate that its level was set right
        requests_logger = logging.getLogger('requests.packages.urllib3')
        self.assertEquals(10, requests_logger.level)

    def test_validate_options(self):
        self.actor.all_options = {'test': (str, None, '')}
        self.actor._options = {'a': 'b'}
        with self.assertRaises(exceptions.InvalidOptions):
            ret = self.actor._validate_options()

        self.actor.all_options = {'test': (str, None, '')}
        self.actor._options = {'test': 'b'}
        ret = self.actor._validate_options()
        self.assertEquals(None, ret)

        self.actor.all_options = {'test': (str, None, ''),
                                  'test2': (str, None, '')}
        self.actor._options = {'test': 'b', 'test2': 'b'}
        ret = self.actor._validate_options()
        self.assertEquals(None, ret)

    def test_validation_issues(self):
        self.actor.all_options = {'needed': (str, None, ''),
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

    @testing.gen_test
    def test_execute(self):
        res = yield self.actor.execute()
        self.assertEquals(res, True)

    @testing.gen_test
    def test_execute_fail(self):
        self.actor._execute = self.false
        res = yield self.actor.execute()
        self.assertEquals(res, False)

    @testing.gen_test
    def test_execute_fail_with_warn_on_failure(self):
        self.actor._execute = self.false
        self.actor._warn_on_failure = True
        res = yield self.actor.execute()
        self.assertEquals(res, True)

    @testing.gen_test
    def test_execute_catches_expected_exception(self):
        @gen.coroutine
        def raise_exc():
            raise exceptions.ActorException('Test')

        self.actor._execute = raise_exc
        res = yield self.actor.execute()
        self.assertEquals(res, False)

    @testing.gen_test
    def test_execute_catches_unexpected_exception(self):
        @gen.coroutine
        def raise_exc():
            raise Exception('Test')

        self.actor._execute = raise_exc
        res = yield self.actor.execute()
        self.assertEquals(res, False)


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
        self.assertEquals('http://unittest?xyz=abc&foo=bar', result)

        result = self.actor._generate_escaped_url(
            'http://unittest',
            {'foo': 'bar baz', 'xyz': 'abc'})
        self.assertEquals('http://unittest?xyz=abc&foo=bar+baz', result)

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
