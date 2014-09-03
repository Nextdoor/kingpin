import logging

from tornado import testing
import boto.sqs.connection
import boto.sqs.queue
import mock

from kingpin.actors.aws import settings
from kingpin.actors.aws import sqs

log = logging.getLogger(__name__)


class SQSTestCase(testing.AsyncTestCase):

    def setUp(self):
        super(SQSTestCase, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'

    @mock.patch.object(boto.sqs.connection, 'SQSConnection')
    def run(self, result, sqsc):
        self.conn = sqsc
        super(SQSTestCase, self).run(result=result)


class TestCreateSQSQueueActor(SQSTestCase):

    @testing.gen_test
    def test_require_env(self):
        settings.AWS_ACCESS_KEY_ID = ''
        with self.assertRaises(Exception):
            sqs.WaitUntilEmpty('Unit Test Action', {
                'name': 'unit-test-queue',
                'region': 'us-west-2'})

    @testing.gen_test
    def test_check_regions(self):
        with self.assertRaises(Exception):
            sqs.SQSBaseActor('Unit Test Action', {
                'name': 'unit-test-queue',
                'region': 'bonkers'})  # This should fail

        actor = sqs.SQSBaseActor('Unit Test Action', {
            'name': 'unit-test-queue',
            'region': 'us-east-1'})

        self.assertEquals(actor._get_region('us-east-1').name, 'us-east-1')

    @testing.gen_test
    def test_execute(self):
        self.actor = sqs.Create('Unit Test Action',
                                {'name': 'unit-test-queue',
                                 'region': 'us-west-2'})

        self.conn().create_queue.return_value = boto.sqs.queue.Queue()

        yield self.actor.execute()

        self.conn().create_queue.assert_called_once_with('unit-test-queue')

    @testing.gen_test
    def test_execute_dry(self):
        self.actor = sqs.Create('Unit Test Action',
                                {'name': 'unit-test-queue',
                                 'region': 'us-west-2'},
                                dry=True)

        self.conn().create_queue.return_value = boto.sqs.queue.Queue()

        yield self.actor.execute()

        self.assertFalse(self.conn().create_queue.called)

    @testing.gen_test
    def test_execute_with_error(self):
        self.actor = sqs.Create('Unit Test Action',
                                {'name': 'unit-test-queue',
                                 'region': 'us-west-2'})

        self.conn().create_queue.return_value = False
        with self.assertRaises(Exception):
            yield self.actor.execute()

        self.conn().create_queue.assert_called_once_with('unit-test-queue')


class TestDeleteSQSQueueActor(SQSTestCase):

    @testing.gen_test
    def test_execute(self):
        actor = sqs.Delete('Unit Test Action',
                           {'name': 'unit-test-queue',
                            'region': 'us-west-2'})

        q = mock.Mock()
        q.name = 'unit-test-queue'
        self.conn().get_all_queues = mock.Mock(return_value=[q])
        self.conn().delete_queue.return_value = True
        yield actor.execute()

        self.assertTrue(self.conn().get_all_queues.called)
        self.assertTrue(self.conn().delete_queue.called)

    @testing.gen_test
    def test_execute_dry(self):
        actor = sqs.Delete('Unit Test Action',
                           {'name': 'unit-test-queue',
                            'region': 'us-west-2'},
                           dry=True)

        q = mock.Mock()
        q.name = 'unit-test-queue'
        self.conn().get_all_queues = mock.Mock(return_value=[q])
        self.conn().delete_queue.return_value = True
        yield actor.execute()

        self.assertTrue(self.conn().get_all_queues.called)
        self.assertFalse(self.conn().delete_queue.called)

    @testing.gen_test
    def test_execute_with_failure(self):
        settings.SQSRETRYDELAY = 0
        reload(sqs)
        actor = sqs.Delete('Unit Test Action',
                           {'name': 'non-existent-queue',
                            'region': 'us-west-2'})

        with self.assertRaises(Exception):
            yield actor.execute()


class TestWaitUntilQueueEmptyActor(SQSTestCase):

    @testing.gen_test
    def test_execute(self):
        self.actor = sqs.WaitUntilEmpty('UTA!',
                                        {'name': 'unit-test-queue',
                                         'region': 'us-west-2'})

        self.conn().get_queue().count.return_value = 0
        yield self.actor.execute()

    @testing.gen_test
    def test_wrong_queuename(self):
        self.actor = sqs.WaitUntilEmpty('UTA!',
                                        {'name': 'unit-test-queue',
                                         'region': 'us-west-2'})

        self.conn().get_queue.return_value = None
        with self.assertRaises(Exception):
            yield self.actor.execute()

    @testing.gen_test
    def test_dry_run(self):
        self.actor = sqs.WaitUntilEmpty('UTA!',
                                        {'name': 'unit-test-queue',
                                         'region': 'us-west-2'},
                                        dry=True)

        self.conn().get_queue().count.return_value = 10  # Note: NOT zero
        yield self.actor.execute()

        # Dry run means count should not be called.
        self.assertFalse(self.conn().get_queue().count.called)

    @testing.gen_test
    def test_sleep_and_retry(self):
        self.actor = sqs.WaitUntilEmpty('UTA!',
                                        {'name': 'unit-test-queue',
                                         'region': 'us-west-2'})

        self.conn().get_queue().count.side_effect = [3, 2, 1, 0]
        yield self.actor._wait('unit-name', sleep=0)

        self.assertEquals(self.conn().get_queue().count.call_count, 4)
