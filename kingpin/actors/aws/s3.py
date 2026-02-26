"""
:mod:`kingpin.actors.aws.s3`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
"""

import json
import logging

import jsonpickle
from botocore.exceptions import ClientError, ParamValidationError
from inflection import camelize

from kingpin import utils
from kingpin.actors import exceptions
from kingpin.actors.aws import base
from kingpin.actors.utils import dry
from kingpin.constants import REQUIRED, STATE, SchemaCompareBase

log = logging.getLogger(__name__)

__author__ = "Matt Wise <matt@nextdoor.com"


class InvalidBucketConfig(exceptions.RecoverableActorFailure):
    """Raised whenever an invalid option is passed to a Bucket"""


class PublicAccessBlockConfig(SchemaCompareBase):
    """Provides JSON-Schema based validation of the supplied Public Access
    Block Configuration..

    The S3 PublicAccessBlockConfiguration should look like this:

    .. code-block:: json

        {
            "block_public_acls": true,
            "ignore_public_acls": true,
            "block_public_policy": true,
            "restrict_public_buckets": true
        }

    If you supply an empty dict, then we will explicitly remove the Public
    Access Block Configuration.

    """

    ACCESS_BLOCK_SCHEMA = {
        "type": ["object"],
        "required": [
            "block_public_acls",
            "ignore_public_acls",
            "block_public_policy",
            "restrict_public_buckets",
        ],
        "additionalProperties": False,
        "properties": {
            "block_public_acls": {"type": "boolean"},
            "ignore_public_acls": {"type": "boolean"},
            "block_public_policy": {"type": "boolean"},
            "restrict_public_buckets": {"type": "boolean"},
        },
    }

    SCHEMA = {
        "definitions": {
            "public_access_block_config": ACCESS_BLOCK_SCHEMA,
        },
        "anyOf": [
            {"$ref": "#/definitions/public_access_block_config"},
            {"type": "null"},
            {"type": "object", "additionalProperties": False},
        ],
    }

    valid = (
        '{ "block_public_acls": true, "ignore_public_acls": false, '
        '"block_public_policy": true, "restrict_public_buckets": false }'
    )


class LoggingConfig(SchemaCompareBase):
    """Provides JSON-Schema based validation of the supplied logging config.

    The S3 LoggingConfig format should look like this:

    .. code-block:: json

        {
            "target": "s3_bucket_name_here",
            "prefix": "an_optional_prefix_here"
        }

    If you supply an empty `target`, then we will explicitly remove the logging
    configuration from the bucket. Example:

    .. code-block:: json

        { "target": "" }

    """

    SCHEMA = {
        "type": ["object", "null"],
        "required": ["target"],
        "additionalProperties": False,
        "properties": {"target": {"type": "string"}, "prefix": {"type": "string"}},
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
            {
                "id": "unique_rule_identifier",
                "status": "Enabled",
                "filter": {
                    "prefix": "/some_path"
                },
                "transitions": [
                    {
                        "days": 90,
                        "date": "2016-05-19T20:04:17+00:00",
                        "storage_class": "GLACIER",
                    }
                ],
                "noncurrent_version_transitions": [
                    {
                        "noncurrent_days": 90,
                        "storage_class": "GLACIER",
                    }
                ],
                "expiration": {
                    "days": 365,
                },
                "noncurrent_version_expiration": {
                    "noncurrent_days": 365,
                }
            }
        ]
    """

    SCHEMA = {
        "definitions": {
            "tag": {
                "type": "object",
                "required": ["key", "value"],
                "additionalProperties": False,
                "properties": {
                    "key": {
                        "type": "string",
                    },
                    "value": {
                        "type": "string",
                    },
                },
            },
            "transition": {
                "type": "object",
                "required": ["storage_class"],
                "additionalProperties": False,
                "properties": {
                    "days": {
                        "type": ["string", "integer"],
                        "pattern": "^[0-9]+$",
                    },
                    "date": {"type": "string", "format": "date-time"},
                    "storage_class": {
                        "type": "string",
                        "enum": ["GLACIER", "STANDARD_IA"],
                    },
                },
            },
            "noncurrent_version_transition": {
                "type": "object",
                "required": ["storage_class"],
                "additionalProperties": False,
                "properties": {
                    "noncurrent_days": {
                        "type": ["string", "integer"],
                        "pattern": "^[0-9]+$",
                    },
                    "storage_class": {
                        "type": "string",
                        "enum": ["GLACIER", "STANDARD_IA"],
                    },
                },
            },
        },
        # The outer wrapper must be a list of properly formatted objects,
        # or Null if we are not going to manage this configuration at all.
        "type": ["array", "null"],
        "uniqueItems": True,
        "items": {
            "type": "object",
            "required": ["id", "status"],
            "oneOf": [{"required": ["filter"]}, {"required": ["prefix"]}],
            "anyOf": [
                {
                    "oneOf": [
                        {"required": ["transition"]},
                        {"required": ["transitions"]},
                    ]
                },
                {
                    "oneOf": [
                        {"required": ["noncurrent_version_transition"]},
                        {"required": ["noncurrent_version_transitions"]},
                    ]
                },
                {"required": ["expiration"]},
                {"required": ["noncurrent_version_expiration"]},
                {"required": ["abort_incomplete_multipart_upload"]},
            ],
            "additionalProperties": False,
            "properties": {
                # Basic Properties
                "id": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 255,
                },
                "status": {
                    "type": "string",
                    "enum": ["Enabled", "Disabled"],
                },
                # Filtering Properties
                #
                # prefix is deprecated in the AWS s3 API. Please use filter
                # instead.
                "filter": {
                    "type": "object",
                    "minProperties": 1,
                    "maxProperties": 1,
                    "additionalProperties": False,
                    "properties": {
                        "prefix": {
                            "type": "string",
                        },
                        "tag": {"$ref": "#/definitions/tag"},
                        "and": {
                            "type": "object",
                            "minProperties": 1,
                            "maxProperties": 2,
                            "additionalProperties": False,
                            "properties": {
                                "prefix": {
                                    "type": "string",
                                },
                                "tag": {"$ref": "#/definitions/tag"},
                            },
                        },
                    },
                },
                "prefix": {
                    "type": "string",
                },
                # Action Properties
                #
                # transition is deprecated in the AWS s3 API. Please use
                # transitions instead.
                "transitions": {
                    "type": "array",
                    "itmes": {"$ref": "#/definitions/transition"},
                },
                "transition": {"$ref": "#/definitions/transition"},
                # noncurrent_version_transition is deprecated in the AWS s3
                # API. Please use noncurrent_version_transitions instead.
                "noncurrent_version_transitions": {
                    "type": "array",
                    "itmes": {"$ref": "#/definitions/noncurrent_version_transition"},
                },
                "noncurrent_version_transition": {
                    "$ref": "#/definitions/noncurrent_version_transition"
                },
                # Note for expireation, we allow the actor to just accept a
                # number of days instead of an object and we create the
                # correct json with days in the init. Hence the object type of
                # str/int/obj here.
                "expiration": {
                    "type": ["string", "integer", "object"],
                    "pattern": "^[0-9]+$",
                    "additionalProperties": False,
                    "properties": {
                        "days": {
                            "type": ["string", "integer"],
                            "pattern": "^[0-9]+$",
                        },
                        "date": {
                            "type": "string",
                            "format": "date-time",
                        },
                        "expired_object_delete_marker": {
                            "type": "boolean",
                        },
                    },
                },
                "noncurrent_version_expiration": {
                    "type": "object",
                    "required": ["noncurrent_days"],
                    "additionalProperties": False,
                    "properties": {
                        "noncurrent_days": {
                            "type": ["string", "integer"],
                            "pattern": "^[0-9]+$",
                        },
                    },
                },
                "abort_incomplete_multipart_upload": {
                    "type": "object",
                    "required": ["days_after_initiation"],
                    "additionalProperties": False,
                    "properties": {
                        "days_after_initiation": {
                            "type": ["string", "integer"],
                            "pattern": "^[0-9]+$",
                        },
                    },
                },
            },
        },
    }


class NotificationConfiguration(SchemaCompareBase):
    """Provides JSON-Schema based validation of the supplied Notification Config.

    .. code-block:: json

       {
          "queue_configurations": [
              {
                 "queue_arn": "ARN of the SQS queue",
                 "events": ["s3:ObjectCreated:*"],
              }
         ]
       }
    """

    SCHEMA = {
        "type": ["object", "null"],
        "required": ["queue_configurations"],
        "properties": {
            "queue_configurations": {
                "type": ["array"],
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["queue_arn", "events"],
                    "properties": {
                        "queue_arn": {"type": "string"},
                        "events": {"type": "array", "items": {"type": "string"}},
                    },
                },
            }
        },
    }


class TaggingConfig(SchemaCompareBase):
    """Provides JSON-Schema based validation of the supplied tagging config.

    The S3 TaggingConfig format should look like this:

    .. code-block:: json

        [ { "key": "my_key", "value": "some_value" } ]

    """

    SCHEMA = {
        "type": ["array", "null"],
        "uniqueItems": True,
        "items": {
            "type": "object",
            "required": ["key", "value"],
            "additionalProperties": False,
            "properties": {
                "key": {
                    "type": "string",
                },
                "value": {
                    "type": "string",
                },
            },
        },
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
      * Enable Event Notification. (limited to SQS for now)

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
      keys for:

      * `id`
      * `status`
      * `filter` (or `prefix`, which is deprecated)

      and at least one of:

      * `transitions` (or `transition`, which is deprecated)
      * `noncurrent_version_transitions` (or `noncurrent_version_transition`)
      * `expiration`
      * `noncurrent_version_expiration`
      * `abort_incomplete_multipart_upload`

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

    :public_access_block_configuration:
      (:py:class:`PublicAccessBlockConfig`, None)

      If a dictionary is supplied, then it must conform to the
      :py:class:`PublicAccessBlockConfig` type and include all of the Public
      Access Block Configuration parameters.

      If an empty dictionary is supplied, then Kingpin will explicitly remove
      any Public Access Block Configurations from the bucket.

      Finally, if None is supplied, Kingpin will ignore the checks entirely on
      this portion of the bucket configuration.

      Default: None

    :region:
      AWS region (or zone) name, such as us-east-1 or us-west-2

    :versioning:
      (bool, None): Whether or not to enable Versioning on the bucket. If
      "None", then we don't manage versioning either way. Default: None

    :notification_configuration:
      (:py:class:`NotificationConfiguration`, None)

      If a dictionary is supplised, then it must conform to
      :py:class:`NotificationConfiguration`, type and include mapping
      queuearn & events

      If an empty dictionary is supplied, then Kingpin will explicitly remove
      any Notification Configuration from the bucket.

      Finally, If None is supplies, Kingoin will ignore the checks entire on
      this portion of the bucket configuration

    **Examples**

    .. code-block:: json

       {
         "actor": "aws.s3.Bucket",
         "options": {
           "name": "kingpin-integration-testing",
           "region": "us-west-2",
           "policy": "./examples/aws.s3/amazon_put.json",
           "lifecycle": [
              {
                "id": "main",
                "status": "Enabled",
                "filter": {
                    "prefix": "/"
                },
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
           "notification_configuration": {
              "queue_configurations": [
                {
                  "queue_arn": "arn:aws:sqs:us-east-1:1234567:some_sqs",
                  "events": [
                                "s3:ObjectCreated:*",
                                "s3:ObjectRemoved*"
                            ]
                }
              ]
           }
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
        "name": (str, REQUIRED, "Name of the S3 Bucket"),
        "state": (STATE, "present", "Desired state of the bucket: present/absent"),
        "lifecycle": (LifecycleConfig, None, "List of Lifecycle configurations."),
        "logging": (LoggingConfig, None, "Logging configuration for the bucket"),
        "public_access_block_configuration": (
            PublicAccessBlockConfig,
            None,
            "Public Access Block Configuration",
        ),
        "tags": (TaggingConfig, None, "Array of dicts with the key/value tags"),
        "policy": (
            (str, None),
            None,
            "Path to the JSON policy file to apply to the bucket.",
        ),
        "region": (str, REQUIRED, "AWS region (or zone) name, like us-west-2"),
        "versioning": (
            (bool, None),
            None,
            ("Desired state of versioning on the bucket: true/false"),
        ),
        "notification_configuration": (NotificationConfiguration, None, ""),
    }

    unmanaged_options = ["name", "region"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # If the policy is None, or '', we simply set it to self.policy. If its
        # anything else, we parse it.
        self.policy = self.option("policy")
        if self.option("policy"):
            self.policy = self._parse_json(self.option("policy"))

        # If the Lifecycle config is anything but None, we parse it and
        # pre-build all of our Lifecycle/Rule/Expiration/Transition objects.
        self.lifecycle = self.option("lifecycle")
        if self.lifecycle is not None:
            self.lifecycle = self._generate_lifecycle(self.option("lifecycle"))

        # If the PublicAccessBlockConfiguration is anything but None, we parse
        # it and pre-build the rules.
        self.access_block = self.option("public_access_block_configuration")
        if self.access_block is not None:
            self.access_block = self._snake_to_camel(self.access_block)

        # If the NotificationConfiguration is anything but None, we parse
        # it and pre-build the rules.
        self.notification_configuration = self.option("notification_configuration")
        if self.notification_configuration is not None:
            self.notification_configuration = self._snake_to_camel(
                self.notification_configuration
            )

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
            return dict((camelize(k), self._snake_to_camel(v)) for k, v in data.items())
        else:
            return data

    def _generate_lifecycle(self, config):
        """Generates a Lifecycle Configuration object.

        Takes the supplied configuration (a list of dicts) and turns them into
        proper Boto Lifecycle Rules, then returns a Lifecycle configuration
        object with these rules.

        Args:
            config: A dict that matches the :py:class:`LifecycleConfig` schema.

        Returns:
            :py:class:`boto.s3.lifecycle.Lifecycle`
            None: If the supplied configuration is empty
        """
        self.log.debug("Generating boto.s3.lifecycle.Lifecycle config..")

        # Generate a fresh Lifecycle configuration object
        rules = []
        for c in config:
            self.log.debug(f"Generating lifecycle rule from foo: {c}")

            # Convert the snake_case into CamelCase.
            c = self._snake_to_camel(c)

            # Fully capitalize the ID field
            c["ID"] = c.pop("Id")

            # If the Prefix was supplied in the old style, convert it into
            # the proper format for Amazon.
            if "Prefix" in c:
                c["Filter"] = {"Prefix": c.pop("Prefix")}

            # If the Tranisition was supplied in the old style, convert it into
            # the proper format for Amazon.
            if "Transition" in c:
                c["Transitions"] = [c.pop("Transition")]

            # If the NoncurrentVersionTransition was supplied in the old style,
            # convert it into the proper format for Amazon.
            if "NoncurrentVersionTransition" in c:
                c["NoncurrentVersionTransitions"] = [
                    c.pop("NoncurrentVersionTransition")
                ]

            # If the Expiration was supplied in the old style as a string/int,
            # convert it into the proper format for Amazon.
            if "Expiration" in c and not isinstance(c["Expiration"], dict):
                c["Expiration"] = {"Days": int(c.pop("Expiration"))}

            # Finally add our rule to the lifecycle object
            rules.append(c)

        return rules

    async def _precache(self):
        # Store a quick reference to whether or not the bucket exists or not.
        # This allows the rest of the getter-methods to know whether or not the
        # bucket exists and not make bogus API calls when the bucket doesn't
        # exist.
        buckets = await self.api_call(self.s3_conn.list_buckets)
        matching = [b for b in buckets["Buckets"] if b["Name"] == self.option("name")]
        if len(matching) == 1:
            self._bucket_exists = True

    async def _get_state(self):
        if not self._bucket_exists:
            return "absent"

        return "present"

    async def _set_state(self):
        if self.option("state") == "absent":
            await self._verify_can_delete_bucket()
            await self._delete_bucket()
        else:
            await self._create_bucket()

    @dry("Would have created the bucket")
    async def _create_bucket(self):
        """Creates an S3 bucket if its missing.

        returns:
            <A boto.s3.Bucket object>
        """
        params = {"Bucket": self.option("name")}

        if self.option("region") != "us-east-1":
            params["CreateBucketConfiguration"] = {
                "LocationConstraint": self.option("region")
            }

        self.log.info("Creating bucket")
        await self.api_call(self.s3_conn.create_bucket, **params)

    async def _verify_can_delete_bucket(self):
        # Find out if there are any files in the bucket before we go to delete
        # it. We cannot delete a bucket with files in it -- nor do we want to.
        bucket = self.option("name")
        keys = await self.api_call(self.s3_conn.list_objects, Bucket=bucket)

        if "Contents" not in keys:
            return

        if len(keys["Contents"]) > 0:
            raise exceptions.RecoverableActorFailure(
                f"Cannot delete bucket with keys: {len(keys)} files found"
            )

    @dry("Would have deleted bucket")
    async def _delete_bucket(self):
        bucket = self.option("name")
        try:
            self.log.info(f"Deleting bucket {bucket}")
            await self.api_call(self.s3_conn.delete_bucket, Bucket=bucket)
        except ClientError as e:
            raise exceptions.RecoverableActorFailure(
                f"Cannot delete bucket: {str(e)}"
            ) from e

    async def _get_policy(self):
        if not self._bucket_exists:
            return None

        try:
            raw = await self.api_call(
                self.s3_conn.get_bucket_policy, Bucket=self.option("name")
            )
            exist = json.loads(raw["Policy"])
        except ClientError as e:
            if "NoSuchBucketPolicy" in str(e):
                return ""
            raise

        return exist

    async def _compare_policy(self):
        new = self.policy
        if self.policy is None:
            self.log.debug("Not managing policy")
            return True

        exist = await self._get_policy()

        # Now, diff our new policy from the existing policy. If there is no
        # difference, then we bail out of the method.
        diff = utils.diff_dicts(exist, new)
        if not diff:
            self.log.debug("Bucket policy matches")
            return True

        # Now, print out the diff..
        self.log.info("Bucket policy differs from Amazons:")
        for line in diff.split("\n"):
            self.log.info(f"Diff: {line}")

        return False

    async def _set_policy(self):
        if self.policy == "":
            await self._delete_policy()
        else:
            await self._push_policy()

    @dry("Would have pushed bucket policy")
    async def _push_policy(self):
        self.log.info(f"Pushing bucket policy {self.option('policy')}")
        self.log.debug(f"Policy doc: {self.policy}")

        try:
            await self.api_call(
                self.s3_conn.put_bucket_policy,
                Bucket=self.option("name"),
                Policy=json.dumps(self.policy),
            )
        except ClientError as e:
            if "MalformedPolicy" in str(e):
                raise base.InvalidPolicy(str(e)) from e

            raise exceptions.RecoverableActorFailure(
                f"An unexpected error occurred: {e}"
            ) from e

    @dry("Would delete bucket policy")
    async def _delete_policy(self):
        self.log.info("Deleting bucket policy")
        await self.api_call(
            self.s3_conn.delete_bucket_policy, Bucket=self.option("name")
        )

    async def _get_logging(self):
        if not self._bucket_exists:
            return None

        data = await self.api_call(
            self.s3_conn.get_bucket_logging, Bucket=self.option("name")
        )

        if "LoggingEnabled" not in data:
            self.log.debug("Logging is disabled")
            return {"target": "", "prefix": ""}

        self.log.debug(
            f"Logging is set to"
            f" s3://{data['LoggingEnabled']['TargetBucket']}"
            f"/{data['LoggingEnabled']['TargetPrefix']}"
        )
        return {
            "target": data["LoggingEnabled"]["TargetBucket"],
            "prefix": data["LoggingEnabled"]["TargetPrefix"],
        }

    async def _set_logging(self):
        desired = self.option("logging")

        if desired is None:
            self.log.debug("Not managing logging")
            return

        # If desired is False, check the state, potentially disable it, and
        # then bail out. Note, we check explicitly for 'target' to be set to
        # ''. Setting it to None, or setting the entire logging config to None
        # should not destroy any existing logging configs.
        if desired["target"] == "":
            await self._disable_logging()
            return

        # If desired has a logging or prefix config, check each one and
        # validate that they are correct.
        await self._enable_logging(**desired)

    @dry("Bucket logging would have been disabled")
    async def _disable_logging(self):
        self.log.info("Deleting Bucket logging configuration")
        await self.api_call(
            self.s3_conn.put_bucket_logging,
            Bucket=self.option("name"),
            BucketLoggingStatus={},
        )

    @dry("Bucket logging config would be updated to {target}/{prefix}")
    async def _enable_logging(self, target, prefix):
        """Enables logging on a bucket.

        Args:
            target: Target S3 bucket
            prefix: Target S3 bucket prefix
        """
        target_str = f"s3://{target}/{prefix.lstrip('/')}"
        self.log.info(f"Updating Bucket logging config to {target_str}")

        try:
            await self.api_call(
                self.s3_conn.put_bucket_logging,
                Bucket=self.option("name"),
                BucketLoggingStatus={
                    "LoggingEnabled": {
                        "TargetBucket": target,
                        "TargetPrefix": prefix,
                    }
                },
            )
        except ClientError as e:
            raise InvalidBucketConfig(str(e)) from e

    async def _get_versioning(self):
        if not self._bucket_exists:
            return None

        existing = await self.api_call(
            self.s3_conn.get_bucket_versioning, Bucket=self.option("name")
        )

        if "Status" not in existing or existing["Status"] == "Suspended":
            self.log.debug("Versioning is disabled/suspended")
            return False

        self.log.debug("Versioning is enabled")
        return True

    async def _set_versioning(self):
        if self.option("versioning") is None:
            self.log.debug("Not managing versioning")
            return

        if self.option("versioning") is False:
            await self._put_versioning("Suspended")
        else:
            await self._put_versioning("Enabled")

    @dry("Bucket versioning would set to: {0}")
    async def _put_versioning(self, state):
        self.log.info(f"Setting bucket object versioning to: {state}")
        await self.api_call(
            self.s3_conn.put_bucket_versioning,
            Bucket=self.option("name"),
            VersioningConfiguration={"Status": state},
        )

    async def _get_lifecycle(self):
        if not self._bucket_exists:
            return None

        try:
            raw = await self.api_call(
                self.s3_conn.get_bucket_lifecycle_configuration,
                Bucket=self.option("name"),
            )
        except ClientError as e:
            if "NoSuchLifecycleConfiguration" in str(e):
                return []
            raise

        return raw["Rules"]

    async def _compare_lifecycle(self):
        existing = await self._get_lifecycle()
        new = self.lifecycle

        if new is None:
            self.log.debug("Not managing lifecycle")
            return True

        # Now sort through the existing Lifecycle configuration and the one
        # that we've built locally. If there are any differences, we're going
        # to push an all new config.
        diff = utils.diff_dicts(
            json.loads(jsonpickle.encode(existing)), json.loads(jsonpickle.encode(new))
        )

        if not diff:
            return True

        self.log.info("Lifecycle configurations do not match. Updating.")
        for line in diff.split("\n"):
            self.log.info(f"Diff: {line}")
        return False

    async def _set_lifecycle(self):
        if self.lifecycle == []:
            await self._delete_lifecycle()
        else:
            await self._push_lifecycle()

    @dry("Would have deleted the existing lifecycle configuration")
    async def _delete_lifecycle(self):
        self.log.info("Deleting the existing lifecycle configuration.")
        await self.api_call(
            self.s3_conn.delete_bucket_lifecycle, Bucket=self.option("name")
        )

    @dry("Would have pushed a new lifecycle configuration")
    async def _push_lifecycle(self):
        self.log.debug(f"Lifecycle config: {jsonpickle.encode(self.lifecycle)}")

        self.log.info("Updating the Bucket Lifecycle config")
        try:
            await self.api_call(
                self.s3_conn.put_bucket_lifecycle_configuration,
                Bucket=self.option("name"),
                LifecycleConfiguration={"Rules": self.lifecycle},
            )
        except (ParamValidationError, ClientError) as e:
            raise InvalidBucketConfig(f"Invalid Lifecycle Configuration: {e}") from e

    async def _get_public_access_block_configuration(self):
        if not self._bucket_exists:
            return None

        try:
            raw = await self.api_call(
                self.s3_conn.get_public_access_block, Bucket=self.option("name")
            )
        except ClientError as e:
            if "NoSuchPublicAccessBlockConfiguration" in str(e):
                return []
            raise

        return raw["PublicAccessBlockConfiguration"]

    async def _set_public_access_block_configuration(self):
        if self.access_block == {}:
            await self._delete_public_access_block_configuration()
        else:
            await self._push_public_access_block_configuration()

        return

    @dry("Would have deleted the existing public access block config")
    async def _delete_public_access_block_configuration(self):
        self.log.info("Deleting the existing public access block config.")
        await self.api_call(
            self.s3_conn.delete_public_access_block, Bucket=self.option("name")
        )

    @dry("Would have pushed a new public access block config")
    async def _push_public_access_block_configuration(self):
        self.log.debug(
            f"Public Access Block Config: {jsonpickle.encode(self.access_block)}"
        )

        self.log.info("Updating the Bucket Public Access Block Config")
        try:
            await self.api_call(
                self.s3_conn.put_public_access_block,
                Bucket=self.option("name"),
                PublicAccessBlockConfiguration=self.access_block,
            )
        except (ParamValidationError, ClientError) as e:
            raise InvalidBucketConfig(f"Invalid Public Access Block Config: {e}") from e

    async def _compare_public_access_block_configuration(self):
        existing = await self._get_public_access_block_configuration()
        new = self.access_block

        if new is None:
            self.log.debug("Not managing public access block config")
            return True

        # Now sort through the existing Lifecycle configuration and the one
        # that we've built locally. If there are any differences, we're going
        # to push an all new config.
        diff = utils.diff_dicts(
            json.loads(jsonpickle.encode(existing)), json.loads(jsonpickle.encode(new))
        )

        if not diff:
            return True

        self.log.info("Public Access Block Configurations do not match. Updating.")
        for line in diff.split("\n"):
            self.log.info(f"Diff: {line}")
        return False

    async def _get_tags(self):
        if self.option("tags") is None:
            return None

        if not self._bucket_exists:
            return None

        try:
            raw = await self.api_call(
                self.s3_conn.get_bucket_tagging, Bucket=self.option("name")
            )
        except ClientError as e:
            if "NoSuchTagSet" in str(e):
                return []
            raise

        # The keys in the sets returned always are capitalized (Key, Value) ...
        # but our schema uses lower case. Lowercase all of the keys before
        # returning them so that they are compared properly.
        tagset = []
        for tag in raw["TagSet"]:
            tag = {k.lower(): v for k, v in tag.items()}
            tagset.append(tag)

        return tagset

    async def _compare_tags(self):
        new = self.option("tags")
        if new is None:
            self.log.debug("Not managing Tags")
            return True

        exist = await self._get_tags()

        diff = utils.diff_dicts(exist, new)
        if not diff:
            self.log.debug("Bucket tags match")
            return True

        self.log.info("Bucket tags differs from Amazons:")
        for line in diff.split("\n"):
            self.log.info(f"Diff: {line}")

        return False

    @dry("Would have pushed tags")
    async def _set_tags(self):
        tags = self.option("tags")

        if tags is None:
            self.log.debug("Not managing tags")
            return None

        tagset = self._snake_to_camel(self.option("tags"))
        self.log.info("Updating the Bucket Tags")
        await self.api_call(
            self.s3_conn.put_bucket_tagging,
            Bucket=self.option("name"),
            Tagging={"TagSet": tagset},
        )

    async def _get_notification_configuration(self):
        if self.notification_configuration is None:
            return None

        if not self._bucket_exists:
            return None

        raw = await self.api_call(
            self.s3_conn.get_bucket_notification_configuration,
            Bucket=self.option("name"),
        )

        existing_configurations = {}
        for configuration in [
            "TopicConfigurations",
            "QueueConfigurations",
            "LambdaFunctionConfigurations",
        ]:
            if configuration in raw:
                existing_configurations[configuration] = raw[configuration]
        return existing_configurations

    async def _compare_notification_configuration(self):
        new = self.notification_configuration
        if new is None:
            self.log.debug("No Notification Configuration")
            return True

        exist = await self._get_notification_configuration()
        diff = utils.diff_dicts(exist, new)

        if not diff:
            self.log.debug("Notification Configurations match")
            return True

        self.log.info("Bucket Notification Configuration differs:")
        for line in diff.split("\n"):
            self.log.info(f"Diff: {line}")

        return False

    @dry("Would have added notification configurations")
    async def _set_notification_configuration(self):
        if self.notification_configuration is None:
            self.log.debug("No Notification Configurations")
            return None

        self.log.info("Updating Bucket Notification Configuration")
        await self.api_call(
            self.s3_conn.put_bucket_notification_configuration,
            Bucket=self.option("name"),
            NotificationConfiguration=self.notification_configuration,
        )
