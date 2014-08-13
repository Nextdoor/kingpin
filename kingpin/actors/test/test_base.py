import logging
import time

from tornado import gen
from tornado import testing
from tornado.ioloop import IOLoop

from kingpin.actors import base


log = logging.getLogger(__name__)


class TestActorBase(testing.AsyncTestCase):
    @gen.coroutine
    def sleep(self, desc, options):
        # Basically a fake action that should take a few seconds to run for the
        # sake of the unit tests.
        yield gen.Task(IOLoop.current().add_timeout, time.time() + 0.1)
        raise gen.Return(True)

    def setUp(self):
        super(TestActorBase, self).setUp()

        # Create a ActorBase object
        self.actor = base.ActorBase()

        # Mock out the actors ._execute() method so that we have something to
        # test
        self.actor._execute = self.sleep

    @testing.gen_test
    def test_execute(self):
        # Call the executor and test it out
        res = yield self.actor.execute('Unit Test Action', {})

        # Make sure we fired off an alert.
        self.assertEquals(res, True)
