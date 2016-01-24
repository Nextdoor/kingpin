Basic Use
---------

.. code-block:: guess

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
:download:`simple.json <../examples/simple.json>` file. Executing it is a
simple as this:

.. code-block:: bash

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
setting ``SKIP_DRY`` environment variable.

Credentials
~~~~~~~~~~~

In an effort to keep the commandline interface of Kingpin simple, the majority
of the configuration settings used at runtime are actually set as environment
variables. Individual Kingpin Actors have their credential requirements
documented in their specific documentation (*see below*).

JSON-based DSL
~~~~~~~~~~~~~~

The entire model for the configuration is based on the concept of a JSON
dictionary that contains at least one *actor* configuration. This JSON format
is highly structured and must rigidly conform to the :py:mod:`kingpin.schema`.

Validation
^^^^^^^^^^
The JSON file will be validated for schema-conformity as one of the first
things that happens at load-time when the app starts up. If it fails, you will
be notified immediately. This is performed in ``misc.Macro`` actor.

The Script
^^^^^^^^^^

Definition: *The blueprint or roadmap that outlines a movie story through
visual descriptions, actions of characters and their dialogue. The term
"script" also applies to stageplays as well.*

Every Kingpin *script* is a chunk of JSON-encoded data that contains *actors*.
Each *actor* configuration includes the same three parameters: *actor*, *desc*
and *options*.

The simplest script will have a single configuration that executes a single
*actor*. More complex scripts can be created with our ``group.Sync`` and
``group.Async`` actors which can be used to group together multiple *actors* and
execute them in a predictable order.

Schema Description
''''''''''''''''''

The JSON schema is simple. We take a single JSON object that has a few
fields:

-  ``actor`` - A text-string describing the name of the Actor package
   and class. For example, ``kingpin.actors.rightscale.server_array.Clone``,
   or ``misc.Sleep``.
-  ``condition`` - A bool or string that indicates whether or not to
   execute this actor.
-  ``desc`` - A text-string describing the name of the stage or action.
   Meant to ensure that the logs are very human readable.
-  ``warn_on_failure`` - True/False whether or not to ignore an Actors
   failure and return True anyways. Defaults to ``False``, but if ``True``
   a ``warning`` message is logged.
-  ``timeout`` - Maximum time (in *seconds*) for the actor to execute
   before raising an ``ActorTimedOut`` exception is raised.
-  ``options`` - A dictionary of key/value pairs that are required for
   the specific ``actor`` that you're instantiating. See individual Actor
   documentation below for these options.

The simples JSON file could look like this:

.. code-block:: json

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
``group.Sync`` and ``group.Async`` actors to describe massively more
complex deployents.

Conditional Execution
'''''''''''''''''''''

The ``base.BaseActor`` definition supports a ``condition`` parameter that can be
used to enable or disable execution of an actor in a given Kingpin run. The
field defaults to enabled, but takes many different values which allow you to
choose whether or not to execute portions of your script.

Conditions that behave as ``False``::

    0, '0', 'False', 'FALse', 'FALSE'

Conditions that behave as ``True``::

    'any string', 'true', 'TRUE', '1', 1

Example usage:

.. code-block:: json

    { "desc": "Hipchat: Notify Oncall Room",
      "actor": "hipchat.Message",
      "condition": "%SEND_MESSAGE%",
      "warn_on_failure": true,
      "options": {
        "message": "Beginning release %RELEASE%", "room": "Oncall"
      }
    }

JSON Commenting
'''''''''''''''

Because these JSON scripts can get quite large, Kingpin leverages the
``demjson`` package to parse your script. This package is slightly more graceful
when handling syntax issues (extra commas, for example), and allows for
JavaScript style commenting inside of the script.

Take this example::

    { "actor": "misc.Sleep",

      /* Cool description */
      "desc": 'This is funny',

      /* This shouldn't end with a comma, but does */
      "options": { "time": 30 }, }

The above example would fail to parse in most JSON parsers, but in ``demjson``
it works just fine.

Timeouts
''''''''

By *default*, Kingpin actors are set to timeout after 3600s (1 hour).  Each
indivudal actor will raise an ``ActorTimedOut`` exception after this timeout has
been reached. The ``ActorTimedOut`` exception is considered a
``RecoverableActorFailure``, so the ``warn_on_failure`` setting applies here and
thus the failure can be ignored if you choose to.

Additionally, you can override the *global default* setting on the commandline
with an environment variable:

-  ``DEFAULT_TIMEOUT`` - Time (in seconds) to use as the default actor
   timeout.

Here is an example log output when the timer is exceeded:

.. code-block:: bash

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

The first ``misc.Sleep`` actor will fail, but only warn (``warn_on_failure=True``)
about the failure. The parent ``group.Sync`` actor will continue on and allow the
second ``misc.Sleep`` actor to continue.

Token-replacement
'''''''''''''''''

*Environmental Tokens*

In an effort to allow for more re-usable JSON files, *tokens* can be inserted
into the raw JSON file like this ``%TOKEN_NAME%``. These will then be dynamically
swapped with environment variables found at execution time. Any missing
environment variables will cause the JSON parsing to fail and will notify you
immediately.

For an example, take a look at the :download:`complex.json
<../examples/complex.json>` file, and these examples of execution.

.. code-block:: bash

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


*Contextual Tokens*

Once the initial JSON files have been loaded up, we have a second layer of
*tokens* that can be referenced. These tokens are known as *contextual tokens*.
These *contextual tokens* are used during-runtime to swap out *strings* with
*variables*. Currently only the ``group.Sync`` and ``group.Async`` actors have the
ability to define usable tokens, but any actor can then reference these tokens.

*Contextual tokens for simple variable behavior*

.. code-block:: json

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

.. code-block:: bash

    2015-01-14 15:03:16,840 INFO      [DRY: Send out hipchat notifications] Beginning 1 actions
    2015-01-14 15:03:16,840 INFO      [DRY: Notify Systems] Sending message "Hey room .. I'm done with something" to Hipchat room "Systems"

*Contextual tokens used for iteration*

.. code-block:: json

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

.. code-block:: bash

    2015-01-14 15:02:22,165 INFO      [DRY: Send ending notifications...] Beginning 2 actions
    2015-01-14 15:02:22,165 INFO      [DRY: Notify Engineering] Sending message "Hey room .. I'm done with the release. Get back to work" to Hipchat room "Engineering"
    2015-01-14 15:02:22,239 INFO      [DRY: Notify Cust Service] Sending message "Hey room .. I'm done with the release. Have a nice day" to Hipchat room "Cust Service"

Contextual tokens stored in separate file
'''''''''''''''''''''''''''''''''''''''''

When multiple Kingpin JSON files need to leverage the same context for
different purposes it is useful to put the contexts into a stand alone file and
then reference that file. Context files support `token-replacement`_ just like
:py:mod:`misc.Macro` actor. See example below.

*kingpin.json*

.. code-block:: json

    { "desc": "Send ending notifications...",
      "actor": "group.Async",
      "options": {
        "contexts": {
          "file": "data/notification-rooms.json",
          "tokens": {
            "USER": "%USER%",
          }
        },
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

*data/notification-rooms.json*

.. code-block:: json

    [
      { "ROOM": "Engineering", "WISDOM": "%USER% says: Get back to work" },
      { "ROOM": "Cust Service", "WISDOM": "%USER% says: Have a nice day" }
    ]

Early Actor Instantiation
'''''''''''''''''''''''''

Again, in an effort to prevent mid-run errors, we pre-instantiate all Actor
objects all at once before we ever begin executing code. This ensures that
major typos or misconfigurations in the JSON will be caught early on.

Command-line Execution without JSON
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For the simple case of executing a single actor without too many options, you
are able to pass these options in on the commandline to avoid writing any JSON.

.. code-block:: bash

    $ kingpin --actor misc.Sleep --explain
    Sleeps for an arbitrary number of seconds.

    **Options**

    :sleep:
      Integer of seconds to sleep.

    **Examples**

    .. code-block:: json

       { "actor": "misc.Sleep",
         "desc": "Sleep for 60 seconds",
         "options": {
           "sleep": 60
         }
       }

    **Dry Mode**

    Fully supported -- does not actually sleep, just pretends to.

``--explain`` provides the same text that is available in this used in this
documentation.


.. code-block:: bash

    $ kingpin --actor misc.Sleep --param warn_on_failure=true --option sleep=5
    17:54:53   INFO      Rehearsing... Break a leg!
    17:54:53   INFO      [DRY: Kingpin] Preparing actors from {"actor":"misc.Sleep","desc":"Commandline Execution","options":{"sleep":"5"},"warn_on_failure":"true"}
    17:54:53   INFO      Rehearsal OK! Performing!
    17:54:53   INFO      [Kingpin] Preparing actors from {"actor":"misc.Sleep","desc":"Commandline Execution","options":{"sleep":"5"},"warn_on_failure":"true"}
    17:54:53   INFO
    17:54:53   WARNING   Lights, camera ... action!
    17:54:53   INFO

You can stack as many ``--option`` and ``--param`` command line options as you wish.

.. code-block:: bash

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

