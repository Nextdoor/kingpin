"""Integration tests for the kingpin.actors.support.api module"""

from tornado import testing

from kingpin.actors.support import api


__author__ = 'Matt Wise <matt@nextdoor.com>'


HTTPBIN = {
    'path': '/',
    'http_methods': {'get': {}},
    'attrs': {
        'get': {
            'path': '/get',
            'http_methods': {'get': {}},
        },
        'post': {
            'path': '/post',
            'http_methods': {'post': {}},
        },
        'put': {
            'path': '/put',
            'http_methods': {'put': {}},
        },
        'delete': {
            'path': '/delete',
            'http_methods': {'delete': {}},
        },
    }
}


class HTTPBinRestClient(api.RestConsumer):

    _CONFIG = HTTPBIN
    _ENDPOINT = 'http://httpbin.org'


class IntegrationRestConsumer(testing.AsyncTestCase):

    integration = True

    @testing.gen_test(timeout=60)
    def integration_base_get(self):
        httpbin = HTTPBinRestClient()
        ret = yield httpbin.http_get()
        self.assertIn('DOCTYPE', ret)

    @testing.gen_test(timeout=60)
    def integration_get_json(self):
        httpbin = HTTPBinRestClient()
        ret = yield httpbin.get().http_get()
        self.assertEquals(ret['url'], 'http://httpbin.org/get')

    @testing.gen_test(timeout=60)
    def integration_get_with_args(self):
        httpbin = HTTPBinRestClient()
        ret = yield httpbin.get().http_get(foo='bar', baz='bat')
        self.assertEquals(ret['url'], 'http://httpbin.org/get?foo=bar&baz=bat')

    @testing.gen_test(timeout=60)
    def integration_post(self):
        httpbin = HTTPBinRestClient()
        ret = yield httpbin.post().http_post(foo='bar', baz='bat')
        self.assertEquals(ret['url'], 'http://httpbin.org/post')
        self.assertEquals(ret['form'], {'foo': 'bar', 'baz': 'bat'})

    @testing.gen_test(timeout=60)
    def integration_put(self):
        httpbin = HTTPBinRestClient()
        ret = yield httpbin.put().http_put(foo='bar', baz='bat')
        self.assertEquals(ret['url'], 'http://httpbin.org/put')
        self.assertEquals(ret['data'], 'foo=bar&baz=bat')

    @testing.gen_test(timeout=60)
    def integration_delete(self):
        httpbin = HTTPBinRestClient()
        ret = yield httpbin.delete().http_delete(foo='bar', baz='bat')
        self.assertEquals(
            ret['url'],
            'http://httpbin.org/delete?foo=bar&baz=bat')
