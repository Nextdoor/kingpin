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
:mod:`kingpin.actors.hipchat`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The Hipchat Actors allow you to send messages to a HipChat room at stages
during your job execution. The actor supports dry mode by validating that the
configured API Token has access to execute the methods, without actually
sending the messages.

**Required Environment Variables**

:HIPCHAT_TOKEN:
  HipChat API Token

:HIPCHAT_NAME:
  HipChat message from name
  (defaults to ``Kingpin``)
"""

import logging
import os

from tornado import gen
from tornado import httpclient

from kingpin import utils
from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.constants import REQUIRED

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


API_CONTENT_TYPE = 'application/json'
API_URL = 'https://api.hipchat.com/v1'
API_MESSAGE_PATH = '%s/rooms/message' % API_URL
API_TOPIC_PATH = '%s/rooms/topic' % API_URL

TOKEN = os.getenv('HIPCHAT_TOKEN', None)
NAME = os.getenv('HIPCHAT_NAME', 'Kingpin')


class HipchatBase(base.HTTPBaseActor):

    """Simple Hipchat Abstract Base Object"""

    def __init__(self, *args, **kwargs):
        """Check required environment variables."""
        super(HipchatBase, self).__init__(*args, **kwargs)

        if not TOKEN:
            raise exceptions.InvalidCredentials(
                'Missing the "HIPCHAT_TOKEN" environment variable.')

        self._token = TOKEN
        self._name = self._validate_from_name(NAME)

    def _validate_from_name(self, name):
        """Parses and validates the FROM name.

        The username must be between 1 and 15 characters. If its not,
        we return a partial name to ensure that the push still works.

        Args:
            name: (Str) Proposed Hipchat message 'from' name

        Returns:
            A potentially modified string name thats valid.
        """
        return name[:15]

    def _build_potential_args(self, potential_args):
        """Builds a full set of arguments to pass to Hipchat.

        Appends the authentication token and a few other bits to the
        arguments supplied.

        Args:
            potential_Args: A hash of potential arguments.

        Returns:
            A larger hash of arguments.
        """
        potential_args['auth_token'] = self._token
        potential_args['from'] = self._name

        # If we're in 'dry run' mode, add the auth_test parameter
        if self._dry:
            potential_args['auth_test'] = True

        return potential_args

    @gen.coroutine
    @utils.retry(excs=exceptions.RecoverableActorFailure, retries=3)
    def _fetch_wrapper(self, *args, **kwargs):
        """Wrap the superclass _fetch method to catch known Hipchat errors."""
        try:
            res = yield self._fetch(*args, **kwargs)
        except httpclient.HTTPError as e:
            # These are HTTPErrors that we know about, and can log specific
            # error messages for.

            self.log.critical(e)
            if e.code in (401, 403):
                # "The authentication you provided is invalid."
                raise exceptions.InvalidCredentials(
                    'The "HIPCHAT_NAME" or "HIPCHAT_TOKEN" supplied is '
                    'invalid. %s' % e)
            else:
                # We ran into a problem we can't handle. Also, keep in mind
                # that @utils.retry() was used, so this error happened several
                # times before getting here. Raise it.
                raise exceptions.RecoverableActorFailure(
                    'Unexpected error from Hipchat API: %s' % e)

        raise gen.Return(res)


class Message(HipchatBase):

    """Sends a message to a room in HipChat.

    **Options**

    :room:
      (str) The string-name (or ID) of the room to send a message to

    :message:
      (str) Message to send

    **Examples**

    .. code-block:: json

       { "actor": "hipchat.Message",
         "desc": "Send a message!",
         "options": {
           "room": "Operations",
           "message": "Beginning Deploy: v1.2"
         }
       }

    **Dry Mode**

    Fully supported -- does not actually send messages to a room, but validates
    that the API credentials would have access to send the message using the
    HipChat ``auth_test`` optional API argument.
    """

    all_options = {
        'room': (str, REQUIRED, 'Hipchat room name'),
        'message': (str, REQUIRED, 'Message to send')
    }

    desc = "Sending Message to {room}"

    @gen.coroutine
    def _post_message(self, room_id, message,
                      message_format='html', notify=0,
                      color='yellow'):
        """Posts a message to Hipchat.

        https://www.hipchat.com/docs/api/method/rooms/message

        Args:
            room_id: (Str/Int) Name or ID of the room to post to.
            message: (Str) Required. The message body. 10,000 characters max.
            message_format: (Str) 'html' or 'text'.
            notify: (0/1) Whether or not this message should trigger a
                    notification for people in the room.
            color: (Str): Background color for message. One of "yellow", "red",
                          "green", "purple", "gray", or "random".

        Raises:
            gen.Return(<Dictionary of the response from Hipchat>)
        """
        args = self._build_potential_args({
            'room_id': room_id,
            'message': message,
            'message_format': message_format,
            'notify': notify,
            'color': color,
            'format': 'json',
        })
        url = self._generate_escaped_url(API_MESSAGE_PATH, args)
        res = yield self._fetch_wrapper(url)
        raise gen.Return(res)

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        raises: gen.Return()
        """
        self.log.info('Sending message "%s" to Hipchat room "%s"' %
                      (self.option('message'), self.option('room')))
        res = yield self._post_message(self.option('room'),
                                       self.option('message'))

        # If we get 'None' or 'False' back, the actor failed.
        if not res:
            raise exceptions.RecoverableActorFailure(
                'Failed to send message to HipChat: %s' % res)

        # If we got here, the result is supposed to include 'success' as a key
        # and inside that key we can dig for the actual message. If the
        # response code is 202, we know that we didn't actually execute the
        # message send, but just validated the API token against the API.
        if 'success' in res:
            if res['success']['code'] == 202:
                self.log.info('API Token Validated: %s' %
                              res['success']['message'])

        raise gen.Return()


class Topic(HipchatBase):

    """Sets a HipChat room topic.

    **Options**

    -  ``room`` - The string-name (or ID) of the room to set the topic of
    -  ``topic`` - String of the topic to send

    **Examples**

    .. code-block:: json

      { "actor": "hipchat.Topic",
        "desc": "set the room topic",
        "options": {
          "room": "Operations",
          "topic": "Latest Deployment: v1.2"
        }
      }

    **Dry Mode**

    Fully supported -- does not actually set a room topic, but validates
    that the API credentials would have access to set the topic of the room
    requested.
    """

    all_options = {
        'room': (str, REQUIRED, 'Hipchat room name'),
        'topic': (str, REQUIRED, 'Topic to set')
    }

    desc = "Setting Room {room} topic"

    @gen.coroutine
    def _set_topic(self, room_id, topic):
        """Posts a message to Hipchat.

        https://www.hipchat.com/docs/api/method/rooms/topic

        Args:
            room_id: (Str/Int) Name or ID of the room to post to.
            topic: (Str) Required. The topic string, 250 char max

        Raises:
            gen.Return(<Dictionary of the response from Hipchat>)
        """
        args = self._build_potential_args({
            'room_id': room_id,
            'topic': topic,
            'format': 'json',
        })
        url = self._generate_escaped_url(API_TOPIC_PATH, args)

        # Note, we set post='' here to make sure we send a POST message, even
        # though were passing all of our arguments on the actual request line.
        res = yield self._fetch_wrapper(url, post='')
        raise gen.Return(res)

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        raises: gen.Return()
        """
        self.log.info('Setting room "%s" topic to: %s' %
                      (self.option('room'), self.option('topic')))
        res = yield self._set_topic(self.option('room'),
                                    self.option('topic'))

        # If we get 'None' or 'False' back, the actor failed.
        if not res:
            raise exceptions.RecoverableActorFailure(
                'Failed to set room topic: %s' % res)

        # If we got here, the result is supposed to include 'success' as a key
        # and inside that key we can dig for the actual message. If the
        # response code is 202, we know that we didn't actually execute the
        # message send, but just validated the API token against the API.
        if 'success' in res:
            if res['success']['code'] == 202:
                self.log.info('API Token Validated: %s' %
                              res['success']['message'])

        raise gen.Return()
