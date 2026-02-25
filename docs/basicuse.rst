Basic Use
---------

For basic command line options, run:

.. code-block:: console

    $ kingpin --help

The simplest use cases of this code can be better understood by looking at the
:download:`simple.json <../examples/simple.json>` file. Executing it is a simple
as this:

.. code-block:: console

    $ kingpin --dry --script examples/simple.json
    2014-09-01 21:18:09,022 INFO      [main stage (DRY Mode)] Beginning
    2014-09-01 21:18:09,022 INFO      [stage 1 (DRY Mode)] Beginning
    2014-09-01 21:18:09,022 INFO      [copy serverA (DRY Mode)] Beginning
    2014-09-01 21:18:09,023 INFO      [copy serverB (DRY Mode)] Beginning
    2014-09-01 21:18:09,027 INFO      [copy serverC (DRY Mode)] Beginning
    2014-09-01 21:18:09,954 INFO      [copy serverA (DRY Mode)] Verifying that array "kingpin-integration-testing" exists
    [...]
    2014-09-01 21:18:14,533 INFO      [stage 3 (DRY Mode)] Finished, success? True
    2014-09-01 21:18:14,533 INFO      [main stage (DRY Mode)] Finished, success? True

Kingpin always executes a dry run before executing. Each actor specifies their
own definition of a dry run. Actors are designed to do as much checking in the
dry run as possible to assure that everything will work during real execution.

It's possible, with extreme discouragement to skip the default dry run by
setting ``SKIP_DRY`` environment variable.

Credentials
~~~~~~~~~~~

In an effort to keep the commandline interface of Kingpin simple, the majority
of the configuration settings used at runtime are actually set as environment
variables. Individual Kingpin Actors have their credential requirements
documented in their specific documentation (*see below*).

JSON/YAML DSL
~~~~~~~~~~~~~

The entire model for the configuration is based on the concept of a JSON or
YAML dictionary that contains at least one *actor* configuration. This
format is highly structured and must rigidly conform to the
:py:mod:`kingpin.schema`.

Validation
^^^^^^^^^^
The script will be validated for schema-conformity as one of the first
things that happens at load-time when the app starts up. If it fails, you will
be notified immediately. This is performed in ``misc.Macro`` actor.

The Script
^^^^^^^^^^

Definition: *The blueprint or roadmap that outlines a movie story through
visual descriptions, actions of characters and their dialogue. The term
"script" also applies to stageplays as well.*

Every Kingpin *script* is a chunk of JSON or YAML-encoded data that contains
*actors*.  Each *actor* configuration includes the same three parameters:
*actor*, and optional *desc*, and *options*.

The simplest script will have a single configuration that executes a single
*actor*. More complex scripts can be created with our ``group.Sync`` and
``group.Async`` actors which can be used to group together multiple *actors* and
execute them in a predictable order.

Schema Description
''''''''''''''''''

The schema is simple. We take a single JSON or YAML object that has a few
fields:

-  ``actor`` - A text-string describing the name of the Actor package
   and class. For example, ``misc.Sleep``
-  ``condition`` - A bool or string that indicates whether or not to
   execute this actor. Most commonly used with a token variable for its value.
-  ``desc`` - A text-string describing the name of the stage or action.
   Meant to ensure that the logs are very human readable. Optional; a
   default description is chosen if you do not supply one.
-  ``warn_on_failure`` - True/False whether or not to ignore an Actors
   failure and return True anyways. Defaults to ``False``, but if ``True``
   a ``warning`` message is logged.
-  ``timeout`` - Maximum time (in *seconds*) for the actor to execute
   before raising an ``ActorTimedOut`` exception.
-  ``options`` - A dictionary of key/value pairs that are required for
   the specific ``actor`` that you're instantiating. See individual Actor
   documentation below for these options.

The simplest JSON file could look like this:

.. code-block:: json

    {
      "actor": "misc.Note",
      "condition": true,
      "warn_on_failure": true,
      "timeout": 30,
      "options": {
        "message": "Beginning release %RELEASE%"
      }
    }

Alternatively, a YAML file would look like this:

.. code-block:: yaml

    actor: misc.Note
    condition: true
    warn_on_failure: true
    timeout: 30
    options:
      message: Beginning release %RELEASE%

To execute multiple actors in one script you should leverage one of grouping
actors such as ``group.Sync`` or ``group.Async``. These actors have their own
options documented below.

There is an ``array`` short hand for ``group.Sync`` for trivial set of actors.

.. code-block:: yaml

    - actor: misc.Note
      options:
        message: Beginning release %RELEASE%
    - actor: next.Actor
      options:
        release_version: version-%RELEASE%

Conditional Execution
'''''''''''''''''''''

The ``base.BaseActor`` definition supports a ``condition`` parameter that can be
used to enable or disable execution of an actor in a given Kingpin run. The
field defaults to enabled, but takes many different values which allow you to
choose whether or not to execute portions of your script.

Conditions that behave as ``False``:

.. code-block:: text

    0, '0', 'False', 'FALse', 'FALSE'

Conditions that behave as ``True``:

.. code-block:: text

    'any string', 'true', 'TRUE', '1', 1

Example usage:

.. code-block:: json

    {
      "actor": "misc.Note",
      "condition": "%SEND_MESSAGE%",
      "warn_on_failure": true,
      "options": {
        "message": "Beginning release %RELEASE%"
      }
    }

JSON Commenting
'''''''''''''''

Because these JSON scripts can get quite large, Kingpin leverages the
``demjson`` package to parse your script. This package is slightly more graceful
when handling syntax issues (extra commas, for example), and allows for
JavaScript style commenting inside of the script.

Alternatively, if you're using YAML then you automatically get slightly easier
syntax parsing, code commenting, etc.

Take this example:

.. code-block:: text

    {
      "actor": "misc.Sleep",
      /* Cool description */
      "desc": 'This is funny',
      "options": {
        /* This shouldn't end with a comma, but does */
        "time": 30,
      },
    }

The above example would fail to parse in most JSON parsers, but in ``demjson``
it works just fine. You could also write this in YAML:

.. code-block:: yaml

    actor: misc.Sleep
    # Some description here...
    desc: This is funny
    # Comments are good!
    options:
      time: 30

Timeouts
''''''''

By *default*, Kingpin actors are set to timeout after 3600s (1 hour).  Each
indivudal actor will raise an ``ActorTimedOut`` exception after this timeout has
been reached. The ``ActorTimedOut`` exception is considered a
``RecoverableActorFailure``, so the ``warn_on_failure`` setting applies here and
thus the failure can be ignored if you choose to.

Additionally, you can override the *global default* setting on the commandline
with an environment variable:

-  ``DEFAULT_TIMEOUT`` - Time (in seconds) to use as the default actor timeout.

Here is an example log output when the timer is exceeded:

.. code-block:: console

    $ DEFAULT_TIMEOUT=1 SLEEP=10 kingpin -s examples/sleep.json
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

You can disable the timeout on any actor by setting ``timeout: 0`` in
your JSON.

*Group Actor Timeouts*

Group actors are special -- as they do nothing but execute other actors.
Although they support the ``timeout: x`` setting, they default to disabling the
timeout (``timeout: 0``). This is done because the individual timeouts are
generally owned by the individual actors. A single actor that fails will
propagate its exception up the chain and through the Group actor just like any
other actor failure.

As an example... If you take the following example code:

.. code-block:: json

    {
      "desc": "Outer group",
      "actor": "group.Sync",
      "options": {
        "acts": [
          {
            "desc": "Sleep 10 seconds, but fail",
            "actor": "misc.Sleep",
            "timeout": 1,
            "warn_on_failure": true,
            "options": {
              "sleep": 10
            }
          },
          {
            "desc": "Sleep 2 seconds, but don't fail",
            "actor": "misc.Sleep",
            "options": {
              "sleep": 2
            }
          }
        ]
      }
    }

The first ``misc.Sleep`` actor will fail, but only warn (``warn_on_failure=True``)
about the failure. The parent ``group.Sync`` actor will continue on and allow the
second ``misc.Sleep`` actor to continue.

.. _token_replacement:

Token-replacement
'''''''''''''''''

*Environmental Tokens*

In an effort to allow for more re-usable JSON files, *tokens* can be inserted
into the JSON/YAML file like this ``%TOKEN_NAME%``. These will then be
dynamically swapped with environment variables found at execution time. Any
missing environment variables will cause the JSON parsing to fail and will
notify you immediately.

For an example, take a look at the :download:`complex.json
<../examples/complex.json>` file, and these examples of execution.

.. code-block:: console

    # Here we forget to set any environment variables
    $ kingpin -s examples/complex.json -d
    2014-09-01 21:29:47,373 ERROR     Invalid Configuration Detected: Found un-matched tokens in JSON string: ['%RELEASE%', '%OLD_RELEASE%']

    # Here we set one variable, but miss the other one
    $ RELEASE=0001a kingpin -s examples/complex.json -d
    2014-09-01 21:29:56,027 ERROR     Invalid Configuration Detected: Found un-matched tokens in JSON string: ['%OLD_RELEASE%']

    # Finally we set both variables and the code begins...
    $ OLD_RELEASE=0000a RELEASE=0001a kingpin -s examples/complex.json -d
    2014-09-01 21:30:03,886 INFO      [Main (DRY Mode)] Beginning
    2014-09-01 21:30:03,886 INFO      [Note: Notify Oncall (DRY Mode)] Beginning release 0001a
    ...

*Default values for variables*

Tokens and Contexts can have default values specified after a pipe `|` in the variable name. Example with tokens:

*sleeper.json*

.. code-block:: json

    {
      "actor": "misc.Sleep",
      "desc": "Sleeping because %DESC%",
      "options": {
        "sleep": "%SLEEP|60%"
      }
    }

*Deep Nested Tokens and Macros (new in 0.4.0)*

In order to allow for more complex Kingpin script definitions with
:py:mod:`misc.Macro`, :py:mod:`group.Sync` and :py:mod:`group.Async` actors,
Kingpin allows for environmental and manually defined tokens to be passed down
from actor to actor. Here's a fairly trivial example. Take this simple
``sleeper.json`` example that relies on a ``%SLEEP%`` and ``%DESC%`` token.


*sleeper.json*

.. code-block:: json

    {
      "actor": "misc.Sleep",
      "desc": "Sleeping because %DESC%",
      "options": {
        "sleep": "%SLEEP%"
      }
    }

One way to run this would be via the command line with the `$SLEEP`
and `$DESC` environment variable set (*output stripped a bit for
readability*):

.. code-block:: console

    $ SKIP_DRY=1 DESC=pigs SLEEP=0.1 kingpin --debug --script sleeper.json
    [Kingpin] Checking for required options: ['macro']
    [Kingpin] Initialized (warn_on_failure=False, strict_init_context=True)
    [Kingpin] Preparing actors from sleeper.json
    [Kingpin] Parsing <open file u'sleeper.json', mode 'r' at 0x10c8ad150>
    [Kingpin] Validating schema for sleeper.json
    Building Actor "misc.Sleep" with args: {'init_tokens': '<hidden>', u'options': {u'sleep': u'0.1'}, u'desc': u'Sleeping because pigs'}
    [Sleeping because pigs] Checking for required options: ['sleep']
    [Sleeping because pigs] Initialized (warn_on_failure=False, strict_init_context=True)

    Lights, camera ... action!

    [Kingpin] Beginning
    [Kingpin] Condition True evaluates to True
    [Kingpin] kingpin.actors.misc.Macro._execute() deadline: None(s)
    [Sleeping because pigs] Beginning
    [Sleeping because pigs] Condition True evaluates to True
    [Sleeping because pigs] kingpin.actors.misc.Sleep._execute() deadline: 3600(s)
    [Sleeping because pigs] Sleeping for 0.1 seconds
    [Sleeping because pigs] Finished successfully, return value: None
    [Sleeping because pigs] kingpin.actors.misc.Sleep.execute() execution time: 0.11s
    [Kingpin] Finished successfully, return value: None
    [Kingpin] kingpin.actors.misc.Macro.execute() execution time: 0.11s


Another way to run this would be with a wrapper script that sets the ``%DESC%``
for you, but still leaves the ``%SLEEP%`` token up to you:

*wrapper.json*

.. code-block:: json

  {
    "actor": "misc.Macro",
    "options": {
      "macro": "sleeper.json",
      "tokens": {
        "DESC": "flying-pigs"
      }
    }
  }

Now, watch us instantiate this wrapper - with `$DESC` and `$SLEEP` set.
Notice how ``%DESC%`` is overridden by the token from the JSON wrapper?

.. code-block:: console

  $ SKIP_DRY=1 DESC=pigs SLEEP=0.1 kingpin --debug --script wrapper.json

  [Kingpin] Checking for required options: ['macro']
  [Kingpin] Initialized (warn_on_failure=False, strict_init_context=True)
  [Kingpin] Preparing actors from wrapper.json
  [Kingpin] Parsing <open file u'wrapper.json', mode 'r' at 0x10f52f150>
  [Kingpin] Validating schema for wrapper.json
  Building Actor "misc.Macro" with args: {'init_tokens': '<hidden>', u'options': {u'tokens': {u'DESC': u'flying-pigs'}, u'macro': u'sleeper.json'}}
  [Macro: sleeper.json] Checking for required options: ['macro']
  [Macro: sleeper.json] Initialized (warn_on_failure=False, strict_init_context=True)
  [Macro: sleeper.json] Preparing actors from sleeper.json
  [Macro: sleeper.json] Parsing <open file u'sleeper.json', mode 'r' at 0x10f52f1e0>
  [Macro: sleeper.json] Validating schema for sleeper.json
  Building Actor "misc.Sleep" with args: {'init_tokens': '<hidden>', u'options': {u'sleep': u'0.1'}, u'desc': u'Sleeping because flying-pigs'}
  [Sleeping because flying-pigs] Checking for required options: ['sleep']
  [Sleeping because flying-pigs] Initialized (warn_on_failure=False, strict_init_context=True)

  Lights, camera ... action!

  [Kingpin] Beginning
  [Kingpin] Condition True evaluates to True
  [Kingpin] kingpin.actors.misc.Macro._execute() deadline: None(s)
  [Macro: sleeper.json] Beginning
  [Macro: sleeper.json] Condition True evaluates to True
  [Macro: sleeper.json] kingpin.actors.misc.Macro._execute() deadline: None(s)
  [Sleeping because flying-pigs] Beginning
  [Sleeping because flying-pigs] Condition True evaluates to True
  [Sleeping because flying-pigs] kingpin.actors.misc.Sleep._execute() deadline: 3600(s)
  [Sleeping because flying-pigs] Sleeping for 0.1 seconds
  [Sleeping because flying-pigs] Finished successfully, return value: None
  [Sleeping because flying-pigs] kingpin.actors.misc.Sleep.execute() execution time: 0.10s
  [Macro: sleeper.json] Finished successfully, return value: None
  [Macro: sleeper.json] kingpin.actors.misc.Macro.execute() execution time: 0.10s
  [Kingpin] Finished successfully, return value: None
  [Kingpin] kingpin.actors.misc.Macro.execute() execution time: 0.11s

*Contextual Tokens*

Once the initial JSON files have been loaded up, we have a second layer of
*tokens* that can be referenced. These tokens are known as *contextual tokens*.
These *contextual tokens* are used during-runtime to swap out *strings* with
*variables*. Currently only the ``group.Sync`` and ``group.Async`` actors have the
ability to define usable tokens, but any actor can then reference these tokens.

*Contextual tokens for simple variable behavior*

.. code-block:: json

    {
      "desc": "Send out notifications",
      "actor": "group.Sync",
      "options": {
        "contexts": [
          { "TEAM": "Systems" }
        ],
        "acts": [
          {
            "desc": "Notify {TEAM}",
            "actor": "misc.Note",
            "options": {
              "message": "Hey {TEAM} .. I'm done with something"
            }
          }
        ]
      }
    }

.. code-block:: console

    2015-01-14 15:03:16,840 INFO      [DRY: Send out notifications] Beginning 1 actions
    2015-01-14 15:03:16,840 INFO      [DRY: Notify Systems] Hey Systems .. I'm done with something

*Contextual tokens used for iteration*

.. code-block:: json

    {
      "actor": "group.Async",
      "options": {
        "contexts": [
          { "TEAM": "Engineering", "WISDOM": "Get back to work" },
          { "TEAM": "Cust Service", "WISDOM": "Have a nice day" }
        ],
        "acts": [
          {
            "desc": "Notify {TEAM}",
            "actor": "misc.Note",
            "options": {
              "message": "Hey {TEAM} .. I'm done with the release. {WISDOM}"
            }
          }
        ]
      }
    }

.. code-block:: console

    2015-01-14 15:02:22,165 INFO      [DRY: kingpin.actor.group.Async] Beginning 2 actions
    2015-01-14 15:02:22,165 INFO      [DRY: Notify Engineering] Hey Engineering .. I'm done with the release. Get back to work
    2015-01-14 15:02:22,239 INFO      [DRY: Notify Cust Service] Hey Cust Service .. I'm done with the release. Have a nice day

Contextual tokens stored in separate file
'''''''''''''''''''''''''''''''''''''''''

When multiple Kingpin JSON files need to leverage the same context for
different purposes it is useful to put the contexts into a stand alone file and
then reference that file. Context files support `token-replacement`_ just like
:py:mod:`misc.Macro` actor. See example below.

*kingpin.json*

.. code-block:: json

    {
      "desc": "Send ending notifications...",
      "actor": "group.Async",
      "options": {
        "contexts": "data/notification-teams.json",
        "acts": [
          {
            "desc": "Notify {TEAM}",
            "actor": "misc.Note",
            "options": {
              "message": "Hey {TEAM} .. I'm done with the release. {WISDOM}"
            }
          }
        ]
      }
    }

*data/notification-teams.json*

.. code-block:: json

    [
      { "TEAM": "Engineering", "WISDOM": "%USER% says: Get back to work" },
      { "TEAM": "Cust Service", "WISDOM": "%USER% says: Have a nice day" }
    ]

Early Actor Instantiation
'''''''''''''''''''''''''

Again, in an effort to prevent mid-run errors, we pre-instantiate all Actor
objects all at once before we ever begin executing code. This ensures that
major typos or misconfigurations in the JSON will be caught early on.

You can test the correctness of all actor instantiation without executing
a run or a dry-run by passing in the `--build-only` flag. Kingpin will exit
with status 0 on success and status 1 if any actor instantiations have failed.


Command-line Execution without JSON
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For the simple case of executing a single actor without too many options, you
are able to pass these options in on the commandline to avoid writing any JSON.

.. code-block:: console

    $ kingpin --actor misc.Sleep --explain
    Sleeps for an arbitrary number of seconds.

    **Options**

    :sleep:
      Integer of seconds to sleep.

    **Examples**

    .. code-block:: json

       {
         "actor": "misc.Sleep",
         "desc": "Sleep for 60 seconds",
         "options": {
           "sleep": 60
         }
       }

    **Dry Mode**

    Fully supported -- does not actually sleep, just pretends to.

``--explain`` provides the same text that is available in this used in this
documentation.


.. code-block:: console

    $ kingpin --actor misc.Sleep --param warn_on_failure=true --option sleep=5
    17:54:53   INFO      Rehearsing... Break a leg!
    17:54:53   INFO      [DRY: Kingpin] Preparing actors from {"actor":"misc.Sleep","desc":"Commandline Execution","options":{"sleep":"5"},"warn_on_failure":"true"}
    17:54:53   INFO      Rehearsal OK! Performing!
    17:54:53   INFO      [Kingpin] Preparing actors from {"actor":"misc.Sleep","desc":"Commandline Execution","options":{"sleep":"5"},"warn_on_failure":"true"}
    17:54:53   INFO
    17:54:53   WARNING   Lights, camera ... action!
    17:54:53   INFO

You can stack as many ``--option`` and ``--param`` command line options as you wish.

.. code-block:: console

    $ kingpin --actor misc.Sleep --param warn_on_failure=true --param condition=false --option "sleep=0.1"
    17:59:46   INFO      Rehearsing... Break a leg!
    17:59:46   INFO      [DRY: Kingpin] Preparing actors from {"actor":"misc.Sleep","condition":"false","desc":"Commandline Execution","options":{"sleep":"0.1"},"warn_on_failure":"true"}
    17:59:46   WARNING   [DRY: Commandline Execution] Skipping execution. Condition: false
    17:59:46   INFO      Rehearsal OK! Performing!
    17:59:46   INFO      [Kingpin] Preparing actors from {"actor":"misc.Sleep","condition":"false","desc":"Commandline Execution","options":{"sleep":"0.1"},"warn_on_failure":"true"}
    17:59:46   INFO
    17:59:46   WARNING   Lights, camera ... action!
    17:59:46   INFO
    17:59:46   WARNING   [Commandline Execution] Skipping execution. Condition: false

