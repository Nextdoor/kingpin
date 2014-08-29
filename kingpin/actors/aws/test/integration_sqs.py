"""Simple integration tests for the AWS SQS actors."""

from nose.plugins.attrib import attr
import logging
import uuid

from tornado import testing

from kingpin import utils
from kingpin.actors.aws import sqs

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'

# Generate a common UUID for this particular set of tests
UUID = uuid.uuid4().hex

log = logging.getLogger(__name__)
logging.getLogger('boto').setLevel(logging.INFO)


class IntegrationSQS(testing.AsyncTestCase):
    """High level SQS Actor testing.

    This suite of tests performs the following actions:
    * Create a queue with a randomized name
    * Add a few messages to the queue
    * Start the WaitUntilEmpty task
    * Check that this task is not exiting while there are messages
    * Remove all the messages from the queue
    * Check that the WaitUntilEmpty notices, and returns success
    * Delete the temporary queue

    Note, these tests must be run in-order. The order is defined by
    their definition order in this file. Nose follows this order according
    to its documentation:

        http://nose.readthedocs.org/en/latest/writing_tests.html
    """

    integration = True

    queue_name = 'integration-test-%s' % UUID

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_01_create_queue(self):
        actor = sqs.Create(
            'Create %s' % self.queue_name,
            {'name': self.queue_name})
        done = yield actor.execute()
        yield utils.tornado_sleep(0.1)  # Prevents IOError close() errors
        self.assertTrue(done)

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_02_monitor_queue(self):

        test_message_count = 100

        actor = sqs.WaitUntilEmpty('Wait until empty',
                                   {'name': self.queue_name})

        log.debug('New queue should be empty')
        queue = actor.conn.get_queue(self.queue_name)
        self.assertEquals(queue.count(), 0)

        log.debug('Inserting a message')
        for i in xrange(test_message_count):
            yield utils.thread_coroutine(
                queue.write, queue.new_message('unit-testing'))
        self.assertTrue(queue.count() > 0)

        log.debug('Creating the coroutined WaitUntilEmpty task.')
        # Not waiting for it to finish because it'll never finish.
        wait_task = actor.execute()

        # Sanity check -- the async task is not finished.
        self.assertFalse(wait_task.done())
        # This tornado-sleep guarantees that the task will have a few loops
        yield utils.tornado_sleep(5)

        # Since messages are still in the queue the task should not be done
        self.assertFalse(wait_task.done())

        log.debug('Draining the queue...')
        messages = True
        while messages:
            messages = queue.get_messages(10)
            if messages:
                queue.delete_message_batch(messages)

        # Give our task a few more loops to notice that the queue is empty
        yield utils.tornado_sleep(5)
        self.assertTrue(wait_task.done())  # Should be done!

        done = yield wait_task  # Should be instant since it's done already.
        self.assertTrue(done)

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_03_delete_queue(self):

        actor = sqs.Delete('Delete %s' % self.queue_name,
                           {'name': self.queue_name})

        done = yield actor.execute()
        self.assertTrue(done)
