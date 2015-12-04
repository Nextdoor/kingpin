import logging
import mock

from tornado import testing

from kingpin.actors import exceptions
from kingpin.actors.rightscale import base
from kingpin.actors.test.helper import mock_tornado

log = logging.getLogger(__name__)


class TestRightScaleBaseActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestRightScaleBaseActor, self).setUp()
        base.TOKEN = 'unittest'

        # Create the actor
        self.actor = base.RightScaleBaseActor(
            'Copy UnitTestArray to NewUnitArray', {})

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock()
        self.actor._client = self.client_mock

    @testing.gen_test
    def test_init_without_environment_creds(self):
        # Un-set the token and make sure the init fails
        base.TOKEN = None
        with self.assertRaises(exceptions.InvalidCredentials):
            base.RightScaleBaseActor('Unit Test Action', {})

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
    def test_find_server_arrays_many_returned(self):
        mocked_array1 = mock.MagicMock(name='mocked array1')
        mocked_array2 = mock.MagicMock(name='mocked array2')

        mock_find = mock_tornado([mocked_array1, mocked_array2])
        self.client_mock.find_server_arrays = mock_find

        ret = yield self.actor._find_server_arrays('t', raise_on='notfound')
        self.assertEquals([mocked_array1, mocked_array2], ret)

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

    def test_generate_rightscale_params_with_invalid_params(self):
        actor = base.RightScaleBaseActor('Unit Test Action', {})
        with self.assertRaises(exceptions.InvalidOptions):
            actor._generate_rightscale_params('test', ['a', 'b'])

        with self.assertRaises(exceptions.InvalidOptions):
            actor._generate_rightscale_params('test', 'foo')

    def test_generate_rightscale_params(self):
        params = {'name': 'unittest-name',
                  'status': 'enabled',
                  'elasticity_params': {
                      'bounds': {
                          'min_count': 3,
                          'max_count': 10}}}
        expected_params = [
            ('server_array[status]', 'enabled'),
            ('server_array[name]', 'unittest-name'),
            ('server_array[elasticity_params][bounds][max_count]', 10),
            ('server_array[elasticity_params][bounds][min_count]', 3)]

        actor = base.RightScaleBaseActor('Unit Test Action', {})
        ret = actor._generate_rightscale_params('server_array', params)

        self.assertItemsEqual(expected_params, ret)

    def test_generate_rightscale_params_with_array(self):
        self.maxDiff = None
        schedule = [
            {'day': 'Sunday', 'max_count': 2, 'min_count': 1, 'time': '07:00'},
            {'day': 'Monday', 'max_count': 2, 'min_count': 1, 'time': '07:00'},
            {'day': 'Tuesday', 'max_count': 2, 'min_count': 1, 'time': '07:00'}
        ]
        params = {
            'elasticity_params': {'schedule': schedule}
        }

        expected_params = [[
            ('server_array[elasticity_params][schedule][][day]', 'Sunday'),
            ('server_array[elasticity_params][schedule][][max_count]', 2),
            ('server_array[elasticity_params][schedule][][min_count]', 1),
            ('server_array[elasticity_params][schedule][][time]', '07:00'),
        ], [
            ('server_array[elasticity_params][schedule][][day]', 'Monday'),
            ('server_array[elasticity_params][schedule][][max_count]', 2),
            ('server_array[elasticity_params][schedule][][min_count]', 1),
            ('server_array[elasticity_params][schedule][][time]', '07:00'),
        ], [
            ('server_array[elasticity_params][schedule][][day]', 'Tuesday'),
            ('server_array[elasticity_params][schedule][][max_count]', 2),
            ('server_array[elasticity_params][schedule][][min_count]', 1),
            ('server_array[elasticity_params][schedule][][time]', '07:00')
        ]]

        actor = base.RightScaleBaseActor('Unit Test Action', {})
        ret = actor._generate_rightscale_params('server_array', params)

        # Relevant commit: d403420ccc482f2f91eab0eebd38100b3eff6344
        # Groups of 4 have to contain all the needed data

        # Break into chunks of 4 items.
        ret_chunks = zip(*[iter(ret)] * 4)

        self.assertItemsEqual(expected_params[0], ret_chunks[0])
        self.assertItemsEqual(expected_params[1], ret_chunks[1])
        self.assertItemsEqual(expected_params[2], ret_chunks[2])
