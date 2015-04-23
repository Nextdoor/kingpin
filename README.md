# Kingpin: Deployment Automation Engine

[![Build Status](https://travis-ci.org/Nextdoor/kingpin.svg?branch=master)](https://travis-ci.org/Nextdoor/kingpin)
[![# of downloads](https://pypip.in/d/kingpin/badge.png)](https://pypi.python.org/pypi/kingpin)
[![pypy version](https://badge.fury.io/py/kingpin.png)](https://pypi.python.org/pypi/kingpin)

_Kingpin: the chief element of any system, plan, or the like._

Kingpin provides 3 main functions:

 * **API Abstraction** - Job instructions are provided to Kingpin via a JSON based DSL (read below). The schema is strict and consistent from one action to another. 
 * **Automation Engine** - Kingpin is leverages python's [tornado](http://tornado.readthedocs.org/) engine.
 * **Parallel Execution** - Aside from non-blocking network IO, Kingpin can execute any action in parallel with another. (Read group.Async below)

## Table of Contents

1. [Installation](#installation)
    * [Github Checkout/Install](#github-checkoutinstall)
    * [Direct PIP Install](#direct-pip-install)
    * [Zip File Packaging](#zip-file-packaging)
2. [Basic Use](#basic-use)
    * [Credentials](#credentials)
    * [JSON-based DSL](#json-based-dsl)
        * [The Script](#the-script)
        * [Schema Description](#schema-description)
        * [Conditional Execution](#conditional-execution)
        * [JSON Commenting](#json-commenting)
        * [Timeouts](#timeouts)
        * [Token-replacement](#token-replacement)
          * [Environmental Tokens](#environmental-tokens)
          * [Contextual Tokens](#contextual-tokens)
3. [The Actors](#the-actors)
    * [Base Actors](#base-actors)
    * [AWS](#aws)
    * [GenericHTTP](#generichttp)
    * [HipChat](#hipchat)
    * [Librato](#librato)
    * [Pingdom](#pingdom)
    * [RightScale](#rightscale)
    * [Rollbar](#rollbar)
    * [Slack](#slack)
3. [Security](#security)
4. [Development](#development)

## Installation

The simplest installation method is via [PyPI](https://pypi.python.org/pypi/kingpin).

    $ pip install --process-dependency-links kingpin

Note, we *strongly* recommend running the code inside a Python virtual
environment. All of our examples below will show how to do this.

### Github Checkout/Install

    $ virtualenv .venv --no-site-packages
    New python executable in .venv/bin/python
    Installing setuptools, pip...done.
    $ source .venv/bin/activate
    (.venv) $ git clone https://github.com/Nextdoor/kingpin
    Cloning into 'kingpin'...
    remote: Counting objects: 1824, done.
    remote: Compressing objects: 100% (10/10), done.
    remote: Total 1824 (delta 4), reused 0 (delta 0)
    Receiving objects: 100% (1824/1824), 283.35 KiB, done.
    Resolving deltas: 100% (1330/1330), done.
    (.venv)$ cd kingpin/
    (.venv)$ python setup.py install
    warning: no files found matching 'boto/mturk/test/*.doctest'
    warning: no files found matching 'boto/mturk/test/.gitignore'
    zip_safe flag not set; analyzing archive contents...
    ...
    ...

### Direct PIP Install

    $ virtualenv .venv --no-site-packages
    New python executable in .venv/bin/python
    Installing setuptools, pip...done.
    $ source .venv/bin/activate
    (.venv) $ git clone https://github.com/Nextdoor/kingpin
    (.venv)$ pip install --process-dependency-links git+https://github.com/Nextdoor/kingpin.git
    Downloading/unpacking git+https://github.com/Nextdoor/kingpin.git
      Cloning https://github.com/Nextdoor/kingpin.git (to master) to /var/folders/j6/qyd2dp6n3f156h6xknndt35m00010b/T/pip-H9LwNt-build
    ...
    ...

### Zip File Packaging

For the purpose of highly reliable and fast installations, you can also execute
`make package` to generate a Python-executable `.zip` file. This file is built
with all of the dependencies installed inside of it, and can be executed on the
command line very simply:

    $ virtualenv .venv --no-site-packages
    New python executable in .venv/bin/python
    Installing setuptools, pip...done.
    $ source .venv/bin/activate
    $ make kingpin.zip
    $ python kingpin.zip --version
    0.2.5

*VirtualEnv Note*

Its not strictly necessary to set up the virtual environment like we did in the
example above -- but it helps prevent any confusion during the build process
around what packages are available or are not.

## Basic Use

    $ kingpin --help
    Usage: kingpin [json file] <options>

    Options:
      --version             show program's version number and exit
      -h, --help            show this help message and exit
      -j JSON, --json=JSON  Path to JSON Deployment File
      -d, --dry             Executes a dry run only.
      -l LEVEL, --level=LEVEL
                            Set logging level (INFO|WARN|DEBUG|ERROR)
      --debug               Equivalent to --level=DEBUG
      -c, --color           Colorize the log output

The simplest use cases of this code can be better understood by looking at the
[simple.json](examples/simple.json) file. Executing it is a simple as this:

    $ export RIGHTSCALE_TOKEN=xyz
    $ export RIGHTSCALE_ENDPOINT=https://us-3.rightscale.com
    $ (.venv)$ kingpin -j examples/simple.json -d
    2014-09-01 21:18:09,022 INFO      [main stage (DRY Mode)] Beginning
    2014-09-01 21:18:09,022 INFO      [stage 1 (DRY Mode)] Beginning
    2014-09-01 21:18:09,022 INFO      [copy serverA (DRY Mode)] Beginning
    2014-09-01 21:18:09,023 INFO      [copy serverB (DRY Mode)] Beginning
    2014-09-01 21:18:09,027 INFO      [copy serverC (DRY Mode)] Beginning
    2014-09-01 21:18:09,954 INFO      [copy serverA (DRY Mode)] Verifying that array "kingpin-integration-testing" exists
    ...
    2014-09-01 21:18:14,533 INFO      [stage 3 (DRY Mode)] Finished, success? True
    2014-09-01 21:18:14,533 INFO      [main stage (DRY Mode)] Finished, success? True

Kingpin always executes a dry run before executing. Each actor specifies their
own definition of a dry run. Actors are designed to do as much checking in the
dry run as possible to assure that everything will work during real execution.

It's possible, with extreme discouragement to skip the default dry run by
setting `SKIP_DRY` environment variable.

### Credentials

In an effort to keep the commandline interface of Kingpin simple, the majority
of the configuration settings used at runtime are actually set as environment
variables. Individual Kingpin Actors have their credential requirements
documented in their specific documentation (_see below_).

### JSON-based DSL

The entire model for the configuration is based on the concept of a JSON
dictionary that contains at least one _actor_ configuration. This JSON format
is highly structured and must rigidly conform to the [JSON
Schema](kingpin/schema.py).

*Validation*
The JSON file will be validated for schema-conformity as one of the first
things that happens at load-time when the app starts up. If it fails, you will
be notified immediately. This is performed in `misc.Macro` actor.

#### The Script
Definition: _The blueprint or roadmap that outlines a movie story through
visual descriptions, actions of characters and their dialogue. The term
"script" also applies to stageplays as well._

Every Kingpin _script_ is a chunk of JSON-encoded data that contains _actors_.
Each _actor_ configuration includes the same three parameters: _actor_, _desc_
and _options_.

The simplest script will have a single configuration that executes a single
_actor_. More complex scripts can be created with our `group.Sync` and
`group.Async` actors which can be used to group together multiple _actors_ and
execute them in a predictable order.

##### Schema Description

The JSON schema is simple. We take a single JSON object that has a few fields:

  * `actor` - A text-string describing the name of the Actor package and class.
    For example, `kingpin.actors.rightscale.server_array.Clone`, or
    `misc.Sleep`.
  * `condition` - A bool or string that indicates whether or not to execute
    this actor.
  * `desc` - A text-string describing the name of the stage or action. Meant to
    ensure that the logs are very human readable.
  * `warn_on_failure` - True/False whether or not to ignore an Actors failure and
    return True anyways. Defaults to `False`, but if `True` a `warning` message
    is logged.
  * `timeout` - Maximum time (in _seconds_) for the actor to execute before
                raising an `ActorTimedOut` exception is raised.
  * `options` - A dictionary of key/value pairs that are required for the
    specific `actor` that you're instantiating. See individual Actor
    documentation below for these options.

The simples JSON file could look like this:

    { "desc": "Hipchat: Notify Oncall Room",
      "actor": "hipchat.Message",
      "condition": "true",
      "warn_on_failure": true,
      "timeout": 30,
      "options": {
        "message": "Beginning release %RELEASE%", "room": "Oncall"
      }
    }

However, much more complex configurations can be created by using the
`group.Sync` and `group.Async` actors to describe massively more complex
deployents.

##### Conditional Execution

The `base.BaseActor` definition supports a `condition` parameter that can be
used to enable or disable execution of an actor in a given Kingpin run. The
field defaults to enabled, but takes many different values which allow you to
choose whether or not to execute portions of your script.

Conditions that behave as `False`:

    0, '0', 'False', 'FALse', 'FALSE'

Conditions that behave as `True`:

    'any string', 'true', 'TRUE', '1', 1

Example usage:

    { "desc": "Hipchat: Notify Oncall Room",
      "actor": "hipchat.Message",
      "condition": "%SEND_MESSAGE%",
      "warn_on_failure": true,
      "options": {
        "message": "Beginning release %RELEASE%", "room": "Oncall"
      }
    }

##### JSON Commenting

Because these JSON scripts can get quite large, Kingping leverages the
`demjson` package to parse your script. This package is slightly more graceful
when handling syntax issues (extra commas, for example), and allows for
JavaScript style commenting inside of the script.

Take this example:

    { "actor": "misc.Sleep",
    
      /* Cool description */
      "desc": 'This is funny',
    
      /* This shouldn't end with a comma, but does */
      "options": { "time": 30 }, }


The above example would fail to parse in most JSON parsers, but in `demjson`
it works just fine.

##### Timeouts

By _default_, Kingpin actors are set to timeout after 3600s (1 hour). Each
indivudal actor will raise an `ActorTimedOut` exception after this timeout has
been reached. The `ActorTimedOut` exception is considered a
`RecoverableActorFailure`, so the `warn_on_failure` setting applies here and
thus the failure can be ignored if you choose to.

Additionally, you can override the _global default_ setting on the commandline
with an environment variable:

  * `DEFAULT_TIMEOUT` - Time (in seconds) to use as the default actor timeout.

Here is an example log output when the timer is exceeded:

    $ DEFAULT_TIMEOUT=1 SLEEP=10 kingpin -j examples/sleep.json
    11:55:16   INFO      Rehearsing... Break a leg!
    11:55:16   INFO      [DRY: Kingpin] Preparing actors from examples/sleep.json
    11:55:16   INFO      Rehearsal OK! Performing!
    11:55:16   INFO      Lights, camera ... action!
    11:55:16   INFO      [Kingpin] Preparing actors from examples/sleep.json
    11:55:17   ERROR     [Kingpin] kingpin.actors.misc.Macro._execute() execution exceeded deadline: 1s
    11:55:17   ERROR     [Sleep for some amount of time] kingpin.actors.misc.Sleep._execute() execution exceeded deadline: 1s
    11:55:17   CRITICAL  [Kingpin] kingpin.actors.misc.Macro._execute() execution exceeded deadline: 1s
    11:55:17   CRITICAL  [Sleep for some amount of time] kingpin.actors.misc.Sleep._execute() execution exceeded deadline: 1s
    11:55:17   ERROR     Kingpin encountered mistakes during the play.
    11:55:17   ERROR     kingpin.actors.misc.Macro._execute() execution exceeded deadline: 1s

*Disabling the Timeout*

You can disable the timeout on any actor by setting `timeout: 0` in your JSON.

*Group Actor Timeouts*

Group actors are special -- as they do nothing but execute other actors.
Although they support the `timeout: x` setting, they default to disabling the
timeout (`timeout: 0`). This is done because the individual timeouts are
generally owned by the individual actors. A single actor that fails will
propagate its exception up the chain and through the Group actor just like any
other actor failure.

As an example... If you take the following example code:

    { "desc": "Outer group",
      "actor": "group.Sync",
      "options": {
        "acts": [
          { "desc": "Sleep 10 seconds, but fail",
            "actor": "misc.Sleep",
            "timeout": 1,
            "warn_on_failure": true,
            "options": {
              "sleep": 10
            }
          },
          { "desc": "Sleep 2 seconds, but don't fail",
            "actor": "misc.Sleep",
            "options": {
              "sleep": 2
            }
          }
        ]
      }
    }

The first `misc.Sleep` actor will fail, but only warn (`warn_on_failure=True`)
about the failure. The parent `group.Sync` actor will continue on and allow the
second `misc.Sleep` actor to continue.

##### Token-replacement

###### Environmental Tokens

In an effort to allow for more re-usable JSON files, _tokens_ can be inserted
into the raw JSON file like this `%TOKEN_NAME%`. These will then be dynamically
swapped with environment variables found at execution time. Any missing
environment variables will cause the JSON parsing to fail and will notify you
immediately.

For an example, take a look at the [complex.json](examples/complex.json) file,
and these examples of execution.

    # Here we forget to set any environment variables
    $ kingpin -j examples/complex.json -d
    2014-09-01 21:29:47,373 ERROR     Invalid Configuration Detected: Found un-matched tokens in JSON string: ['%RELEASE%', '%OLD_RELEASE%']

    # Here we set one variable, but miss the other one
    $ RELEASE=0001a kingpin -j examples/complex.json -d
    2014-09-01 21:29:56,027 ERROR     Invalid Configuration Detected: Found un-matched tokens in JSON string: ['%OLD_RELEASE%']

    # Finally we set both variables and the code begins...
    $ OLD_RELEASE=0000a RELEASE=0001a kingpin -j examples/complex.json -d
    2014-09-01 21:30:03,886 INFO      [Main (DRY Mode)] Beginning
    2014-09-01 21:30:03,886 INFO      [Hipchat: Notify Oncall Room (DRY Mode)] Beginning
    2014-09-01 21:30:03,886 INFO      [Hipchat: Notify Oncall Room (DRY Mode)] Sending message "Beginning release 0001a" to Hipchat room "Oncall"
    ...

###### Contextual Tokens

Once the initial JSON files have been loaded up, we have a second layer of
_tokens_ that can be referenced. These tokens are known as _contextual tokens_.
These _contextual tokens_ are used during-runtime to swap out _strings_ with
_variables_. Currently only the `group.Sync` and `group.Async` actors have the
ability to define usable tokens, but any actor can then reference these tokens.

*Contextual tokens for simple variable behavior*

    { "desc": "Send out hipchat notifications",
      "actor": "group.Sync",
      "options": {
          "contexts": [ { "ROOM": "Systems" } ],
          "acts": [
              { "desc": "Notify {ROOM}",
                "actor": "hipchat.Message",
                "options": {
                  "room": "{ROOM}",
                    "message": "Hey room .. I'm done with something"
                }
              }
          ]
      }
    }

    2015-01-14 15:03:16,840 INFO      [DRY: Send out hipchat notifications] Beginning 1 actions
    2015-01-14 15:03:16,840 INFO      [DRY: Notify Systems] Sending message "Hey room .. I'm done with something" to Hipchat room "Systems"


*Contextual tokens used for iteration*

    { "desc": "Send ending notifications...", "actor": "group.Async",
      "options": {
        "contexts": [
          { "ROOM": "Engineering", "WISDOM": "Get back to work" },
          { "ROOM": "Cust Service", "WISDOM": "Have a nice day" }
        ],
        "acts": [
          { "desc": "Notify {ROOM}",
            "actor": "hipchat.Message",
            "options": {
                "room": "{ROOM}",
                "message": "Hey room .. I'm done with the release. {WISDOM}"
            }
          }
        ]
      }
    }

    2015-01-14 15:02:22,165 INFO      [DRY: Send ending notifications...] Beginning 2 actions
    2015-01-14 15:02:22,165 INFO      [DRY: Notify Engineering] Sending message "Hey room .. I'm done with the release. Get back to work" to Hipchat room "Engineering"
    2015-01-14 15:02:22,239 INFO      [DRY: Notify Cust Service] Sending message "Hey room .. I'm done with the release. Have a nice day" to Hipchat room "Cust Service"


##### Early Actor Instantiation

Again, in an effort to prevent mid-run errors, we pre-instantiate all Actor
objects all at once before we ever begin executing code. This ensures that
major typos or misconfigurations in the JSON will be caught early on.

## The Actors
Definition: _a participant in an action or process._

### Base Actors

Kingpin provides several internal actors that can be used to create complex
and reliable groups of actions to be executed.

**Optional Environment Variables**

  * `URLLIB_DEBUG` - Set this variable to enable extreme debug logging of the
    URLLIB requests made by the RightScale/AWS actors.
    _Note, this is very insecure as headers/cookies/etc. are exposed_

**Actor-specific Documentation**

  * [misc.Macro](docs/actors/misc.Macro.md)
  * [misc.Sleep](docs/actors/misc.Sleep.md)
  * [group.Sync](docs/actors/group.Sync.md)
  * [group.Async](docs/actors/group.Async.md)

### AWS

The AWS Actors allow you to interact with the resources (such as SQS and ELB)
inside your Amazon AWS account. These actors all support dry runs properly, but
each actor has its own caveats with `dry=True`. Please read the instructions
below for using each actor.

**Required Environment Variables**

  * `AWS_ACCESS_KEY_ID` - Your AWS access key
  * `AWS_SECRET_ACCESS_KEY` - Your AWS secret

**Actor-specific Documentation**

  * [aws.cloudformation.Create](docs/actors/aws.cloudformation.Create.md)
  * [aws.cloudformation.Delete](docs/actors/aws.cloudformation.Delete.md)
  * [aws.elb.DeregisterInstance](docs/actors/aws.elb.DeregisterInstance.md)
  * [aws.elb.RegisterInstance](docs/actors/aws.elb.RegisterInstance.md)
  * [aws.elb.SetCert](docs/actors/aws.elb.SetCert.md)
  * [aws.elb.WaitUntilHealthy](docs/actors/aws.elb.WaitUntilHealthy.md)
  * [aws.iam.DeleteCert](docs/actors/aws.iam.DeleteCert.md)
  * [aws.iam.UploadCert](docs/actors/aws.iam.UploadCert.md)
  * [aws.sqs.Create](docs/actors/aws.sqs.Create.md)
  * [aws.sqs.Delete](docs/actors/aws.sqs.Delete.md)
  * [aws.sqs.WaitUntilEmpty](docs/actors/aws.sqs.WaitUntilEmpty.md)

### GenericHTTP

A very simple actor that allows GET/POST methods over HTTP. Also includes
"Basic-Auth" authentication.

**Actor-specific Documentation**

  * [misc.GenericHTTP](docs/actors/misc.GenericHTTP.md)

### HipChat

The Hipchat Actors allow you to send messages to a HipChat room at stages during
your job execution. The actor supports dry mode by validating that the
configured API Token has access to execute the methods, without actually sending
the messages.

**Required Environment Variables**

  * `HIPCHAT_TOKEN` - HipChat API Token
  * `HIPCHAT_NAME` - HipChat `message from` name
    (defaults to `Kingpin`)

**Actor-specific Documentation**

  * [hipchat.Message](docs/actors/hipchat.Message.md)
  * [hipchat.Topic](docs/actors/hipchat.Topic.md)

### Librato

The Librato Actor allows you to post an Annotation to Librato. This is
specifically useful for marking when deployments occur on your graphs for
cause/effect analysis.

**Required Environment Variables**

  * `LIBRATO_TOKEN` - Librato API Token
  * `LIBRATO_EMAIL` - Librato email account (i.e. username)

**Actor-specific Documentation**

  * [librato.Annotation](docs/actors/librato.Annotation.md)

### Rollbar

The Rollbar Actor allows you to post Deploy messages to Rollbar when you
execute a code deployment.

**Required Environment Variables**

  * `ROLLBAR_TOKEN` - Rollbar API Token

**Actor-specific Documentation**

  * [rollbar.Deploy](docs/actors/rollbar.Deploy.md)


### RightScale

The RightScale Actors allow you to interact with resources inside your
Rightscale account. These actors all support dry runs properly, but each
actor has its own caveats with `dry=True`. Please read the instructions
below for using each actor.

**Required Environment Variables**

  * `RIGHTSCALE_TOKEN` - RightScale API Refresh Token
     (from the _Account Settings/API Credentials_ page)
  * `RIGHTSCALE_ENDPOINT` - Your account-specific API Endpoint
     (defaults to `https://my.rightscale.com`)

**Actor-specific Documentation**

  * [rightscale.server_array.Clone](docs/actors/rightscale.server_array.Clone.md)
  * [rightscale.server_array.Destroy](docs/actors/rightscale.server_array.Destroy.md)
  * [rightscale.server_array.Execute](docs/actors/rightscale.server_array.Execute.md)
  * [rightscale.server_array.Launch](docs/actors/rightscale.server_array.Launch.md)
  * [rightscale.server_array.Update](docs/actors/rightscale.server_array.Update.md)
  * [rightscale.server_array.Terminate](docs/actors/rightscale.server_array.Terminate.md)

### Pingdom

Pingdom actors to pause and unpause checks. These are useful when you are aware
of an expected downtime and don't want to be alerted about it. Also known as
Maintenance mode.

**Required Environment Variables**

  * `PINGDOM_TOKEN` - Pingdom API Token
  * `PINGDOM_USER` - Pingdom Username (email)
  * `PINGDOM_PASS` - Pingdom Password

**Actor-specific Documentation**

  * [pingdom.Pause](docs/actors/pingdom.Pause.md)
  * [pingdom.Unpause](docs/actors/pingdom.Unpause.md)

### Slack

The Slack Actors allow you to send messages to a Slack channel at stages during
your job execution. The actor supports dry mode by validating that the
configured API Token has access to execute the methods, without actually sending
the messages.

**Required Environment Variables**

  * `SLACK_TOKEN` - Slack API Token
  * `SLACK_NAME` - Slack `message from` name
    (defaults to `Kingpin`)

**Actor-specific Documentation**

  * [slack.Message](docs/actors/slack.Message.md)

## Security

Recently urllib3 library has started issuing [InsecurePlatformWarning](https://urllib3.readthedocs.org/en/latest/security.html#insecureplatformwarning).
We [suppress](kingpin/actors/rightscale/api.py) urllib3 warnings to limit log output to Kingping's own.


## Development

Development-specific documentation can be found [here](docs/DEVELOPMENT.md)
