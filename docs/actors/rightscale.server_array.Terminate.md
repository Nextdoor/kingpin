##### rightscale.server_array.Destroy

Terminates all instances for a ServerArray in RightScale marking the array
disabled.

**Options**

  * `array` - The name of the ServerArray to destroy

Examples

    # Terminate all running instances array
    { 'array': 'my-array' }

**Dry Mode**

Dry mode still validates that the server array you want to terminate is
actually gone. If you want to bypass this check, then set the `warn_on_failure`
flag for the actor.
