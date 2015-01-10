##### aws.cloudformation.Create

Creates a CloudFormation stack and waits until its finished its entire creation
before moving on.

**Options**

  * `name` - The name of the queue to create
  * `template` - String of path to CloudFormation template. Can either be in
     the form of a local file path (ie, `./my_template.json`) or a URI (ie
     `https://my_site.com/cf.json`).
  * `region` - AWS region string, like 'us-west-2'

Examples

    { "desc": "Create production backend stack",
      "actor": "aws.cloudformation.Create",
      "options" {
        "region": "us-west-1",
        "template": "file:///examples/cloudformation_test.json",
        "name": "%CF_NAME%",
        "parameters": {
          "test_param": "%TEST_PARAM_NAME%",
         }
      }
    }

**Dry Mode**

