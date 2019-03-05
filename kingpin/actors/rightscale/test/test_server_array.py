import logging
import mock
import time

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

    @testing.gen_test
    def test_apply(self):
        # Fake method used to test the apply function
        @gen.coroutine
        def fake_func(array, ret_val):
            raise gen.Return(ret_val)

        # Test 1: Pass in a single array
        arrays = [mock.MagicMock()]
        ret = yield self.actor._apply(fake_func, arrays, ret_val=1)
        self.assertEqual(ret, [1])

        # Test 2: Pass in several arrays
        arrays = [mock.MagicMock(), mock.MagicMock()]
        ret = yield self.actor._apply(fake_func, arrays, ret_val=1)
        self.assertEqual(ret, [1, 1])


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

    def test_less_strict_source_and_dest(self):
        self.actor = server_array.Clone('Copy UnitTestArray to NewUnitArray',
                                        {'source': 'unittestarray',
                                         'strict_source': False,
                                         'dest': 'newunitarray',
                                         'strict_dest': False})

        self.assertEqual(self.actor._source_raise_on, None)
        self.assertEqual(self.actor._dest_raise_on, None)
        self.assertEqual(self.actor._source_allow_mock, True)
        self.assertEqual(self.actor._dest_allow_mock, True)

    @testing.gen_test
    def test_execute(self):

        source_array = mock.MagicMock(name='unittestarray')
        source_array.self.path = '/fo/bar/123'
        self.actor._find_server_arrays = mock_tornado(source_array)

        new_array = mock.MagicMock(name='unittestarray v1')
        new_array.self.path = '/foo/bar/124'
        self.client_mock.clone_server_array = mock_tornado(new_array)

        self.client_mock.update = mock_tornado()

        ret = yield self.actor._execute()
        self.assertEqual(None, ret)

    @testing.gen_test
    def test_execute_in_dry_mode(self):
        self.actor._dry = True

        source_array = mock.MagicMock(name='unittestarray')
        source_array.self.path = '/fo/bar/123'
        self.actor._find_server_arrays = mock_tornado(source_array)

        self.client_mock.update = mock_tornado()

        ret = yield self.actor._execute()
        self.assertEqual(None, ret)


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

    @testing.gen_test
    def test_check_inputs_empty(self):
        array = mock.Mock()
        array.soul = {'name': 'real array'}
        inputs = {}
        self.actor._client.get_server_array_inputs = mock_tornado([])
        ok = yield self.actor._check_array_inputs(array, inputs)
        self.assertEqual(ok, None)

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
        self.assertEqual(ok, None)

    @testing.gen_test
    def test_execute(self):
        self.actor._dry = False
        mocked_array = mock.MagicMock(name='unittestarray')

        self.actor._check_array_inputs = mock_tornado(True)
        self.actor._find_server_arrays = mock_tornado(mocked_array)

        self.client_mock.update.return_value = tornado_value(None)

        self.client_mock.update_server_array_inputs.return_value = (
            tornado_value(None))

        ret = yield self.actor._execute()

        self.client_mock.update.assert_called_once_with(
            mocked_array, [('server_array[name]', 'newunitarray')])
        self.client_mock.update_server_array_inputs.assert_called_once_with(
            mocked_array, [('inputs[test]', 'text:test')])

        self.assertEqual(None, ret)

    @testing.gen_test
    def test_update_inputs_empty(self):
        mocked_array = mock.MagicMock(name='unittestarray')
        self.actor._options['inputs'] = None

        yield self.actor._update_inputs(mocked_array)
        self.assertEqual(0, mocked_array.call_count)

    @testing.gen_test
    def test_update_params_empty(self):
        mocked_array = mock.MagicMock(name='unittestarray')
        self.actor._options['params'] = None

        yield self.actor._update_params(mocked_array)
        self.assertEqual(0, mocked_array.call_count)

    @testing.gen_test
    def test_execute_500_error_raises_exc(self):
        mocked_array = mock.MagicMock(name='unittestarray')

        self.actor._check_array_inputs = mock_tornado(True)
        self.actor._find_server_arrays = mock_tornado(mocked_array)

        msg = '500 : Unknown error'
        mocked_response = mock.MagicMock(name='response')
        mocked_response.status_code = 500
        error = requests.exceptions.HTTPError(msg, response=mocked_response)
        self.client_mock.update.side_effect = error

        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            yield self.actor._execute()

        self.client_mock.update.assert_called_once_with(
            mocked_array, [('server_array[name]', 'newunitarray')])

    @testing.gen_test
    def test_execute_422_error(self):
        mocked_array = mock.MagicMock(name='unittestarray')

        self.actor._check_array_inputs = mock_tornado(True)
        self.actor._find_server_arrays = mock_tornado(mocked_array)

        error = api.RightScaleError('error doing thing')
        self.client_mock.update.side_effect = error

        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._execute()

        self.client_mock.update.assert_called_once_with(
            mocked_array, [('server_array[name]', 'newunitarray')])

    @testing.gen_test
    def test_execute_dry(self):
        self.actor._dry = True
        mocked_array = mock.MagicMock(name='fake array')
        mocked_array.soul = {'name': 'mocked-array'}
        mocked_array.self.path = '/a/b/1234'

        self.actor._check_array_inputs = mock_tornado(True)
        self.actor._find_server_arrays = mock_tornado(mocked_array)

        ret = yield self.actor._execute()
        self.assertEqual(None, ret)

    @testing.gen_test
    def test_execute_dry_with_missing_array(self):
        self.actor._dry = True
        mocked_array = mock.MagicMock(name='unittestarray')
        mocked_array.soul = {'name': 'unittestarray'}

        self.actor._check_array_inputs = mock_tornado(True)
        self.actor._find_server_arrays = mock_tornado(mocked_array)

        ret = yield self.actor._execute()
        self.assertEqual(None, ret)


class TestUpdateNextInstanceActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestUpdateNextInstanceActor, self).setUp()
        base.TOKEN = 'unittest'

        # Create the actor
        self.actor = server_array.UpdateNextInstance(
            options={'array': 'unittestarray',
                     'params': {'image_href': 'default'}})

        # Patch the actor so that we use the client mock. Save the real
        # "client" object because its actually used during a unit test.
        self.client_mock = mock.MagicMock()
        self.actor._orig_client = self.actor._client
        self.actor._client = self.client_mock

        # Validate that the actor._params were saved properly the first time
        # and that the 'image_href' was not modified.
        self.assertEqual(
            self.actor._params, [('instance[image_href]', 'default')])

    @testing.gen_test
    def test_update_params(self):
        # Mock out our array object, and the next_instance. Then mock out the
        # api.show() method to return the mocked instance. Verify that the
        # right calls were made to the API though.
        mocked_array = mock.MagicMock(name='unittestarray')
        mocked_instance = mock.MagicMock(name='nextinstance')
        self.actor._find_def_image_href = mock_tornado('fake_href')
        self.actor._client.show.side_effect = mock_tornado(mocked_instance)
        self.actor._client.update.side_effect = mock_tornado(True)

        yield self.actor._update_params(mocked_array)

        self.client_mock.show.assert_has_calls([
            mock.call(mocked_array.next_instance),
        ])
        self.client_mock.update.assert_has_calls([
            mock.call(mocked_instance, [('instance[image_href]', 'fake_href')])
        ])

    @testing.gen_test
    def test_update_params_dry(self):
        self.actor._dry = True

        # Mock out our array object, and the next_instance. Then mock out the
        # api.show() method to return the mocked instance. Verify that the
        # right calls were made to the API though.
        mocked_array = mock.MagicMock(name='unittestarray')
        mocked_instance = mock.MagicMock(name='nextinstance')
        self.actor._find_def_image_href = mock_tornado('fake_href')
        self.actor._client.show.side_effect = mock_tornado(mocked_instance)
        self.actor._client.update.side_effect = mock_tornado(True)

        yield self.actor._update_params(mocked_array)

        self.client_mock.show.assert_has_calls([
            mock.call(mocked_array.next_instance),
        ])
        self.assertFalse(self.client_mock.update.called)

    @testing.gen_test
    def test_update_params_400_error(self):
        # Mock out our array object, and the next_instance. Then mock out the
        # api.show() method to return the mocked instance. Verify that the
        # right calls were made to the API though.
        mocked_array = mock.MagicMock(name='unittestarray')
        mocked_instance = mock.MagicMock(name='nextinstance')
        self.actor._find_def_image_href = mock_tornado('fake_href')
        self.actor._client.show.side_effect = mock_tornado(mocked_instance)

        error = api.RightScaleError('error')
        self.client_mock.update.side_effect = error

        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._update_params(mocked_array)

    @testing.gen_test
    def test_update_params_500_error(self):
        # Mock out our array object, and the next_instance. Then mock out the
        # api.show() method to return the mocked instance. Verify that the
        # right calls were made to the API though.
        mocked_array = mock.MagicMock(name='unittestarray')
        mocked_instance = mock.MagicMock(name='nextinstance')
        self.actor._find_def_image_href = mock_tornado('fake_href')
        self.actor._client.show.side_effect = mock_tornado(mocked_instance)

        msg = '500 Unknown Error'
        mocked_response = mock.MagicMock(name='response')
        mocked_response.status_code = 500
        error = requests.exceptions.HTTPError(msg, response=mocked_response)
        self.client_mock.update.side_effect = error

        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            yield self.actor._update_params(mocked_array)

    @testing.gen_test
    def test_find_def_image_href(self):
        # Mock up the final 'MCI Settings' objets that we'll be sorting through
        # looking for a matching 'cloud' HREF.
        mock_setting_1 = mock.MagicMock(name='setting1')
        mock_setting_1.cloud.path = '/cloud/1'
        mock_setting_1.soul = {}  # no links.. this would fail if called
        mock_setting_2 = mock.MagicMock(name='setting2')
        mock_setting_2.cloud.path = '/cloud/2'
        mock_setting_2.soul = {
            'links': [
                {'rel': 'foo', 'href': '/foo'},
                {'rel': 'image', 'href': '/test/image'},
            ]
        }

        # Mock up a single MCI object that returns the above settings objects
        mocked_mci = mock.MagicMock(name='mci')
        mocked_mci.settings.show.return_value = [
            mock_setting_1,
            mock_setting_2
        ]

        # Finally, mock out an instance thats using our above template.
        mocked_instance = mock.MagicMock(name='nextinstance')
        mocked_instance.soul = {'name': 'nextinstance'}
        mocked_instance.cloud.path = '/cloud/2'
        mocked_instance.multi_cloud_image.show.return_value = mocked_mci

        # For ease of testing, we put the real RightScale Client API object
        # back in place and use its show() method for real. Our mocks above
        # ensure that we don't make any real API calls.
        self.actor._client = self.actor._orig_client

        # Execute the method
        ret = yield self.actor._find_def_image_href(mocked_instance)
        # Did we ultimatley get back /test/image?
        self.assertEqual('/test/image', ret)

        # Second test -- written inline with the first test to avoid the
        # massive setup process above.
        mocked_instance.cloud.path = '/cloud/1'
        with self.assertRaises(server_array.InvalidInputs):
            yield self.actor._find_def_image_href(mocked_instance)

    @testing.gen_test
    def test_execute(self):
        self.actor._dry = False
        mocked_array = mock.MagicMock(name='unittestarray')

        self.actor._update_params = mock_tornado(True)
        self.actor._find_server_arrays = mock_tornado(mocked_array)

        ret = yield self.actor._execute()

        self.assertEqual(None, ret)

    @testing.gen_test
    def test_execute_with_missing_array(self):
        mocked_array = mock.MagicMock(name='unittestarray')
        mocked_array.soul = {'name': 'unittestarray'}

        self.actor._update_params = mock_tornado(True)
        self.actor._find_server_arrays = mock_tornado(mocked_array)

        ret = yield self.actor._execute()
        self.assertEqual(None, ret)


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

    def test_less_strict(self):
        self.actor = server_array.Terminate('Terminate',
                                            {'array': 'unittestarray',
                                             'strict': False})
        self.assertEqual(self.actor._raise_on, None)
        self.assertEqual(self.actor._allow_mock, True)

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
        self.assertEqual(ret, None)
        self.assertEqual(
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
        self.assertEqual(ret, None)
        self.assertEqual(
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
        self.assertEqual(get_func.call_count, 4)
        self.assertEqual(ret, None)

    @testing.gen_test
    def test_wait_until_empty_dry(self):
        self.actor._dry = True
        array_mock = mock.MagicMock(name='unittest')
        ret = yield self.actor._wait_until_empty(array_mock)
        self.assertEqual(ret, None)

    @testing.gen_test
    def test_disable_array(self):
        array_mock = mock.MagicMock(name='unittest')
        array_mock.soul = {'name': 'unittest'}
        array_mock.self.path = '/a/b/1234'
        self.client_mock.update.side_effect = mock_tornado()

        yield self.actor._disable_array(array_mock)
        self.client_mock.update.assert_has_calls([
            mock.call(array_mock, [('server_array[state]', 'disabled')])])

    @testing.gen_test
    def test_execute(self):
        self.actor._dry = False
        initial_array = mock.MagicMock(name='unittestarray')
        self.actor._find_server_arrays = mock_tornado(initial_array)

        @gen.coroutine
        def update_array(array, params):
            array.updated(params)

        self.client_mock.update.side_effect = update_array
        self.actor._terminate_all_instances = mock_tornado()
        self.actor._wait_until_empty = mock_tornado()
        ret = yield self.actor._execute()

        # Verify that the array object would have been patched
        self.client_mock.update.assert_called_once_with(
            initial_array, [('server_array[state]', 'disabled')])
        initial_array.updated.assert_called_once_with(
            [('server_array[state]', 'disabled')])

        # Now verify that each of the steps (terminate, wait, destroyed) were
        # all called.
        self.assertEqual(self.actor._wait_until_empty._call_count, 1)
        self.assertEqual(self.actor._terminate_all_instances._call_count, 1)
        self.assertEqual(ret, None)

    @testing.gen_test
    def test_execute_dry(self):
        self.actor._dry = True
        initial_array = mock.MagicMock(name='unittestarray')
        self.actor._find_server_arrays = mock_tornado(initial_array)

        @gen.coroutine
        def update_array(array, params):
            array.updated(params)
        self.client_mock.update.side_effect = update_array

        # ensure that we never called the update_array method!
        yield self.actor._execute()
        initial_array.updated.assert_has_calls([])


class TestDestroyActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestDestroyActor, self).setUp()
        base.TOKEN = 'unittest'

        # Create the actor
        self.actor = server_array.Destroy(
            'Destroy',
            {'array': 'unittestarray'})

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock()
        self.actor._client = self.client_mock

    @testing.gen_test
    def test_destroy_array(self):
        array = mock.MagicMock(name='unittest')
        array.soul = {'name': 'unittest'}

        self.actor._client = mock.Mock()
        self.actor._client.destroy_server_array.side_effect = tornado_value

        yield self.actor._destroy_array(array)
        self.actor._client.destroy_server_array.called_with(array)

        self.actor._dry = True
        yield self.actor._destroy_array(array)
        self.actor._client.destroy_server_array.called_with(array)

    @testing.gen_test
    def test_execute(self):
        array = mock.MagicMock(name='unittest')
        array.soul = {'name': 'unittest'}

        # Mock out calls that are made in the Super class (Terminate)
        # _execute function.
        self.actor._find_server_arrays = mock_tornado(array)
        self.actor._disable_array = mock_tornado()
        self.actor._terminate_all_instances = mock_tornado()
        self.actor._wait_until_empty = mock_tornado()

        # Mock out the destroy_array call
        self.actor._destroy_array = mock_tornado()

        ret = yield self.actor._execute()

        self.assertEqual(self.actor._destroy_array._call_count, 1)
        self.assertEqual(ret, None)


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

    @testing.gen_test
    def test_requirements(self):

        with self.assertRaises(exceptions.InvalidOptions):
            # Bad string passed in as count
            server_array.Launch(
                'Unit test', {
                    'array': 'unit test array',
                    'count': 'foo'
                })

    @testing.gen_test
    def test_wait_until_healthy(self):
        array_mock = mock.MagicMock(name='unittest')
        array_mock.soul = {
            'name': 'unittest',
            'elasticity_params': {'bounds': {'max_count': '4'}}}

        server_list = []

        @gen.coroutine
        def get(self, *args, **kwargs):
            server_list.append('x')
            raise gen.Return(server_list)
        self.client_mock.get_server_array_current_instances = get

        ret = yield self.actor._wait_until_healthy(array_mock, sleep=0.01)
        self.assertEqual(len(server_list), 4)
        self.assertEqual(ret, None)

        # Now run the same test, but in dry mode..
        self.actor._dry = True
        server_list = []
        ret = yield self.actor._wait_until_healthy(array_mock, sleep=0.01)
        self.assertEqual(len(server_list), 0)
        self.assertEqual(ret, None)

    @testing.gen_test
    def test_wait_until_healthy_based_on_specific_count(self):
        # Set the 'count' option to 2 in the Actor
        self.actor._options['count'] = 2

        # Now proceed with creating a fake array, etc.
        array_mock = mock.MagicMock(name='unittest')
        array_mock.soul = {
            'name': 'unittest',
            'elasticity_params': {'bounds': {'max_count': '4'}}}

        server_list = []

        @gen.coroutine
        def get(self, *args, **kwargs):
            server_list.append('x')
            raise gen.Return(server_list)
        self.client_mock.get_server_array_current_instances = get

        ret = yield self.actor._wait_until_healthy(array_mock, sleep=0.01)
        self.assertEqual(len(server_list), 2)
        self.assertEqual(ret, None)

        # Now run the same test, but in dry mode..
        self.actor._dry = True
        server_list = []
        ret = yield self.actor._wait_until_healthy(array_mock, sleep=0.01)
        self.assertEqual(len(server_list), 0)
        self.assertEqual(ret, None)

    @testing.gen_test
    def test_launch_instances(self):
        array_mock = mock.MagicMock(name='unittest')
        array_mock.soul = {
            'name': 'unittest',
            'elasticity_params': {'bounds': {'max_count': '4'}}}

        launch = mock_tornado()
        self.client_mock.launch_server_array.side_effect = launch

        # Regular function call
        self.client_mock.get_server_array_current_instances = mock_tornado([])
        self.client_mock.launch_server_array.reset_mock()
        yield self.actor._launch_instances(array_mock)
        self.assertEqual(1, self.client_mock.launch_server_array.call_count)
        self.client_mock.launch_server_array.assert_has_calls(
            [mock.call(array_mock, count=4)])

        # Regular function call with some servers already existing.
        self.client_mock.get_server_array_current_instances = mock_tornado([
            1, 2])
        self.client_mock.launch_server_array.reset_mock()
        yield self.actor._launch_instances(array_mock)
        self.client_mock.launch_server_array.assert_has_calls(
            [mock.call(array_mock, count=2)])

        # Regular function call more arrays than max_count
        self.client_mock.get_server_array_current_instances = mock_tornado([
            1, 2, 3, 4, 5])
        self.client_mock.launch_server_array.reset_mock()
        yield self.actor._launch_instances(array_mock)
        self.assertEqual(self.client_mock.launch_server_array.call_count, 0)

        # Dry call
        self.actor._dry = True
        self.client_mock.launch_server_array.reset_mock()
        yield self.actor._launch_instances(array_mock)
        self.client_mock.launch_server_array.assert_has_calls([])

    @testing.gen_test
    def test_enable_array(self):
        initial_array = mock.MagicMock(name='unittestarray')
        updated_array = mock.MagicMock(name='unittestarray-updated')

        @gen.coroutine
        def update_array(array, params):
            array.updated(params)
            raise gen.Return(updated_array)
        self.client_mock.update.side_effect = update_array

        # Verify that the array object would have been patched
        yield self.actor._enable_array(initial_array)
        self.client_mock.update.assert_called_once_with(
            initial_array, [('server_array[state]', 'enabled')])
        initial_array.updated.assert_called_once_with(
            [('server_array[state]', 'enabled')])

        # Reset for a dry run
        self.actor._dry = True
        initial_array.reset_mock()
        updated_array.reset_mock()

        # Run it again, object shoudl NOT be updated.
        yield self.actor._enable_array(initial_array)
        self.assertEqual(initial_array.updated.call_count, 0)

    @testing.gen_test
    def test_disabled_no_launch(self):
        self.actor._options['enable'] = False
        self.actor._options['count'] = 0

        mocked_array = mock.MagicMock(name='unittest')
        mocked_array.soul = {'name': 'unittest'}
        self.actor._find_server_arrays = mock_tornado(mocked_array)
        self.actor._apply = mock.MagicMock(name='apply')
        self.actor._apply.side_effect = mock_tornado()

        yield self.actor._execute()

        # Now verify that the right calls were made
        self.actor._apply.assert_has_calls([
            mock.call(self.actor._enable_array, mocked_array),
            mock.call(self.actor._launch_instances, mocked_array, False),
            mock.call(self.actor._wait_until_healthy, mocked_array),
        ])

    @testing.gen_test
    def test_execte(self):
        mocked_array = mock.MagicMock(name='unittest')
        mocked_array.soul = {'name': 'unittest'}
        self.actor._find_server_arrays = mock_tornado(mocked_array)
        self.actor._apply = mock.MagicMock(name='apply')
        self.actor._apply.side_effect = mock_tornado()

        yield self.actor._execute()

        # Now verify that the right calls were made
        self.actor._apply.assert_has_calls([
            mock.call(self.actor._enable_array, mocked_array),
            mock.call(self.actor._launch_instances, mocked_array, False),
            mock.call(self.actor._wait_until_healthy, mocked_array),
        ])


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
        self.assertEqual(2, len(ret))

    @testing.gen_test
    def test_exec_and_wait(self):
        self.client_mock.run_executable_on_instances = mock_tornado(['test'])
        self.client_mock.wait_for_task = mock_tornado('success-test')
        ret = yield self.actor._exec_and_wait('', {}, [], 1)

        self.assertEqual(ret, 'success-test')
        self.assertEqual(
            self.client_mock.run_executable_on_instances._call_count, 1)
        self.assertEqual(self.client_mock.wait_for_task._call_count, 1)

    @testing.gen_test
    def test_execute_array_with_concurrency_dry(self):
        self.actor._get_operational_instances = mock_tornado(['test'])
        self.actor._dry = True
        yield self.actor._execute_array_with_concurrency(
            arrays='a4', inputs={})

    @testing.gen_test
    def test_execute_arrays_with_concurrency_dry(self):
        self.actor._get_operational_instances = mock_tornado(['test'])
        self.actor._dry = True
        yield self.actor._execute_array_with_concurrency(
            arrays=['a1', 'a2', 'a3', 'a4'], inputs={})

    @testing.gen_test
    def test_execute_array_with_concurrency(self):
        self.actor._get_operational_instances = mock_tornado(['test'])

        @gen.coroutine
        def local_sleep(name, inputs, instance, sleep):
            yield gen.sleep(.1)
            raise gen.Return(True)

        self.actor._exec_and_wait = local_sleep

        self.actor._options['concurrency'] = 2
        start = time.time()
        yield self.actor._execute_array_with_concurrency(
            arrays=['a1', 'a2', 'a3', 'a4'], inputs={})
        stop = time.time()
        exe_time = stop - start

        # Execution should take at least .2 seconds, but not .3
        self.assertTrue(.2 < exe_time < .3,
                        "Bad exec time. Expected .2 < %s < .3" % exe_time)

    @testing.gen_test
    def test_execute_array(self):
        mock_array = mock.MagicMock(name='array')
        mock_op_instance = mock.MagicMock(name='mock_instance')
        mock_op_instance.soul = {'state': 'operational',
                                 'name': 'unit-test-instance'}
        mock_task = mock.MagicMock(name='mock_task')

        yi = tornado_value([mock_op_instance])
        self.client_mock.get_server_array_current_instances.return_value = yi

        run_e = tornado_value([(mock_op_instance, mock_task)])
        self.client_mock.run_executable_on_instances.return_value = run_e

        wait = tornado_value(True)
        self.client_mock.wait_for_task.return_value = wait

        # Now verify that each of the expected steps were called in a
        # successful execution.
        ret = yield self.actor._execute_array(mock_array, 1)

        (self.client_mock.get_server_array_current_instances
            .assert_called_twice_with(mock_array))
        (self.client_mock.run_executable_on_instances
            .assert_called_once_with(
                'test_script', 1, [mock_op_instance]))

        self.client_mock.wait_for_task.assert_called_with(
            task=mock_task,
            task_name=('Executing "test_script" '
                       'on instance: unit-test-instance'),
            sleep=5,
            loc_log=self.actor.log,
            instance=mock_op_instance)
        self.assertEqual(ret, None)

        # Now mock out a failure of the script execution
        wait = mock_tornado(False)
        self.client_mock.wait_for_task = wait
        self.client_mock.get_audit_logs.side_effect = [
            tornado_value(False), tornado_value(['logs'])]
        with self.assertRaises(server_array.TaskExecutionFailed):
            yield self.actor._execute_array(mock_array, 1)

        # Finally, a test that mocks out an http error on bad inputs
        error = api.ServerArrayException()
        self.client_mock.run_executable_on_instances.side_effect = error
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._execute_array(mock_array, 1)

    @testing.gen_test
    def test_execute_array_dry(self):
        self.actor._dry = True
        mock_array = mock.MagicMock(name='array')

        self.client_mock.get_server_array_current_instances = mock_tornado([])

        ret = yield self.actor._execute_array(mock_array, 1)
        self.assertEqual(ret, None)

    @testing.gen_test
    def test_execute_concurrent(self):
        mock_array = mock.MagicMock(name='array')
        mock_array.soul = {'name': 'array'}
        self.actor._options['concurrency'] = 2
        self.actor._find_server_arrays = mock_tornado(mock_array)
        self.actor._execute_array_with_concurrency = mock.MagicMock()
        self.actor._execute_array_with_concurrency.side_effect = mock_tornado()

        yield self.actor._execute()

        self.actor._execute_array_with_concurrency.assert_has_calls([
            mock.call(mock_array,
                      [('inputs[foo]', 'text:bar')])])

    @testing.gen_test
    def test_execute(self):
        mock_array = mock.MagicMock(name='array')
        mock_array.soul = {'name': 'array'}
        self.actor._find_server_arrays = mock_tornado(mock_array)
        self.actor._apply = mock.MagicMock()
        self.actor._apply.side_effect = mock_tornado()

        yield self.actor._execute()
        self.actor._apply.assert_has_calls([
            mock.call(self.actor._execute_array,
                      mock_array,
                      [('inputs[foo]', 'text:bar')])])

    @testing.gen_test
    def test_execute_dry(self):
        self.actor._dry = True
        mock_array = mock.MagicMock(name='array')
        mock_array.soul = {'name': 'array'}
        self.actor._find_server_arrays = mock_tornado(mock_array)
        self.actor._check_script = mock_tornado(True)
        self.actor._apply = mock.MagicMock()
        self.actor._apply.side_effect = mock_tornado()
        yield self.actor._execute()
        self.actor._apply.assert_has_calls([
            mock.call(self.actor._execute_array,
                      mock_array, [('inputs[foo]', 'text:bar')])
        ])

    @testing.gen_test
    def test_execute_dry_fail(self):
        self.actor._dry = True
        mock_array = mock.MagicMock(name='array')
        self.actor._find_server_arrays = mock_tornado(mock_array)

        # Checking script fails
        self.actor._check_script = mock_tornado(False)
        self.client_mock.get_server_array_current_instances = mock_tornado([])

        with self.assertRaises(exceptions.InvalidOptions):
            yield self.actor._execute()
