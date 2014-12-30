##### misc.Macro

Parses a kingpin JSON file, instantiates and executes it.

**Parse JSON**

Kingpin JSON has 2 passes at its validity. JSON syntax must be valid, with the
exception of a few useful deviations allowed by `demjson` parser. Main one
being the permission of inline comments via `/* this */` syntax.

The second pass is validating the Schema. The JSON file will be validated for
schema-conformity as one of the first things that happens at load-time when the
app starts up. If it fails, you will be notified immediately.

Lastly after JSON is established to be valid, all the tokens are replaced with
their specified value. Any key/value pair passed in the `tokens` option will be
available inside of the JSON file as `%KEY%` and replaced with the value at
this time.

In a situation where nested Macro executions are invoked the tokens **do not**
propagate from outter macro into the inner. This allows to reuse token names,
but forces the user to specify every token needed. Similarly, if environment
variables are used for token replacement in the main file, these tokens are not
available in the subsequent macros.

**Pre-Instantiation**

In an effort to prevent mid-run errors, we pre-instantiate all Actor objects
all at once before we ever begin executing code. This ensures that major typos
or misconfigurations in the JSON will be caught early on.

**Execution**

`misc.Macro` actor simply calls the `execute()` method of the most-outter
actor; be it a single action, or a group actor.

###### Options

  * `file` - String of local path to a JSON file.
  * `tokens` - Dictionary to search/replace within the file.

Examples

    { "desc": "Stage 1",
      "actor": "misc.Macro",
      "options": {
          "file": "deployment/stage-1.json",
          "tokens": {
              "TIMEOUT": 360,
              "RELEASE": "%RELEASE%"
          }
      }
    }

###### Dry Mode

Fully supported -- instantiates the actor inside of JSON with dry=True. The
behavior of the consecutive actor is unique to each; read their description
for more information on dry mode.
