"""Tests for the actors.slack package"""

import mock

from tornado import testing

from kingpin.actors import slack
from kingpin.actors import exceptions
from kingpin.actors.test.helper import mock_tornado


__author__ = 'Matt Wise <matt@nextdoor.com>'


class TestSlackBase(testing.AsyncTestCase):

    """Unit tests for the Slack Base actor."""

    def setUp(self, *args, **kwargs):
        # For most tests, mock out the TOKEN
        super(TestSlackBase, self).setUp(*args, **kwargs)
        slack.TOKEN = 'Unittest'

    def test_init(self):
        actor = slack.SlackBase('Unit test action', {})

        # Ensure that the actor._slack_client is configured with a dictionary
        # that contains the token in it.
        slack_client_tokens = actor._slack_client._client._tokens
        self.assertEquals(
            slack_client_tokens,
            {'token': 'Unittest'})

    def test_init_missing_creds(self):
        # Un-set the token now and make sure the init fails
        slack.TOKEN = None
        with self.assertRaises(exceptions.InvalidCredentials):
            slack.SlackBase('Unit Test Action', {})
        # Reload the slack library to re-get the token
        reload(slack)

    def test_check_results_with_ok_results(self):
        actor = slack.SlackBase('Unit test action', {})
        results = {
            "ok": True, "channel": "C03H4GRDF", "ts": "1423092527.000006",
            "message": {
                "text": "Hi, testing!",
                "username": "Kingpin",
                "type": "message",
                "subtype": "bot_message",
                "ts": "1423092527.000006"
            }
        }
        self.assertEquals(None, actor._check_results(results))

    def test_check_results_with_invalid_creds(self):
        actor = slack.SlackBase('Unit test action', {})
        results = {'ok': False, 'error': 'invalid_auth'}
        with self.assertRaises(exceptions.InvalidCredentials):
            actor._check_results(results)

    def test_check_results_with_unexpected_results(self):
        actor = slack.SlackBase('Unit test action', {})
        results = 'got some unexpected result'
        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            actor._check_results(results)


class TestMessage(testing.AsyncTestCase):

    """Unit tests for the Slack Message actor."""

    def setUp(self, *args, **kwargs):
        # For most cases, mock out the TOKEN
        super(TestMessage, self).setUp(*args, **kwargs)
        slack.TOKEN = 'Unittest'

        self.actor = slack.Message(
            'Unit test message',
            {'channel': '#testing',
             'message': 'Unittest'})
        self._slack_mock = mock.MagicMock(name='SlackAPIMock')
        self.actor._slack_client = self._slack_mock

    @testing.gen_test
    def test_execute_dry(self):
        # Mock out the calls to SlackAPI.auth_test().auth_test()
        auth_test_mock = mock.MagicMock(name='auth_test')
        auth_test_mock.http_post.side_effect = mock_tornado({'ok': 'true'})
        self._slack_mock.auth_test.return_value = auth_test_mock

        # Ensure we're dry
        self.actor._dry = True
        ret = yield self.actor._execute()
        self.assertEquals(None, ret)

        # Ensure the calls were made to the API
        auth_test_mock.http_post.assert_has_calls([mock.call()])

    @testing.gen_test
    def test_execute(self):
        # Mock out the calls to SlackAPI.auth_test().auth_test()
        auth_test_mock = mock.MagicMock(name='auth_test')
        auth_test_mock.http_post.side_effect = mock_tornado({'ok': 'true'})
        self._slack_mock.auth_test.return_value = auth_test_mock

        # Mock out the calls to SlackAPI.chat_postMessage().http_post()
        post_mock = mock.MagicMock(name='auth_test')
        post_mock.http_post.side_effect = mock_tornado({'ok': 'true'})
        self._slack_mock.chat_postMessage.return_value = post_mock

        ret = yield self.actor._execute()
        self.assertEquals(None, ret)

        # Ensure the calls were made to the API
        auth_test_mock.http_post.assert_has_calls([mock.call()])
        post_mock.http_post.assert_has_calls([mock.call(
            username='Kingpin', unfurl_links=True, text='Unittest',
            unfurl_media=True, parse='full', link_names=1, channel='#testing'
        )])
