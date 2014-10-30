"""Simple integration tests for the AWS SQS actors."""

from nose.plugins.attrib import attr
import logging
import uuid

from tornado import testing

from kingpin import utils
from kingpin.actors.aws import settings
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
    region = 'us-east-1'

    @attr('integration', 'dry')
    @testing.gen_test(timeout=60)
    def integration_01a_create_queue_dry(self):
        actor = sqs.Create(
            'Create %s' % self.queue_name,
            {'name': self.queue_name,
             'region': self.region},
            dry=True)
        done = yield actor.execute()
        self.assertEquals(done, None)

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_01b_create_queue(self):
        actor = sqs.Create(
            'Create %s' % self.queue_name,
            {'name': self.queue_name,
             'region': self.region})
        done = yield actor.execute()
        self.assertEquals(done, None)

    @attr('integration', 'dry')
    @testing.gen_test(timeout=60)
    def integration_02a_monitor_queue_dry(self):
        actor = sqs.WaitUntilEmpty('Wait until empty',
                                   {'name': self.queue_name,
                                    'region': self.region},
                                   dry=True)
        done = yield actor.execute()
        self.assertEquals(done, None)

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_02b_monitor_queue(self):

        actor = sqs.WaitUntilEmpty('Wait until empty',
                                   {'name': self.queue_name,
                                    'region': self.region})

        log.debug('New queue should be empty')
        queue = actor.conn.get_queue(self.queue_name)
        self.assertEquals(queue.count(), 0)

        done = yield actor.execute()
        yield utils.tornado_sleep()
        self.assertEquals(done, None)

    @attr('integration', 'dry')
    @testing.gen_test()
    def integration_03a_delete_queue_dry(self):
        actor = sqs.Delete('Delete %s' % self.queue_name,
                           {'name': self.queue_name,
                            'region': self.region,
                            'idempotent': True},
                           dry=True)

        done = yield actor.execute()
        self.assertEquals(done, None)

    @attr('integration')
    @testing.gen_test(timeout=120)  # Delete actor sleeps and retries.
    def integration_03b_delete_queue(self):
        actor = sqs.Delete('Delete %s' % self.queue_name,
                           {'name': self.queue_name,
                            'region': self.region})

        done = yield actor.execute()
        self.assertEquals(done, None)

    @attr('integration')
    @testing.gen_test(timeout=120)  # Delete actor sleeps and retries.
    def integration_03c_delete_fake_queue(self):
        settings.SQS_RETRY_DELAY = 0
        reload(sqs)
        actor = sqs.Delete('Delete %s' % self.queue_name,
                           {'name': 'totally-fake-queue',
                            'region': self.region})

        with self.assertRaises(sqs.QueueNotFound):
            yield actor.execute()
