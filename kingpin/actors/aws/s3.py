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

from boto.s3 import lifecycle
from boto.exception import S3ResponseError
from boto.exception import BotoServerError
from tornado import concurrent
from tornado import gen
import jsonpickle

from kingpin.actors import exceptions
from kingpin.actors.utils import dry
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
        'type': ['object', 'null'],
        'required': ['target'],
        'additionalProperties': False,
        'properties': {
            'target': {'type': 'string'},
            'prefix': {'type': 'string'}
        }
    }

    valid = '{ "target": "<bucket name>", [ "prefix": "<logging prefix>" ]}'


class LifecycleConfig(SchemaCompareBase):

    """Provides JSON-Schema based validation of the supplied Lifecycle config.

    The S3 Lifecycle system allows for many unique configurations. Each
    configuration object defined in this schema will be turned into a
    :py:class:`boto.s3.lifecycle.Rule` object. All of the rules together will
    be turned into a :py:class:`boto.s3.lifecycle.Lifecycle` object.

    .. code-block:: json

        [
          { "id": "unique_rule_identifier",
            "prefix": "/some_path",
            "status": "Enabled",
            "expiration": 365,
            "transition": {
              "days": 90,
              "date": "2016-05-19T20:04:17+00:00",
              "storage_class": "GLACIER",
            }
          }
        ]
    """

    SCHEMA = {
        # The outer wrapper must be a list of properly formatted objects,
        # or Null if we are not going to manage this configuration at all.
        'type': ['array', 'null'],
        'uniqueItems': True,
        'items': {
            'type': 'object',
            'required': ['id', 'prefix', 'status'],
            'additionalProperties': False,
            'properties': {
                # The ID and Prefix must be strings. We do not allow for them
                # to be empty -- they must be defined.
                'id': {
                    'type': 'string',
                    'minLength': 1,
                    'maxLength': 255,
                },
                'prefix': {'type': 'string'},

                # The Status field must be 'Enabled' or 'Disabled'
                'status': {
                    'type': 'string',
                    'enum': ['Enabled', 'Disabled'],
                },

                # Expiration and Transition can be empty, or have
                # configurations associated with them.
                'expiration': {
                    'type': ['string', 'integer'],
                    'pattern': '^[0-9]+$',
                },
                'transition': {
                    'type': ['object', 'null'],
                    'required': ['storage_class'],
                    'properties': {
                        'days': {
                            'type': ['string', 'integer'],
                            'pattern': '^[0-9]+$',
                        },
                        'date': {
                            'type': 'string',
                            'format': 'date-time'
                        },
                        'storage_class': {
                            'type': 'string',
                            'enum': ['GLACIER', 'STANDARD_IA']
                        }
                    }
                }
            }
        }
    }


class S3BaseActor(base.AWSBaseActor):

    """Base class for S3 actors."""

    all_options = {
        'name': (str, REQUIRED, 'Name of the S3 Bucket'),
        'state': (STATE, 'present',
                  'Desired state of the bucket: present/absent'),
        'lifecycle': (LifecycleConfig, None,
                      'List of Lifecycle configurations.'),
        'logging': (LoggingConfig, None,
                    'Dict with the logging configuration information.'),
        'policy': ((str, None), None,
                   'Path to the JSON policy file to apply to the bucket.'),
        'region': (str, REQUIRED, 'AWS region (or zone) name, like us-west-2'),
        'versioning': ((bool, None), None,
                       ('Desired state of versioning on the bucket: '
                        'true/false')),
    }


class Bucket(S3BaseActor):

    """Manage the state of a single S3 Bucket.

    The actor has the following functionality:

      * Ensure that an S3 bucket is present or absent.
      * Manage the bucket policy.
      * Manage the bucket Lifecycle configurations.
      * Enable or Suspend Bucket Versioning.
        Note: It is impossible to actually _disable_ bucket versioning -- once
        it is enabled, you can only suspend it, or re-enable it.

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

    :lifecycle:
      (:py:class:`LifecycleConfig`, None)

      A list of individual Lifecycle configurations. Each dictionary includes
      keys for the `id`, `prefix` and `status` as required parameters.
      Optionally you can supply an `expiration` and/or `transition` dictionary.

      If an empty list is supplied, or the list in any way does not match what
      is currently configured in Amazon, the appropriate changes will be made.

    :logging:
      (:py:class:`LoggingConfig`, None)

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

    :versioning:
      (bool, None): Whether or not to enable Versioning on the bucket. If
      "None", then we don't manage versioning either way. Default: None

    **Examples**

    .. code-block:: json

       { "actor": "aws.s3.Bucket",
         "options": {
           "name": "kingpin-integration-testing",
           "region": "us-west-2",
           "policy": "./examples/aws.s3/amazon_put.json",
           "lifecycle": {
              "id": "main",
              "prefix": "/",
              "status": "Enabled",
              "expiration": 30,
           },
           "logging": {
             "target": "logs.myco.com",
             "prefix": "/kingpin-integratin-testing"
           },
           "versioning": true,
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

        # If the Lifecycle config is anything but None, we parse it and
        # pre-build all of our Lifecycle/Rule/Expiration/Transition objects.
        if self.option('lifecycle') is not None:
            self.lifecycle = self._generate_lifecycle(self.option('lifecycle'))

    def _generate_lifecycle(self, config):
        """Generates a Lifecycle Configuration object.

        Takes the supplied configuration (a list of dicts) and turns them into
        proper Boto Lifecycle Rules, then returns a Lifecycle configuration
        object with these rules.

        args:
            config: A dict that matches the :py:class:`LifecycleConfig` schema.

        returns:
            :py:class:`boto.s3.lifecycle.Lifecycle`
            None: If the supplied configuration is empty
        """
        self.log.debug('Generating boto.s3.lifecycle.Lifecycle config..')

        # If the config list is empty, return None -- later in the code this
        # None will be used to determine whether or not to "delete" the
        # existing bucket lifecycle configs.
        if len(config) < 1:
            return None

        # Generate a fresh Lifecycle configuration object
        lc = lifecycle.Lifecycle()
        for c in config:
            self.log.debug('Generating lifecycle rule from: %s' % config)

            # You must supply at least 'expiration' or 'transition' in your
            # lifecycle config. This is tricky to check in the jsonschema, so
            # we do it here.
            if not any(k in c for k in ('expiration', 'transition')):
                raise InvalidBucketConfig(
                    'You must supply at least an expiration or transition '
                    'configuration in your config: %s' % c)

            # If the expiration 'days' were in string form turn them into an
            # integer.
            if 'expiration' in c:
                c['expiration'] = int(c['expiration'])

            # If 'transition' is supplied, turn it into a lifecycle.Transition
            # object using the generate_transition() method.
            if 'transition' in c:
                transition_dict = c['transition']
                transition_obj = self._generate_transition(transition_dict)
                c['transition'] = transition_obj

            # Finally add our rule to the lifecycle object
            lc.add_rule(**c)

        # Interesting hack -- Although Amazon does not document this, or
        # provide it as a parameter to the boto.s3.lifecycle.Rule/Lifecycle
        # objects, it seems that when you "get" the config from Amazon, each
        # Rule has a blank "Rule" attribute added. The Lifecycle object is the
        # same it get a blank "Lifecycle" attribute added. These show up when
        # we do the comparison between our config and the Amazon one, so we are
        # adding them here to help the comparison later on in
        # self._ensure_lifecycle().
        for r in lc:
            r.Rule = ''
        lc.LifecycleConfiguration = ''

        return lc

    def _generate_transition(self, config):
        """Generates a Lifecycle Transition object.

        See :py:class:`~boto.s3.lifecycle.Transition` for details about the
        contents of the dictionary.

        (*Note, we don't do much input validation here - we rely on the
        :py:class:`LifecycleConfig` schema to do that for us*)

        args:
            config: A dictionary with `days` or `date`, and `storage_class`.

        returns:
            :py:class:`boto.s3.lifecycle.Transition`
        """
        self.log.debug('Generating transition config from: %s' % config)
        if 'days' in config:
            config['days'] = int(config['days'])
        return lifecycle.Transition(**config)

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
            yield self._verify_can_delete_bucket(bucket=bucket)
            yield self._delete_bucket(bucket=bucket)
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

            # Mock out the versioning config -- return an empty dict to
            # indicate there is no configuration.
            mock_bucket.get_versioning_config.return_value = {}

            # Raise a 404 (empty) because new buckets do not have lifecycle
            # policies attached.
            mock_bucket.get_lifecycle_config.side_effect = S3ResponseError(
                404, 'Empty')

            raise gen.Return(mock_bucket)

        # This throws no exceptions, even if the bucket exists, that we know
        # about or can expect.
        self.log.info('Creating bucket')
        bucket = yield self.thread(self.s3_conn.create_bucket,
                                   self.option('name'))
        raise gen.Return(bucket)

    @gen.coroutine
    def _verify_can_delete_bucket(self, bucket):
        # Find out if there are any files in the bucket before we go to delete
        # it. We cannot delete a bucket with files in it -- nor do we want to.
        keys = yield self.thread(bucket.get_all_keys)
        if len(keys) > 0:
            raise exceptions.RecoverableActorFailure(
                'Cannot delete bucket with keys: %s files found' % len(keys))

    @gen.coroutine
    @dry('Would have deleted bucket {bucket}')
    def _delete_bucket(self, bucket):
        """Tries to delete an S3 bucket.

        args:
            bucket: The S3 bucket object as returned by Boto
        """
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
            if exist:
                yield self._delete_policy(bucket)
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

        # Push the new policy!
        yield self._set_policy(bucket)

    @gen.coroutine
    @dry('Would delete bucket policy')
    def _delete_policy(self, bucket):
        """Deletes a Bucket Policy.

        args:
            bucket: :py:class:`~boto.s3.bucket.Bucket`
        """
        self.log.info('Deleting bucket policy')
        try:
            yield self.thread(bucket.delete_policy)
        except S3ResponseError as e:
            raise exceptions.RecoverableActorFailure(
                'An unexpected error occurred: %s' % e)

    @gen.coroutine
    @dry('Would have pushed bucket policy')
    def _set_policy(self, bucket):
        """Sets a Bucket policy.

        args:
            bucket: :py:class:`~boto.s3.bucket.Bucket`
        """
        self.log.info('Pushing bucket policy %s' % self.option('policy'))
        self.log.debug('Policy doc: %s' % self.policy)
        try:
            yield self.thread(bucket.set_policy, json.dumps(self.policy))
        except S3ResponseError as e:
            if e.error_code == 'MalformedPolicy':
                raise base.InvalidPolicy(e.message)

            raise exceptions.RecoverableActorFailure(
                'An unexpected error occurred: %s' % e)

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
                raise gen.Return()
            yield self._disable_logging(bucket)
            raise gen.Return()

        # If desired has a logging or prefix config, check each one and
        # validate that they are correct.
        if (desired['target'] != existing.target or
                desired['prefix'] != existing.prefix):
            yield self._enable_logging(bucket, **desired)

    @gen.coroutine
    @dry('Bucket logging would have been disabled')
    def _disable_logging(self, bucket):
        """Disables logging on a bucket.

        args:
            bucket: :py:class`~boto.s3.bucket.Bucket`
        """
        self.log.info('Deleting Bucket logging configuration')
        yield self.thread(bucket.disable_logging)

    @gen.coroutine
    @dry('Bucket logging config would be updated to {target}/{prefix}')
    def _enable_logging(self, bucket, target, prefix):
        """Enables logging on a bucket.

        args:
            bucket: :py:class:`~boto.s3.bucket.Bucket`
            target: Target S3 bucket
            prefix: Target S3 bucket prefix
        """
        target_str = 's3://%s/%s' % (target, prefix.lstrip('/'))
        self.log.info('Updating Bucket logging config to %s' % target_str)

        try:
            yield self.thread(bucket.enable_logging, target, prefix)
        except S3ResponseError as e:
            if e.error_code == 'InvalidTargetBucketForLogging':
                raise InvalidBucketConfig(e.message)
            raise exceptions.RecoverableActorFailure(
                'An unexpected error occurred. %s' % e)

    @gen.coroutine
    def _ensure_versioning(self, bucket):
        """Enables or suspends object versioning on the bucket.

        args:
            bucket: The S3 bucket object as returned by Boto
        """
        # Get the buckets current versioning status
        existing = yield self.thread(bucket.get_versioning_status)

        # Shortcuts for our desired state
        desired = self.option('versioning')

        if not desired:
            # If desired is False, check the state, potentially disable it, and
            # then bail out.
            if ('Versioning' not in existing or
                    existing['Versioning'] == 'Suspended'):
                self.log.debug('Versioning is already disabled.')
                raise gen.Return()
            yield self._disable_versioning(bucket)
        else:
            # If desired is True, check the state, potentially enable it, and
            # bail.
            if ('Versioning' in existing and
                    existing['Versioning'] == 'Enabled'):
                self.log.debug('Versioning is already enabled.')
                raise gen.Return()

            yield self._enable_versioning(bucket)

    @gen.coroutine
    @dry('Bucket versioning would be suspended')
    def _disable_versioning(self, bucket):
        """Disables Bucket Versioning.

        args:
            bucket: :py:class:`~boto.s3.bucket.Bucket`
        """
        self.log.info('Suspending bucket versioning.')
        yield self.thread(bucket.configure_versioning, False)

    @gen.coroutine
    @dry('Would enable bucket versioning')
    def _enable_versioning(self, bucket):
        """Enables Bucket Versioning.

        args:
            bucket: :py:class:`~boto.s3.bucket.Bucket`
        """
        self.log.info('Enabling bucket versioning.')
        yield self.thread(bucket.configure_versioning, True)

    @gen.coroutine
    def _ensure_lifecycle(self, bucket):
        """Ensures that the Bucket Lifecycle configuration is in place.

        args:
            bucket: A :py:class:`boto.s3.Bucket` object
        """
        try:
            existing = yield self.thread(bucket.get_lifecycle_config)
        except S3ResponseError as e:
            if e.status != 404:
                raise exceptions.RecoverableActorFailure(
                    'An unexpected error occurred. %s' % e)
            existing = None

        # Simple check -- are we deleting the lifecycle? Do it.
        if self.lifecycle is None:
            if existing is None:
                self.log.debug('No existing lifecycle configuration found.')
                raise gen.Return()
            yield self._delete_lifecycle(bucket)
            raise gen.Return()

        # Next simple check -- if we're pushing a new config, and the old
        # config is empty (there was none), then just go and push it.
        if existing is None:
            yield self._configure_lifecycle(bucket=bucket,
                                            lifecycle=self.lifecycle)
            raise gen.Return()

        # Now sort through the existing Lifecycle configuration and the one
        # that we've built locally. If there are any differences, we're going
        # to push an all new config.
        diff = self._diff_policy_json(
            json.loads(jsonpickle.encode(existing)),
            json.loads(jsonpickle.encode(self.lifecycle)))
        if diff:
            self.log.info('Lifecycle configurations do not match. Updating.')
            for line in diff.split('\n'):
                self.log.info('Diff: %s' % line)
            yield self._configure_lifecycle(bucket=bucket,
                                            lifecycle=self.lifecycle)

    @gen.coroutine
    @dry('Would have deleted the existing lifecycle configuration')
    def _delete_lifecycle(self, bucket):
        self.log.info('Deleting the existing lifecycle configuration.')
        yield self.thread(bucket.delete_lifecycle_configuration)

    @gen.coroutine
    @dry('Would have pushed this lifecycle configuration: {lifecycle}')
    def _configure_lifecycle(self, bucket, lifecycle):
        self.log.debug('Lifecycle config: %s' %
                       jsonpickle.encode(lifecycle))

        self.log.info('Updating the Bucket Lifecycle config')
        try:
            yield self.thread(bucket.configure_lifecycle, lifecycle)
        except S3ResponseError as e:
            raise InvalidBucketConfig('Invalid Lifecycle Configuration: %s'
                                      % e.message)

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

        # Only manage versioning if a config was supplied
        if self.option('versioning') is not None:
            yield self._ensure_versioning(bucket)

        # Only manage the lifecycle configuration if one was supplied
        if self.option('lifecycle') is not None:
            yield self._ensure_lifecycle(bucket)

        raise gen.Return()
