import logging
import mock

from tornado import gen
from tornado import testing
import requests

from kingpin.actors.rightscale import api


log = logging.getLogger(__name__)


class TestRightScale(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestRightScale, self).setUp()

        self.token = 'test'
        self.client = api.RightScale(self.token)
        self.mock_client = mock.MagicMock()
        self.client._client = self.mock_client

#    def test_get_res_id(self):
        # TODO: Figure out how to test this?
        #
        # mocked_resource = mock.Magic
        # ret = self.client._get_res_id(mocked_resource)
        # self.assertEquals(ret, '12345')

    @testing.gen_test
    def test_login(self):
        # Regular successfull call
        self.mock_client.login.return_value = True
        ret = yield self.client.login()
        self.mock_client.login.assert_called_once_with()
        self.assertEquals(None, ret)

    @testing.gen_test
    def test_login_400_error(self):
        # Ensure that if we raise an exception in the call to RS,
        # that the Exception is re-raised through the thread to
        # the caller.
        msg = '400 Client Error: Bad Request'
        error = requests.exceptions.HTTPError(msg)
        self.mock_client.login.side_effect = error
        with self.assertRaises(requests.exceptions.HTTPError):
            yield self.client.login()

        self.mock_client.login.assert_called_once_with()

    @testing.gen_test
    def test_find_server_arrays(self):
        with mock.patch.object(api.rightscale_util, 'find_by_name') as u_mock:
            u_mock.return_value = [1, 2, 3]
            ret = yield self.client.find_server_arrays('test', exact=True)
            u_mock.assert_called_once_with(
                self.mock_client.server_arrays, 'test', exact=True)
            self.assertEquals([1, 2, 3], ret)
            u_mock.reset()

        with mock.patch.object(api.rightscale_util, 'find_by_name') as u_mock:
            u_mock.return_value = [1, 2, 3]
            ret = yield self.client.find_server_arrays('test2', exact=False)
            u_mock.assert_called_once_with(
                self.mock_client.server_arrays, 'test2', exact=False)
            self.assertEquals([1, 2, 3], ret)

    @testing.gen_test
    def test_find_server_arrays_empty_result(self):
        with mock.patch.object(api.rightscale_util, 'find_by_name') as u_mock:
            u_mock.return_value = None
            ret = yield self.client.find_server_arrays('test', exact=True)
            u_mock.assert_called_once_with(
                self.mock_client.server_arrays, 'test', exact=True)
            self.assertEquals(None, ret)

    @testing.gen_test
    def test_clone_server_array(self):
        # First, create the rightscale.server_array api mock
        sa_rsr_mock = mock.MagicMock()
        self.mock_client.server_arrays = sa_rsr_mock

        # Next, create the returned server array resource mock
        sa_mock = mock.MagicMock()
        sa_mock.soul = {'name': 'Mocked ServerArray'}
        sa_rsr_mock.clone.return_value = sa_mock

        # Clone the array
        ret = yield self.client.clone_server_array('source_array_id')
        self.assertEquals(ret, sa_mock)

    @testing.gen_test
    def test_destroy_server_array(self):
        self.mock_client.server_arrays.destroy.return_value = True
        ret = yield self.client.destroy_server_array(123)
        self.assertEquals(None, ret)

    @testing.gen_test
    def test_update_server_array(self):
        # Create a mock and the params we're going to pass in
        sa_mock = mock.MagicMock()
        sa_mock.self.update.return_value = True
        sa_mock.self.show.return_value = 'test'
        params = {'server_array[name]': 'new_name'}

        ret = yield self.client.update_server_array(sa_mock, params)
        sa_mock.self.update.assert_called_once_with(params=params)

        self.assertEquals(ret, 'test')

    @testing.gen_test
    def test_get_server_array_current_instances(self):
        # Next, create the list of resources returned by the mock
        fake_instances = [mock.MagicMock(), mock.MagicMock()]
        array_mock = mock.MagicMock()
        array_mock.soul = {'name': 'fake array'}
        array_mock.current_instances.index.return_value = fake_instances

        ret = yield self.client.get_server_array_current_instances(array_mock)
        self.assertEquals(fake_instances, ret)

    @testing.gen_test
    def test_terminate_server_array_instances(self):
        # Mock out the multi_terminate command and the task it returns
        mock_task = mock.MagicMock(name='fake task')

        def action(*args, **kwargs):
            return mock_task
        self.mock_client.server_arrays.multi_terminate.side_effect = action

        @gen.coroutine
        def fake_wait(*args, **kwargs):
            return gen.Return()

        # Mock out the wait_for_task method to return quickly
        with mock.patch.object(self.client, 'wait_for_task') as mock_wait:
            mock_wait.side_effect = fake_wait
            ret = yield self.client.terminate_server_array_instances(123)
        self.assertEquals(None, ret)

    @testing.gen_test
    def test_terminate_server_array_instances_422_error(self):
        def action(*args, **kwargs):
            response = mock.MagicMock()
            response.status_code = 422
            raise requests.exceptions.HTTPError(response=response)
        self.mock_client.server_arrays.multi_terminate.side_effect = action

        ret = yield self.client.terminate_server_array_instances(123)
        self.assertEquals(None, ret)

    @testing.gen_test
    def test_wait_for_task(self):
        # Create some fake task outputs
        queued = mock.MagicMock(name='mock_output_queued')
        queued.soul = {'name': 'fake_task',
                       'summary': 'queued: still going'}

        success = mock.MagicMock(name='mock_output_success')
        success.soul = {'name': 'fake_task',
                        'summary': 'success: done'}

        failed = mock.MagicMock(name='mock_output_failed')
        failed.soul = {'name': 'fake_task',
                       'summary': 'failed: crap'}

        in_process = mock.MagicMock(name='mock_output_failed')
        in_process.soul = {'name': 'fake_task',
                           'summary': '30%: in process'}

        # Test 1... task succeeds
        mock_task = mock.MagicMock(name='fake task')
        mock_task.self.show.side_effect = [queued, in_process, success]
        ret = yield self.client.wait_for_task(mock_task, sleep=0.1)
        self.assertEquals(ret, True)
        mock_task.assert_has_calls(
            [mock.call.self.show(), mock.call.self.show(),
             mock.call.self.show()])

        # Test 2... task fails
        mock_task = mock.MagicMock(name='fake task')
        mock_task.self.show.side_effect = [queued, in_process, failed]
        ret = yield self.client.wait_for_task(mock_task, sleep=0.1)
        self.assertEquals(ret, False)
        mock_task.assert_has_calls(
            [mock.call.self.show(), mock.call.self.show(),
             mock.call.self.show()])

    @testing.gen_test
    def test_thread_coroutine(self):
        # Create a method that we'll call and have it return
        mock_thing = mock.MagicMock()
        mock_thing.action.return_value = True

        ret = yield api.thread_coroutine(mock_thing.action)
        self.assertEquals(ret, True)
        mock_thing.action.assert_called_once_with()

        # Now, lets have the function actually fail with a requests exception
        mock_thing = mock.MagicMock()
        mock_thing.action.side_effect = [
            requests.exceptions.ConnectionError('doh'), True]

        ret = yield api.thread_coroutine(mock_thing.action)
        self.assertEquals(ret, True)
        mock_thing.action.assert_called_twice_with()

        # Finally, make it fail twice..
        mock_thing = mock.MagicMock()
        mock_thing.action.side_effect = [
            requests.exceptions.ConnectionError('doh'),
            requests.exceptions.ConnectionError('really_doh')]

        with self.assertRaises(requests.exceptions.ConnectionError):
            yield api.thread_coroutine(mock_thing.action)
        mock_thing.action.assert_called_twice_with()

    @testing.gen_test
    def test_retry_with_backoff(self):

        # Define a method that will fail every time
        @gen.coroutine
        @api.retry(excs=(requests.exceptions.HTTPError), retries=3)
        def raise_exception():
            raise requests.exceptions.HTTPError('Failed')

        with self.assertRaises(requests.exceptions.HTTPError):
            yield raise_exception()

        # Now a method that works
        @gen.coroutine
        @api.retry(excs=(requests.exceptions.HTTPError), retries=3)
        def work():
            raise gen.Return(True)

        ret = yield work()
        self.assertEquals(ret, True)
