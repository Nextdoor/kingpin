##### aws.elb.WaitUntilEmpty

Wait indefinitely until a specified SQS queue has 0 messages.

This actor will loop infinitely as long as the count of messages in the queue
is greater than zero. SQS does not guarantee exact count, so this can return a
stale value if the number of messages in the queue changes rapidly.


**Options**

  * `name` - The name of the queue to operate on

Examples

    # For an SQS queue named `production-tasks`
    { 'name': 'production-tasks' }


**Dry Mode**

This actor performs the finding of the queue, but will pretend that the count
is 0 and return success.
