# Kingpin: The Deployment Director

Automated Deployment Engine

## Basic Use

TODO

### Credentials

TODO

### DSL

TODO

### Actors

#### HipChat

The Hipchat Actors allow you to send messages to a HipChat room during
as stages during your job execution. The actor supports dry mode by validating
that the configured API Token has access to execute the methods, without
actually sending the messages.

**Required Environment Variables**

  * `HIPCHAT_TOKEN` - HipChat API Token
  * `HIPCHAT_NAME` - HipChat `message from` name
    (defaults to `Kingpin`)

##### hipchat.Message

Sends a message to a room in HipChat

**Options**

  * `room` - The string-name (or ID) of the room to send a message to
  * `message` - String of the message to send

Examples

    { 'room': 'Operations', 'message': 'Beginning Deploy: v1.2' }

**Dry Mode**

Fully supported -- does not actually send messages to a room, but validates
that the API credentials would have access to send the message using the
HipChat `auth_test` optional API argument.

#### RightScale

The RightScale Actors allow you to interact with resources inside your
Rightscale account. These actors all support dry runs properly, but each
actor has its own caveats with `dry=True`. Please read the instructions
below for using each actor.

**Required Environment Variables**

  * `RIGHTSCALE_TOKEN` - RightScale API Refresh Token
     (from the _Account Settings/API Credentials_ page)
  * `RIGHTSCALE_ENDPOINT` - You're account-specific API Endpoint
     (defaults to `https://my.rightscale.com`)

##### rightscale.server_array.Clone

Clones a ServerArray in RightScale and renames it to the newly supplied name.

**Options**

  * `source` - The name of the ServerArray to clone
  * `dest`   - The new name for your cloned ServerArray

Examples

    # Clone my-template-array to my-new-array
    { 'source': 'my-template-array', 'dest': 'my-new-array' }

**Dry Mode**

In Dry mode this actor _does_ validate that the `source` array exists. If it
does not, a `rightscale.api.ServerArrayException` is thrown. Once that has
been validated, the dry mode execution pretends to copy the array by creating
a mocked cloned array resource. This mocked resource is then operated on during
the rest of the execution of the actor, guaranteeing that no live resources are
modified.

Example _dry_ output:

    [Copy Test (DRY Mode)] Verifying that array "template" exists
    [Copy Test (DRY Mode)] Verifying that array "new" does not exist
    [Copy Test (DRY Mode)] Cloning array "template"
    [Copy Test (DRY Mode)] Renaming array "<mocked clone of template>" to "new"

##### rightscale.server_array.Update

Updates an existing ServerArray in RightScale with the supplied parameters. Can
update any parameter that is described in the RightScale API docs here:

  [Resource/ServerArrays #update Method](http://reference.rightscale.com/api1.5/resources/ResourceServerArrays.html#update)

Parameters are passed into the actor in the form of a dictionary, and are
then converted into the RightScale format. See below for examples.

**Options**

  * `array`  - The name of the ServerArray to update
  * `params` - Dictionary of parameters to update

Examples

    # Update the server array name, and set its min_count to 4
    { 'array': 'my-new-array',
      'params': { 'elasticity_params': { 'bounds': { 'min_count': 4 } },
                  'name': 'my-really-new-name' } }

**Dry Mode**

In Dry mode this actor _does_ search for the `array`, but allows it to be
missing because its highly likely that the array does not exist yet. If the
array does not exist, a mocked array object is created for the rest of the
execution.

During the rest of the execution, the code bypasses making any real changes
and just tells you what changes it would have made.

_This means that the dry mode cannot validate that the supplied inputs will
work._

Example _dry_ output:

    [Update Test (DRY Mode)] Verifying that array "new" exists
    [Update Test (DRY Mode)] Array "new" not found -- creating a mock.
    [Update Test (DRY Mode)] Would have updated "<mocked array new>" with
    params: {'server_array[name]': 'my-really-new-name',
             'server_array[elasticity_params][bounds][min_count]': '4'}

##### rightscale.server_array.Launch

Launches instances in an existing ServerArray and waits until that array
has become healthy before returning. _Healthy_ means that the array has
at least the `min_count` number of instances running as defined by the
array definition in RightScale.

_Note: Explicitly enables the array so that auto-scaling functions as well_

**Options**

  * `array` - The name of the ServerArray to launch

Examples

    # Launch the newly created array and wait until all 4 instances
    # have booted and are marked Operational
    { 'array': 'my-array' }
    
**Dry Mode**

In Dry mode this actor _does_ search for the `array`, but allows it to be
missing because its highly likely that the array does not exist yet. If the
array does not exist, a mocked array object is created for the rest of the
execution.

During the rest of the execution, the code bypasses making any real changes
and just tells you what changes it would have made.

Example _dry_ output:

    [Launch Array Test #0 (DRY Mode)] Verifying that array "my-array" exists
    [Launch Array Test #0 (DRY Mode)] Array "my-array" not found -- creating a 
        mock.
    [Launch Array Test #0 (DRY Mode)] Enabling Array "my-array"
    [Launch Array Test #0 (DRY Mode)] Launching Array "my-array" instances
    [Launch Array Test #0 (DRY Mode)] Would have launched instances of array
        <MagicMock name='my-array.self.show().soul.__getitem__()'
        id='4420453200'>
    [Launch Array Test #0 (DRY Mode)] Pretending that array <MagicMock 
        name='my-array.self.show().soul.__getitem__()' id='4420453200'>
        instances are launched.

##### rightscale.server_array.Destroy

Destroys a ServerArray in RightScale by terminating all of the running
instances, marking the array to be disabled, and then deleting the array
as soon as all of the running instances have been terminated.

**Options**

  * `array`     - The name of the ServerArray to destroy
  * `terminate` - Boolean True/False whether or not to terminate all of
    the live running instances before destroying the array.

Examples

    # Terminate all running instances and destroy our new array
    { 'array': 'my-array', 'terminate': True }

**Dry Mode**

In Dry mode this actor _does_ search for the `array`, but allows it to be
missing because its highly likely that the array does not exist yet. If the
array does not exist, a mocked array object is created for the rest of the
execution.

During the rest of the execution, the code bypasses making any real changes
and just tells you what changes it would have made.

Example _dry_ output:

    [Destroy Test (DRY Mode)] Verifying that array "my-array" exists
    [Destroy Test (DRY Mode)] Array "my-array" not found -- creating a mock.
    [Destroy Test (DRY Mode)] Disabling Array "my-array"
    [Destroy Test (DRY Mode)] Would have terminated all array "<mocked array
                              my-array>" instances.
    [Destroy Test (DRY Mode)] Pretending that array <mocked array my-array>
                              instances are terminated.
    [Destroy Test (DRY Mode)] Pretending to destroy array "<mocked array
                              my-array>"

##### rightscale.server_array.Execute

Executes a RightScript or Recipe on a set of hosts in a ServerArray in
RightScale using individual calls to the live running instances.

The RightScale API offers a `multi_run_executable` method that can be used
to run a single script on all servers in an array -- but unfortunately this
API method provides no way to monitor the progress of the individual jobs
on the hosts. Furthermore, the method often executes on recently terminated
or terminating hosts, which throws false-negative error results.

Our actor explicitly retrieves a list of the _operational_ hosts in an array
and kicks off individual execution tasks for every host. It then tracks the
execution of those tasks from start to finish and returns the results.

**Options**

  * `array`    - The name of the ServerArray to operate on
  * `script`   - The name of the RightScript or Recipe to execute
  * `inputs`   - Dictionary of Key/Value pairs to use as inputs for the script

Examples

    # If you have a script named 'connect to elb' that takes a single text
    # input named ELB_NAME.
    { 'array': 'my-array',
      'script': 'connect to elb',
      'inputs': { 'ELB_NAME': 'text:my-elb' } }

**Dry Mode**

In Dry mode this actor _does_ search for the `array`, but allows it to be
missing because its highly likely that the array does not exist yet. If the
array does not exist, a mocked array object is created for the rest of the
execution.

During the rest of the execution, the code bypasses making any real changes
and just tells you what changes it would have made.

Example _dry_ output:

    [Destroy Test (DRY Mode)] Verifying that array "my-array" exists

    [Execute Test (DRY Mode)] kingpin.actors.rightscale.server_array.Execute
                              Initialized
    [Execute Test (DRY Mode)] Beginning execution
    [Execute Test (DRY Mode)] Verifying that array "my-array" exists
    [Execute Test (DRY Mode)] Would have executed "Connect instance to ELB"
        with inputs "{'inputs[ELB_NAME]': 'text:my-elb'}" on "my-array".
    [Execute Test (DRY Mode)] Returning result: True

## Development

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
        |       +-- Update
        |       +-- Launch
        |       +-- Destroy
        |
        +-- actors.aws
        |   | Amazon Web Services Actor
        |
        +-- actors.email
        |   | Email Actor
        |
        +-- actors.hipchat
        |   | Hipchat Actor
        |
        +-- actors.librator
            | Librator Metric Actor


### Setup

    # Create a dedicated Python virtual environment and source it
    virtualenv --no-site-packages .venv
    unset PYTHONPATH
    source .venv/bin/activate

    # Install the dependencies
    make build

    # Run the tests
    make test

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
