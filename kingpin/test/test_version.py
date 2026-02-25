"""Vanity test"""

import importlib
import unittest


class TestVersion(unittest.TestCase):
    def test_version(self):
        from kingpin import version

        importlib.reload(version)
        self.assertEqual(type(version.__version__), str)
