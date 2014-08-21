"""Simple integration tests for the RightScale Server_Array actors."""

from tornado import testing

from kingpin.actors import exceptions
from kingpin.actors.rightscale import api
from kingpin.actors.rightscale import server_array


__author__ = 'Matt Wise <matt@nextdoor.com>'


class IntegrationServerArray(testing.AsyncTestCase):

    """High level RightScale Server Array Actors Testing.

    These tests rely on you having a ServerArray in RightScale named
      'kingpin-integration-testing'
    that can be cloned, launched, terminated, etc.


    NOTE: At this point, you need to self-clean-up after yourself
          once you've run these tests. Future tests and features will
          allow for these tests to self-clean-up.
    """

    integration = True

    def setUp(self, *args, **kwargs):
        super(IntegrationServerArray, self).setUp(*args, **kwargs)
        self.template_array = 'kingpin-integration-testing'
        self.clone_name = 'kingpin-integratin-testing-clone'

    @testing.gen_test(timeout=10)
    def integration_update_with_invalid_params(self):
        actor = server_array.Update(
            'Update %s' % self.template_array,
            {'array': self.template_array,
             'params': {
                 'elasticity_params': {
                     'bounds': {'min_count': '5', 'max_count': '1'}}}})
        with self.assertRaises(exceptions.UnrecoverableActionFailure):
            yield actor.execute()

    @testing.gen_test(timeout=30)
    def integration_dry_clone(self):
        actor = server_array.Clone('Clone %s' % self.template_array,
                                   {'source': self.template_array,
                                    'dest': self.clone_name},
                                   dry=True)
        ret = yield actor.execute()
        self.assertEquals(True, ret)

    @testing.gen_test(timeout=1800)
    def integration_real_clone(self):
        # Clone the array first
        actor = server_array.Clone('Clone %s' % self.template_array,
                                   {'source': self.template_array,
                                    'dest': self.clone_name})
        ret = yield actor.execute()
        self.assertEquals(True, ret)

        # Patch the array with some new min_instance settings, then launch it
        actor = server_array.Update(
            'Update %s' % self.clone_name,
            {'array': self.clone_name,
                'params': {
                    'elasticity_params': {
                        'bounds': {
                            'min_count': '2',
                            'max_count': '2'
                        }
                    },
                    'status': 'enabled',
                    'description': 'This is pretty nifty'
                }
             }
        )
        ret = yield actor.execute()
        self.assertEquals(True, ret)

        # Launch the machines and wait until they boot
        actor = server_array.Launch(
            'Launch %s' % self.clone_name,
            {'array': self.clone_name})
        ret = yield actor.execute()
        self.assertEquals(True, ret)

        # Now destroy it
        actor = server_array.Destroy('Destroy %s' % self.template_array,
                                     {'array': self.clone_name,
                                      'terminate': True})
        ret = yield actor.execute()
        self.assertEquals(True, ret)

    @testing.gen_test(timeout=30)
    def integration_real_clone_with_duplicate_dest_array(self):
        actor1 = server_array.Clone(
            'Clone %s' % self.template_array,
            {'source': self.template_array,
             'dest': self.clone_name})
        actor2 = server_array.Clone(
            'Clone %s' % self.template_array,
            {'source': self.template_array,
             'dest': self.clone_name})
        with self.assertRaises(api.ServerArrayException):
            yield actor1.execute()
            yield actor2.execute()

        # Now destroy it
        actor = server_array.Destroy('Destroy %s' % self.template_array,
                                     {'array': self.clone_name,
                                      'terminate': True})
        ret = yield actor.execute()
        self.assertEquals(ret, True)
