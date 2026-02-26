import unittest

from kingpin.actors import exceptions
from kingpin.constants import SchemaCompareBase


class _TestSchema(SchemaCompareBase):
    SCHEMA = {
        "type": ["object", "null"],
        "required": ["name"],
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string"},
            "count": {"type": "integer"},
        },
    }


class TestSchemaCompareBase(unittest.TestCase):
    def test_valid_option_passes(self):
        _TestSchema.validate({"name": "foo", "count": 1})

    def test_valid_option_minimal(self):
        _TestSchema.validate({"name": "bar"})

    def test_null_passes_when_schema_allows(self):
        _TestSchema.validate(None)

    def test_invalid_option_raises(self):
        with self.assertRaises(exceptions.InvalidOptions):
            _TestSchema.validate({"wrong_key": "value"})

    def test_missing_required_raises(self):
        with self.assertRaises(exceptions.InvalidOptions):
            _TestSchema.validate({"count": 1})

    def test_wrong_type_raises(self):
        with self.assertRaises(exceptions.InvalidOptions):
            _TestSchema.validate({"name": 123})
