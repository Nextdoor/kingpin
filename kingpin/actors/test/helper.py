from unittest import util as unittest_util

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
def tornado_value(value=None):
    """Convers whatever is passed in to a tornado value."""
    raise gen.Return(value)


class InAnyOrder(object):
    """ An order-independent matcher for enumerables. """
    def __init__(self, items):
        self._items = items

    def __eq__(self, other):
        return not unittest_util._count_diff_all_purpose(self._items, other)

    def __ne__(self, other):
        return not(self == other)

    def __repr__(self):
        return '<IN ANY ORDER: %s>' % self._items
