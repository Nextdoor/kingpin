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
# Copyright 2013 Nextdoor.com, Inc.

"""
:mod:`tornado_rest_client.utils`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Common package for utility functions.
"""

import logging
import re
import time

from tornado import gen
from tornado import ioloop

__author__ = 'Matt Wise (matt@nextdoor.com)'

log = logging.getLogger(__name__)


@gen.coroutine
def tornado_sleep(seconds=1.0):
    """Async method equivalent to sleeping.

    Args:
        seconds: Float seconds. Default 1.0
    """
    yield gen.Task(ioloop.IOLoop.current().add_timeout,
                   time.time() + seconds)


def populate_with_tokens(string, tokens, left_wrapper='%', right_wrapper='%',
                         strict=True):
    """Insert token variables into the string.

    Will match any token wrapped in '%'s and replace it with the value of that
    token.

    Args:
        string: string to modify.
        tokens: dictionary of key:value pairs to inject into the string.
        left_wrapper: the character to use as the START of a token
        right_wrapper: the character to use as the END of a token
        strict: (bool) whether or not to make sure all tokens were replaced

    Example:
        export ME=biz

        string='foo %ME% %bar%'
        populate_with_tokens(string, os.environ)  # 'foo biz %bar%'
    """

    # First things first, swap out all instances of %<str>% with any matching
    # token variables found. If no items are in the hash (none, empty hash,
    # etc), then skip this.
    allowed_types = (str, unicode, bool, int, float)
    if tokens:
        for k, v in tokens.iteritems():

            if type(v) not in allowed_types:
                log.warning('Token %s=%s is not in allowed types: %s' % (
                    k, v, allowed_types))
                continue

            string = string.replace(
                ('%s%s%s' % (left_wrapper, k, right_wrapper)), str(v))

    # If we aren't strict, we return...
    if not strict:
        return string

    # If we are strict, we check if we missed anything. If we did, raise an
    # exception.
    missed_tokens = list(set(re.findall(r'%s[\w]+%s' %
                             (left_wrapper, right_wrapper), string)))
    if missed_tokens:
        raise LookupError(
            'Found un-matched tokens in JSON string: %s' % missed_tokens)

    return string
