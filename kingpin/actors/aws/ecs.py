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
# Copyright 2018 Nextdoor.com, Inc

"""
:mod:`kingpin.actors.aws.ecs`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
"""

import jsonschema
import logging
import operator

from tornado import gen

from kingpin import utils
from kingpin.actors import exceptions
from kingpin.actors.aws import base
from kingpin.actors.aws import settings
from kingpin.actors.utils import dry
from kingpin.constants import REQUIRED, STATE

log = logging.getLogger(__name__)

__author__ = 'Willem Van Eck <willem@nextdoor.com>'


class ECSAPIException(exceptions.RecoverableActorFailure):
    """A failure from the ECS API."""


class ECSTaskFailedException(exceptions.RecoverableActorFailure):
    """A failure from an ECS Task."""


class ServiceNotFound(exceptions.RecoverableActorFailure):
    """Failure to find an ECS Service."""


# http://boto3.readthedocs.io/en/latest/reference/services/ecs.html
TASK_DEFINITION_SCHEMA = {
    'type': 'object',
    'required': ['family', 'containerDefinitions'],
    'properties': {
        'family': {'type': 'string'},
        'networkMode': {'type': 'string'},
        'containerDefinitions': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'name': {'type': 'string'},
                    'image': {'type': 'string'},
                    'cpu': {'type': 'number'},
                    'memory': {'type': 'number'},
                    'memoryReservation': {'type': 'number'},
                    'links': {
                        'type': 'array',
                        'items': {'type': 'string'}
                    },
                    'portMappings': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
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
                            'properties': {
                                'sourceVolume': {'type': 'string'},
                                'containerPath': {'type': 'string'},
                                'readOnly': {'type': 'boolean'}
                            }
                        }
                    },
                    'systemControls': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'namespace': {'type': 'string'},
                                'value': {'type': 'string'}
                            }
                        }
                    },
                    'volumesFrom': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
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
                'properties': {
                    'name': {'type': 'string'},
                    'host': {
                        'type': 'object',
                        'properties': {
                            'sourcePath': {'type': 'string'}
                        }
                    }
                }
            }
        },
        'tags': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'key': {'type': 'string'},
                    'value': {'type': 'string'}
                }
            }
        }
    }
}


class ECSBaseActor(base.AWSBaseActor):
    """Base class for ECS actors."""

    all_options = {
        'count': ((int, str), 1, 'How many tasks to run.')
    }

    def __init__(self, *args, **kwargs):
        super(ECSBaseActor, self).__init__(*args, **kwargs)

        count = self.option('count')
        if type(count) is str or type(count) is str:
            try:
                self._options['count'] = int(count)
            except ValueError:
                raise exceptions.RecoverableActorFailure(
                    'Could not parse option \'count\' as int: %s' % count)

    FAILURE_MISSING = 'MISSING'

    def _handle_failures(self, failures, *ignorable):
        """Logs ECS failures. Raises a recoverable exception if there are any.

        Args:
            failures: list of failures from ECS api.
            ignorable: list of failures to ignore.
        """
        if not failures:
            return

        failure_reasons = []

        for failure in failures:
            reason = failure['reason']
            if reason in ignorable:
                continue
            failure_reasons.append(reason)
            self.log.error(failure)
        if failure_reasons:
            raise ECSAPIException(failure_reasons)

    @gen.coroutine
    @dry('Would register task definition with family {0[family]}')
    def _register_task(self, task_definition):
        """Registers a task.

        Args:
            task_definition: dict of ECS task definition parameters.

        Returns:
            Task Definition name string.
        """
        family = task_definition['family']

        self.log.info('Registering task definition with family {}'.format(
            family))

        response = yield self.api_call(
            self.ecs_conn.register_task_definition, **task_definition)

        # Parse data from the server's response.
        task_definition = response['taskDefinition']
        revision = task_definition['revision']

        task_definition_name = '{}:{}'.format(family, revision)
        self.log.info('Task definition {} registered.'.format(
            task_definition_name))
        raise gen.Return(task_definition_name)

    @gen.coroutine
    @dry('Would deregister task definition {0}')
    def _deregister_task_definition(self, task_definition_name):
        """Deregisters a task definition.

        Args:
            task_definition_name: Task Definition name or arn to deregister.
        """
        self.log.info(
            'Deregistering task definition {}.'.format(task_definition_name))
        yield self.api_call(
            self.ecs_conn.deregister_task_definition,
            taskDefinition=task_definition_name)

    def _read_list_task_definitions_paginator(self, **kwargs):
        """Reads and aggregates results from a list_task_definitions paginator.

        Args:
            **kwargs: Args to pass to the paginator.

        Returns:
            List of task definition arns.
        """
        paginator = self.ecs_conn.get_paginator('list_task_definitions')
        task_definitions = []
        i = 0
        page_iterator = paginator.paginate(**kwargs)
        for page in page_iterator:
            self.log.info('Parsing page {} of results.'.format(i))
            i += 1
            task_definitions += page['taskDefinitionArns']

        return task_definitions

    @gen.coroutine
    @dry('Would describe task definition {0}')
    def _describe_task_definition(self, task_definition_name):
        """Describes the given task definition.

        Args:
            task_definition_name: Task Definition string.

        Returns:
            Returns a dict containing the task definition dict and task
            definition tags list.
        """
        self.log.info('Describing task definition {}.'.format(
            task_definition_name))
        resp = yield self.api_call(
            self.ecs_conn.describe_task_definition,
            taskDefinition=task_definition_name,
            include=['TAGS'])

        del resp['ResponseMetadata']

        raise gen.Return(resp)

    @gen.coroutine
    @dry('Would list task definitions')
    def _list_task_definitions(self, status='ALL', family_prefix=None):
        """List task definitions.

        Optionally uses a prefix to filter family names.
        Optionally returns active task definitions.

        Args:
            status: Type of status to filter with.
                Valid types are 'ACTIVE', 'INACTIVE', and 'ALL'.
                Default 'ALL'.
            family_prefix: Prefix to filter task definition families with.
                Default None.

        Returns:
            List of task definitions arns matching specified restrictions.
        """
        self.log.info(
            'Listing task definitions '
            'with status {} and family prefix {}.'.format(
                status, family_prefix))
        task_definitions = yield self.api_call(
            self._read_list_task_definitions_paginator,
            status=status,
            familyPrefix=family_prefix)

        raise gen.Return(task_definitions)

    @staticmethod
    def _load_task_definition(task_definition_file, tokens, default_tokens={}):
        """Loads and verifies a task definition template file, interpolates
        tokens, and optionally default tokens which may contain environment
        variables.

        Args:
            task_definition_file: task definition file to load, or None.
            tokens: dict of key/value pairs to interpolate into the file.
            default_tokens: dict of default key/value pairs to merge
                with tokens

        Returns:
            Resulting task definition dict or
                None if task_definition_file is None.
        """
        if not task_definition_file:
            return None

        # Defined Kingpin tokens will override environment variables.
        final_tokens = default_tokens.copy()
        final_tokens.update(tokens)

        task_definition = utils.convert_script_to_dict(
            task_definition_file, final_tokens)

        try:
            jsonschema.validate(task_definition,
                                TASK_DEFINITION_SCHEMA)
        except jsonschema.exceptions.ValidationError as e:
            raise exceptions.InvalidOptions(e)
        return task_definition

    @staticmethod
    def _load_service_definition(
            service_definition_file, tokens, default_tokens=None):
        """Loads and verifies a service definition template file, and
        interpolates tokens. and optionally default tokens which may contain
        environment variables. The service definition template file
        can be None.

        Args:
            service_definition_file: service definition file to load.
                If None or an empty string, this returns only defaults.
            tokens: dict of key/value pairs to interpolate into the file.
            default_tokens: dict of default key/value pairs to merge
                with tokens

        Returns:
            Resulting service definition dict.
        """
        if default_tokens is None:
            default_tokens = {}
        if not service_definition_file:
            service_definition = {}
        else:
            final_tokens = default_tokens.copy()
            final_tokens.update(tokens)

            service_definition = utils.convert_script_to_dict(
                service_definition_file, final_tokens)
            try:
                jsonschema.validate(service_definition,
                                    SERVICE_DEFINITION_SCHEMA)

            except jsonschema.exceptions.ValidationError as e:
                raise exceptions.InvalidOptions(e)

        return service_definition

    @staticmethod
    def _arn_to_name(arn):
        """Gets the name in an arn.

        Example input:
            arn:aws:ecs:region:account-id:task-definition/name:135
        Example output:
            name:135

        Args:
            arn: The arn to process.

        Returns:
            The name.
        """
        return arn[arn.index('/') + 1:]

    def _format_location(self):
        """Get a formatted location describing where this actor is running
        for logging.

        Returns:
            Formatted location string with region and cluster.
        """
        return "'{}', cluster '{}'".format(
            self.option('region'),
            self.option('cluster'))


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
      Tokens to be interpolated must be of the form %VAR%.
      Tokens can come in the form of options or environment variables.

    :tokens:
      A dictionary of key/value pairs used to fill in the tokens for the
      Task Definition template.
      These will override environment variables which can be used as tokens.
      Default: {}.

    :count:
      How many tasks to run. Default: 1.

    :wait:
      Whether to wait for the tasks to complete. Default: True.

    **Examples**

    .. code-block:: yaml

       actor: aws.ecs.Task
       desc: Run migrations
       options:
          task_definition: migrate.yaml
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
             'Tokens to be interpolated must be of the form %VAR%.'),
        'tokens': (dict, {},
                   'A dictionary of key/value pairs '
                   'used to fill in the tokens for the '
                   'Task Definition template.'),
        'count': ((int, str), 1, 'How many tasks to run.'),
        'wait': (bool, True,
                 'Whether to wait for the tasks to complete.')
    }

    def __init__(self, *args, **kwargs):
        super(RunTask, self).__init__(*args, **kwargs)
        self.task_definition = self._load_task_definition(
            self.option('task_definition'),
            self.option('tokens'),
            self._init_tokens)

    @gen.coroutine
    @dry('Would run task {0}')
    def _run_task(self, task_definition_name):
        """Runs a task on ECS given a task definition's family and revision.

        A task can result in multiple running tasks,
        depending on count and sidekick tasks.

        Args:
            task_definition_name: Task Definition string

        Returns:
            list: task ARNs.
        """
        repeating_log = utils.create_repeating_log(
            self.log.info,
            'Waiting for task to be found...',
            seconds=30)

        while True:
            response = yield self.api_call(
                self.ecs_conn.run_task,
                cluster=self.option('cluster'),
                taskDefinition=task_definition_name,
                count=self.option('count'))

            if not response['failures']:
                break
            # Error on non-missing failures.
            self._handle_failures(response['failures'], self.FAILURE_MISSING)
            yield gen.sleep(2)

        utils.clear_repeating_log(repeating_log)

        self.log.info('Scheduled task {}.'.format(task_definition_name))
        tasks = [t['taskArn'] for t in response['tasks']]
        raise gen.Return(tasks)

    @gen.coroutine
    def _wait_for_tasks(self, tasks):
        """Wait for tasks to complete on ECS.

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
            yield gen.sleep(10)

    @gen.coroutine
    @utils.retry(excs=ECSAPIException,
                 retries=settings.ECS_RETRY_ATTEMPTS,
                 delay=settings.ECS_RETRY_DELAY)
    def _tasks_done(self, tasks):
        """Checks if tasks are done.

        Args:
            tasks: list of task ARNs to check.

        Returns:
            A boolean indicating whether all tasks are done.
        """
        response = yield self.api_call(
            self.ecs_conn.describe_tasks,
            cluster=self.option('cluster'),
            tasks=tasks)

        self._handle_failures(response['failures'])

        containers = self._get_containers_from_tasks(
            task_list=response['tasks'])

        total_count = len(containers)
        stopped_count = 0

        for container in containers:
            if container['lastStatus'] == 'STOPPED':
                stopped_count += 1
                task_id = container['taskArn']
                if 'reason' in container:
                    self.log.warning('Error reason for {}: {}.'.format(
                        task_id, container['reason']))
                exit_code = container.get('exitCode', None)
                if exit_code is None:
                    raise ECSTaskFailedException(
                        'Task {} stopped without executing.'.format(
                            task_id))
                if exit_code != 0:
                    raise ECSTaskFailedException(
                        'Task {} errored out with exit code {}.'.format(
                            task_id, exit_code))
                self.log.info('Task {} finished successfully!'.format(
                    task_id))

        if stopped_count == total_count:
            self.log.info('All {} tasks finished.'.format(total_count))
            raise gen.Return(True)

        self.log.info(
            '{stopped} tasks finished out of {total}.'.format(
                stopped=stopped_count,
                total=total_count))
        raise gen.Return(False)

    @staticmethod
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

        Returns:
            All containers as a flat list.
        """
        containers = []
        for task_overview in task_list:
            containers.extend(task_overview['containers'])
        return containers

    @gen.coroutine
    def _execute(self):
        self.log.info(
            'Running task from {task_definition} in ECS. '
            'Region: {region}, cluster: {cluster}'.format(
                task_definition=self.option('task_definition'),
                region=self.option('region'),
                cluster=self.option('cluster')))
        task_definition_name = yield self._register_task(
            self.task_definition)

        tasks = yield self._run_task(task_definition_name)
        if self.option('wait'):
            yield self._wait_for_tasks(tasks)
        else:
            self.log.info('Not waiting for tasks to complete.')


# http://boto3.readthedocs.io/en/latest/reference/services/ecs.html
SERVICE_DEFINITION_SCHEMA = {
    'type': 'object',
    'properties': {
        'loadBalancers': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'loadBalancerName': {'type': 'string'},
                    'containerName': {'type': 'string'},
                    'containerPort': {'type': 'number'},
                }
            }
        },
        'role': {'type': 'string'},
        'deploymentConfiguration': {
            'type': 'object',
            'properties': {
                'maximumPercent': {'type': 'number'},
                'minimumHealthyPercent': {'type': 'number'},
            }
        }
    }
}


class Service(ECSBaseActor):
    """Register and run a service on ECS.

    This actor will loop indefinitely until the task is complete. If any
    Service parameters are not supplied, then Amazon supplies the defaults and
    manages them. If these are immutable in Amazon, then you cannot change them
    in the ECS Service Definition down in a future update, and Kingpin will
    error out.

    If the service already exists, it is upgraded.

    **Options**

    :state:
      Desired state: present/absent

    :region:
      AWS region (or zone) name, such as us-west-2 or eu-west-1.

    :cluster:
      ECS cluster in the region to launch the task into.

    :task_definition:
      String of path to the Task Definition file template.
      Must be a local file path.
      Tokens to be interpolated must be of the form %VAR%.
      Tokens can come in the form of options or environment variables.
      Default: None.

    :service_definition:
      String of path to the Service Definition file template.
      Must be a local file path.
      Tokens to be interpolated must be of the form %VAR%.
      Implicit fields - do not include these:
      'serviceName', 'taskDefinition', 'desiredCount', 'clientToken'
      Default: None.

    :service_name:
      Service name to use. If not specified, this will use
      the Task Definition's family.
      Necessary if there is no given Task Definition.
      Default: None.

    :tokens:
      A dictionary of key/value pairs used to fill in the tokens for the
      Task and Service Definition template.
      These will override environment variables which can be used as tokens.
      Default: {}.

    :count:
      How many instances of the service to deploy.
      Not used when state is 'absent'.
      Default: 1.

    :wait:
      Whether to wait for the services to deploy.
      Not used when state is 'absent'.
      Default: True.

    :use_existing_count:
      Whether to use the existing service's count when updating
      instead of the specified count.
      Default: True.

    :deregister_task_definitions:
      Whether to deregister related Task Definitions.
      Only used when state is 'absent'.

    **Examples**

    .. code-block:: yaml

       actor: aws.ecs.Service
       desc: Deploy taskworker
       options:
          task_definition: taskworker.yaml
          region: us-west-2
          cluster: us1-internal

    **Dry Mode**

    Will only validate and interpolate tokens into both the
    task and service definition files.
    """

    all_options = {
        'state': (STATE, 'present', 'Desired state: present/absent'),
        'region': (str, REQUIRED,
                   'AWS region (or zone) name, like us-west-2 or eu-west-1.'),
        'cluster': (str, REQUIRED,
                    'ECS cluster in the region to launch the task into.'),
        'task_definition':
            (str, None,
             'String of path to the Task Definition file template. '
             'Must be a local file path. '
             'Tokens to be interpolated must be of the form %VAR%.'),
        'service_definition':
            (str, None,
             'String of path to the Service Definition file template. '
             'Must be a local file path. '
             'Tokens to be interpolated must be of the form %VAR%. '
             'Implicit fields - do not include these: '
             "'serviceName', 'taskDefinition', 'desiredCount', 'clientToken'"),
        'service_name':
            (str, None,
             'Service name to use. If not specified, this will use '
             "the Task Definition's family."
             'Necessary if there is no given Task Definition.'),
        'tokens': (dict, {},
                   'A dictionary of key/value pairs '
                   'used to fill in the tokens for the Task and Service '
                   'definition templates.'),
        'count': ((int, str), 1,
                  'How many instances of the service to deploy. '
                  "Not used when state is 'absent'."),
        'wait': (bool, True,
                 'Whether to wait for the services to deploy. '
                 "Not used when state is 'absent'."),
        'use_existing_count': (
            bool, True,
            "Whether to use the existing service's count when updating "
            'instead of the specified count.'),
        'deregister_task_definitions': (
            bool, True,
            'Whether to deregister related Task Definitions. '
            "Only used when state is 'absent'.")
    }

    def __init__(self, *args, **kwargs):
        super(Service, self).__init__(*args, **kwargs)
        self.task_definition = self._load_task_definition(
            self.option('task_definition'),
            self.option('tokens'),
            self._init_tokens)
        self.service_definition = self._load_service_definition(
            self.option('service_definition'),
            self.option('tokens'),
            self._init_tokens)

    @gen.coroutine
    def _describe_service(self, service_name):
        """Describe a service by name.

        Args:
            service_name: service name to describe.

        Returns:
            Service description dict.

        Raises:
            RecoverableActorFailure if number of services found is not 1.
        """
        response = yield self.api_call(
            self.ecs_conn.describe_services,
            cluster=self.option('cluster'),
            services=[service_name])
        self._handle_failures(response['failures'], self.FAILURE_MISSING)

        services = response['services']

        # There should never be more than one service for a given name.
        if len(services) != 1:
            raise ServiceNotFound(
                'API returned {count} services for {name}'.format(
                    count=len(services), name=service_name))

        raise gen.Return(services[0])

    @staticmethod
    def _get_primary_deployment(service):
        """Gets the primary deployment from a service.

        Args:
            service: Result of _describe_service
                to get the primary deployment from.

        Returns:
            Primary deployment dict, or None if there is no primary deployment.
        """
        deployments = service['deployments']
        primary_deployment = None
        for deployment in deployments:
            if deployment['status'] == 'PRIMARY':
                primary_deployment = deployment
                break
        return primary_deployment

    @gen.coroutine
    def _wait_for_deployment_update(self, service_name, task_definition_name):
        """Wait's for a service's primary deployment to be updated.

        Args:
            service_name: Service name to wait for.
            task_definition_name: Expected Task Definition string.
        """
        repeating_log = utils.create_repeating_log(
            self.log.info,
            'Waiting for primary deployment to be updated to %s '
            'for service with name %s...' % (task_definition_name,
                                             service_name),
            seconds=30)

        while True:
            try:
                service = yield self._describe_service(service_name)
            except ServiceNotFound as e:
                self.log.info('Service Not Found: %s' % str(e))
                yield gen.sleep(2)
                continue

            primary_deployment = self._get_primary_deployment(service)
            if primary_deployment:
                self.log.info('Primary deployment is %s.' %
                              self._arn_to_name(
                                  primary_deployment['taskDefinition']))
                if self._is_task_in_deployment(
                        primary_deployment, task_definition_name):
                    self.log.info('Primary deployment updated.')
                    break
            yield gen.sleep(2)

        utils.clear_repeating_log(repeating_log)

    @gen.coroutine
    def _is_task_definition_different(self, old_task_definition_name,
                                      new_task_definition_name):
        """Checks if the actor's task definition is different
        than the given service's.

        Args:
            old_task_definition_name: Task Definition string of the
                old task definition.
            new_task_definition_name: Task Definition string of the
                new task definition.

        Returns:
            A boolean which is true if there are no differences.
        """
        old_task_definition = yield self._describe_task_definition(
            old_task_definition_name)
        new_task_definition = yield self._describe_task_definition(
            new_task_definition_name)

        del new_task_definition['taskDefinition']['revision']
        del new_task_definition['taskDefinition']['taskDefinitionArn']
        del old_task_definition['taskDefinition']['revision']
        del old_task_definition['taskDefinition']['taskDefinitionArn']

        raise gen.Return(old_task_definition != new_task_definition)

    @gen.coroutine
    @dry('Would create service')
    def _create_service(self, service_name):
        """Create a service.

        Args:
            service_name: Service name to use.

        Returns:
            task_definition_name: Task Definition string that was registered.
        """
        # Need to register a new task definition and deploy.
        task_definition_name = yield self._register_task(
            self.task_definition)

        create_parameters = dict(
            cluster=self.option('cluster'),
            serviceName=service_name,
            taskDefinition=task_definition_name,
            desiredCount=self.option('count'),
            **self.service_definition)

        self.log.info('Creating service.')

        yield self.api_call(
            self.ecs_conn.create_service,
            **create_parameters)

        yield self._wait_for_deployment_update(service_name,
                                               task_definition_name)
        self.log.info('Finished creating service.')
        raise gen.Return(task_definition_name)

    @gen.coroutine
    @dry('Would update service')
    def _update_service(self, service_name, existing_service, override=None):
        """Update a service.

        Args:
            service_name: Service name to use.
            existing_service: Result of _describe_service
                on the existing service.
            override: List of tuples of key:value to override.

        Returns:
            Task Definition string that was updated or registered.
        """
        update_parameters = dict(
            cluster=self.option('cluster'),
            service=service_name,
            **self.service_definition)

        # Remove any fields that aren't allowed on update.
        for immutable_field in self._immutable_fields():
            update_parameters.pop(immutable_field, None)

        old_task_definition_name = self._arn_to_name(
            existing_service['taskDefinition'])
        task_definition_name = old_task_definition_name

        is_new_task_definition = False
        if self.task_definition:
            new_task_definition_name = yield self._register_task(
                self.task_definition)
            is_new_task_definition = yield self._is_task_definition_different(
                old_task_definition_name,
                new_task_definition_name)
            if is_new_task_definition:
                self.log.info(
                    'The task definition is different, using the new one.')
                # Need to use the new task definition.
                update_parameters.update({
                    'taskDefinition': new_task_definition_name})
                task_definition_name = new_task_definition_name
            else:
                self.log.info(
                    'The task definition is the same, using the old one.')
                yield self._deregister_task_definition(
                    new_task_definition_name)
                task_definition_name = old_task_definition_name

        if override is not None:
            update_parameters.update(override)

        self.log.info('Updating service.')
        self.log.info('Checking if existing service is active...')
        service_is_active = (existing_service and
                             existing_service['status'] != 'INACTIVE')
        if not service_is_active:
            # We can only update an existing, active service.
            self.log.error(
                'Could not find service with name {} to update '
                'in {}. Update is likely to fail!'.format(
                    service_name, self._format_location()))
            current_primary_deployment = self._get_primary_deployment(
                existing_service)
            self.log.info(
                'Current primary deployment task definition is: {}'.format(
                    current_primary_deployment['taskDefinition']))
            current_service_description = str(self._describe_service(
                service_name))
            self.log.info(
                'Service description is: {}'.format(
                    current_service_description))
        yield self.api_call(
            self.ecs_conn.update_service,
            **update_parameters)

        if is_new_task_definition:
            yield self._wait_for_deployment_update(service_name,
                                                   task_definition_name)
        self.log.info('Finished updating service.')
        raise gen.Return(task_definition_name)

    @gen.coroutine
    @dry('Would stop service')
    def _stop_service(self, service_name, existing_service):
        """Stop all the tasks in a service.

        Args:
            service_name: name of the service to stop.
            existing_service: result of _describe_service on the given
                service name.
        """
        self.log.info('Shutting down all current tasks in %s.' % service_name)
        task_definition_name = yield self._update_service(
            service_name,
            existing_service,
            override={'desiredCount': 0})
        yield self._wait_for_service_update(service_name, task_definition_name)
        self.log.info('Service {} stopped successfully.'.format(service_name))

    @gen.coroutine
    @dry('Would delete service')
    def _delete_service(self, service_name, existing_service,
                        deregister=True):
        """Delete a service.

        This also deregisters task definitions with the same family
        unless deregister is False.

        Args:
            service_name: name of the service to delete.
            existing_service: result of _describe_service on the given
                service name.
            deregister: Whether to deregister related Task Definitions.
        """
        status = existing_service['status']
        if status != 'ACTIVE':
            # Either DRAINING or INACTIVE
            self.log.info(
                'Service {} is already not active, is {}.'.format(
                    service_name, status))
        else:
            yield self._stop_service(service_name, existing_service)
            yield self.api_call(self.ecs_conn.delete_service,
                                cluster=self.option('cluster'),
                                service=service_name)
        if deregister:
            task_definition_names = yield self._list_task_definitions(
                status='ACTIVE',
                family_prefix=service_name)
            for task_definition_name in task_definition_names:
                yield self._deregister_task_definition(task_definition_name)

    def _is_task_in_deployment(self, deployment, task_definition_name):
        """Checks whether the given task definition is in the deployment.
        This is useful for checking that we're looking at the right deployment.

        Args:
            deployment: Deployment to check.
            task_definition_name: Task Definition string to look for.

        Returns:
            A boolean, true if the deployment has the task definition.
        """
        return task_definition_name == self._arn_to_name(
            deployment['taskDefinition'])

    def _check_immutable_field_errors(self, old_params, new_params,
                                      immutable_fields):
        """Compares an old service definition to a new one
         to ensure that all of the specified immutable fields
         are the same between them.

        If there are any errors,
        this logs them and raises RecoverableActorFailure.

        Args:
            old_params: old parameters to use.
            new_params: new parameters to compare with.
            immutable_fields: list of immutable fields.
        """
        # API does not return role name, only the role arn.
        role_arn = old_params.get('roleArn')
        role = None
        if role_arn:
            role = self._arn_to_name(role_arn)
        old_params['role'] = role

        has_error = False
        for immutable_field_name in immutable_fields:
            new_field = new_params.get(immutable_field_name)
            old_field = old_params.get(immutable_field_name)

            # If the newly supplied fields are None, then they aren't defined
            # in the service definition at all. It's OK to ignore them.
            if new_field is None:
                continue

            # If the supplied fields are an empty list, treat them also as an
            # null field and move on.
            if isinstance(new_field, list) and len(new_field) == 0:
                continue

            if new_field != old_field:
                has_error = True
                self.log.error(
                    "Field \'{field}\' cannot be updated.\n"
                    'Old value: {old}\n'
                    'New value: {new}'.format(
                        field=immutable_field_name,
                        old=old_field,
                        new=new_field))

        if has_error:
            raise exceptions.RecoverableActorFailure(
                'Immutable fields cannot be updated. '
                'A new service must be created.')

    def _immutable_fields(self):
        """
        Return: List of all fields that ECS doesn't allow mutation on.
        """
        return [
            'loadBalancers', 'launchType', 'role',
            'placementConstraints', 'placementStrategy']

    @gen.coroutine
    @dry('Would wait for service to update its state successfully')
    def _wait_for_service_update(self, service_name, task_definition_name):
        """Wait for the service's state to successfully update.

        If the service fails to be updated for some reason,
        e.g. failing to come up during deployment,
        this will raise an exception.

        Args:
            service_name: name of the service to wait for.
            task_definition_name: Task Definition string.
        """
        # Create set used to ensure event logs are only printed once.
        self.seen_events = set()
        while True:
            done = yield self._is_service_updated(
                service_name, task_definition_name)
            if done:
                break
            yield gen.sleep(10)

    @gen.coroutine
    @utils.retry(excs=exceptions.RecoverableActorFailure,
                 retries=settings.ECS_RETRY_ATTEMPTS,
                 delay=settings.ECS_RETRY_DELAY)
    def _is_service_updated(self, service_name, task_definition_name):
        """Checks if service's state updates successfully.
        Meant to be called in a wait-loop.

        Args:
            service_name: name of the service to wait for.
            task_definition_name: Task Definition string.

        Returns:
            A boolean indicating whether the service is completely updated.
        """
        service = yield self._describe_service(service_name)

        deployments = service['deployments']
        primary_deployment = self._get_primary_deployment(service)
        if not primary_deployment:
            # There should always be one 'PRIMARY' deployment returned.
            raise exceptions.RecoverableActorFailure(
                'No primary deployment.')

        # Verify that the primary deployment has the correct task definition.
        if not self._is_task_in_deployment(
                primary_deployment, task_definition_name):
            raise exceptions.RecoverableActorFailure(
                'Primary deployment was for {}, not {}.'.format(
                    self._arn_to_name(primary_deployment['taskDefinition']),
                    task_definition_name))

        service_timestamp = primary_deployment['updatedAt']

        sorted_new_events = self._get_sorted_new_log_events(
            events=service['events'],
            start_timestamp=service_timestamp)

        for event in sorted_new_events:
            event_timestamp, event_message = event
            self.log.info('Event [{}]: {}'.format(event_timestamp,
                                                  event_message))

        running_count = primary_deployment['runningCount']
        desired_count = primary_deployment['desiredCount']
        missing_count = desired_count - running_count

        extra_deployment_count = len(deployments) - 1

        if missing_count == 0 and extra_deployment_count == 0:
            raise gen.Return(True)

        self.log.info(
            '{} tasks running out of {}, '
            'and {} deployments waiting on termination.'.format(
                running_count, desired_count, extra_deployment_count))
        raise gen.Return(False)

    def _get_sorted_new_log_events(self, events, start_timestamp):
        """Retrieves a list of sorted, new log events.

        Only logs events which:
            Have timestamps greater than start_timestamp.
            Have not been logged before (based on self.seen_events).

        Args:
            events: list of event dicts.
                Must have fields 'id', 'message', and 'createdAt'.
            start_timestamp: timestamp before which to ignore events.

        Returns:
            A list of event tuples like [(event_timestamp, event_message)...]
        """
        # Get list of all new events.
        new_events = []
        for event in events:
            event_id = event['id']
            event_message = event['message']
            event_timestamp = event['createdAt']
            if event_timestamp < start_timestamp:
                continue
            if event_id in self.seen_events:
                continue
            self.seen_events.add(event_id)
            new_events.append((event_timestamp, event_message))

        # Sort events on timestamp.
        return sorted(new_events, key=operator.itemgetter(0))

    @gen.coroutine
    @dry('Would ensure the service is absent')
    def _ensure_service_absent(self, service_name, existing_service):
        """Ensures a service is absent.

        Args:
            service_name: service name to use.
            existing_service:
                Result of _describe_service on the given service name.
        """
        if existing_service:
            yield self._delete_service(
                service_name, existing_service,
                deregister=self.option('deregister_task_definitions'))
            self.log.info(
                'Service {} deleted successfully in {}.'.format(
                    service_name, self._format_location()))
        else:
            self.log.info(
                'Service {} already absent in {}.'.format(
                    service_name, self._format_location()))

    @gen.coroutine
    @dry('Would ensure the service is present')
    def _ensure_service_present(self, service_name, existing_service):
        """Ensures a service is present.

        Args:
            service_name: service name to use.
            existing_service:
                Result of _describe_service on the given service name.
        """
        service_is_active = (existing_service and
                             existing_service['status'] != 'INACTIVE')
        if not service_is_active and not self.task_definition:
            # Without a task definition,
            # we can only update an existing service.
            self.log.error(
                'Could not find service with name {} to update '
                'in {}.'.format(
                    service_name, self._format_location()))
            raise exceptions.RecoverableActorFailure(
                'Cannot update non-existant service.')

        if service_is_active:
            # Service already exists - update it.
            # Ensure no immutable fields were mutated.
            self._check_immutable_field_errors(
                old_params=existing_service,
                new_params=self.service_definition,
                immutable_fields=self._immutable_fields())
            override = None
            if not self.option('use_existing_count'):
                override = {'desiredCount': self.option('count')}
            task_definition_name = yield self._update_service(
                service_name, existing_service, override=override)
        else:
            task_definition_name = yield self._create_service(service_name)

        if self.option('wait'):
            yield self._wait_for_service_update(
                service_name, task_definition_name)
            self.log.info(
                'Service {} updated successfully in {}.'.format(
                    service_name, self._format_location()))
        else:
            self.log.info(
                'Not waiting for service {} to finish updating '
                'in {}.'.format(
                    service_name, self._format_location()))

    @gen.coroutine
    def _execute(self):
        # Get service name
        if self.task_definition:
            service_name = (
                self.option('service_name') or
                self.task_definition['family'])
        else:
            service_name = self.option('service_name')

        if not service_name:
            raise exceptions.RecoverableActorFailure(
                'Either service_name or task_definition must be provided.')
        # Get existing service
        try:
            existing_service = yield self._describe_service(service_name)
        except ServiceNotFound:
            existing_service = None

        # Ensure state
        desired_state = self.option('state')
        if desired_state == 'present':
            yield self._ensure_service_present(service_name, existing_service)
        elif desired_state == 'absent':
            yield self._ensure_service_absent(service_name, existing_service)
