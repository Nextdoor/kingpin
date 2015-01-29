"""Tests for the actors.rollbar package"""

import json
import mock
import StringIO

from tornado import gen
from tornado import httpclient
from tornado import testing

from kingpin.actors import rollbar
from kingpin.actors import exceptions


__author__ = 'Matt Wise <matt@nextdoor.com>'


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


class TestRollbarBase(testing.AsyncTestCase):

    """Unit tests for the Rollbar base actor."""

    def setUp(self, *args, **kwargs):
        # For most tests, mock out the TOKEN
        super(TestRollbarBase, self).setUp()
        rollbar.TOKEN = 'Unittest'

    def test_build_potential_args(self):
        potential_args = {
            'foo': 'bar',
            'baz': 'bat',
        }
        expected_args = dict(potential_args)
        expected_args['access_token'] = rollbar.TOKEN

        actor = rollbar.RollbarBase('Unittest Deploy', {})
        args = actor._build_potential_args(potential_args)

        self.assertEquals(args, expected_args)

    @testing.gen_test
    def test_init_without_environment_creds(self):
        # Un-set the token now and make sure the init fails
        rollbar.TOKEN = None
        with self.assertRaises(exceptions.InvalidCredentials):
            rollbar.RollbarBase('Unittest Deploy', {})

    @testing.gen_test
    def test_fetch_wrapper(self):
        actor = rollbar.RollbarBase('Unit Test Action', {})

        # Valid response test
        response_dict = {'status': 'sent'}
        response_body = json.dumps(response_dict)
        http_response = httpclient.HTTPResponse(
            httpclient.HTTPRequest('/'), code=200,
            buffer=StringIO.StringIO(response_body))

        with mock.patch.object(actor, '_get_http_client') as m:
            m.return_value = FakeHTTPClientClass()
            m.return_value.response_value = http_response
            res = yield actor._fetch_wrapper('http://fake.com')
            self.assertEquals(res, response_dict)

    @testing.gen_test
    def test_fetch_wrapper_with_401(self):
        actor = rollbar.RollbarBase('Unit Test Action', {})
        response_dict = {'err': 1, 'messsage': 'Unauthorized'}
        response_body = json.dumps(response_dict)
        http_response = httpclient.HTTPError(
            code=401, response=response_body)

        with mock.patch.object(actor, '_get_http_client') as m:
            m.return_value = FakeExceptionRaisingHTTPClientClass()
            m.return_value.response_value = http_response

            with self.assertRaises(exceptions.InvalidCredentials):
                yield actor._fetch_wrapper('http://fake.com')

    @testing.gen_test
    def test_fetch_wrapper_with_403(self):
        actor = rollbar.RollbarBase('Unit Test Action', {})
        response_dict = {'err': 1, 'messsage': 'access token not found: xxx'}
        response_body = json.dumps(response_dict)
        http_response = httpclient.HTTPError(
            code=403, response=response_body)

        with mock.patch.object(actor, '_get_http_client') as m:
            m.return_value = FakeExceptionRaisingHTTPClientClass()
            m.return_value.response_value = http_response

            with self.assertRaises(exceptions.InvalidCredentials):
                yield actor._fetch_wrapper('http://fake.com')

    @testing.gen_test
    def test_fetch_wrapper_with_422(self):
        actor = rollbar.RollbarBase('Unit Test Action', {})
        response_dict = {'err': 1, 'messsage': 'Unprocessable Entity'}
        response_body = json.dumps(response_dict)
        http_response = httpclient.HTTPError(
            code=422, response=response_body)

        with mock.patch.object(actor, '_get_http_client') as m:
            m.return_value = FakeExceptionRaisingHTTPClientClass()
            m.return_value.response_value = http_response

            with self.assertRaises(exceptions.RecoverableActorFailure):
                yield actor._fetch_wrapper('http://fake.com')

    @testing.gen_test
    def test_fetch_wrapper_with_429(self):
        actor = rollbar.RollbarBase('Unit Test Action', {})
        response_dict = {'err': 1, 'messsage': 'Too Many Requests'}
        response_body = json.dumps(response_dict)
        http_response = httpclient.HTTPError(
            code=429, response=response_body)

        with mock.patch.object(actor, '_get_http_client') as m:
            m.return_value = FakeExceptionRaisingHTTPClientClass()
            m.return_value.response_value = http_response

            with self.assertRaises(exceptions.RecoverableActorFailure):
                yield actor._fetch_wrapper('http://fake.com')

    @testing.gen_test
    def test_fetch_wrapper_with_other_failure(self):
        actor = rollbar.RollbarBase('Unit Test Action', {})
        response_dict = {'err': 1, 'messsage': 'Something bad happened'}
        response_body = json.dumps(response_dict)
        http_response = httpclient.HTTPError(
            code=123, response=response_body)

        with mock.patch.object(actor, '_get_http_client') as m:
            m.return_value = FakeExceptionRaisingHTTPClientClass()
            m.return_value.response_value = http_response

            with self.assertRaises(exceptions.RecoverableActorFailure):
                yield actor._fetch_wrapper('http://fake.com')

    @testing.gen_test
    def test_project(self):
        actor = rollbar.RollbarBase('Unit Test Action', {})
        response_dict = {'err': 0, 'result': '...'}
        response_body = json.dumps(response_dict)
        http_response = httpclient.HTTPResponse(
            httpclient.HTTPRequest('/'), code=200,
            buffer=StringIO.StringIO(response_body))

        with mock.patch.object(actor, '_get_http_client') as m:
            m.return_value = FakeHTTPClientClass()
            m.return_value.response_value = http_response
            res = yield actor._project()
        self.assertEquals(res, response_dict)


class TestDeploy(testing.AsyncTestCase):

    """Unit tests for the Rollbar Deploy actor."""

    def setUp(self, *args, **kwargs):
        # For most tests, mock out the TOKEN
        super(TestDeploy, self).setUp()
        rollbar.TOKEN = 'Unittest'

    @testing.gen_test
    def test_deploy(self):
        actor = rollbar.Deploy(
            'Unit Test Action',
            {'environment': 'unittest',
             'revision': '0001a',
             'local_username': 'bob',
             'comment': 'weeee'})

        @gen.coroutine
        def fake_fetch_wrapper(*args, **kwargs):
            raise gen.Return('123')
        actor._fetch_wrapper = fake_fetch_wrapper
        res = yield actor._deploy()
        self.assertEquals(res, '123')

    @testing.gen_test
    def test_deploy_with_rollbar_username(self):
        actor = rollbar.Deploy(
            'Unit Test Action',
            {'environment': 'unittest',
             'revision': '0001a',
             'local_username': 'bob',
             'rollbar_username': 'bob@rollbar.com',
             'comment': 'weeee'})

        @gen.coroutine
        def fake_fetch_wrapper(*args, **kwargs):
            raise gen.Return('123')
        actor._fetch_wrapper = fake_fetch_wrapper
        res = yield actor._deploy()
        self.assertEquals(res, '123')

    @testing.gen_test
    def test_execute_dry(self):
        actor = rollbar.Deploy(
            'Unit Test Action',
            {'environment': 'unittest',
             'revision': '0001a',
             'local_username': 'bob',
             'rollbar_username': 'bob@rollbar.com',
             'comment': 'weeee'}, dry=True)

        @gen.coroutine
        def fake_project(*args, **kwargs):
            raise gen.Return('123')
        actor._project = fake_project
        res = yield actor._execute()
        self.assertEquals(res, None)

    @testing.gen_test
    def test_execute(self):
        actor = rollbar.Deploy(
            'Unit Test Action',
            {'environment': 'unittest',
             'revision': '0001a',
             'local_username': 'bob',
             'rollbar_username': 'bob@rollbar.com',
             'comment': 'weeee'})

        @gen.coroutine
        def fake_deploy(*args, **kwargs):
            raise gen.Return('123')
        actor._deploy = fake_deploy
        res = yield actor._execute()
        self.assertEquals(res, None)
