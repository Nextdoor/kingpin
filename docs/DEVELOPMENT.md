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

#### Required Methods

##### _execute() method

Your actor can execute any code you would like in the `_execute()` method. This
method should make sure that its a tornado-style generator (thus, can be
yielded), and that it never calls any blocking operations.

Actors must *not*:
  * Call a blocking operation ever
  * Bypass normal logging methods
  * `return` a result (should `raise gen.Return(...)`)

Actors must:
  * Subclass *kingpin.actors.base.BaseActor* 
  * Include `__author__` attribute thats a single *string* with the owners
    listed in it.
  * Implement a *_execute()* method
  * Handle as many possible exceptions of third-party libraries as possible
  * Return True/False based on whether the action has succeeded. False
    indicates that the Actor failed, and currently stops execution of the rest
    of the program.

Actors can:
  * Raise *kingpin.actors.exceptions.ActorException* rather than returning
    False. This is considered an unrecoverable exception and no Kingpin will
    not execute any further actors when this happens. This is different than
    returning False though. False should be returned when there were no
    problems in the code or environment, but the action simpy failed (lets say
    you tried to launch an already launched server array). Exceptions should be
    raised when an unexpected failure occurs.

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

Accessing options passed to the actor from the JSON file should be done via `self.option()` method. Accessing `self._options` parameter is not recommended, and the edge cases should be handled via the `all_options` class variable.

#### Exception Handling

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
