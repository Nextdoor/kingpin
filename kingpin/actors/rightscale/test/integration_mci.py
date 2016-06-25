from nose.plugins.attrib import attr
import uuid

from tornado import testing

from kingpin.actors.rightscale import mci


__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'
UUID = uuid.uuid4().hex


class IntegrationMCI(testing.AsyncTestCase):

    integration = True

    def setUp(self, *args, **kwargs):
        super(IntegrationMCI, self).setUp(*args, **kwargs)
        self.mci_name = 'Kingpin MCI Integration Test %s' % UUID
        self.images = [
            {'cloud': 'EC2 us-west-2', 'image':
             'ami-e29774d1', 'instance_type': 'm1.small',
             'user_data': 'cd /bin/bash'},
            {'cloud': 'EC2 us-west-1', 'image':
             'ami-b58142f1', 'instance_type':
             'm1.small', 'user_data': 'cd /bin/bash'}
        ]

    @attr('rightscale', 'integration', 'dry')
    @testing.gen_test(timeout=60)
    def integration_01a_create_mci_dry(self):
        actor = mci.MCI(
            options={'name': self.mci_name,
                     'description': self.mci_name,
                     'state': 'present',
                     'images': self.images},
            dry=True)
        yield actor.execute()

    @attr('rightscale', 'integration')
    @testing.gen_test(timeout=60)
    def integration_01b_create_mci(self):
        actor = mci.MCI(
            options={'name': self.mci_name,
                     'description': self.mci_name,
                     'state': 'present',
                     'images': self.images})
        yield actor.execute()

    @attr('rightscale', 'integration', 'dry')
    @testing.gen_test(timeout=60)
    def integration_03a_update_mci(self):
        self.images[0]['instance_type'] = 'm1.large'
        self.images[1]['instance_type'] = 'm1.large'

        actor = mci.MCI(
            options={'name': self.mci_name,
                     'description': self.mci_name,
                     'state': 'present',
                     'commit': 'Changed instance type to m1.large',
                     'images': self.images})

        yield actor.execute()

    @attr('rightscale', 'integration', 'dry')
    @testing.gen_test(timeout=60)
    def integration_03b_update_mci(self):

        actor = mci.MCI(
            options={'name': self.mci_name,
                     'description': self.mci_name,
                     'state': 'present',
                     'tags': 'some_new_tag',
                     'commit': 'Added a tag',
                     'images': self.images})

        yield actor.execute()

    @attr('rightscale', 'integration', 'dry')
    @testing.gen_test(timeout=60)
    def integration_04a_destroy_mci_dry(self):
        actor = mci.MCI(
            options={'name': self.mci_name,
                     'description': self.mci_name,
                     'state': 'absent',
                     'images': self.images},
            dry=True)
        yield actor.execute()

    @attr('rightscale', 'integration', 'dry')
    @testing.gen_test(timeout=60)
    def integration_04b_destroy_mci(self):
        actor = mci.MCI(
            options={'name': self.mci_name,
                     'description': self.mci_name,
                     'state': 'absent',
                     'images': self.images})
        yield actor.execute()
