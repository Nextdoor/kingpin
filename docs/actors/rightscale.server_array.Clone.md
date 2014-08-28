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
