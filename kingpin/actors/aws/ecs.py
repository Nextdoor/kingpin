# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Copyright 2014 Nextdoor.com, Inc

"""
:mod:`kingpin.actors.aws.ecs`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
"""

import jsonschema
import logging

from tornado import gen

from kingpin import utils
from kingpin.actors import exceptions
from kingpin.actors.aws import base
from kingpin.actors.utils import dry
from kingpin.constants import REQUIRED

log = logging.getLogger(__name__)

__author__ = 'Steve Mostovoy <smostovoy@nextdoor.com>'

# http://boto3.readthedocs.io/en/latest/reference/services/ecs.html
TASK_DEFINITION_SCHEMA = {
    'type': 'object',
    'required': ['family', 'containerDefinitions'],
    'additionalProperties': False,
    'properties': {
        'family': {'type': 'string'},
        'containerDefinitions': {
            'type': 'array',
            'items': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {
                    'name': {'type': 'string'},
                    'image': {'type': 'string'},
                    'cpu': {'type': 'number'},
                    'memory': {'type': 'number'},
                    'links': {
                        'type': 'array',
                        'items': {'type': 'string'}
                    },
                    'portMappings': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'additionalProperties': False,
                            'properties': {
                                'containerPort': {'type': 'number'},
                                'hostPort': {'type': 'number'},
                                'protocol': {'type': 'string'}
                            }
                        }
                    },
                    'essential': {'type': 'boolean'},
                    'entryPoint': {
                        'type': 'array',
                        'items': {'type': 'string'}
                    },
                    'command': {
                        'type': 'array',
                        'items': {'type': 'string'}
                    },
                    'environment': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'additionalProperties': False,
                            'properties': {
                                'name': {'type': 'string'},
                                'value': {'type': 'string'}
                            }
                        }
                    },
                    'mountPoints': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'additionalProperties': False,
                            'properties': {
                                'sourceVolume': {'type': 'string'},
                                'containerPath': {'type': 'string'},
                                'readOnly': {'type': 'boolean'}
                            }
                        }
                    },
                    'volumesFrom': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'additionalProperties': False,
                            'properties': {
                                'sourceContainer': {'type': 'string'},
                                'readOnly': {'type': 'boolean'}
                            }
                        }
                    },
                    'hostname': {'type': 'string'},
                    'user': {'type': 'string'},
                    'workingDirectory': {'type': 'string'},
                    'disableNetworking': {'type': 'boolean'},
                    'privileged': {'type': 'boolean'},
                    'readonlyRootFilesystem': {'type': 'boolean'},
                    'dnsServers': {
                        'type': 'array',
                        'items': {'type': 'string'}
                    },
                    'dnsSearchDomains': {
                        'type': 'array',
                        'items': {'type': 'string'}
                    },
                    'extraHosts': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'additionalProperties': False,
                            'properties': {
                                'hostname': {'type': 'string'},
                                'ipAddress': {'type': 'string'}
                            }
                        }
                    },
                    'dockerSecurityOptions': {
                        'type': 'array',
                        'items': {'type': 'string'}
                    },
                    'dockerLabels': {'type': 'object'},
                    'ulimits': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'required': ['name', 'softLimit', 'hardLimit'],
                            'additionalProperties': False,
                            'properties': {
                                'name': {'type': 'string'},
                                'softLimit': {'type': 'number'},
                                'hardLimit': {'type': 'number'}
                            }
                        }
                    },
                    'logConfiguration': {'type': 'object'},
                    'logDriver': {'type': 'string'},
                    'options': {'type': 'object'}
                }
            }
        },
        'volumes': {
            'type': 'array',
            'items': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {
                    'name': {'type': 'string'},
                    'host': {
                        'type': 'object',
                        'additionalProperties': False,
                        'properties': {
                            'sourcePath': {'type': 'string'}
                        }
                    }
                }
            }
        }
    }
}


class ECSBaseActor(base.AWSBaseActor):
    """Base class for ECS actors."""

    def _handle_failures(self, failures):
        """Logs ECS failures. Raises a recoverable exception if there are any.

        Args:
            failures: list of failures from ECS api.
        """
        if not failures:
            return

        # TODO: When can we recover? What are the failures? How do we recover?
        for failure in failures:
            self.log.error(failure)
        raise exceptions.RecoverableActorFailure()


class RunTask(ECSBaseActor):
    """Register and run a task on ECS.

    This actor will loop indefinitely until the task is complete.

    **Options**

    :region:
      AWS region (or zone) name, such as us-west-2 or eu-west-1.

    :cluster:
      ECS cluster in the region to launch the task into.

    :task_definition:
      String of path to the Task Definition file template.
      Must be a local file path.
      Parameters to be interpolated must be of the form %VAR%.

    :parameters:
      A dictionary of key/value pairs used to fill in the parameters for the
      Task Definition template. Default: {}.

    :count:
      How many tasks to run. Default: 1.

    :wait:
      Whether to wait for the tasks to complete. Default: True.

    **Examples**

    .. code-block:: yaml

       actor: aws.ecs.RunTask
       desc: Run migrations
       options:
          task_definition: nextdoor-migrate.json
          region: us-west-2
          cluster: us1-internal

    **Dry Mode**

    Will only attempt to interpolate env vars into the task definition.
    """

    all_options = {
        'region': (str, REQUIRED,
                   'AWS region (or zone) name, like us-west-2 or eu-west-1.'),
        'cluster': (str, REQUIRED,
                    'ECS cluster in the region to launch the task into.'),
        'task_definition':
            (str, REQUIRED,
             'String of path to the Task Definition file template. '
             'Must be a local file path. '
             'Parameters to be interpolated must be of the form %VAR%.'),
        'parameters': (dict, {},
                       'A dictionary of key/value pairs '
                       'used to fill in the parameters for the template.'),
        'count': (int, 1, 'How many tasks to run.'),
        'wait': (bool, True,
                 'Whether to wait for the tasks to complete.')
    }

    def __init__(self, *args, **kwargs):
        super(RunTask, self).__init__(*args, **kwargs)
        self.task_definition = _load_task_definition(
            self.option('task_definition'),
            self.option('parameters'))

    @gen.coroutine
    def _register_task(self, task_definition):
        """Registers a task on ECS.

        Args:
            task_definition: dict of ECS task definition parameters.

        Returns:
            tuple: ('family', 'revision').
        """
        family = task_definition['family']
        if self._dry:
            self.log.info(
                'Would register task definition with family {0}'.format(
                    family))
            raise gen.Return((family, 1))

        self.log.info('Registering task definition with family {0}'.format(
            family))
        response = yield self.thread(
            self.ecs_conn.register_task_definition, **task_definition)

        # Parse data from the server's response.
        task_definition = response['taskDefinition']
        family = task_definition['family']
        revision = task_definition['revision']

        self.log.info('Task definition {0}:{1} registered'.format(
            family, revision))
        raise gen.Return((family, revision))

    @gen.coroutine
    @dry('Would run task {family}:{revision}')
    def _run_task(self, family, revision):
        """Runs a task on ECS given a task definition's family and revision.

        A task can result in multiple running tasks,
        depending on count and sidekick tasks.

        Args:
            family: Task family string
            revision: Task revision string

        Returns:
            list: task ARNs.
        """
        response = yield self.thread(
            self.ecs_conn.run_task,
            cluster=self.option('cluster'),
            taskDefinition='{0}:{1}'.format(family, revision),
            count=self.option('count'))
        self._handle_failures(response['failures'])
        tasks = [t['taskArn'] for t in response['tasks']]
        raise gen.Return(tasks)

    @gen.coroutine
    def _wait_for_tasks(self, tasks):
        """Wait for tasks to stop on ECS.

        If a task stops with a non-zero exit code,
        this will raise an exception.

        Args:
            tasks: list of task ARNs to wait for.
        """
        if not tasks:
            return
        while True:
            done = yield self._tasks_done(tasks)
            if done:
                break
            yield gen.sleep(5)

    @gen.coroutine
    def _tasks_done(self, tasks):
        """Checks if tasks are done.

        Args:
            tasks: list of task ARNs to check.

        Returns:
            A boolean indicating whether all tasks are done.
        """
        response = yield self.thread(
            self.ecs_conn.describe_tasks,
            cluster=self.option('cluster'),
            tasks=tasks)

        self._handle_failures(response['failures'])

        containers = _get_containers_from_tasks(
            task_list=response['tasks'])

        total_count = len(containers)
        stopped_count = 0

        for container in containers:
            if container['lastStatus'] == 'STOPPED':
                stopped_count += 1
                exit_code = container.get('exitCode', None)
                if exit_code is None:
                    self.log.error('Task {0} stopped without executing'.format(
                        container['taskArn']))
                    raise exceptions.RecoverableActorFailure()
                if exit_code != 0:
                    self.log.error(
                        'Task {0} errored out with exit code {1}'.format(
                            container['taskArn'], exit_code))
                    raise exceptions.RecoverableActorFailure()
                self.log.info('Task {0} finished successfully!'.format(
                        container['taskArn']))

        if stopped_count == total_count:
            self.log.info('All {0} tasks finished'.format(total_count))
            raise gen.Return(True)

        self.log.info(
            '{0} tasks finished out of {1} tasks'.format(
                stopped_count, total_count))
        raise gen.Return(False)

    @gen.coroutine
    def _execute(self):
        self.log.info(
            'Running task from {task_definition} in ECS. '
            'Region: {region}, cluster: {cluster}.'.format(
                task_definition=self.option('task_definition'),
                region=self.option('region'),
                cluster=self.option('cluster')))
        family, revision = yield self._register_task(
            self.task_definition)
        tasks = yield self._run_task(
            family=family,
            revision=revision)
        if self.option('wait'):
            yield self._wait_for_tasks(tasks)
        else:
            self.log.info('Not waiting for tasks to stop')


def _get_containers_from_tasks(task_list):
    """Helper function to get a flat list of containers out of a list of tasks.

    Args:
        task_list: List of dictionaries with the format:
            [
                {
                    ...
                    'containers': [ ... ]
                    ...
                }
            ]

    Returns: All containers as a flat list.

    """
    containers = []
    for task_overview in task_list:
        containers.extend(task_overview['containers'])
    return containers


def _load_task_definition(task_definition_file, parameters):
    """Loads and verifies a task definition template file, and interpolates
    parameters.

    Args:
        task_definition_file: task definition file to load.
        parameters: dict of key/value pairs to interpolate into the file.

    Returns:
        Parsed and interpolated task definition dict.
    """
    task_definition_file = utils.convert_script_to_dict(
        task_definition_file, parameters)
    try:
        jsonschema.validate(task_definition_file,
                            TASK_DEFINITION_SCHEMA)
    except jsonschema.exceptions.ValidationError as e:
        raise exceptions.InvalidOptions(e)
    return task_definition_file
