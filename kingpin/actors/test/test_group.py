import logging

from tornado import gen
from tornado import testing

from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.actors import group


log = logging.getLogger(__name__)


class TestActor(base.BaseActor):

    """Fake Actor for Tests"""

    all_options = {
        'return_value': (object, True, 'What this actor will return')
    }

    @gen.coroutine
    def _execute(self):
        raise gen.Return(self.option('return_value'))


class TestActorRaises(base.BaseActor):

    """Fake Actor for Tests"""

    all_options = {
        'exception': (object, True, 'What this actor will return')
    }

    @gen.coroutine
    def _execute(self):
        raise self.option('exception')


class TestGroupActorBaseClass(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestGroupActorBaseClass, self).setUp(*args, **kwargs)
        self.actor_returns = {
            'desc': 'returns',
            'actor': 'kingpin.actors.test.test_group.TestActor',
            'options': {'return_value': None}}
        self.actor_with_a_problem = {
            'desc': 'Problematic',
            'actor': 'kingpin.actors.test.test_group.TestActor',
            'options': {'problem': 'unit-test-problem'}}
        self.actor_raises_unrecoverable_exception = {
            'desc': 'raises Unrecoverable exception',
            'actor': 'kingpin.actors.test.test_group.TestActorRaises',
            'options': {'exception': exceptions.UnrecoverableActorFailure()}}
        self.actor_raises_recoverable_exception = {
            'desc': 'raises Recoverable exception',
            'actor': 'kingpin.actors.test.test_group.TestActorRaises',
            'options': {'exception': exceptions.RecoverableActorFailure()}}


class TestBaseGroupActor(TestGroupActorBaseClass):

    def test_build_actions(self):
        actor = group.BaseGroupActor(
            'Unit Test Action',
            {'acts': [dict(self.actor_returns),
                      dict(self.actor_returns),
                      dict(self.actor_returns),
                      dict(self.actor_returns)]})
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
        self.assertEquals(None, ret)

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
        self.assertEquals(ret, None)


class TestSyncGroupActor(TestGroupActorBaseClass):

    @testing.gen_test
    def test_run_actions_with_no_acts(self):
        # Call the executor and test it out
        actor = group.Sync(
            'Unit Test Action', {'acts': []})

        res = yield actor._run_actions()
        self.assertEquals(res, None)

    @testing.gen_test
    def test_run_actions_with_one_act(self):
        # Call the executor and test it out
        actor = group.Sync(
            'Unit Test Action',
            {'acts': [dict(self.actor_returns)]})

        res = yield actor._run_actions()
        self.assertEquals(res, None)

    @testing.gen_test
    def test_run_actions_with_two_acts(self):
        # Call the executor and test it out
        actor = group.Sync(
            'Unit Test Action',
            {'acts': [
                dict(self.actor_returns),
                dict(self.actor_returns)]})

        res = yield actor._run_actions()
        self.assertEquals(res, None)

    @testing.gen_test
    def test_run_actions_with_two_acts_one_fails_unrecoverable(self):
        # Call the executor and test it out
        actor = group.Sync(
            'Unit Test Action',
            {'acts': [
                dict(self.actor_returns),
                dict(self.actor_raises_unrecoverable_exception)]})
        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            yield actor._run_actions()

    @testing.gen_test
    def test_run_actions_with_two_acts_one_fails_recoverable(self):
        # Call the executor and test it out
        actor = group.Sync(
            'Unit Test Action',
            {'acts': [
                dict(self.actor_returns),
                dict(self.actor_raises_recoverable_exception)]})
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield actor._run_actions()


class TestASyncGroupActor(TestGroupActorBaseClass):

    @testing.gen_test
    def test_run_actions_with_no_acts(self):
        # Call the executor and test it out
        actor = group.Async(
            'Unit Test Action', {'acts': []})

        res = yield actor._run_actions()
        self.assertEquals(res, None)

    @testing.gen_test
    def test_run_actions_with_one_act(self):
        # Call the executor and test it out
        actor = group.Async(
            'Unit Test Action',
            {'acts': [dict(self.actor_returns)]})

        res = yield actor._run_actions()
        self.assertEquals(res, None)

    @testing.gen_test
    def test_run_actions_with_two_acts(self):
        # Call the executor and test it out
        actor = group.Async(
            'Unit Test Action',
            {'acts': [
                dict(self.actor_returns),
                dict(self.actor_returns)]})

        res = yield actor._run_actions()
        self.assertEquals(res, None)

    @testing.gen_test
    def test_run_actions_with_two_acts_one_fails_unrecoverable(self):
        # Call the executor and test it out
        actor = group.Async(
            'Unit Test Action',
            {'acts': [
                dict(self.actor_returns),
                dict(self.actor_raises_unrecoverable_exception)]})

        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            yield actor._run_actions()
