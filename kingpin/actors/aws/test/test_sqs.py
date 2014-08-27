import logging
import mock

from tornado import testing

from kingpin.actors.aws import sqs

log = logging.getLogger(__name__)

import boto.sqs.connection
import boto.sqs.queue


class SQSTestCase(testing.AsyncTestCase):

    @mock.patch.object(boto.sqs.connection, 'SQSConnection')
    def run(self, result, sqsc):
        self.conn = sqsc
        super(SQSTestCase, self).run(result=result)


class TestCreateSQSQueueActor(SQSTestCase):

    @testing.gen_test
    def test_execute(self):
        self.actor = sqs.Create('Unit Test Action',
                                {'name': 'unit-test-queue'})

        self.conn().create_queue.return_value = boto.sqs.queue.Queue()

        yield self.actor.execute()

        self.conn().create_queue.assert_called_once_with('unit-test-queue')

    @testing.gen_test
    def test_execute_dry(self):
        self.actor = sqs.Create('Unit Test Action',
                                {'name': 'unit-test-queue'},
                                dry=True)

        self.conn().create_queue.return_value = boto.sqs.queue.Queue()

        yield self.actor.execute()

        self.assertFalse(self.conn().create_queue.called)

    @testing.gen_test
    def test_execute_with_error(self):
        self.actor = sqs.Create('Unit Test Action',
                                {'name': 'unit-test-queue'})

        self.conn().create_queue.return_value = False
        with self.assertRaises(Exception):
            yield self.actor.execute()

        self.conn().create_queue.assert_called_once_with('unit-test-queue')


class TestDeleteSQSQueueActor(SQSTestCase):

    @testing.gen_test
    def test_execute(self):
        self.actor = sqs.Delete('Unit Test Action',
                                {'name': 'unit-test-queue'})

        self.conn().delete_queue.return_value = True
        yield self.actor.execute()

        self.assertTrue(self.conn.return_value.get_queue.called)
        self.assertTrue(self.conn.return_value.delete_queue.called)

    @testing.gen_test
    def test_execute_dry(self):
        self.actor = sqs.Delete('Unit Test Action',
                                {'name': 'unit-test-queue'},
                                dry=True)

        self.conn().delete_queue.return_value = True
        yield self.actor.execute()

        self.assertTrue(self.conn.return_value.get_queue.called)
        self.assertFalse(self.conn.return_value.delete_queue.called)

    @testing.gen_test
    def test_execute_with_error(self):
        self.actor = sqs.Delete('Unit Test Action',
                                {'name': 'unit-test-queue'})

        self.conn().get_queue.return_value = None

        with self.assertRaises(Exception):
            yield self.actor.execute()

        self.assertFalse(self.conn.return_value.delete_queue.called)

    @testing.gen_test
    def test_execute_with_failure(self):
        self.actor = sqs.Delete('Unit Test Action',
                                {'name': 'unit-test-queue'})

        self.conn().delete_queue.return_value = False

        with self.assertRaises(Exception):
            yield self.actor.execute()

        self.assertTrue(self.conn.return_value.delete_queue.called)


class TestWaitUntilQueueEmptyActor(SQSTestCase):

    @testing.gen_test
    def test_execute(self):
        self.actor = sqs.WaitUntilEmpty('UTA!',
                                        {'name': 'unit-test-queue'})

        self.conn().get_queue().count.return_value = 0
        yield self.actor.execute()

    @testing.gen_test
    def test_wrong_queuename(self):
        self.actor = sqs.WaitUntilEmpty('UTA!',
                                        {'name': 'unit-test-queue'})

        self.conn().get_queue.return_value = None
        with self.assertRaises(Exception):
            yield self.actor.execute()

    @testing.gen_test
    def test_dry_run(self):
        self.actor = sqs.WaitUntilEmpty('UTA!',
                                        {'name': 'unit-test-queue'},
                                        dry=True)

        self.conn().get_queue().count.return_value = 10  # Note: NOT zero
        yield self.actor.execute()

        # Dry run means count should not be called.
        self.assertFalse(self.conn().get_queue().count.called)

    @testing.gen_test
    def test_sleep_and_retry(self):
        self.actor = sqs.WaitUntilEmpty('UTA!',
                                        {'name': 'unit-test-queue'})

        self.conn().get_queue().count.side_effect = [3, 2, 1, 0]
        yield self.actor._wait('unit-name', sleep=0)

        self.assertEquals(self.conn().get_queue().count.call_count, 4)
