# DSL Schema & Script Loading

## Schema (kingpin/schema.py)
ACTOR_SCHEMA properties:
- `actor` (required, string) -- class name like "misc.Sleep" or "aws.cloudformation.Stack"
- `desc` (string) -- human-readable description
- `options` (object) -- actor-specific; `acts` sub-property for groups
- `warn_on_failure` (boolean|string) -- swallow RecoverableActorFailure
- `timeout` (string|integer|number) -- override default timeout
- `condition` (boolean|string, default true) -- skip actor if false

SCHEMA_1_0: top level can be a single actor object OR an array of actors.
Array at top level is implicitly wrapped in group.Sync by misc.Macro.

## Script Loading Flow (misc.Macro)
1. `_check_macro()` -- reject ftp:// URLs
2. `_get_macro()` -- open local file or download HTTP/HTTPS URL
3. `_get_config_from_script()` -- `utils.load_json_with_tokens(file, init_tokens)`
4. `_check_schema()` -- `schema.validate(config)`
5. Instantiate top-level actor (list -> group.Sync, dict -> get_actor)

## Token Sources
- **CLI level**: `os.environ` passed as `tokens` dict to Macro
- **Macro level**: `init_tokens` (inherited from parent) + explicit `tokens` option
- **Group level**: `init_context` from contexts list + inherited context
- Tokens do NOT propagate automatically between nested Macros

## File Format Detection
- `.json` -> json.loads()
- `.yml`/`.yaml` -> cfn_tools.load_yaml() (handles CFN-specific YAML)
- Other -> InvalidScriptName exception

## YAML Special Handling
- cfn_tools.yaml_loader.CfnYamlLoader with monkey-patched construct_mapping
- Supports YAML merge anchors (<<: *anchor)
- Supports CloudFormation intrinsic functions (!Ref, !Sub, etc.)
