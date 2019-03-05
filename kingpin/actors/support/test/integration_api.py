"""Integration tests for the kingpin.actors.support.api module"""

from nose.plugins.attrib import attr

from tornado import testing
from tornado import httpclient

from kingpin.actors import exceptions
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
        'status': {
            'path': '/status/%res%',
            'http_methods': {'get': {}},
        },
        'basic_auth': {
            'path': '/basic-auth/username/password',
            'http_methods': {'get': {}},
        }
    }
}


class HTTPBinRestConsumer(api.RestConsumer):

    _CONFIG = HTTPBIN
    _ENDPOINT = 'http://httpbin.org'


class HTTPBinRestConsumerBasicAuthed(HTTPBinRestConsumer):

    _CONFIG = dict(HTTPBinRestConsumer._CONFIG)
    _CONFIG['auth'] = {
        'user': 'username',
        'pass': 'password',
    }


class IntegrationRestConsumer(testing.AsyncTestCase):

    integration = True

    @attr('http', 'integration')
    @testing.gen_test(timeout=60)
    def integration_base_get(self):
        httpbin = HTTPBinRestConsumer()
        ret = yield httpbin.http_get()
        self.assertIn('DOCTYPE', ret)

    @attr('http', 'integration')
    @testing.gen_test(timeout=60)
    def integration_get_json(self):
        httpbin = HTTPBinRestConsumer()
        ret = yield httpbin.get().http_get()
        self.assertEqual(ret['url'], 'http://httpbin.org/get')

    @attr('http', 'integration')
    @testing.gen_test(timeout=60)
    def integration_get_basic_auth(self):
        httpbin = HTTPBinRestConsumerBasicAuthed()
        ret = yield httpbin.basic_auth().http_get()
        self.assertEqual(
            ret, {'authenticated': True, 'user': 'username'})

    @attr('http', 'integration')
    @testing.gen_test(timeout=60)
    def integration_get_basic_auth_401(self):
        httpbin = HTTPBinRestConsumer()
        with self.assertRaises(exceptions.InvalidCredentials):
            yield httpbin.basic_auth().http_get()

    @attr('http', 'integration')
    @testing.gen_test(timeout=60)
    def integration_get_with_args(self):
        httpbin = HTTPBinRestConsumer()
        ret = yield httpbin.get().http_get(foo='bar', baz='bat')
        self.assertEqual(ret['url'], 'http://httpbin.org/get?baz=bat&foo=bar')

    @attr('http', 'integration')
    @testing.gen_test(timeout=60)
    def integration_post(self):
        httpbin = HTTPBinRestConsumer()
        ret = yield httpbin.post().http_post(foo='bar', baz='bat')
        self.assertEqual(ret['url'], 'http://httpbin.org/post')
        self.assertEqual(ret['form'], {'foo': 'bar', 'baz': 'bat'})

    @attr('http', 'integration')
    @testing.gen_test(timeout=60)
    def integration_put(self):
        httpbin = HTTPBinRestConsumer()
        ret = yield httpbin.put().http_put(foo='bar', baz='bat')
        self.assertEqual(ret['url'], 'http://httpbin.org/put')
        self.assertEqual(ret['data'], 'foo=bar&baz=bat')

    @attr('http', 'integration')
    @testing.gen_test(timeout=60)
    def integration_delete(self):
        httpbin = HTTPBinRestConsumer()
        ret = yield httpbin.delete().http_delete(foo='bar', baz='bat')
        self.assertEqual(
            ret['url'],
            'http://httpbin.org/delete?baz=bat&foo=bar')

    @attr('http', 'integration')
    @testing.gen_test(timeout=60)
    def integration_status_401(self):
        httpbin = HTTPBinRestConsumer()
        with self.assertRaises(exceptions.InvalidCredentials):
            yield httpbin.status(res='401').http_get()

    @attr('http', 'integration')
    @testing.gen_test(timeout=60)
    def integration_status_403(self):
        httpbin = HTTPBinRestConsumer()
        with self.assertRaises(exceptions.InvalidCredentials):
            yield httpbin.status(res='403').http_get()

    @attr('http', 'integration')
    @testing.gen_test(timeout=60)
    def integration_status_500(self):
        httpbin = HTTPBinRestConsumer()
        with self.assertRaises(httpclient.HTTPError):
            yield httpbin.status(res='500').http_get()

    @attr('http', 'integration')
    @testing.gen_test(timeout=60)
    def integration_status_501(self):
        httpbin = HTTPBinRestConsumer()
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield httpbin.status(res='501').http_get()

    @attr('http', 'integration')
    @testing.gen_test(timeout=60)
    def integration_status_502(self):
        httpbin = HTTPBinRestConsumer()
        with self.assertRaises(httpclient.HTTPError):
            yield httpbin.status(res='502').http_get()

    @attr('http', 'integration')
    @testing.gen_test(timeout=60)
    def integration_status_503(self):
        httpbin = HTTPBinRestConsumer()
        with self.assertRaises(httpclient.HTTPError):
            yield httpbin.status(res='503').http_get()

    @attr('http', 'integration')
    @testing.gen_test(timeout=60)
    def integration_status_504(self):
        httpbin = HTTPBinRestConsumer()
        with self.assertRaises(httpclient.HTTPError):
            yield httpbin.status(res='504').http_get()
