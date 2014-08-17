"""Tests for the actors.base package."""
import json
import time
import mock
import StringIO

from tornado import gen
from tornado import simple_httpclient
from tornado import httpclient
from tornado import testing
from tornado.ioloop import IOLoop

from kingpin.actors import base
from kingpin.actors import exceptions


__author__ = 'Matt Wise <matt@nextdoor.com>'


class FakeHTTPClientClass(object):
    """Fake HTTPClient object for testing"""
    response_value = None

    @gen.coroutine
    def fetch(self, *args, **kwargs):
        raise gen.Return(self.response_value)


class TestBaseActor(testing.AsyncTestCase):
    @gen.coroutine
    def sleep(self):
        # Basically a fake action that should take a few seconds to run for the
        # sake of the unit tests.
        yield gen.Task(IOLoop.current().add_timeout, time.time() + 0.1)
        raise gen.Return(True)

    def setUp(self):
        super(TestBaseActor, self).setUp()

        # Create a BaseActor object
        self.actor = base.BaseActor('Unit Test Action', {})

        # Mock out the actors ._execute() method so that we have something to
        # test
        self.actor._execute = self.sleep

    @testing.gen_test
    def test_execute(self):
        # Call the executor and test it out
        res = yield self.actor.execute()

        # Make sure we fired off an alert.
        self.assertEquals(res, True)


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