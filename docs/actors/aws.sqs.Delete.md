##### aws.sqs.Delete

Deletes the SQS queues **even if it`s not empty**

**Options**

  * `name` - The name of the queue to destroy
  * `region` - AWS region string, like 'us-west-2'
  * `idempotent` - optional boolean, default False. Will not raise errors if no
                   matching queues are found.

Examples

    # To delete a 'async-tasks' queue
    { 'name': 'async-tasks,
      'region': 'us-east-1' }

    # To delete all queues with versioned names
    # such as 'async-tasks-release-1234'
    { 'name': '1234,
      'region': 'us-east-1' }

**Dry Mode**

Will find the specified queue, but will have a noop regarding its deletion.
Dry mode will fail if no queues are found, and idempotent flag is set to False.
