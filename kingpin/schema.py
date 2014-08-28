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

"""JSON Schema Objects for Kingpin

These JSON Schema objects define the format that we support and expect
JSON deployment definitions to be defined in.

## v1.0 Schema Example

Simple two-stage example that runs synchronously. Each stage has a single
Actor that runs.

    { "desc": "main stage",
      "options" : { "async":false },
      "acts": [
        { "desc": "stage 1", "options": { "async":true }, "acts": [
          { "desc": "copy serverA", "actor": "copy",
            "options": { "source": "template", "dest": "serverA" } }
          ] },

        { "desc": "stage 2", "options": { "async":true }, "acts": [
          { "desc": "copy serverB", "actor": "copy",
            "options": { "source": "template", "dest": "serverB" } }
        ] },
      ]
    }
"""

import jsonschema

__author__ = 'Matt Wise <matt@nextdoor.com>'


ACTOR_SCHEMA = {
    'type': 'object',
    'required': ['desc', 'actor', 'options'],
    'additionalProperties': False,
    'properties': {
        'desc': {'type': 'string'},
        'actor': {'type': 'string'},
        'options': {'type': 'object'},
    },
}


ACT_SCHEMA_1_0 = {
    'definitions': {
        'actor': ACTOR_SCHEMA,
    },

    'type': 'object',
    'required': ['desc', 'acts'],
    'additionalProperties': False,
    'properties': {
        'desc': {'type': 'string'},
        'acts': {'type': 'array',
                 'items': {
                     'oneOf': [
                         {'$ref': '#'},
                         {'$ref': '#definitions/actor'}
                     ]
                 }},
        'options': {
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'async': {'type': 'boolean'},
                'condition': {'type': 'boolean'},
            }
        }
    }
}

SCHEMA = {
    '1.0': ACT_SCHEMA_1_0,
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
    return jsonschema.validate(config, SCHEMA['1.0'])
