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
import re
import time

from concurrent import futures
from tornado import concurrent
from tornado import gen
from tornado import ioloop
import boto.sqs.connection
import boto.sqs.queue
import mock

from kingpin import utils
from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.actors.aws import settings as aws_settings

log = logging.getLogger(__name__)

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'


# This executor is used by the tornado.concurrent.run_on_executor()
# decorator. We would like this to be a class variable so its shared
# across RightScale objects, but we see testing IO errors when we
# do this.
EXECUTOR = futures.ThreadPoolExecutor(10)


class SQSActorException(Exception):

    """Raised by SQS Actor for any exception."""


class SQSQueueNotFoundException(SQSActorException):

    """Raised by SQS Actor when a needed queue is not found."""


class SQSBaseActor(base.BaseActor):

    # Get references to existing objects that are used by the
    # tornado.concurrent.run_on_executor() decorator.
    ioloop = ioloop.IOLoop.current()
    executor = EXECUTOR

    required_options = ['name', 'region']

    def __init__(self, *args, **kwargs):
        """Create the connection object."""
        super(SQSBaseActor, self).__init__(*args, **kwargs)

        region = self._get_region(self._options['region'])

        if not (aws_settings.AWS_ACCESS_KEY_ID and
                aws_settings.AWS_SECRET_ACCESS_KEY):
            raise exceptions.InvalidCredentials(
                'AWS settings imported but not all credentials are supplied. '
                'AWS_ACCESS_KEY_ID: %s, AWS_SECRET_ACCESS_KEY: %s' % (
                    aws_settings.AWS_ACCESS_KEY_ID,
                    aws_settings.AWS_SECRET_ACCESS_KEY))

        self.conn = boto.sqs.connection.SQSConnection(
            aws_settings.AWS_ACCESS_KEY_ID,
            aws_settings.AWS_SECRET_ACCESS_KEY,
            region=region)

    def _get_region(self, region):
        """Return 'region' object used in SQSConnection

        Args:
            region: string - AWS region name, like us-west-2
        Returns:
            RegionInfo object from boto.sqs
        """

        all_regions = boto.sqs.regions()
        match = [r for r in all_regions if r.name == region]

        if len(match) != 1:
            raise exceptions.UnrecoverableActionFailure((
                'Expected to find exactly 1 region named %s. '
                'Found: %s') % (region, match))

        return match[0]

    @concurrent.run_on_executor
    @utils.exception_logger
    def _fetch_queues(self, pattern):
        """Searches SQS for all queues with a matching name pattern.

        Args:
            pattern: string - regex used in `re.match()`

        Returns:
            Array of matched queues, even if empty.
        """
        queues = self.conn.get_all_queues()
        match_queues = [q for q in queues if re.match(pattern, q.name)]
        return match_queues


class Create(SQSBaseActor):

    """Creates a new SQS Queue."""

    @concurrent.run_on_executor
    @utils.exception_logger
    def _create_queue(self, name):
        """Create an SQS queue with the specified name.

        Returns either the real boto.sqs.queue.Queue object or the Mock object
        in dry run.

        Args:
            name: Queue name (string) to create.

        Returns:
            An SQS Queue Object
        """
        if not self._dry:
            self.log.info('Creating a new queue: %s' % name)
            new_queue = self.conn.create_queue(name)
        else:
            self.log.info('Would create a new queue: %s' % name)
            new_queue = mock.Mock(name=name)

        self.log.debug('Returning queue object: %s' % new_queue)
        return new_queue

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        Raises:
            gen.Return(True)
        """
        q = yield self._create_queue(name=self._options['name'])

        if q.__class__ == boto.sqs.queue.Queue:
            self.log.info('Queue Created: %s' % q.url)
        elif self._dry:
            self.log.info('Fake Queue: %s' % q)
        else:
            raise exceptions.UnrecoverableActionFailure(
                'All hell broke loose: %s' % q)

        raise gen.Return(True)


class Delete(SQSBaseActor):

    """Deletes an existing SQS Queue."""

    @concurrent.run_on_executor
    @utils.exception_logger
    def _delete_queue(self, queue):
        """Delete the provided queue.

        Raises UnrecoverableActionFailure if fail to delete it.

        Returns True if successful in deletion, or is Dry run.
        """
        if not self._dry:
            self.log.info('Deleting Queue: %s...' % queue.url)
            ok = self.conn.delete_queue(queue)
        else:
            self.log.info('Would delete the queue: %s' % queue.url)
            ok = True

        return ok

    @gen.coroutine
    @utils.retry(SQSQueueNotFoundException, delay=aws_settings.SQS_RETRY_DELAY)
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        Raises:
            gen.Return(True)
        """
        pattern = self._options['name']
        matched_queues = yield self._fetch_queues(pattern=pattern)

        if not matched_queues and not self._dry:
            raise SQSQueueNotFoundException(
                'No queues with pattern "%s" found.' % pattern)

        self.log.info('Deleting SQS Queues: %s' % matched_queues)

        tasks = []
        for q in matched_queues:
            tasks.append(self._delete_queue(q))

        result = yield tasks

        raise gen.Return(all(result))


class WaitUntilEmpty(SQSBaseActor):

    """Waits for one or more SQS Queues to become empty."""

    @concurrent.run_on_executor
    @utils.exception_logger
    def _wait(self, queue, sleep=3):
        """Sleeps until an SQS Queue has emptied out.

        Args:
            queue: AWS SQS Queue object
            sleep: Int of seconds to wait between checks

        Returns:
            True: When queue is empty.
        """

        count = 0
        while True:
            if not self._dry:
                self.log.debug('Counting %s' % queue.url)
                count = queue.count()
            else:
                self.log.info('Pretending that count is 0 for %s' % queue.url)
                count = 0

            self.log.debug('Queue has %s messages in it.' % count)
            if count > 0:
                self.log.info('Waiting on %s to become empty...' % queue.name)
                time.sleep(sleep)
            else:
                self.log.debug('Queue is empty!')
                break

        return True

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        raises: gen.Return(True)
        """
        self.log.info('Waiting for "%s" queues to become empty.' %
                      self._options['name'])
        pattern = self._options['name']
        matched_queues = yield self._fetch_queues(pattern)
        sleepers = []
        for q in matched_queues:
            sleepers.append(self._wait(queue=q))

        self.log.info('%s queues need to be empty.' % len(matched_queues))
        self.log.info([q.name for q in matched_queues])
        yield sleepers
        self.log.info('All queues report empty.')

        raise gen.Return(True)
