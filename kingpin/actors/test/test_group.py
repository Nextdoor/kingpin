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
        self.actor_with_a_problem = {
            'desc': 'Problematic',
            'actor': 'kingpin.actors.test.test_group.TestActor',
            'options': {'problem': 'unit-test-problem'}}

    def test_build_actions(self):
        actor = group.BaseGroupActor(
            'Unit Test Action',
            {'acts': [dict(self.actor_return_true),
                      dict(self.actor_return_true),
                      dict(self.actor_return_true),
                      dict(self.actor_return_true)]})
        ret = actor._build_actions()
        self.assertEquals(4, len(ret))

    @testing.gen_test
    def test_execute_success(self):
        actor = group.BaseGroupActor('Unit Test Action', {'acts': []})

        # Mock out the _run_actions method and make sure it just returns two
        # True results.
        @gen.coroutine
        def run_actions_true(*args, **kwargs):
            raise gen.Return([True, True])
        actor._run_actions = run_actions_true

        ret = yield actor._execute()
        self.assertEquals(True, ret)

    @testing.gen_test
    def test_execute_failure(self):
        actor = group.BaseGroupActor('Unit Test Action', {'acts': []})

        # Mock out the _run_actions method and make sure it just returns one
        # True and one False results.
        @gen.coroutine
        def run_actions_true(*args, **kwargs):
            raise gen.Return([True, False])
        actor._run_actions = run_actions_true

        ret = yield actor._execute()
        self.assertEquals(False, ret)


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
    def test_run_actions_with_no_acts(self):
        # Call the executor and test it out
        actor = group.Sync(
            'Unit Test Action', {'acts': []})

        res = yield actor._run_actions()
        self.assertEquals(res, [])

    @testing.gen_test
    def test_run_actions_with_one_act(self):
        # Call the executor and test it out
        actor = group.Sync(
            'Unit Test Action',
            {'acts': [dict(self.actor_return_true)]})

        res = yield actor._run_actions()
        self.assertEquals(res, [True])

    @testing.gen_test
    def test_run_actions_with_two_acts(self):
        # Call the executor and test it out
        actor = group.Sync(
            'Unit Test Action',
            {'acts': [
                dict(self.actor_return_true),
                dict(self.actor_return_true)]})

        res = yield actor._run_actions()
        self.assertEquals(res, [True, True])

    @testing.gen_test
    def test_run_actions_with_two_acts_one_fails(self):
        # Call the executor and test it out
        actor = group.Sync(
            'Unit Test Action',
            {'acts': [
                dict(self.actor_return_true),
                dict(self.actor_return_false)]})

        res = yield actor._run_actions()
        self.assertEquals(res, [True, False])


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
    def test_run_actions_with_no_acts(self):
        # Call the executor and test it out
        actor = group.Async(
            'Unit Test Action', {'acts': []})

        res = yield actor._run_actions()
        self.assertEquals(res, [])

    @testing.gen_test
    def test_run_actions_with_one_act(self):
        # Call the executor and test it out
        actor = group.Async(
            'Unit Test Action',
            {'acts': [dict(self.actor_return_true)]})

        res = yield actor._run_actions()
        self.assertEquals(res, [True])

    @testing.gen_test
    def test_run_actions_with_two_acts(self):
        # Call the executor and test it out
        actor = group.Async(
            'Unit Test Action',
            {'acts': [
                dict(self.actor_return_true),
                dict(self.actor_return_true)]})

        res = yield actor._run_actions()
        self.assertEquals(res, [True, True])

    @testing.gen_test
    def test_run_actions_with_two_acts_one_fails(self):
        # Call the executor and test it out
        actor = group.Async(
            'Unit Test Action',
            {'acts': [
                dict(self.actor_return_true),
                dict(self.actor_return_false)]})

        res = yield actor._run_actions()
        self.assertEquals(res, [True, False])
