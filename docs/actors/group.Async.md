##### group.Async

Groups together a series of Actors and executes them asynchronously -
waiting until all of them finish before returning.

**Options**

  * `acts` - An array of individual Actor definitions.

Examples

    { 'acts': [
      { 'desc': 'do something', 'actor': 'server_array.Clone',
        'options': { 'source': 'template', 'dest': 'new_array_1' } },
      { 'desc': 'do something', 'actor': 'server_array.Clone',
        'options': { 'source': 'template', 'dest': 'new_array_2' } },
    ] }

**Dry Mode**

Passes on the Dry mode setting to the sub-actors that are called.
