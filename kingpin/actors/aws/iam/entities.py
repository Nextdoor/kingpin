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
:mod:`kingpin.actors.aws.iam.entities`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
"""

import json
import os
import logging

from boto.exception import BotoServerError
from tornado import concurrent
from tornado import gen

from kingpin.actors import exceptions
from kingpin.actors.aws.iam import base
from kingpin.constants import REQUIRED
from kingpin.constants import STATE

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


# This executor is used by the tornado.concurrent.run_on_executor()
# decorator. We would like this to be a class variable so its shared
# across RightScale objects, but we see testing IO errors when we
# do this.
EXECUTOR = concurrent.futures.ThreadPoolExecutor(10)


class EntityBaseActor(base.IAMBaseActor):

    """User/Group/Role Base Management Class

    Managing Users, Groups and Roles in Amazon IAM is nearly identical. This
    class abstracts that work, so that the actual User/Group/Role actors can be
    extremely simple and just handle the differences between each type of IAM
    entity.
    """

    all_options = {
        'name': (str, REQUIRED, 'The name of the user.'),
        'state': (STATE, 'present',
                  'Desired state of the User: present/absent'),
        'inline_policies': ((str, list), [],
                            'List of inline policy JSON files to apply.'),
        'inline_policies_purge': (bool, False,
                                  'Purge unmanaged inline policies?')
    }

    def __init__(self, *args, **kwargs):
        super(EntityBaseActor, self).__init__(*args, **kwargs)

        # These IAM Connection methods must be overridden in a subclass of this
        # actor!
        self.entity_name = 'base'
        self.create_entity = None
        self.delete_entity = None
        self.delete_entity_policy = None
        self.get_all_entities = None
        self.get_all_entity_policies = None
        self.get_entity_policy = None
        self.put_entity_policy = None

        # Parse the supplied inline policies
        self._parse_inline_policies(self.option('inline_policies'))

    def _generate_policy_name(self, policy):
        """Generates an Amazon-friendly Policy name from a filename.

        Amazon Inline IAM Policies have names -- and although allowing our
        users to enter their own name might be nice, its overkill in most
        cases. We'd rather just determine the name for them from the name of
        the policy definition file that they included in the JSON.

        http://docs.aws.amazon.com/IAM/latest/UserGuide/reference_iam-limits.html

        args:
            policy: The file name of the policy document

        returns:
            A string name to use as the policy name
        """
        # Get rid of the extension first
        name = os.path.splitext(policy)[0]

        # If theres a leading slash, strip it
        name = name.lstrip('/')

        # Replace slashes with dashes instead
        name = name.replace('/', '-')
        name = name.replace('\\', '-')

        # Strip out any non-allowed characters that made it through
        name = name.replace('*', '')
        name = name.replace('?', '')

        return name

    def _parse_inline_policies(self, policies):
        """Read, parse and store our inline policies.

        Any of the inline policies passed into this actor at init time are read
        in, parsed, turned into dicts and then stored in an object level
        dictionary for future use. This is done at __init__ time to make sure
        we catch any syntax errors as early as possible.

        args:
            policies: A string or list of strings that point to JSON files with
            IAM policies in them.
        """
        # Prepare to store our parsed inline policies in a hash of key/values
        # -- the key is the policy name (with no file ending) and the value is
        # the dict of the policy itself.
        self.inline_policies = {}

        # If a single policy was supplied (ie, maybe on a command line) then
        # turn it into a list.
        if isinstance(policies, basestring):
            policies = [policies]

        # Run through any supplied Inline IAM Policies and verify that they're
        # not corrupt very early on.
        for policy in policies:
            p_name = self._generate_policy_name(policy)
            self.inline_policies[p_name] = self._parse_policy_json(policy)

        self.log.info(self.inline_policies)

    @gen.coroutine
    def _get_entity_policies(self, name):
        """Returns a dictionary of all the inline policies attached to a entity.

        args:
            name: The IAM Entity Name (Name/Group)

        returns:
            A dict of key/value pairs - key is the policy name, value is the
            dict-version of the policy document.
        """
        policies = {}

        # Get the list of inline policies attached to an entity.
        self.log.debug('Searching for any inline policies for %s' % name)
        try:
            ret = yield self.thread(self.get_all_entity_policies, name)
            response = ret['list_%s_policies_response' % self.entity_name]
            result = response['list_%s_policies_result' % self.entity_name]
            policy_names = result['policy_names']
        except BotoServerError as e:
            if e.status == 404:
                # The user doesn't exist.. likely in a dry run. Return no
                # policies.
                policy_names = []
            else:
                raise exceptions.RecoverableActorFailure(
                    'An unexpected API error occurred: %s' % e)

        # Iterate through all of the named policies and fire off
        # get-requests, but don't yield on them yet.
        tasks = []
        for p_name in policy_names:
            tasks.append(
                (p_name,
                 self.thread(self.get_entity_policy, name, p_name)))

        # Now that we've fired off all the calls, we walk through each yielded
        # result, parse the returned policy, and append it to our policies
        # list. We also catch any raised exceptions here.
        for t in tasks:
            (p_name, p_task) = t
            try:
                raw = yield p_task
            except BotoServerError as e:
                raise exceptions.RecoverableActorFailure(
                    'An unexpected API error occurred downloading '
                    'policy %s: %s' % (p_name, e))

            # Convert the uuencoded doc string into a dict
            resp_key = 'get_%s_policy_response' % self.entity_name
            result_key = 'get_%s_policy_result' % self.entity_name
            p_doc = self._policy_doc_to_dict(
                raw[resp_key][result_key]['policy_document'])

            # Store the converted document under the policy name key
            policies[p_name] = p_doc
            self.log.debug('Got policy %s/%s: %s' % (name, p_name, p_doc))

        raise gen.Return(policies)

    @gen.coroutine
    def _ensure_inline_policies(self, name, purge):
        """Ensures that all of the inline IAM policies for a entity are managed

        This method has three stages.. first it ensures that any missing
        policies (as determined by the policy name) are applied to a entity.
        Second, it determines if any existing policies have changed locally and
        need to be updated in IAM. Finally (optionally) it purges unmanaged
        policies that were applied to a entity out of band.

        args:
            name: The entity to manage
            purge: Whether or not to purge unmanaged policies.
        """
        # Get the list of current entity policies first
        existing_policies = yield self._get_entity_policies(name)

        # First, push any policies that we have listed, but aren't in the
        # entity
        tasks = []
        for policy in [policy for policy in self.inline_policies.keys()
                       if policy not in existing_policies.keys()]:
            policy_doc = self.inline_policies[policy]
            tasks.append(self._put_entity_policy(name, policy, policy_doc))
        yield tasks

        # Do we have matching policies that we're managing here, and are
        # already attached to the entity profile? Lets make sure each one of
        # those matches the policy we have here, and update it if necessary.
        tasks = []
        for policy in [policy for policy in self.inline_policies.keys()
                       if policy in existing_policies.keys()]:
            new = self.inline_policies[policy]
            exist = existing_policies[policy]
            diff = self._diff_policy_json(new, exist)
            if diff:
                self.log.info('Policy %s differs from Amazons:' % policy)
                for line in diff.split('\n'):
                    self.log.info('Diff: %s' % line)
                policy_doc = self.inline_policies[policy]
                tasks.append(self._put_entity_policy(name, policy, policy_doc))
        yield tasks

        # We're done now -- are we purging unmanaged records? If not, bail!
        if not purge:
            raise gen.Return()

        # Finally, are we purging? If so, find any policies (by name) that we
        # don't have in our own inline policies doc, and purge them.
        tasks = []
        for policy in [policy for policy in existing_policies.keys()
                       if policy not in self.inline_policies.keys()]:
            tasks.append(self._delete_entity_policy(name, policy))
        yield tasks

    @gen.coroutine
    def _delete_entity_policy(self, name, policy_name):
        """Optionally pushes a policy to an IAM entity.

        args:
            name: The IAM Entity Name
            policy_name: The entity policy name
        """
        if self._dry:
            self.log.warning('Would delete policy %s from %s %s' %
                             (self.entity_name, policy_name, name))
            raise gen.Return()

        self.log.info('Deleting policy %s from %s %s' %
                      (self.entity_name, policy_name, name))
        try:
            ret = yield self.thread(
                self.delete_entity_policy, name, policy_name)
            self.log.debug('Policy %s deleted: %s' % (policy_name, ret))
        except BotoServerError as e:
            if e.error_code != 404:
                raise exceptions.RecoverableActorFailure(
                    'An unexpected API error occurred: %s' % e)

    @gen.coroutine
    def _put_entity_policy(self, name, policy_name, policy_doc):
        """Optionally pushes a policy to an IAM Entity.

        args:
            name: The IAM Entity Name
            policy_name: The entity policy name
            policy_doc: The ploicy document object itself
        """
        if self._dry:
            self.log.warning('Would push policy %s to %s %s' %
                             (self.entity_name, policy_name, name))
            raise gen.Return()

        self.log.info('Pushing policy %s to %s %s' %
                      (self.entity_name, policy_name, name))
        try:
            ret = yield self.thread(
                self.put_entity_policy,
                name,
                policy_name,
                json.dumps(policy_doc))
            self.log.debug('Policy %s pushed: %s' % (policy_name, ret))
        except BotoServerError as e:
            raise exceptions.RecoverableActorFailure(
                'An unexpected API error occurred: %s' % e)

    @gen.coroutine
    def _get_entity(self, name):
        """Returns an IAM Entity JSON Blob.

        Searches for an IAM Entity and either returns None, or a JSON blob that
        describes the Entity.

        args:
            name: The IAM Entity Name
        """
        self.log.debug('Searching for %s %s' % (self.entity_name, name))

        # Get a list of all of our entities.
        try:
            entities = yield self.thread(self.get_all_entities)
        except BotoServerError as e:
            raise exceptions.RecoverableActorFailure(
                'An unexpected API error occurred: %s' % e)

        # Now search for the entity
        resp_key = 'list_%ss_response' % self.entity_name
        result_key = 'list_%ss_result' % self.entity_name
        entity_key = '%ss' % self.entity_name
        entity = [entity for entity in
                  entities[resp_key][result_key][entity_key] if
                  entity['%s_name' % self.entity_name] == name]

        # If there aren't any entities, return None.
        if not entity:
            raise gen.Return()

        # If there is more than one entities, something went really wrong.
        # Raise an exception.
        if len(entity) > 1:
            raise exceptions.RecoverableActorFailure(
                'More than one %s found matching %s! Am I crazy?!' %
                (self.entity_name, name))

        # Finally, return the result!
        self.log.debug('Found %s %s' % (self.entity_name, entity[0]['arn']))
        raise gen.Return(entity[0])

    @gen.coroutine
    def _ensure_entity(self, name, state):
        """Ensures a entity is either present or absent.

        Looks up the entities current state and then makes a decision about
        creating or deleting the entity. If the entity is already in the
        correct state, not changes are made.

        args:
            name: The IAM User Name
            state: 'present' or 'absent'
        """
        self.log.info('Ensuring that %s %s is %s' %
                      (self.entity_name, name, state))

        entity = yield self._get_entity(name)

        if entity and state == 'present':
            raise gen.Return()
        elif not entity and state == 'present':
            yield self._create_entity(name)
        elif entity and state == 'absent':
            yield self._delete_entity(name)
        elif not entity and state == 'absent':
            raise gen.Return()

    @gen.coroutine
    def _create_entity(self, name):
        """Creates an IAM Entity.

        If the entity exists, we just warn and move on.

        args:
            name: The IAM Entity Name
        """
        if self._dry:
            self.log.warning('Would create %s %s' % (self.entity_name, name))
            raise gen.Return()

        try:
            ret = yield self.thread(
                self.create_entity, name)
        except BotoServerError as e:
            if e.status != 409:
                raise exceptions.RecoverableActorFailure(
                    'An unexpected API error occurred: %s' % e)
            self.log.warning(
                '%s %s already exists, skipping creation.' %
                (self.entity_name, name))
            raise gen.Return()

        resp_key = 'create_%s_response' % self.entity_name
        result_key = 'create_%s_result' % self.entity_name
        arn = ret[resp_key][result_key][self.entity_name]['arn']
        self.log.info('%s %s created' % (self.entity_name, arn))

    @gen.coroutine
    def _delete_entity(self, name):
        """Deletes and IAM Entity.

        If the entity doesn't exist, we just warn and move on.

        args:
            name: The IAM Entity Name
        """
        if self._dry:
            self.log.warning('Would delete %s %s' % (self.entity_name, name))
            raise gen.Return()

        try:
            # Get the entities policies. They have to be deleted before we can
            # possibly move forward and delete the entity.
            existing_policies = yield self._get_entity_policies(name)
            tasks = []
            for policy in existing_policies:
                tasks.append(self._delete_entity_policy(name, policy))
            yield tasks

            # Now delete the entity
            yield self.thread(self.delete_entity, name)
            self.log.info('%s %s deleted' % (self.entity_name, name))
        except BotoServerError as e:
            if e.status != 404:
                raise exceptions.RecoverableActorFailure(
                    'An unexpected API error occurred: %s' % e)
            self.log.warning('%s %s doesn\'t exist' % (self.entity_name, name))

    @gen.coroutine
    def _execute(self):
        name = self.option('name')
        state = self.option('state')
        inline_policies_purge = self.option('inline_policies_purge')

        yield self._ensure_entity(name, state)
        if state == 'absent':
            raise gen.Return()

        yield self._ensure_inline_policies(name, inline_policies_purge)
        raise gen.Return()


class User(EntityBaseActor):

    """Manages an IAM User.

    This actor manages the state of an Amazon IAM User. It ensures that the
    user either exists or does not. It also updates any settings for the user
    that are different from the passed in options.

    At the moment you can mange the users state, its inline policies, and you
    can purge unmanaged inline policies.

    **Options**

    :name:
      (str) Name of the User profile to manage

    :state:
      (str) Present or Absent. Default: "present"

    :inline_policies:
      (str,array) A list of strings that point to JSON files to use as inline
      policies. You can also pass in a single inline policy as a string.
      Default: []

    :inline_policies_purge:
      (bool) Whether or not to purge un-managed policies. Default: false

    **Example**

    .. code-block:: json

       { "actor": "aws.iam.User",
         "desc": "Ensure that Bob exists",
         "options": {
           "name": "bob",
           "state": "present",
           "inline_policies": [
             "read-all-s3.json",
             "create-other-stuff.json"
           ],
           "inline_policies_purge": false,
         }
       }

    **Dry run**

    Will let you know if the user exists or not, and what changes it would make
    to the users policy and settings. Will also parse the inline policies
    supplied, make sure any tokens in the files are replaced, and that the
    files are valid JSON.
    """

    all_options = {
        'name': (str, REQUIRED, 'The name of the user.'),
        'state': (STATE, 'present',
                  'Desired state of the User: present/absent'),
        'inline_policies': ((str, list), [],
                            'List of inline policy JSON files to apply.'),
        'inline_policies_purge': (bool, False,
                                  'Purge unmanaged inline policies?')
    }

    def __init__(self, *args, **kwargs):
        super(User, self).__init__(*args, **kwargs)

        self.entity_name = 'user'
        self.create_entity = self.iam_conn.create_user
        self.delete_entity = self.iam_conn.delete_user
        self.delete_entity_policy = self.iam_conn.delete_user_policy
        self.get_all_entities = self.iam_conn.get_all_users
        self.get_all_entity_policies = self.iam_conn.get_all_user_policies
        self.get_entity_policy = self.iam_conn.get_user_policy
        self.put_entity_policy = self.iam_conn.put_user_policy
