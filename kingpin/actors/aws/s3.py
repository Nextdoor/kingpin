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

from botocore.exceptions import ClientError, ParamValidationError
from tornado import concurrent
from tornado import gen
from inflection import camelize
import jsonpickle

from kingpin import utils
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

    valid = '{ "target": "<bucket name>", "prefix": "<logging prefix>" }'


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
            "expiration": {
              "days": 365,
            },
            "noncurrent_version_expiration": {
              "noncurrent_days": 365,
            },
            "transition": {
              "days": 90,
              "date": "2016-05-19T20:04:17+00:00",
              "storage_class": "GLACIER",
            },
            "noncurrent_version_transition": {
              "noncurrent_days": 90,
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
                'prefix': {
                    'type': 'string',
                },

                # The Status field must be 'Enabled' or 'Disabled'
                'status': {
                    'type': 'string',
                    'enum': ['Enabled', 'Disabled'],
                },

                # Expiration and Transition can be empty, or have
                # configurations associated with them.
                'expiration': {
                    'type': ['string', 'integer', 'object'],
                    'pattern': '^[0-9]+$',
                    'additionalProperties': False,
                    'properties': {
                        'days': {
                            'type': ['string', 'integer'],
                            'pattern': '^[0-9]+$',
                        },
                        'date': {
                            'type': 'string',
                            'format': 'date-time',
                        },
                        'expired_object_delete_marker': {
                            'type': 'boolean',
                        }
                    }
                },
                'transition': {
                    'type': ['object', 'null'],
                    'required': ['storage_class'],
                    'additionalProperties': False,
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
                },
                'noncurrent_version_transition': {
                    'type': 'object',
                    'required': ['storage_class'],
                    'additionalProperties': False,
                    'properties': {
                        'noncurrent_days': {
                            'type': ['string', 'integer'],
                            'pattern': '^[0-9]+$',
                        },
                        'storage_class': {
                            'type': 'string',
                            'enum': ['GLACIER', 'STANDARD_IA']
                        }
                    }
                },
                'noncurrent_version_expiration': {
                    'type': 'object',
                    'additionalProperties': False,
                    'properties': {
                        'noncurrent_days': {
                            'type': ['string', 'integer'],
                            'pattern': '^[0-9]+$',
                        },
                    }
                },
            }
        }
    }


class TaggingConfig(SchemaCompareBase):

    """Provides JSON-Schema based validation of the supplied tagging config.

    The S3 TaggingConfig format should look like this:

    .. code-block:: json

        [ { "key": "my_key", "value": "some_value" } ]

    """

    SCHEMA = {
        'type': ['array', 'null'],
        'uniqueItems': True,
        'items': {
            'type': 'object',
            'required': ['key', 'value'],
            'additionalProperties': False,
            'properties': {
                'key': {
                    'type': 'string',
                },
                'value': {
                    'type': 'string',
                }
            }
        }
    }

    valid = '[ { "key": "<key name>", "value": "<tag value>" } ]'


class Bucket(base.EnsurableAWSBaseActor):

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

    :tags:
      (:py:class:`TaggingConfig`, None)

      A list of dictionaries with a `key` and `value` key. Defaults to an empty
      list, which means that if you manually add tags, they will be removed.

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
           "lifecycle": [
              { "id": "main",
                "prefix": "/",
                "status": "Enabled",
                "expiration": 30,
              }
           ],
           "logging": {
             "target": "logs.myco.com",
             "prefix": "/kingpin-integratin-testing"
           },
           "tags": [
             {"key": "my_key", "value": "billing-grp-1"},
           ],
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

    all_options = {
        'name': (str, REQUIRED, 'Name of the S3 Bucket'),
        'state': (STATE, 'present',
                  'Desired state of the bucket: present/absent'),
        'lifecycle': (LifecycleConfig, None,
                      'List of Lifecycle configurations.'),
        'logging': (LoggingConfig, None,
                    'Logging configuration for the bucket'),
        'tags': (TaggingConfig, None,
                 'Array of dicts with the key/value tags'),
        'policy': ((str, None), None,
                   'Path to the JSON policy file to apply to the bucket.'),
        'region': (str, REQUIRED, 'AWS region (or zone) name, like us-west-2'),
        'versioning': ((bool, None), None,
                       ('Desired state of versioning on the bucket: '
                        'true/false')),
    }

    unmanaged_options = ['name', 'region']

    def __init__(self, *args, **kwargs):
        super(Bucket, self).__init__(*args, **kwargs)

        # If the policy is None, or '', we simply set it to self.policy. If its
        # anything else, we parse it.
        self.policy = self.option('policy')
        if self.option('policy'):
            self.policy = self._parse_policy_json(self.option('policy'))

        # If the Lifecycle config is anything but None, we parse it and
        # pre-build all of our Lifecycle/Rule/Expiration/Transition objects.
        self.lifecycle = self.option('lifecycle')
        if self.option('lifecycle') is not None:
            self.lifecycle = self._generate_lifecycle(self.option('lifecycle'))

        # Start out assuming the bucket doesn't exist. The _precache() method
        # will populate this with True if the bucket does exist.
        self._bucket_exists = False

    def _snake_to_camel(self, data):
        """Converts a snake_case dict to CamelCase.

        To keep our LifecycleConfig schema in-line with the rest of Kingpin, we
        use snake_case for all key values. This method converts the snake_case
        into CamelCase for final uploading to Amazons API where CamelCase is
        required.
        """
        if isinstance(data, list):
            return [self._snake_to_camel(v) for v in data]
        elif isinstance(data, dict):
            return dict(
                (camelize(k), self._snake_to_camel(v)) for k, v
                in data.items())
        else:
            return data

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

        # Generate a fresh Lifecycle configuration object
        rules = []
        for c in config:
            self.log.debug('Generating lifecycle rule from: %s' % c)

            # You must supply at least 'expiration' or 'transition' in your
            # lifecycle config. This is tricky to check in the jsonschema, so
            # we do it here.
            if not any(k in c for k in ('expiration', 'transition')):
                raise InvalidBucketConfig(
                    'You must supply at least an expiration or transition '
                    'configuration in your config: %s' % c)

            # Convert the snake_case into CamelCase.
            c = self._snake_to_camel(c)

            # Fully capitalize the ID field
            c['ID'] = c.pop('Id')

            # If the Expiration was supplied in the old style as a string/int,
            # convert it into the proper format for Amazon.
            if 'Expiration' in c and not isinstance(c['Expiration'], dict):
                c['Expiration'] = {'Days': int(c.pop('Expiration'))}

            # Finally add our rule to the lifecycle object
            rules.append(c)

        return rules

    @gen.coroutine
    def _precache(self):
        # Store a quick reference to whether or not the bucket exists or not.
        # This allows the rest of the getter-methods to know whether or not the
        # bucket exists and not make bogus API calls when the bucket doesn't
        # exist.
        buckets = yield self.thread(self.s3_conn.list_buckets)
        matching = [
            b for b in buckets['Buckets'] if b['Name'] == self.option('name')]
        if len(matching) == 1:
            self._bucket_exists = True

    @gen.coroutine
    def _get_state(self):
        if not self._bucket_exists:
            raise gen.Return('absent')

        raise gen.Return('present')

    @gen.coroutine
    def _set_state(self):
        if self.option('state') == 'absent':
            yield self._verify_can_delete_bucket()
            yield self._delete_bucket()
        else:
            yield self._create_bucket()

    @gen.coroutine
    @dry('Would have created the bucket')
    def _create_bucket(self):
        """Creates an S3 bucket if its missing.

        returns:
            <A boto.s3.Bucket object>
        """
        params = {
            'Bucket': self.option('name')
        }

        if self.option('region') != 'us-east-1':
            params['CreateBucketConfiguration'] = {
                'LocationConstraint': self.option('region')
            }

        self.log.info('Creating bucket')
        yield self.thread(self.s3_conn.create_bucket, **params)

    @gen.coroutine
    def _verify_can_delete_bucket(self):
        # Find out if there are any files in the bucket before we go to delete
        # it. We cannot delete a bucket with files in it -- nor do we want to.
        bucket = self.option('name')
        keys = yield self.thread(self.s3_conn.list_objects, Bucket=bucket)

        if 'Contents' not in keys:
            raise gen.Return()

        if len(keys['Contents']) > 0:
            raise exceptions.RecoverableActorFailure(
                'Cannot delete bucket with keys: %s files found' % len(keys))

    @gen.coroutine
    @dry('Would have deleted bucket')
    def _delete_bucket(self):
        bucket = self.option('name')
        try:
            self.log.info('Deleting bucket %s' % bucket)
            yield self.thread(self.s3_conn.delete_bucket, Bucket=bucket)
        except ClientError as e:
            raise exceptions.RecoverableActorFailure(
                'Cannot delete bucket: %s' % e)

    @gen.coroutine
    def _get_policy(self):
        if not self._bucket_exists:
            raise gen.Return(None)

        try:
            raw = yield self.thread(
                self.s3_conn.get_bucket_policy,
                Bucket=self.option('name'))
            exist = json.loads(raw['Policy'])
        except ClientError as e:
            if 'NoSuchBucketPolicy' in str(e):
                raise gen.Return('')
            raise

        raise gen.Return(exist)

    @gen.coroutine
    def _compare_policy(self):
        new = self.policy
        if self.policy is None:
            self.log.debug('Not managing policy')
            raise gen.Return(True)

        exist = yield self._get_policy()

        # Now, diff our new policy from the existing policy. If there is no
        # difference, then we bail out of the method.
        diff = utils.diff_dicts(exist, new)
        if not diff:
            self.log.debug('Bucket policy matches')
            raise gen.Return(True)

        # Now, print out the diff..
        self.log.info('Bucket policy differs from Amazons:')
        for line in diff.split('\n'):
            self.log.info('Diff: %s' % line)

        raise gen.Return(False)

    @gen.coroutine
    def _set_policy(self):
        if self.policy == '':
            yield self._delete_policy()
        else:
            yield self._push_policy()

    @gen.coroutine
    @dry('Would have pushed bucket policy')
    def _push_policy(self):
        self.log.info('Pushing bucket policy %s' % self.option('policy'))
        self.log.debug('Policy doc: %s' % self.policy)

        try:
            yield self.thread(
                self.s3_conn.put_bucket_policy,
                Bucket=self.option('name'),
                Policy=json.dumps(self.policy))
        except ClientError as e:
            if 'MalformedPolicy' in str(e):
                raise base.InvalidPolicy(str(e))

            raise exceptions.RecoverableActorFailure(
                'An unexpected error occurred: %s' % e)

    @gen.coroutine
    @dry('Would delete bucket policy')
    def _delete_policy(self):
        self.log.info('Deleting bucket policy')
        yield self.thread(
            self.s3_conn.delete_bucket_policy,
            Bucket=self.option('name'))

    @gen.coroutine
    def _get_logging(self):
        if not self._bucket_exists:
            raise gen.Return(None)

        data = yield self.thread(
            self.s3_conn.get_bucket_logging, Bucket=self.option('name'))

        if 'LoggingEnabled' not in data:
            self.log.debug('Logging is disabled')
            raise gen.Return({
                'target': '',
                'prefix': ''})

        self.log.debug('Logging is set to s3://%s/%s' %
                       (data['LoggingEnabled']['TargetBucket'],
                        data['LoggingEnabled']['TargetPrefix']))
        raise gen.Return({
            'target': data['LoggingEnabled']['TargetBucket'],
            'prefix': data['LoggingEnabled']['TargetPrefix']})

    @gen.coroutine
    def _set_logging(self):
        desired = self.option('logging')

        if desired is None:
            self.log.debug('Not managing logging')
            raise gen.Return()

        # If desired is False, check the state, potentially disable it, and
        # then bail out. Note, we check explicitly for 'target' to be set to
        # ''. Setting it to None, or setting the entire logging config to None
        # should not destroy any existing logging configs.
        if desired['target'] == '':
            yield self._disable_logging()
            raise gen.Return()

        # If desired has a logging or prefix config, check each one and
        # validate that they are correct.
        yield self._enable_logging(**desired)

    @gen.coroutine
    @dry('Bucket logging would have been disabled')
    def _disable_logging(self):
        self.log.info('Deleting Bucket logging configuration')
        yield self.thread(
            self.s3_conn.put_bucket_logging,
            Bucket=self.option('name'),
            BucketLoggingStatus={})

    @gen.coroutine
    @dry('Bucket logging config would be updated to {target}/{prefix}')
    def _enable_logging(self, target, prefix):
        """Enables logging on a bucket.

        args:
            target: Target S3 bucket
            prefix: Target S3 bucket prefix
        """
        target_str = 's3://%s/%s' % (target, prefix.lstrip('/'))
        self.log.info('Updating Bucket logging config to %s' % target_str)

        try:
            yield self.thread(
                self.s3_conn.put_bucket_logging,
                Bucket=self.option('name'),
                BucketLoggingStatus={
                    'LoggingEnabled': {
                        'TargetBucket': target,
                        'TargetPrefix': prefix,
                    }
                })
        except ClientError as e:
            raise InvalidBucketConfig(str(e))

    @gen.coroutine
    def _get_versioning(self):
        if not self._bucket_exists:
            raise gen.Return(None)

        existing = yield self.thread(
            self.s3_conn.get_bucket_versioning,
            Bucket=self.option('name'))

        if ('Status' not in existing or
                existing['Status'] == 'Suspended'):
            self.log.debug('Versioning is disabled/suspended')
            raise gen.Return(False)

        self.log.debug('Versioning is enabled')
        raise gen.Return(True)

    @gen.coroutine
    def _set_versioning(self):
        if self.option('versioning') is None:
            self.log.debug('Not managing versioning')
            raise gen.Return()

        if self.option('versioning') is False:
            yield self._put_versioning('Suspended')
        else:
            yield self._put_versioning('Enabled')

    @gen.coroutine
    @dry('Bucket versioning would set to: {0}')
    def _put_versioning(self, state):
        self.log.info('Setting bucket object versioning to: %s' % state)
        yield self.thread(
            self.s3_conn.put_bucket_versioning,
            Bucket=self.option('name'),
            VersioningConfiguration={'Status': state})

    @gen.coroutine
    def _get_lifecycle(self):
        if not self._bucket_exists:
            raise gen.Return(None)

        try:
            raw = yield self.thread(
                self.s3_conn.get_bucket_lifecycle,
                Bucket=self.option('name'))
        except ClientError as e:
            if 'NoSuchLifecycleConfiguration' in str(e):
                raise gen.Return([])
            raise

        raise gen.Return(raw['Rules'])

    @gen.coroutine
    def _compare_lifecycle(self):
        existing = yield self._get_lifecycle()
        new = self.lifecycle

        if new is None:
            self.log.debug('Not managing lifecycle')
            raise gen.Return(True)

        # Now sort through the existing Lifecycle configuration and the one
        # that we've built locally. If there are any differences, we're going
        # to push an all new config.
        diff = utils.diff_dicts(
            json.loads(jsonpickle.encode(existing)),
            json.loads(jsonpickle.encode(new)))

        if not diff:
            raise gen.Return(True)

        self.log.info('Lifecycle configurations do not match. Updating.')
        for line in diff.split('\n'):
            self.log.info('Diff: %s' % line)
        raise gen.Return(False)

    @gen.coroutine
    def _set_lifecycle(self):
        if self.lifecycle == []:
            yield self._delete_lifecycle()
        else:
            yield self._push_lifecycle()

    @gen.coroutine
    @dry('Would have deleted the existing lifecycle configuration')
    def _delete_lifecycle(self):
        self.log.info('Deleting the existing lifecycle configuration.')
        yield self.thread(
            self.s3_conn.delete_bucket_lifecycle,
            Bucket=self.option('name'))

    @gen.coroutine
    @dry('Would have pushed a new lifecycle configuration')
    def _push_lifecycle(self):
        self.log.debug('Lifecycle config: %s' %
                       jsonpickle.encode(self.lifecycle))

        self.log.info('Updating the Bucket Lifecycle config')
        try:
            yield self.thread(
                self.s3_conn.put_bucket_lifecycle,
                Bucket=self.option('name'),
                LifecycleConfiguration={'Rules': self.lifecycle})
        except (ParamValidationError, ClientError) as e:
            raise InvalidBucketConfig('Invalid Lifecycle Configuration: %s' % e)

    @gen.coroutine
    def _get_tags(self):
        if self.option('tags') is None:
            raise gen.Return(None)

        if not self._bucket_exists:
            raise gen.Return(None)

        try:
            raw = yield self.thread(
                self.s3_conn.get_bucket_tagging,
                Bucket=self.option('name'))
        except ClientError as e:
            if 'NoSuchTagSet' in str(e):
                raise gen.Return([])
            raise

        # The keys in the sets returned always are capitalized (Key, Value) ...
        # but our schema uses lower case. Lowercase all of the keys before
        # returning them so that they are compared properly.
        tagset = []
        for tag in raw['TagSet']:
            tag = {k.lower(): v for k, v in list(tag.items())}
            tagset.append(tag)

        raise gen.Return(tagset)

    @gen.coroutine
    def _compare_tags(self):
        new = self.option('tags')
        if new is None:
            self.log.debug('Not managing Tags')
            raise gen.Return(True)

        exist = yield self._get_tags()

        diff = utils.diff_dicts(exist, new)
        if not diff:
            self.log.debug('Bucket tags match')
            raise gen.Return(True)

        self.log.info('Bucket tags differs from Amazons:')
        for line in diff.split('\n'):
            self.log.info('Diff: %s' % line)

        raise gen.Return(False)

    @gen.coroutine
    @dry('Would have pushed tags')
    def _set_tags(self):
        tags = self.option('tags')

        if tags is None:
            self.log.debug('Not managing tags')
            raise gen.Return(None)

        tagset = self._snake_to_camel(self.option('tags'))
        self.log.info('Updating the Bucket Tags')
        yield self.thread(
            self.s3_conn.put_bucket_tagging,
            Bucket=self.option('name'),
            Tagging={'TagSet': tagset})
