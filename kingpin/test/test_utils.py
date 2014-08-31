import logging
import os
import time

from tornado import gen
from tornado import testing
from tornado.testing import unittest
import mock
import requests

from kingpin import exceptions
from kingpin import utils


class TestUtils(unittest.TestCase):

    def test_str_to_class(self):
        class_string_name = 'tornado.testing.AsyncTestCase'
        returned_class = utils.str_to_class(class_string_name)
        self.assertEquals(testing.AsyncTestCase, returned_class)

    def test_populate_with_env(self):
        os.environ['UNIT_TEST'] = 'FOOBAR'
        string = 'Unit %UNIT_TEST% Test'
        expect = 'Unit FOOBAR Test'
        result = utils.populate_with_env(string)
        self.assertEquals(result, expect)

    def test_populate_with_env_with_missing_variables(self):
        os.environ['UNIT_TEST'] = 'FOOBAR'
        string = 'Unit %UNIT_TEST% Test %NOTFOUNDVARIABLE%'
        with self.assertRaises(exceptions.InvalidEnvironment):
            utils.populate_with_env(string)

    def test_convert_json_to_dict(self):
        dirname, filename = os.path.split(os.path.abspath(__file__))
        examples = '%s/../../examples' % dirname
        simple = '%s/simple.json' % examples
        ret = utils.convert_json_to_dict(simple)
        self.assertEquals(type(ret), dict)

    def test_exception_logger(self):
        @utils.exception_logger
        def raises_exc():
            raise Exception('Whoa')

        with self.assertRaises(Exception):
            raises_exc()


class TestSetupRootLoggerUtils(unittest.TestCase):

    def setUp(self):
        utils.setup_root_logger()

    def test_setup_root_logger(self):
        # Since we're really checking if loggers get created properly,
        # make sure to wipe out any existing logging handlers on the Root
        # logger object.
        log = logging.getLogger()
        log.handlers = []

        logger = utils.setup_root_logger()
        self.assertEquals(type(logger.handlers[0]), logging.StreamHandler)
        self.assertEquals(logger.level, logging.WARNING)

    def test_setup_root_logger_with_level(self):
        # Since we're really checking if loggers get created properly,
        # make sure to wipe out any existing logging handlers on the Root
        # logger object.
        log = logging.getLogger()
        log.handlers = []

        logger = utils.setup_root_logger(level='error')
        self.assertEquals(logger.level, logging.ERROR)

    def test_setup_root_logger_with_syslog(self):
        # Since we're really checking if loggers get created properly,
        # make sure to wipe out any existing logging handlers on the Root
        # logger object.
        log = logging.getLogger()
        log.handlers = []

        logger = utils.setup_root_logger(syslog='local0')
        self.assertEquals(type(logger.handlers[0]),
                          logging.handlers.SysLogHandler)
        self.assertEquals(logger.handlers[0].facility, 'local0')


class TestCoroutineHelpers(testing.AsyncTestCase):

    @testing.gen_test(timeout=30)
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

        # Finally, make it fail many times and test the retry
        mock_thing = mock.MagicMock()
        mock_thing.action.side_effect = [
            requests.exceptions.ConnectionError('doh1'),
            requests.exceptions.ConnectionError('doh2'),
            requests.exceptions.ConnectionError('doh3'),
            requests.exceptions.ConnectionError('wee'),
        ]

        with self.assertRaises(requests.exceptions.ConnectionError):
            yield utils.thread_coroutine(mock_thing.action)
        mock_thing.action.assert_called_twice_with()

#        # TMP
#        mock_thing.action.side_effect = [
#            requests.exceptions.ConnectionError('doh'),
#            requests.exceptions.ConnectionError('really_doh')]
#
#        yield utils.thread_coroutine(mock_thing.action)

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
