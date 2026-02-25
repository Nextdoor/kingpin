# Kingpin — Style & Conventions

## Formatting
- **Formatter**: `black` (default config, no custom settings)
- Run with: `make lint` (dry-run/check mode) or `DRY=false make lint` (apply)

## Naming Conventions
- **Modules/files**: snake_case (`api_call_queue.py`, `base.py`)
- **Classes**: PascalCase (`BaseActor`, `EnsurableBaseActor`, `BaseGroupActor`)
- **Methods/functions**: snake_case with leading underscore for private (`_setup_log`, `_validate_options`)
- **Constants**: UPPER_SNAKE_CASE (`REQUIRED`, `STATE`, `DEFAULT_TIMEOUT`)
- **Module-level logger**: `log = logging.getLogger(__name__)`
- **Author tag**: `__author__ = "Name <email>"` in module globals

## Docstrings
- Module-level docstrings use Sphinx `:mod:` directive format:
  ```python
  """
  :mod:`kingpin.actors.base`
  ^^^^^^^^^^^^^^^^^^^^^^^^^^
  
  Description of the module
  """
  ```
- Class/method docstrings use plain description with `Args:` sections (Google-ish style)
- Type annotations are described in docstrings, not via Python type hints

## Type Hints
- **Not used** in the codebase — types are documented in docstrings and `all_options` dicts instead

## Imports
- Standard library imports first, then third-party, then local (`kingpin.*`)
- Tornado imports use `from tornado import gen` style (not `import tornado.gen`)
- Local imports use `from kingpin.actors import base` style

## Async Pattern
- Uses Tornado `@gen.coroutine` decorator with `yield` (NOT async/await)
- Return values via `raise gen.Return(value)`
- Timeouts via `gen.with_timeout()`

## Actor Definition Pattern
- Each actor defines `all_options` class attribute (dict of option specs)
- Options format: `{'name': (type, default, "description")}` where `REQUIRED` = no default
- Actors implement `_execute()` coroutine for their main logic
- `EnsurableBaseActor` adds state management (`present`/`absent`)

## Test Conventions
- Test files mirror source: `actors/test/test_base.py` tests `actors/base.py`
- Tests use `tornado.testing.AsyncTestCase` / `gen_test` for async tests
- Mocking via `mock` library (not `unittest.mock`)
- Integration tests prefixed with `integration_` (separate from unit tests)
- Test helper in `actors/test/helper.py`

## PR Title Convention (Conventional Commits)
- Required format: `type(scope): description`
- **Types**: chore, docs, feat, fix, refactor, test
- **Scopes**: deps, docs, ci, actors, aws, s3, iam, cfn, cloudformation, group, macro
- Scope is **required**
