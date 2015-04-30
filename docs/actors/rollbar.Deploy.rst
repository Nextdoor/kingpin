##### rollbar.Deploy

Posts a Deploy message to Rollbar.

[Rollbar Deploy Integration](https://rollbar.com/docs/deploys_other/)

**API Token**

You must use an API token created in your *Project Access Tokens* account
settings section. This token should have *post_server_item* permissions for the
actual deploy, and *read* permissions for the Dry run.

**Options**

  * `environment` - The environment to deploy to
  * `revision` - The deployment revision
  * `local_username` - The user who initiated the deploy
  * `rollbar_username` - *(Optional)* The Rollbar Username to assign the deploy to
  * `comment` - *(Optional)* Comment describing the deploy

Examples

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

Accesses the Rollbar API and validates that the token can access your project.
