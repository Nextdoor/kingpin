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

"""AWS SQS Actors"""

import logging

from tornado import gen
import boto.sqs.connection
import boto.sqs.queue
import mock

from kingpin import utils
from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.actors.aws import settings as aws_settings

log = logging.getLogger(__name__)

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'


class SQSBaseActor(base.BaseActor):
    def __init__(self, *args, **kwargs):
        """Create the connection object."""
        super(SQSBaseActor, self).__init__(*args, **kwargs)

        self.conn = boto.sqs.connection.SQSConnection(
            aws_settings.AWS_SECRET_ACCESS_KEY,
            aws_settings.AWS_ACCESS_KEY_ID)


class Create(SQSBaseActor):
    """Creates a new SQS Queue."""

    required_options = ['name']

    @gen.coroutine
    def _create_queue(self, name):
        if not self._dry:
            self._log(logging.INFO,
                      'Creating a new queue: %s' % name)
            new_queue = yield utils.thread_coroutine(
                self.conn.create_queue, name)
        else:
            self._log(logging.INFO,
                      'Would create a new queue: %s' % name)
            new_queue = mock.Mock(name=name)

        self._log(logging.INFO, 'Returning queue object: %s' % new_queue)
        raise gen.Return(new_queue)

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        raises: gen.Return(True)
        """
        self._log(logging.INFO,
                  'Creating a new SQS Queue "%s"' %
                  self._options['name'])
        q = yield self._create_queue(name=self._options['name'])

        if q.__class__ == boto.sqs.queue.Queue:
            self._log(logging.INFO, 'Queue Created: %s' % q.url)
        elif self._dry:
            self._log(logging.INFO, 'Fake Queue: %s' % q)
        else:
            raise Exception('All hell broke loose: %s' % q)

        raise gen.Return(True)


class Delete(SQSBaseActor):
    """Deletes an existing SQS Queue."""

    required_options = ['name']

    @gen.coroutine
    def _delete_queue(self, name):
        q = yield utils.thread_coroutine(self.conn.get_queue, name)

        if not q:
            raise exceptions.UnrecoverableActionFailure(
                'Queue not found for deletion: %s' % name)

        if not self._dry:
            self._log(logging.INFO, 'Deleting Queue: %s...' % q.url)
            success = yield utils.thread_coroutine(self.conn.delete_queue, q)
        else:
            self._log(logging.INFO, 'Would have deleted the queue: %s' % q.url)
            success = True

        self._log(logging.INFO,
                  'Deleting Queue: %s success: %s' % (q.url, success))
        if not success:
            raise exceptions.UnrecoverableActionFailure(
                'Failed to delete queue: %s' % name)

        raise gen.Return(success)

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        raises: gen.Return(True)
        """
        self._log(logging.INFO,
                  'Deleting SQS Queue "%s"' %
                  self._options['name'])

        result = yield self._delete_queue(
            name=self._options['name'])

        raise gen.Return(result)


class WaitUntilEmpty(SQSBaseActor):
    """Waits for an SQS Queue to become empty."""

    required_options = ['name']

    @gen.coroutine
    def _wait(self, name, sleep=3):
        q = yield utils.thread_coroutine(
            self.conn.get_queue,
            name)
        if not q:
            raise exceptions.UnrecoverableActionFailure(
                'Queue not found: %s' % name)

        count = 1
        while count > 0:
            if not self._dry:
                self._log(logging.INFO, 'Counting %s' % q.url)
                count = yield utils.thread_coroutine(q.count)
            else:
                self._log(logging.INFO,
                          'Pretending that count is 0 for %s' % q.url)
                count = 0

            self._log(logging.INFO, 'Queue has %s messages in it.' % count)
            if count > 0:
                self._log(logging.INFO,
                          'Waiting for the queue to become empty...')
                yield utils.tornado_sleep(sleep)

        raise gen.Return(True)

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        raises: gen.Return(True)
        """
        self._log(logging.INFO,
                  'Waiting for queue "%s" to become empty.' %
                  self._options['name'])
        result = yield self._wait(name=self._options['name'])

        raise gen.Return(result)
