import logging
import mock

from tornado import testing
from tornado import gen
import requests

from kingpin.actors import exceptions
from kingpin.actors.rightscale import api
from kingpin.actors.rightscale import base
from kingpin.actors.rightscale import server_array
from kingpin.actors.test.helper import mock_tornado, tornado_value

log = logging.getLogger(__name__)


class TestServerArrayBaseActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestServerArrayBaseActor, self).setUp()
        base.TOKEN = 'unittest'

        # Create the actor
        self.actor = server_array.ServerArrayBaseActor(
            'Copy UnitTestArray to NewUnitArray', {})

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock()
        self.actor._client = self.client_mock

        # Mock out the login method entirely
        self.client_mock.login = mock_tornado()

    @testing.gen_test
    def test_find_server_arrays_with_bad_raise_on(self):
        with self.assertRaises(exceptions.ActorException):
            yield self.actor._find_server_arrays('t', raise_on='bogus')

    @testing.gen_test
    def test_find_server_arrays_dry_not_found(self):
        self.client_mock.find_server_arrays = mock_tornado(None)

        self.actor._dry = True

        # With allow_mock enabled, we should receive a mock back
        ret = yield self.actor._find_server_arrays('t', allow_mock=True)
        self.assertTrue(isinstance(ret, mock.MagicMock))

        # With it set to false, we should raise an exception
        with self.assertRaises(exceptions.ActorException):
            yield self.actor._find_server_arrays('t', allow_mock=False)

    @testing.gen_test
    def test_find_server_arrays_found(self):
        mocked_array = mock.MagicMock(name='mocked array')

        mock_find = mock_tornado(mocked_array)
        self.client_mock.find_server_arrays = mock_find

        # If the array is found, but we don't want it found, it should
        # raise an exception.
        with self.assertRaises(exceptions.ActorException):
            yield self.actor._find_server_arrays('t', raise_on='found')

        # If the array is found, and we DO want it found, it should be
        # returned properly.
        ret = yield self.actor._find_server_arrays('t', raise_on='notfound')
        self.assertEquals(mocked_array, ret)

        # Lastly, if the array is found and we we don't care whether its
        # found or not, it should be returned
        ret = yield self.actor._find_server_arrays('t', raise_on=None)
        self.assertEquals(mocked_array, ret)

    @testing.gen_test
    def test_find_server_arrays_not_found(self):
        self.client_mock.find_server_arrays = mock_tornado()

        # If the array is not found, but we do want it found, it should
        # raise an exception.
        with self.assertRaises(exceptions.ActorException):
            yield self.actor._find_server_arrays('t', raise_on='notfound')

        # If the array is not found, and we don't want it found, it should
        # return properly.
        ret = yield self.actor._find_server_arrays('t', raise_on='found')
        self.assertEquals(None, ret)

        # Lastly, if the array is not found and we don't care whether its
        # found or not, None should be returned
        ret = yield self.actor._find_server_arrays('t', raise_on=None)
        self.assertEquals(None, ret)


class TestCloneActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestCloneActor, self).setUp()
        base.TOKEN = 'unittest'

        # Create the actor
        self.actor = server_array.Clone('Copy UnitTestArray to NewUnitArray',
                                        {'source': 'unittestarray',
                                         'dest': 'newunitarray'})

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock()
        self.actor._client = self.client_mock

        # Mock out the login method entirely
        self.client_mock.login = mock_tornado()

    @testing.gen_test
    def test_execute(self):

        source_array = mock.MagicMock(name='unittestarray')
        source_array.self.path = '/fo/bar/123'
        self.actor._find_server_arrays = mock_tornado(source_array)

        new_array = mock.MagicMock(name='unittestarray v1')
        new_array.self.path = '/foo/bar/124'
        self.client_mock.clone_server_array = mock_tornado(new_array)

        self.client_mock.update_server_array = mock_tornado()

        ret = yield self.actor.execute()
        self.assertEquals(None, ret)

    @testing.gen_test
    def test_execute_in_dry_mode(self):
        self.actor._dry = True

        source_array = mock.MagicMock(name='unittestarray')
        source_array.self.path = '/fo/bar/123'
        self.actor._find_server_arrays = mock_tornado(source_array)

        self.client_mock.update_server_array = mock_tornado()

        ret = yield self.actor.execute()
        self.assertEquals(None, ret)


class TestUpdateActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestUpdateActor, self).setUp()
        base.TOKEN = 'unittest'

        # Create the actor
        self.actor = server_array.Update(
            'Patch',
            {'array': 'unittestarray',
                'params': {'name': 'newunitarray'},
                'inputs': {'test': 'text:test'}})

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock()
        self.actor._client = self.client_mock

        # Mock out the login method entirely
        self.client_mock.login = mock_tornado()

    @testing.gen_test
    def test_check_inputs_empty(self):
        array = mock.Mock()
        array.soul = {'name': 'real array'}
        inputs = {}
        self.actor._client.get_server_array_inputs = mock_tornado([])
        ok = yield self.actor._check_array_inputs(array, inputs)
        self.assertEquals(ok, None)

    @testing.gen_test
    def test_check_inputs_missing(self):
        array = mock.Mock()
        array.soul = {'name': 'real array'}
        inputs = {'foo': 'bar'}
        self.actor._client.get_server_array_inputs = mock_tornado([])
        with self.assertRaises(server_array.InvalidInputs):
            yield self.actor._check_array_inputs(array, inputs)

    @testing.gen_test
    def test_check_inputs_on_mock(self):
        array = mock.Mock()
        array.soul = {'fake': True}
        inputs = {}
        self.actor._client.get_server_array_inputs = mock_tornado([])
        ok = yield self.actor._check_array_inputs(array, inputs)
        self.assertEquals(ok, None)

    @testing.gen_test
    def test_execute(self):
        self.actor._dry = False
        mocked_array = mock.MagicMock(name='unittestarray')

        self.actor._check_array_inputs = mock_tornado(True)
        self.actor._find_server_arrays = mock_tornado(mocked_array)

        self.client_mock.update_server_array.return_value = tornado_value(None)

        self.client_mock.update_server_array_inputs.return_value = (
            tornado_value(None))

        ret = yield self.actor.execute()

        self.client_mock.update_server_array.assert_called_once_with(
            mocked_array, {'server_array[name]': 'newunitarray'})
        self.client_mock.update_server_array_inputs.assert_called_once_with(
            mocked_array, {'inputs[test]': 'text:test'})

        self.assertEquals(None, ret)

    @testing.gen_test
    def test_execute_422_error(self):
        mocked_array = mock.MagicMock(name='unittestarray')

        self.actor._check_array_inputs = mock_tornado(True)
        self.actor._find_server_arrays = mock_tornado(mocked_array)

        msg = '422 Client Error: Unprocessable Entity'
        mocked_response = mock.MagicMock(name='response')
        mocked_response.status_code = 422
        error = requests.exceptions.HTTPError(msg, response=mocked_response)
        self.client_mock.update_server_array.side_effect = error

        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor.execute()

        self.client_mock.update_server_array.assert_called_once_with(
            mocked_array, {'server_array[name]': 'newunitarray'})

    @testing.gen_test
    def test_execute_dry(self):
        self.actor._dry = True
        mocked_array = object()

        self.actor._check_array_inputs = mock_tornado(True)
        self.actor._find_server_arrays = mock_tornado(mocked_array)

        ret = yield self.actor.execute()
        self.assertEquals(None, ret)

    @testing.gen_test
    def test_execute_dry_with_missing_array(self):
        self.actor._dry = True
        mocked_array = mock.MagicMock(name='unittestarray')
        mocked_array.soul = {'name': 'unittestarray'}

        self.actor._check_array_inputs = mock_tornado(True)
        self.actor._find_server_arrays = mock_tornado(mocked_array)

        ret = yield self.actor.execute()
        self.assertEquals(None, ret)


class TestTerminateActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestTerminateActor, self).setUp()
        base.TOKEN = 'unittest'

        # Create the actor
        self.actor = server_array.Terminate(
            'Terminate',
            {'array': 'unittestarray'})

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock()
        self.actor._client = self.client_mock

        # Mock out the login method entirely
        self.client_mock.login = mock_tornado()

    @testing.gen_test
    def test_terminate_all_instances(self):
        array_mock = mock.MagicMock(name='unittest')
        array_mock.soul = {'name': 'unittest'}
        array_mock.self.path = '/a/b/1234'

        mock_task = mock.MagicMock(name='fake terminate task')

        term = mock_tornado(mock_task)
        self.client_mock.terminate_server_array_instances = term

        self.client_mock.wait_for_task = mock_tornado()

        ret = yield self.actor._terminate_all_instances(array_mock)
        self.assertEquals(ret, None)
        self.assertEquals(
            self.client_mock.terminate_server_array_instances._call_count,
            1)

    @testing.gen_test
    def test_terminate_all_instances_dry(self):
        self.actor._dry = True
        array_mock = mock.MagicMock(name='unittest')
        array_mock.soul = {'name': 'unittest'}
        array_mock.self.path = '/a/b/1234'

        term = mock_tornado()
        self.client_mock.terminate_server_array_instances = term

        self.client_mock.wait_for_task = mock_tornado()

        ret = yield self.actor._terminate_all_instances(array_mock)
        self.assertEquals(ret, None)
        self.assertEquals(
            self.client_mock.terminate_server_array_instances._call_count,
            0)

    @testing.gen_test
    def test_wait_until_empty(self):
        array_mock = mock.MagicMock(name='unittest')

        responses = (['a', 'b', 'c'],
                     ['a', 'b'],
                     ['a'],
                     [])

        get_func = self.client_mock.get_server_array_current_instances
        get_func.side_effect = [
            tornado_value(r) for r in responses]

        ret = yield self.actor._wait_until_empty(array_mock, sleep=0.01)
        self.assertEquals(get_func.call_count, 4)
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_wait_until_empty_dry(self):
        self.actor._dry = True
        array_mock = mock.MagicMock(name='unittest')
        ret = yield self.actor._wait_until_empty(array_mock)
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_execute(self):
        self.actor._dry = False
        initial_array = mock.MagicMock(name='unittestarray')

        self.actor._find_server_arrays = mock_tornado(initial_array)

        @gen.coroutine
        def update_array(array, params):
            array.updated(params)

        self.client_mock.update_server_array.side_effect = update_array

        self.actor._terminate_all_instances = mock_tornado()

        self.actor._wait_until_empty = mock_tornado()

        ret = yield self.actor._execute()

        # Verify that the array object would have been patched
        self.client_mock.update_server_array.assert_called_once_with(
            initial_array,  {'server_array[state]': 'disabled'})
        initial_array.updated.assert_called_once_with(
            {'server_array[state]': 'disabled'})

        # Now verify that each of the steps (terminate, wait, destroyed) were
        # all called.
        self.assertEquals(self.actor._wait_until_empty._call_count, 1)
        self.assertEquals(self.actor._terminate_all_instances._call_count, 1)
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_execute_dry(self):
        self.actor._dry = True
        initial_array = mock.MagicMock(name='unittestarray')
        self.actor._find_server_arrays = mock_tornado(initial_array)

        @gen.coroutine
        def update_array(array, params):
            array.updated(params)
        self.client_mock.update_server_array.side_Effect = update_array

        # ensure that we never called the update_array method!
        yield self.actor._execute()
        initial_array.updated.assert_has_calls([])


class TestDestroyActor(TestServerArrayBaseActor):

    @testing.gen_test
    def test_terminate(self):
        actor = server_array.Destroy(
            'Destroy',
            {'array': 'unittestarray'})
        with mock.patch.object(server_array, 'Terminate') as t:
            t()._execute = mock_tornado(mock.MagicMock())
            obj = yield actor._terminate()
            self.assertEquals(t()._execute._call_count, 1)
            self.assertEquals(obj, t())

    @testing.gen_test
    def test_execute(self):
        actor = server_array.Destroy(
            'Destroy',
            {'array': 'unittestarray'})
        actor._terminate = mock_tornado(mock.Mock())
        actor._destroy_array = mock_tornado()

        array = mock.MagicMock(name='unittest')
        server_array.Terminate.array = array  # Fake helper computation

        ret = yield actor._execute()

        self.assertEquals(actor._terminate._call_count, 1)
        self.assertEquals(actor._destroy_array._call_count, 1)
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_execute_terminate_fails(self):
        actor = server_array.Destroy(
            'Destroy',
            {'array': 'unittestarray'})

        @gen.coroutine
        def raise_exc():
            raise exceptions.UnrecoverableActorFailure('fail')
        actor._terminate = raise_exc

        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            yield actor._execute()

    @testing.gen_test
    def test_destroy_array(self):
        actor = server_array.Destroy(
            'Destroy',
            {'array': 'unittestarray'})
        array = mock.MagicMock(name='unittest')
        array.soul = {'name': 'unittest'}

        actor._client = mock.Mock()
        actor._client.destroy_server_array.side_effect = tornado_value

        ret = yield actor._destroy_array(array)
        self.assertTrue(actor._client.destroy_server_array.called_with(array))
        self.assertEquals(ret, None)

        actor._dry = True
        ret = yield actor._destroy_array(array)
        self.assertTrue(actor._client.destroy_server_array.called_with(array))
        self.assertEquals(ret, None)


class TestLaunchActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestLaunchActor, self).setUp()
        base.TOKEN = 'unittest'

        # Create the actor
        self.actor = server_array.Launch(
            'Launch',
            {'array': 'unittestarray',
             'enable': True})

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock()
        self.actor._client = self.client_mock

        # Mock out the login method entirely
        self.client_mock.login = mock_tornado()

    @testing.gen_test
    def test_requirements(self):

        with self.assertRaises(exceptions.InvalidOptions):
            # Missing enable and count flags
            server_array.Launch(
                'Unit test', {
                    'array': 'unit test array',
                })

        with self.assertRaises(exceptions.InvalidOptions):
            # Not enabling and missing count flag
            server_array.Launch(
                'Unit test', {
                    'array': 'unit test array',
                    'enable': False
                })

    @testing.gen_test
    def test_wait_until_healthy(self):
        array_mock = mock.MagicMock(name='unittest')
        array_mock.soul = {
            'name': 'unittest',
            'elasticity_params': {'bounds': {'min_count': '4'}}}

        server_list = []

        @gen.coroutine
        def get(self, *args, **kwargs):
            server_list.append('x')
            raise gen.Return(server_list)
        self.client_mock.get_server_array_current_instances = get

        ret = yield self.actor._wait_until_healthy(array_mock, sleep=0.01)
        self.assertEquals(len(server_list), 4)
        self.assertEquals(ret, None)

        # Now run the same test, but in dry mode..
        self.actor._dry = True
        server_list = []
        ret = yield self.actor._wait_until_healthy(array_mock, sleep=0.01)
        self.assertEquals(len(server_list), 0)
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_wait_until_healthy_based_on_specific_count(self):
        # Set the 'count' option to 2 in the Actor
        self.actor._options['count'] = 2

        # Now proceed with creating a fake array, etc.
        array_mock = mock.MagicMock(name='unittest')
        array_mock.soul = {
            'name': 'unittest',
            'elasticity_params': {'bounds': {'min_count': '4'}}}

        server_list = []

        @gen.coroutine
        def get(self, *args, **kwargs):
            server_list.append('x')
            raise gen.Return(server_list)
        self.client_mock.get_server_array_current_instances = get

        ret = yield self.actor._wait_until_healthy(array_mock, sleep=0.01)
        self.assertEquals(len(server_list), 2)
        self.assertEquals(ret, None)

        # Now run the same test, but in dry mode..
        self.actor._dry = True
        server_list = []
        ret = yield self.actor._wait_until_healthy(array_mock, sleep=0.01)
        self.assertEquals(len(server_list), 0)
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_launch_instances(self):
        array_mock = mock.MagicMock(name='unittest')
        array_mock.soul = {
            'name': 'unittest',
            'elasticity_params': {'bounds': {'min_count': '4'}}}

        launch = mock_tornado()
        self.client_mock.launch_server_array.side_effect = launch

        two_mock_calls = [mock.call(array_mock), mock.call(array_mock)]
        four_mock_calls = [
            mock.call(array_mock), mock.call(array_mock),
            mock.call(array_mock), mock.call(array_mock)]

        # Regular function call
        yield self.actor._launch_instances(array_mock)
        self.client_mock.launch_server_array.assert_has_calls(four_mock_calls)

        # Count-specific function call
        self.client_mock.launch_server_array.reset_mock()
        yield self.actor._launch_instances(array_mock, count=2)
        self.client_mock.launch_server_array.assert_has_calls(two_mock_calls)

        # Dry call
        self.actor._dry = True
        self.client_mock.launch_server_array.reset_mock()
        yield self.actor._launch_instances(array_mock)
        self.client_mock.launch_server_array.assert_has_calls([])

    @testing.gen_test
    def test_execute(self):
        self.actor._dry = False
        initial_array = mock.MagicMock(name='unittestarray')
        updated_array = mock.MagicMock(name='unittestarray-updated')

        self.actor._find_server_arrays = mock_tornado(initial_array)

        @gen.coroutine
        def update_array(array, params):
            array.updated(params)
            raise gen.Return(updated_array)
        self.client_mock.update_server_array.side_effect = update_array

        self.actor._launch_instances = mock_tornado()
        self.actor._wait_until_healthy = mock_tornado()

        ret = yield self.actor._execute()

        # Verify that the array object would have been patched
        self.client_mock.update_server_array.assert_called_once_with(
            initial_array,  {'server_array[state]': 'enabled'})
        initial_array.updated.assert_called_once_with(
            {'server_array[state]': 'enabled'})

        # Now verify that each of the steps (terminate, wait, destroyed) were
        # all called.
        self.assertEquals(self.actor._launch_instances._call_count, 1)
        self.assertEquals(self.actor._wait_until_healthy._call_count, 1)
        self.assertEquals(ret, None)

        # Dry
        self.actor._dry = True
        self.actor._client.launch_server_array = mock_tornado()
        self.actor._client.get_server_array_current_instances = mock_tornado()
        ret = yield self.actor._execute()
        self.assertEquals(
            self.actor._client.launch_server_array._call_count, 0)
        self.assertEquals(
            self.actor._client.get_server_array_current_instances._call_count,
            0)
        self.assertEquals(ret, None)


class TestExecuteActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestExecuteActor, self).setUp()
        base.TOKEN = 'unittest'

        # Create the actor
        self.actor = server_array.Execute(
            'Execute',
            {'array': 'unittestarray',
             'script': 'test_script',
             'inputs': {'foo': 'text:bar'}})

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock()
        self.actor._client = self.client_mock

        # Mock out the login method entirely
        self.client_mock.login = mock_tornado()

    @testing.gen_test
    def test_check_script(self):
        self.actor._client.find_cookbook = mock.Mock()
        self.actor._client.find_cookbook.side_effect = tornado_value
        result = yield self.actor._check_script('ut::recipe')
        self.assertTrue(result)
        self.actor._client.find_cookbook.assert_called_with('ut::recipe')

        self.actor._client.find_right_script = mock.Mock()
        self.actor._client.find_right_script.side_effect = tornado_value
        result = yield self.actor._check_script('ut-script')
        self.assertTrue(result)
        self.actor._client.find_right_script.assert_called_with('ut-script')

    def test_input_issues(self):
        # Correct inputs have no issues
        self.actor._check_inputs()

        # Incorrect inputs must be found
        self.actor._options['inputs']['broken'] = 'broken'
        with self.assertRaises(exceptions.InvalidOptions):
            self.actor._check_inputs()

    @testing.gen_test
    def test_get_operational_instances_warn(self):
        mock_array = mock.MagicMock(name='array')
        mock_op_instance = mock.MagicMock(name='mock_instance')
        mock_op_instance.soul = {'state': 'operational'}
        mock_non_op_instance = mock.MagicMock(name='mock_instance')
        mock_non_op_instance.soul = {'state': 'booting'}

        get = mock_tornado([mock_op_instance,
                            mock_non_op_instance,
                            mock_op_instance])
        self.client_mock.get_server_array_current_instances = get

        ret = yield self.actor._get_operational_instances(mock_array)
        self.assertEquals(2, len(ret))

    @testing.gen_test
    def test_execute(self):
        mock_array = mock.MagicMock(name='array')
        mock_op_instance = mock.MagicMock(name='mock_instance')
        mock_op_instance.soul = {'state': 'operational',
                                 'name': 'unit-test-instance'}
        mock_task = mock.MagicMock(name='mock_task')

        self.actor._check_script = mock_tornado(True)
        self.actor._find_server_arrays = mock_tornado(mock_array)

        yi = tornado_value([mock_op_instance])
        self.client_mock.get_server_array_current_instances.return_value = yi

        run_e = tornado_value([(mock_op_instance, mock_task)])
        self.client_mock.run_executable_on_instances.return_value = run_e

        wait = tornado_value(True)
        self.client_mock.wait_for_task.return_value = wait

        # Now verify that each of the expected steps were called in a
        # successful execution.
        ret = yield self.actor._execute()
        (self.client_mock.get_server_array_current_instances
            .assert_called_twice_with(mock_array))
        (self.client_mock.run_executable_on_instances
            .assert_called_once_with(
                'test_script',
                {'inputs[foo]': 'text:bar'},
                [mock_op_instance]))
        self.client_mock.wait_for_task.assert_called_once_with(
            task=mock_task,
            task_name='unit-test-instance executing test_script',
            sleep=5,
            logger=self.actor.log.info)
        self.assertEquals(ret, None)

        # Now mock out a failure of the script execution
        self.client_mock.wait_for_task = mock_tornado(False)
        with self.assertRaises(server_array.TaskExecutionFailed):
            yield self.actor._execute()

        # Finally, a test that mocks out an http error on bad inputs
        error = api.ServerArrayException()
        self.client_mock.run_executable_on_instances.side_effect = error
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._execute()

    @testing.gen_test
    def test_execute_dry(self):
        self.actor._dry = True
        mock_array = mock.MagicMock(name='array')

        self.actor._check_script = mock_tornado(True)
        self.actor._find_server_arrays = mock_tornado(mock_array)

        self.client_mock.get_server_array_current_instances = mock_tornado([])

        ret = yield self.actor._execute()
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_execute_dry_fail(self):
        self.actor._dry = True
        mock_array = mock.MagicMock(name='array')

        # Checking script fails
        self.actor._check_script = mock_tornado(False)
        self.actor._find_server_arrays = mock_tornado(mock_array)
        self.client_mock.get_server_array_current_instances = mock_tornado([])

        with self.assertRaises(exceptions.InvalidOptions):
            yield self.actor._execute()
