# Ruff Rules for Tornado-to-AsyncIO Migration

## Key Finding: No Tornado-Specific Rules
Ruff has NO rules that specifically detect Tornado patterns like `gen.coroutine`,
`gen.Return`, `IOLoop.instance()`, etc. These must be caught via custom tooling
or manual review. The flake8-async rules focus on asyncio/trio/anyio patterns.

## ASYNC Rules — Full List (flake8-async)
All detect blocking/problematic patterns in `async def` functions:

- ASYNC100: cancel-scope-no-checkpoint — timeout context manager lacks await
- ASYNC105: trio-sync-call — missing await on trio async call (auto-fix)
- ASYNC109: async-function-with-timeout — timeout param instead of context manager
- ASYNC110: async-busy-wait — sleep in while loop, use Event instead
- ASYNC115: async-zero-sleep — sleep(0) should be checkpoint() (auto-fix)
- ASYNC116: long-sleep-not-forever — sleep >24h should be sleep_forever (auto-fix)
- ASYNC210: blocking-http-call-in-async-function — urllib/requests in async
- ASYNC212: blocking-http-call-httpx-in-async-function — httpx.Client in async
- ASYNC220: create-subprocess-in-async-function — os.popen in async
- ASYNC221: run-process-in-async-function — subprocess.run in async
- ASYNC222: wait-for-process-in-async-function — os.waitpid in async
- ASYNC230: blocking-open-call-in-async-function — open() in async
- ASYNC240: blocking-path-method-in-async-function — os.path/pathlib blocking
- ASYNC250: blocking-input-in-async-function — input() in async
- ASYNC251: blocking-sleep-in-async-function — time.sleep in async

## Key UP Rules for Patterns We Already Fixed
- UP004: useless-object-inheritance — `class Foo(object)` → `class Foo`
- UP008: super-call-with-parameters — `super(Cls, self)` → `super()`
- UP031: printf-string-formatting — `"%s" % x` → `.format()` or f-string
- UP032: f-string — `.format()` → f-string
- UP028: yield-in-for-loop — `for x in y: yield x` → `yield from y`

## Key UP Rules for Async Migration
- UP041: timeout-error-alias — `asyncio.TimeoutError` → `TimeoutError`
- UP024: os-error-alias — `IOError` → `OSError`

## Key UP Rules for Python 3.11+ Modernization
- UP006: non-pep585-annotation — `typing.List[int]` → `list[int]`
- UP007: non-pep604-annotation-union — `Union[X, Y]` → `X | Y`
- UP035: deprecated-import — `from collections import Sequence` → `.abc`
- UP036: outdated-version-block — dead `sys.version_info` checks
- UP042: replace-str-enum — `(str, enum.Enum)` → `enum.StrEnum`

## Key RUF Rules for Async
- RUF006: asyncio-dangling-task — `create_task()` without saving reference
- RUF029: unused-async (preview) — `async def` with no await inside
