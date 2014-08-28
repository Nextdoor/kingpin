# Kingpin: the chief element of any system, plan, or the like.

Automated Deployment Engine

## Basic Use

TODO

### Credentials

TODO

### DSL

#### The Script

*The blueprint or roadmap that outlines a movie story through visual
descriptions, actions of characters and their dialogue. The term "script" also
applies to stageplays as well.*

### Acts
*A large division of a full-length play, separated from the other act or acts
by an intermission.*


### The Actors


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
