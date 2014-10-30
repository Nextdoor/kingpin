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
