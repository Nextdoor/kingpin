The Actors
----------

Definition: *a participant in an action or process.*

Base Actors
~~~~~~~~~~~

Kingpin provides several internal actors that can be used to create complex
and reliable groups of actions to be executed.

**Optional Environment Variables**

-  ``URLLIB_DEBUG`` - Set this variable to enable extreme debug logging
   of the URLLIB requests made by the RightScale/AWS actors.
   *Note, this is very insecure as headers/cookies/etc. are exposed*

**Actor-specific Documentation**

-  `misc.Macro <actors/misc.Macro.rst>`__
-  `misc.Sleep <actors/misc.Sleep.rst>`__
-  `group.Sync <actors/group.Sync.rst>`__
-  `group.Async <actors/group.Async.rst>`__

AWS
~~~

The AWS Actors allow you to interact with the resources (such as SQS and ELB)
inside your Amazon AWS account. These actors all support dry runs properly, but
each actor has its own caveats with ``dry=True``. Please read the instructions
below for using each actor.

**Required Environment Variables**

-  ``AWS_ACCESS_KEY_ID`` - Your AWS access key
-  ``AWS_SECRET_ACCESS_KEY`` - Your AWS secret

**Actor-specific Documentation**

-  `aws.cloudformation.Create <actors/aws.cloudformation.Create.rst>`__
-  `aws.cloudformation.Delete <actors/aws.cloudformation.Delete.rst>`__
-  `aws.elb.DeregisterInstance <actors/aws.elb.DeregisterInstance.rst>`__
-  `aws.elb.RegisterInstance <actors/aws.elb.RegisterInstance.rst>`__
-  `aws.elb.SetCert <actors/aws.elb.SetCert.rst>`__
-  `aws.elb.WaitUntilHealthy <actors/aws.elb.WaitUntilHealthy.rst>`__
-  `aws.iam.DeleteCert <actors/aws.iam.DeleteCert.rst>`__
-  `aws.iam.UploadCert <actors/aws.iam.UploadCert.rst>`__
-  `aws.sqs.Create <actors/aws.sqs.Create.rst>`__
-  `aws.sqs.Delete <actors/aws.sqs.Delete.rst>`__
-  `aws.sqs.WaitUntilEmpty <actors/aws.sqs.WaitUntilEmpty.rst>`__

GenericHTTP
~~~~~~~~~~~

A very simple actor that allows GET/POST methods over HTTP. Also includes
"Basic-Auth" authentication.

**Actor-specific Documentation**

-  `misc.GenericHTTP <actors/misc.GenericHTTP.rst>`__

HipChat
~~~~~~~

The Hipchat Actors allow you to send messages to a HipChat room at stages during
your job execution. The actor supports dry mode by validating that the
configured API Token has access to execute the methods, without actually sending
the messages.

**Required Environment Variables**

-  ``HIPCHAT_TOKEN`` - HipChat API Token
-  ``HIPCHAT_NAME`` - HipChat ``message from`` name
    (defaults to ``Kingpin``)

**Actor-specific Documentation**

-  `hipchat.Message <actors/hipchat.Message.rst>`__
-  `hipchat.Topic <actors/hipchat.Topic.rst>`__

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
