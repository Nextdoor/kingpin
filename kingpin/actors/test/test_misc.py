import logging

from tornado import gen
from tornado import testing

from kingpin.actors import misc
from kingpin.actors import exceptions


log = logging.getLogger(__name__)


class TestSleep(testing.AsyncTestCase):
    @gen.coroutine
    def setUp(self):
        super(TestSleep, self).setUp()

        # Create a Sleep object
        self.actor = misc.Sleep()

    @testing.gen_test
    def test_execute_missing_options(self):
        # Call the executor and test it out
        res = None
        with self.assertRaises(exceptions.InvalidOptions):
            res = yield self.actor.execute('Unit Test Action', {})

        # Make sure we fired off an alert.
        self.assertEquals(res, None)

    @testing.gen_test
    def test_execute(self):
        # Call the executor and test it out
        res = yield self.actor.execute('Unit Test Action', {'sleep': 0.1})

        # Make sure we fired off an alert.
        self.assertEquals(res, True)
