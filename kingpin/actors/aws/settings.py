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

"""Common settings for AWS Actors"""

import os

import boto

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'

# NOTE: using empty string here instead of None because boto library will try
# to open a connection if key/secret is None, instead of creating a lazy
# connection object.
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID', '')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY', '')

SQS_RETRY_DELAY = 30
CF_WAIT_MAX = 30000


def is_retriable_exception(exception):
    """Return true if this AWS exception is transient and should be retried.

    http://boto.readthedocs.org/en/latest/ref/boto.html
        #boto.exception.PleaseRetryException

    Example:
        >>> @retry(retry_on_exception=is_retriable_exception)
    """
    return isinstance(exception, boto.exception.PleaseRetryException)
