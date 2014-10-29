"""Tests for the actors.librato package"""

import json
import mock
import StringIO

from tornado import gen
from tornado import httpclient
from tornado import testing

from kingpin.actors import exceptions
from kingpin.actors import librato


class FakeHTTPClientClass(object):
    '''Fake HTTPClient object for testing'''
    response_value = None

    @gen.coroutine
    def fetch(self, *args, **kwargs):
        raise gen.Return(self.response_value)


class FakeExceptionRaisingHTTPClientClass(object):
    '''Fake HTTPClient object for testing'''
    response_value = None

    @gen.coroutine
    def fetch(self, *args, **kwargs):
        raise self.response_value


class TestLibratoAnnotation(testing.AsyncTestCase):
    """Unit tests for the Librato Annotation actor."""

    def setUp(self, *args, **kwargs):
        # For most tests, mock out the TOKEN
        super(TestLibratoAnnotation, self).setUp()
        librato.TOKEN = 'Unittest'
        librato.EMAIL = 'Unittest'

    @testing.gen_test
    def test_init_without_token(self):
        # Un-set the token now and make sure the init fails
        librato.TOKEN = None
        with self.assertRaises(exceptions.InvalidCredentials):
            librato.Annotation(
                'Unit Test Action',
                {'title': 'unittest',
                 'description': 'unittest',
                 'name': 'unittest'})

    @testing.gen_test
    def test_init_without_email(self):
        # Un-set the token now and make sure the init fails
        librato.EMAIL = None
        with self.assertRaises(exceptions.InvalidCredentials):
            librato.Annotation(
                'Unit Test Action',
                {'title': 'unittest',
                 'description': 'unittest',
                 'name': 'unittest'})

    @testing.gen_test
    def test_execute_with_400(self):
        actor = librato.Annotation(
            'Unit Test Action',
            {'title': 'unittest',
             'description': 'unittest',
             'name': 'unittest'})

        http_response = httpclient.HTTPError(
            code=400, response={})

        with mock.patch.object(actor, '_get_http_client') as m:
            m.return_value = FakeExceptionRaisingHTTPClientClass()
            m.return_value.response_value = http_response

            with self.assertRaises(exceptions.BadRequest):
                yield actor._execute()

    @testing.gen_test
    def test_execute_with_401(self):
        actor = librato.Annotation(
            'Unit Test Action',
            {'title': 'unittest',
             'description': 'unittest',
             'name': 'unittest'})

        http_response = httpclient.HTTPError(
            code=401, response={})

        with mock.patch.object(actor, '_get_http_client') as m:
            m.return_value = FakeExceptionRaisingHTTPClientClass()
            m.return_value.response_value = http_response

            with self.assertRaises(exceptions.InvalidCredentials):
                yield actor._execute()

    @testing.gen_test
    def test_execute_with_unknown_exception(self):
        actor = librato.Annotation(
            'Unit Test Action',
            {'title': 'unittest',
             'description': 'unittest',
             'name': 'unittest'})

        http_response = httpclient.HTTPError(
            code=123, response={})

        with mock.patch.object(actor, '_get_http_client') as m:
            m.return_value = FakeExceptionRaisingHTTPClientClass()
            m.return_value.response_value = http_response

            with self.assertRaises(httpclient.HTTPError):
                yield actor._execute()

    @testing.gen_test
    def test_execute(self):
        actor = librato.Annotation(
            'Unit Test Action',
            {'title': 'unittest',
             'description': 'unittest',
             'name': 'unittest'})

        response_dict = {'status': 'sent'}
        response_body = json.dumps(response_dict)
        http_response = httpclient.HTTPResponse(
            httpclient.HTTPRequest('/'), code=200,
            buffer=StringIO.StringIO(response_body))

        with mock.patch.object(actor, '_get_http_client') as m:
            m.return_value = FakeHTTPClientClass()
            m.return_value.response_value = http_response
            res = yield actor._execute()
            self.assertEquals(res, None)

    @testing.gen_test
    def test_execute_dry_mode_response(self):
        actor = librato.Annotation(
            'Unit Test Action',
            {'title': 'unittest',
             'description': 'unittest',
             'name': 'unittest'})
        actor._dry = True

        response_dict = {'status': 'sent'}
        response_body = json.dumps(response_dict)
        http_response = httpclient.HTTPResponse(
            httpclient.HTTPRequest('/'), code=200,
            buffer=StringIO.StringIO(response_body))

        with mock.patch.object(actor, '_get_http_client') as m:
            m.return_value = FakeHTTPClientClass()
            m.return_value.response_value = http_response
            res = yield actor._execute()
            self.assertEquals(res, None)
