from nose.plugins.attrib import attr
import uuid

from tornado import testing

from kingpin.actors.rightscale import mci
from kingpin.actors.rightscale import server_template


__author__ = 'Matt Wise <matt@nextdoor.com>'
UUID = uuid.uuid4().hex


class IntegrationMCIandST(testing.AsyncTestCase):

    integration = True

    def setUp(self, *args, **kwargs):
        super(IntegrationMCIandST, self).setUp(*args, **kwargs)
        self.name = 'Kingpin MCI/ST Integration Test %s' % UUID
        self.images = [
            {'cloud': 'EC2 us-west-2',
             'image': 'ami-e29774d1',
             'instance_type': 'm1.small',
             'user_data': 'cd /bin/bash'
             },
            {'cloud': 'EC2 us-west-1',
             'image': 'ami-b58142f1',
             'instance_type': 'm1.small',
             'user_data': 'cd /bin/bash'}
        ]

        self.template = {
            'name': 'Kingpin MCI/ST Integration Test %s' % UUID,
            'state': 'present',
            'freeze_repositories': True,
            'commit_head_dependencies': False,
            'description': 'Test %s' % UUID,
            'commit': 'Auto commit test',
            'images': [{'mci': self.name}],
            'tags': [
                'boneman:test=true'
            ],
            'alerts': [
                {'name': 'Instance Stranded',
                 'description': 'Alert if an instance enders a stranded',
                 'file': 'RS/server-failure',
                 'variable': 'state',
                 'condition': '==',
                 'threshold': 'stranded',
                 'duration': 2,
                 'escalation_name': 'critical'}
            ]
        }

    @attr('rightscale', 'integration', 'dry')
    @testing.gen_test(timeout=60)
    def integration_01a_create_mci_dry(self):
        actor = mci.MCI(
            options={'name': self.name,
                     'description': self.name,
                     'state': 'present',
                     'images': self.images},
            dry=True)
        yield actor.execute()

    @attr('rightscale', 'integration')
    @testing.gen_test(timeout=60)
    def integration_01b_create_mci(self):
        actor = mci.MCI(
            options={'name': self.name,
                     'description': self.name,
                     'state': 'present',
                     'images': self.images})
        yield actor.execute()

    @attr('rightscale', 'integration')
    @testing.gen_test(timeout=60)
    def integration_03a_update_mci(self):
        self.images[0]['instance_type'] = 'm1.large'
        self.images[1]['instance_type'] = 'm1.large'

        actor = mci.MCI(
            options={'name': self.name,
                     'description': self.name,
                     'state': 'present',
                     'commit': 'Changed instance type to m1.large',
                     'images': self.images})

        yield actor.execute()

    @attr('rightscale', 'integration')
    @testing.gen_test(timeout=60)
    def integration_03b_update_mci(self):

        actor = mci.MCI(
            options={'name': self.name,
                     'description': self.name,
                     'state': 'present',
                     'tags': 'some_new_tag',
                     'commit': 'Added a tag',
                     'images': self.images})

        yield actor.execute()

    @attr('rightscale', 'integration', 'dry')
    @testing.gen_test(timeout=60)
    def integration_05a_create_st_dry(self):
        actor = server_template.ServerTemplate(
            options=self.template,
            dry=True)
        yield actor.execute()

    @attr('rightscale', 'integration')
    @testing.gen_test(timeout=60)
    def integration_05b_create_st(self):
        actor = server_template.ServerTemplate(
            options=self.template)
        yield actor.execute()

    @attr('rightscale', 'integration')
    @testing.gen_test(timeout=60)
    def integration_05c_update_st(self):
        self.template['alerts'][0]['duration'] = 5
        actor = server_template.ServerTemplate(
            options=self.template)
        yield actor.execute()

    @attr('rightscale', 'integration')
    @testing.gen_test(timeout=60)
    def integration_06a_delete_st(self):
        self.template['state'] = 'absent'
        actor = server_template.ServerTemplate(
            options=self.template)
        yield actor.execute()

    @attr('rightscale', 'integration', 'dry')
    @testing.gen_test(timeout=60)
    def integration_09a_destroy_mci_dry(self):
        actor = mci.MCI(
            options={'name': self.name,
                     'description': self.name,
                     'state': 'absent',
                     'images': self.images},
            dry=True)
        yield actor.execute()

    @attr('rightscale', 'integration')
    @testing.gen_test(timeout=60)
    def integration_09b_destroy_mci(self):
        actor = mci.MCI(
            options={'name': self.name,
                     'description': self.name,
                     'state': 'absent',
                     'images': self.images})
        yield actor.execute()
