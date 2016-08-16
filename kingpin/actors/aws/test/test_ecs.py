import datetime
import logging
import mock

from boto3.exceptions import Boto3Error
from tornado import gen
from tornado import testing

from kingpin.actors import exceptions
from kingpin.actors.aws import ecs as ecs_actor
from kingpin.actors.aws import settings
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
    def test_ignored_failure(self):
        ignore = 'ignore'
        failures = [{'reason': ignore}]
        self.actor._handle_failures(failures, ignore)

    @testing.gen_test
    def test_one_failure(self):
        failures = [{'reason': 1}]
        with self.assertRaises(exceptions.RecoverableActorFailure):
            self.actor._handle_failures(failures)

    @testing.gen_test
    def test_multiple_failures(self):
        failures = [{'reason': 1}, {'reason': 2}]
        with self.assertRaises(exceptions.RecoverableActorFailure):
            self.actor._handle_failures(failures)


class TestLoadTaskDefinition(testing.AsyncTestCase):
    def setUp(self):
        super(TestLoadTaskDefinition, self).setUp()
        reload(ecs_actor)
        self.actor = ecs_actor.ECSBaseActor()

    @testing.gen_test
    def test_schema_ok_minimal(self):
        self._test({
            'family': '',
            'containerDefinitions': []})

    @testing.gen_test
    def test_schema_ok_complex(self):
        self._test({
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
    def test_schema_ok_extra(self):
        self._test({
            'other stuff': 0,
            'family': 'name',
            'containerDefinitions': [],
            'extra': 'read all about it'})

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
            task_definition_file = 'file'
            tokens = {'token': 'value'}
            self.actor._load_task_definition(task_definition_file, tokens)
            utils_convert_mock.assert_called_with(task_definition_file, tokens)


class TestLoadServiceDefinition(testing.AsyncTestCase):
    def setUp(self):
        super(TestLoadServiceDefinition, self).setUp()
        reload(ecs_actor)
        self.actor = ecs_actor.ECSBaseActor()

    @testing.gen_test
    def test_schema_ok_minimal(self):
        self._test({})

    @testing.gen_test
    def test_schema_ok_complex(self):
        self._test({
            'loadBalancers': [
                {
                    'loadBalancerName': 'elb',
                    'containerPort': 8000
                }
            ],
            'deploymentConfiguration': {
                'maximumPercent': 100,
                'minimumHealthyPercent': 2
            }
        })

    @testing.gen_test
    def test_schema_ok_extra(self):
        self._test({
            'other stuff': 0,
            'extra': 'read all about it'})

    @testing.gen_test
    def test_schema_fail_empty(self):
        with self.assertRaises(exceptions.InvalidOptions):
            self._test('')

    @testing.gen_test
    def test_schema_fail_none(self):
        with self.assertRaises(exceptions.InvalidOptions):
            self._test(None)

    @testing.gen_test
    def test_default(self):
        result = self.actor._load_service_definition(None, {})
        self.assertEqual(result['loadBalancers'], [])
        self.assertEqual(result['deploymentConfiguration'], {})

        result = self.actor._load_service_definition('', {})
        self.assertEqual(result['loadBalancers'], [])
        self.assertEqual(result['deploymentConfiguration'], {})

    def _test(self, service_definition):
        with mock.patch('kingpin.utils.convert_script_to_dict',
                        return_value=service_definition) as utils_convert_mock:
            service_definition_file = 'file'
            tokens = {'token': 'value'}
            self.actor._load_service_definition(service_definition_file,
                                                tokens)
            utils_convert_mock.assert_called_with(
                service_definition_file, tokens)


class TestRegisterTask(testing.AsyncTestCase):
    def setUp(self):
        super(TestRegisterTask, self).setUp()
        reload(ecs_actor)

        self.actor = _mock_task_actor()
        self.actor.ecs_conn = mock.Mock()

    @testing.gen_test
    def test_ok_minimal(self):
        task_definition = {
            'family': '',
            'containerDefinitions': []}
        response_task_definition = task_definition.copy()
        response_task_definition.update({'revision': 100})
        self.actor.ecs_conn.register_task_definition.return_value = {
            'taskDefinition': response_task_definition
        }
        registered_task = yield \
            self.actor._register_task(task_definition)
        family, revision, task_definition_name = registered_task
        self.actor.ecs_conn.register_task_definition.assert_called_with(
            **task_definition)
        self.assertEqual(family, task_definition['family'])
        self.assertEqual(revision, 100)

    @testing.gen_test
    def test_dry(self):
        self.actor._dry = True
        task_definition = {
            'family': 'name',
            'containerDefinitions': []}
        registered_task = yield \
            self.actor._register_task(task_definition)
        self.assertEqual(registered_task, None)

    @testing.gen_test
    def test_internal_exception(self):
        self.actor.ecs_conn.register_task_definition.side_effect = Boto3Error
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._register_task({
                'family': 'name',
                'containerDefinitions': []})


class TestTaskRun(testing.AsyncTestCase):
    def setUp(self):
        super(TestTaskRun, self).setUp()
        self.actor = _mock_task_actor()
        self.actor.ecs_conn = mock.Mock()
        self.actor._handle_failures = mock.Mock()
        gen.sleep = helper.mock_tornado()

    def tearDown(self):
        reload(gen)

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
        def fail_twice(*args, **kwargs):
            fail_twice.call_count += 1
            if fail_twice.call_count > 2:
                return {'tasks': return_value['tasks'], 'failures': []}
            return {'failures': ['failure']}

        fail_twice.call_count = 0

        self.actor.ecs_conn.run_task = fail_twice

        tasks = yield self.actor._run_task('{}:{}'.format(family, revision))

        self.assertEqual(fail_twice.call_count, 3)

        expected_tasks = [t['taskArn'] for t in return_value['tasks']]
        self.assertEqual(tasks, expected_tasks)

    @testing.gen_test
    def test_with_failures(self):
        failures = ['failure one', 'failure two']
        self.actor.ecs_conn.run_task.return_value = {
            'failures': failures}
        exception = exceptions.RecoverableActorFailure()
        self.actor._handle_failures.side_effect = exception
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._run_task('')

    @testing.gen_test
    def test_dry(self):
        self.actor._dry = True
        yield self.actor._run_task('')
        self.assertEqual(self.actor.ecs_conn.run_task.call_count, 0)


class TestTaskWait(testing.AsyncTestCase):
    def setUp(self):
        super(TestTaskWait, self).setUp()

        self.actor = _mock_task_actor()
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


class TestTaskDone(testing.AsyncTestCase):
    def setUp(self):
        super(TestTaskDone, self).setUp()
        reload(ecs_actor)

        self.actor = _mock_task_actor()
        self.actor.ecs_conn = mock.Mock()
        self.actor.ecs_conn.describe_tasks.return_value = {
            'failures': [],
            'tasks': []}
        self.actor._handle_failures = mock.Mock()
        self.actor._get_containers_from_tasks = mock.Mock()

    def tearDown(self):
        reload(ecs_actor)

    @testing.gen_test
    def test_one_stopped_container(self):
        tasks = ['1']
        self.actor._get_containers_from_tasks.return_value = [{
            'taskArn': '1',
            'lastStatus': 'STOPPED',
            'exitCode': 0
        }]
        result = yield self.actor._tasks_done(tasks)
        self.actor.ecs_conn.describe_tasks.assert_called_with(
            cluster=self.actor.option('cluster'),
            tasks=tasks)
        self.assertTrue(result)

    @testing.gen_test
    def test_two_stopped_container(self):
        tasks = ['1', '2']
        self.actor._get_containers_from_tasks.return_value = [
            {
                'taskArn': '1',
                'lastStatus': 'STOPPED',
                'exitCode': 0
            },
            {
                'taskArn': '2',
                'lastStatus': 'STOPPED',
                'exitCode': 0
            }]
        result = yield self.actor._tasks_done(tasks)
        self.actor.ecs_conn.describe_tasks.assert_called_with(
            cluster=self.actor.option('cluster'),
            tasks=tasks)
        self.assertTrue(result)

    @testing.gen_test
    def test_one_failed_container(self):
        tasks = ['1']
        self.actor._get_containers_from_tasks.return_value = [{
            'taskArn': '1',
            'lastStatus': 'STOPPED',
            'exitCode': 100
        }]
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._tasks_done(tasks)
        self.actor.ecs_conn.describe_tasks.assert_called_with(
            cluster=self.actor.option('cluster'),
            tasks=tasks)

    @testing.gen_test
    def test_still_running(self):
        tasks = ['1']
        self.actor._get_containers_from_tasks.return_value = [{
            'taskArn': '1',
            'lastStatus': 'RUNNING'
        }]
        result = yield self.actor._tasks_done(tasks)
        self.actor.ecs_conn.describe_tasks.assert_called_with(
            cluster=self.actor.option('cluster'),
            tasks=tasks)
        self.assertFalse(result)

    @testing.gen_test
    def test_some_still_running(self):
        tasks = ['1']
        self.actor._get_containers_from_tasks.return_value = [
            {
                'taskArn': '1',
                'lastStatus': 'RUNNING'
            },
            {
                'taskArn': '2',
                'lastStatus': 'STOPPED',
                'exitCode': 0
            }]
        result = yield self.actor._tasks_done(tasks)
        self.actor.ecs_conn.describe_tasks.assert_called_with(
            cluster=self.actor.option('cluster'),
            tasks=tasks)
        self.assertFalse(result)

    @testing.gen_test
    def test_some_pass_some_fail(self):
        tasks = ['1', '2']
        self.actor._get_containers_from_tasks.return_value = [
            {
                'taskArn': '1',
                'lastStatus': 'STOPPED',
                'exitCode': 0
            },
            {
                'taskArn': '2',
                'lastStatus': 'STOPPED',
                'exitCode': 1
            }]
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._tasks_done(tasks)
        self.actor.ecs_conn.describe_tasks.assert_called_with(
            cluster=self.actor.option('cluster'),
            tasks=tasks)

    @testing.gen_test
    def test_fail_without_exit(self):
        tasks = ['1']
        self.actor._get_containers_from_tasks.return_value = [{
            'taskArn': '1',
            'lastStatus': 'STOPPED',
            'reason': 'fail reason'}]
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._tasks_done(tasks)
        self.actor.ecs_conn.describe_tasks.assert_called_with(
            cluster=self.actor.option('cluster'),
            tasks=tasks)

    @testing.gen_test
    def test_some_pass_some_fail_reverse(self):
        tasks = ['1', '2']
        self.actor._get_containers_from_tasks.return_value = [
            {
                'taskArn': '1',
                'lastStatus': 'STOPPED',
                'exitCode': 1
            },
            {
                'taskArn': '2',
                'lastStatus': 'STOPPED',
                'exitCode': 0
            }]
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


class TestTaskExecute(testing.AsyncTestCase):
    def setUp(self):
        super(TestTaskExecute, self).setUp()

        self.actor = _mock_task_actor()
        self.actor._register_task = helper.mock_tornado(('family', 1,
                                                         'family:1'))
        self.actor._run_task = helper.mock_tornado([1, 2])
        self.actor._wait_for_tasks = helper.mock_tornado()

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

    @testing.gen_test
    def test_dry(self):
        self.actor._dry = True
        yield self.actor._execute()
        self.assertEqual(self.actor._register_task._call_count, 1)
        self.assertEqual(self.actor._run_task._call_count, 1)
        self.assertEqual(self.actor._wait_for_tasks._call_count, 1)


class TestGetServiceName(testing.AsyncTestCase):
    def setUp(self):
        super(TestGetServiceName, self).setUp()
        self.actor = _mock_service_actor()

    @testing.gen_test
    def testServiceNameSet(self):
        service_name = 'service_name'
        family = 'family'
        self.actor._options['service_name'] = service_name
        result = self.actor._get_service_name(family)
        self.assertEqual(result, service_name)

    @testing.gen_test
    def testServiceNameNotSet(self):
        family = 'family'
        self.assertTrue(self.actor.option('service_name') is None)
        result = self.actor._get_service_name(family)
        self.assertEqual(result, family)


class TestDescribeService(testing.AsyncTestCase):
    def setUp(self):
        super(TestDescribeService, self).setUp()
        self.actor = _mock_service_actor()
        self.actor.ecs_conn = mock.Mock()
        self.actor._handle_failures = mock.Mock()

    @testing.gen_test
    def test_describe_call(self):
        self.actor.ecs_conn.describe_services.return_value = {
            'failures': [],
            'services': []}

        service_name1 = 'service_name1'
        yield self.actor._describe_service(service_name1)
        self.actor.ecs_conn.describe_services.assert_called_with(
            cluster=self.actor.option('cluster'),
            services=[service_name1])

        service_name2 = 'service_name2'
        self.actor._options['cluster'] = 'cluster'
        yield self.actor._describe_service(service_name2)
        self.actor.ecs_conn.describe_services.assert_called_with(
            cluster=self.actor.option('cluster'),
            services=[service_name2])

    @testing.gen_test
    def test_failure_call(self):
        service_name = 'service_name'

        failures = []
        self.actor.ecs_conn.describe_services.return_value = {
            'failures': failures,
            'services': []}

        yield self.actor._describe_service(service_name)
        self.actor._handle_failures.assert_called_with(
            failures,
            ecs_actor.ECSBaseActor.FAILURE_MISSING)

        failures = ['1', '2']
        self.actor.ecs_conn.describe_services.return_value = {
            'failures': failures,
            'services': []}

        yield self.actor._describe_service(service_name)
        self.actor._handle_failures.assert_called_with(
            failures,
            ecs_actor.ECSBaseActor.FAILURE_MISSING)

    @testing.gen_test
    def test_no_service(self):
        self.actor.ecs_conn.describe_services.return_value = {
            'failures': [],
            'services': []}

        service_name = 'service_name'
        result = yield self.actor._describe_service(service_name)
        self.assertEqual(result, None)

    @testing.gen_test
    def test_one_service(self):
        service_name = 'service_name'
        self.actor.ecs_conn.describe_services.return_value = {
            'failures': [],
            'services': [service_name]}

        result = yield self.actor._describe_service(service_name)
        self.assertEqual(result, service_name)

    @testing.gen_test
    def test_multiple_services_only_one(self):
        service_name1 = 'service_name1'
        service_name2 = 'service_name2'
        self.actor.ecs_conn.describe_services.return_value = {
            'failures': [],
            'services': [service_name1, service_name2]}

        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._describe_service(service_name1)


class TestCreateService(testing.AsyncTestCase):
    def setUp(self):
        super(TestCreateService, self).setUp()
        self.actor = _mock_service_actor()
        self.actor.ecs_conn = mock.Mock()

    @testing.gen_test
    def test_call(self):
        service_name = 'service_name'
        task_definition_name = 'family:1'
        token = 'token'

        yield self.actor._create_service(
            service_name=service_name,
            task_definition_name=task_definition_name,
            client_token=token)
        call_args = self.actor.ecs_conn.create_service.call_args
        expected = ({
                        'clientToken': token,
                        'cluster': self.actor.option('cluster'),
                        'serviceName': service_name,
                        'taskDefinition': task_definition_name,
                        'desiredCount': self.actor.option('count'),
                    },)
        self.assertTrue(call_args == expected)

        task_definition_name = 'family:2'
        self.actor._options['cluster'] = 'cluster'
        self.actor._options['count'] = 5
        extra = {
            'test1': 'a',
            'test2': 'b'
        }
        self.actor.service_definition = extra
        yield self.actor._create_service(
            service_name=service_name,
            task_definition_name=task_definition_name,
            client_token=token)
        expected = ({
                        'clientToken': token,
                        'cluster': self.actor.option('cluster'),
                        'serviceName': service_name,
                        'taskDefinition': task_definition_name,
                        'desiredCount': self.actor.option('count'),
                    },)
        expected[0].update(extra)
        call_args = self.actor.ecs_conn.create_service.call_args
        self.assertTrue(call_args == expected)

    @testing.gen_test
    def test_dry(self):
        self.actor._dry = True
        yield self.actor._create_service(
            service_name='',
            family='',
            revision='',
            client_token='')
        self.assertFalse(self.actor.ecs_conn.create_service.called)

    @testing.gen_test
    def test_internal_exception(self):
        self.actor.ecs_conn.create_service.side_effect = Boto3Error
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._create_service(
                service_name='service_name',
                task_definition_name='family:1',
                client_token='token')


class TestDeleteService(testing.AsyncTestCase):
    def setUp(self):
        super(TestDeleteService, self).setUp()
        self.actor = _mock_service_actor()
        self.actor.ecs_conn = mock.Mock()

    @testing.gen_test
    def test_call(self):
        self.actor._update_service = helper.mock_tornado()
        self.actor._wait_for_deployment = helper.mock_tornado()
        yield self.actor._delete_service('sertest', 'tasktest')

        self.assertEquals(self.actor.ecs_conn.delete_service.call_count, 1)


class TestUpdateService(testing.AsyncTestCase):
    def setUp(self):
        super(TestUpdateService, self).setUp()
        self.actor = _mock_service_actor()
        self.actor.ecs_conn = mock.Mock()

    @testing.gen_test
    def test_call(self):
        service_name = 'service_name'
        family = 'family'
        revision = '1'
        configuration = 'configuration'
        self.actor.service_definition = {
            'deploymentConfiguration': configuration,
            'extra': 'not included'}

        yield self.actor._update_service(
            service_name=service_name,
            task_definition_name='{}:{}'.format(family, revision))
        call_args = self.actor.ecs_conn.update_service.call_args
        expected = ({
                        'cluster': self.actor.option('cluster'),
                        'service': service_name,
                        'taskDefinition': '{0}:{1}'.format(family, revision),
                        'desiredCount': self.actor.option('count'),
                        'deploymentConfiguration': configuration
                    },)
        self.assertTrue(call_args == expected)

        revision = '2'
        self.actor._options['cluster'] = 'cluster'
        self.actor._options['count'] = 5
        yield self.actor._update_service(
            service_name=service_name,
            task_definition_name='{}:{}'.format(family, revision))
        expected = ({
                        'cluster': self.actor.option('cluster'),
                        'service': service_name,
                        'taskDefinition': '{0}:{1}'.format(family, revision),
                        'desiredCount': self.actor.option('count'),
                        'deploymentConfiguration': configuration
                    },)
        call_args = self.actor.ecs_conn.update_service.call_args
        self.assertTrue(call_args == expected)

    @testing.gen_test
    def test_dry(self):
        self.actor._dry = True
        yield self.actor._update_service(
            service_name='',
            family='',
            revision='')
        self.assertFalse(self.actor.ecs_conn.update_service.called)

    @testing.gen_test
    def test_internal_exception(self):
        self.actor.ecs_conn.update_service.side_effect = Boto3Error
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._update_service(
                service_name='service_name',
                task_definition_name='family:1')


class TestEnsureService(testing.AsyncTestCase):
    def setUp(self):
        super(TestEnsureService, self).setUp()

        self.actor = _mock_service_actor()
        self.actor.ecs_conn = mock.Mock()
        self.actor._create_service = helper.mock_tornado()
        self.actor._update_service = helper.mock_tornado()
        self.actor._check_immutable_field_errors = mock.Mock()
        self.actor._get_primary_deployment = mock.Mock()
        self.actor._get_primary_deployment.return_value = {
            'taskDefinition': 'arn/family:1'}

        gen.sleep = helper.mock_tornado()

        self.service_name = 'service_name'
        self.task_definition_name = 'family:1'
        self.start = datetime.datetime.now()

    def tearDown(self):
        reload(gen)

    @testing.gen_test
    def test_create(self):
        self.actor._describe_service = helper.mock_tornado(None)
        yield self.actor._ensure_service(
            service_name=self.service_name,
            task_definition_name=self.task_definition_name)
        self.assertEqual(self.actor._describe_service._call_count, 2)
        self.assertEqual(self.actor._create_service._call_count, 1)
        self.assertEqual(self.actor._update_service._call_count, 0)

    @testing.gen_test
    def test_create_inactive(self):
        self.actor._describe_service = helper.mock_tornado(
            {'status': 'INACTIVE'})
        yield self.actor._ensure_service(
            service_name=self.service_name,
            task_definition_name=self.task_definition_name)
        self.assertEqual(self.actor._describe_service._call_count, 2)
        self.assertEqual(self.actor._create_service._call_count, 1)
        self.assertEqual(self.actor._update_service._call_count, 0)

    @testing.gen_test
    def test_delete(self):
        self.actor._options['state'] = 'absent'
        self.actor._describe_service = helper.mock_tornado(
            {'status': 'ACTIVE'})
        self.actor._delete_service = helper.mock_tornado()
        yield self.actor._ensure_service(
            service_name=self.service_name,
            task_definition_name=self.task_definition_name)
        self.assertEqual(self.actor._delete_service._call_count, 1)

    @testing.gen_test
    def test_update(self):
        self.actor._describe_service = helper.mock_tornado(
            {'status': 'ACTIVE'})
        self.actor._check_immutable_field_errors.return_value = []
        yield self.actor._ensure_service(
            service_name=self.service_name,
            task_definition_name=self.task_definition_name)
        self.assertEqual(self.actor._describe_service._call_count, 2)
        self.assertEqual(self.actor._create_service._call_count, 0)
        self.assertEqual(self.actor._update_service._call_count, 1)
        self.assertEqual(self.actor._check_immutable_field_errors.call_count,
                         1)

    @testing.gen_test
    def test_update_with_immutable_error(self):
        self.actor._describe_service = helper.mock_tornado(
            {'status': 'ACTIVE'})
        ex = exceptions.RecoverableActorFailure
        self.actor._check_immutable_field_errors.side_effect = ex
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._ensure_service(
                service_name=self.service_name,
                task_definition_name=self.task_definition_name)
        self.assertEqual(self.actor._describe_service._call_count, 1)
        self.assertEqual(self.actor._create_service._call_count, 0)
        self.assertEqual(self.actor._update_service._call_count, 0)
        self.assertEqual(self.actor._check_immutable_field_errors.call_count,
                         1)

    @testing.gen_test
    def test_slow_update(self):
        def fail_twice(*args, **kwargs):
            fail_twice.call_count += 1
            if fail_twice.call_count > 2:
                return {'taskDefinition': 'arn/family:1'}
            return None

        fail_twice.call_count = 0

        self.actor._get_primary_deployment = fail_twice

        self.actor._describe_service = helper.mock_tornado(
            {'status': 'ACTIVE'})
        yield self.actor._ensure_service(
            service_name=self.service_name,
            task_definition_name=self.task_definition_name)
        self.assertEqual(self.actor._describe_service._call_count, 4)
        self.assertEqual(self.actor._create_service._call_count, 0)
        self.assertEqual(self.actor._update_service._call_count, 1)
        self.assertEqual(self.actor._check_immutable_field_errors.call_count,
                         1)
        self.assertEqual(fail_twice.call_count, 3)

    @testing.gen_test
    def test_already_deleted(self):
        self.actor._options['state'] = 'absent'
        self.actor._describe_service = helper.mock_tornado(None)
        self.actor._delete_service = helper.mock_tornado()
        yield self.actor._ensure_service(
            service_name=self.service_name,
            task_definition_name=self.task_definition_name)
        self.assertEqual(self.actor._delete_service._call_count, 0)


class TestWaitForDeployment(testing.AsyncTestCase):
    def setUp(self):
        super(TestWaitForDeployment, self).setUp()

        self.actor = _mock_service_actor()
        gen.sleep = helper.mock_tornado()

        self.service_name = 'service_name'

    def tearDown(self):
        reload(gen)

    @testing.gen_test
    def test_instant_success(self):
        self.actor._is_service_deployed = helper.mock_tornado(True)

        yield self.actor._wait_for_deployment(self.service_name, 'family:1')
        self.assertEqual(self.actor._is_service_deployed._call_count, 1)
        self.assertEqual(gen.sleep._call_count, 0)

    @testing.gen_test
    def test_two_failures_before_success(self):
        @gen.coroutine
        def fail_twice(*args):
            fail_twice.call_count += 1
            return fail_twice.call_count > 2

        fail_twice.call_count = 0

        self.actor._is_service_deployed = fail_twice
        yield self.actor._wait_for_deployment(self.service_name, 'family:1')
        self.assertEqual(fail_twice.call_count, 3)
        self.assertEqual(gen.sleep._call_count, 2)


class TestIsServiceDeployed(testing.AsyncTestCase):
    def setUp(self):
        super(TestIsServiceDeployed, self).setUp()

        self.actor = _mock_service_actor()
        self.actor._get_sorted_new_log_events = mock.Mock()
        self.actor._get_sorted_new_log_events.return_value = []

        self.service_name = 'service_name'
        self.start = datetime.datetime.now()

    @testing.gen_test
    def test_no_deployments(self):
        self.actor._describe_service = helper.mock_tornado({'deployments': []})
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._is_service_deployed(
                service_name=self.service_name,
                task_definition_name='family:1')

        self.assertEqual(self.actor._describe_service._call_count, 1)

    @testing.gen_test
    def test_no_primary_deployment(self):
        self.actor._describe_service = helper.mock_tornado({
            'deployments': [{
                'status': 'NOT PRIMARY'
            }]})
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._is_service_deployed(
                service_name=self.service_name,
                task_definition_name='family:1')

        self.assertEqual(self.actor._describe_service._call_count, 1)

    @testing.gen_test
    def test_done(self):
        self.actor._describe_service = helper.mock_tornado({
            'deployments': [{
                'status': 'PRIMARY',
                'taskDefinition': 'arn/family:1',
                'createdAt': self.start,
                'runningCount': 1,
                'desiredCount': 1}],
            'events': []})
        result = yield self.actor._is_service_deployed(
            service_name=self.service_name,
            task_definition_name='family:1')
        self.assertTrue(result)

    @testing.gen_test
    def test_not_done(self):
        self.actor._describe_service = helper.mock_tornado({
            'deployments': [{
                'status': 'PRIMARY',
                'taskDefinition': 'arn/family:1',
                'createdAt': self.start,
                'runningCount': 0,
                'desiredCount': 1}],
            'events': []})
        result = yield self.actor._is_service_deployed(
            service_name=self.service_name,
            task_definition_name='family:1')
        self.assertFalse(result)

    @testing.gen_test
    def test_not_done_extra_deployments(self):
        self.actor._describe_service = helper.mock_tornado({
            'deployments': [{
                'status': 'PRIMARY',
                'taskDefinition': 'arn/family:1',
                'createdAt': self.start,
                'runningCount': 0,
                'desiredCount': 1,
            }, {
                'status': 'NOT PRIMARY',
            }],
            'events': []})
        result = yield self.actor._is_service_deployed(
            service_name=self.service_name,
            task_definition_name='family:1')
        self.assertFalse(result)

    @testing.gen_test
    def test_done_extra_deployments(self):
        self.actor._describe_service = helper.mock_tornado({
            'deployments': [{
                'status': 'PRIMARY',
                'taskDefinition': 'arn/family:1',
                'createdAt': self.start,
                'runningCount': 1,
                'desiredCount': 1,
            }, {
                'status': 'NOT PRIMARY',
            }],
            'events': []})
        result = yield self.actor._is_service_deployed(
            service_name=self.service_name,
            task_definition_name='family:1')
        self.assertFalse(result)

    @testing.gen_test
    def test_events(self):
        events = ['event1', 'event2']
        self.actor._describe_service = helper.mock_tornado({
            'deployments': [{
                'status': 'PRIMARY',
                'taskDefinition': 'arn/family:1',
                'createdAt': self.start,
                'runningCount': 1,
                'desiredCount': 1}],
            'events': events})
        self.actor._get_sorted_new_log_events.return_value = [
            (self.start, events[0]),
            (self.start, events[1])]
        result = yield self.actor._is_service_deployed(
            service_name=self.service_name,
            task_definition_name='family:1')
        self.actor._get_sorted_new_log_events.assert_called_with(
            events=events,
            start_timestamp=self.start)
        self.assertTrue(result)

    @testing.gen_test
    def test_stale_response(self):
        self.actor._describe_service = helper.mock_tornado({
            'deployments': [{
                'status': 'PRIMARY',
                'taskDefinition': 'arn/family:1',
                'createdAt': self.start,
                'runningCount': 1,
                'desiredCount': 1}],
            'events': []})
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._is_service_deployed(
                service_name=self.service_name,
                task_definition_name='family:2')


class TestServiceExecute(testing.AsyncTestCase):
    def setUp(self):
        super(TestServiceExecute, self).setUp()

        self.actor = _mock_service_actor()
        self.actor._register_task = helper.mock_tornado(('family', 1,
                                                         'family:1'))
        self.actor._get_service_name = mock.Mock()
        self.actor._get_service_name.return_value = 'service_name'
        self.actor._ensure_service = helper.mock_tornado()
        self.actor._wait_for_deployment = helper.mock_tornado()

    @testing.gen_test
    def test_ok(self):
        yield self.actor._execute()
        self.assertEqual(self.actor._register_task._call_count, 1)
        self.assertEqual(self.actor._get_service_name.call_count, 1)
        self.assertEqual(self.actor._ensure_service._call_count, 1)
        self.assertEqual(self.actor._wait_for_deployment._call_count, 1)

    @testing.gen_test
    def test_without_wait(self):
        self.actor._options['wait'] = False
        yield self.actor._execute()
        self.assertEqual(self.actor._register_task._call_count, 1)
        self.assertEqual(self.actor._get_service_name.call_count, 1)
        self.assertEqual(self.actor._ensure_service._call_count, 1)
        self.assertEqual(self.actor._wait_for_deployment._call_count, 0)

    @testing.gen_test
    def test_dry(self):
        self.actor._dry = True
        yield self.actor._execute()
        self.assertEqual(self.actor._register_task._call_count, 1)
        self.assertEqual(self.actor._get_service_name.call_count, 1)
        self.assertEqual(self.actor._ensure_service._call_count, 1)
        self.assertEqual(self.actor._wait_for_deployment._call_count, 1)


class TestGetContainersFromTasks(testing.AsyncTestCase):
    def setUp(self):
        super(TestGetContainersFromTasks, self).setUp()
        self.actor = _mock_task_actor()

    @testing.gen_test
    def test_empty(self):
        result = self.actor._get_containers_from_tasks([])
        self.assertEqual(result, [])

    @testing.gen_test
    def test_one(self):
        result = self.actor._get_containers_from_tasks([{
            'containers': [1]
        }])
        self.assertEqual(result, [1])

    @testing.gen_test
    def test_two_in_one_container(self):
        result = self.actor._get_containers_from_tasks([{
            'containers': [1, 2]
        }])
        self.assertEqual(result, [1, 2])

    @testing.gen_test
    def test_two_in_two_containers(self):
        result = self.actor._get_containers_from_tasks([
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
        result = self.actor._get_containers_from_tasks([
            {
                'containers': [{'a', 'b'}, {'a': 1}]
            },
            {
                'containers': [1, 2]
            }
        ])
        self.assertEqual(result, [{'a', 'b'}, {'a': 1}, 1, 2])


class TestCheckImmutableFieldErrors(testing.AsyncTestCase):
    def setUp(self):
        super(TestCheckImmutableFieldErrors, self).setUp()
        self.actor = _mock_service_actor()
        self.actor.log.error = mock.Mock()

    @testing.gen_test
    def test_everything_empty(self):
        self._test(old={}, new={}, immutable=[], expected_error_count=0)

    @testing.gen_test
    def test_same_no_immutable(self):
        self._test(old={'a': 1},
                   new={'a': 1},
                   immutable=[], expected_error_count=0)

    @testing.gen_test
    def test_different_no_immutable(self):
        self._test(old={'a': 1},
                   new={'b': 1},
                   immutable=[], expected_error_count=0)

    @testing.gen_test
    def test_same_only_has_immutable(self):
        self._test(old={'a': 1},
                   new={'a': 1},
                   immutable=['a'], expected_error_count=0)

    @testing.gen_test
    def test_different_only_has_immutable(self):
        self._test(old={'a': 1},
                   new={'a': 2},
                   immutable=['a'], expected_error_count=1)
        self._test(old={'a': 2},
                   new={'a': 1},
                   immutable=['a'], expected_error_count=1)

    @testing.gen_test
    def test_different_only_has_immutable_multiple(self):
        self._test(old={'a': 2},
                   new={'a': 1},
                   immutable=['a', 'b'], expected_error_count=1)
        self._test(old={'a': 2},
                   new={'a': 1},
                   immutable=['b', 'a'], expected_error_count=1)

    @testing.gen_test
    def test_complex(self):
        self._test(old={'a': 1, 'b': 2, 'c': 3},
                   new={'a': {'a': {'b': 1}}, 'b': 'different', 'c': 3},
                   immutable=['b', 'c'], expected_error_count=1)

    @testing.gen_test
    def test_role_logic(self):
        self._test(old={'roleArn': 'a/b'},
                   new={'role': 'b'},
                   immutable=['role'], expected_error_count=0)
        self._test(old={'roleArn': 'a/c'},
                   new={'role': 'b'},
                   immutable=['role'], expected_error_count=1)
        self._test(old={},
                   new={'role': 'b'},
                   immutable=['role'], expected_error_count=1)

    def _test(self, old, new, immutable, expected_error_count):
        # Reset call count
        self.actor.log.error.call_count = 0
        if expected_error_count > 0:
            with self.assertRaises(exceptions.RecoverableActorFailure):
                self.actor._check_immutable_field_errors(old, new, immutable)
            self.assertEqual(self.actor.log.error.call_count,
                             expected_error_count)
        else:
            self.actor._check_immutable_field_errors(old, new, immutable)


class TestGetSortedNewLogEvents(testing.AsyncTestCase):
    def setUp(self):
        super(TestGetSortedNewLogEvents, self).setUp()
        self.actor = _mock_service_actor()
        self.start = datetime.datetime.now()
        self.two_seconds_ago = self.start - datetime.timedelta(seconds=2)
        self.one_seconds_ago = self.start - datetime.timedelta(seconds=1)
        self.one_seconds_later = self.start + datetime.timedelta(seconds=1)
        self.two_seconds_later = self.start + datetime.timedelta(seconds=2)

    def test_no_events(self):
        self.actor.seen_events = set()
        events = self.actor._get_sorted_new_log_events(
            events=[],
            start_timestamp=self.start)
        self.assertEqual(events, [])

    def test_seen_all_one_event(self):
        self.actor.seen_events = {0}
        events = self.actor._get_sorted_new_log_events(
            events=[{
                'id': 0,
                'message': 'message',
                'createdAt': self.one_seconds_ago}],
            start_timestamp=self.start)
        self.assertEqual(events, [])

    def test_seen_all_two_events(self):
        self.actor.seen_events = {0, 1}
        events = self.actor._get_sorted_new_log_events(
            events=[{
                'id': 0,
                'message': 'message1',
                'createdAt': self.one_seconds_ago
            }, {
                'id': 1,
                'message': 'message2',
                'createdAt': self.one_seconds_later
            }],
            start_timestamp=self.start)
        self.assertEqual(events, [])

    def test_timestamp_filtering(self):
        events_after = [{
            'id': 0,
            'message': 'message1',
            'createdAt': self.two_seconds_later
        }, {
            'id': 1,
            'message': 'message2',
            'createdAt': self.one_seconds_later
        }]
        events_before = [{
            'id': 2,
            'message': 'message3',
            'createdAt': self.one_seconds_ago}]
        self.actor.seen_events = set()
        events = self.actor._get_sorted_new_log_events(
            events=events_after + events_before,
            start_timestamp=self.start)
        expected = [
            (self.one_seconds_later, 'message2'),
            (self.two_seconds_later, 'message1')]
        self.assertEqual(events, expected)

    def test_seen_added_to(self):
        input_events = [{
            'id': 0,
            'message': 'message1',
            'createdAt': self.one_seconds_ago
        }, {
            'id': 1,
            'message': 'message2',
            'createdAt': self.one_seconds_later
        }]
        self.actor.seen_events = {2}
        events = self.actor._get_sorted_new_log_events(
            events=input_events,
            start_timestamp=self.start)
        expected = [
            (input_events[1]['createdAt'], input_events[1]['message'])
        ]
        self.assertEqual(events, expected)
        self.assertEqual(self.actor.seen_events, {1, 2})


def _mock_task_actor():
    settings.ECS_RETRY_ATTEMPTS = 0
    reload(ecs_actor)
    base_actor = 'kingpin.actors.aws.ecs.ECSBaseActor'
    load_task_definition = base_actor + '._load_task_definition'
    with mock.patch(load_task_definition):
        return ecs_actor.RunTask(
            options={
                'region': '',
                'cluster': '',
                'task_definition': ''})


def _mock_service_actor():
    settings.ECS_RETRY_ATTEMPTS = 0
    reload(ecs_actor)
    base_actor = 'kingpin.actors.aws.ecs.ECSBaseActor'
    load_task_definition = base_actor + '._load_task_definition'
    load_service_definition = base_actor + '._load_service_definition'
    with mock.patch(load_task_definition), mock.patch(load_service_definition):
        return ecs_actor.Service(
            options={
                'region': '',
                'cluster': '',
                'task_definition': ''})
