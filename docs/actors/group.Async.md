##### group.Async

Groups together a series of Actors and executes them asynchronously -
waiting until all of them finish before returning.

**Options**

  * `acts` - An array of individual Actor definitions.
  * `contexts` - A list of dictionaries with _contextual tokens_ to pass into
    the actors at instantiation time. If the list has more than one element,
    then every actor defined in `acts` will be instantiated once for each item
    in the `contexts` list.

**Timeouts**

Timeouts are disabled specifically in this actor. The sub-actors can still
raise their own `ActorTimedOut` exceptions, but since the group actors run an
arbitrary number of sub actors, we have chosen to not have this actor
specifically raise its own `ActorTimedOut` exception unless the user sets the
`timeout` setting.

Examples

    # Clone two arrays quickly
    { "desc": "Clone two arrays",
      "actor": "group.Async",
      "options": {
        "contexts": [
          { "ARRAY": "NewArray1" },
          { "ARRAY": "NewArray2" }
        ],
        "acts": [
          { "desc": "do something",
            "actor": "server_array.Clone",
            "options": {
              "source": "template",
              "dest": "{ARRAY}",
            }
          }
        ]
      }
    }

**Dry Mode**

Passes on the Dry mode setting to the sub-actors that are called.

**Failure**

In the event that one or more `acts` fail in this group, the entire group acts
will return a failure to Kingpin. Because multiple actors are executing all at
the same time, the all of these actors will be allowed to finish before the
failure is returned.
