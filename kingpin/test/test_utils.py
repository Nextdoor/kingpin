import logging
import os
import time

from tornado import gen
from tornado import testing
from tornado.testing import unittest
import rainbow_logging_handler

from kingpin import exceptions
from kingpin import utils
from kingpin.actors.test import helper


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

        # Default logger is basic
        logger = utils.setup_root_logger()
        self.assertEquals(type(logger.handlers[0]), logging.StreamHandler)
        self.assertEquals(logger.level, logging.WARNING)

    def test_setup_root_logger_color(self):
        # Since we're really checking if loggers get created properly,
        # make sure to wipe out any existing logging handlers on the Root
        # logger object.
        log = logging.getLogger()
        log.handlers = []

        # Color logger is nifty
        logger = utils.setup_root_logger(color=True)
        self.assertEquals(
            type(logger.handlers[0]),
            rainbow_logging_handler.RainbowLoggingHandler)
        self.assertEquals(logger.level, logging.WARNING)

    def test_setup_root_logger_with_level(self):
        # Since we're really checking if loggers get created properly,
        # make sure to wipe out any existing logging handlers on the Root
        # logger object.
        log = logging.getLogger()
        log.handlers = []

        logger = utils.setup_root_logger(level='debug')
        self.assertEquals(logger.level, logging.DEBUG)

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

    def test_super_httplib_debug_logging(self):
        logger = utils.super_httplib_debug_logging()
        self.assertEquals(10, logger.level)


class TestCoroutineHelpers(testing.AsyncTestCase):

    @testing.gen_test
    def test_retry_with_backoff(self):

        # Define a method that will fail every time
        counter = helper.mock_tornado()

        @gen.coroutine
        @utils.retry(retries=3)
        def always_fail():
            yield counter()
            raise gen.Return(False)

        res = yield always_fail()
        self.assertFalse(res)  # Should alwyays return false
        self.assertEquals(counter._call_count, 3)  # should retry 3 times.

        # Now a method that works
        counter = helper.mock_tornado()

        @gen.coroutine
        @utils.retry(retries=3)
        def work():
            yield counter()
            raise gen.Return(True)

        ret = yield work()
        self.assertTrue(ret)
        self.assertEquals(counter._call_count, 1)  # Shouldn't be retried

    @testing.gen_test
    def testTornadoSleep(self):
        start = time.time()
        yield utils.tornado_sleep(0.1)
        stop = time.time()
        self.assertTrue(stop - start > 0.1)
