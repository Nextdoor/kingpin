import logging

from tornado import gen
from tornado import testing

from kingpin.actors import exceptions
from kingpin.actors import utils
from kingpin.actors import misc


log = logging.getLogger(__name__)


class FakeActor(object):

    """Fake Actor use for Unit Tests"""

    def __init__(self, desc, options, dry=False):
        log.info('Initializing %s: %s' % (desc, options))
        self.options = options

    @gen.coroutine
    def execute(self):
        raise gen.Return(self.options['return_value'])


class TestUtils(testing.AsyncTestCase):

    def test_get_actor(self):
        actor_return_true = {
            'desc': 'returns true',
            'actor': 'kingpin.actors.test.test_utils.FakeActor',
            'options': {'return_value': True}}
        ret = utils.get_actor(actor_return_true, dry=True)
        self.assertEquals(True, ret.options['return_value'])
        self.assertEquals(FakeActor, type(ret))

    def test_get_actor_class(self):
        actor_string = 'misc.Sleep'
        ret = utils.get_actor_class(actor_string)
        self.assertEquals(type(misc.Sleep), type(ret))

    def test_get_actor_class_direct(self):
        actor_string = 'kingpin.actors.test.test_utils.FakeActor'
        ret = utils.get_actor_class(actor_string)
        self.assertEquals(type(FakeActor), type(ret))

    def test_get_actor_class_bogus_actor(self):
        actor_string = 'bogus.actor'
        with self.assertRaises(exceptions.InvalidActor):
            utils.get_actor_class(actor_string)
