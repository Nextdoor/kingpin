## Version 0.2.0
 * #174: Add actor 'initialization context' support. ([@diranged])
 * #172: Add logger test in wait_for_task ([@siminm])
 * #166: Increase rollbar integration test timeout. ([@siminm])
 * #164: Launch up to min count, instead of new min count. ([@siminm])
 * #162: Increase the timeout time for the Hipchat/Rollbar integration tests. ([@diranged])
 * #151: Add misc.Macro actor ([@siminm])
 * #133: Track execution time and print it out in debug statements. ([@diranged])
 * #130: Cleanup Hipchat error handling and return values. ([@diranged])
 * #128: Improve group actor tests. ([@siminm])
 * #126: Kill the bools ([@diranged])

## Version 0.1.2
  * #120: Don't warn unless a warning is actually necessary

## Version 0.1.1
 * #118: Bugfix: Destroying a non existent server array should return False
 * #117: Catch BotoExceptions and return False from Actors
 * #115: Remove deprecated `terminate` option from integration tests
 * #97: kingpin.actors.BaseActor now catches *all* Exceptions
 * #94: kingpin.actors.rightscale.Destroy/Terminate should be optionally strict about pre-existing arrays
 * #86: Colorize the Kingpin log output
 * #85: Added `warn_on_failure` option to BaseActor
 * #84: aws.sqs.Delete should fail in dry-run if no queues are found
 * #83: aws.sqs.WaitUntilEmpty should error out on missing queues
 * #82: Kingpin should exit >1 if there are any Actor failures
 * #81: rightscale.server_array.Execute actor should FAIL not WARN on script failure
 * #79: kingpin.actors.aws.sqs.SQSBaseActor._fetch_queues() method broken
 * #78: Better json handling
 * #41, #71: kingpin.actors.librato.Annotation: Librato Annotation-Pushing Actor

## Version 0.1.0
  * Initial launch version.

[@diranged]: https://github.com/diranged
[@siminm]: https://github.com/siminm
[@cmclaughlin]: https://github.com/cmclaughlin
