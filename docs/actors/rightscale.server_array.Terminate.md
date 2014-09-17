##### rightscale.server_array.Destroy

Terminates all instances for a ServerArray in RightScale marking the array
disabled.

**Options**

  * `array`     - The name of the ServerArray to destroy

Examples

    # Terminate all running instances array
    { 'array': 'my-array' }

**Dry Mode**

In Dry mode this actor _does_ search for the `array`, but allows it to be
missing because its highly likely that the array does not exist yet. If the
array does not exist, a mocked array object is created for the rest of the
execution.

During the rest of the execution, the code bypasses making any real changes
and just tells you what changes it would have made.

Example _dry_ output:

    [Terminate Test (DRY Mode)] Beginning
    [Terminate Test (DRY Mode)] Array "my-array" not found -- creating a mock.
    [Terminate Test (DRY Mode)] Disabling Array "my-array"
    [Terminate Test (DRY Mode)] Would have terminated all array "<mocked array my-array>" instances.
    [Terminate Test (DRY Mode)] Pretending that array <mocked array my-array> instances are terminated.
    [Terminate Test (DRY Mode)] Finished successfully. Result: True

