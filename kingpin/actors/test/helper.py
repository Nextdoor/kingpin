from tornado import gen

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'


def mock_tornado(value=None, exc=None):
    """Creates a mock for a coroutine function that returns `value`"""

    @gen.coroutine
    def call(*args, **kwargs):
        call._call_count = call._call_count + 1
        if exc:
            raise exc
        raise gen.Return(value)

    call._call_count = 0
    return call


@gen.coroutine
def tornado_value(value):
    """Convers whatever is passed in to a tornado value."""
    raise gen.Return(value)
