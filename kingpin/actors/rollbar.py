"""
:mod:`kingpin.actors.rollbar`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The Rollbar Actor allows you to post Deploy messages to Rollbar when you
execute a code deployment.

**Required Environment Variables**

:ROLLBAR_TOKEN:
    Rollbar API Token
"""

import logging
import os
import urllib.request
import urllib.parse
import urllib.error

from tornado import gen
from tornado import httpclient

from kingpin import utils
from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.constants import REQUIRED

log = logging.getLogger(__name__)

__author__ = "Matt Wise <matt@nextdoor.com>"


API_CONTENT_TYPE = "application/json"
API_URL = "https://api.rollbar.com/api/1"
API_DEPLOY_PATH = "%s/deploy/" % API_URL
API_PROJECT_PATH = "%s/project/" % API_URL

TOKEN = os.getenv("ROLLBAR_TOKEN", None)


class RollbarBase(base.HTTPBaseActor):
    """Simple Rollbar Base Abstract Actor"""

    def __init__(self, *args, **kwargs):
        """Check required environment variables."""
        super(RollbarBase, self).__init__(*args, **kwargs)

        if not TOKEN:
            raise exceptions.InvalidCredentials(
                'Missing the "ROLLBAR_TOKEN" environment variable.'
            )

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
        potential_args["access_token"] = self._token
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
                raise exceptions.InvalidCredentials('The "ROLLBAR_TOKEN" is invalid')
            elif e.code == 422:
                raise exceptions.RecoverableActorFailure(
                    "Unprocessable Entity - the request was parseable (i.e. "
                    "valid JSON), but some parameters were missing or "
                    "otherwise invalid."
                )
            elif e.code == 429:
                raise exceptions.RecoverableActorFailure(
                    "Too Many Requests - If rate limiting is enabled for "
                    "your access token, this return code signifies that the "
                    "rate limit has been reached and the item was not "
                    "processed."
                )
            else:
                # We ran into a problem we can't handle. Also, keep in mind
                # that @utils.retry() was used, so this error happened several
                # times before getting here. Raise it.
                raise exceptions.RecoverableActorFailure(
                    "Unexpected error from Rollbar API: %s" % e
                )

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
    """Posts a Deploy message to Rollbar.

    https://rollbar.com/docs/deploys_other/

    **API Token**

    You must use an API token created in your *Project Access Tokens* account
    settings section. This token should have *post_server_item* permissions for
    the actual deploy, and *read* permissions for the Dry run.

    **Options**

    :environment:
      The environment to deploy to

    :revision:
      The deployment revision

    :local_username:
      The user who initiated the deploy

    :rollbar_username:
      *(Optional)* The Rollbar Username to assign the deploy to

    :comment:
      *(Optional)* Comment describing the deploy

    **Examples**

    .. code-block:: json

       { "actor": "rollbar.Deploy",
         "desc": "update rollbar deploy",
         "options": {
           "environment": "Prod",
           "revision": "%DEPLOY%",
           "local_username": "Kingpin",
           "rollbar_username": "Kingpin",
           "comment": "some comment %DEPLOY%"
         }
       }

    **Dry Mode**

    Accesses the Rollbar API and validates that the token can access your
    project.
    """

    all_options = {
        "environment": (str, REQUIRED, "Name of the environment to deploy"),
        "revision": (str, REQUIRED, "Revision number/sha being deployed"),
        "local_username": (str, "Kingpin", "User who deployed"),
        "rollbar_username": (str, "", "Rollbar username"),
        "comment": (str, "", "Deploy comment"),
    }

    desc = "Sending Deploy {environment}/{revision}"

    @gen.coroutine
    def _deploy(self):
        """Posts a Deploy to rollbar.

        https://rollbar.com/docs/deploys_other/

        Raises:
            gen.Return(<Dictionary of the response from Rollbar>)
        """

        rollbar_username = self.option("rollbar_username")
        if rollbar_username == "":
            rollbar_username = None

        args = self._build_potential_args(
            {
                "environment": self.option("environment"),
                "revision": self.option("revision"),
                "local_username": self.option("local_username"),
                "rollbar_username": rollbar_username,
                "comment": self.option("comment"),
            }
        )

        escaped_post = urllib.parse.urlencode(args)
        res = yield self._fetch_wrapper(API_DEPLOY_PATH, post=escaped_post)
        raise gen.Return(res)

    @gen.coroutine
    def _execute(self):
        """Executes an actor and yields the results when its finished.

        raises: gen.Return()
        """
        rollbar_string = "Rollbar Deploy Notification %s/%s" % (
            self.option("environment"),
            self.option("revision"),
        )

        if self._dry:
            self.log.info(
                "Would have sent %s, but instead just validating "
                "API key." % rollbar_string
            )
            yield self._project()
            raise gen.Return()

        self.log.info("Sending %s" % rollbar_string)
        yield self._deploy()
        raise gen.Return()
