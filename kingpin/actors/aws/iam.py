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
:mod:`kingpin.actors.aws.iam`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
"""

import json
import os
import logging

from boto.exception import BotoServerError
from tornado import concurrent
from tornado import gen

from kingpin.actors.aws import base
from kingpin.actors import exceptions
from kingpin.constants import REQUIRED
from kingpin.constants import STATE

log = logging.getLogger(__name__)

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'


# This executor is used by the tornado.concurrent.run_on_executor()
# decorator. We would like this to be a class variable so its shared
# across RightScale objects, but we see testing IO errors when we
# do this.
EXECUTOR = concurrent.futures.ThreadPoolExecutor(10)


class IAMBaseActor(base.AWSBaseActor):

    """Base class for IAM actors."""


class UploadCert(IAMBaseActor):

    """Uploads a new SSL Cert to AWS IAM.

    **Options**

    :private_key_path:
      (str) Path to the private key.

    :path:
      (str) The AWS "path" for the server certificate. Default: "/"

    :public_key_path:
      (str) Path to the public key certificate.

    :name:
      (str) The name for the server certificate.

    :cert_chain_path:
      (str) Path to the certificate chain. Optional.

    **Example**

    .. code-block:: json

       { "actor": "aws.iam.UploadCert",
         "desc": "Upload a new cert",
         "options": {
           "name": "new-cert",
           "private_key_path": "/cert.key",
           "public_key_path": "/cert.pem",
           "cert_chain_path": "/cert-chain.pem"
         }
       }

    **Dry run**

    Checks that the passed file paths are valid. In the future will also
    validate that the files are of correct format and content.
    """

    all_options = {
        'name': (str, REQUIRED, 'The name for the server certificate.'),
        'public_key_path': (str, REQUIRED,
                            'Path to the public key certificate.'),
        'private_key_path': (str, REQUIRED, 'Path to the private key.'),
        'cert_chain_path': (str, None, 'Path to the certificate chain.'),
        'path': (str, None, 'The path for the server certificate.')
    }

    @gen.coroutine
    def _upload(self, cert_name, cert_body, private_key, cert_chain, path):
        """Create a new server certificate in AWS IAM."""
        yield self.thread(
            self.iam_conn.upload_server_cert,
            cert_name=cert_name,
            cert_body=cert_body,
            private_key=private_key,
            cert_chain=cert_chain,
            path=path)

    @gen.coroutine
    def _execute(self):
        """Gather all the cert data and upload it.

        The `boto` library requires actual cert contents, but this actor
        expects paths to files.
        """
        # Gather needed cert data
        cert_chain_body = None
        if self.option('cert_chain_path'):
            cert_chain_body = self.readfile(self.option('cert_chain_path'))

        cert_body = self.readfile(self.option('public_key_path'))
        private_key = self.readfile(self.option('private_key_path'))

        # Upload it
        if self._dry:
            self.log.info('Would upload cert "%s"' % self.option('name'))
            raise gen.Return()

        self.log.info('Uploading cert "%s"' % self.option('name'))
        yield self._upload(
            cert_name=self.option('name'),
            cert_body=cert_body,
            private_key=private_key,
            cert_chain=cert_chain_body,
            path=self.option('path'))


class DeleteCert(IAMBaseActor):

    """Delete an existing SSL Cert in AWS IAM.

    **Options**

    :name:
      (str) The name for the server certificate.

    **Example**

    .. code-block:: json

       { "actor": "aws.iam.DeleteCert",
         "desc": "Run DeleteCert",
         "options": {
           "name": "fill-in"
         }
       }

    **Dry run**

    Will find the cert by name or raise an exception if it's not found.
    """

    all_options = {
        'name': (str, REQUIRED, 'The name for the server certificate.')
    }

    @gen.coroutine
    def _find_cert(self, name):
        """Find a cert by name."""

        self.log.debug('Searching for cert "%s"...' % name)
        try:
            yield self.thread(self.iam_conn.get_server_certificate, name)
        except BotoServerError as e:
            raise exceptions.UnrecoverableActorFailure(
                'Could not find cert %s. Reason: %s' % (name, e))

    @gen.coroutine
    def _delete(self, cert_name):
        """Delete a server certificate in AWS IAM."""
        yield self.thread(self.iam_conn.delete_server_cert, cert_name)

    @gen.coroutine
    def _execute(self):
        if self._dry:
            self.log.info('Checking that the cert exists...')
            yield self._find_cert(self.option('name'))
            self.log.info('Would delete cert "%s"' % self.option('name'))
            raise gen.Return()

        self.log.info('Deleting cert "%s"' % self.option('name'))
        yield self._delete(cert_name=self.option('name'))


class User(IAMBaseActor):

    """Manages an IAM User.

    **Options**

    :name:
      (str) Name of the User profile to manage

    :state:
      (str) Present or Absent. Default: "present"

    :inline_policies:
      (array) A list of strings that point to JSON files to use as inline
      policies. Default: []

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
    def _get_user_policies(self, name):
        """Returns a dictionary of all the inline policies attached to a user.

        args:
            name: The IAM User Name

        returns:
            A dict of key/value pairs - key is the policy name, value is the
            dict-version of the policy document.
        """
        policies = {}

        # Get the list of inline policies attached to a user.
        self.log.debug('Searching for any inline policies for %s' % name)
        try:
            ret = yield self.thread(self.iam_conn.get_all_user_policies, name)
            response = ret['list_user_policies_response']
            result = response['list_user_policies_result']
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
                 self.thread(self.iam_conn.get_user_policy, name, p_name)))

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
            result = raw['get_user_policy_response']['get_user_policy_result']
            p_doc = self._policy_doc_to_dict(result['policy_document'])

            # Store the converted document under the policy name key
            policies[p_name] = p_doc
            self.log.debug('Got policy %s/%s: %s' % (name, p_name, p_doc))

        raise gen.Return(policies)

    @gen.coroutine
    def _ensure_inline_policies(self, name, purge):
        """Ensures that all of the inline IAM policies for a user are managed.

        This method has three stages.. first it ensures that any missing
        policies (as determined by the policy name) are applied to a user.
        Second, it determines if any existing policies have changed locally and
        need to be updated in IAM. Finally (optionally) it purges unmanaged
        policies that were applied to a user out of band.

        args:
            name: The username to manage
            purge: Whether or not to purge unmanaged policies.
        """
        # Get the list of current user policies first
        existing_policies = yield self._get_user_policies(name)

        # First, push any policies that we have listed, but aren't in the user
        tasks = []
        for policy in [policy for policy in self.inline_policies.keys()
                       if policy not in existing_policies.keys()]:
            policy_doc = self.inline_policies[policy]
            tasks.append(self._put_user_policy(name, policy, policy_doc))
        yield tasks

        # Do we have matching policies that we're managing here, and are
        # already attached to the user profile? Lets make sure each one of
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
                tasks.append(self._put_user_policy(name, policy, policy_doc))
        yield tasks

        # We're done now -- are we purging unmanaged records? If not, bail!
        if not purge:
            raise gen.Return()

        # Finally, are we purging? If so, find any policies (by name) that we
        # don't have in our own inline policies doc, and purge them.
        tasks = []
        for policy in [policy for policy in existing_policies.keys()
                       if policy not in self.inline_policies.keys()]:
            tasks.append(self._delete_user_policy(name, policy))
        yield tasks

    @gen.coroutine
    def _delete_user_policy(self, name, policy_name):
        """Optionally pushes a policy to an IAM user.

        args:
            name: The IAM User Name
            policy_name: The users policy name
        """
        if self._dry:
            self.log.warning('Would delete policy %s from user %s' %
                             (policy_name, name))
            raise gen.Return()

        self.log.info('Deleting policy %s from user %s' % (policy_name, name))
        try:
            ret = yield self.thread(
                self.iam_conn.delete_user_policy, name, policy_name)
            self.log.debug('Policy %s deleted: %s' % (policy_name, ret))
        except BotoServerError as e:
            if e.error_code != 404:
                raise exceptions.RecoverableActorFailure(
                    'An unexpected API error occurred: %s' % e)

    @gen.coroutine
    def _put_user_policy(self, name, policy_name, policy_doc):
        """Optionally pushes a policy to an IAM user.

        args:
            name: The IAM User Name
            policy_name: The users policy name
            policy_doc: The ploicy document object itself
        """
        if self._dry:
            self.log.warning('Would push policy %s to user %s' %
                             (policy_name, name))
            raise gen.Return()

        self.log.info('Pushing policy %s to user %s' % (policy_name, name))
        try:
            ret = yield self.thread(
                self.iam_conn.put_user_policy,
                name,
                policy_name,
                json.dumps(policy_doc))
            self.log.debug('Policy %s pushed: %s' % (policy_name, ret))
        except BotoServerError as e:
            raise exceptions.RecoverableActorFailure(
                'An unexpected API error occurred: %s' % e)

    @gen.coroutine
    def _get_user(self, name):
        """Returns an IAM User JSON Blob.

        Searches for an IAM user and either returns None, or a JSON blob that
        describes the user.

        args:
            name: The IAM User Name
        """
        self.log.debug('Searching for user %s' % name)

        # Get a list of all of our users.
        try:
            users = yield self.thread(self.iam_conn.get_all_users)
        except BotoServerError as e:
            raise exceptions.RecoverableActorFailure(
                'An unexpected API error occurred: %s' % e)

        # Now search for the user
        user = [user for user in
                users['list_users_response']['list_users_result']['users'] if
                user['user_name'] == name]

        # If there aren't any users, return None.
        if not user:
            raise gen.Return()

        # If there is more than one user, something went really wrong. Raise an
        # exception.
        if len(user) > 1:
            raise exceptions.RecoverableActorFailure(
                'More than one user found matching %s! Am I crazy?!' % name)

        # Finally, return the result!
        self.log.debug('Found user %s' % user[0]['arn'])
        raise gen.Return(user[0])

    @gen.coroutine
    def _ensure_user(self, name, state):
        """Ensures a user is either present or absent.

        Looks up the users current state and then makes a decision about
        creating or deleting the user. If the user is already in the correct
        state, not changes are made.

        args:
            name: The IAM User Name
            state: 'present' or 'absent'
        """
        self.log.info('Ensuring that user %s is %s' % (name, state))

        user = yield self._get_user(name)

        if user and state == 'present':
            raise gen.Return()
        elif not user and state == 'present':
            yield self._create_user(name)
        elif user and state == 'absent':
            yield self._delete_user(name)
        elif not user and state == 'absent':
            raise gen.Return()

    @gen.coroutine
    def _create_user(self, name):
        """Creates an IAM User.

        If the user exists, we just warn and move on.

        args:
            name: The IAM User Name
        """
        if self._dry:
            self.log.warning('Would create user %s' % name)
            raise gen.Return()

        try:
            ret = yield self.thread(
                self.iam_conn.create_user, name)
        except BotoServerError as e:
            if e.status != 409:
                raise exceptions.RecoverableActorFailure(
                    'An unexpected API error occurred: %s' % e)
            self.log.warning(
                'User %s already exists, skipping creation.' % name)
            raise gen.Return()

        arn = ret['create_user_response']['create_user_result']['user']['arn']
        self.log.info('User %s created' % arn)

    @gen.coroutine
    def _delete_user(self, name):
        """Deletes and IAM User.

        If the user doesn't exist, we just warn and move on.

        args:
            name: The IAM User Name
        """
        if self._dry:
            self.log.warning('Would delete user %s' % name)
            raise gen.Return()

        try:
            # Get the users policies. They have to be deleted before we can
            # possibly move forward and delete the user.
            existing_policies = yield self._get_user_policies(name)
            tasks = []
            for policy in existing_policies:
                tasks.append(self._delete_user_policy(name, policy))
            yield tasks

            # Now delete the user
            yield self.thread(self.iam_conn.delete_user, name)
            self.log.info('User %s deleted' % name)
        except BotoServerError as e:
            if e.status != 404:
                raise exceptions.RecoverableActorFailure(
                    'An unexpected API error occurred: %s' % e)
            self.log.warning('User %s doesn\'t exist' % name)

    @gen.coroutine
    def _execute(self):
        name = self.option('name')
        state = self.option('state')
        inline_policies_purge = self.option('inline_policies_purge')

        yield self._ensure_user(name, state)
        if state == 'absent':
            raise gen.Return()

        yield self._ensure_inline_policies(name, inline_policies_purge)
        raise gen.Return()
