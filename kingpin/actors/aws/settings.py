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
:mod:`kingpin.actors.aws.settings`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Common settings used by many of the `kingpin.actors.aws` modules.
"""


import os

__author__ = "Mikhail Simin <mikhail@nextdoor.com>"

# By default, this means that Boto will make HTTP calls at instantiation time
# to determine whether or not credentials are available from the metadata
# service.
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
AWS_MAX_ATTEMPTS = os.getenv("AWS_MAX_ATTEMPTS", 10)
AWS_RETRY_MODE = os.getenv("AWS_RETRY_MODE", "standard")
