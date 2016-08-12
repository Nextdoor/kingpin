import logging
import mock

from tornado import testing
import requests

from kingpin.actors import exceptions
from kingpin.actors.rightscale import base
from kingpin.actors.rightscale import server_template
from kingpin.actors.test import helper

log = logging.getLogger(__name__)


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

        # Pre-populate our cached Server Template information for the purposes
        # of most of the tests. We start with some basic defaults, and then our
        # tests below will try changing these.
        self.actor.st = mock.MagicMock(name='server_template_a')
        self.actor.st.href = '/api/server_templates/test'
        self.actor.st.links = {
            'self': '/api/server_templates/xxx',
            'default_multi_cloud_image': '/api/multi_cloud_images/imageA',
            'inputs': '/api/server_templates/xxx/inputs',
            'alert_specs': '/api/server_templates/xxx/alert_specs',
            'runnable_bindings': '/api/server_templates/xxx/runnable_bindings',
            'cookbook_attachments':
                '/api/server_templates/xxx/cookbook_attachments'
        }
        self.actor.st.soul = {
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
                {'href': '/api/multi_cloud_images/imageA',
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
        self.actor.tags = ['tag1', 'tag2']
        self.actor.desired_images = {
            '/api/multi_cloud_images/imageA': {
                'default': True
            },
            '/api/multi_cloud_images/imageB': {
                'default': False
            },
            '/api/multi_cloud_images/imageC': {
                'default': False
            }
        }

        self.actor.images = {
            '/api/multi_cloud_images/imageD': {
                'default': True,
                'map_href': '/api/st_mci/imageD',
                'map_obj': mock.MagicMock(name='imaged_map')
            }
        }

    @testing.gen_test
    def test_precache(self):
        # Generate new ST and Tag mocks
        new_st = mock.MagicMock(name='new_st')
        new_tags = ['tag3']

        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(new_st)
        ]

        self.actor._get_resource_tags = mock.MagicMock()
        self.actor._get_resource_tags.side_effect = [
            helper.tornado_value(new_tags)
        ]

        yield self.actor._precache()
        self.assertEquals(self.actor.st, new_st)
        self.assertEquals(self.actor.desired_images, {})
        self.assertEquals(self.actor.tags, new_tags)

    @testing.gen_test
    def test_precache_absent_template(self):
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value([])
        ]

        yield self.actor._precache()
        self.assertEquals(self.actor.st.soul['description'], None)
        self.assertEquals(self.actor.st.soul['name'], None)
        self.assertEquals(self.actor.tags, [])

    @testing.gen_test
    def test_get_mci_href(self):
        self.actor.desired_images = {}

        mci_mock = mock.MagicMock(name='returned_mci')
        mci_mock.href = '/api/multi_cloud_images/test'

        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(mci_mock)
        ]
        yield self.actor._get_mci_href({'mci': 'test mci'})
        self.assertEquals(
            self.actor.desired_images,
            {'/api/multi_cloud_images/test': {'default': False}}
        )

    @testing.gen_test
    def test_get_mci_href_missing(self):
        self.actor.desired_images = {}

        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value([])
        ]
        with self.assertRaises(exceptions.InvalidOptions):
            yield self.actor._get_mci_href({'mci': 'test mci'})

    @testing.gen_test
    def test_get_mci_mappings_no_st(self):
        self.actor.st.href = None
        ret = yield self.actor._get_mci_mappings()
        self.assertEquals(None, ret)

    @testing.gen_test
    def test_get_mci_mappings(self):
        mci_map = mock.MagicMock(name='mci_mapping')
        mci_map.soul = {
            'is_default': True
        }
        mci_map.links = {
            'multi_cloud_image': '/api/mci/test'
        }
        mci_map.href = '/api/st_mci/test'

        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(mci_map)
        ]

        ret = yield self.actor._get_mci_mappings()

        self.maxDiff = None
        self.assertEquals(
            ret,
            {'/api/mci/test': {
             'default': True,
             'map_href': '/api/st_mci/test',
             'map_obj': mci_map
             }}
        )

    @testing.gen_test
    def test_get_state(self):
        ret = yield self.actor._get_state()
        self.assertEquals(ret, 'present')

    @testing.gen_test
    def test_get_state_absent(self):
        self.actor.st = mock.MagicMock(name='st')
        self.actor.st.href = None
        self.actor.st.soul = {'name': None}
        ret = yield self.actor._get_state()
        self.assertEquals(ret, 'absent')

    @testing.gen_test
    def test_set_state_present(self):
        self.actor._create_st = mock.MagicMock(name='create_st')
        self.actor._create_st.side_effect = [
            helper.tornado_value(None)
        ]
        yield self.actor._set_state()
        self.assertTrue(self.actor._create_st.called)

    @testing.gen_test
    def test_set_state_absent(self):
        self.actor._options['state'] = 'absent'
        self.actor._delete_st = mock.MagicMock(name='delete_st')
        self.actor._delete_st.side_effect = [
            helper.tornado_value(None)
        ]
        yield self.actor._set_state()
        self.assertTrue(self.actor._delete_st.called)

    @testing.gen_test
    def test_create_st(self):
        new_st = mock.MagicMock(name='new_st')
        self.client_mock.create_resource.side_effect = [
            helper.tornado_value(new_st)
        ]
        yield self.actor._create_st()
        self.assertEquals(self.actor.st, new_st)

    @testing.gen_test
    def test_delete_st(self):
        self.client_mock.destroy_resource.side_effect = [
            helper.tornado_value(None)
        ]
        ret = yield self.actor._delete_st()
        self.assertEquals(ret, None)
        self.client_mock.destroy_resource.assert_has_calls([
            mock.call(self.actor.st)
        ])

    @testing.gen_test
    def test_get_description(self):
        ret = yield self.actor._get_description()
        self.assertEquals('Fake desc', ret)

    @testing.gen_test
    def test_set_description(self):
        new_st = mock.MagicMock(name='new_st')
        self.client_mock.update.side_effect = [
            helper.tornado_value(new_st)
        ]
        yield self.actor._set_description()
        self.assertEquals(new_st, self.actor.st)

    def test_verify_one_default_image(self):
        ret = self.actor._verify_one_default_image()
        self.assertEquals(ret, None)

    def test_verify_one_default_image_too_many(self):
        self.actor.option('images')[1]['is_default'] = True
        with self.assertRaises(exceptions.InvalidOptions):
            self.actor._verify_one_default_image()

    @testing.gen_test
    def test_create_mci_reference(self):
        mci_ref_params = [
            ('server_template_multi_cloud_image[multi_cloud_image_href]',
             '/api/clouds/A/images/abc'),
            ('server_template_multi_cloud_image[server_template_href]',
             '/api/server_templates/abc')
        ]
        self.client_mock.create_resource.side_effect = [
            helper.tornado_value(None)
        ]
        yield self.actor._create_mci_reference(mci_ref_params)

        self.assertTrue(self.client_mock.create_resource.called)
        self.assertTrue(self.actor.changed)

    @testing.gen_test
    def test_delete_mci_reference(self):
        mci_ref_obj = mock.MagicMock(name='mci_ref_obj')
        mci_ref_obj.links = {
            'multi_cloud_image': '/mci_link'
        }
        self.client_mock.destroy_resource.side_effect = [
            helper.tornado_value(None)
        ]
        yield self.actor._delete_mci_reference(mci_ref_obj)

        self.assertTrue(self.client_mock.destroy_resource.called)
        self.assertTrue(self.actor.changed)

    @testing.gen_test
    def test_delete_mci_reference_fails_was_default(self):
        mci_ref_obj = mock.MagicMock(name='mci_ref_obj')
        mci_ref_obj.links = {
            'multi_cloud_image': '/mci_link'
        }
        mocked_resp = mock.MagicMock(name='response')
        mocked_resp.text = 'Default ServerTemplateMultiCloudImages ...'
        exc = requests.exceptions.HTTPError(
            'error', response=mocked_resp)
        self.client_mock.destroy_resource.side_effect = exc
        with self.assertRaises(exceptions.InvalidOptions):
            yield self.actor._delete_mci_reference(mci_ref_obj)

    @testing.gen_test
    def test_get_tags(self):
        ret = yield self.actor._get_tags()
        self.assertEquals(self.actor.tags, ret)

    @testing.gen_test
    def test_set_tags(self):
        self.actor._add_resource_tags = mock.MagicMock(name='add_tags')
        self.actor._add_resource_tags.side_effect = [
            helper.tornado_value(None)
        ]
        self.actor._delete_resource_tags = mock.MagicMock(name='delete_tags')
        self.actor._delete_resource_tags.side_effect = [
            helper.tornado_value(None)
        ]
        self.actor._options['tags'] = ['tag2', 'tag3']
        yield self.actor._set_tags()

        self.actor._add_resource_tags.assert_has_calls([
            mock.call(resource=self.actor.st, tags=['tag3'])
        ])

        self.actor._delete_resource_tags.assert_has_calls([
            mock.call(resource=self.actor.st, tags=['tag1'])
        ])

    @testing.gen_test
    def test_get_images(self):
        yield self.actor._get_images()

    @testing.gen_test
    def test_set_images(self):
        self.client_mock.create_resource.side_effect = [
            helper.tornado_value(None)]
        self.client_mock.destroy_resource.side_effect = [
            helper.tornado_value(None)]
        self.actor._ensure_mci_default = mock.MagicMock()
        self.actor._ensure_mci_default.side_effect = [
            helper.tornado_value(None)]

        yield self.actor._set_images()

        self.client_mock.create_resource.assert_has_calls([
            mock.call(
                self.client_mock._client.server_template_multi_cloud_images,
                [('server_template_multi_cloud_image[multi_cloud_image_href]',
                  '/api/multi_cloud_images/imageB'),
                 ('server_template_multi_cloud_image[server_template_href]',
                  '/api/server_templates/test')]
            ),
            mock.call(
                self.client_mock._client.server_template_multi_cloud_images,
                [('server_template_multi_cloud_image[multi_cloud_image_href]',
                  '/api/multi_cloud_images/imageC'),
                 ('server_template_multi_cloud_image[server_template_href]',
                  '/api/server_templates/test')]
            ),
            mock.call(
                self.client_mock._client.server_template_multi_cloud_images,
                [('server_template_multi_cloud_image[multi_cloud_image_href]',
                  '/api/multi_cloud_images/imageA'),
                 ('server_template_multi_cloud_image[server_template_href]',
                  '/api/server_templates/test')]
            )
        ])
        self.client_mock.destroy_resource.assert_has_calls([
            mock.call(
                self.actor.images['/api/multi_cloud_images/imageD']
                ['map_obj']
            )
        ])

    @testing.gen_test
    def test_compare_images(self):
        ret = yield self.actor._compare_images()
        self.assertFalse(ret)

    @testing.gen_test
    def test_ensure_mci_default_already_matches(self):
        yield self.actor._ensure_mci_default()
        self.assertFalse(self.client_mock.find_by_name_and_keys.called)

    @testing.gen_test
    def test_ensure_mci_default_has_no_MCIs(self):
        self.actor.st.links = {'self': '/api/server_templates/abc'}
        yield self.actor._ensure_mci_default()

    @testing.gen_test
    def test_ensure_mci_default_no_default_selected(self):
        self.actor._dry = True
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value([])]
        di = self.actor.desired_images['/api/multi_cloud_images/imageA']
        di['default'] = False
        yield self.actor._ensure_mci_default()

    @testing.gen_test
    def test_ensure_mci_default_bails_on_dry(self):
        self.actor.st.links['default_multi_cloud_image'] = 'invalid'

        self.actor._dry = True
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(['junk'])
        ]
        yield self.actor._ensure_mci_default()

    @testing.gen_test
    def test_ensure_mci_default(self):
        self.actor.st.links['default_multi_cloud_image'] = 'invalid'

        st_mci_a = mock.MagicMock(name='st_mci_a')
        st_mci_a.links = {
            'self': '/api/server_template_multi_cloud_image/A',
            'multi_cloud_image': '/api/multi_cloud_images/imageA'
        }
        st_mci_b = mock.MagicMock(name='st_mci_b')
        st_mci_b.links = {
            'self': '/api/server_template_multi_cloud_image/B',
            'multi_cloud_image': '/api/multi_cloud_images/imageB'
        }

        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value([st_mci_a, st_mci_b])
        ]

        self.client_mock.make_generic_request.side_effect = [
            helper.tornado_value(None)]

        yield self.actor._ensure_mci_default()

        self.client_mock.make_generic_request.assert_has_calls([
            mock.call(
                '/api/server_template_multi_cloud_image/A/make_default',
                post=[])
        ])

    @testing.gen_test
    def test_ensure_mci_default_invalid_api_data(self):
        self.actor.st.links['default_multi_cloud_image'] = 'junk'

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
            yield self.actor._ensure_mci_default()

    @testing.gen_test
    def test_commit(self):
        fake_st_setting = mock.MagicMock(name='st_setting')
        fake_st_setting.soul = {
            'revision': 2
        }
        self.client_mock.commit_resource.side_effect = [
            helper.tornado_value(fake_st_setting)
        ]
        self.actor.log = mock.MagicMock(name='log')
        yield self.actor._commit()
        self.actor.log.assert_has_calls([
            mock.call.info('Committing a new revision'),
            mock.call.info('Committed revision 2')
        ])

    @testing.gen_test
    def test_execute_present(self):
        self.actor.changed = True
        self.actor._dry = True
        self.actor._commit = helper.mock_tornado(None)
        self.actor._precache = helper.mock_tornado(None)
        self.actor._set_description = helper.mock_tornado(None)
        self.actor._set_images = helper.mock_tornado(None)

        yield self.actor._execute()

    @testing.gen_test
    def test_execute_absent(self):
        self.actor._options['state'] = 'absent'
        self.actor.st = mock.MagicMock()
        self.actor.st.href = None
        self.actor._precache = helper.mock_tornado(None)

        yield self.actor._execute()
