import logging
import mock

from tornado import testing

from kingpin.actors.aws import sqs

log = logging.getLogger(__name__)

import boto.sqs.connection
import boto.sqs.queue


class TestCreateSQSQueueActor(testing.AsyncTestCase):

    @testing.gen_test
    def test_execute(self):
        self.actor = sqs.Create('Unit Test Action',
                                {'name': 'unit-test-queue'})

        with mock.patch.object(boto.sqs.connection, 'SQSConnection') as sqsc:
            sqsc().create_queue.return_value = boto.sqs.queue.Queue()

            yield self.actor.execute()

        sqsc().create_queue.assert_called_once_with('unit-test-queue')

    @testing.gen_test
    def test_execute_dry(self):
        self.actor = sqs.Create('Unit Test Action',
                                {'name': 'unit-test-queue'},
                                dry=True)

        with mock.patch.object(boto.sqs.connection, 'SQSConnection') as sqsc:
            sqsc().create_queue.return_value = boto.sqs.queue.Queue()

            yield self.actor.execute()

        self.assertFalse(sqsc().create_queue.called)

    @testing.gen_test
    def test_execute_with_error(self):
        self.actor = sqs.Create('Unit Test Action',
                                {'name': 'unit-test-queue'})

        with mock.patch.object(boto.sqs.connection, 'SQSConnection') as sqsc:
            sqsc().create_queue.return_value = False
            with self.assertRaises(Exception):
                yield self.actor.execute()

        sqsc().create_queue.assert_called_once_with('unit-test-queue')


class TestDeleteSQSQueueActor(testing.AsyncTestCase):

    @testing.gen_test
    def test_execute(self):
        self.actor = sqs.Delete('Unit Test Action',
                                {'name': 'unit-test-queue'})

        with mock.patch.object(boto.sqs.connection, 'SQSConnection') as sqsc:
            sqsc().delete_queue.return_value = True
            yield self.actor.execute()

        self.assertTrue(sqsc.return_value.get_queue.called)
        self.assertTrue(sqsc.return_value.delete_queue.called)

    @testing.gen_test
    def test_execute_dry(self):
        self.actor = sqs.Delete('Unit Test Action',
                                {'name': 'unit-test-queue'},
                                dry=True)

        with mock.patch.object(boto.sqs.connection, 'SQSConnection') as sqsc:
            sqsc().delete_queue.return_value = True
            yield self.actor.execute()

        self.assertTrue(sqsc.return_value.get_queue.called)
        self.assertFalse(sqsc.return_value.delete_queue.called)

    @testing.gen_test
    def test_execute_with_error(self):
        self.actor = sqs.Delete('Unit Test Action',
                                {'name': 'unit-test-queue'})

        with mock.patch.object(boto.sqs.connection, 'SQSConnection') as sqsc:

            sqsc().get_queue.return_value = None

            with self.assertRaises(Exception):
                yield self.actor.execute()

        self.assertFalse(sqsc.return_value.delete_queue.called)

    @testing.gen_test
    def test_execute_with_failure(self):
        self.actor = sqs.Delete('Unit Test Action',
                                {'name': 'unit-test-queue'})

        with mock.patch.object(boto.sqs.connection, 'SQSConnection') as sqsc:

            sqsc().delete_queue.return_value = False

            with self.assertRaises(Exception):
                yield self.actor.execute()

        self.assertTrue(sqsc.return_value.delete_queue.called)
