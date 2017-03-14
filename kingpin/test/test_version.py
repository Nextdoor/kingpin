"""Vanity test"""

import unittest

import six.moves


class TestVersion(unittest.TestCase):

    def test_version(self):
        from kingpin import version
        six.moves.reload_module(version)
        self.assertEquals(type(version.__version__), str)
