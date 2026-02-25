# Code Style & Conventions

## Formatting
- **black** formatter (no custom config detected, uses defaults)
- Line length: black default (88 chars)

## Naming
- snake_case for functions, methods, variables
- CamelCase for classes
- UPPER_SNAKE_CASE for module-level constants
- Private methods prefixed with `_` (e.g., `_execute`, `_fetch`)

## Type Hints
- Minimal use of type hints — mostly absent except in newer code
- Some `-> bool` return type annotations in `utils.py`
- `typing.Optional` used in `cloudformation.py`

## Docstrings
- Google-style docstrings with Args/Returns/Raises sections
- RST-style module docstrings at top of files (`:mod:` directive)
- `__author__` module-level attribute required in every actor module

## Async Pattern
- Tornado `@gen.coroutine` + `yield` pattern (NOT async/await)
- Return values via `raise gen.Return(value)` (NOT `return`)
- Non-blocking IO via Tornado's IOLoop

## Actor Design Pattern
- Every actor must subclass `base.BaseActor`
- Must implement `_execute()` as a coroutine
- Must support dry mode (`self._dry`)
- Options via `all_options` class dict: `{name: (type, default_or_REQUIRED, description)}`
- `__author__` attribute is required and used at runtime

## PR Title Convention
Conventional commits required: `type(scope): description`
- Types: chore, docs, feat, fix, refactor, test
- Scopes: deps, docs, ci, actors, aws, s3, iam, cfn, cloudformation, group, macro
