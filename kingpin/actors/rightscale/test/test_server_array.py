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
                source_array.soul.path = '/fo/bar/123'
                raise gen.Return(source_array)
            if name == 'newunitarray':
                raise gen.Return(None)
        self.actor._find_server_arrays = find_server_arrays

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
        def find_server_arrays(name, *args, **kwargs):
            if name == 'unittestarray':
                source_array = mock.MagicMock(name='unittestarray')
                source_array.soul.path = '/fo/bar/123'
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
                'params': {'name': 'newunitarray'}})

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

        ret = yield self.actor.execute()

        self.client_mock.update_server_array.assert_called_once_with(
            mocked_array, {'server_array[name]': 'newunitarray'})

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
