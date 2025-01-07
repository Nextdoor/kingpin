Development
-----------

Setting up your Environment
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check out the code
^^^^^^^^^^^^^^^^^^

.. code-block:: console

    $ git clone https://github.com:Nextdoor/kingpin
    Cloning into 'kingpin'...
    remote: Counting objects: 1831, done.
    remote: irangedCompressing objects: 100% (17/17), done.
    remote: Total 1831 (delta 7), reused 0 (delta 0)
    Receiving objects: 100% (1831/1831), 287.68 KiB, done.
    Resolving deltas: 100% (1333/1333), done.

Create your VirtualEnvironment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: console

    $ make venv
    $ source .venv/bin/activate

Testing
~~~~~~~

Unit Tests
^^^^^^^^^^

The code is 100% unit test coverage complete, and no pull-requests will be accepted that do not maintain this level of coverage. That said, it's possible (*likely*) that we have not covered every possible scenario in our unit tests that could cause failures. We will strive to fill out every reasonable failure scenario.

Executing Only Certain Test Suites
''''''''''''''''''''''''''''''''''

Because not everyone will use or need to test all of our actors, you can
execute only certain subsets of our integration tests if you wish. Simply set
the `INTEGRATION_TESTS` environment variable to a comma-separated list of test
suites. See below for the list.

*Executing only the HTTP Tests*

.. code-block:: console

    $ INTEGRATION_TESTS=http make integration
    INTEGRATION_TESTS=http PYFLAKES_NODOCTEST=True python setup.py integration pep8 pyflakes
    running integration
    integration_base_get (integration_api.IntegrationRestConsumer) ... ok
    integration_delete (integration_api.IntegrationRestConsumer) ... ok
    integration_get_basic_auth (integration_api.IntegrationRestConsumer) ... ok
    integration_get_basic_auth_401 (integration_api.IntegrationRestConsumer) ... ok
    integration_get_json (integration_api.IntegrationRestConsumer) ... ok
    integration_get_with_args (integration_api.IntegrationRestConsumer) ... ok
    integration_post (integration_api.IntegrationRestConsumer) ... ok
    integration_put (integration_api.IntegrationRestConsumer) ... ok
    integration_status_401 (integration_api.IntegrationRestConsumer) ... ok
    integration_status_403 (integration_api.IntegrationRestConsumer) ... ok
    integration_status_500 (integration_api.IntegrationRestConsumer) ... ok
    integration_status_501 (integration_api.IntegrationRestConsumer) ... ok
    ...

*List of Built-In Integration Test Suites*

* aws
* librato
* http
* hipchat
* pingdom
* rollbar
* pingdom
* slack


Class/Object Architecture
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

    kingpin.rb
    |
    +-- deployment.Deployer
        | Executes a deployment based on the supplied DSL.
        |
        +-- actors.aws
        |   | Amazon Web Services Actor
        |   |
        |   +-- sqs
        |       +-- Create
        |       +-- Delete
        |       +-- WaitUntilEmpty
        |
        +-- actors.email
        |   | Email Actor
        |
        +-- actors.hipchat
        |   | Hipchat Actor
        |   |
        |   +-- Message
        |
        +-- actors.librato
            | Librato Metric Actor
            |
            +-- Annotation

Actor Design
~~~~~~~~~~~~

Kingpin Actors are self-contained python classes that execute operations
asynchronously. Actors should follow a consistent structure (described below)
and be written to be as fault tolerant as possible.

Example - Hello World
^^^^^^^^^^^^^^^^^^^^^

This is the basic structure for an actor class.

.. code-block:: python

    import os

    from tornado import gen

    from kingpin.actors import base
    from kingpin.actors import exceptions

    # All actors must have an __author__ tag. This is used actively
    # by the Kingpin code, do not forget this!
    __author__ = 'Billy Joe Armstrong <american_idiot@broadway.com>'

    # Perhaps you need an API token?
    TOKEN = os.getenv('HELLO_WORLD_TOKEN', None)

    class HelloWorld(base.BaseActor):
        # Create an all_options dictionary that contains all of
        # the required and optional options that can be passed into
        # this actor.
        all_options = {
            'name': (str, None, 'Your name'),
            'world': (str, None, 'World we\'re saying hello to!'),
        }

        # Optionally, if you need to do any instantiation-level, non-blocking
        # validation checks (for example, looking for an API token) you can do
        # them in the __init__. Do *not* put blocking code in here.
        def __init__(self, *args, **kwargs):
            super(HelloWorld, self).__init__(*args, **kwargs)
            if not TOKEN:
                raise exceptions.InvalidCredentials(
                    'Missing the "HELLO_WORLD_TOKEN" environment variable.')

            # Initialize our hello world sender object. This is non-blocking.
            self._hello_world = my.HelloWorldSender(token=TOKEN)

        # Its nice to wrap some of your logic into separate methods. This
        # method handles sending the message, or pretends to send the
        # message if we're in a dry run.
        @gen.coroutine
        def _send_message(self, name, world):
            # Attempt to log into the API to sanity check our credentials
            try:
                yield self._hello_world.login()
            except Shoplifter:
                msg = 'Could not log into the world!'
                raise exceptions.UnrecoverableActorFailure(msg)

            # Make sure to support DRY mode all the time!
            if self._dry:
                self.log.info('Would have said Hi to %s' % world)
                raise gen.Return()

            # Finally, send the message!
            try:
                res = yield self._hello_world.send(
                    from=name, to=world)
            except WalkingAlone as e:
                # Lets say that this error is completely un-handleable exception,
                # there's no one to say hello to!
                self.log.critical('Some extra information about this error...')

                # Now, raise an exception that is will stop execution of Kingpin,
                # regardless of the warn_on_failure setting.
                raise exceptions.UnrecoverableActorException('Oh my: %s' % e)

            # Return the value back to the execute method
            raise gen.Return(res)

        # The meat of the work happens in the _execute() method. This method
        # is called by the BaseActor.execute() method. Your method must be
        # wrapped in a gen.Coroutine wrapper.
        #
        # Note, the _execute() method takes no arguments, all arguments for the
        # acter were passed in to the __init__() method.
        @gen.coroutine
        def _execute(self):
            self.log.debug('Warming up the HelloWorld Actor')

            # Fire off an async request to a our private method for sending
            # hello world messages. Get the response and evaluate
            res = yield self._send_message(
                self.option('name'), self.option('world'))

            # Got a response. Did our message really go through though?
            if not res:
                # The world refuses to hear our message... A shame, really, but
                # not entirely critical.
                self.log.error('We failed to get our message out ... just '
                               'letting you know!')
                raise exceptions.RecoverableActorFailure(
                    'A shame, but I suppose they can listen to what they want')

            # We've been heard!
            self.log.info('%s people have heard our message!' % res)

            # Indicate to Tornado that we're done with our execution.
            raise gen.Return()

Actor Parameters
^^^^^^^^^^^^^^^^

The following parameters are baked into our
:py:mod:`~kingpin.actors.base.BaseActor` model and must be supported by any
actor that subclasses it. They are fundamentally critical to the behavior of
Kingpin, and should not be bypassed or ignored.

``desc``
''''''''

A string describing the stage or action thats occuring. Meant to be human
readable and useful for logging. You do not need to do anything intentinally to
support this option (it's handled in :py:mod:`~kingpin.actors.base.BaseActor`).
All logging (when using :ref:`self.log`) are passed through a custom
:py:mod:`~kingpin.actors.base.LogAdapter`.

``dry``
'''''''

All Actors *must* support a ``dry`` run flag. The codepath thats executed when
``_execute()`` is yielded should be as wet as possible without actually making
any changes. For example, if you have an actor that checks the state of an
CloudFormaion stack (*hint see*
:py:mod:`kingpin.actors.aws.cloudformation.Stack`), you would want the actor to
actually search Amazons API for the CFN stack, check its current state,
compare the desired and actual templates, etc.

.. _all_options:

``options``
'''''''''''

Your actor can take in custom options (ELB name, Route53 DNS entry name, etc)
through a dictionary named ``options`` thats passed in to every actor and
accessible through the :py:mod:`~kingpin.actors.base.BaseActor.option()`
method. The contents of this dictionary are entirely up to you.

These options are defined in your class's `all_options` dict. A simple example:

.. code-block:: python

    from kingpin.constants import REQUIRED

    class SayHi(object):
        all_options = {
            'name': (str, REQUIRED, 'What is your name?')
        }

        @gen.coroutine
        def _execute(self):
            self.log.info('Hi %s' % self.option('name'))


For more complex user input validation, see :ref:`option_validation`.

``warn_on_failure`` (*optional*)
''''''''''''''''''''''''''''''''

If the user sets ``warn_on_failure=True``, any raised exceptions that subclass
``kingpin.actors.exceptions.RecoverableActorFailure`` will be swallowed up and
warned about, but will not cause the execution of the kingpin script to end.

Exceptions that subclass ``kingpin.actors.exceptions.UnrecoverableActorFailure``
(or uncaught third party exceptions) will cause the actor to fail and the
script to be aborted **no matter what!**

Required Methods
^^^^^^^^^^^^^^^^

\_execute() method
''''''''''''''''''

Your actor can execute any code you would like in the ``_execute()`` method. This
method should make sure that it's a tornado-style generator (thus, can be
yielded), and that it never calls any blocking operations.

Actors must *not*:

-  Call a blocking operation ever
-  Call an async operation from inside the **init**\ () method
-  Bypass normal logging methods
-  ``return`` a result (should ``raise gen.Return(...)``)

Actors must:

-  Subclass *kingpin.actors.base.BaseActor*
-  Include ``__author__`` attribute thats a single *string* with the
   owners listed in it.
-  Implement a \*\_execute()\* method
-  Handle as many possible exceptions of third-party libraries as possible
-  Return None when the actor has succeeded.

Actors can:

-  Raise *kingpin.actors.exceptions.UnrecoverableActorFailure*.
   This is considered an unrecoverable exception and no Kingpin will not
   execute any further actors when this happens.

-  Raise *kingpin.actors.exceptions.RecoverableActorFailure*.
   This is considered an error in execution, but is either expected or at
   least cleanly handled in the code. It allows the user to specify
   ``warn_on_failure=True``, where they can then continue on in the script
   even if an actor fails.

**Super simple example Actor \_execute() method**

.. code-block:: python

    @gen.coroutine
    def _execute(self):
        self.log.info('Making that web call')
        res = yield self._post_web_call(URL)
        raise gen.Return(res)

Recommended Design Patterns
^^^^^^^^^^^^^^^^^^^^^^^^^^^

State Management Actors
'''''''''''''''''''''''

While many of our actors are designed as code that "does something once" -- ie,
"Create User Foo" -- we are increasingly seeing actors that "ensure a resource
exists." This new pattern is a bit more Puppet-like, and more well suited for
ensuring the state of cloud resources rather than simply creating or destrying
things.

To that end, we have a few recommended guidelines for patterns to follow when
creating actors like this. These guidelines will help breed consistency between
our various actors so that users are never surprised by their behavior.

**Resource attributes should be managed explicitly**

(*See this http://github.com/Nextdoor/issues/342 for more discussion*)

Generally speaking, if an actor manages a resource (call it a `User`), any
parameters, sub resources like group memberships or other attributes should
only be managed by the Actor if they are explicitly defined by the user.

For example, the following code should create a user, and do absolutely nothing
else to the user. Any additional attirbutes (group memberships, or inline IAM
policies) should not be managed:

.. code-block:: json

    { "actor": "aws.iam.User",
      "options": {
        "name": "myuser",
        "state": "present"
      }
    }

On the other hand, if the user does supply groups or inline_policies, the actor
should explicitly manage those and ensure that they exactly match what was
supplied:

.. code-block:: json

    { "actor": "aws.iam.User",
      "options": {
        "name": "myuser",
        "state": "present"
        "inline_policies": "my-policy.json",
        "groups": [
          "admin", "engineers"
        ]
      }
    }

In this case, the `myuser` account should have its groups and inline policies
exactly set to the above settings, and anything that was found to be mismatched
in Amazon should be wiped out.

Helper Methods/Objects
^^^^^^^^^^^^^^^^^^^^^^

.. _self.__class__.desc:

self.__class__.desc
'''''''''''''''''''

The "description" of a particular actor is a parameter that the user can supply
through the JSON if they wish. If no description is supplied, a default
description is supplied by the actor's `self.__class__.desc` attribute. If your
actor wants to supply its own default description, it can be done like this:

.. code-block:: python

    class Sleep(object):
      desc = "Sleeping for {sleep}s"
      all_options = {
        'sleep': (int), REQUIRED, 'Number of seconds to do nothing.')
      }

.. code-block:: console

    $ python kingpin/bin/deploy.py --color --debug -a misc.Sleep -o sleep=10 --dry
    09:55:08   DEBUG    33688 [kingpin.actors.utils                    ] [get_actor_class     ] Tried importing "misc.Sleep" but failed: No module named misc
    09:55:08   DEBUG    33688 [kingpin.actors.misc.Sleep               ] [_validate_options   ] [DRY: Sleeping for 10s] Checking for required options: ['sleep']
    09:55:08   DEBUG    33688 [kingpin.actors.misc.Sleep               ] [__init__            ] [DRY: Sleeping for 10s] Initialized (warn_on_failure=False, strict_init_context=True)
    09:55:08   INFO     33688 [__main__                                ] [main                ]
    09:55:08   WARNING  33688 [__main__                                ] [main                ] Lights, camera ... action!
    09:55:08   INFO     33688 [__main__                                ] [main                ]
    09:55:08   DEBUG    33688 [kingpin.actors.misc.Sleep               ] [execute             ] [DRY: Sleeping for 10s] Beginning
    09:55:08   DEBUG    33688 [kingpin.actors.misc.Sleep               ] [_check_condition    ] [DRY: Sleeping for 10s] Condition True evaluates to True
    09:55:08   DEBUG    33688 [kingpin.actors.misc.Sleep               ] [timeout             ] [DRY: Sleeping for 10s] kingpin.actors.misc.Sleep._execute() deadline: 3600(s)
    09:55:08   DEBUG    33688 [kingpin.actors.misc.Sleep               ] [_execute            ] [DRY: Sleeping for 10s] Sleeping for 10 seconds
    09:55:08   DEBUG    33688 [kingpin.actors.misc.Sleep               ] [execute             ] [DRY: Sleeping for 10s] Finished successfully, return value: None
    09:55:08   DEBUG    33688 [kingpin.actors.misc.Sleep               ] [_wrap_in_timer      ] [DRY: Sleeping for 10s] kingpin.actors.misc.Sleep.execute() execution time: 0.00s

The `format() <https://docs.python.org/2/library/stdtypes.html#str.format>`__
is called with the following key/values as possible variables that can be
parsed at runtime:

  * `actor`: The Actor Package and Class -- ie, `kingpin.actors.misc.Sleep` in
    the example above.
  * `**self._options`: The entire set of options passed into the actor, broken
    out by key/value.

.. _self.log:

self.log()
''''''''''
For consistency in logging, a custom Logger object is instantiated for every
Actor. This logging object ensures that prefixes such as the ``desc`` of an Actor
are included in the log messages. Usage examples:

.. code-block:: python

    self.log.error('Hey, something failed')
    self.log.info('I am doing work')
    self.log.warning('I do not think that should have happened')


.. _self.option():

self.option()
'''''''''''''

Accessing options passed to the actor from the JSON file should be done via
``self.option()`` method. Accessing ``self._options`` parameter is not recommended,
and the edge cases should be handled via the ``all_options`` class variable.

.. _option_validation:

kingpin.actors.utils.dry()
''''''''''''''''''''''''''
The :py:mod:`kingpin.actors.utils.dry()` wrapper quickly allows you to make a
call dry -- so it only warns about execution during a dry run rather than
actually executing.

User Option Validation
''''''''''''''''''''''

While you can rely on :ref:`all_options` for simple validation of strings,
bools, etc -- you may find yourself needing to validate more complex user
inputs. Regular expressions, lists of valid strings, or even full JSON schema
validations.

The Self-Validating Class
.........................

If you create a class with a `validate()` method, Kingpin will automatically
validate a users input against that method. Here's a super simple example that
only accepts words that start with the letter `X`.

.. code-block:: python

    from kingpin.actors.exceptions import InvalidOptions

    class OnlyStartsWithX(object):
        @classmethod
        def validate(self, option):
            if not option.startswith('X'):
                raise InvalidOptions('Must start with X: %s' % option)


    class MyActor(object):
        all_options = {
            (OnlyStartsWithX, REQUIRED, 'Any string that starts with an X')
        }

Pre-Built Option Validators
...........................

We have created a few useful option validators that you can easily leverage in
your own code:

  * :py:mod:`kingpin.constants.StringCompareBase`
  * :py:mod:`kingpin.constants.SchemaCompareBase`

Exception Handling
^^^^^^^^^^^^^^^^^^

Simple API Access Objects
~~~~~~~~~~~~~~~~~~~~~~~~~

Most of the APIs out there leverage basic REST with JSON or XML as the data
encoding method. Since these APIs behave similarly, we have created a simple
API access object that can be extended for creating actors quickly.  The object
is called a ``RestConsumer`` and is in the ``kingpin.actors.support.api`` package.
This ``RestConsumer`` can be subclassed and filled in with a ``dict`` that
describes the API in detail.

HTTPBin Actor with the RestConsumer
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    HTTPBIN = {
        'path': '/',
        'http_methods': {'get': {}},
        'attrs': {
            'get': {
                'path': '/get',
                'http_methods': {'get': {}},
            },
            'post': {
                'path': '/post',
                'http_methods': {'post': {}},
            },
            'put': {
                'path': '/put',
                'http_methods': {'put': {}},
            },
            'delete': {
                'path': '/delete',
                'http_methods': {'delete': {}},
            },
        }
    }


    class HTTPBinRestClient(api.RestConsumer):

        _CONFIG = HTTPBIN
        _ENDPOINT = 'http://httpbin.org'


    class HTTPBinGetThenPost(base.BaseActor):
        def __init__(self, \*args, \**kwargs):
            super(HTTPBinGetThenPost, self).__init__(\*args, \**kwargs)
            self._api = HTTPBinRestClient()

        @gen.coroutine
        def _execute(self):
            yield self._api.get().http_get()

            if self._dry
                raise gen.Return()

            yield self._api.post().http_post(foo='bar')

            raise gen.Return()

Exception Handling in HTTP Requests
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The ``RestClient.fetch()`` method has been wrapped in a ``retry decorator`` that
allows you to define different behaviors based on the exceptions returned from
the fetch method. For example, you may want to handle an HTTPError exception
with a ``401`` error code differently than a ``503`` error code.

You can customize the exception handling by subclassing the
``RestClient``:

.. code-block:: python

    class MyRestClient(api.RestClient):
        _EXCEPTIONS = {
            httpclient.HTTPError: {
                '401': my.CustomException(),
                '403': exceptions.InvalidCredentials,
                '500': my.UnretryableError(),
                '502': exceptions.InvalidOptions,

                # This acts as a catch-all
                '': exceptions.RecoverableActorFailure,
            }
        }
