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


class TestActorPopulate(base.BaseActor):

    """Fake Actor for Tests"""

    all_options = {
        'object': (list, [], 'A list to append values.'),
        'value': (object, True, 'Add this value to the object two times.'),
    }

    last_value = None

    @gen.coroutine
    def _execute(self):
        self.option('object').append(self.option('value'))
        yield gen.moment
        self.option('object').append(self.option('value'))
        raise gen.Return(None)


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
        self.assertEqual(4, len(ret))

    def test_build_actions_with_bad_context_file(self):
        with self.assertRaises(exceptions.InvalidOptions):
            group.BaseGroupActor(
                'bad context',
                {'acts': [],
                 'contexts': {'file': 'no_such_file',
                              'tokens': {}}
                 }
            )

    def test_build_actions_with_context_file(self):
        acts = [dict(self.actor_returns)]

        with mock.patch.object(group.BaseGroupActor,
                               '_build_action_group') as action_builder:
            action_builder.return_value = acts
            group.BaseGroupActor(
                'ContextFile Actor',
                {
                    'acts': acts,
                    'contexts': {
                        'file': 'examples/test/context.json',
                        'tokens': {'TOKEN_VALUE': 'tadaa'}
                    }
                },
                init_context={'init': 'stuff'})

        self.assertEqual(2, len(action_builder.mock_calls))
        action_builder.assert_has_calls([
            mock.call(context={'init': 'stuff', 'key': 'value1'}),
            mock.call(context={'init': 'stuff', 'key': 'tadaa'})
        ])

    def test_build_actions_with_context_file_str(self):
        acts = [dict(self.actor_returns)]

        with mock.patch.object(group.BaseGroupActor,
                               '_build_action_group') as action_builder:
            action_builder.return_value = acts
            group.BaseGroupActor(
                'ContextFile Actor',
                {'acts': acts,
                 'contexts': 'examples/test/context.json'},
                init_tokens={'TOKEN_VALUE': 'tadaa'},
                init_context={'init': 'stuff'})

        self.assertEqual(2, len(action_builder.mock_calls))
        action_builder.assert_has_calls([
            mock.call(context={'init': 'stuff', 'key': 'value1'}),
            mock.call(context={'init': 'stuff', 'key': 'tadaa'})
        ])

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

        self.assertEqual(2, len(action_builder.mock_calls))
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
        self.assertEqual(ret[0]._init_context, {'TEST': 'CONTEXT'})

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
        self.assertEqual(None, ret)

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
        self.assertEqual(ret, None)


class TestSyncGroupActor(TestGroupActorBaseClass):

    @testing.gen_test
    def test_run_actions_with_no_acts(self):
        # Call the executor and test it out
        actor = group.Sync(
            'Unit Test Action', {'acts': []})

        res = yield actor._run_actions()
        self.assertEqual(res, None)

    @testing.gen_test
    def test_run_actions_with_one_act(self):
        # Call the executor and test it out
        actor = group.Sync(
            'Unit Test Action',
            {'acts': [dict(self.actor_returns)]})

        res = yield actor._run_actions()
        self.assertEqual(res, None)

    @testing.gen_test
    def test_run_actions_with_two_acts(self):
        # Call the executor and test it out
        actor = group.Sync(
            'Unit Test Action',
            {'acts': [
                dict(self.actor_returns),
                dict(self.actor_returns)]})

        res = yield actor._run_actions()
        self.assertEqual(res, None)

    @testing.gen_test
    def test_run_actions_continue_on_dry(self):
        # Call the executor and test it out
        self.actor_returns['options']['value'] = '123'
        actor = group.Sync(
            'Unit Test Action',
            {'acts': [
                dict(self.actor_raises_unrecoverable_exception),
                dict(self.actor_returns),
            ]},
            dry=True)
        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            yield actor._run_actions()

        # Even after the first actor fails, the second one should get executed.
        self.assertEqual(TestActor.last_value, '123')

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
        self.assertEqual(TestActor.last_value, None)

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
        self.assertEqual(ret, exceptions.UnrecoverableActorFailure)

    @testing.gen_test
    def test_get_exc_type_with_only_recoverable(self):
        exc_list = [
            exceptions.RecoverableActorFailure(),
            exceptions.RecoverableActorFailure(),
            exceptions.RecoverableActorFailure()
        ]
        actor = group.Async('Unit Test Action', {'acts': []})
        ret = actor._get_exc_type(exc_list)
        self.assertEqual(ret, exceptions.RecoverableActorFailure)

    @testing.gen_test
    def test_get_exc_type_with_both(self):
        exc_list = [
            exceptions.RecoverableActorFailure(),
            exceptions.UnrecoverableActorFailure(),
            exceptions.RecoverableActorFailure()
        ]
        actor = group.Async('Unit Test Action', {'acts': []})
        ret = actor._get_exc_type(exc_list)
        self.assertEqual(ret, exceptions.UnrecoverableActorFailure)

    @testing.gen_test
    def test_run_actions_with_no_acts(self):
        # Call the executor and test it out
        actor = group.Async(
            'Unit Test Action', {'acts': []})

        res = yield actor._run_actions()
        self.assertEqual(res, None)

    @testing.gen_test
    def test_run_actions_with_one_act(self):
        # Call the executor and test it out
        actor = group.Async(
            'Unit Test Action',
            {'acts': [dict(self.actor_returns)]})

        res = yield actor._run_actions()
        self.assertEqual(res, None)

    @testing.gen_test
    def test_execute_async(self):
        """Make sure this actor starts all processes in parallel!"""
        check_order = []
        actor_1 = {'actor': 'kingpin.actors.test.test_group.TestActorPopulate',
                   'desc': 'test',
                   'options': {
                       'object': ['fake'],
                       'value': 1}}
        actor_2 = {'actor': 'kingpin.actors.test.test_group.TestActorPopulate',
                   'desc': 'test',
                   'options': {
                       'object': ['fake'],
                       'value': 2}}
        actor = group.Async(
            'Unit Test Action',
            {
                'acts': [actor_1, actor_2]
            })

        # The options above were copied by value
        # This test requires same object to be modified so we set it directly
        actor._actions[0]._options['object'] = check_order
        actor._actions[1]._options['object'] = check_order

        yield actor.execute()

        # if the actions above were executed sequentially then the resulting
        # list would be [1,1,2,2] and here we know it's hopping between actors
        self.assertEqual(check_order, [1, 2, 1, 2])

    @testing.gen_test
    def test_execute_concurrent(self):
        sleeper = {'actor': 'misc.Sleep',
                   'desc': 'Sleep',
                   'options': {'sleep': 0.1}}
        actor = group.Async('Unit Test Action', {
            'concurrency': 2,
            'acts': [sleeper, sleeper, sleeper, sleeper]})

        start = time.time()
        yield actor.execute()
        stop = time.time()
        exe_time = stop - start
        self.assertTrue(0.2 < exe_time < 0.4)

    @testing.gen_test
    def test_run_actions_with_two_acts(self):
        # Call the executor and test it out
        actor = group.Async(
            'Unit Test Action',
            {'acts': [
                dict(self.actor_returns),
                dict(self.actor_returns)]})

        res = yield actor._run_actions()
        self.assertEqual(res, None)

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
        self.assertEqual(TestActor.last_value, '123')

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
