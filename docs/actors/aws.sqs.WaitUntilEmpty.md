##### aws.elb.WaitUntilEmpty

Wait indefinitely until for SQS queues that match a name pattern to get to 0
messages.

This actor will loop infinitely as long as the count of messages in at least
one queue is greater than zero. SQS does not guarantee exact count, so this can
return a stale value if the number of messages in the queue changes rapidly.


**Options**

  * `name` - The name or regex pattern of the queues to operate on
  * `region` - AWS region (or zone) string, like 'us-west-2'
  * `required` - optional boolean, default False. On True will fail if no
                 queues are found.

Examples

    # For an SQS queues with name containing `release-0025a`
    { 'name': 'release-0025a',
      'region': 'us-east-1',
      'required': True }


**Dry Mode**

This actor performs the finding of the queue, but will pretend that the count
is 0 and return success. Will fail even in dry mode if `required` option is set
to True and no queues with the name pattern are found.
