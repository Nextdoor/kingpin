import logging
import mock

from tornado import testing

from kingpin.actors import exceptions
from kingpin.actors.rightscale import base
from kingpin.actors.rightscale import mci
from kingpin.actors.test import helper

log = logging.getLogger(__name__)


class TestCreateActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestCreateActor, self).setUp()
        base.TOKEN = 'unittest'

        # Create some fake image reference objects
        self._images = [
            {'cloud': 'cloudA', 'image': 'ami-A',
             'instance_type': 'm1.small', 'user_data': 'userdataA'},
            {'cloud': 'cloudB', 'image': 'ami-B',
             'instance_type': 'm1.small', 'user_data': 'userdataB'}
        ]

        # Create the actor
        self.actor = mci.Create('Test',
                                {'name': 'unit-test',
                                 'description': 'unit test',
                                 'images': self._images})

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock()
        self.actor._client = self.client_mock

    @testing.gen_test
    def test_bad_image_options(self):
        bad = [
            {'bad_option': 'cloudA', 'image': 'ami-A',
             'instance_type': 'm1.small', 'user_data': 'userdataA'}]
        missing = [
            {'image': 'ami-A', 'user_data': 'userdataA'}]

        with self.assertRaises(exceptions.InvalidOptions):
            mci.Create('Test', {'name': 'test', 'images': bad})

        with self.assertRaises(exceptions.InvalidOptions):
            mci.Create('Test', {'name': 'test', 'images': missing})

    @testing.gen_test
    def test_get_image_def(self):
        description = self._images[0]

        # Create a few mocked objects that will be returned to help the method
        # complete as if it made an API call.
        cloud_mock = mock.MagicMock(name='cloudA')
        cloud_mock.href = '/cloud_href'
        image_mock = mock.MagicMock(name='ami-A')
        image_mock.href = '/image_href'
        instance_mock = mock.MagicMock(name='m1.small')
        instance_mock.href = '/instance_href'

        # What we expect this to look like when its all done
        expected_result = [
            ('multi_cloud_image_setting[cloud_href]', '/cloud_href'),
            ('multi_cloud_image_setting[image_href]', '/image_href'),
            ('multi_cloud_image_setting[instance_type_href]',
                '/instance_href'),
            ('multi_cloud_image_setting[user_data]', 'userdataA'),
        ]

        # Fake the find_by_name_and_keys method out so that the first time its
        # called, it returns a mocked cloud object. The second time, it reutnrs
        # a mocked image object. The third time it returns a mocked instance
        # object.
        actor = self.actor
        with mock.patch.object(actor._client, 'find_by_name_and_keys') as cr:
            cr.side_effect = [
                helper.tornado_value(cloud_mock),
                helper.tornado_value(image_mock),
                helper.tornado_value(instance_mock)
            ]

            ret = yield actor._get_image_def(description)

            self.assertItemsEqual(ret, expected_result)

    @testing.gen_test
    def test_get_image_def_unable_to_find_hrefs(self):
        description = self._images[0]

        # Create a few mocked objects that will be returned to help the method
        # complete as if it made an API call.
        cloud_mock = mock.MagicMock(name='cloudA')
        cloud_mock.href = '/cloud_href'
        image_mock = mock.MagicMock(name='ami-A')
        image_mock.href = '/image_href'
        instance_mock = mock.MagicMock(name='m1.small')
        instance_mock.href = '/instance_href'

        # First test, nothing is returned on the cloud search
        actor = self.actor
        with mock.patch.object(actor._client, 'find_by_name_and_keys') as cr:
            cr.return_value = helper.tornado_value(None)
            with self.assertRaises(exceptions.InvalidOptions):
                yield actor._get_image_def(description)

        # Second test, a cloud is returned but no image is returned
        with mock.patch.object(actor._client, 'find_by_name_and_keys') as cr:
            cr.side_effect = [
                helper.tornado_value(mock.MagicMock(name='cloud')),
                helper.tornado_value(None),
                helper.tornado_value(None),
            ]
            with self.assertRaises(exceptions.InvalidOptions):
                yield actor._get_image_def(description)

        # Final test, a cloud and image are returned but no instance type
        with mock.patch.object(actor._client, 'find_by_name_and_keys') as cr:
            cr.side_effect = [
                helper.tornado_value(mock.MagicMock(name='cloud')),
                helper.tornado_value(mock.MagicMock(name='image')),
                helper.tornado_value(None),
            ]
            with self.assertRaises(exceptions.InvalidOptions):
                yield actor._get_image_def(description)

    @testing.gen_test
    def test_exec_mci_exists(self):
        self.actor._client.find_by_name_and_keys = helper.mock_tornado(1)
        with self.assertRaises(exceptions.InvalidOptions):
            yield self.actor._execute()

    @testing.gen_test
    def test_exec_dry(self):
        self.actor._dry = True
        self.actor._client.find_by_name_and_keys = helper.mock_tornado(None)
        self.actor._get_image_def = helper.mock_tornado('fake_mci_params')

        with mock.patch.object(self.actor._client, 'create_resource') as cr:
            cr.return_value = 1
            yield self.actor._execute()
            self.assertEquals(
                self.actor._client.create_resource._mock_call_count, 0)

    @testing.gen_test
    def test_exec(self):
        self.actor._find_deployment = helper.mock_tornado(None)
        self.actor._client.find_by_name_and_keys = helper.mock_tornado(None)
        self.actor._get_image_def = helper.mock_tornado('fake_mci_params')
        mci_mock = mock.MagicMock(name='fake-created-mci')

        with mock.patch.object(self.actor._client, 'create_resource') as cr:
            cr.side_effect = helper.mock_tornado(mci_mock)
            yield self.actor._execute()
            self.assertEquals(cr._mock_call_count, 3)


class TestMCIDestroyActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestMCIDestroyActor, self).setUp()
        base.TOKEN = 'unittest'

        # Create the actor
        self.actor = mci.Destroy('Test', {'name': 'unit-test'})

        # Patch the actor so that we use the client mock
        self.actor._client = mock.Mock()

    @testing.gen_test
    def test_exec_missing(self):
        self.actor._client.find_by_name_and_keys = helper.mock_tornado(None)
        with self.assertRaises(exceptions.InvalidOptions):
            yield self.actor._execute()

    @testing.gen_test
    def test_exec_dry(self):
        mci = mock.MagicMock(name='unit-test-mci')
        self.actor._client.find_by_name_and_keys = helper.mock_tornado(mci)
        self.actor._client.show = helper.mock_tornado(mock.MagicMock())
        self.actor._dry = True

        with mock.patch.object(self.actor._client, 'destroy_resource') as dr:
            dr.return_value = 1
            yield self.actor._execute()
            self.assertEquals(
                self.actor._client.destroy_resource._mock_call_count, 0)

    @testing.gen_test
    def test_exec(self):
        mci = mock.MagicMock(name='unit-test-mci')
        self.actor._client.find_by_name_and_keys = helper.mock_tornado(mci)
        self.actor._client.show = helper.mock_tornado(mock.MagicMock())

        with mock.patch.object(self.actor._client, 'destroy_resource') as dr:
            dr.return_value = helper.tornado_value(1)
            yield self.actor._execute()
            self.assertEquals(
                self.actor._client.destroy_resource._mock_call_count, 1)
