"""Simple integration tests for the AWS ECS actors."""

from nose.plugins.attrib import attr
import logging
import json
import os
import tempfile
import uuid
from contextlib import contextmanager

from tornado import testing

from kingpin.actors.aws import ecs

__author__ = 'Steve Mostovoy <smostovoy@nextdoor.com>'

# Generate a common UUID for this particular set of tests
UUID = uuid.uuid4().hex

log = logging.getLogger(__name__)
logging.getLogger('boto').setLevel(logging.INFO)


class IntegrationECS(testing.AsyncTestCase):

    """High level ECS Actor testing.

    This suite of tests performs the following actions:
        * Runs a series of successful and failing tasks and wait for completion
        * Runs a task without waiting
        * Starts a service with count 0
        * Changes the scale of service to 1
        * Changes the scale of service to 5 without waiting
        * Deletes service
        * Starts a service with count 1
        * Changes the scale of service to count 0
        * Deletes service

    Note, these tests must be run in-order. The order is defined by
    their definition order in this file. Nose follows this order according
    to its documentation:

        http://nose.readthedocs.org/en/latest/writing_tests.html
    """

    integration = True

    region = os.getenv('ECS_INTEGRATION_REGION', 'us-east-1')
    cluster = os.getenv('ECS_INTEGRATION_CLUSTER', 'default')

    def _successful_task(self):
        name = 'kingpin-integration-task-successful'
        return name, self._make_task(name, 'exit 0')

    def _slow_successful_task(self):
        name = 'kingpin-integration-task-slow-successful'
        return name, self._make_task(name, 'sleep 5; exit 0')

    def _failing_task(self):
        name = 'kingpin-integration-task-failing'
        return name, self._make_task(name, 'exit 1')

    def _slow_failing_task(self):
        name = 'kingpin-integration-task-slow-failing'
        return name, self._make_task(name, 'sleep 5; exit 1')

    def _hanging_task(self):
        name = 'kingpin-integration-task-hang'
        return name, self._make_task(name, 'tail -f /dev/null')

    def _make_task(self, name, command):
        return json.dumps({
            'family': name,
            'containerDefinitions': [{
                'name': name,
                'image': 'ubuntu:12.04',
                'cpu': 64,
                'memory': 64,
                'essential': True,
                'command': ['/bin/bash', '-c', command]
            }]})

    @contextmanager
    def _tmp_file(self, data):
        temp = tempfile.NamedTemporaryFile(suffix='.json', delete=False)
        temp.write(data)
        temp.close()
        yield temp.name
        os.unlink(temp.name)

    @attr('aws', 'integration')
    @testing.gen_test(timeout=120)
    def integration_01a_run_successful_task(self):
        name, task = self._successful_task()
        with self._tmp_file(task) as definition:
            actor = ecs.RunTask(
                'Run %s' % name,
                {'region': self.region,
                 'cluster': self.cluster,
                 'task_definition': definition})
        yield actor.execute()

    @attr('aws', 'integration')
    @testing.gen_test(timeout=120)
    def integration_01b_run_slow_successful_task(self):
        name, task = self._slow_successful_task()
        with self._tmp_file(task) as definition:
            actor = ecs.RunTask(
                'Run %s' % name,
                {'region': self.region,
                 'cluster': self.cluster,
                 'task_definition': definition})
        yield actor.execute()

    @attr('aws', 'integration')
    @testing.gen_test(timeout=120)
    def integration_01c_run_failing_task(self):
        name, task = self._failing_task()
        with self._tmp_file(task) as definition:
            actor = ecs.RunTask(
                'Run %s' % name,
                {'region': self.region,
                 'cluster': self.cluster,
                 'task_definition': definition})
        with self.assertRaises(ecs.ECSTaskFailedException):
            yield actor.execute()

    @attr('aws', 'integration')
    @testing.gen_test(timeout=120)
    def integration_01d_run_slow_failing_task(self):
        name, task = self._slow_failing_task()
        with self._tmp_file(task) as definition:
            actor = ecs.RunTask(
                'Run %s' % name,
                {'region': self.region,
                 'cluster': self.cluster,
                 'task_definition': definition})
        with self.assertRaises(ecs.ECSTaskFailedException):
            yield actor.execute()

    @attr('aws', 'integration')
    @testing.gen_test(timeout=120)
    def integration_02a_run_slow_failing_task_dont_wait(self):
        name, task = self._slow_failing_task()
        with self._tmp_file(task) as definition:
            actor = ecs.RunTask(
                'Run %s' % name,
                {'region': self.region,
                 'cluster': self.cluster,
                 'task_definition': definition,
                 'wait': False})
        yield actor.execute()

    @attr('aws', 'integration')
    @testing.gen_test(timeout=120)
    def integration_03a_start_service_no_count(self):
        name, task = self._hanging_task()
        with self._tmp_file(task) as definition:
            actor = ecs.Service(
                'Starting service %s with count 0' % name,
                {'region': self.region,
                 'cluster': self.cluster,
                 'task_definition': definition,
                 'service_name': '%s_%s' % (name, '03'),
                 'count': 0})
        yield actor.execute()

    @attr('aws', 'integration')
    @testing.gen_test(timeout=120)
    def integration_03b_scale_service(self):
        name, task = self._hanging_task()
        with self._tmp_file(task) as definition:
            actor = ecs.Service(
                'Scaling service %s to count 1' % name,
                {'region': self.region,
                 'cluster': self.cluster,
                 'task_definition': definition,
                 'service_name': '%s_%s' % (name, '03'),
                 'use_existing_count': False,
                 'count': 1})
        yield actor.execute()

    @attr('aws', 'integration')
    @testing.gen_test(timeout=120)
    def integration_03c_scale_service_dont_wait(self):
        name, task = self._hanging_task()
        with self._tmp_file(task) as definition:
            actor = ecs.Service(
                'Scaling service %s to count 2' % name,
                {'region': self.region,
                 'cluster': self.cluster,
                 'task_definition': definition,
                 'service_name': '%s_%s' % (name, '03'),
                 'use_existing_count': False,
                 'count': 2})
        yield actor.execute()

    @attr('aws', 'integration')
    @testing.gen_test(timeout=120)
    def integration_03d_delete_service(self):
        name, task = self._hanging_task()
        with self._tmp_file(task) as definition:
            actor = ecs.Service(
                'Deleting service %s' % name,
                {'region': self.region,
                 'cluster': self.cluster,
                 'task_definition': definition,
                 'service_name': '%s_%s' % (name, '03'),
                 'state': 'absent'})
        yield actor.execute()

    @attr('aws', 'integration')
    @testing.gen_test(timeout=120)
    def integration_04a_start_service_scaled(self):
        name, task = self._hanging_task()
        with self._tmp_file(task) as definition:
            actor = ecs.Service(
                'Starting service %s with count 1' % name,
                {'region': self.region,
                 'cluster': self.cluster,
                 'task_definition': definition,
                 'service_name': '%s_%s' % (name, '04'),
                 'count': 1})
        yield actor.execute()

    @attr('aws', 'integration')
    @testing.gen_test(timeout=120)
    def integration_04b_scale_service_down(self):
        name, task = self._hanging_task()
        with self._tmp_file(task) as definition:
            actor = ecs.Service(
                'Scaling service %s to count 0' % name,
                {'region': self.region,
                 'cluster': self.cluster,
                 'task_definition': definition,
                 'service_name': '%s_%s' % (name, '04'),
                 'use_existing_count': False,
                 'count': 0})
        yield actor.execute()

    @attr('aws', 'integration')
    @testing.gen_test(timeout=120)
    def integration_04c_delete_service(self):
        name, task = self._hanging_task()
        with self._tmp_file(task) as definition:
            actor = ecs.Service(
                'Deleting service %s' % name,
                {'region': self.region,
                 'cluster': self.cluster,
                 'task_definition': definition,
                 'service_name': '%s_%s' % (name, '04'),
                 'state': 'absent'})
        yield actor.execute()
