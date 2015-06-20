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
:mod:`kingpin.actors.rightscale.alerts`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
"""

import logging

from tornado import gen
import requests

from kingpin.actors import exceptions
from kingpin.actors.rightscale import base
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
