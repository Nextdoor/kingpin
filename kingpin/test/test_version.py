"""Vanity test"""

import unittest
import importlib


class TestVersion(unittest.TestCase):

    def test_version(self):
        from kingpin import version
        importlib.reload(version)
        self.assertEqual(type(version.__version__), str)
