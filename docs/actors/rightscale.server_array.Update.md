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