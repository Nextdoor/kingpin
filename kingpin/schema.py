import jsonschema

from kingpin import exceptions

__author__ = "Matt Wise <matt@nextdoor.com>"


ACTOR_SCHEMA = {
    "type": ["object"],
    "required": ["actor"],
    "additionalProperties": False,
    "properties": {
        "desc": {"type": "string"},
        "actor": {"type": "string"},
        "options": {
            # 'Options' are Actor specific. However, we validate some internal
            # option types here, if they are supplied.
            "type": "object",
            # Since options are actor specific, ignore unexpected options.
            "additionalProperties": True,
            # Internally expected properties
            "properties": {
                # 'acts' are lists of actors that should be instantiated. Each
                # object should look like this actual schema (with a desc,
                # actor and option key)
                "acts": {
                    "type": "array",
                    # This is a reference to 'self' ... in other words,
                    # this array can only contain other SCHEMA_1_0 type
                    # objets.
                    "items": {"$ref": "#"},
                },
            },
        },
        # Not required. In code, will default to False.
        "warn_on_failure": {"type": ["boolean", "string"]},
        # Not required. In code, will default to <actor>.default_timeout
        "timeout": {"type": ["string", "integer", "number"]},
        # Optional conditional to indicate to skip this actor.
        "condition": {"type": ["boolean", "string"], "default": True},
    },
}

SCHEMA_1_0 = {
    "definitions": {"actor": ACTOR_SCHEMA},
    "anyOf": [
        {"$ref": "#/definitions/actor"},
        {"type": "array", "items": {"$ref": "#/definitions/actor"}},
    ],
}


def validate(config):
    """Validates the JSON against our schemas.

    TODO: Support multiple schema versions

    Args:
        config: Dictionary of parsed JSON

    Returns:
        None: if all is well

    Raises:
        Execption if something went wrong.
    """
    try:
        return jsonschema.validate(config, SCHEMA_1_0)
    except jsonschema.exceptions.ValidationError as e:
        raise exceptions.InvalidScript(e)
