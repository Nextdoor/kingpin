# Kingpin Code Style & Conventions

## Formatting
- **Black** is the sole formatter (ruff format exists in config but NOT active)
- Line length: managed by Black (E501 ignored in ruff)

## Imports
- Sorted by isort (ruff `I` rule)
- Standard pattern: stdlib, third-party, then `from kingpin...`

## Naming
- snake_case for functions, variables, module names
- CamelCase for classes
- `_private_method` prefix for internal methods
- `__author__` module-level attribution in every module

## Type Hints
- Gradual adoption (`disallow_untyped_defs = false` in mypy)
- Modern syntax: `str | None` (not `Optional[str]`), `dict[str, object]`
- Public APIs have hints; internal methods vary

## Docstrings
- RST-style for Sphinx: `:mod:`, `:param:`, etc.
- Module-level docstrings with description
- Actor classes have extensive docstrings documenting options, examples, dry mode behavior

## Logging
- `log = logging.getLogger(__name__)` in every module
- Actors use `LogAdapter` with `[DRY: desc]` prefix
- f-strings for log messages

## Testing
- `unittest.IsolatedAsyncioTestCase` for async tests
- `unittest.mock.AsyncMock` for async mocking
- Tests co-located: `module/test/test_module.py`
- Integration tests separated as `integration_*.py`

## Actor Conventions
- `all_options` dict: `{name: (type, default_or_REQUIRED, description)}`
- `desc` class attribute with `{option}` placeholders
- `_execute()` is the main coroutine (called by `execute()`)
- `@dry("message")` decorator for dry-run skipping
- Errors: RecoverableActorFailure vs UnrecoverableActorFailure

## What to Run After Code Changes
1. `make lint` (Black check)
2. `make ruff` (Ruff check)  
3. `make test` (full test suite)
4. `make mypy` (type check, optional but recommended)
