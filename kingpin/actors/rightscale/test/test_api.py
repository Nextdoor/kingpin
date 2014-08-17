import logging
import mock

from tornado import testing
from rightscale import util
import requests
import rightscale

from kingpin.actors import exceptions
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
        self.assertEquals(True, ret)

    @testing.gen_test
    def test_login_400_error(self):
        # Ensure that if we raise an exception in the call to RS,
        # that the Exception is re-raised through the thread to
        # the caller.
        msg = '400 Client Error: Bad Request'
        error = requests.exceptions.HTTPError(msg)
        self.mock_client.login.side_effect = error
        with self.assertRaises(requests.exceptions.HTTPError):
            ret = yield self.client.login()

        self.mock_client.login.assert_called_once_with()

    @testing.gen_test
    def test_find_server_arrays(self):
        with mock.patch.object(api.rightscale_util, 'find_by_name') as u_mock:
            u_mock.return_value = [1, 2, 3]
            ret = yield self.client.find_server_arrays('test', exact=True)
            u_mock.assert_called_once_with(
                self.mock_client.server_arrays, 'test', exact=True)
            u_mock.reset()

        with mock.patch.object(api.rightscale_util, 'find_by_name') as u_mock:
            u_mock.return_value = [1, 2, 3]
            ret = yield self.client.find_server_arrays('test2', exact=False)
            u_mock.assert_called_once_with(
                self.mock_client.server_arrays, 'test2', exact=False)

    @testing.gen_test
    def test_find_server_arrays_empty_result(self):
        with mock.patch.object(api.rightscale_util, 'find_by_name') as u_mock:
            u_mock.return_value = None
            with self.assertRaises(api.ServerArrayException):
                yield self.client.find_server_arrays('test', exact=True)
            u_mock.assert_called_once_with(
                self.mock_client.server_arrays, 'test', exact=True)
