import logging
import mock
import simplejson

from tornado import gen
from tornado import testing
import requests

from kingpin.actors.rightscale import api
from kingpin.actors.test import helper


log = logging.getLogger(__name__)


class TestRightScale(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestRightScale, self).setUp()

        self.token = 'test'
        self.client = api.RightScale(self.token)
        self.mock_client = mock.MagicMock()
        self.client._client = self.mock_client

    def test_get_res_id(self):
        resource = mock.Mock()
        resource.self.path = '/foo/bar/12345'
        ret = self.client.get_res_id(resource)
        self.assertEqual(ret, 12345)

    def test_exception_logger(self):
        response = mock.MagicMock(name='fake_response')
        response.text = 'Error'

        @api.rightscale_error_logger
        def raises_exc():
            raise requests.exceptions.HTTPError(response=response)

        with self.assertRaises(api.RightScaleError):
            raises_exc()

    def test_exception_logger_with_no_text(self):
        response = mock.MagicMock(name='fake_response', spec=[])

        @api.rightscale_error_logger
        def raises_exc():
            raise requests.exceptions.HTTPError(response=response)

        with self.assertRaises(requests.exceptions.HTTPError):
            raises_exc()

    @testing.gen_test
    def test_find_server_arrays(self):
        with mock.patch.object(api.rightscale_util, 'find_by_name') as u_mock:
            array = mock.MagicMock(name='array')
            array.soul = {'name': 'Mocked ServerArray'}
            array.self.path = '/a/b/1234'
            u_mock.return_value = array

            ret = yield self.client.find_server_arrays('test', exact=True)
            u_mock.assert_called_once_with(
                self.mock_client.server_arrays, 'test', exact=True)
            self.assertEqual(array, ret)

        with mock.patch.object(api.rightscale_util, 'find_by_name') as u_mock:
            array1 = mock.MagicMock(name='array1')
            array1.soul = {'name': 'Mocked ServerArray'}
            array1.self.path = '/a/b/1234'
            array2 = mock.MagicMock(name='array2')
            array2.soul = {'name': 'Mocked ServerArray'}
            array2.self.path = '/a/b/1234'
            u_mock.return_value = [array1, array2]

            ret = yield self.client.find_server_arrays('test2', exact=False)
            u_mock.assert_called_once_with(
                self.mock_client.server_arrays, 'test2', exact=False)
            self.assertEqual([array1, array2], ret)

    @testing.gen_test
    def test_find_server_arrays_empty_result(self):
        with mock.patch.object(api.rightscale_util, 'find_by_name') as u_mock:
            u_mock.return_value = None
            ret = yield self.client.find_server_arrays('test', exact=True)
            u_mock.assert_called_once_with(
                self.mock_client.server_arrays, 'test', exact=True)
            self.assertEqual(None, ret)

    @testing.gen_test
    def test_show(self):
        mock_rsr = mock.MagicMock(name='resource')
        mock_rsr.show.return_value = 1
        ret = yield self.client.show(mock_rsr)
        self.assertEqual(1, ret)

    @testing.gen_test
    def test_find_cookbook(self):
        self.client._client = mock.Mock()
        resource = mock.Mock(name='Resource')
        resource.soul = {'metadata': {'recipes': {'cook::book': True}}}
        self.client._client.cookbooks.index.return_value = [resource]
        ret = yield self.client.find_cookbook('cook::book')
        self.assertEqual(resource, ret)

    @testing.gen_test
    def test_find_cookbook_empty_result(self):
        with mock.patch.object(api.rightscale_util, 'find_by_name') as u_mock:
            u_mock.return_value = None
            ret = yield self.client.find_cookbook('cook::book')
            self.assertEqual(None, ret)

    @testing.gen_test
    def test_find_right_script(self):
        with mock.patch.object(api.rightscale_util, 'find_by_name') as u_mock:
            u_mock.return_value = 1
            ret = yield self.client.find_right_script('test')
            u_mock.assert_called_once_with(
                self.mock_client.right_scripts, 'test', exact=True)
            self.assertEqual(1, ret)

    @testing.gen_test
    def test_find_right_script_empty_result(self):
        with mock.patch.object(api.rightscale_util, 'find_by_name') as u_mock:
            u_mock.return_value = None
            ret = yield self.client.find_right_script('test')
            u_mock.assert_called_once_with(
                self.mock_client.right_scripts, 'test', exact=True)
            self.assertEqual(None, ret)

    @testing.gen_test
    def test_find_by_name_and_keys(self):
        # Create a single object that we'll return in our search
        res_mock = mock.MagicMock(name='FakeResource')
        res_mock.soul = {'name': 'FakeResource'}

        # Do a search, but return nothing.
        ret = yield self.client.find_by_name_and_keys(
            collection=mock.MagicMock(), exact=True,
            name='FakeResource', href='/123')
        self.assertEqual(ret, [])

        # Now create a fake Rightscale resource collection object.
        collection = mock.MagicMock(name='collection')

        # Do a search for a single resource with an additional keyword argument
        # passed in to the search
        collection.index.return_value = [res_mock]
        ret = yield self.client.find_by_name_and_keys(
            collection=collection, exact=True,
            name='FakeResource', href='/123')
        self.assertEqual(ret, res_mock)
        collection.index.assert_called_once_with(
            params={'filter[]': ['href==/123', 'name==FakeResource']})
        collection.reset_mock()

        # Same search -- but we return two resources instead of one. We should
        # get both back.
        collection.index.return_value = [res_mock, res_mock]
        ret = yield self.client.find_by_name_and_keys(
            collection=collection, exact=True,
            name='FakeResource', href='/123')
        self.assertEqual(ret, [res_mock, res_mock])
        collection.index.assert_called_once_with(
            params={'filter[]': ['href==/123', 'name==FakeResource']})
        collection.reset_mock()

        # Now do the same search, but with exact=False
        collection.index.return_value = [res_mock]
        ret = yield self.client.find_by_name_and_keys(
            collection=collection, exact=False,
            name='FakeResource', href='/123')
        self.assertEqual(ret, [res_mock])
        collection.index.assert_called_once_with(
            params={'filter[]': ['href==/123', 'name==FakeResource']})
        collection.reset_mock()

    @testing.gen_test
    def test_destroy_resource(self):
        mock_res = mock.MagicMock(res='MockedResource')
        yield self.client.destroy_resource(mock_res)
        mock_res.self.destroy.assert_called_once()

    @testing.gen_test
    def test_create_resource(self):
        mock_res = mock.MagicMock(res='MockedResource')
        yield self.client.create_resource(mock_res, params=123)
        mock_res.self.create.assert_called_once()

    @testing.gen_test
    def test_commit_resource(self):
        mock_res = mock.MagicMock(res='MockedResource')
        mock_res_type = mock.MagicMock()
        yield self.client.commit_resource(
            mock_res, mock_res_type, message='test')
        mock_res_type.commit.assert_has_calls([
            mock.call(res_id=1, params={'commit_message': 'test'})
        ])

    @testing.gen_test
    def test_add_resource_tags(self):
        mock_res = mock.MagicMock(res='MockedResource')
        mock_res.href = '/href'
        tags = ['a', 'b']
        yield self.client.add_resource_tags(mock_res, tags)
        self.mock_client.tags.multi_add.assert_has_calls([
            mock.call(params=[
                ('resource_hrefs[]', '/href'),
                ('tags[]', 'a'),
                ('tags[]', 'b')
            ])
        ])

    @testing.gen_test
    def test_delete_resource_tags(self):
        mock_res = mock.MagicMock(res='MockedResource')
        mock_res.href = '/href'
        tags = ['a', 'b']
        yield self.client.delete_resource_tags(mock_res, tags)
        self.mock_client.tags.multi_delete.assert_has_calls([
            mock.call(params=[
                ('resource_hrefs[]', '/href'),
                ('tags[]', 'a'),
                ('tags[]', 'b')
            ])
        ])

    @testing.gen_test
    def test_get_resource_tags(self):
        mock_res = mock.MagicMock(res='MockedResource')
        mock_res.href = '/href'
        yield self.client.get_resource_tags(mock_res)
        self.mock_client.tags.by_resource.assert_has_calls([
            mock.call(params=[
                ('resource_hrefs[]', '/href'),
            ])
        ])

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
        self.assertEqual(ret, clone_mock)

    @testing.gen_test
    def test_destroy_server_array(self):
        array_mock = mock.MagicMock(name='unittest_array')
        array_mock.soul = {'name': 'Mocked ServerArray'}
        array_mock.self.path = '/a/b/1234'

        self.mock_client.server_arrays.destroy.return_value = True
        ret = yield self.client.destroy_server_array(array_mock)
        self.mock_client.server_arrays.destroy.assert_called_once_with(
            res_id=1234)

        self.assertEqual(None, ret)

    @testing.gen_test
    def test_update(self):
        # Create a mock and the params we're going to pass in
        sa_mock = mock.MagicMock()
        sa_mock.self.update.return_value = True
        sa_mock.self.show.return_value = 'test'
        params = {'server_array[name]': 'new_name'}

        ret = yield self.client.update(sa_mock, params)
        sa_mock.self.update.assert_called_once_with(params=params)

        self.assertEqual(ret, 'test')

    @testing.gen_test
    def test_update_with_string_and_sub_resource(self):
        # Create a mock and the params we're going to pass in
        sa_mock = mock.MagicMock()
        sa_mock.test_res.update.return_value = True
        sa_mock.self.show.return_value = 'test'
        params = 'some_string'

        ret = yield self.client.update(sa_mock, params,
                                       sub_resource='test_res')
        sa_mock.test_res.update.assert_called_once_with(data=params)

        self.assertEqual(ret, 'test')

    @testing.gen_test
    def test_get_server_array_inputs(self):
        array = mock.Mock()
        ret = yield self.client.get_server_array_inputs(array)

        self.assertEqual(
            ret,
            array.next_instance.show().inputs.index())

    @testing.gen_test
    def test_update_inputs(self):
        ni_mock = mock.MagicMock(name='next_instance')
        ni_mock.inputs.multi_update.return_value = None
        sa_mock = mock.MagicMock(name='server_array')
        sa_mock.next_instance.show.return_value = ni_mock

        inputs = {'inputs[ELB_NAME]': 'text:foobar'}

        ret = yield self.client.update_server_array_inputs(
            sa_mock, inputs=inputs)
        self.assertEqual(ret, None)
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
        self.assertEqual(fake_instances, ret)

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
            res_id=1234, params=None)
        self.assertEqual(ret, instance_mock)

    @testing.gen_test
    def test_launch_server_array_launch_0_instance(self):
        array_mock = mock.MagicMock(name='fake_array')
        array_mock.soul = {'name': 'fake array to launch'}
        array_mock.self.path = '/a/b/1234'

        # A count of 0 should pass params=None to the launch call
        ret = yield self.client.launch_server_array(array_mock, count=0)
        self.assertEqual(ret, None)
        self.assertEqual(0, self.mock_client.server_arrays.launch.call_count)

        # A count of None should pass params=None to the launch call
        ret = yield self.client.launch_server_array(array_mock, count=None)
        self.assertEqual(ret, None)

    @testing.gen_test
    def test_launch_server_array_launch_1_instance(self):
        array_mock = mock.MagicMock(name='fake_array')
        array_mock.soul = {'name': 'fake array to launch'}
        array_mock.self.path = '/a/b/1234'
        instance_mock = mock.MagicMock(name='fake_launch_queue')
        self.mock_client.server_arrays.launch.return_value = instance_mock

        # A count of 1 should pass params=None to the launch call
        yield self.client.launch_server_array(array_mock, count=1)
        self.mock_client.server_arrays.launch.assert_called_once_with(
            res_id=1234, params=None)

    @testing.gen_test
    def test_launch_server_array_launch_2_instances(self):
        array_mock = mock.MagicMock(name='fake_array')
        array_mock.soul = {'name': 'fake array to launch'}
        array_mock.self.path = '/a/b/1234'
        instance_mock = mock.MagicMock(name='fake_launch_queue')
        self.mock_client.server_arrays.launch.return_value = instance_mock

        # A count of >1 should pass params={count: 2} to the launch call
        yield self.client.launch_server_array(array_mock, count=2)
        self.mock_client.server_arrays.launch.assert_called_once_with(
            res_id=1234, params={'count': 2})

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
        self.assertEqual(mock_task, ret)

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
        self.assertEqual(None, ret)

    @testing.gen_test
    def test_wait_for_task(self):
        # Create some fake task outputs
        mocked_instance = mock.MagicMock(name='mocked_instance')
        mocked_instance.soul = {'name': 'fake_instance'}

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

        self.client.get_audit_logs = helper.mock_tornado([])
        # task succeeds
        mock_task = mock.MagicMock(name='fake task')
        mock_task.self.show.side_effect = [queued, in_process, success]
        mock_logger = mock.Mock()
        repeat_patcher = mock.patch.object(api.utils,
                                           'create_repeating_log')
        with repeat_patcher as repeat_mock:
            ret = yield self.client.wait_for_task(
                mock_task, task_name='ut-fake-task',
                sleep=0.01, loc_log=mock_logger)
        self.assertEqual(ret, True)
        mock_task.assert_has_calls(
            [mock.call.self.show(), mock.call.self.show(),
             mock.call.self.show()])

        repeat_mock.assert_called_with(
            mock_logger.info,
            'Still waiting on ut-fake-task',
            seconds=0.01)

        # task completed
        mock_task = mock.MagicMock(name='fake task')
        mock_task.self.show.side_effect = [queued, in_process, completed]
        ret = yield self.client.wait_for_task(mock_task, sleep=0.01)
        self.assertEqual(ret, True)
        mock_task.assert_has_calls(
            [mock.call.self.show(), mock.call.self.show(),
             mock.call.self.show()])

        # task fails (no instance)
        mock_task = mock.MagicMock(name='fake task')
        mock_task.self.show.side_effect = [queued, in_process, failed]
        ret = yield self.client.wait_for_task(mock_task, sleep=0.01)
        self.assertEqual(ret, False)

        # task fails
        mock_task = mock.MagicMock(name='fake task')
        mock_task.self.show.side_effect = [queued, in_process, failed]
        ret = yield self.client.wait_for_task(
            mock_task, sleep=0.01, instance=mocked_instance)
        self.assertEqual(ret, False)
        mock_task.assert_has_calls(
            [mock.call.self.show(), mock.call.self.show(),
             mock.call.self.show()])

        # task fails
        self.client.get_audit_logs = helper.mock_tornado(['log', 'log'])
        mock_task = mock.MagicMock(name='fake task')
        mock_task.self.show.side_effect = [queued, in_process, failed]
        ret = yield self.client.wait_for_task(
            mock_task, sleep=0.01, instance=mocked_instance)
        self.assertEqual(ret, False)
        mock_task.assert_has_calls(
            [mock.call.self.show(), mock.call.self.show(),
             mock.call.self.show()])

        # task is empty
        mock_task = None
        ret = yield self.client.wait_for_task(mock_task, sleep=0.01)
        self.assertEqual(ret, True)

    @testing.gen_test
    def test_get_audit_logs(self):
        mock_instance = mock.MagicMock(name='unittest-instance')
        mock_instance.soul = {'name': 'unittest-instance'}
        mock_instance.links = {'self': '/foo/bar'}
        mock_instance.self.path = '/a/b/1234'

        fail = mock.Mock()
        fail.soul = {'summary': "failed: 'Some Script' [HEAD]"}

        success = mock.Mock()
        success.soul = {'summary': "completed: 'Some Script' [HEAD]"}

        self.mock_client.audit_entries.index.return_value = [
            fail,
            success
        ]

        logs = yield self.client.get_audit_logs(mock_instance,
                                                'start',
                                                'end',
                                                'failed')

        self.assertEqual(len(logs), 1)
        expected = self.mock_client.client.get().raw_response.text
        self.assertEqual(logs[0], expected)

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
            self.assertEqual(resource_mock, ret)
            requests_mock_client.post.assert_called_once_with(
                '/foo', data={'a': 'b'})

        # Test 2: Simple GET that returns JSON
        response_mock.json.return_value = "{'name': 'fake soul'}"
        requests_mock_client.reset_mock()
        with mock.patch('rightscale.rightscale.Resource') as r_mock:
            resource_mock = mock.MagicMock(name='resource_mock')
            r_mock.return_value = resource_mock
            ret = yield self.client.make_generic_request('/foo')
            self.assertEqual(resource_mock, ret)
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
            self.assertEqual(resource_mock, ret)
            requests_mock_client.post.assert_called_once_with(
                '/foo', data={'a': 'b'})
            requests_mock_client.get.assert_called_once_with('/foobar')

        # Test 4: Simple GET that returns no JSON
        response_mock.raw_response.text = 'test'
        response_mock.json.side_effect = simplejson.scanner.JSONDecodeError(
            'a', 'b', 0)
        ret = yield self.client.make_generic_request('/foo')
        self.assertEqual('test', ret)
