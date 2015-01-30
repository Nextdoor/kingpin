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

"""AWS Base Actor"""

import logging
import requests

from boto.exception import BotoServerError
from concurrent import futures
from tornado import concurrent
from tornado import gen
from tornado import ioloop
import boto.ec2.elb

from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.actors.aws import settings as aws_settings

log = logging.getLogger(__name__)

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'

AWS_META_URL = 'http://169.254.169.254/latest'

EXECUTOR = futures.ThreadPoolExecutor(10)


class ELBNotFound(exceptions.RecoverableActorFailure):

    """Raised when an ELB is not found"""


class AWSBaseActor(base.BaseActor):

    # Get references to existing objects that are used by the
    # tornado.concurrent.run_on_executor() decorator.
    ioloop = ioloop.IOLoop.current()
    executor = EXECUTOR

    def __init__(self, *args, **kwargs):
        """Check for required settings."""

        super(AWSBaseActor, self).__init__(*args, **kwargs)

        if not (aws_settings.AWS_ACCESS_KEY_ID and
                aws_settings.AWS_SECRET_ACCESS_KEY):
            raise exceptions.InvalidCredentials(
                'AWS settings imported but not all credentials are supplied. '
                'AWS_ACCESS_KEY_ID: %s, AWS_SECRET_ACCESS_KEY: %s' % (
                    aws_settings.AWS_ACCESS_KEY_ID,
                    aws_settings.AWS_SECRET_ACCESS_KEY))

        region = self.option('region')
        if region:
            self.elb_conn = boto.ec2.elb.connect_to_region(
                region,
                aws_access_key_id=aws_settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=aws_settings.AWS_SECRET_ACCESS_KEY)

    @concurrent.run_on_executor
    def _find_elb(self, name):
        """Return an ELB with the matching name.

        Must find exactly 1 match. Zones are limited by the AWS credentials.

        Args:
            name: String-name of the ELB to search for

        Returns:
            A single ELB reference object

        Raises:
            ELBNotFound
        """
        self.log.info('Searching for ELB "%s"' % name)

        try:
            elbs = self.elb_conn.get_all_load_balancers(
                load_balancer_names=name)
        except BotoServerError as e:
            raise ELBNotFound(e)

        self.log.debug('ELBs found: %s' % elbs)

        if len(elbs) != 1:
            raise ELBNotFound('Expected to find exactly 1 ELB. Found %s: %s'
                              % (len(elbs), elbs))

        return elbs[0]

    @gen.coroutine
    def _get_meta_data(self, key):
        meta = requests.get(AWS_META_URL + '/' + key)
        raise gen.Return(meta.text)
