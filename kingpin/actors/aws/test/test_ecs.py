import logging

from tornado import gen
from tornado import testing
import mock

from kingpin import utils
from kingpin.actors import exceptions
from kingpin.actors.aws import ecs as ecs_actor
from kingpin.actors.test import helper

log = logging.getLogger(__name__)


class TestHandleFailures(testing.AsyncTestCase):
    def setUp(self):
        super(TestHandleFailures, self).setUp()
        reload(ecs_actor)
        self.actor = ecs_actor.ECSBaseActor()

    @testing.gen_test
    def test_no_failures(self):
        failures = []
        self.actor._handle_failures(failures)

    @testing.gen_test
    def test_one_failure(self):
        failures = ['failure reason']
        with self.assertRaises(exceptions.RecoverableActorFailure):
            self.actor._handle_failures(failures)

    @testing.gen_test
    def test_multiple_failures(self):
        failures = ['failure reason1', 'failure reason2']
        with self.assertRaises(exceptions.RecoverableActorFailure):
            self.actor._handle_failures(failures)


class TestTaskDefinitionSchemaValidation(testing.AsyncTestCase):
    def setUp(self):
        super(TestTaskDefinitionSchemaValidation, self).setUp()
        reload(ecs_actor)

    @testing.gen_test
    def test_schema_ok_minimal(self):
        self._test(
            {
                'family': '',
                'containerDefinitions': [],
            })

    @testing.gen_test
    def test_schema_ok_complex(self):
        self._test(
            {
                'family': 'family-name',
                'containerDefinitions': [
                    {
                        'name': 'test',
                        'image': 'test-image',
                        'cpu': 1,
                        'memory': 2,
                        'links': ['a'],
                        'portMappings': [{
                            'containerPort': 8000,
                            'hostPort': 80,
                            'protocol': 'tcp'
                        }],
                        'essential': True,
                        'environment': [
                            {'name': 'var1', 'value': 'value1'},
                            {'name': 'var2', 'value': 'value2'}
                        ],
                    },
                    {
                        'name': 'a',
                        'image': 'a-image'
                    }
                ],
                'volumes': [{
                    'name': 'volume',
                    'host': {
                        'sourcePath': '/mountme'
                    }
                }]
            })

    @testing.gen_test
    def test_schema_fail_extra(self):
        with self.assertRaises(exceptions.InvalidOptions):
            self._test(
                {
                    'other stuff': 0,
                    'family': 'name',
                    'containerDefinitions': [],
                    'extra': 'read all about it'
                })

    @testing.gen_test
    def test_schema_fail_empty(self):
        with self.assertRaises(exceptions.InvalidOptions):
            self._test('')

    @testing.gen_test
    def test_schema_fail_none(self):
        with self.assertRaises(exceptions.InvalidOptions):
            self._test(None)

    def _test(self, task_definition):
        with mock.patch('kingpin.utils.convert_script_to_dict',
                        return_value=task_definition) as utils_convert_mock:
            file = 'file'
            parameters = {'token': 'value'}
            ecs_actor._load_task_definition(file, parameters)
            utils_convert_mock.assert_called_with(file, parameters)


class TestRegisterTask(testing.AsyncTestCase):
    def setUp(self):
        super(TestRegisterTask, self).setUp()
        reload(ecs_actor)

        with mock.patch('kingpin.actors.aws.ecs._load_task_definition'):
            self.actor = ecs_actor.RunTask(
                options={
                    'region': '',
                    'cluster': '',
                    'task_definition': ''
                })
        self.actor.ecs_conn = mock.Mock()

    @testing.gen_test
    def test_ok_minimal(self):
        task_definition = {
            'family': '',
            'containerDefinitions': [],
        }
        response_task_definition = task_definition.copy()
        response_task_definition.update({'revision': 100})
        self.actor.ecs_conn.register_task_definition.return_value = {
            'taskDefinition': response_task_definition
        }
        family, revision = yield self.actor._register_task(task_definition)
        self.actor.ecs_conn.register_task_definition.assert_called_with(
            **task_definition)
        self.assertEqual(family, task_definition['family'])
        self.assertEqual(revision, 100)

    @testing.gen_test
    def test_dry_mode(self):
        self.actor._dry = True
        task_definition = {
            'family': 'name',
            'containerDefinitions': []
        }
        family, revision = yield self.actor._register_task(task_definition)
        self.assertEqual(family, task_definition['family'])
        self.assertEqual(revision, 1)


class TestRunTask(testing.AsyncTestCase):
    def setUp(self):
        super(TestRunTask, self).setUp()
        reload(ecs_actor)

        with mock.patch('kingpin.actors.aws.ecs._load_task_definition'):
            self.actor = ecs_actor.RunTask(
                options={
                    'region': '',
                    'cluster': '',
                    'task_definition': ''
                })
        self.actor.ecs_conn = mock.Mock()
        self.actor._handle_failures = mock.Mock()

    def test_ok_minimal(self):
        self._test(
            family='family',
            revision=1,
            return_value={
                'failures': [],
                'tasks': [
                    {'taskArn': '1'}
                ]
            })

    def test_ok_complex(self):
        self.actor._options['cluster'] = 'cluster'
        self.actor._options['count'] = 5
        self._test(
            family='family',
            revision=100,
            return_value={
                'failures': [],
                'tasks': [
                    {'taskArn': '1'},
                    {'taskArn': '2'},
                    {'taskArn': '3'},
                ]
            })

    @testing.gen_test
    def _test(self, family, revision, return_value):
        self.actor.ecs_conn.run_task.return_value = return_value
        tasks = yield self.actor._run_task(
            family=family,
            revision=revision)
        self.actor.ecs_conn.run_task.assert_called_with(
            cluster=self.actor.option('cluster'),
            taskDefinition='{0}:{1}'.format(family, revision),
            count=self.actor.option('count')
        )
        self.actor._handle_failures.assert_called_with(
            return_value['failures'])
        expected_tasks = [t['taskArn'] for t in return_value['tasks']]
        self.assertEqual(tasks, expected_tasks)

    @testing.gen_test
    def test_with_failures(self):
        failures = ['failure one', 'failure two']
        self.actor.ecs_conn.run_task.return_value = {
            'failures': failures
        }
        exception = exceptions.RecoverableActorFailure()
        self.actor._handle_failures.side_effect = exception
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._run_task(
                family='',
                revision=0)

    @testing.gen_test
    def test_dry(self):
        self.actor._dry = True
        yield self.actor._run_task(
            family='',
            revision=0)
        self.assertEqual(self.actor.ecs_conn.run_task.call_count, 0)


class TestWaitForTasks(testing.AsyncTestCase):
    def setUp(self):
        super(TestWaitForTasks, self).setUp()
        reload(ecs_actor)

        with mock.patch('kingpin.actors.aws.ecs._load_task_definition'):
            self.actor = ecs_actor.RunTask(
                options={
                    'region': '',
                    'cluster': '',
                    'task_definition': ''
                })
        gen.sleep = helper.mock_tornado()

    def tearDown(self):
        reload(gen)

    @testing.gen_test
    def test_return_for_empty(self):
        self.actor._tasks_done = helper.mock_tornado(True)
        yield self.actor._wait_for_tasks([])
        self.assertEqual(self.actor._tasks_done._call_count, 0)
        self.assertEqual(gen.sleep._call_count, 0)

    @testing.gen_test
    def test_return_for_none(self):
        self.actor._tasks_done = helper.mock_tornado(True)
        yield self.actor._wait_for_tasks(None)
        self.assertEqual(self.actor._tasks_done._call_count, 0)
        self.assertEqual(gen.sleep._call_count, 0)

    @testing.gen_test
    def test_instant_success(self):
        self.actor._tasks_done = helper.mock_tornado(True)
        yield self.actor._wait_for_tasks(['0'])
        self.assertEqual(self.actor._tasks_done._call_count, 1)
        self.assertEqual(gen.sleep._call_count, 0)

    @testing.gen_test
    def test_two_failures_before_success(self):
        @gen.coroutine
        def fail_twice(*args):
            fail_twice.call_count += 1
            return fail_twice.call_count > 2

        fail_twice.call_count = 0

        self.actor._tasks_done = fail_twice
        yield self.actor._wait_for_tasks(['0'])
        self.assertEqual(fail_twice.call_count, 3)
        self.assertEqual(gen.sleep._call_count, 2)


class TestTasksDone(testing.AsyncTestCase):
    def setUp(self):
        super(TestTasksDone, self).setUp()
        reload(ecs_actor)

        with mock.patch('kingpin.actors.aws.ecs._load_task_definition'):
            self.actor = ecs_actor.RunTask(options={
                'region': '',
                'cluster': '',
                'task_definition': ''
            })
        self.actor.ecs_conn = mock.Mock()
        self.actor.ecs_conn.describe_tasks.return_value = {
            'failures': [],
            'tasks': []
        }
        self.actor._handle_failures = mock.Mock()
        ecs_actor._get_containers_from_tasks = mock.Mock()

    def tearDown(self):
        reload(ecs_actor)

    @testing.gen_test
    def test_one_stopped_container(self):
        tasks = ['1']
        ecs_actor._get_containers_from_tasks.return_value = [
            {
                'taskArn': '1',
                'lastStatus': 'STOPPED',
                'exitCode': 0
            }
        ]
        result = yield self.actor._tasks_done(tasks)
        self.actor.ecs_conn.describe_tasks.assert_called_with(
            cluster=self.actor.option('cluster'),
            tasks=tasks)
        self.assertTrue(result)

    @testing.gen_test
    def test_two_stopped_container(self):
        tasks = ['1', '2']
        ecs_actor._get_containers_from_tasks.return_value = [
            {
                'taskArn': '1',
                'lastStatus': 'STOPPED',
                'exitCode': 0
            },
            {
                'taskArn': '2',
                'lastStatus': 'STOPPED',
                'exitCode': 0
            }
        ]
        result = yield self.actor._tasks_done(tasks)
        self.actor.ecs_conn.describe_tasks.assert_called_with(
            cluster=self.actor.option('cluster'),
            tasks=tasks)
        self.assertTrue(result)

    @testing.gen_test
    def test_one_failed_container(self):
        tasks = ['1']
        ecs_actor._get_containers_from_tasks.return_value = [
            {
                'taskArn': '1',
                'lastStatus': 'STOPPED',
                'exitCode': 100
            }
        ]
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._tasks_done(tasks)
        self.actor.ecs_conn.describe_tasks.assert_called_with(
            cluster=self.actor.option('cluster'),
            tasks=tasks)

    @testing.gen_test
    def test_still_running(self):
        tasks = ['1']
        ecs_actor._get_containers_from_tasks.return_value = [
            {
                'taskArn': '1',
                'lastStatus': 'RUNNING'
            }
        ]
        result = yield self.actor._tasks_done(tasks)
        self.actor.ecs_conn.describe_tasks.assert_called_with(
            cluster=self.actor.option('cluster'),
            tasks=tasks)
        self.assertFalse(result)

    @testing.gen_test
    def test_some_still_running(self):
        tasks = ['1']
        ecs_actor._get_containers_from_tasks.return_value = [
            {
                'taskArn': '1',
                'lastStatus': 'RUNNING'
            },
            {
                'taskArn': '2',
                'lastStatus': 'STOPPED',
                'exitCode': 0
            }
        ]
        result = yield self.actor._tasks_done(tasks)
        self.actor.ecs_conn.describe_tasks.assert_called_with(
            cluster=self.actor.option('cluster'),
            tasks=tasks)
        self.assertFalse(result)

    @testing.gen_test
    def test_some_pass_some_fail(self):
        tasks = ['1', '2']
        ecs_actor._get_containers_from_tasks.return_value = [
            {
                'taskArn': '1',
                'lastStatus': 'STOPPED',
                'exitCode': 0
            },
            {
                'taskArn': '2',
                'lastStatus': 'STOPPED',
                'exitCode': 1
            }
        ]
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._tasks_done(tasks)
        self.actor.ecs_conn.describe_tasks.assert_called_with(
            cluster=self.actor.option('cluster'),
            tasks=tasks)

    @testing.gen_test
    def test_fail_without_exit(self):
        tasks = ['1']
        ecs_actor._get_containers_from_tasks.return_value = [
            {
                'taskArn': '1',
                'lastStatus': 'STOPPED'
            }
        ]
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._tasks_done(tasks)
        self.actor.ecs_conn.describe_tasks.assert_called_with(
            cluster=self.actor.option('cluster'),
            tasks=tasks)

    @testing.gen_test
    def test_some_pass_some_fail_reverse(self):
        tasks = ['1', '2']
        ecs_actor._get_containers_from_tasks.return_value = [
            {
                'taskArn': '1',
                'lastStatus': 'STOPPED',
                'exitCode': 1
            },
            {
                'taskArn': '2',
                'lastStatus': 'STOPPED',
                'exitCode': 0
            }
        ]
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._tasks_done(tasks)
        self.actor.ecs_conn.describe_tasks.assert_called_with(
            cluster=self.actor.option('cluster'),
            tasks=tasks)

    @testing.gen_test
    def test_failure_in_describe(self):
        tasks = ['1']
        failures = ['failure one', 'failure two']
        self.actor.ecs_conn.describe_tasks.return_value = {
            'failures': failures,
            'tasks': []
        }
        exception = exceptions.RecoverableActorFailure()
        self.actor._handle_failures.side_effect = exception
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._tasks_done(tasks)
        self.actor._handle_failures.assert_called_with(failures)


class TestExecute(testing.AsyncTestCase):
    def setUp(self):
        super(TestExecute, self).setUp()
        reload(utils)
        reload(ecs_actor)

        with mock.patch('kingpin.actors.aws.ecs._load_task_definition'):
            self.actor = ecs_actor.RunTask(
                options={
                    'region': '',
                    'cluster': '',
                    'task_definition': ''
                })
        self.actor.task_definition = 'task definition'
        self.actor._register_task = helper.mock_tornado(('family', 1))
        self.actor._run_task = helper.mock_tornado([1, 2])
        self.actor._wait_for_tasks = helper.mock_tornado()

    def tearDown(self):
        reload(utils)

    @testing.gen_test
    def test_ok(self):
        yield self.actor._execute()
        self.assertEqual(self.actor._register_task._call_count, 1)
        self.assertEqual(self.actor._run_task._call_count, 1)
        self.assertEqual(self.actor._wait_for_tasks._call_count, 1)

    @testing.gen_test
    def test_without_wait(self):
        self.actor._options['wait'] = False
        yield self.actor._execute()
        self.assertEqual(self.actor._register_task._call_count, 1)
        self.assertEqual(self.actor._run_task._call_count, 1)
        self.assertEqual(self.actor._wait_for_tasks._call_count, 0)


class TestGetContainersFromTasks(testing.AsyncTestCase):
    def setUp(self):
        super(TestGetContainersFromTasks, self).setUp()

    @testing.gen_test
    def test_empty(self):
        result = ecs_actor._get_containers_from_tasks([])
        self.assertEqual(result, [])

    @testing.gen_test
    def test_one(self):
        result = ecs_actor._get_containers_from_tasks([{
            'containers': [1]
        }])
        self.assertEqual(result, [1])

    @testing.gen_test
    def test_two_in_one_container(self):
        result = ecs_actor._get_containers_from_tasks([{
            'containers': [1, 2]
        }])
        self.assertEqual(result, [1, 2])

    @testing.gen_test
    def test_two_in_two_containers(self):
        result = ecs_actor._get_containers_from_tasks([
            {
                'containers': [1, 2]
            },
            {
                'containers': [3, 4]
            }
        ])
        self.assertEqual(result, [1, 2, 3, 4])

    @testing.gen_test
    def test_objects(self):
        result = ecs_actor._get_containers_from_tasks([
            {
                'containers': [{'a', 'b'}, {'a': 1}]
            },
            {
                'containers': [1, 2]
            }
        ])
        self.assertEqual(result, [{'a', 'b'}, {'a': 1}, 1, 2])
