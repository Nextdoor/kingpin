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
# Copyright 2014 Nextdoor.com, Inc

"""Misc Actor objects"""

import logging
import os

from tornado import gen
import boto.sqs.connection
import boto.sqs.queue
import mock

from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin import utils

log = logging.getLogger(__name__)

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'

AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID', None)
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY', None)


class Create(base.HTTPBaseActor):
    """Creates a new SQS Queue."""

    required_options = ['name']

    def __init__(self, *args, **kwargs):
        """Initializes the Actor.

        Args:
            desc: String description of the action being executed.
            options: Dictionary with the following settings:
              { 'name': queue name }
        """
        super(Create, self).__init__(*args, **kwargs)

        self._queue_name = self._options['name']

    @gen.coroutine
    def _create_queue(self):
        # boto pools connections
        conn = yield utils.thread_coroutine(
            boto.sqs.connection.SQSConnection,
            AWS_SECRET_ACCESS_KEY,
            AWS_ACCESS_KEY_ID)

        if not self._dry:
            self._log(logging.INFO, 'Creating a new queue: %s' % self._queue_name)
            new_queue = yield utils.thread_coroutine(conn.create_queue, self._queue_name)
        else:
            self._log(logging.INFO, 'Would create a new queue: %s' % self._queue_name)
            new_queue = mock.Mock(name=self._queue_name)

        self._log(logging.INFO, 'Returning queue object: %s' % new_queue)
        raise gen.Return(new_queue)

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        raises: gen.Return(True)
        """
        self._log(logging.INFO,
                  'Creating a new SQS Queue "%s"' %
                  self._queue_name)
        q = yield self._create_queue()

        if q.__class__ == boto.sqs.queue.Queue:
            self._log(logging.INFO, 'Queue Created: %s' % q.url)
        elif self._dry:
            self._log(logging.INFO, 'Fake Queue: %s' % q)
        else:
            raise Exception('All hell broke loose: %s' % q)

        raise gen.Return(True)


class Delete(base.HTTPBaseActor):
    """Deletes an existing SQS Queue."""

    required_options = ['name']

    def __init__(self, *args, **kwargs):
        """Initializes the Actor.

        Args:
            desc: String description of the action being executed.
            options: Dictionary with the following settings:
              { 'name': queue name,
                'delete_non_empty': False }
        """
        super(Delete, self).__init__(*args, **kwargs)

        self._queue_name = self._options['name']
        self._delete_non_empty = self._options.get('delete_non_empty', False)

    @gen.coroutine
    def _delete_queue(self):
        # boto pools connections
        conn = yield utils.thread_coroutine(
            boto.sqs.connection.SQSConnection,
            AWS_SECRET_ACCESS_KEY,
            AWS_ACCESS_KEY_ID)

        q = yield utils.thread_coroutine(
            conn.get_queue,
            self._queue_name)
        if not q:
            raise exceptions.UnrecoverableActionFailure(
                'Queue not found for deletion: %s' % self._queue_name)

        if not self._dry:
            self._log(logging.INFO, 'Deleting Queue: %s...' % q.url)
            success = yield utils.thread_coroutine(conn.delete_queue, q)
        else:
            self._log(logging.INFO, 'Would have deleted the queue: %s' % q.url)
            success = True

        self._log(logging.INFO, 'Deleting Queue: %s success: %s' % (q.url, success))
        if success != True:
            raise exceptions.UnrecoverableActionFailure(
                'Failed to delete queue: %s' % self._queue_name)

        raise gen.Return(success)

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        raises: gen.Return(True)
        """
        self._log(logging.INFO,
                  'Deleting SQS Queue "%s"' %
                  self._queue_name)
        result = yield self._delete_queue() 
        raise gen.Return(result)


class WaitUntilEmpty(base.HTTPBaseActor):
    """Waits for an SQS Queue to become empty."""

    required_options = ['name']

    def __init__(self, *args, **kwargs):
        """Initializes the Actor.

        Args:
            desc: String description of the action being executed.
            options: Dictionary with the following settings:
              { 'name': queue name }
        """
        super(WaitUntilEmpty, self).__init__(*args, **kwargs)

        self._queue_name = self._options['name']

    @gen.coroutine
    def _wait(self, sleep=3):
        # boto pools connections
        conn = yield utils.thread_coroutine(
            boto.sqs.connection.SQSConnection,
            AWS_SECRET_ACCESS_KEY,
            AWS_ACCESS_KEY_ID)

        q = yield utils.thread_coroutine(
            conn.get_queue,
            self._queue_name)
        if not q:
            raise exceptions.UnrecoverableActionFailure(
                'Queue not found: %s' % self._queue_name)

        count = 1
        while count > 0:
            if not self._dry:
                self._log(logging.INFO, 'Counting %s' % q.url)
                count = yield utils.thread_coroutine(q.count)
            else:
                self._log(logging.INFO, 'Pretending that count is 0 for %s' % q.url)
                count = 0

            self._log(logging.INFO, 'Queue has %s messages in it.' % count)
            if count > 0:
                self._log(logging.INFO, 'Waiting for the queue to become empty...')
                yield utils.tornado_sleep(sleep)

        raise gen.Return(True)

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        raises: gen.Return(True)
        """
        self._log(logging.INFO,
                  'Waiting for queue "%s" to become empty.' %
                  self._queue_name)
        result = yield self._wait()

        raise gen.Return(result)
