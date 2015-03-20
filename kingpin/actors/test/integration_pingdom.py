"""Tests for the pingdom actors"""

from tornado import testing

from kingpin import utils
from kingpin.actors import pingdom


__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'


class IntegrationPingdom(testing.AsyncTestCase):

    integration = True

    check_name = 'kingpin-integration-test'

    @testing.gen_test(timeout=60)
    def integration_01a_test_pause(self):

        actor = pingdom.Pause('Pause check', {'name': self.check_name})

        yield actor.execute()

        yield utils.tornado_sleep(30)  # Let Pingdom cache settle

        check = yield actor._get_check()

        self.assertEquals(check['status'], 'paused')

    @testing.gen_test(timeout=60)
    def integration_02a_test_unpause(self):

        actor = pingdom.Unpause('Unpause check', {'name': self.check_name})

        yield actor.execute()

        yield utils.tornado_sleep(30)  # Let Pingdom cache settle

        check = yield actor._get_check()

        self.assertEquals(check['status'], 'up')
