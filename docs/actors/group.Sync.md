##### group.Sync

Groups together a series of Actors and executes them synchronously
in the order that they were defined.

**Options**

  * `acts` - An array of individual Actor definitions.
  * `contexts` - A list of dictionaries with _contextual tokens_ to pass into
    the actors at instantiation time. If the list has more than one element,
    then every actor defined in `acts` will be instantiated once for each item
    in the `contexts` list.

Examples

    # Creates two arrays ... but sleeps 60 seconds between the two, then
    # does not sleep at all after the last one.
    { "desc": "Clone, then sleep ... then clone, then sleep shorter...",
      "actor": "group.Sync",
      "options": {
        "contexts": [
          { "ARRAY": "First", "SLEEP": "60", },
          { "ARRAY": "Second", "SLEEP": "0", }
        ],
        "acts": [
          { "desc":
            "do something",
            "actor": "server_array.Clone",
            "options": {
              "source": "template",
              "dest": "{ARRAY}"
            }
          },
          { "desc": "sleep",
            "actor": "misc.Sleep",
            "options": {
              "sleep": "{SLEEP}",
            }
          }
        ]
      }
    }

**Dry Mode**

Passes on the Dry mode setting to the acts that are called.

**Failure**

In the event that an act fails, this actor will return the failure immediately.
Because the acts are executed in-order of definition, the failure will
prevent any further acts from executing.
