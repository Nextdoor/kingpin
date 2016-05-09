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
# Copyright 2016 Nextdoor.com, Inc

"""
:mod:`kingpin.actors.aws.s3`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
"""

import logging

from boto.exception import S3ResponseError
from boto.exception import BotoServerError
from tornado import concurrent
from tornado import gen

from kingpin.actors import exceptions
from kingpin.actors.aws import base
from kingpin.constants import REQUIRED
from kingpin.constants import STATE

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com'


# This executor is used by the tornado.concurrent.run_on_executor()
# decorator. We would like this to be a class variable so its shared
# across RightScale objects, but we see testing IO errors when we
# do this.
EXECUTOR = concurrent.futures.ThreadPoolExecutor(10)


class S3BaseActor(base.AWSBaseActor):

    """Base class for S3 actors."""

    all_options = {
        'name': (str, REQUIRED, 'Name of the S3 Bucket'),
        'state': (STATE, 'present',
                         'Desired state of the bucket: present/absent'),
        'region': (str, REQUIRED, 'AWS region (or zone) name, like us-west-2')
    }


class Bucket(S3BaseActor):

    """Manage the state of a single S3 Bucket.

    The actor has the following functionality:

      * Ensure that an S3 bucket is present or absent.

    **Note about Buckets with Files**

    Amazon requires that an S3 bucket be empty in order to delete it. Although
    we could recursively search for all files in the bucket and then delete
    them, this is a wildly dangerous thing to do inside the confines of this
    actor. Instead, we raise an exception and alert the you to the fact that
    they need to delete the files themselves.

    **Options**

    :name:
      The name of the bucket to operate on

    :state:
      (str) Present or Absent. Default: "present"

    :region:
      AWS region (or zone) name, such as us-east-1 or us-west-2

    **Examples**

    .. code-block:: json

       { "actor": "aws.s3.Bucket",
         "options": {
           "name": "production-logs",
           "region": "us-west-2"
         }
       }


    **Dry Mode**

    Finds the bucket if it exists (or tells you it would create it). Describes
    each potential change it would make to the bucket depending on the
    configuration of the live bucket, and the options that were passed into the
    actor.

    Will gracefully fail and alert you if there are files in the bucket and you
    are trying to delete it.
    """

    desc = "S3 Bucket {name}"

    @gen.coroutine
    def _get_bucket(self):
        """Retrives the existing S3 bucket object, or None.

        Returns either the S3 bucket or None if the bucket doesn't exist. Note,
        the boto.s3.lookup() method claims to do this, but has odd inconsistent
        behavior where it returns None very quickly sometimes. Also, it does
        not help us determine whether or not the bucket we find is in the
        target region we actually intended to use.

        Returns:
          <A Boto.s3.Bucket object> or None
        """
        try:
            bucket = yield self.thread(self.s3_conn.get_bucket,
                                       self.option('name'))
        except BotoServerError as e:
            if e.status == 301:
                raise exceptions.RecoverableActorFailure(
                    'Bucket %s exists, but is not in %s' %
                    (self.option('name'), self.option('region')))
            if e.status == 404:
                self.log.debug('No bucket %s found' % self.option('name'))
                raise gen.Return(None)

            raise exceptions.RecoverableActorFailure(
                'An unexpected error occurred: %s' % e)

        self.log.debug('Found bucket %s' % bucket)
        raise gen.Return(bucket)

    @gen.coroutine
    def _ensure_bucket(self):
        """Ensures a bucket exists or does not."""
        # Determine if the bucket already exists or not
        state = self.option('state')
        bucket = yield self._get_bucket()

        if state == 'absent' and bucket is None:
            self.log.debug('Bucket does not exist')
        elif state == 'absent' and bucket:
            yield self._delete_bucket(bucket)
            bucket = None
        elif state == 'present' and bucket is None:
            bucket = yield self._create_bucket()
        elif state == 'present' and bucket:
            self.log.debug('Bucket exists')

        raise gen.Return(bucket)

    @gen.coroutine
    def _create_bucket(self):
        """Creates an S3 bucket if its missing.

        returns:
            <A boto.s3.Bucket object>
        """
        if self._dry:
            self.log.warning('Would have created s3://%s' %
                             self.option('name'))
            raise gen.Return()

        # This throws no exceptions, even if the bucket exists, that we know
        # about or can expect.
        self.log.info('Creating bucket')
        bucket = yield self.thread(self.s3_conn.create_bucket,
                                   self.option('name'))
        raise gen.Return(bucket)

    @gen.coroutine
    def _delete_bucket(self, bucket):
        """Tries to delete an S3 bucket.

        args:
            bucket: The S3 bucket object as returned by Boto
        """
        # Find out if there are any files in the bucket before we go to delete
        # it. We cannot delete a bucket with files in it -- nor do we want to.
        keys = yield self.thread(bucket.get_all_keys)
        if len(keys) > 0:
            raise exceptions.RecoverableActorFailure(
                'Cannot delete bucket with keys: %s files found' % len(keys))

        if self._dry:
            self.log.warning('Would have deleted bucket %s' % bucket)
            raise gen.Return()

        try:
            self.log.info('Deleting bucket %s' % bucket)
            yield self.thread(bucket.delete)
        except S3ResponseError as e:
            if e.status == 409:
                raise exceptions.RecoverableActorFailure(
                    'Cannot delete bucket: %s' % e.message)

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        raises: gen.Return(True)
        """
        yield self._ensure_bucket()

        # We don't go any further -- if we're deleting the bucket, we're done
        # here. Just return.
        if self.option('state') == 'absent':
            raise gen.Return()

        raise gen.Return()
