import logging

from tornado import testing
import boto.sqs.connection
import boto.sqs.queue
import mock

from kingpin.actors import exceptions
from kingpin.actors.aws import settings
from kingpin.actors.aws import sqs
from kingpin.actors.test.helper import mock_tornado

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


class TestSQSBaseActor(SQSTestCase):

    @testing.gen_test
    def test_fetch(self):

        all_queues = [mock.Mock(), mock.Mock(), mock.Mock(), mock.Mock()]
        all_queues[0].name = '1-miss'
        all_queues[1].name = '2-miss'
        all_queues[2].name = '3-match'
        all_queues[3].name = '4-match'

        self.conn().get_all_queues.return_value = all_queues

        actor = sqs.SQSBaseActor('Unit Test Action', {
            'name': 'unit-test-queue',
            'region': 'us-east-1'})

        results = yield actor._fetch_queues('match')

        self.assertEquals(results, [all_queues[2], all_queues[3]])


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
        ret = yield self.actor.execute()
        self.assertEquals(ret, None)
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

        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            yield self.actor.execute()
        self.conn().create_queue.assert_called_once_with('unit-test-queue')


class TestDeleteSQSQueueActor(SQSTestCase):

    @testing.gen_test
    def test_delete_queue(self):
        actor = sqs.Delete('Unit Test Action',
                           {'name': 'unit-test-queue',
                            'region': 'us-west-2'})
        q = mock.Mock()
        q.name = 'unit-test-queue'
        self.conn().delete_queue.return_value = False
        with self.assertRaises(sqs.QueueDeletionFailed):
            yield actor._delete_queue(q)

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

        self.conn().get_all_queues = mock.Mock(return_value=[])
        # Should fail even in dry run, if idempotent flag is not there.
        settings.SQS_RETRY_DELAY = 0
        reload(sqs)
        with self.assertRaises(sqs.QueueNotFound):
            yield actor.execute()

    @testing.gen_test
    def test_execute_with_failure(self):
        settings.SQS_RETRY_DELAY = 0
        reload(sqs)
        actor = sqs.Delete('Unit Test Action',
                           {'name': 'non-existent-queue',
                            'region': 'us-west-2'})

        with self.assertRaises(sqs.QueueNotFound):
            yield actor.execute()

    @testing.gen_test
    def test_execute_idempotent(self):
        settings.SQS_RETRY_DELAY = 0
        reload(sqs)
        actor = sqs.Delete('Unit Test Action',
                           {'name': 'non-existent-queue',
                            'region': 'us-west-2',
                            'idempotent': True})

        # Should work w/out raising an exception.
        yield actor.execute()


class TestWaitUntilQueueEmptyActor(SQSTestCase):

    @testing.gen_test
    def test_execute(self):
        actor = sqs.WaitUntilEmpty('UTA!',
                                   {'name': 'unit-test-queue',
                                    'region': 'us-west-2'})

        actor._wait = mock_tornado(True)
        actor._fetch_queues = mock_tornado([mock.Mock()])
        yield actor.execute()

    @testing.gen_test
    def test_execute_empty(self):
        actor = sqs.WaitUntilEmpty('UTA!',
                                   {'name': 'unit-test-queue',
                                    'region': 'us-west-2',
                                    'required': True})

        actor._wait = mock_tornado(True)
        actor._fetch_queues = mock_tornado()
        with self.assertRaises(sqs.QueueNotFound):
            yield actor.execute()

    @testing.gen_test
    def test_wait(self):
        actor = sqs.WaitUntilEmpty('UTA!',
                                   {'name': 'unit-test-queue',
                                    'region': 'us-west-2'})
        queue = mock.Mock()
        queue.count.side_effect = [1, 0, 0]
        attr = 'ApproximateNumberOfMessagesNotVisible'
        queue.get_attributes.side_effect = [{attr: u'0'},
                                            {attr: u'1'},
                                            {attr: u'0'}]
        yield actor._wait(queue, sleep=0)
        self.assertEqual(queue.count.call_count, 3)

    @testing.gen_test
    def test_wait_dry(self):
        actor = sqs.WaitUntilEmpty('UTA!',
                                   {'name': 'unit-test-queue',
                                    'region': 'us-west-2'},
                                   dry=True)
        queue = mock.Mock()
        queue.count.side_effect = [1, 2]  # Not zero!
        yield actor._wait(queue, sleep=0)
        self.assertEqual(queue.count.call_count, 0)
