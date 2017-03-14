import logging
import mock

from tornado import testing
import requests

from kingpin.actors import exceptions
from kingpin.actors.rightscale import base
from kingpin.actors.rightscale import alerts
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

        self._boot_bindings = [
            {'right_script': 'bootA', 'rev': 0},
            {'right_script': 'bootB', 'rev': 0},
        ]
        self._operational_bindings = [
            {'right_script': 'operationalA', 'rev': 0},
            {'right_script': 'operationalB', 'rev': 0},
        ]
        self._decommission_bindings = [
            {'right_script': 'decommissionA', 'rev': 0},
            {'right_script': 'decommissionB', 'rev': 0},
        ]
        self._alerts = [
            {'name': 'Instance Stranded',
             'description': 'Alert if an instance enders a stranded',
             'file': 'RS/server-failure',
             'variable': 'state',
             'condition': '==',
             'threshold': 'stranded',
             'duration': 2,
             'escalation_name': 'critical'}
        ]

        # Create the actor
        self.actor = server_template.ServerTemplate(
            options={
                'name': 'testst',
                'state': 'present',
                'commit': 'Yeah, committed',
                'tags': ['tag'],
                'description': 'test st desc',
                'images': self._images,
                'boot_bindings': self._boot_bindings,
                'operational_bindings': self._operational_bindings,
                'decommission_bindings': self._decommission_bindings,
                'alerts': self._alerts,
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

        # For most tests, pretend we have no bindings at all
        self.actor.boot_bindings = []
        self.actor.operational_bindings = []
        self.actor._bindings = []

        # Pretend though that we were able to populate our desired bindings
        # with real HREFs.
        self.actor.desired_boot_bindings = [
            {'position': 0,
             'right_script_href': '/api/binding/bootA',
             'sequence': 'boot'},
            {'position': 1,
             'right_script_href': '/api/binding/bootB',
             'sequence': 'boot'},
        ]
        self.actor.desired_operational_bindings = [
            {'position': 0,
             'right_script_href': '/api/binding/operationalA',
             'sequence': 'operational'},
            {'position': 1,
             'right_script_href': '/api/binding/operationalB',
             'sequence': 'operational'},
        ]
        self.actor.desired_decommission_bindings = [
            {'position': 0,
             'right_script_href': '/api/binding/decommissionA',
             'sequence': 'decommission'},
            {'position': 1,
             'right_script_href': '/api/binding/decommissionB',
             'sequence': 'decommission'},
        ]

    @testing.unittest.skip('This test is missing some stuff.  Help!!!')
    def test_precache(self):
        # Generate new ST and Tag mocks
        new_st = mock.MagicMock(name='new_st')
        boot_binding_c = mock.MagicMock(name='bootC')
        new_tags = ['tag3']

        # Used when searching for the server template
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(new_st)
        ]

        self.client_mock.show.side_effect = [
            helper.tornado_value(boot_binding_c)
        ]

        self.actor._get_resource_tags = mock.MagicMock()
        self.actor._get_resource_tags.side_effect = [
            helper.tornado_value(new_tags)
        ]

        with mock.patch.object(alerts, 'AlertSpecsBase') as a_mock:
            a_mock()._precache.side_effect = [
                helper.tornado_value(None)]

            yield self.actor._precache()
            self.assertEquals(self.actor.alert_specs, a_mock())
        self.assertEquals(self.actor.st, new_st)
        self.assertEquals(self.actor.desired_images, {})
        self.assertEquals(self.actor.tags, new_tags)

    @testing.gen_test
    def test_precache_absent_template(self):
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value([]),
            helper.tornado_value([]),
            helper.tornado_value([]),
            helper.tornado_value([]),
        ]

        with self.assertRaises(exceptions.InvalidOptions):
            yield self.actor._precache()

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
            helper.tornado_value(None)] * 3
        self.client_mock.destroy_resource.side_effect = [
            helper.tornado_value(None)]
        self.actor._ensure_mci_default = mock.MagicMock()
        self.actor._ensure_mci_default.side_effect = [
            helper.tornado_value(None)]

        yield self.actor._set_images()

        print(self.client_mock.create_resource.call_args_list)
        self.client_mock.create_resource.assert_has_calls([
            mock.call(
                self.client_mock._client.server_template_multi_cloud_images,
                helper.InAnyOrder([
                    ('server_template_multi_cloud_image[multi_cloud_image_href]',
                     '/api/multi_cloud_images/imageB'),
                    ('server_template_multi_cloud_image[server_template_href]',
                     '/api/server_templates/test')])
                ),
            mock.call(
                self.client_mock._client.server_template_multi_cloud_images,
                helper.InAnyOrder([
                 ('server_template_multi_cloud_image[multi_cloud_image_href]',
                  '/api/multi_cloud_images/imageC'),
                 ('server_template_multi_cloud_image[server_template_href]',
                  '/api/server_templates/test')])
                ),
            mock.call(
                self.client_mock._client.server_template_multi_cloud_images,
                helper.InAnyOrder([
                    ('server_template_multi_cloud_image[multi_cloud_image_href]',
                     '/api/multi_cloud_images/imageA'),
                    ('server_template_multi_cloud_image[server_template_href]',
                     '/api/server_templates/test')])
                )
        ], any_order=True)
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
    def test_set_operational_bindings(self):
        self.actor._set_bindings = mock.MagicMock()
        self.actor._set_bindings.side_effect = [helper.tornado_value(None)]
        yield self.actor._set_operational_bindings()
        self.actor._set_bindings.assert_called_with(
            self.actor.desired_operational_bindings,
            self.actor.operational_bindings,
            'operational'
        )

    @testing.gen_test
    def test_get_operational_bindings(self):
        ret = yield self.actor._get_operational_bindings()
        self.assertEquals(self.actor.operational_bindings, ret)

    @testing.gen_test
    def test_set_decommission_bindings(self):
        self.actor._set_bindings = mock.MagicMock()
        self.actor._set_bindings.side_effect = [helper.tornado_value(None)]
        yield self.actor._set_decommission_bindings()
        self.actor._set_bindings.assert_called_with(
            self.actor.desired_decommission_bindings,
            self.actor.decommission_bindings,
            'decommission'
        )

    @testing.gen_test
    def test_get_decommission_bindings(self):
        ret = yield self.actor._get_decommission_bindings()
        self.assertEquals(self.actor.decommission_bindings, ret)

    @testing.gen_test
    def test_set_boot_bindings(self):
        self.actor._set_bindings = mock.MagicMock()
        self.actor._set_bindings.side_effect = [helper.tornado_value(None)]
        yield self.actor._set_boot_bindings()
        self.actor._set_bindings.assert_called_with(
            self.actor.desired_boot_bindings,
            self.actor.boot_bindings,
            'boot'
        )

    @testing.gen_test
    def test_get_boot_bindings(self):
        ret = yield self.actor._get_boot_bindings()
        self.assertEquals(self.actor.boot_bindings, ret)

    @testing.gen_test
    def test_get_bindings(self):
        boot_binding_c = mock.MagicMock()
        boot_binding_c.soul = {'sequence': 'boot', 'position': 0}

        operational_binding_c = mock.MagicMock()
        operational_binding_c.soul = {'sequence': 'operational', 'position': 0}

        existing_bindings = [boot_binding_c, operational_binding_c]

        self.client_mock.show.side_effect = [
            helper.tornado_value(existing_bindings)
        ]

        (boot, operational, decommission) = yield self.actor._get_bindings()

        self.assertEquals([boot_binding_c], boot)
        self.assertEquals([operational_binding_c], operational)
        self.assertEquals([], decommission)

    @testing.gen_test
    def test_generate_bindings_empty(self):
        ret = yield self.actor._generate_bindings([], 'test')
        self.assertEquals([], ret)

    @testing.gen_test
    def test_generate_bindings(self):
        binding_a_mocked_res_rev_0 = mock.MagicMock(name='binding_a')
        binding_a_mocked_res_rev_0.href = '/api/binding/binding_a_rev_0'
        binding_a_mocked_res_rev_0.soul = {'revision': 0}

        binding_a_mocked_res_rev_1 = mock.MagicMock(name='binding_a')
        binding_a_mocked_res_rev_1.href = '/api/binding/binding_a_rev_1'
        binding_a_mocked_res_rev_1.soul = {'revision': 1}

        binding_b_mocked_res = mock.MagicMock(name='binding_b')
        binding_b_mocked_res.href = '/api/binding/binding_b_rev_0'
        binding_b_mocked_res.soul = {'revision': 0}

        self.client_mock.find_by_name_and_keys.side_effect = [
            # The first call will look for script A and get a list of results
            # back. One will match, the others wont.
            helper.tornado_value([
                binding_a_mocked_res_rev_0, binding_a_mocked_res_rev_1]),

            # The second call will actually get back a single result thats not
            # in a list. It will match what we're looking for
            helper.tornado_value(binding_b_mocked_res),
        ]

        ret = yield self.actor._generate_bindings(
            self.actor.option('boot_bindings'), 'boot')
        self.assertEquals(
            [
                {'position': 1,
                 'right_script_href': '/api/binding/binding_a_rev_0',
                 'sequence': 'boot'},
                {'position': 2,
                 'right_script_href': '/api/binding/binding_b_rev_0',
                 'sequence': 'boot'},
            ], ret)

    @testing.gen_test
    def test_generate_bindings_empty_result(self):
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value([])
        ]
        with self.assertRaises(exceptions.InvalidOptions):
            yield self.actor._generate_bindings(
                self.actor.option('boot_bindings'), 'boot')

    @testing.gen_test
    def test_generate_bindings_missing_revision(self):
        binding_a_mocked_res_rev_2 = mock.MagicMock(name='binding_a')
        binding_a_mocked_res_rev_2.href = '/api/binding/binding_a_rev_2'
        binding_a_mocked_res_rev_2.soul = {'revision': 2}

        binding_a_mocked_res_rev_1 = mock.MagicMock(name='binding_a')
        binding_a_mocked_res_rev_1.href = '/api/binding/binding_a_rev_1'
        binding_a_mocked_res_rev_1.soul = {'revision': 1}

        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value([
                binding_a_mocked_res_rev_2, binding_a_mocked_res_rev_1]),
        ]

        with self.assertRaises(exceptions.InvalidOptions):
            yield self.actor._generate_bindings(
                self.actor.option('boot_bindings'), 'boot')

        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(binding_a_mocked_res_rev_2)
        ]

        with self.assertRaises(exceptions.InvalidOptions):
            yield self.actor._generate_bindings(
                self.actor.option('boot_bindings'), 'boot')

    @testing.gen_test
    def test_set_bindings(self):
        binding_c = mock.MagicMock('binding_c')
        binding_c.href = '/api/binding/C'

        self.actor.boot_bindings = [
            binding_c
        ]
        self.client_mock.destroy_resource.side_effect = [
            helper.tornado_value(None)
        ]
        self.client_mock.create_resource.side_effect = [
            helper.tornado_value(None),
            helper.tornado_value(None)
        ]

        yield self.actor._set_bindings(
            self.actor.desired_boot_bindings,
            self.actor.boot_bindings,
            'boot')

        self.client_mock.destroy_resource.assert_has_calls(
            [mock.call(self.actor.boot_bindings[0])],
        )
        self.client_mock.create_resource.assert_has_calls([
            mock.call(
                self.actor.st.runnable_bindings,
                helper.InAnyOrder([
                    ('runnable_binding[right_script_href]', '/api/binding/bootA'),
                    ('runnable_binding[sequence]', 'boot')])),
            mock.call(
                self.actor.st.runnable_bindings,
                helper.InAnyOrder([
                    ('runnable_binding[right_script_href]', '/api/binding/bootB'),
                    ('runnable_binding[sequence]', 'boot')])),
        ])

        self.assertTrue(self.actor.changed)

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
    def test_get_alerts(self):
        ret = yield self.actor._get_alerts()
        self.assertEquals(None, ret)

    @testing.gen_test
    def test_compare_alerts(self):
        self.actor.alert_specs = mock.MagicMock()
        self.actor.alert_specs._compare_specs.side_effect = [
            helper.tornado_value(False)]
        ret = yield self.actor._compare_alerts()
        self.assertEquals(False, ret)

    @testing.gen_test
    def test_set_alerts(self):
        self.actor.alert_specs = mock.MagicMock()
        self.actor.alert_specs.execute.side_effect = [
            helper.tornado_value(None)]
        yield self.actor._set_alerts()
        self.assertTrue(self.actor.changed)
        self.assertTrue(self.actor.alert_specs.execute.called)

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
