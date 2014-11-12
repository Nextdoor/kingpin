"""Tests for the actors.hipchat package"""

import json
import mock
import StringIO

from tornado import gen
from tornado import httpclient
from tornado import testing

from kingpin.actors import hipchat
from kingpin.actors import exceptions
from kingpin.actors.test.helper import mock_tornado


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


class TestHipchatBase(testing.AsyncTestCase):

    """Unit tests for the Hipchat Message actor."""

    def setUp(self, *args, **kwargs):
        # For most tests, mock out the TOKEN
        super(TestHipchatBase, self).setUp()
        hipchat.TOKEN = 'Unittest'

    def test_validate_from_name(self):
        message = 'Unit test message'
        room = 'Operations'
        actor = hipchat.Message(
            'Unit Test Action',
            {'message': message, 'room': room})

        # Regular run
        self.assertEquals('Foo Bar', actor._validate_from_name('Foo Bar'))

    def test_build_potential_args(self):
        potential_args = {
            'foo': 'bar',
            'baz': 'bat',
        }
        expected_args = dict(potential_args)
        expected_args['auth_token'] = hipchat.TOKEN
        expected_args['from'] = hipchat.NAME

        expected_dry_args = dict(expected_args)
        expected_dry_args['auth_test'] = True

        message = 'Unit test message'
        room = 'Operations'
        actor = hipchat.Message(
            'Unit Test Action',
            {'message': message, 'room': room})

        # Regular run
        args = actor._build_potential_args(potential_args)
        self.assertEquals(args, expected_args)

        # Now in dry mode
        actor._dry = True
        args = actor._build_potential_args(potential_args)
        self.assertEquals(args, expected_dry_args)

    @testing.gen_test
    def test_init_without_environment_creds(self):
        # Un-set the token now and make sure the init fails
        hipchat.TOKEN = None
        with self.assertRaises(exceptions.InvalidCredentials):
            hipchat.Message('Unit Test Action',
                            {'room': 'test', 'message': 'test'})

    @testing.gen_test
    def test_init_with_missing_options(self):
        with self.assertRaises(exceptions.InvalidOptions):
            hipchat.Message('Unit Test Action', {})


class TestHipchatMessage(testing.AsyncTestCase):

    """Unit tests for the Hipchat Message actor."""

    def setUp(self, *args, **kwargs):
        # For most tests, mock out the TOKEN
        super(TestHipchatMessage, self).setUp()
        hipchat.TOKEN = 'Unittest'

    @testing.gen_test
    def test_execute(self):
        message = 'Unit test message'
        room = 'unit_room'
        actor = hipchat.Message(
            'Unit Test Action',
            {'message': message, 'room': room})

        # Valid response test
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
        message = 'Unit test message'
        room = 'unit_room'
        actor = hipchat.Message(
            'Unit Test Action',
            {'message': message, 'room': room})

        # Valid response test
        response_dict = {'success': {'code': 202, 'type': 'Accepted',
                         'message': 'It worked'}}
        response_body = json.dumps(response_dict)
        http_response = httpclient.HTTPResponse(
            httpclient.HTTPRequest('/'), code=202,
            buffer=StringIO.StringIO(response_body))

        with mock.patch.object(actor, '_get_http_client') as m:
            m.return_value = FakeHTTPClientClass()
            m.return_value.response_value = http_response
            res = yield actor._execute()
            self.assertEquals(res, None)

    @testing.gen_test
    def test_execute_with_401(self):
        message = 'Unit test message'
        room = 'unit_room'
        actor = hipchat.Message(
            'Unit Test Action',
            {'message': message, 'room': room})

        # Valid response test
        response_dict = {'error': {'code': 401, 'type': 'Unauthorized',
                         'message': 'Auth token not found'}}
        response_body = json.dumps(response_dict)
        http_response = httpclient.HTTPError(
            code=401, response=response_body)

        with mock.patch.object(actor, '_get_http_client') as m:
            m.return_value = FakeExceptionRaisingHTTPClientClass()
            m.return_value.response_value = http_response

            with self.assertRaises(exceptions.InvalidCredentials):
                yield actor._execute()

    @testing.gen_test
    def test_execute_with_403(self):
        message = 'Unit test message'
        room = 'unit_room'
        actor = hipchat.Message(
            'Unit Test Action',
            {'message': message, 'room': room})

        # Valid response test
        response_dict = {'error': {'code': 403, 'type': 'Forbidden',
                         'message': 'Hit the rate limit'}}
        response_body = json.dumps(response_dict)
        http_response = httpclient.HTTPError(
            code=403, response=response_body)

        with mock.patch.object(actor, '_get_http_client') as m:
            m.return_value = FakeExceptionRaisingHTTPClientClass()
            m.return_value.response_value = http_response

            with self.assertRaises(exceptions.RecoverableActorFailure):
                yield actor._execute()

    @testing.gen_test
    def test_execute_with_unknown_exception(self):
        message = 'Unit test message'
        room = 'unit_room'
        actor = hipchat.Message(
            'Unit Test Action',
            {'message': message, 'room': room})

        # Valid response test
        response_dict = {'error': {'code': 123, 'type': 'Unknown',
                         'message': 'Auth token not found'}}
        response_body = json.dumps(response_dict)
        http_response = httpclient.HTTPError(
            code=123, response=response_body)

        with mock.patch.object(actor, '_get_http_client') as m:
            m.return_value = FakeExceptionRaisingHTTPClientClass()
            m.return_value.response_value = http_response

            with self.assertRaises(exceptions.RecoverableActorFailure):
                yield actor._execute()

    @testing.gen_test
    def test_execute_with_empty_response(self):
        message = 'Unit test message'
        room = 'unit_room'
        actor = hipchat.Message(
            'Unit Test Action',
            {'message': message, 'room': room})

        @gen.coroutine
        def fake_post_message(*args, **kwargs):
            raise gen.Return(None)
        actor._post_message = fake_post_message

        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield actor._execute()


class TestHipchatTopic(testing.AsyncTestCase):

    """Unit tests for the Hipchat Message actor."""

    def setUp(self, *args, **kwargs):
        # For most tests, mock out the TOKEN
        super(TestHipchatTopic, self).setUp()
        hipchat.TOKEN = 'Unittest'

    @testing.gen_test
    def test_execute(self):
        topic = 'Unit test topic'
        room = 'unit_room'
        actor = hipchat.Topic(
            'Unit Test Action',
            {'topic': topic, 'room': room})

        # Valid response test
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
        topic = 'Unit test topic'
        room = 'unit_room'
        actor = hipchat.Topic(
            'Unit Test Action',
            {'topic': topic, 'room': room})

        # Valid response test
        response_dict = {'success': {'code': 202, 'type': 'Accepted',
                         'message': 'It worked'}}
        response_body = json.dumps(response_dict)
        http_response = httpclient.HTTPResponse(
            httpclient.HTTPRequest('/'), code=202,
            buffer=StringIO.StringIO(response_body))

        with mock.patch.object(actor, '_get_http_client') as m:
            m.return_value = FakeHTTPClientClass()
            m.return_value.response_value = http_response
            res = yield actor._execute()
            self.assertEquals(res, None)

    @testing.gen_test
    def test_execute_with_401(self):
        topic = 'Unit test topic'
        room = 'unit_room'
        actor = hipchat.Topic(
            'Unit Test Action',
            {'topic': topic, 'room': room})

        # Valid response test
        response_dict = {'error': {'code': 401, 'type': 'Unauthorized',
                         'message': 'Auth token not found'}}
        response_body = json.dumps(response_dict)
        http_response = httpclient.HTTPError(
            code=401, response=response_body)

        with mock.patch.object(actor, '_get_http_client') as m:
            m.return_value = FakeExceptionRaisingHTTPClientClass()
            m.return_value.response_value = http_response

            with self.assertRaises(exceptions.InvalidCredentials):
                yield actor._execute()

    @testing.gen_test
    def test_execute_with_403(self):
        topic = 'Unit test topic'
        room = 'unit_room'
        actor = hipchat.Topic(
            'Unit Test Action',
            {'topic': topic, 'room': room})

        # Valid response test
        response_dict = {'error': {'code': 403, 'type': 'Forbidden',
                         'message': 'Hit the rate limit'}}
        response_body = json.dumps(response_dict)
        http_response = httpclient.HTTPError(
            code=403, response=response_body)

        actor._fetch = mock_tornado(exc=http_response)

        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield actor._execute()

        # Assert that the call is retried multiple times.
        self.assertEquals(actor._fetch._call_count, 3)

    @testing.gen_test
    def test_execute_with_unknown_exception(self):
        topic = 'Unit test topic'
        room = 'unit_room'
        actor = hipchat.Topic(
            'Unit Test Action',
            {'topic': topic, 'room': room})

        # Valid response test
        response_dict = {'error': {'code': 123, 'type': 'Unknown',
                         'message': 'Auth token not found'}}
        response_body = json.dumps(response_dict)
        http_response = httpclient.HTTPError(
            code=123, response=response_body)

        with mock.patch.object(actor, '_get_http_client') as m:
            m.return_value = FakeExceptionRaisingHTTPClientClass()
            m.return_value.response_value = http_response

            with self.assertRaises(exceptions.RecoverableActorFailure):
                yield actor._execute()

    @testing.gen_test
    def test_execute_with_empty_response(self):
        topic = 'Unit test topic'
        room = 'unit_room'
        actor = hipchat.Topic(
            'Unit Test Action',
            {'topic': topic, 'room': room})

        @gen.coroutine
        def fake_set_topic(*args, **kwargs):
            raise gen.Return(None)
        actor._set_topic = fake_set_topic

        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield actor._execute()
