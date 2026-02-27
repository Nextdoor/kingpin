# Actor Patterns & Internals

## BaseActor.__init__ flow
1. Set instance vars (_type, _options, _desc, _dry, _warn_on_failure, _condition, _timeout)
2. `_fill_in_contexts()` -- Replace {KEY} tokens in desc, condition, and options
3. `_setup_log()` -- Create LogAdapter with dry prefix
4. `_setup_defaults()` -- Fill missing options with defaults from `all_options`
5. `_validate_options()` -- Check required options, type validation, custom validators

## BaseActor.execute() flow
1. Check `_check_condition()` -- skip if false
2. `timeout(_execute)` -- wrap in asyncio.wait_for + asyncio.shield
3. Exception handling:
   - `ActorException` -- if RecoverableActorFailure AND warn_on_failure, warn and continue
   - `ExceptionGroup` -- unwrap first exception, same recovery logic
   - Generic `Exception` -- wrap in ActorException, log author contact info

## EnsurableBaseActor pattern
- Auto-adds `state` option (present/absent)
- `_gather_methods()` at init: discovers `_get_X`, `_set_X`, `_compare_X` for each option
- Creates default `_compare_X` (simple equality) if not provided
- `_execute()` pipeline: `_precache()` -> `_ensure("state")` -> for each option: `_ensure(option)`
- `unmanaged_options` list: options excluded from ensure cycle (e.g., "name", "region")

## Group actors
- `strict_init_context = False` (nested groups may have unresolved tokens)
- `remove_escape_sequence = False` (let sub-actors handle their own escapes)
- `_build_actions()`: if contexts provided, instantiate acts once per context dict
- Contexts can be: list of dicts, or string path to JSON/YAML file with list of dicts

## Token replacement details
- `%TOKEN%` tokens: replaced via `utils.populate_with_tokens()` when loading scripts
- `{CONTEXT}` tokens: replaced at actor instantiation via `_fill_in_contexts()`
- Default values: `%KEY|default_value%` syntax supported
- Escape: `\%TOKEN\%` -> `%TOKEN%` (not replaced)
- Options are JSON-serialized -> token-replaced -> JSON-deserialized (enables deep replacement)

## @dry decorator (actors/utils.py)
- Always compiles the dry message (catches bad kwargs even in non-dry)
- In dry mode: logs warning and returns None
- In real mode: calls the wrapped async function

## @timer decorator (actors/utils.py)
- Wraps async functions, records wall-clock time via time.time()
- Logs execution time as debug message

## get_actor() resolution order
Tries to import actor string with prefixes: "kingpin.actors.", "", "actors."
Allows short names like "misc.Sleep" or fully qualified "kingpin.actors.misc.Sleep"
