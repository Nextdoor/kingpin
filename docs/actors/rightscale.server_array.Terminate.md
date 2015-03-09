##### rightscale.server_array.Terminate

Terminates all instances for a ServerArray in RightScale marking the array
disabled.

**Options**

  * `array` - The name of the ServerArray to destroy
  * `exact` - Boolean whether or not to search for the exact array name.
              (default: `true`)

Examples

    # Terminate a single array
    { "desc": "Terminate my array",
      "actor": "rightscale.server_array.Terminate",
      "options": {
        "array": "my-array"
      }
    }

    # Terminate many arrays
    { "desc": "Terminate many arrays",
      "actor": "rightscale.server_array.Terminate",
      "options": {
        "array": "array-prefix",
        "exact": false,
      }
    }

**Dry Mode**

Dry mode still validates that the server array you want to terminate is
actually gone. If you want to bypass this check, then set the `warn_on_failure`
flag for the actor.
