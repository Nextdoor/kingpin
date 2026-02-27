# Testing Patterns

## Framework
- pytest as runner, unittest.IsolatedAsyncioTestCase for async tests
- unittest.mock (Mock, MagicMock, AsyncMock, patch)
- pytest-cov for coverage (omits **/test/*)
- No pytest-asyncio -- pure stdlib async testing

## Common Patterns

### Mocking boto3
```python
# AWS tests mock at the connection method level
self.actor.iam_conn.create_user = mock.MagicMock()
self.actor.s3_conn.list_buckets = mock.MagicMock(return_value={...})
```

### Mocking async execute
```python
self.actor._execute = AsyncMock()
await self.actor.execute()
self.assertEqual(self.actor._execute.await_count, 1)
```

### Testing actors
```python
class TestMyActor(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.actor = MyActor("Test", {"option": "value"}, dry=True)

    async def test_execute(self):
        # Mock external calls
        self.actor.some_method = AsyncMock(return_value="result")
        await self.actor.execute()
```

### Fake Ensurable actors for testing
```python
class FakeEnsurableBaseActor(base.EnsurableBaseActor):
    all_options = {"name": (str, REQUIRED, "...")}
    unmanaged_options = ["name"]
    async def _set_state(self): ...
    async def _get_state(self): ...
```

## Test File Naming
- Unit: `test_<module>.py`
- Integration: `integration_<module>.py`

## Running Specific Tests
```bash
PYTHONPATH=. uv run pytest -v kingpin/actors/test/test_base.py
PYTHONPATH=. uv run pytest -v -k "test_execute"
PYTHONPATH=. uv run pytest --cov=kingpin -v  # With coverage
```

## AWS Test Setup
- `aws_settings.AWS_ACCESS_KEY_ID = ""` in test setUp to prevent real API calls
- boto3 clients are mocked at the method level, not at the client creation level
