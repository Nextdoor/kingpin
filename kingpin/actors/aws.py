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

"""Misc Actor objects"""

import logging
import os

from tornado import gen

import boto.sqs.connection
import boto.sqs.queue

from kingpin.actors import base

# TODO(Matt): move thread_coroutine to some global location
from kingpin.actors.rightscale.api import thread_coroutine

log = logging.getLogger(__name__)

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'

SECRET_KEY = os.getenv('AWS_SECRET_KEY', None)
ACCESS_KEY = os.getenv('AWS_ACCESS_KEY', None)


class CreateSQSQueue(base.HTTPBaseActor):
    """Creates a new SQS Queue."""

    required_options = ['name']

    def __init__(self, *args, **kwargs):
        """Initializes the Actor.

        Args:
            desc: String description of the action being executed.
            options: Dictionary with the following settings:
              { 'name': queue name }
        """
        super(CreateSQSQueue, self).__init__(*args, **kwargs)

        self._queue_name = self._options['name']

    @gen.coroutine
    def _create_queue(self):
        # boto pools connections
        conn = boto.sqs.connection.SQSConnection(SECRET_KEY, ACCESS_KEY)
        new_queue = conn.create_queue(self._queue_name)

        raise gen.Return(new_queue)



    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        raises: gen.Return(True)
        """
        self._log(logging.INFO,
                  'Creating a new SQS Queue "%s"' %
                  self._queue_name)
        future = yield thread_coroutine(self._create_queue)
        q = future.result()

        if q.__class__ == boto.sqs.queue.Queue:
            self._log(logging.INFO, 'Queue Created: %s' % q.url)
        else:
            raise Exception('All hell broke loose: %s' % q)

        raise gen.Return(True)
