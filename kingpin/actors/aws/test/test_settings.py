from boto.exception import BotoServerError
from tornado import testing

from kingpin.actors.aws import settings


class TestSettings(testing.AsyncTestCase):

    def test_is_retriable(self):

        class TransientError(BotoServerError):
            """Unit-test exception"""

        exc = TransientError('500', 'Throttling everything')
        exc.error_code = 'Throttling'
        self.assertTrue(settings.is_retriable_exception(exc))

        self.assertFalse(settings.is_retriable_exception(Exception()))
