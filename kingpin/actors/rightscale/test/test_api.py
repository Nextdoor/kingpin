import logging
import mock
import simplejson

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
    def test_find_cookbook(self):
        self.client._client = mock.Mock()
        resource = mock.Mock(name='Resource')
        resource.soul = {'metadata': {'recipes': {'cook::book': True}}}
        self.client._client.cookbooks.index.return_value = [resource]
        ret = yield self.client.find_cookbook('cook::book')
        self.assertEquals(resource, ret)

    @testing.gen_test
    def test_find_cookbook_empty_result(self):
        with mock.patch.object(api.rightscale_util, 'find_by_name') as u_mock:
            u_mock.return_value = None
            ret = yield self.client.find_cookbook('cook::book')
            self.assertEquals(None, ret)

    @testing.gen_test
    def test_find_right_script(self):
        with mock.patch.object(api.rightscale_util, 'find_by_name') as u_mock:
            u_mock.return_value = 1
            ret = yield self.client.find_right_script('test')
            u_mock.assert_called_once_with(
                self.mock_client.right_scripts, 'test', exact=True)
            self.assertEquals(1, ret)

    @testing.gen_test
    def test_find_right_script_empty_result(self):
        with mock.patch.object(api.rightscale_util, 'find_by_name') as u_mock:
            u_mock.return_value = None
            ret = yield self.client.find_right_script('test')
            u_mock.assert_called_once_with(
                self.mock_client.right_scripts, 'test', exact=True)
            self.assertEquals(None, ret)

    @testing.gen_test
    def test_clone_server_array(self):
        # First, create the rightscale.server_array api mock
        sa_rsr_mock = mock.MagicMock()
        self.mock_client.server_arrays = sa_rsr_mock

        # Mock the input template array
        source_mock = mock.MagicMock(name='source_template')
        source_mock.soul = {'name': 'Mocked ServerArray'}
        source_mock.self.path = '/a/b/1234'

        # Next, create the returned server array resource mock
        clone_mock = mock.MagicMock()
        clone_mock.soul = {'name': 'Mocked ServerArray'}
        sa_rsr_mock.clone.return_value = clone_mock

        # Clone the array
        ret = yield self.client.clone_server_array(source_mock)
        self.mock_client.server_arrays.clone.assert_called_once_with(
            res_id=1234)
        self.assertEquals(ret, clone_mock)

    @testing.gen_test
    def test_destroy_server_array(self):
        array_mock = mock.MagicMock(name='unittest_array')
        array_mock.soul = {'name': 'Mocked ServerArray'}
        array_mock.self.path = '/a/b/1234'

        self.mock_client.server_arrays.destroy.return_value = True
        ret = yield self.client.destroy_server_array(array_mock)
        self.mock_client.server_arrays.destroy.assert_called_once_with(
            res_id=1234)

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
    def test_get_server_array_inputs(self):
        array = mock.Mock()
        ret = yield self.client.get_server_array_inputs(array)

        self.assertEquals(
            ret,
            array.next_instance.show().inputs.index())

    @testing.gen_test
    def test_update_server_array_inputs(self):
        ni_mock = mock.MagicMock(name='next_instance')
        ni_mock.inputs.multi_update.return_value = None
        sa_mock = mock.MagicMock(name='server_array')
        sa_mock.next_instance.show.return_value = ni_mock

        inputs = {'inputs[ELB_NAME]': 'text:foobar'}

        ret = yield self.client.update_server_array_inputs(
            sa_mock, inputs=inputs)
        self.assertEquals(ret, None)
        sa_mock.next_instance.show.assert_called_once_with()
        ni_mock.assert_has_calls([
            mock.call.inputs.multi_update(params=inputs)
        ])

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
    def test_launch_server_array(self):
        array_mock = mock.MagicMock(name='fake_array')
        array_mock.soul = {'name': 'fake array to launch'}
        array_mock.self.path = '/a/b/1234'
        instance_mock = mock.MagicMock(name='fake_instance')
#        sa_rsr_mock = mock.MagicMock(name='sa_resource_mock')
#        sa_rsr_mock.launch.return_value = instance_mock
        self.mock_client.server_arrays.launch.return_value = instance_mock

        ret = yield self.client.launch_server_array(array_mock)
        self.mock_client.server_arrays.launch.assert_called_once_with(
            res_id=1234)
        self.assertEquals(ret, instance_mock)

    @testing.gen_test
    def test_terminate_server_array_instances(self):
        array_mock = mock.MagicMock(name='fake array')
        array_mock.soul = {'name': 'fake array'}
        array_mock.self.path = '/a/b/1234'

        # Mock out the multi_terminate command and the task it returns
        mock_task = mock.MagicMock(name='fake task')

        def action(*args, **kwargs):
            return mock_task
        self.mock_client.server_arrays.multi_terminate.side_effect = action

        # Mock out the wait_for_task method to return quickly
        ret = yield self.client.terminate_server_array_instances(array_mock)
        self.mock_client.server_arrays.multi_terminate.assert_called_once_with(
            res_id=1234)
        self.assertEquals(mock_task, ret)

    @testing.gen_test
    def test_terminate_server_array_instances_422_error(self):
        array_mock = mock.MagicMock(name='fake array')
        array_mock.soul = {'name': 'fake array'}
        array_mock.self.path = '/a/b/1234'

        # Mock out the multi_terminate command and the task it returns
        def action(*args, **kwargs):
            response = mock.MagicMock()
            response.status_code = 422
            raise requests.exceptions.HTTPError(response=response)
        self.mock_client.server_arrays.multi_terminate.side_effect = action

        ret = yield self.client.terminate_server_array_instances(array_mock)
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

        completed = mock.MagicMock(name='mock_output_completed')
        completed.soul = {'name': 'fake_task',
                          'summary': 'completed: done'}

        failed = mock.MagicMock(name='mock_output_failed')
        failed.soul = {'name': 'fake_task',
                       'summary': 'failed: crap'}

        in_process = mock.MagicMock(name='mock_output_in_process')
        in_process.soul = {'name': 'fake_task',
                           'summary': '30%: in process'}

        unknown = mock.MagicMock(name='mock_output_unknown')
        unknown.soul = {'name': 'fake_task',
                        'summary': 'unknown return'}

        # task succeeds
        mock_task = mock.MagicMock(name='fake task')
        mock_task.self.show.side_effect = [queued, in_process, success]
        ret = yield self.client.wait_for_task(mock_task, sleep=0.01)
        self.assertEquals(ret, True)
        mock_task.assert_has_calls(
            [mock.call.self.show(), mock.call.self.show(),
             mock.call.self.show()])

        # task completed
        mock_task = mock.MagicMock(name='fake task')
        mock_task.self.show.side_effect = [queued, in_process, completed]
        ret = yield self.client.wait_for_task(mock_task, sleep=0.01)
        self.assertEquals(ret, True)
        mock_task.assert_has_calls(
            [mock.call.self.show(), mock.call.self.show(),
             mock.call.self.show()])

        # task fails
        mock_task = mock.MagicMock(name='fake task')
        mock_task.self.show.side_effect = [queued, in_process, failed]
        ret = yield self.client.wait_for_task(mock_task, sleep=0.01)
        self.assertEquals(ret, False)
        mock_task.assert_has_calls(
            [mock.call.self.show(), mock.call.self.show(),
             mock.call.self.show()])

    @testing.gen_test
    def test_run_executable_on_instances(self):
        mock_instance = mock.MagicMock(name='unittest-instance')
        mock_instance.soul = {'name': 'unittest-instance'}
        mock_instance.links = {'self': '/foo/bar'}
        mock_instance.self.path = '/a/b/1234'

        mock_tracker = mock.MagicMock(name='tracker')

        @gen.coroutine
        def fake_web_request(url, post):
            mock_tracker.web_request(url, post)
            raise gen.Return(True)
        self.client.make_generic_request = fake_web_request

        @gen.coroutine
        def fake_find_right_script(name):
            mock_tracker.right_script(name)
            fake_script = mock.MagicMock()
            fake_script.href = '/fake'
            raise gen.Return(fake_script)
        self.client.find_right_script = fake_find_right_script

        @gen.coroutine
        def fake_find_right_script_return_none(name):
            raise gen.Return()

        inputs = {'inputs[ELB_NAME]': 'something'}

        # Initial test with a simple recipe
        yield self.client.run_executable_on_instances(
            'my::recipe', inputs, [mock_instance])
        mock_tracker.web_request.assert_called_once_with(
            '/foo/bar/run_executable',
            {'inputs[ELB_NAME]': 'something', 'recipe_name': 'my::recipe'})

        # Test with a RightScript instead
        mock_tracker.web_request.reset_mock()
        yield self.client.run_executable_on_instances(
            'my_script', inputs, [mock_instance])
        mock_tracker.web_request.assert_called_once_with(
            '/foo/bar/run_executable',
            {'inputs[ELB_NAME]': 'something', 'right_script_href': '/fake'})
        mock_tracker.right_script.assert_called_once_with('my_script')

        # Test with a missing RightScript
        self.client.find_right_script = fake_find_right_script_return_none
        with self.assertRaises(api.ServerArrayException):
            yield self.client.run_executable_on_instances(
                'my_script', inputs, [mock_instance])

    @testing.gen_test
    def test_run_executable_on_instances_raise_exceptions(self):
        mock_instance = mock.MagicMock(name='unittest-instance')
        mock_instance.soul = {'name': 'unittest-instance'}
        mock_instance.links = {'self': '/foo/bar'}
        mock_instance.self.path = '/a/b/1234'

        @gen.coroutine
        def fake_web_request(url, post):
            msg = '422 Client Error: Unprocessable Entity'
            raise requests.exceptions.HTTPError(msg)
        self.client.make_generic_request = fake_web_request

        # Test with invalid inputs raising a 422 error
        self.client.make_generic_request = fake_web_request
        with self.assertRaises(api.ServerArrayException):
            yield self.client.run_executable_on_instances(
                'my::recipe', {}, [mock_instance])

    @testing.gen_test
    def test_make_generic_request(self):
        # Mock out the requests library client that the rightscale object
        # thinks its using.
        requests_mock_client = mock.MagicMock(name='rightscale.client mock')
        self.mock_client.client = requests_mock_client

        response_mock = mock.MagicMock(name='response mock')
        response_mock.headers = {}
        requests_mock_client.post.return_value = response_mock
        requests_mock_client.get.return_value = response_mock

        # Test: Simple POST that returns JSON
        response_mock.json.return_value = "{'name': 'fake soul'}"
        requests_mock_client.reset_mock()
        with mock.patch('rightscale.rightscale.Resource') as r_mock:
            resource_mock = mock.MagicMock(name='resource_mock')
            r_mock.return_value = resource_mock
            ret = yield self.client.make_generic_request(
                '/foo', post={'a': 'b'})
            self.assertEquals(resource_mock, ret)
            requests_mock_client.post.assert_called_once_with(
                '/foo', data={'a': 'b'})

        # Test 2: Simple GET that returns JSON
        response_mock.json.return_value = "{'name': 'fake soul'}"
        requests_mock_client.reset_mock()
        with mock.patch('rightscale.rightscale.Resource') as r_mock:
            resource_mock = mock.MagicMock(name='resource_mock')
            r_mock.return_value = resource_mock
            ret = yield self.client.make_generic_request('/foo')
            self.assertEquals(resource_mock, ret)
            requests_mock_client.get.assert_called_once_with('/foo')

        # Test 3: Simple POST that returns a location header
        response_mock.headers = {'location': '/foobar'}
        response_mock.json.return_value = "{'name': 'fake soul'}"
        requests_mock_client.reset_mock()
        with mock.patch('rightscale.rightscale.Resource') as r_mock:
            resource_mock = mock.MagicMock(name='resource_mock')
            r_mock.return_value = resource_mock
            ret = yield self.client.make_generic_request(
                '/foo', post={'a': 'b'})
            self.assertEquals(resource_mock, ret)
            requests_mock_client.post.assert_called_once_with(
                '/foo', data={'a': 'b'})
            requests_mock_client.get.assert_called_once_with('/foobar')

        # Test 4: Simple GET that returns no JSON
        response_mock.json.side_effect = simplejson.scanner.JSONDecodeError(
            'a', 'b', 0)
        ret = yield self.client.make_generic_request('/foo')
        self.assertEquals(None, ret)
