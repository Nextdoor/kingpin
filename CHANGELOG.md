## Version 0.2.2
 * #195: Bugfix: Fix parsing of unicode os.environ[] tokens at script parse time. ([@diranged])
 * #193: Add ELB Add/Remove instance actors. ([@siminm])
 * #192: Initial kingpin.actors.support.api module for fast-creation of REST API ... ([@diranged])
 * #191: Create simple_api.BaseJSON Class ([@diranged])
 * #190: Use the patched python-rightscale library with auto-token-refreshment. ([@diranged])
 * #189: RightScale actors should observe OAUTH token timeout.. ([@diranged])
 * #184: New Actor(s): aws.elb.Connect, aws.elb.Disconnect ([@siminm])
 * #169: Add actors to update ELB certs. ([@siminm])

## Version 0.2.1
 * #186: Don't fetch audit logs if the instance is missing ([@siminm])
 * #183: actors.rightscale.server_array integration test fixes ([@diranged])
 * #182: Handle 401 and 403 response codes the same ([@diranged])
 * #181: rightscale.server_array.Terminate throws: 'NoneType' object has no attribute 'soul' ([@siminm]

## Version 0.2.0
 * #174: Add actor 'initialization context' support. ([@diranged])
 * #172: Add logger test in wait_for_task ([@siminm])
 * #171: Add aws.cloudformation.Create/Delete actors ([@diranged])
 * #168: Use REQUIRED constant instead of None for options ([@siminm])
 * #166: Increase rollbar integration test timeout. ([@siminm])
 * #165: Show instance audit logs when Execute task fails. ([@siminm])
 * #164: Launch up to min count, instead of new min count. ([@siminm])
 * #162: Increase the timeout time for the Hipchat/Rollbar integration tests. ([@diranged])
 * #161: Track instances during script execution ([@siminm])
 * #159: Increase retries for launch_server_array ([@siminm])
 * #158: Add @retry decorator to current_instances call ([@siminm])
 * #153: Don't wait for empty tasks ([@siminm])
 * #152: Bump timeout for GenericHTTP Integration tests ([@siminm])
 * #151: Add misc.Macro actor ([@siminm])
 * #150: Print ELB health status every 30 seconds instead of 3 ([@siminm])
 * #133: Track execution time and print it out in debug statements. ([@diranged])
 * #132: Issue #88: Rollbar Deployment Actor ([@diranged])
 * #131: Add hipchat.Topic actor ([@diranged])
 * #130: Cleanup Hipchat error handling and return values. ([@diranged])
 * #129: Refactor exception tracking in GroupActor ([@siminm])
 * #128: Improve group actor tests. ([@siminm])
 * #127: Nested exceptions ([@siminm])
 * #126: Kill the bools ([@diranged])
 * #125: Add BaseActor execution conditions ([@siminm])
 * #123: Check scripts inputs for Execute actor. ([@siminm])
 * #113: Add GenericHTTP actor ([@siminm])

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
