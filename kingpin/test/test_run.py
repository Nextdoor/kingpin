import logging

from tornado.testing import unittest

from kingpin import run


class TestRunserver(unittest.TestCase):
    def testGetRootLogger(self):
        """Test getRootLogger() method"""
        logger = run.getRootLogger('iNfO', 'level0')
        self.assertTrue(isinstance(logger, logging.RootLogger))
