## Version 0.3.0

Big release with a ton of bug fixes, several new actors, and actor enhancements.

### Bug-fixes/Improvements

  * Patches to the python-rightscale library now properly support actors that
    take longer than 2 hours to execute.
  * Properly support RightScale "Array" values when updating RightScale objects.
  * Properly handle PackageCloud.io interactions that take longer than 30s

### New Actors

  * `rightscale.alerts.Create` and `rightscale.alerts.Destroy`
  * `rightscale.deployment.Create` and `rightscale.deployment.Destroy`
  * `rightscale.server_array.UpdateNextInstance`
  * `packagecloud.Delete`, `packagecloud.DeleteByDate` and
    `packagecloud.WaitForPackage`
  * `pingdom.check.Pause`

### Big new feature: `concurrency: X`

The `group.Async` actor can now limit the concurrency so that no more than a
certain number of actors execute at once. This is useful if you have a mass
amount of actors defined inside your `Async` group, but want to limit the
number of them that are running at any one time.

### Concurrency also on the `rightscale.server_array.Execute` actor!

You can also pass in a `concurrency` setting to the RightScale `Execute` actor
and limit the number of concurrent executions of your RightScript!

### Big new improvement: ReadTheDocs!

We have completely re-vamped the documentation so that its built and published
to the ReadTheDocs service at http://kingpin.readthedocs.org.

## Version 0.2.6

Mostly a bug-fix release. Sigificant work went into improving the AWS actor reliability though.

### Bug-fixes/Improvements

  * Significant improvements to the retry mechanisms used by the AWS Actors.
    All of the AWS actors now subclass from a single common AWSBaseActor class,
    and use a common retry mechanism with built in jitter and exponential
    backoff.
  * Fix the [group.Sync](docs/actors/group.Sync.md),
    [group.Async](docs/actors/group.Async.md) and
    [misc.Macro](docs/actors/misc.Macro.md) actors timeout setting. It is disabled
    by default now (as it was intended to be).
  * Allow skipping of the pre-run DRY execution.
  * Show all errors in the DRY run rather than failing out on the first one.

## Version 0.2.5

Skipped a version because there were numerous new actors in this release.

### New Actors

  * [pingdom.Pause](docs/actors/pingdom.Pause.md): Pauses a Pingdom Service Check
  * [pingdom.Unpause](docs/actors/pingdom.Unpause.md): Resumes/Unpauses a Pingdom Service Check

### Big new feature: `timeout: X`

A new schema-wide option has been added (`timeout: X`). All actors default to a
1 hour timeout. After 1 hour of execution time, an `ActorTimedOut` exception is
raised. This exception honors the `Recoverable` vs `Unrecoverable` actor
failures, which means that you can set `warn_on_failure` as well as a `timeout`
setting on your actor.

This new option allows a long-running task to raise an exception, and then for
the Kingpin execution to either fail immediately or continue on to other tasks
(based on the `warn_on_failure` setting).

### Tornado Upgraded to 4.1+

We have upgraded the base-version of Tornado that we use to 4.1+ in order to
support the `timeout` argument above. This upgrade brings in a ton of
performance improvements from the Tornado team, as well as forced us to do some
cleanup on a few modules to ensure that we were really capturing every
exception and logging it appropriately.

### Bug-fixes/Improvements

  * [rightscale.server_array.Clone](docs/actors/rightscale.server_array.Clone.md) added options: `strict_source`, `strict_dest`:

  These options allow the `rightscale.server_array.Clone` actor to operate on
  not-yet-created, or not-yet-deleted arrays without throwing errors during the
  Dry run. This is especially useful for doing things like a *Relaunch* of a
  ServerArray. See issue #222.

  * [rightscale.server_array.Terminate](docs/actors/rightscale.server_array.Terminate.md) added options: `strict`:

  Same as above

  * [rightscale.server_array.Destroy](docs/actors/rightscale.server_array.Destroy.md) added options: `strict`:

  Same as above

  * Use a single api.RightScale object on all RightScale actors:

  This reduces the number of API calls we make to the RightScale API for OAuth
  tokens, ensures that we are using the same token for all calls, and generally
  just reduces memory usage and time of execution.

  * Allow wild-card matches of ServerArray names in the Rightscale actors:

  Now `exact=False` can be set on the majority of the RightScale actors which
  allows you to act on many arrays at once with simple name matching.

  * Use `count=X` in RightScale ServerArray `Launch()` calls.

  This dramatically reduces the time it takes to launch many instances at once,
  putting the burdon on RightScale instead. This is a new feature in the
  RightScale 1.5 API.

  * Fix Pip install by removing `setup_requires()` sections from `setup.py`.
  * Mask credentials used in the actors.support.api package when `loglevel=debug`.

## Version 0.2.3

### Improvements

 * [aws.elb.RegisterInstance](docs/actors/aws.elb.RegisterInstance.md) will not only register the instance but also
   check that the ELB is set up for all zones that it can handle.
 * For any `aws` actor that receives a region you can now pass a particular
   zone if that happens to be more convenient for you. The aws base class will
   log a warning and convert a zone into a region on the fly.

## Version 0.2.2

### New Actors

 * [aws.iam.UploadCert](docs/actors/aws.iam.UploadCert.md)
 * [aws.iam.DeleteCert](docs/actors/aws.iam.DeleteCert.md)

 * [aws.elb.RegisterInstance](docs/actors/aws.elb.RegisterInstance.md)
 * [aws.elb.DeregisterInstance](docs/actors/aws.elb.DeregisterInstance.md)
 * [aws.elb.SetCert](docs/actors/aws.elb.SetCert.md)

### Bug-fixes

 * Rightscale OAuth token was timing out and not auto-refreshing.
 * Can now handle environment variables with unicode values


## Version 0.2.1

Bug-fix release:

 * The Rollbar API changed and started returning 401's rather than 403's for
   invalid credential notifications.
 * Bugfix in our `rightscale.api.wait_for_task()` method that was causing it to
   try to look up instance-logs when sometimes there was no instance to track
   down.

## Version 0.2.0

Version v0.2.0 is a huge improvement over v0.1.2. A ton of new tests, code
cleanup, and new actors have been added to the system. For a complete diff,
please see [v0.1.2...v0.2.0].

### New Concepts

*[Conditional Execution](README.rst#conditional-execution)*:
Make any actor or group of actors execution conditional based on a token that
you've supplied. Allows you to easily turn on and off sections of your
deployment like switches.

*[Contextual Tokens](README.rst#contextual-tokens)*:
Now we have a model for a new type of token-replacement in the JSON files that
can be used to change tokens at or during run time. The initial usage of these
tokens is in the `group.Sync` and `group.Async` actors where we have added a
model for iterating over a list of data and dynamically generating actors to
act on that data. This model can also be used as a simple variable structure,
allowing you to define variables high up in your JSON script, and leverage them
further down the code.

### New Actors

*[aws.cloudformation.Create](docs/actors/aws.cloudformation.Create.md)*:
Create Amazon CloudFormation stacks on the fly in Kingpin. This allows you to
define highly complex structures in Amazon, but implement them on-demand
through Kingpin as part of your script.

*[aws.cloudformation.Delete](docs/actors/aws.cloudformation.Delete.md)*:
Tear down existing CloudFormation stacks.

*[hipchat.Topic](docs/actors/hipchat.Topic.md)*:
Set a HipChat room topic as part of your deployment!

*[misc.GenericHTTP](docs/actors/misc.GenericHTTP.md)*:
Make generic HTTP web calls.

*[misc.Macro](docs/actors/misc.Macro.md)*:
This actor allows you to build many smaller JSON scripts and leverage them as
if they are individual actors inside other scripts. This structure makes it
much easier to build re-usable scripts!

*[rollbar.Deploy](docs/actors/rollbar.Deploy.md)*:
Notify Rollbar of your deployments.

[v0.1.2...v0.2.0]: https://github.com/Nextdoor/kingpin/compare/v0.1.2...v0.2.0

### Improvements

  * Generous use of the @retry decorators on many different API call methods.
  * Significantly improved `rightscale.server_array.Execute` actor logging for
    failures.
  * Much quieter logger on highly repetetive checks. Exponentially backs off
    logging statements to avoid flooding the log output with useless data.
  * Cleaned up the nested exception handling so that exceptions are caught only
    in the right places and log entries are appropriately printed.
  * Completely replaced the Boolean-based return values in actor execution with
    proper `Exception` raising instead.
  * Checks the RightScale Execute actor inputs before execution.
