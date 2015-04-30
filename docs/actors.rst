Actors
------

Definition: *a participant in an action or process.*

.. toctree::
   :glob:
   :maxdepth: 3

   kingpin.actors*

Librato
~~~~~~~

The Librato Actor allows you to post an Annotation to Librato. This is
specifically useful for marking when deployments occur on your graphs for
cause/effect analysis.

**Required Environment Variables**

-  ``LIBRATO_TOKEN`` - Librato API Token
-  ``LIBRATO_EMAIL`` - Librato email account (i.e. username)

**Actor-specific Documentation**

-  `librato.Annotation <actors/librato.Annotation.rst>`__

Rollbar
~~~~~~~

The Rollbar Actor allows you to post Deploy messages to Rollbar when you
execute a code deployment.

**Required Environment Variables**

-  ``ROLLBAR_TOKEN`` - Rollbar API Token

**Actor-specific Documentation**

-  `rollbar.Deploy <actors/rollbar.Deploy.rst>`__

RightScale
~~~~~~~~~~

The RightScale Actors allow you to interact with resources inside your
Rightscale account. These actors all support dry runs properly, but each
actor has its own caveats with ``dry=True``. Please read the instructions
below for using each actor.

**Required Environment Variables**

-  ``RIGHTSCALE_TOKEN`` - RightScale API Refresh Token
    (from the *Account Settings/API Credentials* page)
-  ``RIGHTSCALE_ENDPOINT`` - Your account-specific API Endpoint
    (defaults to ``https://my.rightscale.com``)

**Actor-specific Documentation**

-  `rightscale.server\_array.Clone <actors/rightscale.server_array.Clone.rst>`__
-  `rightscale.server\_array.Destroy <actors/rightscale.server_array.Destroy.rst>`__
-  `rightscale.server\_array.Execute <actors/rightscale.server_array.Execute.rst>`__
-  `rightscale.server\_array.Launch <actors/rightscale.server_array.Launch.rst>`__
-  `rightscale.server\_array.Update <actors/rightscale.server_array.Update.rst>`__
-  `rightscale.server\_array.Terminate <actors/rightscale.server_array.Terminate.rst>`__

Pingdom
~~~~~~~

Pingdom actors to pause and unpause checks. These are useful when you are aware
of an expected downtime and don't want to be alerted about it. Also known as
Maintenance mode.

**Required Environment Variables**

-  ``PINGDOM_TOKEN`` - Pingdom API Token
-  ``PINGDOM_USER`` - Pingdom Username (email)
-  ``PINGDOM_PASS`` - Pingdom Password

**Actor-specific Documentation**

-  `pingdom.Pause <actors/pingdom.Pause.rst>`__
-  `pingdom.Unpause <actors/pingdom.Unpause.rst>`__

Slack
~~~~~

The Slack Actors allow you to send messages to a Slack channel at stages during
your job execution. The actor supports dry mode by validating that the
configured API Token has access to execute the methods, without actually sending
the messages.

**Required Environment Variables**

-  ``SLACK_TOKEN`` - Slack API Token
-  ``SLACK_NAME`` - Slack ``message from`` name
    (defaults to ``Kingpin``)

**Actor-specific Documentation**

-  `slack.Message <actors/slack.Message.rst>`__
