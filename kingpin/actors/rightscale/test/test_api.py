import logging
import mock

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
            u_mock.reset()

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
    def test_clone_server_array(self):
        # First, create the rightscale.server_array api mock
        sa_rsr_mock = mock.MagicMock()
        self.mock_client.server_arrays = sa_rsr_mock

        # Next, create the returned server array resource mock
        sa_mock = mock.MagicMock()
        sa_mock.soul = {'name': 'Mocked ServerArray'}
        sa_rsr_mock.clone.return_value = sa_mock

        # Clone the array
        ret = yield self.client.clone_server_array('source_array_id')
        self.assertEquals(ret, sa_mock)

    @testing.gen_test
    def test_update_server_array(self):
        # Create a mock and the params we're going to pass in
        sa_mock = mock.MagicMock()
        sa_mock.self.update.return_value = True
        params = {'server_array[name]': 'new_name'}

        ret = yield self.client.update_server_array(sa_mock, params)
        sa_mock.self.update.assert_called_once_with(params=params)

        self.assertEquals(ret, None)
