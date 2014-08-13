import os
import logging

from tornado import testing
from tornado.testing import unittest

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
