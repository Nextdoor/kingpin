# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Copyright 2014 Nextdoor.com, Inc

import jsonschema

from kingpin import exceptions

__author__ = 'Matt Wise <matt@nextdoor.com>'


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

                    # This is a reference to 'self' ... in other words,
                    # this array can only contain other SCHEMA_1_0 type
                    # objets.
                    'items': {'$ref': '#'},
                },
            },
        },

        # Not required. In code, will default to False.
        'warn_on_failure': {'type': 'boolean'},

        # Optional conditional to indicate to skip this actor.
        'condition': {'type': ['boolean', 'string'], 'default': True},
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
    try:
        return jsonschema.validate(config, SCHEMA_1_0)
    except jsonschema.exceptions.ValidationError as e:
        raise exceptions.InvalidJSON(e)
