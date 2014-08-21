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
                                    'dest': '%s-clone' % self.template_array},
                                   dry=True)
        ret = yield actor.execute()
        self.assertEquals(True, ret)

    @testing.gen_test(timeout=30)
    def integration_real_clone(self):
        actor = server_array.Clone('Clone %s' % self.template_array,
                                   {'source': self.template_array,
                                    'dest': '%s-clone' % self.template_array})
        ret = yield actor.execute()
        self.assertEquals(True, ret)

    @testing.gen_test(timeout=30)
    def integration_real_clone_with_duplicate_dest_array(self):
        actor1 = server_array.Clone(
            'Clone %s' % self.template_array,
            {'source': self.template_array,
             'dest': '%s-clone1' % self.template_array})
        actor2 = server_array.Clone(
            'Clone %s' % self.template_array,
            {'source': self.template_array,
             'dest': '%s-clone1' % self.template_array})
        with self.assertRaises(api.ServerArrayException):
            yield actor1.execute()
            yield actor2.execute()
