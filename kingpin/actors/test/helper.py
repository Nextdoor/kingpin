__author__ = "Mikhail Simin <mikhail@nextdoor.com>"


def mock_tornado(value=None, exc=None):
    """Creates a mock for an async function that returns `value`"""

    async def call(*args, **kwargs):
        call._call_count = call._call_count + 1
        if exc:
            raise exc
        return value

    call._call_count = 0
    return call


class _ReusableAwaitable:
    """An awaitable that can be awaited multiple times, always returning value.

    Native coroutines can only be awaited once. This class wraps a value in an
    object with __await__ that can be reused, matching the old Tornado Future
    behavior where mock.return_value could be yielded repeatedly.
    """

    def __init__(self, value):
        self._value = value

    def __await__(self):
        yield
        return self._value


def tornado_value(value=None):
    """Returns a reusable awaitable wrapping value. Safe for mock.return_value."""
    return _ReusableAwaitable(value)
