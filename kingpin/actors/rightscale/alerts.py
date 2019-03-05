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
:mod:`kingpin.actors.rightscale.alerts`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
"""

import logging

from tornado import gen
import requests

from kingpin.actors import exceptions
from kingpin.actors.utils import dry
from kingpin.actors.rightscale import base
from kingpin.constants import SchemaCompareBase
from kingpin.constants import REQUIRED

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


class InvalidInputs(exceptions.InvalidOptions):

    """Raised when supplied inputs are invalid for a ServerArray."""


class AlertSpecNotFound(exceptions.RecoverableActorFailure):

    """Raised when an Alert Spec could not be found"""


class CreateFailed(exceptions.RecoverableActorFailure):

    """Raised when an Alert Spec could not be created"""


class AlertsBaseActor(base.RightScaleBaseActor):

    """Abstract Alerts Actor that provides some utility methods."""

    @gen.coroutine
    def _find_alert_spec(self, name, subject_href):
        """Search for an AlertSpec by-name and return the resource.

        Note: A non-exact resource match is used below so that we return all of
        the Alert Specs that are matched by name. This method returns the
        resources in a list.

        Args:
            name: RightScale AlertSpec Name
            subject_href: The HREF of the subject this AlertSpec is assigned
              to.

        Return:
            [<rightcale.Resource objects>]
        """
        log.debug('Searching for AlertSpec matching: %s' % name)
        found_spec = yield self._client.find_by_name_and_keys(
            self._client._client.alert_specs, name, exact=False,
            subject_href=subject_href)

        if not found_spec:
            log.debug('AlertSpec matching "%s" could not be found.' % name)
            return

        log.debug('Got AlertSpec: %s' % found_spec)
        raise gen.Return(found_spec)


class Create(AlertsBaseActor):

    """Create a RightScale Alert Spec

    Options match the documentation in RightScale:
    http://reference.rightscale.com/api1.5/resources/ResourceAlertSpecs.html#create

    **Options**

    :array:
      The name of the Server or ServerArray to create the AlertSpec on.

    :strict_array:
      Whether or not to fail if the Server/ServerArray does not exist.
      (default: False)

    :condition:
      The condition (operator) in the condition sentence.
      (`>, >=, <, <=, ==, !=`)

    :description:
      The description of the AlertSpec.
      (*optional*)

    :duration:
      The duration in minutes of the condition sentence.
      (`^\d+$`)

    :escalation_name:
      Escalate to the named alert escalation when the alert is triggered.
      (*optional*)

    :file:
      The RRD path/file_name of the condition sentence.

    :name:
      The name of the AlertSpec.

    :threshold:
      The threshold of the condition sentence.

    :variable:
      The RRD variable of the condition sentence

    :vote_tag:
      Should correspond to a vote tag on a ServerArray if vote to grow or
      shrink.

    :vote_type:
      Vote to grow or shrink a ServerArray when the alert is triggered. Must
      either escalate or vote.
      (`grow` or `shrink`)

    **Examples**

    Create a high network activity alert on my-array:

    .. code-block:: json

       { "desc": "Create high network rx alert",
         "actor": "rightscale.alerts.Create",
         "options": {
           "array": "my-array",
           "strict_array": true,
           "condition": ">",
           "description": "Alert if amount of network data received is high",
           "duration": 180,
           "escalation_name": "Email Engineering",
           "file": "interface/if_octets-eth0",
           "name": "high network rx activity",
           "threshold": "50000000",
           "variable": "rx"
         }
       }

    **Dry Mode**

    In Dry mode this actor *does* validate that the ``array`` array exists.
    If it does not, a `kingpin.actors.rightscale.api.ServerArrayException` is
    thrown. Once that has been validated, the dry mode execution simply logs
    the Alert Spec that it would have created.

    Example *dry* output::

        TODO: Fill this in
    """

    all_options = {
        'array': (str, REQUIRED, 'Name of the ServerArray act on.'),
        'strict_array': (bool, False,
                         ('Whether or not to fail if the  Server/ServerArray ',
                          'does not exist.')),
        'condition': (str, REQUIRED,
                      'The condition (operator) in the condition sentence.'),
        'description': (str, None, 'The description of the AlertSpec.'),
        'duration': ((int, str), REQUIRED,
                     'The duration in minutes of the condition sentence.'),
        'escalation_name': (str, None,
                            ('Escalate to the named alert escalation when the',
                             'alert is triggered. Must either escalate or',
                             'vote.')),
        'file': (str, REQUIRED,
                 'The RRD path/file_name of the condition sentence.'),
        'name': (str, REQUIRED, 'The name of the AlertSpec.'),
        'threshold': (str, REQUIRED,
                      'The threshold of the condition sentence.'),
        'variable': (str, REQUIRED,
                     'The RRD variable of the condition sentence.'),
        'vote_tag': (str, None,
                     ('Should correspond to a vote tag on a ServerArray if ',
                      'vote to grow or shrink.')),
        'vote_type': (str, None,
                      ('Vote to grow or shrink a ServerArray when the alert ',
                       'is triggered. Must either escalate or vote.'))
    }

    def __init__(self, *args, **kwargs):
        """Validate the user-supplied parameters at instantiation time."""
        super(Create, self).__init__(*args, **kwargs)
        # By default, we're strict on our array array validation
        self._array_raise_on = 'notfound'
        self._array_allow_mock = False

        if not self.option('strict_array'):
            self._array_raise_on = None
            self._array_allow_mock = True

        if self.option('vote_type') not in ('grow', 'shrink', None):
            raise exceptions.InvalidOptions(
                'vote_type must be either: grow, shrink, None')

    @gen.coroutine
    def _execute(self):
        # Find the array we're adding an alert spec to. Specifically, we need
        # the servers HREF.
        array = yield self._find_server_arrays(
            self.option('array'),
            raise_on=self._array_raise_on,
            allow_mock=self._array_allow_mock)
        self.log.info('Found %s (%s)' % (array.soul['name'], array.href))

        # Add all of the required parameters to a dictionary
        params = {
            'condition': self.option('condition'),
            'description': self.option('description'),
            'duration': int(self.option('duration')),
            'file': self.option('file'),
            'name': self.option('name'),
            'subject_href': array.href,
            'threshold': self.option('threshold'),
            'variable': self.option('variable'),
        }

        # Generate the RightScale parameters that we need to pass in when
        # creating the alert. The optional parameters should not be passed in
        # if their option value came in as None.
        _optional_params = [
            'description', 'escalation_name', 'vote_tag', 'vote_type'
        ]
        for optional in _optional_params:
            if self.option(optional):
                params[optional] = self.option(optional)

        params = self._generate_rightscale_params('alert_spec', params)
        self.log.debug('Generated params: %s' % params)

        if self._dry:
            # In dry run mode, just log out what we would have done.
            self.log.info('Would have created the alert spec \"%s\" on %s' %
                          (self.option('name'), array.soul['name']))
            raise gen.Return()

        # We're really doin this. If we get a known exception back, handle
        # it. Otherwise, raise it.
        try:
            yield self._client.create_resource(
                self._client._client.alert_specs, params)
            self.log.info('Alert spec has been created')
        except requests.exceptions.HTTPError as e:
            if e.response.status_code in (422, 400):
                msg = ('Invalid parameters supplied to Alert Spec "%s": %s'
                       % (self.option('name'), params))
                raise exceptions.RecoverableActorFailure(msg)
            raise


class Destroy(AlertsBaseActor):

    """Destroy existing RightScale Alert Specs

    This actor searches RightScale for any Alert Specs that match the ``name``
    and ``array`` that you supplied, then deletes all of them. RightScale lets
    you have multiple alert specs with the same name, so if this actor finds
    multiple specs, it will delete them all.

    **Options**

    :array:
      The name of the Server or ServerArray to delete the AlertSpec from.

    :name:
      The name of the AlertSpec.

    **Examples**

    Destroy a high network activity alert on my-array:

    .. code-block:: json

       { "desc": "Destroy high network rx alert",
         "actor": "rightscale.alerts.Destroy",
         "options": {
           "array": "my-array",
           "name": "high network rx activity",
         }
       }

    **Dry Mode**

    In Dry mode this actor *does* validate that the ``array`` array exists,
    and that the AlertSpec exists on that array so that it can be deleted. A
    RecoverableActorFailure error is thrown if it does not exist.

    Example *dry* output::

        14:31:49   INFO      Rehearsing... Break a leg!
        14:31:49   INFO      [DRY: Kingpin] Preparing actors from delete.json
        14:31:53   INFO      [DRY: Destroy high network rx alert] Found
          my-array (/api/server_arrays/329142003) to delete alert spec from
        14:31:54   INFO      [DRY: Destroy high network rx alert] Would have
          deleted the alert spec "high network rx activity" on my-array
    """

    all_options = {
        'array': (str, REQUIRED, 'Name of the ServerArray act on.'),
        'name': (str, REQUIRED, 'The name of the AlertSpec.')
    }

    def __init__(self, *args, **kwargs):
        """Validate the user-supplied parameters at instantiation time."""
        super(Destroy, self).__init__(*args, **kwargs)
        # By default, we're strict on our array validation
        self._array_raise_on = 'notfound'
        self._array_allow_mock = False

    @gen.coroutine
    def _execute(self):
        # Find the array we're adding an alert spec to. Specifically, we need
        # the servers HREF.
        array = yield self._find_server_arrays(
            self.option('array'),
            raise_on=self._array_raise_on,
            allow_mock=self._array_allow_mock)

        self.log.info('Found %s (%s) to delete alert spec from' %
                      (array.soul['name'], array.href))

        # Find the AlertSpec on this server, if it exists.
        alerts = yield self._find_alert_spec(
            self.option('name'), array.href)

        # If we can't find the AlertSpec specific to the subjet array that was
        # supplied, raise an exception and bail.
        if not alerts:
            raise AlertSpecNotFound(
                '"%s" could not be found on %s' %
                (self.option('name'), array.soul['name']))

        # We'll store our 'delete spec' futures in here
        deletes = []

        for spec in alerts:
            log.debug('Found Alert Spec %s' % spec.soul)

            if self._dry:
                # In dry run mode, just log out what we would have done.
                self.log.info('Would have deleted alert \"%s\" (%s) on %s' %
                              (spec.soul['name'],
                               spec.href,
                               array.soul['name']))
            else:
                # We're really doin this!
                self.log.info('Deleting alert \"%s\" (%s) on %s' %
                              (spec.soul['name'],
                               spec.href,
                               array.soul['name']))
                deletes.append(self._client.destroy_resource(spec))

        # Wait for the deletes to finish
        if deletes:
            yield deletes


class AlertSpecSchema(SchemaCompareBase):

    """Provides JSON-Schema based verification of the supplied AlertSpec

    The majority of the schema mirrors the RightScale API:
      http://reference.rightscale.com/api1.5/resources/ResourceAlertSpecs.html#create
    """

    SCHEMA = {
        'type': ['object'],
        'required': [
            'condition', 'duration', 'file', 'name', 'threshold', 'variable'
        ],
        'properties': {
            'condition': {
                'type': 'string',
                'enum': ['>', '>=', '<', '<=', '==', '!=']
            },
            'description': {'type': 'string'},
            'duration': {'type': 'integer'},
            'escalation_name': {'type': 'string'},
            'file': {'type': 'string'},
            'name': {'type': 'string'},
            'threshold': {'type': 'string'},
            'variable': {'type': 'string'},
            'vote_tag': {'type': 'string'},
            'vote_type': {'enum': ['grow', 'shrink']}
        }
    }


class AlertSpecsSchema(SchemaCompareBase):

    """Provides JSON-Schema verification that the supplied input was a list
    of AlertSpecSchemas."""

    SCHEMA = {
        'type': ['array', 'null'],
        'uniqueItems': True,
        'items': {
            'anyOf': [AlertSpecSchema.SCHEMA]
        }
    }


class AlertSpecBase(base.EnsurableRightScaleBaseActor):

    """Extremely simple AlertSpec creation actor.

    This actor isn't really meant to be instantiated on its own -- it provides
    the base functionality though for creating, deleting and updating an
    AlertSpec on a given RightScale resource. The resource can be either a
    Server Array, Server Template, Instance or Deployment.

    **Options**

    :href:
      The RightScale HREF for the resource you wish to apply the Alert Spec to.

    :state:
      (str) Either `present` or `absent`

    :spec:
      A dictionary that conforms to the
      :py:mod:`~kingpin.actors.rightscale.alerts.AlertSpecSchema`.

    **Examples**

    .. code-block:: json

       { "actor": "rightscale.alerts.AlertSpecBase",
         "options": {
           "href": "/api/server_arrays/abcd1234",
           "spec": {
                "name": "Instance Stranded",
                "description": "Alert if an instance enders a stranded",
                "file": "RS/server-failure",
                "variable": "state",
                "condition": "==",
                "threshold": "stranded",
                "duration": 2,
                "escalation_name": "critical"
           }
         }
       }

    """

    all_options = {
        'href': (str, None, 'RightScale Resource HREF to act on'),
        'spec': (AlertSpecSchema, None,
                 'The actual Alert Spec definition itself.')
    }
    unmanaged_options = ['href']
    desc = "AlertSpec: {spec[name]}"

    def __init__(self, *args, **kwargs):
        super(AlertSpecBase, self).__init__(*args, **kwargs)
        self.changed = False

    @gen.coroutine
    def _precache(self):
        name = self.option('spec').get('name')
        href = self.option('href')

        # Generate a fully populated set of parameters by including the href
        # that was supplied to us.
        desired_spec = dict(self.option('spec'))
        desired_spec['subject_href'] = href
        self.desired_params = self._generate_rightscale_params(
            'alert_spec', desired_spec)

        # Search for the existing spec. Even though we do an 'exact' search
        # here, this is kind of misleading. We are searching on multiple keys
        # (name, subject_href) and the find_by_name_and_keys() code isn't smart
        # enough to return a true perfect match on all the keys supplied.
        # Therefore, this MAY return a list with multiple results.
        log.debug('Searching for AlertSpec matching: %s' % name)
        self.existing_spec = yield self._client.find_by_name_and_keys(
            self._client._client.alert_specs, exact=True,
            name=name, subject_href=href)

        # Handle the multiple-result scenario. Since exact=True above, we
        # should never get a list back with a single item, so we'll only focus
        # on the issue of getting back multiple items. Search through the list
        # of items for an _exact_ match on the name.
        if (isinstance(self.existing_spec, list) and
                len(self.existing_spec) > 1):
            self.existing_spec = [
                s for s in self.existing_spec if
                s.soul['name'] == self.option('spec')['name']][0]

        if not self.existing_spec:
            log.debug('AlertSpec matching "%s" could not be found.' % name)
            self.existing_spec = None
        else:
            log.debug('Got AlertSpec: %s' % self.existing_spec)

    @gen.coroutine
    def _get_state(self):
        if self.existing_spec:
            raise gen.Return('present')
        raise gen.Return('absent')

    @gen.coroutine
    def _set_state(self):
        if self.option('state') == 'absent':
            yield self._delete_spec()
        else:
            yield self._create_spec()

        self.changed = True

    @gen.coroutine
    def _get_spec(self):
        if self.existing_spec:
            raise gen.Return(
                self._strip_returned_spec_resource(self.existing_spec))

    @gen.coroutine
    def _set_spec(self):
        yield self._update_spec()
        self.changed = True

    @gen.coroutine
    @dry('Would have created the AlertSpec')
    def _create_spec(self):
        try:
            self.existing_spec = yield self._client.create_resource(
                self._client._client.alert_specs, self.desired_params)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code in (422, 400):
                msg = ('Invalid parameters supplied to Alert Spec "%s": %s'
                       % (self.option('href'), self.desired_params))
                raise exceptions.RecoverableActorFailure(msg)
            raise

        self.log.info('Alert spec has been created')

    @gen.coroutine
    @dry('Would have updated the AlertSpec')
    def _update_spec(self):
        try:
            self.existing_spec = yield self._client.update(
                self.existing_spec, self.desired_params)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code in (422, 400):
                msg = ('Invalid parameters supplied to Alert Spec "%s": %s'
                       % (self.existing_spec.soul['name'],
                          self.desired_params))
                raise exceptions.RecoverableActorFailure(msg)
            raise

        self.log.info('Alert spec has been updated')

    @gen.coroutine
    @dry('Would have deleted the AlertSpec')
    def _delete_spec(self):
        yield self._client.destroy_resource(self.existing_spec)
        self.existing_spec = None

        self.log.info('Alert spec has been destroyed')

    def _strip_returned_spec_resource(self, spec):
        """Converts an AlertSpec resource into a comparable dict.

        Walks through the AlertSpecSchema and creates a new dictionary object
        with only the values from the AlertSpec that were supplied. This
        creates a dict we can compare against the supplied data by the user.

        args:
            spec: A RightScale AlertSpec resource

        returns:
            <dictionary that matches the AlertSpecSchema>
        """
        new = {}
        desired_keys = list(AlertSpecSchema.SCHEMA['properties'].keys())
        for key in desired_keys:
            if key in spec.soul:
                new[key] = spec.soul[key]
        return new


class AlertSpecsBase(base.EnsurableRightScaleBaseActor):

    """Extremely simple AlertSpec management actor.

    This actor isn't really meant to be instantiated on its own -- it provides
    the base functionality though for creating, deleting and updating an
    AlertSpec on a given RightScale resource. The subtle difference here is
    that this actor manages the entire list of AlertSpecs on a given resource,
    rather than just a single spec.

    **Options**

    :href:
      The RightScale HREF for the resource you wish to apply the Alert Spec to.

    :state:
      (str) Either `present` or `absent`

    :spec:
      A dictionary that conforms to the
      :py:mod:`~kingpin.actors.rightscale.alerts.AlertSpecSchema`.

    **Examples**

    .. code-block:: json

       { "actor": "rightscale.alerts.AlertSpecsBase",
         "options": {
           "href": "/api/server_arrays/abcd1234",
           "specs": [
                { "name": "Instance Stranded",
                  "description": "Alert if an instance enders a stranded",
                  "file": "RS/server-failure",
                  "variable": "state",
                  "condition": "==",
                  "threshold": "stranded",
                  "duration": 2,
                  "escalation_name": "critical"
                }
            ]
         }
       }

    """

    all_options = {
        'href': (str, None, 'RightScale Resource HREF to act on'),
        'specs': (AlertSpecsSchema, None, 'A list of AlertSpec dicts'),
    }
    unmanaged_options = ['href']
    desc = "AlertSpecs: {href}"

    def __init__(self, *args, **kwargs):
        super(AlertSpecsBase, self).__init__(*args, **kwargs)
        self.changed = False

        self.alert_actors = []
        for spec in self.option('specs'):
            a = AlertSpecBase(
                desc=('AlertSpecs: %s "%s"' % (
                      self.option('href'), spec['name'])),
                options={
                    'href': self.option('href'),
                    'state': self.option('state'),
                    'spec': spec
                },
                dry=self._dry)

            # Replace the new child actors RightScale client with our own --
            # this way we only have to log in once rather than
            # once-per-alert-spec.
            a._client = self._client
            self.alert_actors.append(a)

    @gen.coroutine
    def _precache(self):
        # Get a list of all of the AlertSpecs associated with the resource.
        all_resource_specs = yield self._client.find_by_name_and_keys(
            self._client._client.alert_specs, exact=True,
            subject_href=self.option('href'))
        if not isinstance(all_resource_specs, list):
            all_resource_specs = [all_resource_specs]

        # Now quickly compare this list to the list of desired specs. For each
        # one thats found that doesn't match, create a new AlertSpecBase actor
        # that will purge this AlertSpec.
        desired_spec_names = [s['name'] for s in self.option('specs')]

        for spec in all_resource_specs:
            if spec.soul['name'] in desired_spec_names:
                continue

            # Create a AlertSpec actor where state is absent
            self.alert_actors.append(
                AlertSpecBase(
                    desc=('AlertSpecs: %s "%s"' % (
                          self.option('href'), spec.soul['name'])),
                    options={
                        'href': self.option('href'),
                        'state': 'absent',
                        'spec': {
                            'name': spec.soul['name'],

                            # The rest of these options don't matter, but need
                            # to be here in order to pass the Schema
                            # verification.
                            'condition': '==',
                            'duration': 0,
                            'file': 'bogus',
                            'threshold': 'NaN',
                            'variable': 'state'
                        }
                    },
                    dry=self._dry))

        # Now create all of the AlertSpec actors that we want to use to manage
        # the defined alert specs.
        tasks = []
        for actor in self.alert_actors:
            # Do all the heavy lifting by throwing these _precache() calls onto
            # a task list and then yield the whole list at once. This makes the
            # rest of the get/set comparison calls super fast.
            tasks.append(actor._precache())
        yield tasks

    @gen.coroutine
    def _get_state(self):
        raise gen.Return()

    @gen.coroutine
    def _compare_state(self):
        equals = True

        # For every actor we've created, make sure the state matches the
        # desired state. If they aren't, set our equals to False and let
        # set_state() get called.
        for actor in self.alert_actors:
            # Note, this is super fast because the AlertSpecBase._precache()
            # actor did all of the actual API calls ahead of time. This returns
            # instantly.
            is_equal = yield actor._compare_state()
            if not is_equal:
                equals = False

        raise gen.Return(equals)

    @gen.coroutine
    def _set_state(self):
        tasks = []
        for actor in self.alert_actors:
            is_equal = yield actor._compare_state()
            if not is_equal:
                tasks.append(actor._set_state())
                self.changed = True
        yield tasks

    @gen.coroutine
    def _get_specs(self):
        specs = []
        for actor in self.alert_actors:
            # Note, this is super fast because the AlertSpecBase._precache()
            # actor did all of the actual API calls ahead of time. This returns
            # instantly.
            specs.append((yield actor._get_spec()))
        raise gen.Return(specs)

    @gen.coroutine
    def _set_specs(self):
        tasks = []
        for actor in self.alert_actors:
            # Note, this is super fast because the AlertSpecBase._precache()
            # actor did all of the actual API calls ahead of time. This returns
            # instantly.
            equals = yield actor._compare_spec()
            if not equals:
                # Note, we don't call _set_spec() here intentionally because
                # that doesn't have the logic to skip setting the spec if we
                # want it absent.
                tasks.append(actor._execute())
                self.changed = True
        yield tasks
