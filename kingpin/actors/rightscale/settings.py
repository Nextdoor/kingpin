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
:mod:`kingpin.actors.rightscale.settings`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Common settings used by many of the `kingpin.actors.rightscale` modules.
"""


import logging
import requests

__author__ = 'Matt Wise <matt@nextdoor.com>'

log = logging.getLogger(__name__)


# Common Settings for the retrying.retry() decorator
#
# Use like this: @retrying.retry(**settings.RETRYING_SETTINGS)
#
def is_retriable_exception(exception):
    """Return true if this RightScale exception is transient.

    Example:
        >>> @retry(retry_on_exception=is_retriable_exception)
    """
    not_retry_codes = ('422',)

    # Only handle requests.exceptions.HTTPError exceptions
    if not isinstance(exception, requests.exceptions.HTTPError):
        return False

    log.debug('Comparing "%s" to "%s".' % (str(exception), not_retry_codes))
    return not any(code in str(exception) for code in not_retry_codes)


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
    'wait_exponential_max': 30000
}
