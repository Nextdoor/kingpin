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

"""
:mod:`kingpin.actors.spotinst`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The Spotinst package allows you to create, manage and destroy Spotinst
ElastiGroups.

https://spotinst.atlassian.net/wiki/display/API/API+Semantics

**Environment Variables**

:SPOTINST_DEBUG:
  If set, then every single response body from Spotinst will be printed out in
  the debug logs for Kingpin. This can include credentials, and can be
  extremely verbose, so use with caution.

:SPOINST_TOKEN:
  SpotInst API Token generated at
  https://console.spotinst.com/#/settings/tokens
"""

import base64
import copy
import logging
import os
import json

from tornado import gen
from tornado import httpclient
from tornado_rest_client import api

from kingpin import utils
from kingpin import exceptions as kingpin_exceptions
from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.actors.utils import dry
from kingpin.constants import REQUIRED
from kingpin.constants import SchemaCompareBase

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'

DEBUG = os.getenv('SPOTINST_DEBUG', False)
TOKEN = os.getenv('SPOTINST_TOKEN', None)


class SpotinstAPI(api.RestConsumer):

    ENDPOINT = 'https://api.spotinst.io/'
    CONFIG = {
        'attrs': {
            'aws': {
                'attrs': {
                    'ec2': {
                        'attrs': {
                            'list_groups': {
                                'path': 'aws/ec2/group',
                                'http_methods': {'get': {}}
                            },
                            'create_group': {
                                'path': 'aws/ec2/group',
                                'http_methods': {'post': {}}
                            },
                            'list_group': {
                                'path': 'aws/ec2/group/%id%',
                                'http_methods': {'get': {}}
                            },
                            'update_group': {
                                'path': 'aws/ec2/group/%id%',
                                'http_methods': {'put': {}}
                            },
                            'delete_group': {
                                'path': 'aws/ec2/group/%id%',
                                'http_methods': {'delete': {}}
                            },
                            'group_status': {
                                'path': 'aws/ec2/group/%id%',
                                'http_methods': {'get': {}}
                            },
                            'validate_group': {
                                'path': 'aws/ec2/group/validation',
                                'http_methods': {'post': {}}
                            }
                        }
                    }
                }
            }
        }
    }


class SpotinstException(exceptions.RecoverableActorFailure):

    """Base SpotInst exception handler.

    This exception handler parses the Spotinst returned messages when an error
    is thrown. The error message comes back in the body in a JSON formatted
    blob. This exception handler will parse out the exception message, print it
    out in a semi-readable log form for the user, and then store it in the
    Exception body.

    See https://spotinst.atlassian.net/wiki/display/API/API+Semantics
    for more details.
    """

    def __init__(self, e):
        msg = self._parse(e)
        Exception.__init__(self, msg)
        self.exc = e

    def _parse(self, e):
        """Reads through a SpotInst error message body and parses it.

        This method looks for a proper error message(s) from Spotinst in the
        response body, parses them into something more humanly readable, and
        then logs them out. It also adds them to the exception message so that
        you get something beyond '400 Bad Request'.
        """
        log = logging.getLogger('%s.%s' % (self.__module__,
                                           self.__class__.__name__))
        try:
            error = json.loads(e.response.body)
        except AttributeError:
            return 'Unknown error: %s' % e

        msg_id = ('Request ID (%s) %s %s' % (error['request']['id'],
                                             error['request']['method'],
                                             error['request']['url']))
        log.error('Error on %s' % msg_id)

        if 'error' in error['response']:
            return 'Spotinst %s: %s' % (msg_id, error['response']['error'])

        if 'errors' in error['response']:
            msgs = []
            for err in error['response']['errors']:
                msg = '%s: %s' % (err['code'], err['message'])
                msgs.append(msg)
                log.error(msg)
            return 'Spotinst %s: %s' % (msg_id, ', '.join(msgs))

        # Fallback if we don't know what kind of error body this is
        error_str = ('Spotinst %s: %s' % (msg_id, error['response']))
        return error_str


class InvalidConfig(SpotinstException):

    """Thrown when an invalid request was supplied to Spotinst"""


class SpotinstRestClient(api.RestClient):

    EXCEPTIONS = {
        httpclient.HTTPError: {
            '400': InvalidConfig,
            '401': exceptions.InvalidCredentials,
            '403': exceptions.InvalidCredentials,
            '500': None,
            '502': None,
            '503': None,
            '504': None,

            # Represents a standard HTTP Timeout
            '599': None,

            '': exceptions.BadRequest,
        }
    }


class ElastiGroupSchema(SchemaCompareBase):

    """Light validation against the Spotinst ElastiGroup schema.

    For full description of the JSON data format, please see:
    https://spotinst.atlassian.net/wiki/display/API/Create+Group#CreateGroup-JF

    This schema handles the following validation cases:

    * Only allow a single `SubnetID` for each `availabilityZone` object.
    * Disallow `t2|i2|hc1` instance types for the `spot` instance section.
    * Ensure that the `scaling.up` and `scaling.down` arrays are either `null`
      or contain at least **1** record.
    """
    SCHEMA = {
        'type': 'object',
        'additionalProperties': True,
        'required': ['group'],
        'properties': {
            'group': {
                'type': 'object',
                'properties': {
                    'compute': {
                        'type': 'object',
                        'properties': {
                            'availabilityZones': {
                                'type': 'array',
                                'uniqueItems': True,
                                'items': {
                                    'type': 'object',
                                    'required': ['name', 'subnetId'],
                                    'additionalProperties': False,
                                    'properties': {
                                        'name': {'type': 'string'},
                                        'subnetId': {'type': 'string'}
                                    }
                                }
                            },
                            'instanceTypes': {
                                'type': 'object',
                                'properties': {
                                    'spot': {
                                        'type': 'array',
                                        'additionalItems': False,
                                        'items': {
                                            'type': 'string',
                                            'not': {
                                                'pattern': '^t2|i2|hc1'
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    },
                    'scaling': {
                        'type': 'object',
                        'additionalProperties': False,
                        'properties': {
                            'up': {
                                'type': ['null', 'array'],
                                'minItems': 1
                            },
                            'down': {
                                'type': ['null', 'array'],
                                'minItems': 1
                            },
                        }
                    }
                }
            }
        }
    }


class SpotinstBase(base.EnsurableBaseActor):

    """Simple Spotinst Abstract Base Object"""

    def __init__(self, *args, **kwargs):
        super(SpotinstBase, self).__init__(*args, **kwargs)

        if not TOKEN:
            raise exceptions.InvalidCredentials(
                'Missing the "SPOTINST_TOKEN" environment variable.')

        if not DEBUG:
            logging.getLogger('tornado_rest_client.api').setLevel('INFO')

        rest_client = SpotinstRestClient(
            headers={
                'Authorization': 'Bearer %s' % TOKEN,
                'Content-Type': 'application/json',
            })
        self._client = SpotinstAPI(client=rest_client)


class ElastiGroup(SpotinstBase):

    """Manages an ElastiGroup in Spotinst.

    `Spotinst ElastiGroups
    <https://spotinst.com/products/workload-management/elastigroup/>`_ act as
    smarter EC2 AutoScalingGroups that scale up and down leveraging Amazon Spot
    instances wherever possible. These ElastiGroups are completely configurable
    through a `JSON Blob
    <https://spotinst.atlassian.net/wiki/display/API/Create+Group>`_.

    For a fully functional example JSON config, see :download:`this one
    <../examples/test/spotinst.elastigroup/unittest.json>`. You can also write
    your files in YAML if you prefer -- Kingpin will handle the conversion.

    **UserData Startup Script**

    The Spotinst API wants the instances UserData script to be supplied as
    a Base64-encoded string -- which you can do if you wish. However, there is
    no need, as Kingpin will automatically convert your plain-text script into
    a Base64 blob for you behind the scenes.

    **Known Limitations**

    * At this time, this actor only makes changes to ElastiGroups or
      creates/deletes them. It does not trigger rolling changes, or wait until
      instances have launched or terminated before returning.

    * The Spotinst API does not allow you to change an ElastiGroup scaling
      'unit' (ie, CPU Count or Instance Count). You can also not change an
      ElastiGroup's basic platform (ie, VPC Linux vs Non VPC Linux). We warn
      about this on each change.

    **Options**

    :name:
      The desired name of the ElastiGroup. Note that this will override
      whatever value is inside your configuration JSON/YAML blob.

    :config:
      Path to the ElastiGroup configuration blob (JSON or YAML) file.
      :ref:`token_replacement` can be used inside of your configuration files
      allowing environment variables to replace `%VAR%` strings.

      This file will be checked against a light-schema defined in
      :py:class:`ElastiGroupSchema` before any authentication is required. The
      file will be further validated against the Spotinst API during the DRY
      run, but this requires authentication.

    **Examples**

    .. code-block:: json

      { "actor": "spotinst.ElastiGroup",
        "options": {
          "name": "my-group",
          "config": "./group_config.json",
        }
      }

    **Dry Mode**

    Will discover the current state of the ElastiGroup (*present*, *absent*),
    and whether or not the current configuration is different than the desired
    configuration. Will also validate the desired configuration against the
    SpostInst API to give you a heads up about any potential failures up
    front.
    """

    all_options = {
        'name': (
            str, REQUIRED, 'Name of the ElastiGroup to manage'),
        'config': (
            str, None, 'Name of the file with the ElastiGroup config')
    }
    unmanaged_options = ['name']

    desc = 'ElastiGroup {name}'

    def __init__(self, *args, **kwargs):
        super(ElastiGroup, self).__init__(*args, **kwargs)

        # Parse the user-supplied ElastiGroup config, swap in any tokens, etc.
        self._config = self._parse_group_config()

        # Filld in later by self._precache()
        self._group = None

    def _parse_group_config(self):
        """Parses the ElastiGroup config and replaces tokens.

        Reads through the supplied ElastiGroup configuration JSON blob (or
        YAML!), replaces any tokens that need replacement, and then sanity
        checks it against our schema.

        Note, contextual tokens (which are evaluated at run time, not
        compilation time) are not included here. Instead, those will be
        evaluated in the self._precache() method.
        """
        config = self.option('config')

        if config is None:
            return None

        self.log.debug('Parsing and validating %s' % config)

        try:
            parsed = utils.convert_script_to_dict(
                script_file=config, tokens=self._init_tokens)
        except (kingpin_exceptions.InvalidScript, LookupError) as e:
            raise exceptions.InvalidOptions(
                'Error parsing %s: %s' % (config, e))

        # The userData portion of the body data needs to be Base64 encoded if
        # its not already. We will try to decode whatever is there, and if it
        # fails, we assume its raw text and we encode it.
        orig_data = (parsed['group']['compute']
                     ['launchSpecification']['userData'])
        try:
            base64.b64decode(orig_data)
        except TypeError:
            new = base64.b64encode(orig_data)
            parsed['group']['compute']['launchSpecification']['userData'] = new

        # Ensure that the name of the ElastiGroup in the config file matches
        # the name that was supplied to the actor -- or overwrite it.
        parsed['group']['name'] = self.option('name')

        # Now run the configuration through the schema validator
        ElastiGroupSchema.validate(parsed)

        return parsed

    @gen.coroutine
    def _list_groups(self):
        """Returns a list of all ElastiGroups in your Spotinst acct.

        Returns:
            [List of JSON ElastiGroup objects]
        """
        resp = yield self._client.aws.ec2.list_groups.http_get()
        raise gen.Return(resp['response']['items'])

    @gen.coroutine
    def _get_group(self):
        """Finds and returns the existing ElastiGroup configuration.

        If the ElastiGroup exists, it returns the configuration for the group.
        If the group is missing, it returns None. Used by the self._precache()
        method to determine whether or not the desired ElastiGroup already
        exists or not, and what its configuration looks like.

        *Note: Depends on self._precache() being run*

        Returns:
          A dictionary with the ElastiGroup configuration returned by Spotinst
          or None if no matching group is found.

        Raises:
          exceptions.InvalidOptions: If too many groups are returned.
        """
        all_groups = yield self._list_groups()
        if not all_groups:
            raise gen.Return(None)

        matching = [
            group for group in all_groups
            if group['name'] == self.option('name')]

        if len(matching) > 1:
            raise exceptions.InvalidOptions(
                'Found more than one ElastiGroup with the name %s - '
                'this actor cannot manage multiple groups with the same'
                'name, you must use a unique name for each group.'
                % self.option('name'))

        if len(matching) < 1:
            raise gen.Return(None)

        match = matching[0]
        self.log.debug('Found ElastiGroup %s' % match['id'])
        raise gen.Return({'group': match})

    @gen.coroutine
    def _validate_group(self):
        """Basic Schema validation of the Elastigroup config.

        This endpoint is not documented, but it performs the most basic schema
        validation of the supplied ElastiGroup config. It cannot verify that
        instances will truly launch, but it can help catch obvious errors.

        It does require authentication, which is sad.
        """
        yield self._client.aws.ec2.validate_group.http_post(
            group=self._config['group'])

    @gen.coroutine
    def _precache(self):
        """Pre-populate a bunch of data.

        Searches for the list of ElastiGroups and stores the existing
        configuration for an ElastiGroup if it matches the name of the one
        we're managing here.

        Attempts light schema-validation of the desired ElastiGroup config to
        try to catch errors early in the Dry run.
        """
        self._group = yield self._get_group()
        yield self._validate_group()

    @gen.coroutine
    def _get_state(self):
        if self._group:
            raise gen.Return('present')

        raise gen.Return('absent')

    @gen.coroutine
    def _set_state(self):
        if self.option('state') == 'absent' and self._group:
            yield self._delete_group(id=self._group['group']['id'])
        elif self.option('state') == 'present':
            yield self._create_group()

    @gen.coroutine
    @dry('Would have created ElastiGroup')
    def _create_group(self):
        self.log.info('Creating ElastiGroup %s' % self.option('name'))
        yield self._client.aws.ec2.create_group.http_post(
            group=self._config['group'])

    @gen.coroutine
    @dry('Would have deleted ElastiGroup {id}')
    def _delete_group(self, id):
        self.log.info('Deleting ElastiGroup %s' % id)
        yield self._client.aws.ec2.delete_group(id=id).http_delete()

    @gen.coroutine
    def _compare_config(self):
        # For the purpose of comparing the two configuration dicts, we need to
        # modify them (below).. so first lets copy them so we don't modify the
        # originals.
        new = copy.deepcopy(self._config)
        existing = copy.deepcopy(self._group)

        # Strip out some of the Spotinst generated and managed fields that
        # should never end up in either our new or existing configs.
        for field in ('id', 'createdAt', 'updatedAt'):
            new['group'].pop(field, None)
            existing['group'].pop(field, None)

        # We only allow a user to supply a single subnetId for each AZ (this is
        # handled by the ElastiGroupSchema). Spotinst returns back though both
        # the original setting, as well as a list of subnetIds. We purge that
        # from our comparison here.
        for az in existing['group']['compute']['availabilityZones']:
            az.pop('subnetIds', None)

        diff = utils.diff_dicts(existing, new)

        if diff:
            self.log.warning('Group configurations do not match')
            for line in diff.split('\n'):
                self.log.info('Diff: %s' % line)
            return False

        return True

    @gen.coroutine
    def _get_config(self):
        """Not really used, but a stub for correctness"""
        raise gen.Return(self._group)

    @gen.coroutine
    @dry('Would have updated ElastiGroup config')
    def _set_config(self):
        group_id = self._group['group']['id']
        self.log.info('Updating ElastiGroup %s' % group_id)

        # There are certain fields that simply cannot be updated -- strip them
        # out. We have a warning up in the above _compare_config() section that
        # will tell the user about this in a dry run.
        if 'capacity' in self._config['group']:
            self.log.warning(
                'Note: Ignoring the group[capacity][unit] setting.')
            self._config['group']['capacity'].pop('unit', None)
        if 'compute' in self._config['group']:
            self.log.warning(
                'Note: Ignoring the group[compute][unit] setting.')
            self._config['group']['compute'].pop('product', None)

        # Now do the update and capture the results. Once we have them, we'll
        # store the updated group configuration.
        ret = yield self._client.aws.ec2.update_group(id=group_id).http_put(
            group=self._config['group'])
        self._group = ret['response']['items'][0]
