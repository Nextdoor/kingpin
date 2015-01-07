##### rightscale.server_array.Execute

Executes a RightScript or Recipe on a set of hosts in a ServerArray in
RightScale using individual calls to the live running instances. These can be
found in your RightScale account under Design -> RightScript or Cookbooks

The RightScale API offers a `multi_run_executable` method that can be used
to run a single script on all servers in an array -- but unfortunately this
API method provides no way to monitor the progress of the individual jobs
on the hosts. Furthermore, the method often executes on recently terminated
or terminating hosts, which throws false-negative error results.

Our actor explicitly retrieves a list of the _operational_ hosts in an array
and kicks off individual execution tasks for every host. It then tracks the
execution of those tasks from start to finish and returns the results.

**Options**

  * `array` - The name of the ServerArray to operate on
  * `script` - The name of the RightScript or Recipe to execute
  * `execute_runtime` - Expected number of seconds to execute. Default: 5.
  * `inputs` - Dictionary of Key/Value pairs to use as inputs for the script

Examples

    # If you have a script named 'connect to elb' that takes a single text
    # input named ELB_NAME.
    { 'array': 'my-array',
      'script': 'connect to elb',
      'expected_runtime': 3,
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
