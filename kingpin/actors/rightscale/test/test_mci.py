import logging
import mock

import six

from tornado import testing

from kingpin.actors import exceptions
from kingpin.actors.rightscale import base
from kingpin.actors.rightscale import mci
from kingpin.actors.test import helper

log = logging.getLogger(__name__)


class TestMCIBaseActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestMCIBaseActor, self).setUp()
        base.TOKEN = 'unittest'

        # Create some fake image reference objects
        self._images = [
            {'cloud': 'cloudA', 'image': 'ami-A',
             'instance_type': 'm1.small', 'user_data': 'userdataA'},
            {'cloud': 'cloudB', 'image': 'ami-B',
             'instance_type': 'm1.small'}
        ]

        # Create the actor
        self.actor = mci.MCIBaseActor()

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock(name='client')
        self.actor._client = self.client_mock

        self.clouda_image_mock = mock.MagicMock(name='imageA')
        self.clouda_image_mock.href = '/api/clouds/A/images/abc'
        self.clouda_instance_mock = mock.MagicMock(name='instance_mockA')
        self.clouda_instance_mock.href = '/api/clouds/A/instance_types/abc'
        self.clouda_mock = mock.MagicMock(name='cloudA')
        self.clouda_mock.href = '/api/clouds/A'
        self.clouda_mock.soul = 'CloudA'
        self.clouda_mock.images = self.clouda_image_mock

        self.cloudb_image_mock = mock.MagicMock(name='imageB')
        self.cloudb_image_mock.href = '/api/clouds/B/images/abc'
        self.cloudb_instance_mock = mock.MagicMock(name='instance_mockB')
        self.cloudb_instance_mock.href = '/api/clouds/B/instance_types/abc'
        self.cloudb_mock = mock.MagicMock(name='cloudB')
        self.cloudb_mock.href = '/api/clouds/B'
        self.cloudb_mock.soul = 'CloudB'
        self.cloudb_mock.images = self.cloudb_image_mock

        # What the final converted clouda/cloudb mocks should look like when
        # all of their names have been converted into HREFs and the data has
        # been turned into a RightScale formatted parameters list.
        self.clouda_href_tuples = [
            ('multi_cloud_image_setting[image_href]',
             '/api/clouds/A/images/abc'),
            ('multi_cloud_image_setting[user_data]', 'userdataA'),
            ('multi_cloud_image_setting[instance_type_href]',
             '/api/clouds/A/instance_types/abc'),
            ('multi_cloud_image_setting[cloud_href]', '/api/clouds/A')]
        self.cloudb_href_tuples = [
            ('multi_cloud_image_setting[image_href]',
             '/api/clouds/B/images/abc'),
            ('multi_cloud_image_setting[instance_type_href]',
             '/api/clouds/B/instance_types/abc'),
            ('multi_cloud_image_setting[cloud_href]', '/api/clouds/B')]

    @testing.gen_test
    def test_get_mci_setting_def(self):
        # First, mock out a correct set of responses where we succeed in
        # finding the cloud, image and instance HREFs.
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(self.clouda_mock),
            helper.tornado_value(self.clouda_image_mock),
            helper.tornado_value(self.clouda_instance_mock),
        ]
        ret = yield self.actor._get_mci_setting_def(self._images[0])
        six.assertCountEqual(self, ret, self.clouda_href_tuples)

    @testing.gen_test
    def test_get_mci_setting_def_no_user_data(self):
        # First, mock out a correct set of responses where we succeed in
        # finding the cloud, image and instance HREFs.
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(self.cloudb_mock),
            helper.tornado_value(self.cloudb_image_mock),
            helper.tornado_value(self.cloudb_instance_mock),
        ]
        ret = yield self.actor._get_mci_setting_def(self._images[1])
        six.assertCountEqual(self, ret, self.cloudb_href_tuples)

    @testing.gen_test
    def test_get_mci_setting_def_exc_in_cloud_call(self):
        # First, mock out a correct set of responses where we succeed in
        # finding the cloud, image and instance HREFs.
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(None)
        ]
        with self.assertRaises(exceptions.InvalidOptions):
            yield self.actor._get_mci_setting_def(self._images[0])

    @testing.gen_test
    def test_get_mci_setting_def_exc_in_image_call(self):
        # First, mock out a correct set of responses where we succeed in
        # finding the cloud, image and instance HREFs.
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(self.clouda_mock),
            helper.tornado_value(None),
            helper.tornado_value(self.clouda_instance_mock),
        ]
        with self.assertRaises(exceptions.InvalidOptions):
            yield self.actor._get_mci_setting_def(self._images[0])

    @testing.gen_test
    def test_get_mci_setting_def_exc_in_instance_call(self):
        # First, mock out a correct set of responses where we succeed in
        # finding the cloud, image and instance HREFs.
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(self.clouda_mock),
            helper.tornado_value(self.clouda_image_mock),
            helper.tornado_value(None)
        ]
        with self.assertRaises(exceptions.InvalidOptions):
            yield self.actor._get_mci_setting_def(self._images[0])

    @testing.gen_test
    def test_get_mci(self):
        mci = mock.MagicMock(name='mci')
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(mci)
        ]
        ret = yield self.actor._get_mci('testmci')
        self.assertEquals(mci, ret)
        self.client_mock.find_by_name_and_keys.assert_has_calls([
            mock.call(
                collection=self.client_mock._client.multi_cloud_images,
                name='testmci',
                revision=0)
        ])

    @testing.gen_test
    def test_get_mci_returns_empty_list(self):
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value([])
        ]
        ret = yield self.actor._get_mci('testmci')
        self.assertEquals(None, ret)

    @testing.gen_test
    def test_get_mci_returns_too_many_things(self):
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value([1, 2])
        ]
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._get_mci('testmci')

    @testing.gen_test
    def test_create_mci(self):
        mci = mock.MagicMock(name='mci')
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(None)
        ]
        self.client_mock.create_resource.side_effect = [
            helper.tornado_value(mci)
        ]
        ret = yield self.actor._create_mci(
            name='testmci',
            params=[
                ('test', 'test'),
                ('testa', 'testa')
            ]
        )

        self.assertEquals(mci, ret)

    @testing.gen_test
    def test_create_mci_dry_returns_mock(self):
        self.actor._dry = True
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(None)
        ]
        ret = yield self.actor._create_mci(
            name='testmci',
            params=[])

        self.assertEquals('<mocked MCI testmci>', ret.soul['name'])

    @testing.gen_test
    def test_create_mci_already_exists(self):
        mci = mock.MagicMock(name='mci')
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(mci)
        ]
        ret = yield self.actor._create_mci(
            name='testmci',
            params=[
                ('test', 'test'),
                ('testa', 'testa')
            ]
        )

        self.assertEquals(mci, ret)
        self.assertFalse(self.client_mock.create_resource.called)

    @testing.gen_test
    def test_delete_mci(self):
        mci = mock.MagicMock(name='mci')
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(mci)
        ]
        self.client_mock.destroy_resource.side_effect = [
            helper.tornado_value(None)
        ]
        ret = yield self.actor._delete_mci(name='mci')
        self.assertEquals(ret, None)
        self.client_mock.destroy_resource.assert_has_calls([
            mock.call(mci)
        ])

    @testing.gen_test
    def test_delete_mci_already_gone(self):
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(None)
        ]
        ret = yield self.actor._delete_mci(name='mci')
        self.assertEquals(ret, None)
        self.assertFalse(self.client_mock.destroy_resource.called)

    @testing.gen_test
    def test_create_mci_setting(self):
        mci = mock.MagicMock(name='mci')
        self.client_mock.create_resource.side_effect = [
            helper.tornado_value(None)
        ]
        yield self.actor._create_mci_setting(
            cloud='cloudA',
            mci=mci,
            params=self.clouda_href_tuples)
        self.client_mock.create_resource.assert_has_calls([
            mock.call(mci.settings, self.clouda_href_tuples)
        ])

    @testing.gen_test
    def test_update_mci_setting(self):
        mci_setting = mock.MagicMock(name='mci_settings_obj')
        mci_setting.links = {'cloud': 'testcloud'}
        self.client_mock.update.side_effect = [
            helper.tornado_value(None)
        ]
        yield self.actor._update_mci_setting(
            mci_setting=mci_setting,
            params=self.clouda_href_tuples)
        self.client_mock.update.assert_has_calls([
            mock.call(mci_setting, self.clouda_href_tuples)
        ])

    @testing.gen_test
    def test_delete_mci_setting(self):
        mci_setting = mock.MagicMock(name='mci_settings_obj')
        mci_setting.links = {'cloud': 'testcloud'}
        self.client_mock.destroy_resource.side_effect = [
            helper.tornado_value(None)
        ]
        yield self.actor._delete_mci_setting(
            mci_setting=mci_setting)
        self.client_mock.destroy_resource.assert_has_calls([
            mock.call(mci_setting)
        ])

    @testing.gen_test
    def test_update_description(self):
        mci = mock.MagicMock(name='mci')
        desc = 'test desc'
        self.client_mock.update.side_effect = [
            helper.tornado_value(mci)
        ]
        ret = yield self.actor._update_description(
            mci=mci, description=desc, params={})
        self.assertEquals(ret, mci)
        self.client_mock.update.assert_has_calls([
            mock.call(mci, {})
        ])

    def test_diff_setting(self):
        mci_setting = mock.MagicMock(name='mci_settings_obj')
        mci_setting.links = {
            'cloud': '/api/clouds/A',
            'image': '/api/clouds/A/images/abc',
            'instance_type': '/api/clouds/A/instance_types/abc'
        }
        ret = self.actor._diff_setting(mci_setting, self.clouda_href_tuples)
        self.assertEquals(False, ret)

    def test_diff_setting_are_different(self):
        mci_setting = mock.MagicMock(name='mci_settings_obj')
        mci_setting.links = {
            'cloud': '/api/clouds/A',
            'image': '/api/clouds/A/images/123',
            'instance_type': '/api/clouds/A/instance_types/123'
        }
        ret = self.actor._diff_setting(mci_setting, self.clouda_href_tuples)
        self.assertEquals(True, ret)


class TestMCIActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestMCIActor, self).setUp()
        base.TOKEN = 'unittest'

        # Create some fake image reference objects
        self._images = [
            {'cloud': 'cloudA', 'image': 'ami-A',
             'instance_type': 'm1.small', 'user_data': 'userdataA'},
            {'cloud': 'cloudB', 'image': 'ami-B',
             'instance_type': 'm1.small'}
        ]

        # Create the actor
        self.actor = mci.MCI(
            options={
                'name': 'testmci',
                'state': 'present',
                'commit': 'Yeah, committed',
                'tags': ['tag'],
                'description': 'test mci desc',
                'images': self._images
            })

        # What the final converted clouda/cloudb mocks should look like when
        # all of their names have been converted into HREFs and the data has
        # been turned into a RightScale formatted parameters list.
        self.clouda_href_tuples = [
            ('multi_cloud_image_setting[image_href]',
             '/api/clouds/A/images/abc'),
            ('multi_cloud_image_setting[user_data]', 'userdataA'),
            ('multi_cloud_image_setting[instance_type_href]',
             '/api/clouds/A/instance_types/abc'),
            ('multi_cloud_image_setting[cloud_href]', '/api/clouds/A')]
        self.cloudb_href_tuples = [
            ('multi_cloud_image_setting[image_href]',
             '/api/clouds/B/images/abc'),
            ('multi_cloud_image_setting[instance_type_href]',
             '/api/clouds/B/instance_types/abc'),
            ('multi_cloud_image_setting[cloud_href]', '/api/clouds/B')]

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock(name='client')
        self.actor._client = self.client_mock

    @testing.gen_test
    def test_ensure_mci_is_absent_and_is_none(self):
        self.actor._options['state'] = 'absent'
        self.actor._get_mci = helper.mock_tornado(None)
        ret = yield self.actor._ensure_mci()
        self.assertEquals(None, ret)

    @testing.gen_test
    def test_ensure_mci_is_absent_but_is_present(self):
        existing_mci = mock.MagicMock(name='existing_mci')
        self.actor._options['state'] = 'absent'
        self.actor._get_mci = helper.mock_tornado(existing_mci)
        self.actor._delete_mci = mock.MagicMock(name='delete_mci')
        self.actor._delete_mci.side_effect = [helper.tornado_value(None)]

        ret = yield self.actor._ensure_mci()
        self.assertEquals(None, ret)
        self.assertTrue(self.actor._delete_mci.called)

    @testing.gen_test
    def test_ensure_mci_is_present_and_would_create(self):
        new_mci = mock.MagicMock(name='new_mci')
        self.actor._options['state'] = 'present'
        self.actor._get_mci = helper.mock_tornado(None)
        self.actor._create_mci = mock.MagicMock(name='create_mci')
        self.actor._create_mci.side_effect = [helper.tornado_value(new_mci)]

        ret = yield self.actor._ensure_mci()
        self.assertEquals(new_mci, ret)
        self.assertTrue(self.actor._create_mci.called)

    @testing.gen_test
    def test_ensure_mci_is_present_and_is_present(self):
        existing_mci = mock.MagicMock(name='existing_mci')
        self.actor._options['state'] = 'present'
        self.actor._get_mci = helper.mock_tornado(existing_mci)

        ret = yield self.actor._ensure_mci()
        self.assertEquals(existing_mci, ret)

    @testing.gen_test
    def test_ensure_description_matches(self):
        mci = mock.MagicMock(name='mci')
        mci.soul = {
            'description': 'test mci desc'
        }
        self.actor._update_description = mock.MagicMock(name='update_desc')
        self.actor._update_description.side_effect = [
            helper.tornado_value(None)
        ]
        yield self.actor._ensure_description(mci)
        self.assertFalse(self.actor._update_description.called)

    @testing.gen_test
    def test_ensure_description_not_matches(self):
        mci = mock.MagicMock(name='mci')
        mci.soul = {
            'description': 'test mci desc different'
        }
        self.actor._update_description = mock.MagicMock(name='update_desc')
        self.actor._update_description.side_effect = [
            helper.tornado_value(None)
        ]
        yield self.actor._ensure_description(mci)
        self.assertTrue(self.actor._update_description.called)

    @testing.gen_test
    def test_ensure_settings(self):
        mci = mock.MagicMock(name='mci')
        mci.soul = {
            'name': 'testmci',
            'description': 'test mci desc different'
        }

        # For simplicity (and to ensure we're passing the right data into the
        # create/delete/update mci setting methods), we mock out the final API
        # call.. not the internal actor methods.
        self.client_mock.create_resource.side_effect = [
            helper.tornado_value(None)
        ]
        self.client_mock.update.side_effect = [
            helper.tornado_value(None),
            helper.tornado_value(None),
        ]
        self.client_mock.destroy_resource.side_effect = [
            helper.tornado_value(None),
            helper.tornado_value(None),
            helper.tornado_value(None),
            helper.tornado_value(None),
        ]

        # mci_setting_a looks like the desired clouda settings, but has the
        # wrong image id, so it will trigger an update_mci_setting() call
        mci_setting_a = mock.MagicMock(name='mci_setting_a')
        mci_setting_a.links = {
            'cloud': '/api/clouds/A',
            'image': '/api/clouds/A/images/bad_image_id',
            'instance_type': '/api/clouds/A/instance_types/abc'}

        # mci_setting_b is deliberately missing, which will trigger a
        # create_mci_setting() call

        # mci_setting_c doesn't exist at all  in our desired settings, so it
        # should trigger a delete_mci_setting() call
        mci_setting_c = mock.MagicMock(name='mci_setting_c')
        mci_setting_c.links = {
            'cloud': '/api/clouds/C',
            'image': '/api/clouds/C/images/abc',
            'instance_type': '/api/clouds/C/instance_types/abc'}

        self.client_mock.show.side_effect = [
            # The first call of _client.show should return the list of settings
            # objects we've created above.
            helper.tornado_value([
                mci_setting_a,
                mci_setting_c,
            ])
        ]

        # Mock out _get_mci_setting_def and have it return the clouda/cloudb
        # href populated setting lists.
        self.actor._get_mci_setting_def = mock.MagicMock(name='get_mci_set')
        self.actor._get_mci_setting_def.side_effect = [
            helper.tornado_value(self.clouda_href_tuples),
            helper.tornado_value(self.cloudb_href_tuples),
            helper.tornado_value(self.cloudb_href_tuples),
        ]

        # Go for it
        yield self.actor._ensure_settings(mci)

        # Finally, make sure that the right things were deleted/updated/etc
        self.client_mock.create_resource.assert_has_calls([
            mock.call(mci.settings, self.cloudb_href_tuples),
        ])
        self.client_mock.update.assert_has_calls([
            mock.call(mci_setting_a, self.clouda_href_tuples),
        ])
        self.client_mock.destroy_resource.assert_has_calls([
            mock.call(mci_setting_c)
        ])

    @testing.gen_test
    def test_commit(self):
        mci = mock.MagicMock(name='mci')
        fake_mci_setting = mock.MagicMock(name='mci_setting')
        fake_mci_setting.soul = {
            'revision': 2
        }
        self.client_mock.commit_resource.side_effect = [
            helper.tornado_value(fake_mci_setting)
        ]
        self.actor.log = mock.MagicMock(name='log')
        yield self.actor._commit(mci, 'message')
        self.actor.log.assert_has_calls([
            mock.call.info('Committing a new revision'),
            mock.call.info('Committed revision 2')
        ])

    @testing.gen_test
    def test_execute_present(self):
        self.actor._ensure_mci = helper.mock_tornado(None)
        self.actor._ensure_description = helper.mock_tornado(None)
        self.actor._ensure_settings = helper.mock_tornado(None)
        self.actor._ensure_tags = helper.mock_tornado(None)
        self.actor._commit = helper.mock_tornado(None)
        self.actor.changed = True
        yield self.actor._execute()

    @testing.gen_test
    def test_execute_absent(self):
        self.actor._options['state'] = 'absent'
        self.actor._ensure_mci = helper.mock_tornado(None)
        yield self.actor._execute()
