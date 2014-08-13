import logging

from tornado import gen
from tornado import testing

from kingpin.actors import misc
from kingpin.actors import exceptions


log = logging.getLogger(__name__)


class TestSleep(testing.AsyncTestCase):
    @testing.gen_test
    def test_init_missing_options(self):
        with self.assertRaises(exceptions.InvalidOptions):
            misc.Sleep('Unit Test Action', {})

    @testing.gen_test
    def test_execute(self):
        # Call the executor and test it out
        actor = misc.Sleep('Unit Test Action', {'sleep': 0.1})
        res = yield actor.execute()

        # Make sure we fired off an alert.
        self.assertEquals(res, True)
