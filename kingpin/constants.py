import jsonschema

from kingpin.actors import exceptions


class REQUIRED(object):
    """Meta class to identify required arguments for actors."""


class StringCompareBase(object):
    """Meta class to identify the desired state for a resource.

    This basic type of constant allows someone to easily define a set of valid
    strings for their option and have the base actor class automatically
    validate the inputs against those strings.
    """

    valid = None

    @classmethod
    def validate(self, option):
        if option not in self.valid:
            raise exceptions.InvalidOptions(
                "%s not valid, use: %s" % (option, self.valid)
            )


class STATE(StringCompareBase):
    """Meta class to identify the desired state for a resource.

    Simple tester for 'present' or 'absent' on actors. Used for any actor thats
    idempotent and used to ensure some state of a resource.
    """

    valid = ("present", "absent")


class SchemaCompareBase(object):
    """Meta class that compares the schema of a dict against rules."""

    SCHEMA = None

    @classmethod
    def validate(self, option):
        try:
            jsonschema.Draft4Validator(self.SCHEMA).validate(option)
        except jsonschema.exceptions.ValidationError as e:
            raise exceptions.InvalidOptions(
                "Supplied parameter does not match schema: %s" % e
            )
