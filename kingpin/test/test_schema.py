import json
import os

import unittest

from kingpin import exceptions
from kingpin import schema


class TestSchema(unittest.TestCase):
    def setUp(self, *args, **kwargs):
        super(TestSchema, self).setUp(*args, **kwargs)

        dirname, filename = os.path.split(os.path.abspath(__file__))
        self.examples = "%s/../../examples" % dirname

    def test_validate_with_simple_json(self):
        j = json.loads(open("%s/simple.json" % self.examples).read())
        ret = schema.validate(j)
        self.assertEqual(None, ret)

    def test_validate_with_complex_json(self):
        j = json.loads(open("%s/complex.json" % self.examples).read())
        ret = schema.validate(j)
        self.assertEqual(None, ret)

    def test_validate_with_invalid_json(self):
        j = {"this": "is", "invalid": "ok"}
        with self.assertRaises(exceptions.InvalidScript):
            schema.validate(j)

    def test_validate_with_array_syntax(self):
        j = [{"actor": "some actor"}]
        schema.validate(j)

    def test_validate_with_invalid_array(self):
        j = [{"garbage": "json"}]
        with self.assertRaises(exceptions.InvalidScript):
            schema.validate(j)
