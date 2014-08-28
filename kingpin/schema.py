import jsonschema

SCHEMA_1_0 = {
    'type': 'object',
    'required': ['actor', 'desc', 'options'],
    'additionalProperties': False,
    'properties': {
        'desc': {'type': 'string'},
        'actor': {'type': 'string'},
        'options': {
            # 'Options' are Actor specific. However, we validate some internal
            # option types here, if they are supplied.
            'type': 'object',

            # Since options are actor specific, ignore unexpected options.
            'additionalProperties': True,

            # Internally expected properties
            'properties': {
                # 'acts' are lists of actors that should be instantiated. Each
                # object should look like this actual schema (with a desc,
                # actor and option key)
                'acts': {
                    'type': 'array',
                    'items': {'oneOf': [
                        # This is a reference to 'self' ... in other words,
                        # this array can only contain other SCHEMA_1_0 type
                        # objets.
                        {'$ref': '#'},
                    ]},
                },
            },
        },
    }
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
    return jsonschema.validate(config, SCHEMA_1_0)
