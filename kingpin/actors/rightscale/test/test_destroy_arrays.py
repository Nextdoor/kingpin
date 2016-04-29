import logging
import mock

from tornado import testing

from kingpin.actors.rightscale import base
from kingpin.actors.rightscale import server_array, destroy_arrays
from kingpin.actors.test.helper import mock_tornado, mock_tornado_sequence

log = logging.getLogger(__name__)


def create_mock_array(name):
    array = mock.MagicMock(name=name)
    array.soul = {'name': name}
    return array


class TestDestroyArrays(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestDestroyArrays, self).setUp()
        base.TOKEN = 'unittest'

        # Patch Destroy
        def create_destroy_mock_instance(*args, **kwargs):
            instance = mock.MagicMock()
            instance.execute.side_effect = mock_tornado()
            return instance

        destroy_patch = mock.patch.object(
            server_array, 'Destroy',
            autospec=True,
            side_effect=create_destroy_mock_instance)
        self.destroy_mock = destroy_patch.start()
        self.destroy_mock.side_effect = create_destroy_mock_instance
        self.addCleanup(destroy_patch.stop)

    def mock_find_server_arrays(self, actor, values_to_return):
        find_server_arrays_patch = mock.patch.object(
            actor,
            '_find_server_arrays',
            autospec=True,
            side_effect=mock_tornado_sequence(values_to_return))
        self.addCleanup(find_server_arrays_patch.stop)
        return find_server_arrays_patch.start()

    @testing.gen_test
    def test_destroy_one(self):
        array = mock.MagicMock(name='my-array')
        array.soul = {'name': 'my-array'}

        actor = destroy_arrays.DestroyMany('Destroy', {'target': 'my-array'})

        mock_find = self.mock_find_server_arrays(actor, [[array]])

        ret = yield actor.execute()

        self.assertEquals(self.destroy_mock.call_args_list,
                          [mock.call('Destroy', {'array': 'my-array'},
                                     warn_on_failure=False, dry=False)])
        self.assertEquals(mock_find.call_args_list,
                          [mock.call('my-array', raise_on=None)])
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_destroy_one_array_target(self):
        array = mock.MagicMock(name='my-array')
        array.soul = {'name': 'my-array'}

        actor = destroy_arrays.DestroyMany('Destroy', {'target': ['my-array']})

        mock_find = self.mock_find_server_arrays(actor, [[array]])

        ret = yield actor.execute()

        self.assertEquals(self.destroy_mock.call_args_list,
                          [mock.call('Destroy', {'array': 'my-array'},
                                     warn_on_failure=False, dry=False)])
        self.assertEquals(mock_find.call_args_list,
                          [mock.call('my-array', raise_on=None)])
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_destroys_many(self):
        array1 = create_mock_array('my-array1')
        array2 = create_mock_array('my-array2')

        actor = destroy_arrays.DestroyMany('Destroy', {'target': 'my-array'})

        mock_find = self.mock_find_server_arrays(actor, [[array1, array2]])

        ret = yield actor.execute()

        self.assertEquals(self.destroy_mock.call_args_list,
                          [mock.call('Destroy', {'array': 'my-array1'},
                                     warn_on_failure=False, dry=False),
                           mock.call('Destroy', {'array': 'my-array2'},
                                     warn_on_failure=False, dry=False)])
        self.assertEquals(mock_find.call_args_list,
                          [mock.call('my-array', raise_on=None)])
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_does_not_destroy_excluded(self):
        array = create_mock_array('my-array')
        excluded_array = create_mock_array('my-array-excluded')

        actor = destroy_arrays.DestroyMany('Destroy', {'target': 'my-array',
                                                       'exclude': 'excluded'})

        mock_find = self.mock_find_server_arrays(actor, [[array],
                                                         [excluded_array]])

        ret = yield actor.execute()

        self.assertEquals(self.destroy_mock.call_args_list,
                          [mock.call('Destroy', {'array': 'my-array'},
                                     warn_on_failure=False, dry=False)])
        self.assertEquals(mock_find.call_args_list,
                          [mock.call('my-array', raise_on=None),
                           mock.call('excluded', raise_on=None)])
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_dry_run(self):
        array = create_mock_array('my-array')

        actor = destroy_arrays.DestroyMany('Destroy', {'target': 'my-array'},
                                           dry=True)

        mock_find = self.mock_find_server_arrays(actor, [[array]])

        ret = yield actor.execute()

        self.assertEquals(self.destroy_mock.call_args_list,
                          [mock.call('Destroy', {'array': 'my-array'},
                                     warn_on_failure=False, dry=True)])
        self.assertEquals(mock_find.call_args_list,
                          [mock.call('my-array', raise_on=None)])
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_warn_on_failure(self):
        array = create_mock_array('my-array')

        actor = destroy_arrays.DestroyMany('Destroy', {'target': 'my-array'},
                                           warn_on_failure=True)

        mock_find = self.mock_find_server_arrays(actor, [[array]])

        ret = yield actor.execute()

        self.assertEquals(self.destroy_mock.call_args_list,
                          [mock.call('Destroy', {'array': 'my-array'},
                                     warn_on_failure=True, dry=False)])
        self.assertEquals(mock_find.call_args_list,
                          [mock.call('my-array', raise_on=None)])
        self.assertEquals(ret, None)
