import logging
import mock

from tornado import gen
from tornado import testing

from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.actors import utils
from kingpin.actors import misc
from kingpin.actors.test import helper


log = logging.getLogger(__name__)


class FakeActor(base.BaseActor):

    """Fake Actor use for Unit Tests"""

    def __init__(self, *args, **kwargs):
        super(FakeActor, self).__init__(*args, **kwargs)
        self.conn = mock.MagicMock()
        self.conn.call.return_value = helper.tornado_value(None)
        self.conn.call.__name__ = 'test_call'

    @gen.coroutine
    @utils.dry('Would have done {0}')
    def do_thing(self, thing):
        yield self.conn.call(thing)

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
        self.assertEqual(True, ret._options['return_value'])
        self.assertEqual(FakeActor, type(ret))

    def test_get_actor_class(self):
        actor_string = 'misc.Sleep'
        ret = utils.get_actor_class(actor_string)
        self.assertEqual(type(misc.Sleep), type(ret))

    def test_get_actor_class_direct(self):
        actor_string = 'kingpin.actors.test.test_utils.FakeActor'
        ret = utils.get_actor_class(actor_string)
        self.assertEqual(type(FakeActor), type(ret))

    def test_get_actor_class_bogus_actor(self):
        actor_string = 'bogus.actor'
        with self.assertRaises(exceptions.InvalidActor):
            utils.get_actor_class(actor_string)

    @testing.gen_test
    def test_dry_decorator_with_dry_true(self):
        actor = FakeActor('Fake', options={}, dry=True)
        yield actor.do_thing('my thing string')
        self.assertFalse(actor.conn.called)

    @testing.gen_test
    def test_dry_decorator_with_dry_false(self):
        actor = FakeActor('Fake', options={}, dry=False)
        yield actor.do_thing('my thing string')
        actor.conn.call.assert_has_calls([mock.call('my thing string')])
