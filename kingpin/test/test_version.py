"""Vanity test"""

import unittest


class TestVersion(unittest.TestCase):

    def test_version(self):
        from kingpin import version
        reload(version)
        self.assertEquals(type(version.__version__), str)
