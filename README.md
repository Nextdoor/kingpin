# Kingpin: the chief element of any system, plan, or the like.

[![Build Status](https://travis-ci.org/Nextdoor/kingpin.svg?branch=master)](https://travis-ci.org/Nextdoor/kingpin)

Automated Deployment Engine

## Basic Use

TODO

### Credentials

TODO

### DSL

#### The Script
Definition: _The blueprint or roadmap that outlines a movie story through
visual descriptions, actions of characters and their dialogue. The term
"script" also applies to stageplays as well._

Every Kingpin _script_ is a chunk of JSON-encoded data that contains _actors_.
Each _actor_ configuration includes the same three parameters: _actor_, _desc_
and _options_.

The simplest script will have a single configuration that executes a single
_actor_. More complex scripts can be created with our _group.Sync_ and
_group.Async_ actors which can be used to group together multiple _actors_ and
execute them in a predictable order.

### The Actors
Definition: _a participant in an action or process._

#### Base Actors

Kingpin provides several internal actors that can be used to create complex
and reliable groups of actions to be executed.

**Actor-specific Documentation**

  * [misc.Sleep](docs/actors/misc.Sleep.md)
  * [group.Sync](docs/actors/group.Sync.md)
  * [group.Async](docs/actors/group.Async.md)

#### HipChat

The Hipchat Actors allow you to send messages to a HipChat room during
as stages during your job execution. The actor supports dry mode by validating
that the configured API Token has access to execute the methods, without
actually sending the messages.

**Required Environment Variables**

  * `HIPCHAT_TOKEN` - HipChat API Token
  * `HIPCHAT_NAME` - HipChat `message from` name
    (defaults to `Kingpin`)

**Actor-specific Documentation**

  * [hipchat.Message](docs/actors/hipchat.Message.md)

#### RightScale

The RightScale Actors allow you to interact with resources inside your
Rightscale account. These actors all support dry runs properly, but each
actor has its own caveats with `dry=True`. Please read the instructions
below for using each actor.

**Required Environment Variables**

  * `RIGHTSCALE_TOKEN` - RightScale API Refresh Token
     (from the _Account Settings/API Credentials_ page)
  * `RIGHTSCALE_ENDPOINT` - You're account-specific API Endpoint
     (defaults to `https://my.rightscale.com`)

**Actor-specific Documentation**

  * [rightscale.server_array.Clone](docs/actors/rightscale.server_array.Clone.md)
  * [rightscale.server_array.Update](docs/actors/rightscale.server_array.Update.md)
  * [rightscale.server_array.Launch](docs/actors/rightscale.server_array.Launch.md)
  * [rightscale.server_array.Destroy](docs/actors/rightscale.server_array.Destroy.md)
  * [rightscale.server_array.Execute](docs/actors/rightscale.server_array.Execute.md)

## Development

Development-specific documentation can be found [here](DEVELOPMENT.md)
