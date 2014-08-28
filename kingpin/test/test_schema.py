import os
import unittest

import commentjson as json
import jsonschema

from kingpin import schema


class TestSchema(unittest.TestCase):

    def setUp(self):
        abs_path = os.path.abspath(__file__)
        self.examples = '%s/../../examples' % os.path.dirname(abs_path)

    def test_validate_simple(self):
        # Import a valid schema from our examples
        simple = json.loads(open('%s/simple.json' % self.examples).read())
        self.assertEquals(None, schema.validate(simple))

    def test_validate_complex(self):
        # Import a valid schema from our examples
        complex = json.loads(open('%s/complex.json' % self.examples).read())
        self.assertEquals(None, schema.validate(complex))

    def test_validate_with_invalid_data(self):
        invalid = {'desc': 'do something', 'my_options': 'huh?'}
        with self.assertRaises(jsonschema.ValidationError):
            schema.validate(invalid)
