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

import json
import logging
import mock

from boto.exception import S3ResponseError
from boto.exception import BotoServerError
from tornado import concurrent
from tornado import gen

from kingpin.actors import exceptions
from kingpin.actors.aws import base
from kingpin.constants import SchemaCompareBase
from kingpin.constants import REQUIRED
from kingpin.constants import STATE

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com'


# This executor is used by the tornado.concurrent.run_on_executor()
# decorator. We would like this to be a class variable so its shared
# across RightScale objects, but we see testing IO errors when we
# do this.
EXECUTOR = concurrent.futures.ThreadPoolExecutor(10)


class InvalidBucketConfig(exceptions.RecoverableActorFailure):

    """Raised whenever an invalid option is passed to a Bucket"""


class LoggingConfig(SchemaCompareBase):

    """Provides JSON-Schema based validation of the supplied logging config.

    The S3 LoggingConfig format should look like this:

    .. code-block:: json

        { "target": "s3_bucket_name_here",
          "prefix": "an_optional_prefix_here" }

    If you supply an empty `target`, then we will explicitly remove the logging
    configuration from the bucket. Example:

    .. code-block:: json

        { "target": "" }

    """

    SCHEMA = {
        'type': 'object',
        'required': ['target'],
        'additionalProperties': False,
        'properties': {
            'target': {'type': 'string'},
            'prefix': {'type': 'string'}
        }
    }

    valid = '{ "target": "<bucket name>", [ "prefix": "<logging prefix>" ]}'


class S3BaseActor(base.AWSBaseActor):

    """Base class for S3 actors."""

    all_options = {
        'name': (str, REQUIRED, 'Name of the S3 Bucket'),
        'state': (STATE, 'present',
                  'Desired state of the bucket: present/absent'),
        'logging': (LoggingConfig, None,
                    'Dict with the logging configuration information.'),
        'policy': ((str, None), None,
                   'Path to the JSON policy file to apply to the bucket.'),
        'region': (str, REQUIRED, 'AWS region (or zone) name, like us-west-2')
    }


class Bucket(S3BaseActor):

    """Manage the state of a single S3 Bucket.

    The actor has the following functionality:

      * Ensure that an S3 bucket is present or absent.
      * Manage the bucket policy.

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

    :logging:
      (LoggingConfig, None)

      If a dictionary is supplied (`{'target': 'logging_bucket', 'prefix':
      '/mylogs'}`), then we will configure bucket logging to the supplied
      bucket and prefix. If `prefix` is missing then no prefix will be used.

      If `target` is supplied as an empty string (`''`), then we will disable
      logging on the bucket. If `None` is supplied, we will not manage logging
      either way.

    :policy:
      (str, None) A JSON file with the bucket policy. Passing in a blank string
      will cause any policy to be deleted. Passing in None (or not passing it
      in at all) will cause Kingpin to ignore the policy for the bucket
      entirely. Default: None

    :region:
      AWS region (or zone) name, such as us-east-1 or us-west-2

    **Examples**

    .. code-block:: json

       { "actor": "aws.s3.Bucket",
         "options": {
           "name": "kingpin-integration-testing",
           "region": "us-west-2",
           "policy": "./examples/aws.s3/amazon_put.json",
           "logging": {
             "target": "logs.myco.com",
             "prefix": "/kingpin-integratin-testing"
           },
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

    def __init__(self, *args, **kwargs):
        super(Bucket, self).__init__(*args, **kwargs)

        # If the policy is None, or '', we simply set it to self.policy. If its
        # anything else, we parse it.
        self.policy = self.option('policy')
        if self.option('policy'):
            self.policy = self._parse_policy_json(self.option('policy'))

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
        name = self.option('name')
        self.log.info('Ensuring that s3://%s is %s' % (name, state))
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
        # If we're running in DRY mode, then we create a fake bucket object
        # that will be passed back. This mock object lets us simplify the rest
        # of our code because we can mock out the results of creating a fresh
        # empty bucket with no policies, versions, etc.
        if self._dry:
            self.log.warning('Would have created s3://%s' %
                             self.option('name'))

            # Generate a fake bucket and return it
            mock_bucket = mock.MagicMock(name=self.option('name'))

            # Mock out the get_policy function to raise a 404 because there is
            # no policy attached to buckets by default. This is used to trick
            # the self._ensure_policy() function.
            mock_bucket.get_policy.side_effect = S3ResponseError(404, 'Empty')

            raise gen.Return(mock_bucket)

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
    def _ensure_policy(self, bucket):
        """Ensure the policy attached to the bucket is correct.

        (Note, this method is longer than we'd like .. but in this Bucket actor
        is going to do _a lot_ of things, so encapsulating the logic all in a
        single method makes the rest of the code easier to read and
        understand.)

        args:
            bucket: The S3 bucket object as returned by Boto
        """
        new = self.policy
        exist = {}

        # Get our existing policy and convert it into a dict we can deal with
        try:
            raw = yield self.thread(bucket.get_policy)
            exist = json.loads(raw)
        except S3ResponseError as e:
            if e.status != 404:
                raise exceptions.RecoverableActorFailure(
                    'An unexpected error occurred: %s' % e)

        # Now, if we're deleting the policy (policy=''), then optionally do
        # that and bail.
        if new == '':
            # If no existing policy was found, just get us out of this function
            if not exist:
                raise gen.Return()

            if self._dry:
                self.log.warning('Would have deleted bucket policy')
                raise gen.Return()

            self.log.info('Deleting bucket policy')
            try:
                yield self.thread(bucket.delete_policy)
            except S3ResponseError as e:
                raise exceptions.RecoverableActorFailure(
                    'An unexpected error occurred: %s' % e)
            raise gen.Return()

        # Now, diff our new policy from the existing policy. If there is no
        # difference, then we bail out of the method.
        diff = self._diff_policy_json(exist, new)
        if not diff:
            self.log.debug('Bucket policy matches')
            raise gen.Return()

        # Now, print out the diff..
        self.log.info('Bucket policy differs from Amazons:')
        for line in diff.split('\n'):
            self.log.info('Diff: %s' % line)

        # Final DRY check ... if dry, get out of here.
        if self._dry:
            self.log.warning('Would have pushed bucket policy %s'
                             % self.option('policy'))
            raise gen.Return()

        # Push the new policy!
        self.log.info('Pushing bucket policy %s' % self.option('policy'))
        self.log.debug('Policy doc: %s' % new)
        try:
            yield self.thread(bucket.set_policy, json.dumps(new))
        except S3ResponseError as e:
            if e.error_code == 'MalformedPolicy':
                raise base.InvalidPolicy(e.message)

            raise exceptions.RecoverableActorFailure(
                'An unexpected error occurred: %s' % e)
        raise gen.Return()

    @gen.coroutine
    def _ensure_logging(self, bucket):
        """Ensure that the bucket logging configuration is setup.

        args:
            bucket: The S3 bucket object as returned by Boto
        """
        # Get the buckets current logging configuration
        existing = yield self.thread(bucket.get_logging_status)

        # Shortcuts for our desired logging state
        desired = self.option('logging')

        # If desired is False, check the state, potentially disable it, and
        # then bail out.
        if desired['target'] == '':
            if existing.target is None:
                self.log.debug('Logging is already disabled on this bucket')
                raise gen.Return()

            if self._dry:
                self.log.warning('Bucket logging target is %s, would disable.'
                                 % existing.target)
                raise gen.Return()

            self.log.info('Deleting Bucket logging configuration')
            yield self.thread(bucket.disable_logging)
            raise gen.Return()

        # Simple shortcut name for some logging
        target_str = 's3://%s/%s' % (desired['target'],
                                     desired['prefix'].lstrip('/'))

        # If desired has a logging or prefix config, check each one and
        # validate that they are correct.
        if (desired['target'] != existing.target or
                desired['prefix'] != existing.prefix):
            if self._dry:
                self.log.warning('Bucket logging config would be updated to '
                                 '%s' % target_str)
                raise gen.Return()

            self.log.info('Updating Bucket logging config to %s' % target_str)
            try:
                yield self.thread(bucket.enable_logging,
                                  desired['target'],
                                  desired['prefix'])
            except S3ResponseError as e:
                if e.error_code == 'InvalidTargetBucketForLogging':
                    raise InvalidBucketConfig(e.message)
                raise exceptions.RecoverableActorFailure(
                    'An unexpected error occurred. %s' % e)

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        raises: gen.Return(True)
        """
        bucket = yield self._ensure_bucket()

        # If we're deleting the bucket, then there is no need to continue after
        # we've done that.
        if self.option('state') == 'absent':
            raise gen.Return()

        # Only manage the policy if self.policy was actually set.
        if self.policy is not None:
            yield self._ensure_policy(bucket)

        # Only manage the logging config if the logging config was supplied
        if self.option('logging') is not None:
            yield self._ensure_logging(bucket)

        raise gen.Return()
