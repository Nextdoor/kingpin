## Version 0.2.6
  * #264: Use self.thread() in elb.WaitUntilHealthy._is_healthy() method. ([@diranged])
  * #263: Clean up all AWS Actors: Use retrying.retry with common backoff settings... ([@diranged])
  * #261: Fix the default_timeout=0 class setting on Group/Macro actors. ([@diranged])
  * #260: The BaseActor class setting `default_timeout=0` does not seem to function. ([@diranged])
  * #258: Set the default timeout for the misc.Macro actor to 0 (unlimited). ([@diranged])
  * #257: Minor fixes ([@siminm])
  * #256: Bump find_elb retry delay to 1 second. ([@siminm])
  * #254: Add `Rate exceeded` to retriable exceptions. ([@siminm])
  * #252: Use correct BotoServerError attribute for error_code ([@siminm])
  * #251: Do not leverage PleaseRetryException to handle Throttling ([@siminm])
  * #248: Allow skipping of the automated dry run. ([@siminm])
  * #247: Show all errors in Dry run before failing. ([@siminm])
  * #246: Add option to skip dry run ([@siminm])
  * #243: Retry on HTTP 599s in support.api ([@diranged])

## Version 0.2.5
 * #239: Add the @sync_retry decorator to the make_generic_request() call. ([@diranged])
 * #238: Improve the timeout system... ([@diranged])
 * #237: Support Tornado 4.1+ by ensuring all exceptions are caught and handled. ([@diranged])
 * #234: Authentication testing/logging improvements to actors.support.api Package ([@diranged])
 * #233: Accept 'string counts' for rightscale.server_array.Launch. ([@diranged])
 * #232: rightscale.server_array.Execute does not handle 403 correctly ([@diranged])
 * #231: Add 'strict' parameter to the rightscale.server_array.Destroy/Terminate actors ([@diranged])
 * #230: Add Execution timeout setting to BaseActor ([@diranged])
 * #229: rightscale.server_Array.Execute actor should handle 422 better ([@diranged])
 * #228: Allow setting of the 'strictness' of the rightscale.server_array.Clone actor ([@diranged])
 * #227: Use a single api.RightScale object on all RightScale actors. ([@diranged])
 * #226: Support non-exact ServerArray matching in the RightScale actors ([@diranged])
 * #225: Support rightscale launch count option ([@diranged])
 * #224: Add pingdom.Pause/Unpause actors ([@siminm])
 * #221: Install kingpin via setup.py in Makefile. ([@siminm])
 * #220: Remove setup requirements from setup.py. ([@siminm])
 * #218: Allow wildcard/non-exact ServerArray matches in ServerArrayBaseActor._find_server_arrays() ([@diranged])
 * #213: Setup broken on clean install ([@diranged])
 * #203: Add support for single API call to launch many RightScale instances ([@diranged])
 * #116: Add a 'timeout' to kingpin.actors.base.BaseActor ([@diranged])

## Version 0.2.3
 * #205: aws.elb.RegisterInstance should add ELB to zone if its not already there ([@siminm])
 * #204: Add aws.elb.RegisterInstance/aws.elb.DeregisterInstance to main README.md ([@siminm])
 * #202: Catch InvalidCredentials in AWS Base class. ([@siminm])
 * #198: AWS Actors should convert Zones into Regions ([@siminm])
 * #197: AWS Actors should swallow Boto Invalid Credential Errors ([@siminm])

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
