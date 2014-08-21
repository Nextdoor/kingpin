import logging
import mock

from tornado import testing
from tornado import gen

from kingpin.actors import aws

log = logging.getLogger(__name__)

import boto.sqs.connection
import boto.sqs.queue


class TestCreateSQSQueueActor(testing.AsyncTestCase):

    @testing.gen_test
    def test_execute(self):
        self.actor = aws.CreateSQSQueue('Unit Test Action',
                                        {'name': 'unit-test-queue'})

        with mock.patch.object(boto.sqs.connection, 'SQSConnection') as sqsc:
            connection = mock.Mock()
            connection.create_queue = mock.Mock()
            sqsc.return_value = connection

            connection.create_queue.return_value = boto.sqs.queue.Queue()

            yield self.actor.execute()

        connection.create_queue.assert_called_once_with('unit-test-queue')

    @testing.gen_test
    def test_execute_with_error(self):
        self.actor = aws.CreateSQSQueue('Unit Test Action',
                                        {'name': 'unit-test-queue'})

        with mock.patch.object(boto.sqs.connection, 'SQSConnection') as sqsc:
            connection = mock.Mock()
            connection.create_queue = mock.Mock()
            sqsc.return_value = connection

            # This will cause an error
            connection.create_queue.return_value = None

            with self.assertRaises(Exception):
                yield self.actor.execute()

        connection.create_queue.assert_called_once_with('unit-test-queue')
