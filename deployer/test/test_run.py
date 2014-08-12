from StringIO import StringIO
import mock
import logging

from tornado.testing import unittest

from deployer import run


class TestRunserver(unittest.TestCase):
    def testGetRootLogger(self):
        """Test getRootLogger() method"""
        logger = run.getRootLogger('iNfO', 'level0')
        self.assertTrue(isinstance(logger, logging.RootLogger))
