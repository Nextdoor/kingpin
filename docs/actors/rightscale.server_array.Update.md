##### rightscale.server_array.Update

Updates an existing ServerArray in RightScale with the supplied parameters. Can
update any parameter that is described in the RightScale API docs here:

  [Resource/ServerArrays #update Method](http://reference.rightscale.com/api1.5/resources/ResourceServerArrays.html#update)

Parameters are passed into the actor in the form of a dictionary, and are
then converted into the RightScale format. See below for examples.

**Options**

  * `array`  - The name of the ServerArray to update
  * `exact`  - Boolean whether or not to search for the exact array name.
               (default: `true`)
  * `params` - Dictionary of parameters to update
  * `inputs` - Dictionary of next-instance server arryay inputs to update

Examples

    # Update the server array name, and set its min_count to 4
    { "desc": "Update my array",
      "actor": "rightscale.server_array.Update",
      "options": {
        "array": "my-new-array",
        "params": {
          "elasticity_params": {
            "bounds": {
              "min_count": 4
            }
          },
          "name": "my-really-new-name"
        }
      }
    }

    # Update the next-instance server array inputs
    { "desc": "Update my array inputs",
      "actor": "rightscale.server_array.Update",
      "options": {
        "array": "my-new-array",
        "inputs": {
          "ELB_NAME": "text:foobar"
        }
      }
    }

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
