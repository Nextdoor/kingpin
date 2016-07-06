import logging
import mock

from tornado import testing
import requests

from kingpin.actors import exceptions
from kingpin.actors.rightscale import base
from kingpin.actors.rightscale import server_template
from kingpin.actors.test import helper

log = logging.getLogger(__name__)


class TestServerTemplateBaseActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestServerTemplateBaseActor, self).setUp()
        base.TOKEN = 'unittest'

        # Create the actor
        self.actor = server_template.ServerTemplateBaseActor()

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock(name='client')
        self.actor._client = self.client_mock

        # Create a fake ServerTemplate mock that we'll pretend is returned by
        # RightScale for our tests.
        self.st_mock = mock.MagicMock(name='server_template_a')
        self.st_mock.soul = {
            'actions': [
                {'rel': 'commit'},
                {'rel': 'clone'},
                {'rel': 'resolve'},
                {'rel': 'swap_repository'},
                {'rel': 'detect_changes_in_head'}
            ],
            'description': 'Fake desc',
            'lineage': 'https://fake.com/api/acct/xx/ec3_server_templates/xxx',
            'links': [
                {'href': '/api/server_templates/xxx',
                 'rel': 'self'},
                {'href': '/api/server_templates/xxx/multi_cloud_images',
                 'rel': 'multi_cloud_images'},
                {'href': '/api/multi_cloud_images/123',
                 'rel': 'default_multi_cloud_image'},
                {'href': '/api/server_templates/xxx/inputs',
                 'rel': 'inputs'},
                {'href': '/api/server_templates/xxx/alert_specs',
                 'rel': 'alert_specs'},
                {'href': '/api/server_templates/xxx/runnable_bindings',
                 'rel': 'runnable_bindings'},
                {'href': '/api/server_templates/xxx/cookbook_attachments',
                 'rel': 'cookbook_attachments'}
            ],
            'name': 'Test ServerTemplate',
            'revision': 0
        }

    @testing.gen_test
    def test_get_st(self):
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(self.st_mock)
        ]
        ret = yield self.actor._get_st('testst')
        self.assertEquals(self.st_mock, ret)
        self.client_mock.find_by_name_and_keys.assert_has_calls([
            mock.call(
                collection=self.client_mock._client.server_templates,
                name='testst',
                revision=0)
        ])

    @testing.gen_test
    def test_get_st_returns_empty_list(self):
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value([])
        ]
        ret = yield self.actor._get_st('testst')
        self.assertEquals(None, ret)

    @testing.gen_test
    def test_get_st_returns_too_many_things(self):
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value([1, 2])
        ]
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._get_st('testst')

    @testing.gen_test
    def test_create_st(self):
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(None)
        ]
        self.client_mock.create_resource.side_effect = [
            helper.tornado_value(self.st_mock)
        ]
        ret = yield self.actor._create_st(
            name='testst',
            params=[
                ('test', 'test'),
                ('testa', 'testa')
            ]
        )

        self.assertEquals(self.st_mock, ret)

    @testing.gen_test
    def test_create_st_dry_returns_mock(self):
        self.actor._dry = True
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(None)
        ]
        ret = yield self.actor._create_st(
            name='testst',
            params=[])

        self.assertEquals('<mocked st testst>', ret.soul['name'])

    @testing.gen_test
    def test_create_st_already_exists(self):
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(self.st_mock)
        ]
        ret = yield self.actor._create_st(
            name='testst',
            params=[
                ('test', 'test'),
                ('testa', 'testa')
            ]
        )

        self.assertEquals(self.st_mock, ret)
        self.assertFalse(self.client_mock.create_resource.called)

    @testing.gen_test
    def test_delete_st(self):
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(self.st_mock)
        ]
        self.client_mock.destroy_resource.side_effect = [
            helper.tornado_value(None)
        ]
        ret = yield self.actor._delete_st(name='st')
        self.assertEquals(ret, None)
        self.client_mock.destroy_resource.assert_has_calls([
            mock.call(self.st_mock)
        ])

    @testing.gen_test
    def test_delete_st_already_gone(self):
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(None)
        ]
        ret = yield self.actor._delete_st(name='st')
        self.assertEquals(ret, None)
        self.assertFalse(self.client_mock.destroy_resource.called)

    @testing.gen_test
    def test_update_description(self):
        st = mock.MagicMock(name='st')
        desc = 'test desc'
        self.client_mock.update.side_effect = [
            helper.tornado_value(st)
        ]
        ret = yield self.actor._update_description(
            st=st, description=desc, params={})
        self.assertEquals(ret, st)
        self.client_mock.update.assert_has_calls([
            mock.call(st, {})
        ])


class TestServerTemplateActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestServerTemplateActor, self).setUp()
        base.TOKEN = 'unittest'

        # Create some fake image reference objects
        self._images = [
            {'mci': 'imageA', 'rev': 1, 'is_default': True},
            {'mci': 'imageB', 'is_default': False},
            {'mci': 'imageC'}
        ]

        # Create the actor
        self.actor = server_template.ServerTemplate(
            options={
                'name': 'testst',
                'state': 'present',
                'commit': 'Yeah, committed',
                'tags': ['tag'],
                'description': 'test st desc',
                'images': self._images
            })

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock(name='client')
        self.actor._client = self.client_mock

    def test_get_default_image(self):
        ret = self.actor._verify_one_default_image(self._images)
        self.assertEquals(ret, None)

    def test_verify_one_default_image_too_many(self):
        self._images[1]['is_default'] = True
        with self.assertRaises(exceptions.InvalidOptions):
            self.actor._verify_one_default_image(self._images)

    @testing.gen_test
    def test_ensure_st_is_absent_and_is_none(self):
        self.actor._options['state'] = 'absent'
        self.actor._get_st = helper.mock_tornado(None)
        ret = yield self.actor._ensure_st()
        self.assertEquals(None, ret)

    @testing.gen_test
    def test_ensure_st_is_absent_but_is_present(self):
        existing_st = mock.MagicMock(name='existing_st')
        self.actor._options['state'] = 'absent'
        self.actor._get_st = helper.mock_tornado(existing_st)
        self.actor._delete_st = mock.MagicMock(name='delete_st')
        self.actor._delete_st.side_effect = [helper.tornado_value(None)]

        ret = yield self.actor._ensure_st()
        self.assertEquals(None, ret)
        self.assertTrue(self.actor._delete_st.called)

    @testing.gen_test
    def test_ensure_st_is_present_and_would_create(self):
        new_st = mock.MagicMock(name='new_st')
        self.actor._options['state'] = 'present'
        self.actor._get_st = helper.mock_tornado(None)
        self.actor._create_st = mock.MagicMock(name='create_st')
        self.actor._create_st.side_effect = [helper.tornado_value(new_st)]

        ret = yield self.actor._ensure_st()
        self.assertEquals(new_st, ret)
        self.assertTrue(self.actor._create_st.called)

    @testing.gen_test
    def test_ensure_st_is_present_and_is_present(self):
        existing_st = mock.MagicMock(name='existing_st')
        self.actor._options['state'] = 'present'
        self.actor._get_st = helper.mock_tornado(existing_st)

        ret = yield self.actor._ensure_st()
        self.assertEquals(existing_st, ret)

    @testing.gen_test
    def test_ensure_description_matches(self):
        st = mock.MagicMock(name='st')
        st.soul = {
            'description': 'test st desc'
        }
        self.actor._update_description = mock.MagicMock(name='update_desc')
        self.actor._update_description.side_effect = [
            helper.tornado_value(None)
        ]
        yield self.actor._ensure_description(st)
        self.assertFalse(self.actor._update_description.called)

    @testing.gen_test
    def test_ensure_description_not_matches(self):
        st = mock.MagicMock(name='st')
        st.soul = {
            'description': 'test st desc different'
        }
        self.actor._update_description = mock.MagicMock(name='update_desc')
        self.actor._update_description.side_effect = [
            helper.tornado_value(None)
        ]
        yield self.actor._ensure_description(st)
        self.assertTrue(self.actor._update_description.called)

    @testing.gen_test
    def test_ensure_st_mcis(self):
        # For simplicity (and to ensure we're passing the right data into the
        # create/delete/update st_mci setting methods), we mock out the final
        # API call.. not the internal actor methods.
        self.client_mock.create_resource.side_effect = [
            helper.tornado_value(None)
        ]
        self.client_mock.update.side_effect = [
            helper.tornado_value(None)
        ]
        self.client_mock.destroy_resource.side_effect = [
            helper.tornado_value(None)
        ]

        # This is the final, post HREF-gathering, set of configuration tuples
        # that we will use to configure the ServerTemplate with MCI refs.
        st_image_a_href_tuples = [
            [('server_template_multi_cloud_image[multi_cloud_image_href]',
              '/api/clouds/A/images/abc'),
             ('server_template_multi_cloud_image[server_template_href]',
              '/api/server_templates/abc')], False]
        st_image_b_href_tuples = [
            [('server_template_multi_cloud_image[multi_cloud_image_href]',
              '/api/clouds/B/images/abc'),
             ('server_template_multi_cloud_image[server_template_href]',
              '/api/server_templates/abc')], False]
        st_image_c_href_tuples = [
            [('server_template_multi_cloud_image[multi_cloud_image_href]',
              '/api/clouds/C/images/abc'),
             ('server_template_multi_cloud_image[server_template_href]',
              '/api/server_templates/abc')], True]

        # Mock out the actual ServerTemplate object we're going to operate on.
        # Pretend that a 4th MCI (MCI-D) is associated with the template.
        st = mock.MagicMock(name='st')
        st_mci_d = mock.MagicMock(name='st_mci_d')
        st_mci_d.links = {
            'multi_cloud_image': '/api/clouds/D/images/abc'
        }
        self.client_mock.find_by_name_and_keys.side_effect = [
            # The first call of _client.show should return the list of settings
            # objects we've created above.
            helper.tornado_value(st_mci_d)
        ]

        # Mock out _get_st_mci_refs and have it return the clouda/cloudb
        # href populated setting lists.
        self.actor._get_st_mci_refs = mock.MagicMock(name='get_st_mci_refs')
        self.actor._get_st_mci_refs.side_effect = [
            helper.tornado_value(st_image_a_href_tuples),
            helper.tornado_value(st_image_b_href_tuples),
            helper.tornado_value(st_image_c_href_tuples),
        ]

        # Go for it
        yield self.actor._ensure_st_mcis(st)

        # Finally, make sure that the right things were deleted/updated/etc
        self.client_mock.create_resource.assert_has_calls([
            mock.call(
                self.client_mock._client.server_template_multi_cloud_images,
                st_image_a_href_tuples[0]),
            mock.call(
                self.client_mock._client.server_template_multi_cloud_images,
                st_image_b_href_tuples[0]),
            mock.call(
                self.client_mock._client.server_template_multi_cloud_images,
                st_image_c_href_tuples[0]),
        ])

        self.client_mock.destroy_resource.assert_has_calls([
            mock.call(st_mci_d)
        ])

    @testing.gen_test
    def test_ensure_st_mci_skips_on_mock(self):
        st = mock.MagicMock(name='st')
        st.href = None
        yield self.actor._ensure_st_mcis(st)
        self.assertFalse(self.client_mock.find_by_name_and_keys.called)

    @testing.gen_test
    def test_ensure_st_mci_default_already_matches(self):
        st = mock.MagicMock(name='st')
        st.links = {
            'self': '/api/server_templates/abc',
            'default_multi_cloud_image': '/api/clouds/A/images/abc',
        }
        yield self.actor._ensure_st_mci_default(
            st, '/api/clouds/A/images/abc')
        self.assertFalse(self.client_mock.find_by_name_and_keys.called)

    @testing.gen_test
    def test_ensure_st_mci_default_has_no_MCIs(self):
        st = mock.MagicMock(name='st')
        st.links = {'self': '/api/server_templates/abc'}

        yield self.actor._ensure_st_mci_default(
            st, '/api/clouds/C/images/abc')

    @testing.gen_test
    def test_ensure_st_mci_default_bails_on_dry(self):
        st = mock.MagicMock(name='st')
        st.links = {
            'self': '/api/server_templates/abc',
            'default_multi_cloud_image': '/api/clouds/A/images/abc',
        }

        self.actor._dry = True
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(['junk'])
        ]
        yield self.actor._ensure_st_mci_default(
            st, '/api/clouds/B/images/abc')

    @testing.gen_test
    def test_ensure_st_mci_default(self):
        st = mock.MagicMock(name='st')
        st.links = {
            'self': '/api/server_templates/abc',
            'default_multi_cloud_image': '/api/clouds/A/images/abc',
        }

        st_mci_a = mock.MagicMock(name='st_mci_a')
        st_mci_a.links = {
            'self': '/api/server_template_multi_cloud_image/A',
            'multi_cloud_image': '/api/clouds/A/images/abc'
        }
        st_mci_b = mock.MagicMock(name='st_mci_b')
        st_mci_b.links = {
            'self': '/api/server_template_multi_cloud_image/B',
            'multi_cloud_image': '/api/clouds/B/images/abc'
        }

        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value([st_mci_a, st_mci_b])
        ]

        self.client_mock.make_generic_request.side_effect = [
            helper.tornado_value(None)]

        yield self.actor._ensure_st_mci_default(
            st, '/api/clouds/B/images/abc')

        self.client_mock.make_generic_request.assert_has_calls(
            mock.call(
                '/api/server_template_multi_cloud_image/B/make_default',
                post=[])
        )

    @testing.gen_test
    def test_ensure_st_mci_default_invalid_api_data(self):
        st = mock.MagicMock(name='st')
        st.links = {
            'self': '/api/server_templates/abc',
            'default_multi_cloud_image': '/api/clouds/A/images/abc',
        }

        st_mci_a = mock.MagicMock(name='st_mci_a')
        st_mci_a.links = {
            'self': '/api/server_template_multi_cloud_image/A',
            'multi_cloud_image': '/api/clouds/A/images/abc'
        }
        st_mci_b = mock.MagicMock(name='st_mci_b')
        st_mci_b.links = {
            'self': '/api/server_template_multi_cloud_image/B',
            'multi_cloud_image': 'JUNK DATA'
        }

        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value([st_mci_a, st_mci_b])
        ]

        self.client_mock.make_generic_request.side_effect = [
            helper.tornado_value(None)]

        with self.assertRaises(exceptions.InvalidOptions):
            yield self.actor._ensure_st_mci_default(
                st, '/api/clouds/B/images/abc')

    @testing.gen_test
    def test_get_st_mci_refs_wrong_mci(self):
        img = {'mci': '/mci'}
        st = mock.MagicMock(name='st')

        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(None)]

        with self.assertRaises(exceptions.InvalidOptions):
            yield self.actor._get_st_mci_refs(img, st)

    @testing.gen_test
    def test_get_st_mci_refs(self):
        img = {'mci': '/mci'}
        st = mock.MagicMock(name='st')
        st.href = '/href/st'

        mocked_mci = mock.MagicMock(name='mci')
        mocked_mci.href = '/href'

        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(mocked_mci)]

        ret = yield self.actor._get_st_mci_refs(img, st)

        expected_ret = (
            [('server_template_multi_cloud_image[multi_cloud_image_href]',
              '/href'),
             ('server_template_multi_cloud_image[server_template_href]',
              '/href/st')], False)

        self.assertEquals(expected_ret, ret)

    @testing.gen_test
    def test_delete_st_mci_reference_handles_error(self):
            obj = mock.MagicMock(name='mci_ref_obj')

            mocked_resp = mock.MagicMock(name='response')
            mocked_resp.text = 'Default ServerTemplateMultiCloudImages ...'
            exc = requests.exceptions.HTTPError(
                'error', response=mocked_resp)
            self.client_mock.destroy_resource.side_effect = exc

            with self.assertRaises(exceptions.InvalidOptions):
                yield self.actor._delete_st_mci_reference(
                    mci_ref_obj=obj)

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
        self.actor._ensure_st = helper.mock_tornado(None)
        self.actor._ensure_description = helper.mock_tornado(None)
        self.actor._ensure_st_mcis = helper.mock_tornado(None)
        self.actor._ensure_tags = helper.mock_tornado(None)
        self.actor._commit = helper.mock_tornado(None)
        self.actor.changed = True
        yield self.actor._execute()

    @testing.gen_test
    def test_execute_absent(self):
        self.actor._options['state'] = 'absent'
        self.actor._ensure_st = helper.mock_tornado(None)
        yield self.actor._execute()
