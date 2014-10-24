# Kingpin: the chief element of any system, plan, or the like.

[![Build Status](https://travis-ci.org/Nextdoor/kingpin.svg?branch=master)](https://travis-ci.org/Nextdoor/kingpin)
[![# of downloads](https://pypip.in/d/kingpin/badge.png)](https://pypi.python.org/pypi/kingpin)
[![pypy version](https://badge.fury.io/py/kingpin.png)](https://pypi.python.org/pypi/kingpin)

The Kingpin of your Deployment Model

## Installation

The simplest installation method is via [PyPI](https://pypi.python.org/pypi/kingpin).

    $ pip install kingpin

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

## Basic Use

    Usage: kingpin <options>

    Options:
      --version             show program's version number and exit
      -h, --help            show this help message and exit
      -j JSON, --json=JSON  Path to JSON Deployment File
      -d, --dry             Executes a DRY run.
      -l LEVEL, --level=LEVEL
                            Set logging level (INFO|WARN|DEBUG|ERROR)

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
be notified immediately.

#### The Script
Definition: _The blueprint or roadmap that outlines a movie story through
visual descriptions, actions of characters and their dialogue. The term
"script" also applies to stageplays as well._

Every Kingpin _script_ is a chunk of JSON-encoded data that contains _actors_.
Each _actor_ configuration includes the same three parameters: _actor_, _desc_
and _options_.

The simplest script will have a single configuration that executes a single
_actor_. More complex scripts can be created with our _group.Sync_ and
_group.Async_ actors which can be used to group together multiple _actors_ and
execute them in a predictable order.

##### Schema Description

The JSON schema is simple. We take a single JSON object that has a few fields:

  * `actor` - A text-string describing the name of the Actor package and class.
    For example, `kingpin.actors.rightscale.server_array.Clone`, or
    `misc.Sleep`.
  * `desc` - A text-string describing the name of the stage or action. Meant to
    ensure that the logs are very human readable.
  * `warn_on_failure` - True/False whether or not to ignore an Actors failure and
    return True anyways. Defaults to `False`, but if `True` a `warning` message
    is logged.
  * `options` - A dictionary of key/value pairs that are required for the
    specific `actor` that you're instantiating. See individual Actor
    documentation below for these options.

The simples JSON file could look like this:

    { "desc": "Hipchat: Notify Oncall Room",
      "actor": "hipchat.Message",
      "warn_on_failure": true,
      "options": {
        "message": "Beginning release %RELEASE%", "room": "Oncall"
      }
    }

However, much more complex configurations can be created by using the
`group.Sync` and `group.Async` actors to describe massively more complex
deployents.

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

##### Token-replacement

In an effort to allow for more re-usable JSON files, _tokens_ can be inserted
into the raw JSON file like this `%TOKEN_NAME`. These will then be dynamically
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

##### Early Actor Instantiation

Again, in an effort to prevent mid-run errors, we pre-instantiate all Actor
objects all at once before we ever begin executing code. This ensures that
major typos or misconfigurations in the JSON will be caught early on.

### The Actors
Definition: _a participant in an action or process._

#### Base Actors

Kingpin provides several internal actors that can be used to create complex
and reliable groups of actions to be executed.

**Optional Environment Variables**

  * `URLLIB_DEBUG` - Set this variable to enable extreme debug logging of the
    URLLIB requests made by the RightScale/AWS actors.
    _Note, this is very insecure as headers/cookies/etc. are exposed_

**Actor-specific Documentation**

  * [misc.Sleep](docs/actors/misc.Sleep.md)
  * [group.Sync](docs/actors/group.Sync.md)
  * [group.Async](docs/actors/group.Async.md)

#### AWS

The AWS Actors allow you to interact with the resources (such as SQS and ELB)
inside your Amazon AWS account. These actors all support dry runs properly, but
each actor has its own caveats with `dry=True`. Please read the instructions
below for using each actor.

**Required Environment Variables**

  * `AWS_ACCESS_KEY_ID` - Your AWS access key
  * `AWS_SECRET_ACCESS_KEY` - Your AWS secret

**Actor-specific Documentation**

  * [aws.elb.WaitUntilHealthy](docs/actors/aws.elb.WaitUntilHealthy.md)
  * [aws.sqs.Create](docs/actors/aws.sqs.Create.md)
  * [aws.sqs.WaitUntilEmpty](docs/actors/aws.sqs.WaitUntilEmpty.md)
  * [aws.sqs.Delete](docs/actors/aws.sqs.Delete.md)

#### HipChat

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

#### Librato

The Librato Actor allows you to post an Annotation to Librato. This is
specifically useful for marking when deployments occur on your graphs for
cause/effect analysis.

**Required Environment Variables**

  * `LIBRATO_TOKEN` - Librato API Token
  * `LIBRATO_EMAIL` - Librato email account (i.e. username)

**Actor-specific Documentation**

  * [librato.Annotation](docs/actors/librato.Annotation.md)

#### RightScale

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

## Development

Development-specific documentation can be found [here](docs/DEVELOPMENT.md)
