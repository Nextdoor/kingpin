## Version 0.4.1
 * #435: Pass Kingpin ECS actor ENV vars to task definition ([@diranged])
 * #434: SYSTEMS-957: Support NoEcho Parameters in CloudFormation stacks. ([@diranged])
 * #433: ECS: Fix a race condition in stop service ([@swaggy])
 * #432: New Actor: spottinst.ElastiGroup ([@diranged])
 * #431: Compare S3 bucket tags with some intelligence. ([@diranged])
 * #429: Quiet down a logging statement ([@diranged])
 * #428: Strip out unicode characters in diff_dicts. ([@swaggy])
 * #427: Bugfix on S3 Bucket Tag comparison. ([@mikhail])
 * #426: Add CAPABILITY_NAMED_IAM to the enumeration of capabilities parameters. ([@sabw8217])
 * #424: Missed adding the self._bucket_exists check to \_get_policy(). ([@diranged])
 * #423: Bugfixes around creation of new S3 buckets. ([@diranged])
 * #422: Convert the aws.s3.Bucket actor to use Boto3 ([@diranged])
 * #412: Bugfix -- handling a single alertspec on a template was broken ([@diranged])
 * #411: Bugfix: Make sure we set self.changed=True after updating the runnabl… ([@diranged])
 * #410: Fix the RightScale ServerTemplate/Alert integration tests.. ([@diranged])
 * #409: Delete .base.py.swo ([@diranged])
 * #407: Bugfix - threshold must be a string. ([@diranged])
 * #402: Create a new AlertSpecBase ensurable base actor for managing RightScale AlertSpecs ([@diranged])
 * #393: Bugfix -- we couldn't create S3 buckets in anything other than the default region. ([@diranged])
 * #391: Bugfix -- if no cloudformation parameters, thats fine. ([@diranged])
 * #389: Remove bogus testing log line that was left there accidentally. ([@diranged])
 * #385: Add ecs service actor. ([@swaggy])
 * #383: New Actor: rightscale.ServerTemplate ([@diranged])

## Version 0.4.0
 * #372: Bugfix -- Ensure the appropriate kwargs are used for the dry decorator. ([@diranged])
 * #371: Bugfix -- pass the right parameters to configure_lifecycle() ([@diranged])
 * #370: Add Lifecycle Management support to the aws.s3.Bucket actor. ([@diranged])
 * #369: Add bucket versioning management to the aws.s3.Bucket actor. ([@diranged])
 * #368: Bugfix -- allow Null/None in aws.s3.LoggingConfig. ([@diranged])
 * #367: Add Bucket Logging Configuration support to the aws.s3.Bucket actor. ([@diranged])
 * #366: Fix an integration test that used to fail intentionally. ([@diranged])
 * #365: Make the 'init_tokens' available to all actors. ([@diranged])
 * #364: Allow array syntax for group.Sync ([@mikhail])
 * #363: Support deep nested token passing to macros and group actors ([@diranged])
 * #360: Manage S3 Bucket policies ([@diranged])
 * #359: Manage S3 buckets ([@diranged])
 * #352: Don't print out the IAM Policy Content as log.info ([@diranged])
 * #350: Documentation fix for the misc.Macro actor ([@diranged])
 * #349: Bugfix -- Ensure parse_inline_policies handles None properly ([@diranged])
 * #348: Search for the "default" RightScale MCI HREF even in the DRY run. ([@diranged])
 * #347: Make the `desc` parameter optional ([@diranged])
 * #346: Create kingpin.actors.utils.dry() for wrapping methods and making them dry! ([@diranged])
 * #345: Provide a @dry method wrapper ([@diranged])
 * #344: Remove explicit 'purge' options from AWS IAM Actors ([@diranged])
 * #342: Proposal -- "ensure-able" actors should treat `undef` as a sign to not manage something ([@diranged])
 * #338: Bugfix on IAM Group deletion ([@diranged])
 * #336: New Actor - aws.iam.Role ([@diranged])
 * #335: Issue #56: Make each Integration test suite optional. ([@diranged])
 * #332: New Actor: aws.iam.User ([@diranged])
 * #329: Add data-json to GenericHTTP actor ([@mikhail])
 * #328: add functools32 as a test dep ([@niallo])
 * #327: Recreate sample certs with 10 year expiry ([@mikhail])
 * #326: Fix rightscale concurrency execution error with single array ([@mikhail])
 * #325: Fix documentation code-block bugs with latest Sphinx. ([@diranged])
 * #324: Increase timeout on Deleting CloudFormation stack integration test. ([@diranged])
 * #323: Rewrite async test to make pypy happy ([@mikhail])
 * #321: Fix hipchat integration tests ([@mikhail])
 * #320: Allow a list of channels for slack.Message ([@mikhail])
 * #319: Add --explain to --actor to print the docstring ([@mikhail])
 * #318: Use kingpin.actors.utils.get_actor_class() when getting an actor from the CLI ([@diranged])
 * #317: Search for Actor names with the Kingpin prefixes first. ([@diranged])
 * #316: Allow stringified-booleans to be passed in to the ELB actor. ([@diranged])
 * #315: aws.elb.DeregisterInstance 'wait_on_draining' option should take a string and convert it bug ([@diranged])
 * #314: When running an actor on the command line, a failed actor resolution doesn't exit > 0. ([@diranged])
 * #313: When running zip file, actor discvoery should include 'actors.*' ([@diranged])
 * #312: aws.elb.RegisterInstance 'enable_zones' option should take a string and convert it ([@diranged])
 * #311: Fix clobber ([@mikhail])
 * #310: Allow actor input from command line rather than json file. ([@mikhail])
 * #309: Auto-deploy releases to Github ([@diranged])
 * #308: Issue 306: Wait for all ELB connections to drain. ([@diranged])
 * #306: aws.elb.DeregisterInstance should wait for connections to drain ([@diranged])
 * #305: aws.elb.DeregisterInstance should take a wildcard for ELB name ([@diranged])
 * #302: Don't sort rightscale params. ([@mikhail])
 * #301: Allow contexts in conditions ([@mikhail])
 * #299: Allow server_array.Launch to not enable and not launch. ([@mikhail])
 * #296: Add context-file ([@mikhail])

## Version 0.3.0
  * #292 Make rightscale.api.find_by_name_and_keys() return only a list or a s…  bug ([@diranged])
  * #291 Fix alert tests ([@diranged])
  * #290 Depend on the newest RightScale library patch ([@diranged])
  * #289 Initial support for creating and destroying RightScale MCIs ([@diranged])
  * #288 Fix doc typo ([@mikhail])
  * #287 Use a 120s timeout when interacting with PackageCloud ([@diranged])
  * #282 Create rightscale deployment Destroy actor ([@mikhail])
  * #280 Fix pypi link in README.rst ([@diranged])
  * #278 Add Concurrency Limit to Execute Actor ([@mikhail])
  * #277 Packagecloud Actor ([@cmclaughlin])
  * #276 New Actor: rightscale.server_array.UpdateNextInstance ([@diranged])
  * #273 Allow Async actor to limit concurrency ([@mikhail])
  * #272 Add a few input safety checks around the rightscale.alerts.Create actor ([@diranged])
  * #271 Fix documentation typo in server_array.Execute ([@mikhail])
  * #270 RightScale Alert Spec Actors ([@diranged])
  * #269 Disable the cross-actor RightScale API Object sharing ([@diranged])
  * #268 Migrate to Sphinx/RTD hosted docs ([@diranged])
  * #266 Handle RightScales concept of 'array values' ([@diranged])
  * #241 Simple mechanism for creating fully ecapsulated Kingpin zip file ([@diranged])
  * #223 New Actor: pingdom.check.Pause ([@diranged])
  * #219 Add "rolling" execution to Async actor ([@mikhail])
  * #72 Make a clone_and_launch actor enhancement ([@diranged])

## Version 0.2.6
  * #264: Use self.thread() in elb.WaitUntilHealthy._is_healthy() method. ([@diranged])
  * #263: Clean up all AWS Actors: Use retrying.retry with common backoff settings... ([@diranged])
  * #261: Fix the default_timeout=0 class setting on Group/Macro actors. ([@diranged])
  * #260: The BaseActor class setting `default_timeout=0` does not seem to function. ([@diranged])
  * #258: Set the default timeout for the misc.Macro actor to 0 (unlimited). ([@diranged])
  * #257: Minor fixes ([@mikhail])
  * #256: Bump find_elb retry delay to 1 second. ([@mikhail])
  * #254: Add `Rate exceeded` to retriable exceptions. ([@mikhail])
  * #252: Use correct BotoServerError attribute for error_code ([@mikhail])
  * #251: Do not leverage PleaseRetryException to handle Throttling ([@mikhail])
  * #248: Allow skipping of the automated dry run. ([@mikhail])
  * #247: Show all errors in Dry run before failing. ([@mikhail])
  * #246: Add option to skip dry run ([@mikhail])
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
 * #224: Add pingdom.Pause/Unpause actors ([@mikhail])
 * #221: Install kingpin via setup.py in Makefile. ([@mikhail])
 * #220: Remove setup requirements from setup.py. ([@mikhail])
 * #218: Allow wildcard/non-exact ServerArray matches in ServerArrayBaseActor._find_server_arrays() ([@diranged])
 * #213: Setup broken on clean install ([@diranged])
 * #203: Add support for single API call to launch many RightScale instances ([@diranged])
 * #116: Add a 'timeout' to kingpin.actors.base.BaseActor ([@diranged])

## Version 0.2.3
 * #205: aws.elb.RegisterInstance should add ELB to zone if its not already there ([@mikhail])
 * #204: Add aws.elb.RegisterInstance/aws.elb.DeregisterInstance to main README.md ([@mikhail])
 * #202: Catch InvalidCredentials in AWS Base class. ([@mikhail])
 * #198: AWS Actors should convert Zones into Regions ([@mikhail])
 * #197: AWS Actors should swallow Boto Invalid Credential Errors ([@mikhail])

## Version 0.2.2
 * #195: Bugfix: Fix parsing of unicode os.environ[] tokens at script parse time. ([@diranged])
 * #193: Add ELB Add/Remove instance actors. ([@mikhail])
 * #192: Initial kingpin.actors.support.api module for fast-creation of REST API ... ([@diranged])
 * #191: Create simple_api.BaseJSON Class ([@diranged])
 * #190: Use the patched python-rightscale library with auto-token-refreshment. ([@diranged])
 * #189: RightScale actors should observe OAUTH token timeout.. ([@diranged])
 * #184: New Actor(s): aws.elb.Connect, aws.elb.Disconnect ([@mikhail])
 * #169: Add actors to update ELB certs. ([@mikhail])

## Version 0.2.1
 * #186: Don't fetch audit logs if the instance is missing ([@mikhail])
 * #183: actors.rightscale.server_array integration test fixes ([@diranged])
 * #182: Handle 401 and 403 response codes the same ([@diranged])
 * #181: rightscale.server_array.Terminate throws: 'NoneType' object has no attribute 'soul' ([@mikhail]

## Version 0.2.0
 * #174: Add actor 'initialization context' support. ([@diranged])
 * #172: Add logger test in wait_for_task ([@mikhail])
 * #171: Add aws.cloudformation.Create/Delete actors ([@diranged])
 * #168: Use REQUIRED constant instead of None for options ([@mikhail])
 * #166: Increase rollbar integration test timeout. ([@mikhail])
 * #165: Show instance audit logs when Execute task fails. ([@mikhail])
 * #164: Launch up to min count, instead of new min count. ([@mikhail])
 * #162: Increase the timeout time for the Hipchat/Rollbar integration tests. ([@diranged])
 * #161: Track instances during script execution ([@mikhail])
 * #159: Increase retries for launch_server_array ([@mikhail])
 * #158: Add @retry decorator to current_instances call ([@mikhail])
 * #153: Don't wait for empty tasks ([@mikhail])
 * #152: Bump timeout for GenericHTTP Integration tests ([@mikhail])
 * #151: Add misc.Macro actor ([@mikhail])
 * #150: Print ELB health status every 30 seconds instead of 3 ([@mikhail])
 * #133: Track execution time and print it out in debug statements. ([@diranged])
 * #132: Issue #88: Rollbar Deployment Actor ([@diranged])
 * #131: Add hipchat.Topic actor ([@diranged])
 * #130: Cleanup Hipchat error handling and return values. ([@diranged])
 * #129: Refactor exception tracking in GroupActor ([@mikhail])
 * #128: Improve group actor tests. ([@mikhail])
 * #127: Nested exceptions ([@mikhail])
 * #126: Kill the bools ([@diranged])
 * #125: Add BaseActor execution conditions ([@mikhail])
 * #123: Check scripts inputs for Execute actor. ([@mikhail])
 * #113: Add GenericHTTP actor ([@mikhail])

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
[@mikhail]: https://github.com/mikhail
[@cmclaughlin]: https://github.com/cmclaughlin
[@niallo]: https://github.com/niallo
[@sabw8217]: https://github.com/sabw8217
[@swaggy]: https://github.com/swaggy
