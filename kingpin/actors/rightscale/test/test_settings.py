from tornado import testing
import requests

from kingpin.actors.rightscale import settings


class TestSettings(testing.AsyncTestCase):

    def test_is_retriable(self):

        class TransientError(requests.exceptions.HTTPError):

            """Unit-test exception"""

        exc = TransientError('500', 'Throttling everything')
        exc.error_code = 'Throttling'
        self.assertTrue(settings.is_retriable_exception(exc))

        self.assertFalse(settings.is_retriable_exception(Exception()))
