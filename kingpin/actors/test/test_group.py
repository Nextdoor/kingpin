import logging
import time
import mock

from tornado import gen
from tornado import testing

from kingpin import utils
from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.actors import group


log = logging.getLogger(__name__)


class TestActor(base.BaseActor):

    """Fake Actor for Tests"""

    all_options = {
        'value': (object, True, 'Intermediate value to be used'),
    }

    last_value = None

    @gen.coroutine
    def _execute(self):
        TestActor.last_value = self.option('value')
        raise gen.Return(None)


class TestActorRaises(base.BaseActor):

    """Fake Actor for Tests"""

    all_options = {
        'exception': (object, True, 'What this actor will return')
    }

    @gen.coroutine
    def _execute(self):
        exc = utils.str_to_class(self.option('exception'))
        raise exc


class TestGroupActorBaseClass(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestGroupActorBaseClass, self).setUp(*args, **kwargs)
        TestActor.last_value = None
        self.actor_returns = {
            'desc': 'returns',
            'actor': 'kingpin.actors.test.test_group.TestActor',
            'options': {'value': None}}
        self.actor_with_a_problem = {
            'desc': 'Problematic',
            'actor': 'kingpin.actors.test.test_group.TestActor',
            'options': {'problem': 'unit-test-problem'}}
        self.actor_raises_unrecoverable_exception = {
            'desc': 'raises Unrecoverable exception',
            'actor': 'kingpin.actors.test.test_group.TestActorRaises',
            'options': {
                'exception':
                'kingpin.actors.exceptions.UnrecoverableActorFailure'
            }
        }
        self.actor_raises_recoverable_exception = {
            'desc': 'raises Recoverable exception',
            'actor': 'kingpin.actors.test.test_group.TestActorRaises',
            'options': {
                'exception':
                'kingpin.actors.exceptions.RecoverableActorFailure'
            }
        }


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

    def test_build_actions_with_contexts(self):
        acts = [dict(self.actor_returns),
                dict(self.actor_returns),
                dict(self.actor_returns),
                dict(self.actor_returns)]

        with mock.patch.object(group.BaseGroupActor,
                               '_build_action_group') as action_builder:
            action_builder.return_value = acts
            group.BaseGroupActor(
                'Unit Test Action',
                {'acts': acts,
                 'contexts': [{'TEST': 'TestA'},
                              {'TEST': 'TestB'}]
                 },
                init_context={'PRE': 'CONTEXT'})

        self.assertEquals(2, len(action_builder.mock_calls))
        action_builder.assert_has_calls([
            mock.call(context={'PRE': 'CONTEXT', 'TEST': 'TestA'}),
            mock.call(context={'PRE': 'CONTEXT', 'TEST': 'TestB'})
        ])

    def test_build_action_group(self):
        acts = [dict(self.actor_returns),
                dict(self.actor_returns),
                dict(self.actor_returns),
                dict(self.actor_returns)]

        actor = group.BaseGroupActor('Unit Test Action', {'acts': acts})
        ret = actor._build_action_group({'TEST': 'CONTEXT'})
        self.assertEquals(ret[0]._init_context, {'TEST': 'CONTEXT'})

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
        self.actor_returns['options']['value'] = '123'
        actor = group.Sync(
            'Unit Test Action',
            {'acts': [
                dict(self.actor_raises_unrecoverable_exception),
                dict(self.actor_returns),
            ]})
        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            yield actor._run_actions()

        # If the second actor gets executed this value would be 123.
        self.assertEquals(TestActor.last_value, None)

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


class TestAsyncGroupActor(TestGroupActorBaseClass):

    @testing.gen_test
    def test_get_exc_type_with_only_unrecoverable(self):
        exc_list = [
            exceptions.UnrecoverableActorFailure(),
            exceptions.UnrecoverableActorFailure(),
            exceptions.UnrecoverableActorFailure()
        ]
        actor = group.Async('Unit Test Action', {'acts': []})
        ret = actor._get_exc_type(exc_list)
        self.assertEquals(ret, exceptions.UnrecoverableActorFailure)

    @testing.gen_test
    def test_get_exc_type_with_only_recoverable(self):
        exc_list = [
            exceptions.RecoverableActorFailure(),
            exceptions.RecoverableActorFailure(),
            exceptions.RecoverableActorFailure()
        ]
        actor = group.Async('Unit Test Action', {'acts': []})
        ret = actor._get_exc_type(exc_list)
        self.assertEquals(ret, exceptions.RecoverableActorFailure)

    @testing.gen_test
    def test_get_exc_type_with_both(self):
        exc_list = [
            exceptions.RecoverableActorFailure(),
            exceptions.UnrecoverableActorFailure(),
            exceptions.RecoverableActorFailure()
        ]
        actor = group.Async('Unit Test Action', {'acts': []})
        ret = actor._get_exc_type(exc_list)
        self.assertEquals(ret, exceptions.UnrecoverableActorFailure)

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
    def test_execute_async(self):
        """Make sure this actor starts all processes in parallel!"""
        sleeper = {'actor': 'misc.Sleep',
                   'desc': 'Sleep',
                   'options': {'sleep': 0.1}}
        actor = group.Async('Unit Test Action', {'acts': [
            sleeper, sleeper, sleeper]})

        start = time.time()
        yield actor.execute()
        stop = time.time()
        exe_time = stop - start
        # Parallel execution of sleep should not take 3x as long!
        self.assertTrue(0.1 < exe_time < 0.3)

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
        self.actor_returns['options']['value'] = '123'
        actor = group.Async(
            'Unit Test Action',
            {'acts': [
                dict(self.actor_raises_unrecoverable_exception),
                dict(self.actor_returns),
            ]})

        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            yield actor._run_actions()

        # If the second actor does not get executed this value would be None
        self.assertEquals(TestActor.last_value, '123')

    @testing.gen_test
    def test_run_actions_with_two_acts_one_fails_recoverable(self):
        # Call the executor and test it out
        actor = group.Async(
            'Unit Test Action',
            {'acts': [
                dict(self.actor_returns),
                dict(self.actor_raises_recoverable_exception),
                dict(self.actor_raises_recoverable_exception)]})

        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield actor._run_actions()

    @testing.gen_test
    def test_run_actions_with_two_acts_one_fails_with_both(self):
        # Call the executor and test it out
        actor = group.Async(
            'Unit Test Action',
            {'acts': [
                dict(self.actor_returns),
                dict(self.actor_raises_recoverable_exception),
                dict(self.actor_raises_unrecoverable_exception)]})

        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            yield actor._run_actions()
