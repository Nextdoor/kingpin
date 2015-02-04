"""Tests for the actors.base package."""

import mock

from tornado import gen
from tornado import testing
from tornado import simple_httpclient

from kingpin.actors import exceptions
from kingpin.actors.support import api
from kingpin.actors.test.helper import tornado_value

__author__ = 'Matt Wise <matt@nextdoor.com>'


class RestClientTest(api.RestClient):

    """Fake web client object for unit tests."""

    @gen.coroutine
    def fetch(self, url, method, post={},
              auth_username=None, auth_password=None):
        # Turn all the iputs into a JSON dict and return them
        ret = {'url': url, 'method': method, 'post': post,
               'auth_username': auth_username, 'auth_password': auth_password}
        raise gen.Return(ret)


class RestConsumerTest(api.RestConsumer):

    _CONFIG = {
        'attrs': {
            'testA': {
                'path': '/testA',
                'http_methods': {
                    'get': {},
                    'post': {},
                    'put': {},
                    # Note, 'delete' specifically avoided
                }
            },
            'test_path_with_res': {
                'path': '/test/%res%/info',
                'http_methods': {'get': {}}
            }
        }
    }
    _ENDPOINT = 'http://unittest.com'


class TestRestConsumer(testing.AsyncTestCase):

    @testing.gen_test
    def test_object_attributes(self):
        test_consumer = RestConsumerTest(client=RestClientTest())
        self.assertEquals(test_consumer.__repr__(),
                          'RestConsumerTest(None)')
        self.assertEquals(test_consumer.testA().__repr__(),
                          'RestConsumerTest(/testA)')

    @testing.gen_test
    def test_replace_path_tokens(self):
        test_consumer = RestConsumerTest(client=RestClientTest())

        # with missing 'res' arg, it should fail
        with self.assertRaises(TypeError):
            test_consumer.test_path_with_res()

        # with arg, it should pass
        ret = test_consumer.test_path_with_res(res='abcd')
        self.assertEquals(str(ret), '/test/abcd/info')

    @testing.gen_test
    def test_http_method_get(self):
        test_consumer = RestConsumerTest(client=RestClientTest())
        ret = yield test_consumer.testA().http_get()
        expected_ret = {
            'url': 'http://unittest.com/testA',
            'post': {},
            'auth_password': None,
            'auth_username': None,
            'method': 'GET'}
        self.assertEquals(ret, expected_ret)

    @testing.gen_test
    def test_http_method_get_with_kwargs(self):
        test_consumer = RestConsumerTest(client=RestClientTest())
        ret = yield test_consumer.testA().http_get(foo='bar')
        expected_ret = {
            'url': 'http://unittest.com/testA?foo=bar',
            'post': {},
            'auth_password': None,
            'auth_username': None,
            'method': 'GET'}
        self.assertEquals(ret, expected_ret)

    @testing.gen_test
    def test_http_method_post(self):
        test_consumer = RestConsumerTest(client=RestClientTest())
        ret = yield test_consumer.testA().http_post()
        expected_ret = {
            'url': 'http://unittest.com/testA',
            'post': {},
            'auth_password': None,
            'auth_username': None,
            'method': 'POST'}
        self.assertEquals(ret, expected_ret)

    @testing.gen_test
    def test_http_method_put(self):
        test_consumer = RestConsumerTest(client=RestClientTest())
        ret = yield test_consumer.testA().http_put()
        expected_ret = {
            'url': 'http://unittest.com/testA',
            'post': {},
            'auth_password': None,
            'auth_username': None,
            'method': 'PUT'}
        self.assertEquals(ret, expected_ret)

    @testing.gen_test
    def test_http_method_delete(self):
        test_consumer = RestConsumerTest(client=RestClientTest())
        with self.assertRaises(AttributeError):
            yield test_consumer.testA().http_delete()

    @testing.gen_test
    def test_http_get_with_args(self):
        test_consumer = RestConsumerTest(client=RestClientTest())
        with self.assertRaises(exceptions.InvalidOptions):
            yield test_consumer.testA().http_get('bar')


class TestRestClient(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestRestClient, self).setUp()
        self.client = api.RestClient()
        self.http_response_mock = mock.MagicMock(name='response')
        self.http_client_mock = mock.MagicMock(name='http_client')
        self.http_client_mock.fetch.return_value = tornado_value(
            self.http_response_mock)
        self.client._client = self.http_client_mock

    @testing.gen_test
    def test_get_http_client(self):
        self.client._client = None
        ret = self.client._get_http_client()
        self.assertEquals(type(ret), simple_httpclient.SimpleAsyncHTTPClient)

    @testing.gen_test
    def test_generate_escaped_url(self):
        result = self.client._generate_escaped_url('http://unittest',
                                                   {'foo': 'bar'})
        self.assertEquals('http://unittest?foo=bar', result)
        result = self.client._generate_escaped_url('http://unittest',
                                                   {'foo': True})
        self.assertEquals('http://unittest?foo=true', result)
        result = self.client._generate_escaped_url('http://unittest',
                                                   {'foo': 'bar',
                                                    'xyz': 'abc'})
        self.assertEquals('http://unittest?xyz=abc&foo=bar', result)
        result = self.client._generate_escaped_url('http://unittest',
                                                   {'foo': 'bar baz',
                                                    'xyz': 'abc'})
        self.assertEquals('http://unittest?xyz=abc&foo=bar+baz', result)

    @testing.gen_test
    def test_fetch_get_returns_json(self):
        self.http_response_mock.body = '{"foo": "bar"}'
        ret = yield self.client.fetch(url='http://foo.com', method='GET')
        self.assertEquals({'foo': 'bar'}, ret)

    @testing.gen_test
    def test_fetch_get_returns_string(self):
        self.http_response_mock.body = 'foo bar'
        ret = yield self.client.fetch(url='http://foo.com', method='GET')
        self.assertEquals('foo bar', ret)
