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

    @attr('integration', 'dry')
    @testing.gen_test()
    def integration_01a_create_mci_dry(self):
        actor = mci.Create('Integ. Test',
                           {'name': self.mci_name,
                            'images': self.images},
                           dry=True)
        yield actor.execute()

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_01b_create_mci(self):
        actor = mci.Create('Integ. Test',
                           {'name': self.mci_name,
                            'images': self.images})
        yield actor.execute()

    @attr('integration', 'dry')
    @testing.gen_test()
    def integration_02a_destroy_mci_dry(self):
        actor = mci.Destroy('Integ. Test',
                            {'name': self.mci_name},
                            dry=True)
        yield actor.execute()

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_02b_destroy_mci(self):
        actor = mci.Destroy('Integ. Test',
                            {'name': self.mci_name})
        yield actor.execute()
