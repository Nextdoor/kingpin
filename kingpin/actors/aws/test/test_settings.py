from boto.exception import PleaseRetryException
from tornado import testing

from kingpin.actors.aws import settings


class TestSettings(testing.AsyncTestCase):

    def test_is_retriable(self):

        class TransientError(PleaseRetryException):
            """Unit-test exception"""

        self.assertTrue(settings.is_retriable_exception(TransientError('500')))

        self.assertFalse(settings.is_retriable_exception(Exception()))
