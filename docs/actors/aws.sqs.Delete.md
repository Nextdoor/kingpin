##### aws.sqs.Delete

Deletes the SQS queues **even if it`s not empty**

**Options**

  * `name` - The name of the queue to destroy

Examples

    # To delete a 'async-tasks' queue
    { 'name': 'async-tasks' }

    # To delete all queues with versioned names
    # such as 'async-tasks-release-1234'
    { 'name': '1234' }

**Dry Mode**

Will find the specified queue, but will have a noop regarding its deletion.
