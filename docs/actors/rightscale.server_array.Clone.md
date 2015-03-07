##### rightscale.server_array.Clone

Clones a ServerArray in RightScale and renames it to the newly supplied name.
By default, this actor is extremely strict about validating that the `source`
array already exists, and that the `dest` array does not yet exist. This
behavior can be overridden though if your Kingpin script creates the
`source`, or destroys an existing `dest` ServerArray sometime before this actor
executes.

**Options**

  * `source` - The name of the ServerArray to clone
  * `source_strict` - Whether or not to fail if the source ServerArray does
                      not exist. (default: True)
  * `dest`   - The new name for your cloned ServerArray
  * `strict_dest` - Whether or not to fail if the destination ServerArray
                    already exists. (default: True)

Examples

    # Clone my-template-array to my-new-array
    { "desc": "Clone my array",
      "actor": "rightscale.server_array.Clone",
      "options": {
        "source": "my-template-array",
        "dest": "my-new-array"
      }
    }

    # Clone an array that was created sometime earlier in the Kingpin JSON, and
    # thus does not exist yet during the dry run.
    { "desc": "Clone that array we created earlier",
      "actor": "rightscale.server_array.Clone",
      "options": {
        "source": "my-template-array",
        "strict_source": false,
        "dest": "my-new-array"
      }
    }

    # Clone an array into a destination name that was destroyed sometime
    # earlier in the Kingpin JSON.
    { "desc": "Clone that array we created earlier",
      "actor": "rightscale.server_array.Clone",
      "options": {
        "source": "my-template-array",
        "dest": "my-new-array",
        "strict_dest": false,
      }

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
