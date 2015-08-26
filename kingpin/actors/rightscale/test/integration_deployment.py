from nose.plugins.attrib import attr
import uuid

from tornado import testing

from kingpin.actors.rightscale import deployment


__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'
UUID = uuid.uuid4().hex


class IntegrationDeployment(testing.AsyncTestCase):

    integration = True

    def setUp(self, *args, **kwargs):
        super(IntegrationDeployment, self).setUp(*args, **kwargs)
        self.deployment_name = 'Kingpin Deployment Integration Test %s' % UUID

    @attr('integration', 'dry')
    @testing.gen_test()
    def integration_01a_create_deployment_dry(self):
        actor = deployment.Create('Integ. Test',
                                  {'name': self.deployment_name},
                                  dry=True)

        yield actor.execute()

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_01b_create_deployment(self):
        actor = deployment.Create('Integ. Test',
                                  {'name': self.deployment_name})

        yield actor.execute()

    @attr('integration', 'dry')
    @testing.gen_test(timeout=60)
    def integration_02a_clone_deployment_dry(self):
        actor = deployment.Clone('Integ. Test',
                                 {'clone': self.deployment_name,
                                  'name': '%s clone' % self.deployment_name},
                                 dry=True)

        yield actor.execute()

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_02b_clone_deployment(self):
        actor = deployment.Clone('Integ. Test',
                                 {'clone': self.deployment_name,
                                  'name': '%s clone' % self.deployment_name})

        yield actor.execute()

    @attr('integration', 'dry')
    @testing.gen_test()
    def integration_03a_destroy_deployment_dry(self):
        actor = deployment.Destroy('Integ. Test',
                                   {'name': self.deployment_name},
                                   dry=True)

        yield actor.execute()

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_03b_destroy_deployment(self):
        actor = deployment.Destroy('Integ. Test',
                                   {'name': self.deployment_name})

        yield actor.execute()

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_04b_destroy_cloned_deployment(self):
        actor = deployment.Destroy('Integ. Test',
                                   {'name': '%s clone' % self.deployment_name})

        yield actor.execute()
