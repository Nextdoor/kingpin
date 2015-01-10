##### aws.cloudformation.Delete

Deletes a CloudFormation stack with the specified name.

**Options**

  * `name` - The name of the queue to create
  * `region` - AWS region string, like 'us-west-2'

Examples

    { "desc": "Create production backend stack",
      "actor": "aws.cloudformation.Create",
      "options" {
        "region": "us-west-1",
        "name": "%CF_NAME%",
      }
    }

**Dry Mode**

