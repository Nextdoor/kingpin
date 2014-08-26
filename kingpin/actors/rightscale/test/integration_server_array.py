"""Simple integration tests for the RightScale Server_Array actors."""

from nose.plugins.attrib import attr
import uuid

from tornado import testing

from kingpin.actors import exceptions
from kingpin.actors.rightscale import api
from kingpin.actors.rightscale import server_array


__author__ = 'Matt Wise <matt@nextdoor.com>'


# Generate a common UUID for this particular set of tests
UUID = uuid.uuid4().hex


class IntegrationServerArray(testing.AsyncTestCase):

    """High level RightScale Server Array Actors Testing.

    These tests rely on you having a ServerArray in RightScale named
      'kingpin-integration-testing'
    that can be cloned, launched, terminated, etc.

    Note, these tests must be run in-order. The order is defined by
    their definition order in this file. Nose follows this order according
    to its documentation:

        http://nose.readthedocs.org/en/latest/writing_tests.html


    NOTE: At this point, you need to self-clean-up after yourself
          once you've run these tests. Future tests and features will
          allow for these tests to self-clean-up.
    """

    integration = True

    def setUp(self, *args, **kwargs):
        super(IntegrationServerArray, self).setUp(*args, **kwargs)
        self.template_array = 'kingpin-integration-testing'
        self.clone_name = 'kingpin-%s' % UUID

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_01_clone_dry(self):
        actor = server_array.Clone(
            'Clone %s' % self.template_array,
            {'source': self.template_array,
             'dest': self.clone_name},
            dry=True)
        ret = yield actor.execute()
        self.assertEquals(True, ret)

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_02a_clone(self):
        actor = server_array.Clone(
            'Clone %s' % self.template_array,
            {'source': self.template_array,
             'dest': self.clone_name})
        ret = yield actor.execute()
        self.assertEquals(True, ret)

    @attr('integration')
    @testing.gen_test(timeout=30)
    def integration_02b_clone_with_duplicate_array(self):
        actor2 = server_array.Clone(
            'Clone %s' % self.template_array,
            {'source': self.template_array,
             'dest': self.clone_name})
        with self.assertRaises(api.ServerArrayException):
            yield actor2.execute()

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_03a_update_params(self):
        # Patch the array with some new min_instance settings, then launch it
        actor = server_array.Update(
            'Update %s' % self.clone_name,
            {'array': self.clone_name,
                'params': {
                    'elasticity_params': {
                        'bounds': {
                            'min_count': '1',
                            'max_count': '2'
                        }
                    },
                    'status': 'enabled',
                    'description': 'Unit Tests: %s' % UUID,
                }
             }
        )
        ret = yield actor.execute()
        self.assertEquals(True, ret)

    @attr('integration')
    @testing.gen_test(timeout=10)
    def integration_03b_update_with_invalid_params(self):
        actor = server_array.Update(
            'Update %s' % self.template_array,
            {'array': self.template_array,
             'params': {
                 'elasticity_params': {
                     'bounds': {'min_count': '5', 'max_count': '1'}}}})
        with self.assertRaises(exceptions.UnrecoverableActionFailure):
            yield actor.execute()

    # Note: These tests can run super slow -- the server boot time
    # itself may take 5-10 minutes, and sometimes Amazon and RightScale
    # slowdown. Give this test up to 30m to execute before we bail out.
    @attr('integration')
    @testing.gen_test(timeout=1800)
    def integration_04_launch(self):
        # Launch the machines and wait until they boot
        actor = server_array.Launch(
            'Launch %s' % self.clone_name,
            {'array': self.clone_name})
        ret = yield actor.execute()
        self.assertEquals(True, ret)

    @attr('integration')
    @testing.gen_test(timeout=300)
    def integration_05_destroy(self):
        actor = server_array.Destroy(
            'Destroy %s' % self.template_array,
            {'array': self.clone_name, 'terminate': True})
        ret = yield actor.execute()
        self.assertEquals(True, ret)

        self.assertEquals(ret, True)
