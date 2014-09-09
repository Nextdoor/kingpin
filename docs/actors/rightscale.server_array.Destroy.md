##### rightscale.server_array.Destroy

Destroys a ServerArray in RightScale by first invoking the Terminate actor, and
then deleting the array as soon as all of the running instances have been
terminated.

**Options**

  * `array`     - The name of the ServerArray to destroy

Examples

    # Destroy an array
    { 'array': 'my-array' }

**Dry Mode**

In Dry mode this actor _does_ search for the `array`, but allows it to be
missing because its highly likely that the array does not exist yet. If the
array does not exist, a mocked array object is created for the rest of the
execution.

During the rest of the execution, the code bypasses making any real changes
and just tells you what changes it would have made.

Example _dry_ output:

    [Destroy Test (DRY Mode)] Beginning
    [Destroy Test (DRY Mode)] Terminating array before destroying it.
    [Destroy Test (terminate) (DRY Mode)] Array "my-array" not found -- creating a mock.
    [Destroy Test (terminate) (DRY Mode)] Disabling Array "my-array"
    [Destroy Test (terminate) (DRY Mode)] Would have terminated all array "<mocked array my-array>" instances.
    [Destroy Test (terminate) (DRY Mode)] Pretending that array <mocked array my-array> instances are terminated.
    [Destroy Test (DRY Mode)] Pretending to destroy array "<mocked array my-array>"
    [Destroy Test (DRY Mode)] Finished successfully. Result: True
