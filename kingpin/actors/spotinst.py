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
# Copyright 2018 Nextdoor.com, Inc

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

:SPOTINST_ACCOUNT_ID:
  SpotInst API Account ID - this is required unless you set the account_id
  parameter on each individual actor call.
  http://docs.spotinst.com/#page:api-semantic,header:header-organizations-with-a-single-account
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
ACCOUNT_ID = os.getenv('SPOTINST_ACCOUNT_ID', None)


class SpotinstAPI(api.RestConsumer):

    ENDPOINT = 'https://api.spotinst.io/'
    CONFIG = {
        'attrs': {
            'aws': {
                'new': True,
                'attrs': {
                    'ec2': {
                        'new': True,
                        'attrs': {
                            'list_groups': {
                                'new': True,
                                'path': 'aws/ec2/group?accountId=%account_id%',
                                'http_methods': {'get': {}}
                            },
                            'create_group': {
                                'new': True,
                                'path': 'aws/ec2/group?accountId=%account_id%',
                                'http_methods': {'post': {}}
                            },
                            'list_group': {
                                'path': 'aws/ec2/group/%id%?accountId=%account_id%',  # nopep8
                                'http_methods': {'get': {}}
                            },
                            'update_group': {
                                'path': 'aws/ec2/group/%id%?accountId=%account_id%',  # nopep8
                                'http_methods': {'put': {}}
                            },
                            'delete_group': {
                                'path': 'aws/ec2/group/%id%?accountId=%account_id%',  # nopep8
                                'http_methods': {'delete': {}}
                            },
                            'group_status': {
                                'path': 'aws/ec2/group/%id%/status?accountId=%account_id%',  # nopep8
                                'http_methods': {'get': {}}
                            },
                            'validate_group': {
                                'new': True,
                                'path': 'aws/ec2/group/validation?accountId=%account_id%',  # nopep8
                                'http_methods': {'post': {}}
                            },
                            'roll': {
                                'path': 'aws/ec2/group/%id%/roll?limit=50&accountId=%account_id%',  # nopep8
                                'http_methods': {'put': {}, 'get': {}}
                            },
                            'roll_status': {
                                'path': 'aws/ec2/group/%id%/roll/%roll_id%?accountId=%account_id%',  # nopep8
                                'http_methods': {'get': {}}
                            },
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

    JSON_BODY = True

    TIMEOUT = 60


class ElastiGroupSchema(SchemaCompareBase):

    """Light validation against the Spotinst ElastiGroup schema.

    For full description of the JSON data format, please see:
    https://spotinst.atlassian.net/wiki/display/API/Create+Group#CreateGroup-JF

    This schema handles the following validation cases:

    * Only allow a single `SubnetID` for each `availabilityZone` object.
    * Disallow `t2|hc1` instance types for the `spot` instance section.
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
                                                'pattern': '^t2|hc1'
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    },
                    'scaling': {
                        'type': ['object', 'null'],
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

        # Figure out our account ID and set it.. Or this will end up falling
        # back to None if neither are set.
        account_id = self._options.get('account_id')
        if account_id is None:
            account_id = ACCOUNT_ID

        if account_id is None:
            raise exceptions.InvalidCredentials(
                'Missing SPOTINST_ACCOUNT_ID or account_id parameter')

        rest_client = SpotinstRestClient(
            headers={
                'Authorization': 'Bearer %s' % TOKEN,
                'Content-Type': 'application/json',
            })

        self._client = SpotinstAPI(client=rest_client, account_id=account_id)


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

    **Rolling out Group Changes**

    We will trigger the "roll group" API if the `roll_on_change` parameter is
    set to `True` after any change to an ElastiGroup. It is difficult to know
    which changes may or may not require a replacement of your existing hosts,
    so we leave this up to the user to decide on the behavior.

    **Known Limitations**

    * The Spotinst API does not allow you to change an ElastiGroup scaling
      'unit' (ie, CPU Count or Instance Count). You can also not change an
      ElastiGroup's basic platform (ie, VPC Linux vs Non VPC Linux). We warn
      about this on each change.

    **Options**

    :name:
      The desired name of the ElastiGroup. Note that this will override
      whatever value is inside your configuration JSON/YAML blob.

    :account_id:
      The SpotInst Account ID that the action is taking place in - this
      overrides the SPOTINST_ACCOUNT_ID environment variable (if its set).

    :config:
      Path to the ElastiGroup configuration blob (JSON or YAML) file.
      :ref:`token_replacement` can be used inside of your configuration files
      allowing environment variables to replace `%VAR%` strings.

      This file will be checked against a light-schema defined in
      :py:class:`ElastiGroupSchema` before any authentication is required. The
      file will be further validated against the Spotinst API during the DRY
      run, but this requires authentication.

    :tokens:
      A dict of key/value pairs that can be used to swap in variables into a
      common ElastiGroup template. These are added to (and override) the
      Environment variables that Kingpin already uses for variables swapping
      (as described in the :ref:`token_replacement` section.

    :roll_on_change:
      Whether or not to forcefully roll out changes to the ElastiGroup. If
      `True`, we will issue a 'roll call' to SpotInst and trigger all of the
      instances to be replaced. Defaults to `False`.

    :roll_batch_size:
      Indicates in percentage the amount of instances should be replaced in
      each batch. Defaults to `20`.

    :roll_grace_period:
      Indicates in seconds the timeout to wait until instance become healthy in
      the ELB. Defaults to `600`.

    :wait_on_create:
      If set to `True`, Kingpin will loop until the ElastiGroup has fully
      launched -- this only applies if the group is being created from scratch.
      On updates, see the `wait_on_roll` setting below.
      Defaults to `False`.

    :wait_on_roll:
      If set to `True`, Kingpin will loop until the rollout of any changes has
      completed. This can take a long time, depending on your rollout settings.
      Defaults to `False`.

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
        'account_id': (
            str, None, 'SpotInst Account ID'),
        'config': (
            str, None, 'Name of the file with the ElastiGroup config'),
        'tokens': (
            dict, {}, ('A flat dictionary of Key/Value pairs that can be '
                       'swapped into the ElastiGroup template.')),
        'roll_on_change': (
            bool, False,
            ('Roll out new instances upon any config change.')),
        'roll_batch_size': (
            (str, int), 20,
            ('Indicates in percentage the amount of instances should be'
             'replaced in each batch.')),
        'roll_grace_period': (
            (str, int), 600,
            ('Indicates in seconds the timeout to wait until instance become'
             'healthy in the ELB.')),
        'wait_on_create': (
            bool, False, 'Wait for the ElastiGroup to startup and stabalize'),
        'wait_on_roll': (
            bool, False, 'Wait on any changes to roll out to the nodes'),
    }
    unmanaged_options = ['name', 'account_id', 'wait_on_roll',
                         'wait_on_create', 'roll_on_change', 'roll_batch_size',
                         'roll_grace_period', 'tokens']

    desc = 'ElastiGroup {name}'

    def __init__(self, *args, **kwargs):
        super(ElastiGroup, self).__init__(*args, **kwargs)

        # Quickly make sure that the roll_batch_size and roll_grace_period are
        # integers...
        for key in ('roll_batch_size', 'roll_grace_period'):
            try:
                self._options[key] = int(self._options[key])
            except ValueError:
                raise exceptions.InvalidOptions(
                    '%s (%s) must be an integer' % (key, self._options[key]))

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

        # Join the init_tokens the class was instantiated with and the explicit
        # tokens that the user supplied.
        tokens = dict(self._init_tokens)
        tokens.update(self.option('tokens'))

        try:
            parsed = utils.convert_script_to_dict(
                script_file=config, tokens=tokens)
        except (kingpin_exceptions.InvalidScript, LookupError) as e:
            raise exceptions.InvalidOptions(
                'Error parsing %s: %s' % (config, e))

        # The userData portion of the body data needs to be Base64 encoded if
        # its not already. We will try to decode whatever is there, and if it
        # fails, we assume its raw text and we encode it.
        orig_data = (parsed['group']['compute']
                     ['launchSpecification']['userData'])
        new = base64.b64encode(orig_data.encode("utf-8"))
        parsed['group']['compute']['launchSpecification']['userData'] = new

        # Ensure that the name of the ElastiGroup in the config file matches
        # the name that was supplied to the actor -- or overwrite it.
        parsed['group']['name'] = self.option('name')

        # Now run the configuration through the schema validator
        ElastiGroupSchema.validate(parsed)

        return parsed

    @gen.coroutine
    def _precache(self):
        """Pre-populate a bunch of data.

        Searches for the list of ElastiGroups and stores the existing
        configuration for an ElastiGroup if it matches the name of the one
        we're managing here.

        Attempts light schema-validation of the desired ElastiGroup config to
        try to catch errors early in the Dry run.
        """
        # Check if the desired ElastiGroup already exists or not -- if it does,
        # store its configuration here for comparison purposes.
        self._group = yield self._get_group()

        # Validate the desired ElastiGroup configuration against the
        # schema-checker... light validation, but useful.
        yield self._validate_group()

        # Note - we don't manage the ElastiGroup target size. If the group
        # exists and has a target size set, we override the user-supplied
        # target number with the value returned to us by Spotinst.
        if self._group and 'capacity' in self._group['group']:
            target = self._group['group']['capacity']['target']
            self.log.info('Using the Spotinst supplied [capacity][target]'
                          ' value: %s' % target)
            self._config['group']['capacity']['target'] = target

    @gen.coroutine
    def _list_groups(self):
        """Returns a list of all ElastiGroups in your Spotinst acct.

        Returns:
            [List of JSON ElastiGroup objects]
        """
        raw = yield self._client.aws.ec2.list_groups.http_get()
        resp = raw.get('response', {})
        items = resp.get('items', [])
        raise gen.Return(items)

    @gen.coroutine
    def _get_group(self):
        """Finds and returns the existing ElastiGroup configuration.

        If the ElastiGroup exists, it returns the configuration for the group.
        If the group is missing, it returns None. Used by the self._precache()
        method to determine whether or not the desired ElastiGroup already
        exists or not, and what its configuration looks like.

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
            self.log.debug('Did not find an existing ElastiGroup')
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

        Raises:
            SpotinstException: If any known Spotinst style error comes back.
        """
        yield self._client.aws.ec2.validate_group.http_post(
            group=self._config['group'])

    @gen.coroutine
    def _get_state(self):
        """Validates whether or not a matching ElastiGroup already exists.

        Depends on the self._precache() method having been called. If it has,
        then self._group should be populated if the group exists, or None if it
        doesn't.

        Returns:
            present: If the group exists
            absent: If not
        """
        if self._group:
            raise gen.Return('present')

        raise gen.Return('absent')

    @gen.coroutine
    def _set_state(self):
        """Creates or Deletes the ElastiGroup

        If the desired state is absent adn the group exists, we trigger a
        delete_group call. If the desired state is present and the group does
        not exist, we trigger a group create call. In any other situation, we
        do nothing because the desired and current states match.
        """
        if self.option('state') == 'absent' and self._group:
            yield self._delete_group(id=self._group['group']['id'])
        elif self.option('state') == 'present':
            yield self._create_group()

            # You'd think that we could store the returned group config from
            # Spotinst .. but it turns out that the data returned in the
            # create_group call above is not the same as what we've uploaded.
            # Instead, we have to re-call the self._precache() method to make
            # sure that we get an updated group config.
            # self._group = {'group': ret['response']['items'][0]}
            self._group = yield self._get_group()

            # Optionally, wait until the nodes have booted up before returning.
            if self.option('wait_on_create'):
                yield self._wait_until_stable()

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
    def _get_group_status(self, id):
        self.log.debug('Getting ElastiGroup %s status...' % id)
        ret = yield self._client.aws.ec2.group_status(id=id).http_get()
        raise gen.Return(ret)

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
                'Note: Ignoring the group[compute][product] setting.')
            self._config['group']['compute'].pop('product', None)

        # Now do the update and capture the results. Once we have them, we'll
        # store the updated group configuration.
        ret = yield self._client.aws.ec2.update_group(id=group_id).http_put(
            group=self._config['group'])
        self._group = {'group': ret['response']['items'][0]}

        # If we're supposed to roll the group on any config changes, begin now
        if self.option('roll_on_change'):
            yield self._roll_group()

    @gen.coroutine
    def _compare_config(self):
        """Smart-ish comparison of Spotinst config to our own.

        This method is called by the EnsurableBaseClass to compare the desired
        (local) config with the existing (remote) config of the ElastiGroup.
        A simple == comparison will not work because there are additional
        fields returned by the Spotinst API (id, createdAt, updatedAt, and
        more) that will never be in the desired configuration object.

        This method makes copies of the configuration objects, strips out the
        fields that we cannot compare against, and then diffs. If a diff is
        detected, it logs out the diff for the end user, and then returns
        False.

        Returns:
            True: the configs match
            False: the configs do not match
        """
        # For the purpose of comparing the two configuration dicts, we need to
        # modify them (below).. so first lets copy them so we don't modify the
        # originals.
        new = copy.deepcopy(self._config)
        existing = copy.deepcopy(self._group)

        # If existing is none, then return .. there is no point in diffing the
        # config if the group doesn't exist! Note, this really only happens in
        # a dry run where we're creating the group because the group
        if existing is None:
            raise gen.Return(True)

        # Strip out some of the Spotinst generated and managed fields that
        # should never end up in either our new or existing configs.
        for field in ('id', 'createdAt', 'updatedAt', 'userData'):
            for g in (new, existing):
                g['group'].pop(field, None)

        # Decode both of the userData fields so we can actually see the
        # userdata differences.
        for config in (new, existing):
            config['group']['compute']['launchSpecification']['userData'] = (
                base64.b64decode(config['group']['compute']
                                 ['launchSpecification']['userData']))

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
    @dry('Would have rolled the ElastiGroup..')
    def _roll_group(self, delay=30):
        """Triggers an ElastiGroup rolling operation and waits for completion.

        Sends a signal to Spotinst to "roll" (replace) the nodes in the
        ElastiGroup based on the new configuration. This operation takes a
        while based on the `roll_batch_size` and `roll_grace_period` options.
        Depending on the `wait_on_roll` option, this method will wait until the
        roll has completed before returning.
        """
        group_id = self._group['group']['id']

        # You are not allowed to have two rolls happening at the same time --
        # so if there is already a roll in progress, we need to wait before we
        # issue another one. This is a requirement regardless of whether the
        # user has asked us to 'wait_on_roll' or not, because we'll get an
        # exception back from the API if we try to issue a roll call during an
        # existing roll operation.
        yield self._wait_until_roll_complete(delay)

        # Now, try to do the roll...
        self.log.info('Triggering an ElastiGroup roll')
        yield self._client.aws.ec2.roll(id=group_id).http_put(
            batchSizePercentage=self.option('roll_batch_size'),
            gracePeriod=self.option('roll_grace_period'))

        # Now, if the user wants us to wait, we will wait.
        if self.option('wait_on_roll'):
            yield self._wait_until_roll_complete(delay)

    @gen.coroutine
    @dry('Would have waited for ElastiGroup changes to become active')
    def _wait_until_roll_complete(self, delay):
        """Poll and wait until an ElastiGroup roll is complete.
        """
        group_id = self._group['group']['id']

        # Note: We do not use the repeating_log because we only call this API
        # every 30s or so. Rolling out group changes is almost guaranteed to be
        # a very slow process, so there is no need to make frequent API calls
        # to constantly check the status of the rollout. Instead, we make calls
        # infrequently and thus we are able to simply log out the status after
        # each call.
        self.log.info('Checking if any ElastiGroup rolls are in progress..')
        while True:
            response = yield self._client.aws.ec2.roll(id=group_id).http_get()

            in_progress = [r for r in response['response']['items']
                           if r['status'] != 'finished']

            if len(in_progress) < 1:
                break

            status = in_progress[0]['status']
            unit = in_progress[0]['progress']['unit']
            progress = in_progress[0]['progress']['value']

            self.log.info('Group roll is %s %s complete (%s)' % (progress,
                                                                 unit, status))

            yield gen.sleep(delay)

    @gen.coroutine
    @dry('Would have waited for all ElastiGroup nodes to launch')
    def _wait_until_stable(self, delay=3):
        """Poll and wait until an ElastiGroup has stabalized.

        Upon group creation, most of the instances will be in a "biding" state.
        This method watches the list of instances and waits until they are all
        in the 'fulfilled' state.
        """
        group_id = self._group['group']['id']

        # We use the repeating_log to let the user know we're still monitoring
        # things, while not  flooding them every time we make an API call. We
        # give them a message every 30s, but make an API call every 3 seconds
        # to check the status.
        repeating_log = utils.create_repeating_log(
            self.log.info,
            'Waiting for ElastiGroup to become stable',
            seconds=30)

        while True:
            response = yield self._get_group_status(group_id)

            # Find any nodes that are waiting for spot instance requests to be
            # fulfilled.
            pending = [i for i in response['response']['items']
                       if i['status'] == 'pending-evaluation']
            fulfilled = [i['instanceId'] for i in response['response']['items']
                         if i['status'] == 'fulfilled' and i['instanceId'] is
                         not None]

            if len(pending) < 1:
                self.log.info('All instance requests fulfilled: %s' %
                              ', '.join(fulfilled))
                break

            yield gen.sleep(delay)

        utils.clear_repeating_log(repeating_log)
