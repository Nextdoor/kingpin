'''Simple integration tests for the RightScale Server_Array actors.'''

from nose.plugins.attrib import attr
import uuid

from tornado import testing

from kingpin.actors import exceptions
from kingpin.actors.rightscale import alerts


__author__ = 'Matt Wise <matt@nextdoor.com>'


# Generate a common UUID for this particular set of tests
UUID = uuid.uuid4().hex


class IntegrationAlerts(testing.AsyncTestCase):

    '''High level RightScale Alert Specs testing

    These tests rely on you having a Alerts in RightScale named
      'kingpin-integration-testing'
    that can be cloned, launched, terminated, etc.

    Note, these tests must be run in-order. The order is defined by
    their definition order in this file. Nose follows this order according
    to its documentation:

        http://nose.readthedocs.org/en/latest/writing_tests.html


    NOTE: At this point, you need to self-clean-up after yourself
          once you've run these tests. Future tests and features will
          allow for these tests to self-clean-up.
    '''

    integration = True

    def setUp(self, *args, **kwargs):
        super(IntegrationAlerts, self).setUp(*args, **kwargs)
        self.template_array = 'kingpin-integration-testing'
        self.test_alert_name = 'unit-test-alert-%s' % UUID

    @attr('aws', 'integration', 'dry')
    @testing.gen_test(timeout=60)
    def integration_01a_create_alert_dry(self):
        actor = alerts.Create(
            'Create alert: %s' % self.test_alert_name,
            {'array': self.template_array,
             'strict_array': False,
             'condition': '>',
             'description': 'Integration test alert',
             'duration': 180,
             'vote_tag': 'test',
             'vote_type': 'grow',
             'file': 'interface/if_octets-eth0',
             'name': self.test_alert_name,
             'threshold': '3000000',
             'variable': 'rx'
             },
            dry=True)

        ret = yield actor.execute()
        self.assertEqual(ret, None)

    @attr('aws', 'integration')
    @testing.gen_test(timeout=60)
    def integration_02a_create_alert(self):
        actor = alerts.Create(
            'Create alert: %s' % self.test_alert_name,
            {'array': self.template_array,
             'strict_array': False,
             'condition': '>',
             'description': 'Integration test alert',
             'duration': 180,
             'vote_tag': 'test',
             'vote_type': 'grow',
             'file': 'interface/if_octets-eth0',
             'name': self.test_alert_name,
             'threshold': '300000000',
             'variable': 'rx'
             })

        ret = yield actor.execute()
        self.assertEqual(ret, None)

    @attr('aws', 'integration')
    @testing.gen_test(timeout=60)
    def integration_02b_create_second_alert(self):
        actor = alerts.Create(
            'Create alert: %s' % self.test_alert_name,
            {'array': self.template_array,
             'strict_array': False,
             'condition': '>',
             'description': 'Second alert, same name',
             'duration': 180,
             'vote_tag': 'test',
             'vote_type': 'grow',
             'file': 'interface/if_octets-eth0',
             'name': self.test_alert_name,
             'threshold': '300000000',
             'variable': 'rx'
             })

        ret = yield actor.execute()
        self.assertEqual(ret, None)

    @attr('aws', 'integration')
    @testing.gen_test(timeout=60)
    def integratin_03a_destroy_alert(self):
        actor = alerts.Destroy(
            'Destroy alert: %s' % self.test_alert_name,
            {'array': self.template_array,
             'name': self.test_alert_name})

        ret = yield actor.execute()
        self.assertEqual(ret, None)

    @attr('aws', 'integration')
    @testing.gen_test(timeout=60)
    def integratin_03a_destroy_alert_should_fail(self):
        # The alerts were all deleted in the previous tests, we hope.
        actor = alerts.Destroy(
            'Destroy alert: %s' % self.test_alert_name,
            {'array': self.template_array,
             'name': self.test_alert_name})

        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield actor.execute()
