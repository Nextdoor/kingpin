# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Copyright 2018 Nextdoor.com, Inc

"""
:mod:`kingpin.actors.slack`
^^^^^^^^^^^^^^^^^^^^^^^^^^^

The Slack Actors allow you to send messages to a Slack channel at stages during
your job execution. The actor supports dry mode by validating that the
configured API Token has access to execute the methods, without actually
sending the messages.

**Required Environment Variables**

:SLACK_TOKEN:
  Slack API Token

:SLACK_NAME:
  Slack *message from* name
  (defaults to *Kingpin*)
"""

import logging
import os
import re

from tornado import gen

from tornado_rest_client import api

from kingpin.constants import REQUIRED
from kingpin.actors import base
from kingpin.actors import exceptions

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


TOKEN = os.getenv('SLACK_TOKEN', None)
NAME = os.getenv('SLACK_NAME', 'Kingpin')


class SlackAPI(api.RestConsumer):

    _ENDPOINT = 'https://api.slack.com'
    _CONFIG = {
        'attrs': {
            'auth_test': {
                'path': '/api/auth.test',
                'http_methods': {'post': {}},
            },
            'chat_postMessage': {
                'path': '/api/chat.postMessage',
                'http_methods': {'post': {}},
            }

        }
    }


class SlackBase(base.BaseActor):

    """Simple Slack Abstract Base Object"""

    def __init__(self, *args, **kwargs):
        """Check required environment variables."""
        super(SlackBase, self).__init__(*args, **kwargs)

        if not TOKEN:
            raise exceptions.InvalidCredentials(
                'Missing the "SLACK_TOKEN" environment variable.')

        rest_client = api.SimpleTokenRestClient(
            tokens={'token': TOKEN}
        )
        self._slack_client = SlackAPI(client=rest_client)

    def _check_results(self, result):
        """Returns True/False if the result was OK from Slack.

        The Slack API avoids using standard error codes, and instead embeds
        error codes in the return results. This method returns True or False
        based on those results.

        Args:
            result: A return dict from Slack

        Raises:
            InvalidCredentials if the creds are bad
            RecoverableActorException on any other value
        """
        try:
            ok = result.get('ok', False)
        except AttributeError:
            raise exceptions.UnrecoverableActorFailure(
                'An unexpected Slack API failure occured: %s' % result)

        if ok:
            return

        # By default, our exception type is a RecoverableActorFailure.
        exc = exceptions.RecoverableActorFailure

        # If we know what kind fo error it is, we'll return a more accurate
        # exception type.
        if result['error'] == 'invalid_auth':
            exc = exceptions.InvalidCredentials

        # Finally, raise our exception
        raise exc('Slack API Error: %s' % result['error'])


class Message(SlackBase):

    """Sends a message to a channel in Slack.

    **Options**

    :channel:
      The string-name of the channel to send a message to, or a list of
      channels

    :message:
      String of the message to send

    **Examples**

    .. code-block:: json

       { "desc": "Let the Engineers know things are happening",
         "actor": "slack.Message",
         "options": {
           "channel": "#operations",
           "message": "Beginning Deploy: %VER%"
         }
       }

    **Dry Mode**

    Fully supported -- does not actually send messages to a room, but validates
    that the API credentials would have access to send the message using the
    Slack `auth.test` API method.
    """

    all_options = {
        'channel': ((str, list), REQUIRED, 'Slack channel or a list of names'),
        'message': (str, REQUIRED, 'Message to send')
    }

    desc = "Sending Message to {channel}"

    @gen.coroutine
    def _execute(self):
        self.log.info('Sending message "%s" to Slack channel "%s"' %
                      (self.option('message'), self.option('channel')))

        if self._dry:
            # Check if our authentication creds are valid
            auth_ok = yield self._slack_client.auth_test().http_post()
            self._check_results(auth_ok)

            self.log.info('API Credentials verified, skipping send.')
            raise gen.Return()

        # If only one channel was supplied as string then prepare the list
        if type(self.option('channel')) == list:
            channels = self.option('channel')
        else:
            channels = re.split('[, ]+', self.option('channel'))

        posts = []
        for channel in channels:
            self.log.debug('Posting to %s' % channel)
            # Finally, send the message and check our return value
            posts.append(self._slack_client.chat_postMessage().http_post(
                channel=channel,
                text=self.option('message'),
                username=NAME,
                parse='none',
                link_names=1,
                unfurl_links=True,
                unfurl_media=True
            ))

        results = yield posts
        for res in results:
            self._check_results(res)
