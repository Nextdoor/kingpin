# Gotchas & Things to Watch Out For

## Mutable Default Arguments
- `BaseActor.__init__` uses `options={}` and `init_context={}` as defaults intentionally
- These are immediately copied/consumed, not mutated -- B006/B008 ignored in ruff

## Test Environment Manipulation
- `test_base.py` sets `os.environ["URLLIB_DEBUG"] = "1"` BEFORE importing base module
- Uses `importlib.reload(base)` to re-trigger module-level env checks
- This causes E402 (late imports) which is intentionally ignored

## Class-Level all_options Mutation
- `EnsurableBaseActor.__init__` mutates `self.all_options["state"]` -- must be done before super().__init__
- Some tests modify `base.BaseActor.all_options` directly and must reset it after

## Token Replacement Works on JSON Strings
- Options are JSON.dumps() -> token replace -> JSON.loads()
- This means token values must be JSON-safe strings
- Escape sequence for options is `\\\\` (double-escaped backslash)

## Async Patterns
- group.Async uses `asyncio.ensure_future()` (older pattern), not TaskGroup
- IAM actors use `asyncio.TaskGroup` (newer pattern) -- mixed usage in codebase
- `BaseActor.timeout()` uses `asyncio.shield()` -- timed-out tasks keep running!
- `api_call_queue._consumer_task` created via ensure_future at init -- runs forever

## File Location for Tests
- Tests are co-located: `kingpin/actors/test/`, `kingpin/actors/aws/test/`, `kingpin/test/`
- NOT in a top-level `tests/` directory
- Integration tests (`integration_*.py`) require real AWS creds, not run in CI

## Ruff/Black Transition
- Black is the ONLY active formatter
- Ruff format config exists but has TODO comments saying it's not used yet
- Both pyflakes AND ruff run F checks (parallel during transition)

## Schema Validation
- `SchemaCompareBase` uses `Draft202012Validator` (not Draft4)
- `StringCompareBase.validate()` is a classmethod but uses `self` parameter name (works because classmethod)

## CloudFormation-Specific
- `cfn_tools` YAML loader has a monkey-patched `construct_mapping` in utils.py to fix merge anchor parsing
- Stack actor's hash check uses stack Outputs -- if output key is missing, it falls through to full comparison
- `_discover_noecho_params()` reads template to find params marked NoEcho=true

## PR Requirements
- Scope is REQUIRED in PR titles (not optional)
- `prlint.yml` runs on runs-on (custom runner), not ubuntu-latest
