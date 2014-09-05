##### rightscale.server_array.Launch

Launches instances in an existing ServerArray and waits until that array has
become healthy before returning. _Healthy_ means that the array has at least
the user-specified `count` or `min_count` number of instances running as
defined by the array definition in RightScale.

**Options**

  * `array` - The name of the ServerArray to launch
  * `count` - Optional number of instance to launch. Defaults to min_count
    of the array.
  * `enable` - should the autoscaling of the array be enabled? Settings this
    to False, or omitting the parameter will not disable an enabled array.

Examples

    # Enable the newly created array and wait until all instances
    # have booted and are marked Operational
    { 'array': 'my-array',
      'enable': True}
    
    # Do not enable the newly created array, Launch 1 instance, and wait until
    # 1 instance has booted and is marked Operational
    { 'array': 'my-array',
      'count': 1 }
    
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
