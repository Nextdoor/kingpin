import logging
import os
import time

from tornado import gen
from tornado import testing
from tornado.testing import unittest
import mock
import requests

from kingpin import utils


class TestUtils(unittest.TestCase):

    def testStrToClass(self):
        class_string_name = 'tornado.testing.AsyncTestCase'
        returned_class = utils.strToClass(class_string_name)
        self.assertEquals(testing.AsyncTestCase, returned_class)

    def testGetRootPath(self):
        path = utils.getRootPath()
        self.assertTrue(os.path.exists(path))
        self.assertTrue(os.path.exists('%s/test' % path))


class TestSetupLoggerUtils(unittest.TestCase):

    def setUp(self):
        utils.setupLogger()

    def testSetupLogger(self):
        # Since we're really checking if loggers get created properly,
        # make sure to wipe out any existing logging handlers on the Root
        # logger object.
        log = logging.getLogger()
        log.handlers = []

        logger = utils.setupLogger()
        self.assertEquals(type(logger.handlers[0]), logging.StreamHandler)
        self.assertEquals(logger.level, logging.WARNING)

    def testSetupLoggerWithLevel(self):
        # Since we're really checking if loggers get created properly,
        # make sure to wipe out any existing logging handlers on the Root
        # logger object.
        log = logging.getLogger()
        log.handlers = []

        logger = utils.setupLogger(level=logging.DEBUG)
        self.assertEquals(logger.level, logging.DEBUG)

    def testSetupLoggerWithSyslog(self):
        # Since we're really checking if loggers get created properly,
        # make sure to wipe out any existing logging handlers on the Root
        # logger object.
        log = logging.getLogger()
        log.handlers = []

        logger = utils.setupLogger(syslog='local0')
        self.assertEquals(type(logger.handlers[0]),
                          logging.handlers.SysLogHandler)
        self.assertEquals(logger.handlers[0].facility, 'local0')


class TestCoroutineHelpers(testing.AsyncTestCase):

    @testing.gen_test
    def test_thread_coroutine(self):
        # Create a method that we'll call and have it return
        mock_thing = mock.MagicMock()
        mock_thing.action.return_value = True

        ret = yield utils.thread_coroutine(mock_thing.action)
        self.assertEquals(ret, True)
        mock_thing.action.assert_called_once_with()

        # Now, lets have the function actually fail with a requests exception
        mock_thing = mock.MagicMock()
        mock_thing.action.side_effect = [
            requests.exceptions.ConnectionError('doh'), True]

        ret = yield utils.thread_coroutine(mock_thing.action)
        self.assertEquals(ret, True)
        mock_thing.action.assert_called_twice_with()

        # Finally, make it fail twice..
        mock_thing = mock.MagicMock()
        mock_thing.action.side_effect = [
            requests.exceptions.ConnectionError('doh'),
            requests.exceptions.ConnectionError('really_doh')]

        with self.assertRaises(requests.exceptions.ConnectionError):
            yield utils.thread_coroutine(mock_thing.action)
        mock_thing.action.assert_called_twice_with()

    @testing.gen_test
    def test_retry_with_backoff(self):

        # Define a method that will fail every time
        @gen.coroutine
        @utils.retry(excs=(requests.exceptions.HTTPError), retries=3)
        def raise_exception():
            raise requests.exceptions.HTTPError('Failed')

        with self.assertRaises(requests.exceptions.HTTPError):
            yield raise_exception()

        # Now a method that works
        @gen.coroutine
        @utils.retry(excs=(requests.exceptions.HTTPError), retries=3)
        def work():
            raise gen.Return(True)

        ret = yield work()
        self.assertEquals(ret, True)

    @testing.gen_test
    def testTornadoSleep(self):
        start = time.time()
        yield utils.tornado_sleep(0.1)
        stop = time.time()
        self.assertTrue(stop - start > 0.1)
