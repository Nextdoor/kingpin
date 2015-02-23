##### aws.elb.WaitUntilHealthy

Wait indefinitely until a specified ELB is considered "healthy".

This actor will loop infinitely until a healthy threshold of the ELB is met.
The threshold can be reached when the `count` as specified in the options is
less than or equal to the number of InService instances in the ELB.

Another situation is for `count` to be a string specifying a percentage (see
examples). In this case the percent of InService instances has to be greater
than the `count` percentage.

**Options**

  * `name` - The name of the ELB to operate on
  * `count` - Number, or percentage of InService instance to consider
              this ELB healthy
  * `region` - AWS region (or zone) name, such as us-east-1 or us-west-2

Examples

    # For an ELB named `production-frontend`
    { 'name': 'production-frontend'
      'count': 16,
      'region': 'us-west-2' }

    # or...
    { 'name': 'production-frontend'
      'count': '85%',
      'region': 'us-west-2' }

**Dry Mode**

This actor performs the finding of the ELB as well as calculating its health
at all times. The only difference in dry mode is that it will not re-count
the instances if the ELB is not healthy. A log message will be printed
indicating that the run is dry, and the actor will exit with success.
