import logging
import mock

from tornado import testing
from tornado import gen
import requests

from kingpin.actors import exceptions
from kingpin.actors.rightscale import api
from kingpin.actors.rightscale import base
from kingpin.actors.rightscale import server_array

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
        @gen.coroutine
        def login():
            raise gen.Return()
        self.client_mock.login.side_effect = login

    @testing.gen_test
    def test_find_server_arrays_with_bad_raise_on(self):
        with self.assertRaises(api.ServerArrayException):
            yield self.actor._find_server_arrays('t', raise_on='bogus')

    @testing.gen_test
    def test_find_server_arrays_dry_not_found(self):
        @gen.coroutine
        def yield_no_arrays(self, *args, **kwargs):
            raise gen.Return(None)
        self.client_mock.find_server_arrays.side_effect = yield_no_arrays

        self.actor._dry = True

        # With allow_mock enabled, we should receive a mock back
        ret = yield self.actor._find_server_arrays('t', allow_mock=True)
        self.assertTrue(isinstance(ret, mock.MagicMock))

        # With it set to false, we should raise an exception
        with self.assertRaises(api.ServerArrayException):
            yield self.actor._find_server_arrays('t', allow_mock=False)

    @testing.gen_test
    def test_find_server_arrays_found(self):
        mocked_array = mock.MagicMock(name='mocked array')

        @gen.coroutine
        def yield_source_template(self, *args, **kwargs):
            raise gen.Return(mocked_array)
        self.client_mock.find_server_arrays.side_effect = yield_source_template

        # If the array is found, but we don't want it found, it should
        # raise an exception.
        with self.assertRaises(api.ServerArrayException):
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
        @gen.coroutine
        def yield_source_template(self, *args, **kwargs):
            raise gen.Return()
        self.client_mock.find_server_arrays.side_effect = yield_source_template

        # If the array is not found, but we do want it found, it should
        # raise an exception.
        with self.assertRaises(api.ServerArrayException):
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
        @gen.coroutine
        def login():
            raise gen.Return()
        self.client_mock.login.side_effect = login

    @testing.gen_test
    def test_execute(self):

        @gen.coroutine
        def find_server_arrays(name, *args, **kwargs):
            if name == 'unittestarray':
                source_array = mock.MagicMock(name='unittestarray')
                source_array.self.path = '/fo/bar/123'
                raise gen.Return(source_array)
            if name == 'newunitarray':
                raise gen.Return(None)
        self.actor._find_server_arrays = find_server_arrays

        @gen.coroutine
        def clone_server_array(array):
            new_array = mock.MagicMock(name='unittestarray v1')
            new_array.self.path = '/foo/bar/124'
            raise gen.Return(new_array)
        self.client_mock.clone_server_array.side_effect = clone_server_array

        @gen.coroutine
        def update_server_array(array, params):
            raise gen.Return()
        self.client_mock.update_server_array.side_effect = update_server_array

        ret = yield self.actor.execute()
        self.assertEquals(True, ret)

    @testing.gen_test
    def test_execute_in_dry_mode(self):
        self.actor._dry = True

        @gen.coroutine
        def find_server_arrays(name, *args, **kwargs):
            if name == 'unittestarray':
                source_array = mock.MagicMock(name='unittestarray')
                source_array.self.path = '/fo/bar/123'
                raise gen.Return(source_array)
            if name == 'newunitarray':
                raise gen.Return(None)
        self.actor._find_server_arrays = find_server_arrays

        @gen.coroutine
        def update_server_array(array, params):
            raise gen.Return()
        self.client_mock.update_server_array.side_effect = update_server_array

        ret = yield self.actor.execute()
        self.assertEquals(True, ret)


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
        @gen.coroutine
        def login():
            raise gen.Return()
        self.client_mock.login.side_effect = login

    @testing.gen_test
    def test_execute(self):
        self.actor._dry = False
        mocked_array = mock.MagicMock(name='unittestarray')

        @gen.coroutine
        def yield_array(self, *args, **kwargs):
            raise gen.Return(mocked_array)
        self.actor._find_server_arrays = yield_array

        @gen.coroutine
        def yield_update(self, *args, **kwargs):
            raise gen.Return()
        self.client_mock.update_server_array.side_effect = yield_update

        @gen.coroutine
        def yield_inputs(self, *args, **kwargs):
            raise gen.Return()
        self.client_mock.update_server_array_inputs.side_effect = yield_inputs

        ret = yield self.actor.execute()

        self.client_mock.update_server_array.assert_called_once_with(
            mocked_array, {'server_array[name]': 'newunitarray'})
        self.client_mock.update_server_array_inputs.assert_called_once_with(
            mocked_array, {'inputs[test]': 'text:test'})

        self.assertEquals(True, ret)

    @testing.gen_test
    def test_execute_422_error(self):
        mocked_array = mock.MagicMock(name='unittestarray')

        @gen.coroutine
        def yield_array(self, *args, **kwargs):
            raise gen.Return(mocked_array)
        self.actor._find_server_arrays = yield_array

        msg = '422 Client Error: Unprocessable Entity'
        mocked_response = mock.MagicMock(name='response')
        mocked_response.status_code = 422
        error = requests.exceptions.HTTPError(msg, response=mocked_response)
        self.client_mock.update_server_array.side_effect = error

        with self.assertRaises(exceptions.UnrecoverableActionFailure):
            yield self.actor.execute()

        self.client_mock.update_server_array.assert_called_once_with(
            mocked_array, {'server_array[name]': 'newunitarray'})

    @testing.gen_test
    def test_execute_dry(self):
        self.actor._dry = True
        mocked_array = mock.MagicMock(name='unittestarray')

        @gen.coroutine
        def yield_array(self, *args, **kwargs):
            raise gen.Return(mocked_array)
        self.actor._find_server_arrays = yield_array

        ret = yield self.actor.execute()

        self.assertEquals(True, ret)

    @testing.gen_test
    def test_execute_dry_with_missing_array(self):
        self.actor._dry = True
        mocked_array = mock.MagicMock(name='unittestarray')
        mocked_array.soul = {'name': 'unittestarray'}

        @gen.coroutine
        def yield_array(self, *args, **kwargs):
            raise gen.Return(mocked_array)
        self.actor._find_server_arrays = yield_array

        ret = yield self.actor.execute()

        self.assertEquals(True, ret)


class TestDestroyActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestDestroyActor, self).setUp()
        base.TOKEN = 'unittest'

        # Create the actor
        self.actor = server_array.Destroy(
            'Destroy',
            {'array': 'unittestarray',
             'terminate': True})

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock()
        self.actor._client = self.client_mock

        # Mock out the login method entirely
        @gen.coroutine
        def login():
            raise gen.Return()
        self.client_mock.login.side_effect = login

    @testing.gen_test
    def test_terminate_all_instances(self):
        array_mock = mock.MagicMock(name='unittest')
        array_mock.soul = {'name': 'unittest'}
        array_mock.self.path = '/a/b/1234'

        @gen.coroutine
        def term(self, *args, **kwargs):
            raise gen.Return()
        self.client_mock.terminate_server_array_instances.side_effect = term

        ret = yield self.actor._terminate_all_instances(array_mock)
        self.assertEquals(ret, None)
        (self.client_mock.terminate_server_array_instances.
            assert_has_calls([mock.call(array_mock)]))

    @testing.gen_test
    def test_terminate_all_instances_dry(self):
        self.actor._dry = True
        array_mock = mock.MagicMock(name='unittest')
        array_mock.soul = {'name': 'unittest'}
        array_mock.self.path = '/a/b/1234'

        @gen.coroutine
        def term(self, *args, **kwargs):
            raise gen.Return()
        self.client_mock.terminate_server_array_instances.side_effect = term

        ret = yield self.actor._terminate_all_instances(array_mock)
        self.assertEquals(ret, None)
        (self.client_mock.terminate_server_array_instances.
            assert_has_calls([]))

    @testing.gen_test
    def test_terminate_all_instances_no_terminate(self):
        self.actor._terminate = False
        array_mock = mock.MagicMock(name='unittest')
        array_mock.soul = {'name': 'unittest'}
        array_mock.self.path = '/a/b/1234'

        @gen.coroutine
        def term(self, *args, **kwargs):
            raise gen.Return()
        self.client_mock.terminate_server_array_instances.side_effect = term

        ret = yield self.actor._terminate_all_instances(array_mock)
        self.assertEquals(ret, None)
        (self.client_mock.terminate_server_array_instances.
            assert_has_calls([]))

    @testing.gen_test
    def test_wait_until_empty(self):
        array_mock = mock.MagicMock(name='unittest')
        array_mock.soul = {'name': 'unittest'}
        array_mock.self.path = '/a/b/1234'

        fake_servers = ['a', 'b', 'c', 'd']
        mock_tracker = mock.MagicMock()

        @gen.coroutine
        def get(self, *args, **kwargs):
            fake_servers.pop()
            mock_tracker.track_me()
            raise gen.Return(fake_servers)

        self.client_mock.get_server_array_current_instances = get

        ret = yield self.actor._wait_until_empty(array_mock, sleep=0.1)
        mock_tracker.assert_has_calls([
            mock.call.track_me(), mock.call.track_me(),
            mock.call.track_me(), mock.call.track_me()])
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_wait_until_empty_dry(self):
        self.actor._dry = True
        array_mock = mock.MagicMock(name='unittest')
        array_mock.soul = {'name': 'unittest'}
        array_mock.self.path = '/a/b/1234'
        ret = yield self.actor._wait_until_empty(array_mock)
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_destroy_array(self):
        array_mock = mock.MagicMock(name='unittest')
        array_mock.soul = {'name': 'unittest'}
        array_mock.self.path = '/a/b/1234'

        @gen.coroutine
        def destroy(self, *args, **kwargs):
            raise gen.Return()
        self.client_mock.destroy_server_array.side_effect = destroy

        ret = yield self.actor._destroy_array(array_mock)
        self.client_mock.assert_has_calls(
            [mock.call.destroy_server_array(array_mock)])
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_destroy_array_dry(self):
        self.actor._dry = True
        array_mock = mock.MagicMock(name='unittest')
        array_mock.soul = {'name': 'unittest'}
        array_mock.self.path = '/a/b/1234'
        ret = yield self.actor._destroy_array(array_mock)
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_execute(self):
        self.actor._dry = False
        initial_array = mock.MagicMock(name='unittestarray')
        updated_array = mock.MagicMock(name='unittestarray-updated')

        @gen.coroutine
        def yield_array(self, *args, **kwargs):
            raise gen.Return(initial_array)
        self.actor._find_server_arrays = yield_array

        @gen.coroutine
        def update_array(array, params):
            array.updated(params)
            raise gen.Return(updated_array)
        self.client_mock.update_server_array.side_effect = update_array

        @gen.coroutine
        def term_array(array):
            array.terminated()
            raise gen.Return()
        self.actor._terminate_all_instances = term_array

        @gen.coroutine
        def wait(array):
            array.waited()
            raise gen.Return()
        self.actor._wait_until_empty = wait

        @gen.coroutine
        def destroy(array):
            array.destroyed()
            raise gen.Return()
        self.actor._destroy_array = destroy

        ret = yield self.actor._execute()

        # Verify that the array object would have been patched
        self.client_mock.update_server_array.assert_called_once_with(
            initial_array,  {'server_array[state]': 'disabled'})
        initial_array.updated.assert_called_once_with(
            {'server_array[state]': 'disabled'})

        # Now verify that each of the steps (terminate, wait, destroyed) were
        # all called.
        initial_array.terminated.assert_called_once_with()
        initial_array.waited.assert_called_once_with()
        initial_array.destroyed.assert_called_once_with()
        self.assertEquals(ret, True)


class TestLaunchActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestLaunchActor, self).setUp()
        base.TOKEN = 'unittest'

        # Create the actor
        self.actor = server_array.Launch(
            'Launch',
            {'array': 'unittestarray'})

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock()
        self.actor._client = self.client_mock

        # Mock out the login method entirely
        @gen.coroutine
        def login():
            raise gen.Return()
        self.client_mock.login.side_effect = login

    @testing.gen_test
    def test_wait_until_healthy(self):
        array_mock = mock.MagicMock(name='unittest')
        array_mock.soul = {
            'name': 'unittest',
            'elasticity_params': {'bounds': {'min_count': '4'}}}
        array_mock.self.path = '/a/b/1234'

        fake_servers = []
        mock_tracker = mock.MagicMock()

        @gen.coroutine
        def get(self, *args, **kwargs):
            fake_servers.append('x')
            mock_tracker.track_me()
            raise gen.Return(fake_servers)

        self.client_mock.get_server_array_current_instances = get

        ret = yield self.actor._wait_until_healthy(array_mock, sleep=0.1)
        mock_tracker.assert_has_calls([
            mock.call.track_me(), mock.call.track_me(),
            mock.call.track_me(), mock.call.track_me()])
        self.assertEquals(ret, None)

        # Now run the same test, but in dry mode..
        self.actor._dry = True
        mock_tracker.reset_mock()
        ret = yield self.actor._wait_until_healthy(array_mock, sleep=0.1)
        mock_tracker.assert_has_calls([])
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_launch_min_instances(self):
        array_mock = mock.MagicMock(name='unittest')
        array_mock.soul = {
            'name': 'unittest',
            'elasticity_params': {'bounds': {'min_count': '4'}}}
        array_mock.self.path = '/a/b/1234'

        @gen.coroutine
        def launch(self, *args, **kwargs):
            raise gen.Return()
        self.client_mock.launch_server_array.side_effect = launch

        ret = yield self.actor._launch_min_instances(array_mock)
        self.assertEquals(ret, None)
        self.client_mock.launch_server_array.assert_has_calls(
            [mock.call(array_mock), mock.call(array_mock),
             mock.call(array_mock), mock.call(array_mock)])

        self.actor._dry = True
        self.client_mock.launch_server_array.reset_mock()
        ret = yield self.actor._launch_min_instances(array_mock)
        self.assertEquals(ret, None)
        self.client_mock.launch_server_array.assert_has_calls([])

    @testing.gen_test
    def test_execute(self):
        self.actor._dry = False
        initial_array = mock.MagicMock(name='unittestarray')
        updated_array = mock.MagicMock(name='unittestarray-updated')

        @gen.coroutine
        def yield_array(self, *args, **kwargs):
            raise gen.Return(initial_array)
        self.actor._find_server_arrays = yield_array

        @gen.coroutine
        def update_array(array, params):
            array.updated(params)
            raise gen.Return(updated_array)
        self.client_mock.update_server_array.side_effect = update_array

        @gen.coroutine
        def launch_array(array):
            array.launched()
            raise gen.Return()
        self.actor._launch_min_instances = launch_array

        @gen.coroutine
        def wait(array):
            array.waited()
            raise gen.Return()
        self.actor._wait_until_healthy = wait

        ret = yield self.actor._execute()

        # Verify that the array object would have been patched
        self.client_mock.update_server_array.assert_called_once_with(
            initial_array,  {'server_array[state]': 'enabled'})
        initial_array.updated.assert_called_once_with(
            {'server_array[state]': 'enabled'})

        # Now verify that each of the steps (terminate, wait, destroyed) were
        # all called.
        updated_array.launched.assert_called_once_with()
        updated_array.waited.assert_called_once_with()
        self.assertEquals(ret, True)


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
        @gen.coroutine
        def login():
            raise gen.Return()
        self.client_mock.login.side_effect = login

    @testing.gen_test
    def test_get_operational_instances_warn(self):
        mock_array = mock.MagicMock(name='array')
        mock_op_instance = mock.MagicMock(name='mock_instance')
        mock_op_instance.soul = {'state': 'operational'}
        mock_non_op_instance = mock.MagicMock(name='mock_instance')
        mock_non_op_instance.soul = {'state': 'booting'}

        @gen.coroutine
        def yi(array, filters):
            raise gen.Return([
                mock_op_instance,
                mock_non_op_instance,
                mock_op_instance,
            ])
        self.client_mock.get_server_array_current_instances.side_effect = yi

        ret = yield self.actor._get_operational_instances(mock_array)
        self.assertEquals(2, len(ret))

    @testing.gen_test
    def test_execute(self):
        mock_array = mock.MagicMock(name='array')
        mock_op_instance = mock.MagicMock(name='mock_instance')
        mock_op_instance.soul = {'state': 'operational'}
        mock_task = mock.MagicMock(name='mock_task')

        @gen.coroutine
        def yield_array(self, *args, **kwargs):
            raise gen.Return(mock_array)
        self.actor._find_server_arrays = yield_array

        @gen.coroutine
        def yi(*args, **kwargs):
            raise gen.Return([mock_op_instance])
        self.client_mock.get_server_array_current_instances.side_effect = yi

        @gen.coroutine
        def run_e(*args, **kwargs):
            raise gen.Return([mock_task])
        self.client_mock.run_executable_on_instances.side_effect = run_e

        @gen.coroutine
        def wait(*args, **kwargs):
            raise gen.Return(True)
        self.client_mock.wait_for_task.side_effect = wait

        ret = yield self.actor._execute()

        # Now verify that each of the steps (terminate, wait, destroyed) were
        # all called.
        (self.client_mock.get_server_array_current_instances
            .assert_called_twice_with(mock_array))
        (self.client_mock.run_executable_on_instances
            .assert_called_once_with(
                'test_script',
                {'inputs[foo]': 'text:bar'},
                [mock_op_instance]))
        (self.client_mock.wait_for_task
            .assert_called_once_with(mock_task))

        self.assertEquals(ret, True)

    @testing.gen_test
    def test_execute_dry(self):
        self.actor._dry = True
        mock_array = mock.MagicMock(name='array')
        mock_instance = mock.MagicMock(name='mock_instance')

        @gen.coroutine
        def yield_array(self, *args, **kwargs):
            raise gen.Return(mock_array)
        self.actor._find_server_arrays = yield_array

        @gen.coroutine
        def yi(*args, **kwargs):
            raise gen.Return([mock_instance])
        self.client_mock.get_server_array_current_instances.side_effect = yi

        ret = yield self.actor._execute()

        # Now verify that each of the steps (terminate, wait, destroyed) were
        # all called.
        self.assertEquals(ret, True)
