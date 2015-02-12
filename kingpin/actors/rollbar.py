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

"""Rollbar Actor objects"""

import logging
import os
import urllib

from tornado import gen
from tornado import httpclient

from kingpin import utils
from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.constants import REQUIRED

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


API_CONTENT_TYPE = 'application/json'
API_URL = 'https://api.rollbar.com/api/1'
API_DEPLOY_PATH = '%s/deploy/' % API_URL
API_PROJECT_PATH = '%s/project/' % API_URL

TOKEN = os.getenv('ROLLBAR_TOKEN', None)


class RollbarBase(base.HTTPBaseActor):

    """Simple Rollbar Base Abstract Actor"""

    def __init__(self, *args, **kwargs):
        """Check required environment variables."""
        super(RollbarBase, self).__init__(*args, **kwargs)

        if not TOKEN:
            raise exceptions.InvalidCredentials(
                'Missing the "ROLLBAR_TOKEN" environment variable.')

        self._token = TOKEN

    def _build_potential_args(self, potential_args):
        """Builds a full set of arguments to pass to Rollbar.

        Appends the authentication token and a few other bits to the
        arguments supplied.

        Args:
            potential_Args: A hash of potential arguments.

        Returns:
            A larger hash of arguments.
        """
        potential_args['access_token'] = self._token
        return potential_args

    @gen.coroutine
    @utils.retry(excs=(httpclient.HTTPError), retries=3)
    def _fetch_wrapper(self, *args, **kwargs):
        """Wrap the superclass _fetch method to catch known Rollbar errors.

        https://rollbar.com/docs/api_overview/
        """
        try:
            res = yield self._fetch(*args, **kwargs)
        except httpclient.HTTPError as e:
            # These are HTTPErrors that we know about, and can log specific
            # error messages for.

            if e.code in (401, 403):
                raise exceptions.InvalidCredentials(
                    'The "ROLLBAR_TOKEN" is invalid')
            elif e.code == 422:
                raise exceptions.RecoverableActorFailure(
                    'Unprocessable Entity - the request was parseable (i.e. '
                    'valid JSON), but some parameters were missing or '
                    'otherwise invalid.')
            elif e.code == 429:
                raise exceptions.RecoverableActorFailure(
                    'Too Many Requests - If rate limiting is enabled for '
                    'your access token, this return code signifies that the '
                    'rate limit has been reached and the item was not '
                    'processed.')
            else:
                # We ran into a problem we can't handle. Also, keep in mind
                # that @utils.retry() was used, so this error happened several
                # times before getting here. Raise it.
                raise exceptions.RecoverableActorFailure(
                    'Unexpected error from Rollbar API: %s' % e)

        raise gen.Return(res)

    @gen.coroutine
    def _project(self):
        """Get a project description back from Rollbar.

        This method is used as a simple test that the API keys work. It access
        the list of projects from Rollbar and raises the appropriate exceptions
        if it cannot.

        https://rollbar.com/docs/api/projects/#list-your-projects

        Raises:
            gen.Return(<Dictionary of the response from Rollbar>)
        """

        args = self._build_potential_args({})
        url = self._generate_escaped_url(API_PROJECT_PATH, args)
        res = yield self._fetch_wrapper(url)
        raise gen.Return(res)


class Deploy(RollbarBase):

    """Simple Rollbar Deploy Actor."

    https://rollbar.com/docs/deploys_other/

    """
    all_options = {
        'environment': (str, REQUIRED, 'Name of the environment to deploy'),
        'revision': (str, REQUIRED, 'Revision number/sha being deployed'),
        'local_username': (str, 'Kingpin', 'User who deployed'),
        'rollbar_username': (str, '', 'Rollbar username'),
        'comment': (str, '', 'Deploy comment')
    }

    @gen.coroutine
    def _deploy(self):
        """Posts a Deploy to rollbar.

        https://rollbar.com/docs/deploys_other/

        Raises:
            gen.Return(<Dictionary of the response from Rollbar>)
        """

        rollbar_username = self.option('rollbar_username')
        if rollbar_username == '':
            rollbar_username = None

        args = self._build_potential_args({
            'environment': self.option('environment'),
            'revision': self.option('revision'),
            'local_username': self.option('local_username'),
            'rollbar_username': rollbar_username,
            'comment': self.option('comment')
        })

        escaped_post = urllib.urlencode(args)
        res = yield self._fetch_wrapper(API_DEPLOY_PATH, post=escaped_post)
        raise gen.Return(res)

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        raises: gen.Return()
        """
        rollbar_string = (
            'Rollbar Deploy Notification %s/%s' %
            (self.option('environment'), self.option('revision')))

        if self._dry:
            self.log.info('Would have sent %s, but instead just validating '
                          'API key.' % rollbar_string)
            yield self._project()
            raise gen.Return()

        self.log.info('Sending %s' % rollbar_string)
        yield self._deploy()
        raise gen.Return()
