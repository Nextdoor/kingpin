import logging
import mock

from tornado import testing
from tornado import gen

from kingpin.actors import exceptions
from kingpin.actors.rightscale import api
from kingpin.actors.rightscale import base
from kingpin.actors.rightscale import server_array

log = logging.getLogger(__name__)


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

    @testing.gen_test
    def test_init_without_proper_options(self):
        with self.assertRaises(exceptions.InvalidOptions):
            server_array.Clone('Unit Test Action', {'dest': 'foo'})

        with self.assertRaises(exceptions.InvalidOptions):
            server_array.Clone('Unit Test Action', {'source': 'foo'})

    @testing.gen_test
    def test_execute_with_missing_template(self):
        @gen.coroutine
        def yield_source_template(self, *args, **kwargs):
            raise gen.Return(None)
        self.client_mock.find_server_arrays.side_effect = yield_source_template

        with self.assertRaises(api.ServerArrayException):
            yield self.actor.execute()

    @testing.gen_test
    def test_execute_with_existing_destination(self):

        @gen.coroutine
        def find_server_arrays(name, exact=True):
            if name == 'unittestarray':
                raise gen.Return(mock.MagicMock(name='unittestarray'))
            if name == 'newunitarray':
                raise gen.Return(mock.MagicMock(name='newunitarray'))
        self.client_mock.find_server_arrays.side_effect = find_server_arrays

        with self.assertRaises(api.ServerArrayException):
            yield self.actor.execute()

    @testing.gen_test
    def test_execute(self):

        @gen.coroutine
        def find_server_arrays(name, exact=True):
            if name == 'unittestarray':
                source_array = mock.MagicMock(name='unittestarray')
                source_array.soul.path = '/fo/bar/123'
                raise gen.Return(source_array)
            if name == 'newunitarray':
                raise gen.Return(None)
        self.client_mock.find_server_arrays.side_effect = find_server_arrays

        @gen.coroutine
        def clone_server_array(array):
            new_array = mock.MagicMock(name='unittestarray v1')
            new_array.soul.path = '/foo/bar/124'
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
        def find_server_arrays(name, exact=True):
            if name == 'unittestarray':
                source_array = mock.MagicMock(name='unittestarray')
                source_array.soul.path = '/fo/bar/123'
                raise gen.Return(source_array)
            if name == 'newunitarray':
                raise gen.Return(None)
        self.client_mock.find_server_arrays.side_effect = find_server_arrays

        @gen.coroutine
        def update_server_array(array, params):
            raise gen.Return()
        self.client_mock.update_server_array.side_effect = update_server_array

        ret = yield self.actor.execute()
        self.assertEquals(True, ret)
