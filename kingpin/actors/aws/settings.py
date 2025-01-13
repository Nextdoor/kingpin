"""
:mod:`kingpin.actors.aws.settings`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Common settings used by many of the `kingpin.actors.aws` modules.
"""

import os

# By default, this means that Boto will make HTTP calls at instantiation time to
# determine whether or not credentials are available from the metadata service.
#
# During tests, we mock these out to blank strings to prevent these calls.
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", None)
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", None)
AWS_SESSION_TOKEN = os.getenv("AWS_SESSION_TOKEN", None)

# kingpin is pretty fast which can leads to API throttling. You can set you own
# boto3 configuration by using the standard AWS env vars, but in the absence of
# them, we try to set you some sane defaults based on the boto3 documentation
# and our experience with running kingpin as scale.
#
# Docs: https://boto3.amazonaws.com/v1/documentation/api/latest/guide/retries.html
AWS_MAX_ATTEMPTS = int(os.getenv("AWS_MAX_ATTEMPTS", 10))
AWS_RETRY_MODE = os.getenv("AWS_RETRY_MODE", "standard")

# Set to "" (an empty string) to disable.
KINGPIN_CFN_HASH_OUTPUT_KEY = os.getenv("KINGPIN_CFN_HASH_OUTPUT_KEY", "KingpinCfnHash")

# Instead of specifying the role_arn in each CloudFormation actor, you can set a
# default role.
KINGPIN_CFN_DEFAULT_ROLE_ARN = os.getenv("KINGPIN_CFN_DEFAULT_ROLE_ARN", None)
