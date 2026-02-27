# Kingpin Quick Reference

## What is it?
Deployment Automation Engine by Nextdoor. JSON/YAML DSL for orchestrating deployment actions via the Actor pattern. Uses Python asyncio.

## Version & Python
- Current: 8.1.0 (in `kingpin/version.py`)
- Python: 3.11, 3.12, 3.13

## Key Entry Points
- CLI: `kingpin` -> `kingpin.bin.deploy:begin`
- Main actor loading: `actors/utils.py:get_actor()`
- Schema: `schema.py` (SCHEMA_1_0)

## Architecture
- **Actor pattern**: BaseActor -> EnsurableBaseActor, HTTPBaseActor, BaseGroupActor
- **AWS actors**: AWSBaseActor with boto3 (ThreadPoolExecutor), api_call_queue with backoff
- **Token system**: `%TOKEN%` (env/file) + `{CONTEXT}` (actor instantiation)
- **Dry run**: All actors support `dry=True`; CLI runs dry before real by default

## Package Structure
```
kingpin/
  version.py, constants.py, exceptions.py, schema.py, utils.py
  bin/deploy.py             # CLI
  actors/
    base.py                 # BaseActor, EnsurableBaseActor, HTTPBaseActor
    group.py                # Sync, Async
    misc.py                 # Note, Macro, Sleep, GenericHTTP
    utils.py                # @dry, @timer, get_actor()
    aws/base.py, settings.py, api_call_queue.py
    aws/cloudformation.py   # Create, Delete, Stack (largest file: 1348 lines)
    aws/iam.py              # User, Group, Role, InstanceProfile
    aws/s3.py               # Bucket (EnsurableAWSBaseActor)
```

## Class Hierarchy (key relationships)
```
BaseActor
  EnsurableBaseActor          # get/compare/set pattern for idempotent state mgmt
  HTTPBaseActor               # async HTTP client (urllib in ThreadPoolExecutor)
  BaseGroupActor
    Sync                      # Sequential; in dry mode continues past failures
    Async                     # Parallel; optional concurrency limit

AWSBaseActor(BaseActor)       # boto3 clients, api_call() via executor
  EnsurableAWSBaseActor       # Combines AWS + Ensurable
    s3.Bucket                 # Full S3 lifecycle (largest Ensurable actor)
  IAMBaseActor                # Generalized IAM entity CRUD
    iam.User, iam.Group, iam.Role, iam.InstanceProfile
  CloudFormationBaseActor     # CFN stack operations
    cloudformation.Create, .Delete, .Stack
```

## Error Hierarchy
- `RecoverableActorFailure` -- swallowed if `warn_on_failure=True`
  - ActorTimedOut, BadRequest, CloudFormationError, StackFailed, InvalidBucketConfig
- `UnrecoverableActorFailure` -- always fatal
  - InvalidActor, InvalidOptions, InvalidCredentials, InvalidTemplate

## Commands
- `make test` -- pytest + pyflakes + smoke tests
- `make lint` -- Black formatting check
- `make ruff` -- Ruff linting
- `make mypy` -- Type checking (excludes tests)
- `make build` -- Build package
- `make bump VERSION=patch` -- Version bump + PR

## Style
- Formatter: Black
- Linter: Ruff + Pyflakes (transition)
- Types: mypy (gradual, `disallow_untyped_defs=false`)
- Async: all actors use coroutines; blocking I/O via run_in_executor
- Tests: unittest.IsolatedAsyncioTestCase, co-located with source

## PR Conventions
- Conventional commits required: `type(scope): description`
- Types: chore, docs, feat, fix, refactor, test
- Scopes: deps, docs, ci, actors, aws, s3, iam, cfn, cloudformation, group, macro, release
- Always open PRs in draft mode

## Key Design Decisions
- Timeout does NOT cancel underlying task (uses asyncio.shield)
- Pre-instantiation: all actors validated before any execution
- Token replacement operates on serialized JSON strings
- CFN Stack actor uses MD5 hash of template body to skip no-op updates
- ApiCallQueue serializes AWS calls with exponential backoff (0.25s-30s)
- No web framework dependency -- pure asyncio + stdlib urllib