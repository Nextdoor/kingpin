##### group.Sync

Groups together a series of Actors and executes them synchronously
in the order that they were defined.

**Options**

  * `acts` - An array of individual Actor definitions.

Examples

    { 'acts': [
      { 'desc': 'sleep', 'actor': 'misc.Sleep',
        'options': { 'sleep': 60 } },
      { 'desc': 'do something', 'actor': 'server_array.Clone',
        'options': { 'source': 'template', 'dest': 'new_array' } },
    ] }

**Dry Mode**

Passes on the Dry mode setting to the acts that are called.

**Failure**

In the event that an act fails, this actor will return the failure immediately.
Because the acts are executed in-order of definition, the failure will
prevent any further acts from executing.
