## Version 0.2.0

Version v0.2.0 is a huge improvement over v0.1.2. A ton of new tests, code
cleanup, and new actors have been added to the system. For a complete diff,
please see [v0.1.2...v0.2.0].

### New Concepts

*[Conditional Execution](README.md#conditional-execution)*:
Make any actor or group of actors execution conditional based on a token that
you've supplied. Allows you to easily turn on and off sections of your
deployment like switches.

*[Contextual Tokens](README.md#contextual-tokens)*:
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
