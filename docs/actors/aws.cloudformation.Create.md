##### aws.cloudformation.Create

Creates a CloudFormation stack and waits until its finished its entire creation
before moving on.

**Options**

  * `capabilities` - A list of CF capabilities to add to the stack.
  * `disable_rollback` - Set to True to disable rollback of the stack if
     creation failed.
  * `name` - The name of the queue to create
  * `parameters` - A dictionary of key/value pairs used to fill in the
     parameters for the CloudFormation template.
  * `region` - AWS region string, like 'us-west-2'
  * `template` - String of path to CloudFormation template. Can either be in
     the form of a local file path (ie, `./my_template.json`) or a URI (ie
     `https://my_site.com/cf.json`).
  * `timeout_in_minutes` - The amount of time that can pass before the stack
     status becomes CREATE_FAILED.

Examples

    { "desc": "Create production backend stack",
      "actor": "aws.cloudformation.Create",
      "options" {
        "compatibilities": [ "CAPABILITY_IAM" ],
        "disable_rollback": true,
        "name": "%CF_NAME%",
        "parameters": {
          "test_param": "%TEST_PARAM_NAME%",
        },
        "region": "us-west-1",
        "template": "file:///examples/cloudformation_test.json",
        "timeout_in_minutes": 45,
      }
    }

**Dry Mode**

Validates the template, verifies that an existing stack with that name does not
exist. Does not create the stack.
