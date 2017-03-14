from builtins import zip
import logging
import mock

import six

from tornado import testing
from tornado import gen

from kingpin.actors import exceptions
from kingpin.actors.rightscale import base
from kingpin.actors.test.helper import mock_tornado, tornado_value

log = logging.getLogger(__name__)


class FakeEnsurableRightScaleBaseActor(base.EnsurableRightScaleBaseActor):

    @gen.coroutine
    def _set_state(self):
        self.state = self.option('state')

    @gen.coroutine
    def _get_state(self):
        if self.state:
            raise gen.Return(self.state)


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

    @testing.gen_test
    def test_log_account_name(self):
        cloud_accounts = mock.MagicMock(name='cloud_accounts')
        mocked_account = mock.MagicMock(name='fake_account_obj')
        mocked_account.soul = {'name': 'test'}

        base.log = mock.MagicMock(name='mocked_logger')
        self.client_mock.show.side_effect = [
            tornado_value([cloud_accounts]),
            tornado_value(mocked_account)
        ]
        yield self.actor._log_account_name()

        base.log.assert_has_calls([
            mock.call.warning('RightScale account name: test')])

    @testing.gen_test
    def test_execute(self):
        self.actor._execute = mock_tornado(None)
        self.actor._log_account_name = mock_tornado(None)
        yield self.actor.execute()

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

        six.assertCountEqual(self, expected_params, ret)

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
        ret_chunks = list(zip(*[iter(ret)] * 4))

        six.assertCountEqual(self, expected_params[0], ret_chunks[0])
        six.assertCountEqual(self, expected_params[1], ret_chunks[1])
        six.assertCountEqual(self, expected_params[2], ret_chunks[2])

    def test_generate_rightscale_params_with_pure_array(self):
        params = [
            'testA',
            'testB',
            'testC'
        ]
        expected_params = [
            ('resource_hrefs[]', 'testA'),
            ('resource_hrefs[]', 'testB'),
            ('resource_hrefs[]', 'testC'),
        ]

        actor = base.RightScaleBaseActor('Unit Test Action', {})
        ret = actor._generate_rightscale_params('resource_hrefs', params)

        self.assertEquals(expected_params, ret)

    @testing.gen_test
    def test_get_resource_tags(self):
        resource = mock.MagicMock(name='resource')
        self.client_mock.get_resource_tags.side_effect = [
            tornado_value(None)
        ]
        ret = yield self.actor._get_resource_tags(resource=resource)
        self.assertEquals(None, ret)
        self.client_mock.get_resource_tags.assert_has_calls([
            mock.call(resource)
        ])

    @testing.gen_test
    def test_add_resource_tags(self):
        resource = mock.MagicMock(name='resource')
        self.client_mock.add_resource_tags.side_effect = [tornado_value(None)]
        yield self.actor._add_resource_tags(resource=resource, tags=['a', 'b'])
        self.client_mock.add_resource_tags.assert_has_calls([
            mock.call(resource, ['a', 'b'])
        ])

    @testing.gen_test
    def test_delete_resource_tags(self):
        resource = mock.MagicMock(name='resource')
        self.client_mock.delete_resource_tags.side_effect = [
            tornado_value(None)
        ]
        yield self.actor._delete_resource_tags(
            resource=resource, tags=['a', 'b'])
        self.client_mock.delete_resource_tags.assert_has_calls([
            mock.call(resource, ['a', 'b'])
        ])

    @testing.gen_test
    def test_ensure_tags_with_single_string(self):
        mci = mock.MagicMock(name='mci')
        mci.href = '/test'
        self.client_mock.get_resource_tags = mock.MagicMock(name='get')
        self.client_mock.get_resource_tags.side_effect = [
            tornado_value(['tag1', 'tag2'])
        ]

        self.client_mock.add_resource_tags = mock.MagicMock(name='add')
        self.client_mock.add_resource_tags.side_effect = [
            tornado_value(None)
        ]

        self.client_mock.delete_resource_tags = mock.MagicMock(name='delete')
        self.client_mock.delete_resource_tags.side_effect = [
            tornado_value(None)
        ]

        yield self.actor._ensure_tags(mci, 'tag')

        self.client_mock.add_resource_tags.assert_has_calls([
            mock.call(mci, ['tag'])
        ])
        self.client_mock.delete_resource_tags.assert_has_calls([
            mock.call(mci, mock.ANY)
        ])
        six.assertCountEqual(self,
                             self.client_mock.delete_resource_tags.call_args[0][1], ['tag1', 'tag2'])

    @testing.gen_test
    def test_ensure_tags_with_mocked_mci(self):
        mci = mock.MagicMock(name='mci')
        mci.href = None
        self.client_mock.get_resource_tags = mock.MagicMock(name='get')
        self.client_mock.get_resource_tags.side_effect = [
            tornado_value(['tag1', 'tag2'])
        ]

        self.client_mock.add_resource_tags = mock.MagicMock(name='add')
        self.client_mock.add_resource_tags.side_effect = [
            tornado_value(None)
        ]

        self.client_mock.delete_resource_tags = mock.MagicMock(name='delete')
        self.client_mock.delete_resource_tags.side_effect = [
            tornado_value(None)
        ]

        yield self.actor._ensure_tags(mci, 'tag')

        self.client_mock.add_resource_tags.assert_has_calls([
            mock.call(mci, ['tag'])
        ])
        self.assertFalse(self.client_mock.delete_resource_tags.called)


class TestEnsurableRightScaleBaseActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestEnsurableRightScaleBaseActor, self).setUp()
        base.TOKEN = 'unittest'

        # Create the actor
        self.actor = FakeEnsurableRightScaleBaseActor(
            'Copy UnitTestArray to NewUnitArray', {})

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock()
        self.actor._client = self.client_mock

    @testing.gen_test
    def test_init_without_environment_creds(self):
        # Un-set the token and make sure the init fails
        base.TOKEN = None
        with self.assertRaises(exceptions.InvalidCredentials):
            FakeEnsurableRightScaleBaseActor('Unit Test Action', {})
