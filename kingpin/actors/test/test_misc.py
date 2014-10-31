import logging

from tornado import testing
from tornado import httpclient

from kingpin.actors import exceptions
from kingpin.actors import misc
from kingpin.actors.test.helper import mock_tornado

log = logging.getLogger(__name__)


class TestSleep(testing.AsyncTestCase):
    @testing.gen_test
    def test_execute(self):
        # Call the executor and test it out
        actor = misc.Sleep('Unit Test Action', {'sleep': 0.1})
        res = yield actor.execute()

        # Make sure we fired off an alert.
        self.assertEquals(res, None)


class TestGenericHTTP(testing.AsyncTestCase):

    @testing.gen_test
    def test_execute_dry(self):
        actor = misc.GenericHTTP('Unit Test Action',
                                 {'url': 'http://example.com'},
                                 dry=True)

        actor._fetch = mock_tornado()

        yield actor.execute()

        self.assertEquals(actor._fetch._call_count, 0)

    @testing.gen_test
    def test_execute(self):
        actor = misc.GenericHTTP('Unit Test Action',
                                 {'url': 'http://example.com'})
        actor._fetch = mock_tornado({'success': {'code': 200}})

        yield actor.execute()

    @testing.gen_test
    def test_execute_fail(self):
        actor = misc.GenericHTTP('Unit Test Action',
                                 {'url': 'http://example.com'})
        error = httpclient.HTTPError(code=401, response={})
        actor._fetch = mock_tornado(exc=error)

        with self.assertRaises(exceptions.InvalidCredentials):
            yield actor.execute()
