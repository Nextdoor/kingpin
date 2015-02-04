## Development

### Setting up your Environment

#### Create your VirtualEnvironment

    $ virtualenv .venv --no-site-packages
    New python executable in .venv/bin/python
    Installing setuptools, pip...done.
    $ source .venv/bin/activate

#### Check out the code

    (.venv) $ git clone git@github.com:Nextdoor/kingpin
    Cloning into 'kingpin'...
    Warning: Permanently added 'github.com,192.30.252.128' (RSA) to the list of known hosts.
    remote: Counting objects: 1831, done.
    remote: irangedCompressing objects: 100% (17/17), done.
    remote: Total 1831 (delta 7), reused 0 (delta 0)
    Receiving objects: 100% (1831/1831), 287.68 KiB, done.
    Resolving deltas: 100% (1333/1333), done.

#### Install the test-specific dependencies

    (.venv) $ pip install -r kingpin/requirements.test.txt
    ...
    (.venv) $ cd kingpin
    (.venv) $ python setup.py test
    ...

### Testing

#### Unit Tests

The code is 100% unit test coverage complete, and no pull-requests will be
accepted that do not maintain this level of coverage. That said, its possible
(_likely_) that we have not covered every possible scenario in our unit tests
that could cause failures. We will strive to fill out every reasonable failure
scenario.

#### Integration Tests

Because its hard to predict cloud failures, we provide integration tests for
most of our modules. These integration tests actually go off and execute real
operations in your accounts, and rely on particular environments being setup
in order to run. These tests are great to run though to validate that your
credentials are all correct.

Specific integration test notes are below, describing what is required to run
each set of tests.

Executing the tests:

    HIPCHAT_TOKEN=<xxx> RIGHTSCALE_TOKEN=<xxx> make integration

    PYFLAKES_NODOCTEST=True python setup.py integration pep8 pyflakes
    running integration
    integration_01_clone_dry (integration_server_array.IntegrationServerArray) ... ok
    integration_02a_clone (integration_server_array.IntegrationServerArray) ... ok
    integration_02b_clone_with_duplicate_array (integration_server_array.IntegrationServerArray) ... ok
    integration_03a_update_params (integration_server_array.IntegrationServerArray) ... ok
    integration_03b_update_with_invalid_params (integration_server_array.IntegrationServerArray) ... ok
    integration_04_launch (integration_server_array.IntegrationServerArray) ... ok
    integration_05_destroy (integration_server_array.IntegrationServerArray) ... ok
    integration_test_execute_real (integration_hipchat.IntegrationHipchatMessage) ... ok
    integration_test_execute_with_invalid_creds (integration_hipchat.IntegrationHipchatMessage) ... ok
    integration_test_init_without_environment_creds (integration_hipchat.IntegrationHipchatMessage) ... ok

    Name                                     Stmts   Miss  Cover   Missing
    ----------------------------------------------------------------------
    kingpin                                      0      0   100%   
    kingpin.actors                               0      0   100%   
    kingpin.actors.base                         62      5    92%   90, 95, 146, 215-216
    kingpin.actors.exceptions                    4      0   100%   
    kingpin.actors.hipchat                      58      5    91%   59, 111-118
    kingpin.actors.misc                         17      5    71%   47-49, 57-62
    kingpin.actors.rightscale                    0      0   100%   
    kingpin.actors.rightscale.api              137     46    66%   153-164, 251-258, 343-346, 381-382, 422-445, 466-501
    kingpin.actors.rightscale.base              31      3    90%   36, 49, 79
    kingpin.actors.rightscale.server_array     195     49    75%   59-62, 68-72, 79, 174, 190-196, 213-216, 249-250, 253-256, 278-281, 303-305, 377-380, 437-440, 501-505, 513-547
    kingpin.utils                               67     30    55%   57-69, 78, 93-120, 192-202
    ----------------------------------------------------------------------
    TOTAL                                      571    143    75%   
    ----------------------------------------------------------------------
    Ran 10 tests in 880.274s

    OK
    running pep8
    running pyflakes

##### kingpin.actor.rightscale.server\_array

These tests clone a ServerArray, modify it, launch it, and destroy it. They
rely on an existing ServerArray template being available and launchable in
your environment. For simple testing, I recommend just using a standard
RightScale ServerTemplate.

**Required RightScale Resources**

  * ServerArray: _kingpin-integration-testing_
    Any ServerArray that launches a server in your environment.
  * RightScript: _kingpin-integration-testing-script_
    Should be a script that sleeps for a specified amount of time.
    **Requires `SLEEP` input**

### Class/Object Architecture

    kingpin.rb
    |
    +-- deployment.Deployer
        | Executes a deployment based on the supplied DSL.
        |
        +-- actors.rightscale
        |   | RightScale Cloud Management Actor
        |   |
        |   +-- server_array
        |       +-- Clone
        |       +-- Destroy
        |       +-- Execute
        |       +-- Launch
        |       +-- Update
        |
        +-- actors.aws
        |   | Amazon Web Services Actor
        |   |
        |   +-- elb
        |   |   +-- WaitUntilHealthy
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

### Setup

    # Create a dedicated Python virtual environment and source it
    virtualenv --no-site-packages .venv
    unset PYTHONPATH
    source .venv/bin/activate

    # Install the dependencies
    make build

    # Run the tests
    make test

### Actor Design

Kingpin Actors are self-contained python classes that execute operations
asynchronously. Actors should follow a consistent structure (described below)
and be written to be as fault tolerant as possible.

#### Hello World Actor Example

This is the basic structure for an actor class.

```python
import os

from tornado import gen

from kingpin.actors import base
from kingpin.actors import exceptions

# All actors must have an __author__ tag. This is used actively
# by the Kingpin code, do not forget this!
__author__ = 'Billy Joe Armstrong <american_idiot@broadway.com'

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
    # wrapped in a gen.Coroutine wrapper. Note, the _execute() method takes
    # no arguments, all arguments for the acter were passed in to the
    # __init__() method.
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
```



#### Required Options

The following options are baked into our *BaseActor* model and must be
supported by any actor that subclasses it. They are fundamentally critical to
the behavior of Kingpin, and should not be bypassed or ignored.

##### `desc`

A string describing the stage or action thats occuring. Meant to be human
readable and useful for logging. You do not need to do anything intentinally to
support this option (its handled in
*kingpin.actors.base.BaseActor.__init__()*).

##### `dry`

All Actors *must* support a `dry` run flag. The codepath thats executed when
`_execute()` is yielded should be as wet as possible without actually making
any changes. For example, if you have an actor that checks the state of an
Amazon ELB (*hint see aws.elb.WaitUntilHealthy*), you would want the actor to
actually search Amazons API for the ELB, actually check the number of instances
that are healthy in the ELB, and then fake a return value so that the rest of
the script can be tested.

##### `options`

Your actor can take in custom options (ELB name, Route53 DNS entry name, etc)
through a dictionary named `options` thats passed in to every actor and stored
as `self._options`. The contents of this dictionary are entirely up to you.

##### `warn_on_failure` (*optional*)

If the user sets `warn_on_failure=True`, any raised exceptions that subclass
`kingpin.actors.exceptions.RecoverableActorFailure` will be swallowed up and
warned about, but will not cause the execution of the kingpin script to end.

Exceptions that subclass `kingpin.actors.exceptions.UnrecoverableActorFailure`
(or uncaught third party exceptions) will cause the actor to fail and the
script to be aborted **no matter what!**

#### Required Methods

##### _execute() method

Your actor can execute any code you would like in the `_execute()` method. This
method should make sure that its a tornado-style generator (thus, can be
yielded), and that it never calls any blocking operations.

Actors must *not*:
  * Call a blocking operation ever
  * Call an async operation from inside the __init__() method
  * Bypass normal logging methods
  * `return` a result (should `raise gen.Return(...)`)

Actors must:
  * Subclass *kingpin.actors.base.BaseActor* 
  * Include `__author__` attribute thats a single *string* with the owners
    listed in it.
  * Implement a *_execute()* method
  * Handle as many possible exceptions of third-party libraries as possible
  * Return None when the actor has succeeded.

Actors can:
  * Raise *kingpin.actors.exceptions.UnrecoverableActorFailure*.
    This is considered an unrecoverable exception and no Kingpin will not
    execute any further actors when this happens.

  * Raise *kingpin.actors.exceptions.RecoverableActorFailure*.
    This is considered an error in execution, but is either expected or at
    least cleanly handled in the code. It allows the user to specify
    `warn_on_failure=True`, where they can then continue on in the script even
    if an actor fails.

**Super simple example Actor _execute() method**

    @gen.coroutine
    def _execute(self):
        self.log.info('Making that web call')
        res = yield self._post_web_call(URL)
        raise gen.Return(res)

#### Helper Methods/Objects

##### self.log

For consistency in logging, a custom Logger object is instantiated for every
Actor. This logging object ensures that prefixes such as the `desc` of an Actor
are included in the log messages. Usage examples:

    self.log.error('Hey, something failed')
    self.log.info('I am doing work')
    self.log.warning('I do not think that should have happened')

#### self.option

Accessing options passed to the actor from the JSON file should be done via
`self.option()` method. Accessing `self._options` parameter is not recommended,
and the edge cases should be handled via the `all_options` class variable.

#### Exception Handling

### Simple API Access Objects

Most of the APIs out there leverage basic REST with JSON or XML as the data
encoding method. Since these APIs behave similarly, we have created a simple
API access object that can be extended for creating actors quickly. The object
is called a `RestConsumer` and is in the `kingpin.actors.support.api` package.
This `RestConsumer` can be subclassed and filled in with a `dict` that
describes the API in detail.

#### HTTPBin Actor with the RestConsumer

```python

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
    def __init__(self, *args, **kwargs):
        super(HTTPBinGetThenPost, self).__init__(*args, **kwargs)
        self._api = HTTPBinRestClient()

    @gen.coroutine
    def _execute(self):
        yield self._api.get().http_get()

        if self._dry
            raise gen.Return()

        yield self._api.post().http_post(foo='bar')

        raise gen.Return()
```

### Postfix on Mac OSX

If you want to develop on a Mac OSX host, you need to enable email the
*postfix* daemon on your computer. Here's how!

Modify */Syatem/Library/LaunchDaemons/org.postfix.master.plist*:

    --- /System/Library/LaunchDaemons/org.postfix.master.plist.bak	2014-06-02 11:45:24.000000000 -0700
    +++ /System/Library/LaunchDaemons/org.postfix.master.plist	2014-06-02 11:47:07.000000000 -0700
    @@ -9,8 +9,6 @@
            <key>ProgramArguments</key>
            <array>
                   <string>master</string>
    -              <string>-e</string>
    -              <string>60</string>
            </array>
            <key>QueueDirectories</key>
            <array>
    @@ -18,5 +16,8 @@
            </array>
            <key>AbandonProcessGroup</key>
            <true/>
    +
    +        <key>KeepAlive</key>
    +       <true/>
     </dict>
     </plist>

Restart the service:

    cd /System/Library/LaunchDaemons
    sudo launchctl unload org.postfix.master.plist 
    sudo launchctl load org.postfix.master.plist
