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
:mod:`kingpin.actors.aws.sqs`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
"""

import logging
import re

from tornado import concurrent
from tornado import gen
from tornado import ioloop
import boto.sqs.connection
import boto.sqs.queue
import mock

from kingpin import utils
from kingpin.actors import exceptions
from kingpin.actors.aws import base
from kingpin.actors.aws import settings as aws_settings
from kingpin.actors.utils import dry
from kingpin.constants import REQUIRED

log = logging.getLogger(__name__)

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'


# This executor is used by the tornado.concurrent.run_on_executor()
# decorator. We would like this to be a class variable so its shared
# across RightScale objects, but we see testing IO errors when we
# do this.
EXECUTOR = concurrent.futures.ThreadPoolExecutor(10)


class QueueNotFound(exceptions.RecoverableActorFailure):

    """Raised by SQS Actor when a needed queue is not found."""


class QueueDeletionFailed(exceptions.RecoverableActorFailure):

    """Raised if Boto fails to delete an SQS queue.

    http://boto.readthedocs.org/en/latest/ref/
        sqs.html#boto.sqs.connection.SQSConnection.delete_queue
    """


class SQSBaseActor(base.AWSBaseActor):

    # This actor should not be instantiated, but unit testing requires that
    # it's all options are defined properly here.
    all_options = {
        'name': (str, REQUIRED, 'Queue name to do nothing with.'),
        'region': (str, REQUIRED, 'AWS region (or zone) name like us-west-2')
    }

    # Get references to existing objects that are used by the
    # tornado.concurrent.run_on_executor() decorator.
    ioloop = ioloop.IOLoop.current()
    executor = EXECUTOR

    @gen.coroutine
    def _fetch_queues(self, pattern):
        """Searches SQS for all queues with a matching name pattern.

        Args:
            pattern: string - regex used in `re.match()`

        Returns:
            Array of matched queues, even if empty.
        """
        queues = yield self.api_call(self.sqs_conn.get_all_queues)
        match_queues = [q for q in queues if re.search(pattern, q.name)]
        raise gen.Return(match_queues)


class Create(SQSBaseActor):

    """Creates a new SQS queue with the specified name

    **Options**

    :name:
      (str) The name of the queue to create

    :region:
      (str) AWS region (or zone) string, like 'us-west-2'

    **Examples**

    .. code-block:: json

       { "actor": "aws.sqs.Create",
         "desc": "Create queue named async-tasks",
         "options": {
           "name": "async-tasks",
           "region": "us-east-1",
         }
       }

    **Dry Mode**

    Will not create any queue, or even contact SQS. Will create a mock.Mock
    object and exit with success.
    """

    all_options = {
        'name': (str, REQUIRED, 'Name or pattern for SQS queues.'),
        'region': (str, REQUIRED, 'AWS region (or zone), such as us-west-2')
    }

    @gen.coroutine
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
            new_queue = yield self.api_call(self.sqs_conn.create_queue, name)
        else:
            self.log.info('Would create a new queue: %s' % name)
            new_queue = mock.Mock(name=name)

        self.log.debug('Returning queue object: %s' % new_queue)
        raise gen.Return(new_queue)

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        Raises:
            gen.Return()
        """
        q = yield self._create_queue(name=self.option('name'))

        if q.__class__ == boto.sqs.queue.Queue:
            self.log.info('Queue Created: %s' % q.url)
        elif self._dry:
            self.log.info('Fake Queue: %s' % q)
        else:
            raise exceptions.UnrecoverableActorFailure(
                'All hell broke loose: %s' % q)

        raise gen.Return()


class Delete(SQSBaseActor):

    """Deletes the SQS queues

    Note: **even if it`s not empty**

    **Options**

    :name:
      (str) The name of the queue to destroy

    :region:
      (str) AWS region (or zone) string, like 'us-west-2'

    :idempotent:
      (bool) Will not raise errors if no matching queues are found.
      (default: False)

    **Examples**

    .. code-block:: json

       { "actor": "aws.sqs.Delete",
         "desc": "Delete queue async-tasks",
         "options": {
           "name": "async-tasks",
           "region": "us-east-1"
         }
       }

    .. code-block:: json

       { "actor": "aws.sqs.Delete",
         "desc": "Delete queues with 1234 in the name",
         "options": {
           "name": "1234",
           "region": "us-east-1"
         }
       }

    **Dry Mode**

    Will find the specified queue, but will have a noop regarding its deletion.
    Dry mode will fail if no queues are found, and idempotent flag is set to
    False.
    """

    all_options = {
        'name': (str, REQUIRED, 'Name or pattern for SQS queues.'),
        'region': (str, REQUIRED, 'AWS region (or zone), such as us-west-2'),
        'idempotent': (bool, False, 'Continue if queues are already deleted.')
    }

    @gen.coroutine
    @dry('Would delete the queue: {queue}')
    def _delete_queue(self, queue):
        """Delete the provided queue.

        Raises RecoverableActorFailure if fail to delete it.

        Returns:
          True if successful in deletion, or is Dry run.

        Raises:
          QueueDeletionFailed if queue deletion failed.
        """
        self.log.info('Deleting Queue: %s...' % queue.url)
        ok = yield self.api_call(self.sqs_conn.delete_queue, queue)

        # Raise an exception if the tasks failed
        if not ok:
            raise QueueDeletionFailed('Failed to delete "%s"' % queue.url)

        raise gen.Return(ok)

    @gen.coroutine
    @utils.retry(QueueNotFound, delay=aws_settings.SQS_RETRY_DELAY)
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        Raises:
            gen.Return()
            QueueNotFound()
        """
        pattern = self.option('name')
        matched_queues = yield self._fetch_queues(pattern=pattern)

        not_found_condition = (not matched_queues and
                               not self.option('idempotent'))

        if not_found_condition:
            raise QueueNotFound(
                'No queues with pattern "%s" found.' % pattern)

        self.log.info('Deleting SQS Queues: %s' % matched_queues)

        tasks = []
        for q in matched_queues:
            tasks.append(self._delete_queue(queue=q))
        yield tasks

        raise gen.Return()


class WaitUntilEmpty(SQSBaseActor):

    """Wait indefinitely until for SQS queues to become empty

    This actor will loop infinitely as long as the count of messages in at
    least one queue is greater than zero. SQS does not guarantee exact count,
    so this can return a stale value if the number of messages in the queue
    changes rapidly.


    **Options**

    :name:
      (str) The name or regex pattern of the queues to operate on

    :region:
      (str) AWS region (or zone) string, like 'us-west-2'

    :required:
      (bool) Fail if no matching queues are found.
      (default: False)

    **Examples**

    .. code-block:: json

       { "actor": "aws.sqs.WaitUntilEmpty",
         "desc": "Wait until release-0025a* queues are empty",
         "options": {
           "name": "release-0025a",
           "region": "us-east-1",
           "required": true
         }
       }

    **Dry Mode**

    This actor performs the finding of the queue, but will pretend that the
    count is 0 and return success. Will fail even in dry mode if `required`
    option is set to True and no queues with the name pattern are found.
    """

    all_options = {
        'name': (str, REQUIRED, 'Name or pattern for SQS queues.'),
        'region': (str, REQUIRED, 'AWS region (or zone), such as us-west-2'),
        'required': (bool, False, 'At least 1 queue must be found.')
    }

    @gen.coroutine
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
                visible = yield self.api_call(queue.count)
                attr = 'ApproximateNumberOfMessagesNotVisible'
                invisible = yield self.api_call(queue.get_attributes, attr)
                invisible_int = int(invisible[attr])
                count = visible + invisible_int
            else:
                self.log.info('Pretending that count is 0 for %s' % queue.url)
                count = 0

            self.log.debug('Queue has %s messages in it.' % count)
            if count > 0:
                self.log.info('Waiting on %s to become empty...' % queue.name)
                yield utils.tornado_sleep(sleep)
            else:
                self.log.debug('Queue is empty!')
                break

        raise gen.Return(True)

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        raises: gen.Return()
        """
        pattern = self.option('name')
        matched_queues = yield self._fetch_queues(pattern)

        # Note: this does not check for dry mode.
        if self.option('required') and not matched_queues:
            raise QueueNotFound(
                'No queues like "%s" were found!' % pattern)

        self.log.info('Waiting for "%s" queues to become empty.' %
                      self.option('name'))

        sleepers = []
        for q in matched_queues:
            sleepers.append(self._wait(queue=q))

        self.log.info('%s queues need to be empty.' % len(matched_queues))
        self.log.info([q.name for q in matched_queues])
        yield sleepers
        self.log.info('All queues report empty.')

        raise gen.Return()
