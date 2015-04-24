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


# Common Settings for the retrying.retry() decorator
#
# Use like this: @retrying.retry(**settings.RETRYING_SETTINGS)
#
def is_retriable_exception(exception):
    """Return true if this AWS exception is transient and should be retried.

    Example:
        >>> @retry(retry_on_exception=is_retriable_exception)
    """
    retry_codes = (
        'Throttling',
    )

    # Only handle Boto exceptions
    if not isinstance(exception, boto.exception.BotoServerError):
        return False

    # Boto exceptions should have a code attribute
    return exception.error_code in retry_codes


RETRYING_SETTINGS = {
    # Verify if we need to retry with the is_retriable_exception
    # method described above.
    'retry_on_exception': is_retriable_exception,

    # Wait up to 10 times
    'stop_max_attempt_number': 10,

    # Add 250ms of random jitter to every retry
    'wait_jitter_max': 250,

    # Add 250ms of sleep to every retry
    'wait_fixed': 250,

    # Now add between 250-2000ms to every retry
    'wait_random_min': 250,
    'wait_random_max': 2000,

    # Finally, add in an exponential backoff timer with a 10s limit
    'wait_exponential_multiplier': 100,
    'wait_exponential_max': 10000
}
