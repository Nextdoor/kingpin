##### aws.sqs.Create

Creates a new SQS queue with the specified name

**Options**

  * `name` - The name of the queue to create
  * `region` - AWS region string, like 'us-west-2'

Examples

    # To create a 'async-tasks' queue
    { 'name': 'async-tasks',
      'region': 'us-east-1'}

**Dry Mode**

Will not create any queue, or even contact SQS. Will create a mock.Mock object
and exit with success.
