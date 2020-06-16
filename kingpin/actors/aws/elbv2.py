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
:mod:`kingpin.actors.aws.elbv2`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
"""

import logging

from tornado import concurrent
from tornado import gen

from kingpin.actors import exceptions
from kingpin.actors.aws import base
from kingpin.actors.utils import dry
from kingpin.constants import REQUIRED

import botocore.exceptions

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


# This executor is used by the tornado.concurrent.run_on_executor()
# decorator. We would like this to be a class variable so its shared
# across RightScale objects, but we see testing IO errors when we
# do this.
EXECUTOR = concurrent.futures.ThreadPoolExecutor(10)


class RegisterInstance(base.AWSBaseActor):

    """Add an EC2 instance to a target group.

    **Options**

    :target_group:
      (str) Name of the Target Group ARN or its short name

    :instances:
      (str, list) Instance id, or list of ids. Default "self" id.

    :region:
      (str) AWS region (or zone) name, like us-west-2

    **Example**

    .. code-block:: yaml

       ---
       actor: aws.elbv2.RegisterInstance
       desc: Run RegisterInstance
       options:
         target_group: prod-loadbalancer
         instances: i-123456
         region: us-east-1

    **Dry run**

    Will find the specified Target Group, but not take any actions regarding
    instances.
    """

    all_options = {
        'target_group': (str, REQUIRED,
                         'Name of the Target Group or its full ARN'),
        'region': (str, REQUIRED, 'AWS region (or zone) name, like us-west-2'),
        'instances': ((str, list), None, (
            'Instance id, or list of ids. If no value is specified then '
            'the instance id of the executing machine is used.'))
    }

    @gen.coroutine
    @dry('Would add {1} to {0}')
    def _add(self, arn, targets):
        """Registers the supplied Targets with the Target Group ARN.

        http://boto3.readthedocs.io/en/latest/reference/services/
        elbv2.html#ElasticLoadBalancingv2.Client.register_targets

        Args:
            arn: ELBv2 Target ARN
            targets: A list of Instance IDs or Target IP Addresses.
        """

        #  TODO: In the future, add support for the optional Port and
        #  AvailabilityZone parameters. For now, keeping this dead simple.
        targets = [{'Id': t} for t in targets]

        try:
            yield self.api_call(
                self.elbv2_conn.register_targets,
                TargetGroupArn=arn,
                Targets=targets)
        except botocore.exceptions.ClientError as e:
            raise exceptions.UnrecoverableActorFailure(str(e))

    @gen.coroutine
    def _execute(self):
        arn = yield self._find_target_group(self.option('target_group'))
        instances = self.option('instances')

        if not instances:
            self.log.debug('No instance provided. Using current instance id.')
            iid = yield self._get_meta_data('instance-id')
            instances = [iid]
            self.log.debug('Instances is: %s' % instances)

        if type(instances) is not list:
            instances = [instances]

        self.log.info(('Adding the following instances to Target Group: '
                       '%s' % ', '.join(instances)))
        yield self._add(arn, instances)


class DeregisterInstance(base.AWSBaseActor):

    """Remove EC2 instance(s) from a Target Group.

    **Options**

    :elb:
      (str) Name of the Target Group.

    :instances:
      (str, list) Instance id, or list of ids

    :region:
      (str) AWS region (or zone) name, like us-west-2

    **Example**

    .. code-block:: yaml

       actor: aws.elbv2.DeregisterInstance
       desc: Run DeregisterInstance
       options:
         target_group: my-webserver-elb
         instances: i-abcdeft
         region: us-west-2

    **Dry run**

    Will find the Target Group but not take any actions regarding the
    instances.
    """

    all_options = {
        'target_group': (str, REQUIRED,
                         'Name of the Target Group or its full ARN'),
        'region': (str, REQUIRED, 'AWS region (or zone) name, like us-west-2'),
        'instances': ((str, list), None, (
            'Instance id, or list of ids. If no value is specified then '
            'the instance id of the executing machine is used.')),
    }

    @gen.coroutine
    @dry('Would remove instances from {0}: {1}')
    def _remove(self, arn, targets):
        """Deregisters the supplied Targets with the Target Group ARN.

        http://boto3.readthedocs.io/en/latest/reference/services/
        elbv2.html#ElasticLoadBalancingv2.Client.deregister_targets

        Args:
            arn: ELBv2 Target ARN
            targets: A list of Instance IDs or Target IP Addresses.
        """
        #  TODO: In the future, add support for the optional Port and
        #  AvailabilityZone parameters. For now, keeping this dead simple.
        targets = [{'Id': t} for t in targets]

        try:
            yield self.api_call(
                self.elbv2_conn.deregister_targets,
                TargetGroupArn=arn,
                Targets=targets)
        except botocore.exceptions.ClientError as e:
            raise exceptions.UnrecoverableActorFailure(str(e))

    @gen.coroutine
    def _execute(self):
        arn = yield self._find_target_group(self.option('target_group'))
        instances = self.option('instances')

        if not instances:
            self.log.debug('No instance provided. Using current instance id.')
            iid = yield self._get_meta_data('instance-id')
            instances = [iid]
            self.log.debug('Instances is: %s' % instances)

        if type(instances) is not list:
            instances = [instances]

        self.log.info(
            ('Removing the following instances from the target group: '
             '%s' % ', '.join(instances)))
        yield self._remove(arn, instances)
