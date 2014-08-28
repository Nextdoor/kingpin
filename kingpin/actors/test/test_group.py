import logging

from tornado import gen
from tornado import testing

from kingpin.actors import base
from kingpin.actors import group


log = logging.getLogger(__name__)


class TestActor(base.BaseActor):

    """Fake Actor for Tests"""

    @gen.coroutine
    def _execute(self):
        raise gen.Return(self._options['return_value'])


class TestBaseGroupActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestBaseGroupActor, self).setUp(*args, **kwargs)
        self.actor_return_true = {
            'desc': 'returns true',
            'actor': 'kingpin.actors.test.test_group.TestActor',
            'options': {'return_value': True}}
        self.actor_return_false = {
            'desc': 'returns false',
            'actor': 'kingpin.actors.test.test_group.TestActor',
            'options': {'return_value': False}}

    def test_get_actor(self):
        actor = group.BaseGroupActor(
            'Unit Test Action', {'acts': []})
        ret = actor._get_actor(self.actor_return_true)
        self.assertEquals(True, ret._options['return_value'])
        self.assertEquals(TestActor, type(ret))

    def test_build_actions(self):
        actor = group.BaseGroupActor(
            'Unit Test Action',
            {'acts': [dict(self.actor_return_true),
                      dict(self.actor_return_true),
                      dict(self.actor_return_true),
                      dict(self.actor_return_true)]})
        ret = actor._build_actions()
        self.assertEquals(4, len(ret))


class TestSyncGroupActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestSyncGroupActor, self).setUp(*args, **kwargs)
        self.actor_return_true = {
            'desc': 'returns true',
            'actor': 'kingpin.actors.test.test_group.TestActor',
            'options': {'return_value': True}}
        self.actor_return_false = {
            'desc': 'returns false',
            'actor': 'kingpin.actors.test.test_group.TestActor',
            'options': {'return_value': False}}

    @testing.gen_test
    def test_execute_with_no_acts(self):
        # Call the executor and test it out
        actor = group.Sync(
            'Unit Test Action', {'acts': []})

        res = yield actor.execute()
        self.assertEquals(res, True)

    @testing.gen_test
    def test_execute_with_one_act(self):
        # Call the executor and test it out
        actor = group.Sync(
            'Unit Test Action',
            {'acts': [dict(self.actor_return_true)]})

        res = yield actor.execute()
        self.assertEquals(res, True)

    @testing.gen_test
    def test_execute_with_two_acts(self):
        # Call the executor and test it out
        actor = group.Sync(
            'Unit Test Action',
            {'acts': [
                dict(self.actor_return_true),
                dict(self.actor_return_true)]})

        res = yield actor.execute()
        self.assertEquals(res, True)

    @testing.gen_test
    def test_execute_with_two_acts_one_fails(self):
        # Call the executor and test it out
        actor = group.Sync(
            'Unit Test Action',
            {'acts': [
                dict(self.actor_return_true),
                dict(self.actor_return_false)]})

        res = yield actor.execute()
        self.assertEquals(res, False)


class TestAsyncGroupActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestAsyncGroupActor, self).setUp(*args, **kwargs)
        self.actor_return_true = {
            'desc': 'returns true',
            'actor': 'kingpin.actors.test.test_group.TestActor',
            'options': {'return_value': True}}
        self.actor_return_false = {
            'desc': 'returns false',
            'actor': 'kingpin.actors.test.test_group.TestActor',
            'options': {'return_value': False}}

    @testing.gen_test
    def test_execute_with_no_acts(self):
        # Call the executor and test it out
        actor = group.Async(
            'Unit Test Action', {'acts': []})

        res = yield actor.execute()
        self.assertEquals(res, True)

    @testing.gen_test
    def test_execute_with_one_act(self):
        # Call the executor and test it out
        actor = group.Async(
            'Unit Test Action',
            {'acts': [dict(self.actor_return_true)]})

        res = yield actor.execute()
        self.assertEquals(res, True)

    @testing.gen_test
    def test_execute_with_two_acts(self):
        # Call the executor and test it out
        actor = group.Async(
            'Unit Test Action',
            {'acts': [
                dict(self.actor_return_true),
                dict(self.actor_return_true)]})

        res = yield actor.execute()
        self.assertEquals(res, True)

    @testing.gen_test
    def test_execute_with_two_acts_one_fails(self):
        # Call the executor and test it out
        actor = group.Async(
            'Unit Test Action',
            {'acts': [
                dict(self.actor_return_true),
                dict(self.actor_return_false)]})

        res = yield actor.execute()
        self.assertEquals(res, False)
