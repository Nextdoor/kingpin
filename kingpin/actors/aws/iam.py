"""
:mod:`kingpin.actors.aws.iam`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
"""

import asyncio
import json
import logging
import os

from botocore.exceptions import ClientError
from tornado import concurrent

from kingpin import utils
from kingpin.actors import exceptions
from kingpin.actors.aws import base
from kingpin.constants import REQUIRED, STATE

log = logging.getLogger(__name__)

__author__ = "Matt Wise <matt@nextdoor.com>"


# This executor is used by the tornado.concurrent.run_on_executor()
# decorator. We would like this to be a class variable so its shared
# across RightScale objects, but we see testing IO errors when we
# do this.
EXECUTOR = concurrent.futures.ThreadPoolExecutor(10)

# The maximum number of items returned to us in a get_all_*/list_* api call.
# Defaults to 100, but setting to 1000 to reduce the number of API calls we
# make.
MAX_ITEMS = 1000


class IAMBaseActor(base.AWSBaseActor):
    """User/Group/Role Base Management Class

    Managing Users, Groups and Roles in Amazon IAM is nearly identical. This
    class abstracts that work, so that the actual User/Group/Role actors can be
    extremely simple and just handle the differences between each type of IAM
    entity.
    """

    all_options = {
        "name": (str, REQUIRED, "The name of the user."),
        "state": (STATE, "present", "Desired state of the User: present/absent"),
        "inline_policies": (
            (str, list),
            None,
            "List of inline policy JSON files to apply.",
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # These IAM Connection methods must be overridden in a subclass of this
        # actor. Each of these is a "generalized" name for the method in Boto
        # found at http://boto.cloudhackers.com/en/latest/ref/iam.html.
        #
        # This is a little confusing, but the idea is that these methods all
        # basically behave the same (are called the same way, return the same
        # type of data), so we should be able to generalize them into
        # variables.
        #
        # Once these are mapped to real IAM calls, then the methods in this
        # base class will work.

        # The "text name" of the entity type. This is either:
        #  User, Group, Role, InstanceProfiles
        self.entity_name = "Base"

        self.create_entity = None
        self.delete_entity = None
        self.delete_entity_policy = None
        self.get_entity = None
        self.list_entity_policies = None
        self.get_entity_policy = None
        self.put_entity_policy = None

    @property
    def entity_kwarg_name(self):
        return f"{self.entity_name.capitalize()}Name"

    def _generate_policy_name(self, policy):
        """Generates an Amazon-friendly Policy name from a filename.

        Amazon Inline IAM Policies have names -- and although allowing our
        users to enter their own name might be nice, its overkill in most
        cases. We'd rather just determine the name for them from the name of
        the policy definition file that they included in the JSON.

        http://docs.aws.amazon.com/IAM/latest/UserGuide/reference_iam-limits.html

        Args:
            policy: The file name of the policy document

        Returns:
            A string name to use as the policy name
        """
        # Get rid of the extension first
        name = os.path.splitext(policy)[0]

        # If theres a leading slash, strip it
        name = name.lstrip("/")

        # Replace slashes with dashes instead
        name = name.replace("/", "-")
        name = name.replace("\\", "-")

        # Strip out any non-allowed characters that made it through
        name = name.replace("*", "")
        name = name.replace("?", "")

        return name

    def _parse_inline_policies(self, policies):
        """Read, parse and store our inline policies.

        Any of the inline policies passed into this actor at init time are read
        in, parsed, turned into dicts and then stored in an object level
        dictionary for future use. This is done at __init__ time to make sure we
        catch any syntax errors as early as possible.

        Args:
            policies: A string or list of strings that point to JSON files with
            IAM policies in them.
        """
        # If the inline_policies is None, then we bail and set
        # self.inline_policies to none.
        if policies is None:
            self.inline_policies = None
            return

        # Prepare to store our parsed inline policies in a hash of key/values
        # -- the key is the policy name (with no file ending) and the value is
        # the dict of the policy itself.
        self.inline_policies = {}

        # If a single policy was supplied (ie, maybe on a command line) then
        # turn it into a list.
        if isinstance(policies, str):
            policies = [policies]

        # Run through any supplied Inline IAM Policies and verify that they're
        # not corrupt very early on.
        for policy in policies:
            p_name = self._generate_policy_name(policy)
            self.inline_policies[p_name] = self._parse_json(policy)

            self.log.debug(f"Parsed policy {p_name}: {self.inline_policies[p_name]}")

    async def _get_entity_policies(self, name):
        """Returns a dictionary of all the inline policies attached to a entity.

        Args:
            name: The IAM Entity Name (Name/Group)

        Returns:
            A dict of key/value pairs - key is the policy name, value is the
            dict-version of the policy document.
        """

        policies = {}

        # Get the list of inline policies attached to an entity.
        #
        # Note, not all entities have a concept of inline policies. If
        # self.list_entity_policies is None, it returns a TypeError. We'll catch
        # that and silently move on.
        policy_names = []
        try:
            self.log.debug(f"Searching for any inline policies for {name}")
            ret = await self.api_call(
                self.list_entity_policies, **{self.entity_kwarg_name: name}
            )
            policy_names = ret.get("PolicyNames", [])
        except ClientError as e:
            if "NoSuchEntity" in str(e):
                # The user doesn't exist.. likely in a dry run. Return no
                # policies.
                policy_names = []
            else:
                raise exceptions.RecoverableActorFailure(
                    f"An unexpected API error occurred: {e}"
                ) from e

        # Iterate through all of the named policies and fire off
        # get-requests, but don't await on them yet.
        tasks = []
        for p_name in policy_names:
            tasks.append(
                (
                    p_name,
                    self.api_call(
                        self.get_entity_policy,
                        **{self.entity_kwarg_name: name, "PolicyName": p_name},
                    ),
                )
            )

        # Now that we've fired off all the calls, we walk through each awaited
        # result, parse the returned policy, and append it to our policies
        # list. We also catch any raised exceptions here.
        for t in tasks:
            p_name, p_task = t
            try:
                raw = await p_task
            except ClientError as e:
                raise exceptions.RecoverableActorFailure(
                    f"An unexpected API error occurred downloading "
                    f"policy {p_name}: {e}"
                ) from e

            # Convert the uuencoded doc string into a dict
            p_doc = raw.get("PolicyDocument", {})

            # Store the converted document under the policy name key
            policies[p_name] = p_doc
            self.log.debug(f"Got policy {name}/{p_name}: {p_doc}")

        return policies

    async def _ensure_inline_policies(self, name):
        """Ensures that all of the inline IAM policies for a entity are managed

        This method has three stages.. first it ensures that any missing
        policies (as determined by the policy name) are applied to a entity.
        Second, it determines if any existing policies have changed locally and
        need to be updated in IAM. Finally it purges unmanaged policies that
        were applied to a entity out of band.

        Args:
            name: The entity to manage
        """
        # Get the list of current entity policies first
        existing_policies = await self._get_entity_policies(name)

        # First, push any policies that we have listed, but aren't in the
        # entity
        async with asyncio.TaskGroup() as tg:
            for policy in set(self.inline_policies.keys()) - set(existing_policies.keys()):
                policy_doc = self.inline_policies[policy]
                tg.create_task(self._put_entity_policy(name, policy, policy_doc))

        # Do we have matching policies that we're managing here, and are
        # already attached to the entity profile? Lets make sure each one of
        # those matches the policy we have here, and update it if necessary.
        async with asyncio.TaskGroup() as tg:
            for policy in set(self.inline_policies.keys()) & set(existing_policies.keys()):
                new = self.inline_policies[policy]
                exist = existing_policies[policy]
                diff = utils.diff_dicts(exist, new)
                if diff:
                    self.log.info(f"Policy {policy} differs from Amazons:")
                    for line in diff.split("\n"):
                        self.log.info(f"Diff: {line}")
                    policy_doc = self.inline_policies[policy]
                    tg.create_task(self._put_entity_policy(name, policy, policy_doc))

        # Purge any policies we found in AWS that were not listed in our actor
        async with asyncio.TaskGroup() as tg:
            for policy in set(existing_policies.keys()) - set(self.inline_policies.keys()):
                tg.create_task(self._delete_entity_policy(name, policy))

    async def _delete_entity_policy(self, name, policy_name):
        """Optionally pushes a policy to an IAM entity.

        Args:
            name: The IAM Entity Name
            policy_name: The entity policy name
        """

        if self._dry:
            self.log.warning(
                f"Would delete policy {policy_name} from {self.entity_name} {name}"
            )
            return

        self.log.info(f"Deleting policy {policy_name} from {self.entity_name} {name}")
        try:
            ret = await self.api_call(
                self.delete_entity_policy,
                **{self.entity_kwarg_name: name, "PolicyName": policy_name},
            )
            self.log.debug(f"Policy {policy_name} deleted: {ret}")
        except ClientError as e:
            if "NoSuchEntity" not in str(e):
                raise exceptions.RecoverableActorFailure(
                    f"An unexpected API error occurred: {e}"
                ) from e

    async def _put_entity_policy(self, name, policy_name, policy_doc):
        """Optionally pushes a policy to an IAM Entity.

        Args:
            name: The IAM Entity Name
            policy_name: The entity policy name
            policy_doc: The ploicy document object itself
        """

        if self._dry:
            self.log.warning(
                f"Would push policy {policy_name} to {self.entity_name} {name}"
            )
            return

        self.log.info(f"Pushing policy {policy_name} to {self.entity_name} {name}")
        try:
            ret = await self.api_call(
                self.put_entity_policy,
                **{
                    self.entity_kwarg_name: name,
                    "PolicyName": policy_name,
                    "PolicyDocument": json.dumps(policy_doc),
                },
            )
            self.log.debug(f"Policy {policy_name} pushed: {ret}")
        except ClientError as e:
            raise exceptions.RecoverableActorFailure(
                f"An unexpected API error occurred: {e}"
            ) from e

    async def _get_entity(self, name):
        """Returns an IAM Entity JSON Blob.

        Searches for an IAM Entity and either returns None, or a JSON blob that
        describes the Entity.

        Args:
            name: The IAM Entity Name
        """

        self.log.debug(f"Searching for {self.entity_name} {name}")

        try:
            ret = await self.api_call(self.get_entity, **{self.entity_kwarg_name: name})
        except ClientError as e:
            if "NoSuchEntity" in str(e):
                return None
            raise exceptions.RecoverableActorFailure(
                f"An unexpected API error occurred: {e}"
            ) from e

        return ret.get(self.entity_name)

    async def _ensure_entity(self, name, state):
        """Ensures a entity is either present or absent.

        Looks up the entities current state and then makes a decision about
        creating or deleting the entity. If the entity is already in the
        correct state, not changes are made.

        Args:
            name: The IAM User Name
            state: 'present' or 'absent'
        """

        self.log.info(f"Ensuring that {self.entity_name} {name} is {state}")

        entity = await self._get_entity(name)

        if entity and state == "present":
            return
        elif not entity and state == "present":
            await self._create_entity(name)
        elif entity and state == "absent":
            await self._delete_entity(name)
        elif not entity and state == "absent":
            return

    async def _create_entity(self, name, **kwargs):
        """Creates an IAM Entity.

        If the entity exists, we just warn and move on.

        Args:
            name: The IAM Entity Name
        """

        if self._dry:
            self.log.warning(f"Would create {self.entity_name} {name}")
            return

        try:
            ret = await self.api_call(
                self.create_entity, **{self.entity_kwarg_name: name, **kwargs}
            )
        except ClientError as e:
            if "EntityAlreadyExists" in str(e):
                self.log.warning(
                    f"{self.entity_name} {name} already exists, skipping creation."
                )
                return
            raise exceptions.RecoverableActorFailure(
                f"An unexpected API error occurred: {e}"
            ) from e

        self.log.info(f"{self.entity_name} {ret[self.entity_name]['Arn']} created")

    async def _delete_entity(self, name):
        """Deletes and IAM Entity.

        If the entity doesn't exist, we just warn and move on.

        Args:
            name: The IAM Entity Name
        """

        if self._dry:
            self.log.warning(f"Would delete {self.entity_name} {name}")
            return

        try:
            # Get the entities policies. They have to be deleted before we can
            # possibly move forward and delete the entity.
            existing_policies = await self._get_entity_policies(name)
            async with asyncio.TaskGroup() as tg:
                for policy in existing_policies:
                    tg.create_task(self._delete_entity_policy(name, policy))

            # Now delete the entity
            await self.api_call(self.delete_entity, **{self.entity_kwarg_name: name})
            self.log.info(f"{self.entity_name} {name} deleted")
        except ClientError as e:
            if "NoSuchEntity" in str(e):
                self.log.warning(f"{self.entity_name} {name} doesn't exist")
                return
            raise exceptions.RecoverableActorFailure(
                f"An unexpected API error occurred: {e}"
            ) from e

    async def _add_user_to_group(self, name, group):
        """Quick helper method to add a user to a group.

        Args:
            name: user name
            group: group name
        """

        if self._dry:
            self.log.warning(f"Would have added {name} to {group}")
            return

        try:
            self.log.info(f"Adding {name} to {group}")
            await self.api_call(
                self.iam_conn.add_user_to_group, GroupName=group, UserName=name
            )
        except ClientError as e:
            raise exceptions.RecoverableActorFailure(
                f"An unexpected API error occurred: {e}"
            ) from e

    async def _remove_user_from_group(self, name, group):
        """Quick helper method to remove a user from a group.

        Args:
            name: user name
            group: group name
        """

        if self._dry:
            self.log.warning(f"Would have removed {name} from {group}")
            return

        try:
            self.log.info(f"Removing {name} from {group}")
            await self.api_call(
                self.iam_conn.remove_user_from_group, GroupName=group, UserName=name
            )
        except ClientError as e:
            raise exceptions.RecoverableActorFailure(
                f"An unexpected API error occurred: {e}"
            ) from e


class User(IAMBaseActor):
    """Manages an IAM User.

    This actor manages the state of an Amazon IAM User.

    Currently we can:

      * Ensure is present or absent
      * Manage the inline policies for the user
      * Manage the groups the user is in

    **Options**

    :name:
      (str) Name of the User profile to manage

    :state:
      (str) Present or Absent. Default: "present"

    :groups:
      (str,array) A list of groups for the user to be a member of.
      Default: None

    :inline_policies:
      (str,array) A list of strings that point to JSON files to use as inline
      policies.
      Default: None

    **Example**

    .. code-block:: json

       { "actor": "aws.iam.User",
         "desc": "Ensure that Bob exists",
         "options": {
           "name": "bob",
           "state": "present",
           "groups": "my-test-group",
           "inline_policies": [
             "read-all-s3.json",
             "create-other-stuff.json"
           ]
         }
       }

    **Dry run**

    Will let you know if the user exists or not, and what changes it would make
    to the users policy and settings. Will also parse the inline policies
    supplied, make sure any tokens in the files are replaced, and that the
    files are valid JSON.
    """

    all_options = {
        "name": (str, REQUIRED, "The name of the user."),
        "state": (STATE, "present", "Desired state of the User: present/absent"),
        "groups": ((str, list), None, "List of groups to add the user to."),
        "inline_policies": (
            (str, list),
            None,
            "List of inline policy JSON files to apply.",
        ),
    }

    desc = "IAM User {name}"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.entity_name = "User"
        self.create_entity = self.iam_conn.create_user
        self.delete_entity = self.iam_conn.delete_user
        self.delete_entity_policy = self.iam_conn.delete_user_policy
        self.get_entity = self.iam_conn.get_user
        self.list_entity_policies = self.iam_conn.list_user_policies
        self.get_entity_policy = self.iam_conn.get_user_policy
        self.put_entity_policy = self.iam_conn.put_user_policy

        # Parse the supplied inline policies
        self._parse_inline_policies(self.option("inline_policies"))

    async def _ensure_groups(self, name, groups):
        """Ensure that this user is a member of specific groups.

        Args:
            name: The user we're managing
            groups: The list (or single) of groups to join be members of
        """

        if isinstance(groups, str):
            groups = [groups]

        current_groups = set()
        try:
            res = await self.api_call(
                self.iam_conn.list_groups_for_user, **{self.entity_kwarg_name: name}
            )
            current_groups = {g["GroupName"] for g in res.get("Groups", [])}
        except ClientError as e:
            # If the error is a 404, then the user doesn't exist and we can
            # assume that the mappings don't exist at all. We leave the
            # existing_mappings list alone. For any other error, raise.
            if "NoSuchEntity" not in str(e):
                raise exceptions.RecoverableActorFailure(
                    f"An unexpected API error occurred: {e}"
                ) from e

        # Find any groups that we're not already a member of, and add us
        async with asyncio.TaskGroup() as tg:
            try:
                for new_group in set(groups) - current_groups:
                    tg.create_task(self._add_user_to_group(name, new_group))
            except StopIteration:
                pass  # pragma: no cover

        # Find any group memberships we didn't know about, and purge them
        async with asyncio.TaskGroup() as tg:
            for bad_group in current_groups - set(groups):
                tg.create_task(self._remove_user_from_group(name, bad_group))

    async def _execute(self):
        name = self.option("name")
        state = self.option("state")
        groups = self.option("groups")

        await self._ensure_entity(name, state)
        if state == "absent":
            return

        if self.option("inline_policies") is not None:
            await self._ensure_inline_policies(name)

        if groups is not None:
            await self._ensure_groups(name, groups)

        return


class Group(IAMBaseActor):
    """Manages an IAM Group.

    This actor manages the state of an Amazon IAM Group.

    Currently we can:

      * Ensure is present or absent
      * Manage the inline policies for the group
      * Purge (or not) all group members and delete the group

    **Options**

    :name:
      (str) Name of the Group profile to manage

    :force:
      (bool) Forcefully delete the group (explicitly purging all group
      memberships).
      Default: false

    :state:
      (str) Present or Absent. Default: "present"

    :inline_policies:
      (str,array) A list of strings that point to JSON files to use as inline
      policies. You can also pass in a single inline policy as a string.
      Default: None

    **Example**

    .. code-block:: json

       { "actor": "aws.iam.Group",
         "desc": "Ensure that devtools exists",
         "options": {
           "name": "devtools",
           "state": "present",
           "inline_policies": [
             "read-all-s3.json",
             "create-other-stuff.json"
           ]
         }
       }

    **Dry run**

    Will let you know if the group exists or not, and what changes it would
    make to the groups policy and settings. Will also parse the inline policies
    supplied, make sure any tokens in the files are replaced, and that the
    files are valid JSON.
    """

    all_options = {
        "name": (str, REQUIRED, "The name of the group."),
        "force": (bool, False, "Forcefully delete the group."),
        "state": (STATE, "present", "Desired state of the group: present/absent"),
        "inline_policies": (
            (str, list),
            None,
            "List of inline policy JSON files to apply.",
        ),
    }

    desc = "IAM Group {name}"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.entity_name = "group"
        self.create_entity = self.iam_conn.create_group
        self.delete_entity = self.iam_conn.delete_group
        self.delete_entity_policy = self.iam_conn.delete_group_policy
        self.get_entity = self.iam_conn.get_group
        self.list_entity_policies = self.iam_conn.list_group_policies
        self.get_entity_policy = self.iam_conn.get_group_policy
        self.put_entity_policy = self.iam_conn.put_group_policy

        # Parse the supplied inline policies
        self._parse_inline_policies(self.option("inline_policies"))

    async def _get_group_users(self, name):
        """Returns a list of users assigned to the group.

        Args:
            name: the name of the group

        Returns:
            a list of user name strings
        """

        users = []
        try:
            raw = await self.api_call(
                self.iam_conn.get_group, **{self.entity_kwarg_name: name}
            )
            users = [user["UserName"] for user in raw.get("Users", [])]
        except ClientError as e:
            if "NoSuchEntity" not in str(e):
                raise exceptions.RecoverableActorFailure(
                    f"An unexpected API error occurred: {e}"
                ) from e

        return users

    async def _purge_group_users(self, name, force):
        """Forcefully purge all users from the group.

        This is used only if the group has users, is being deleted, and the
        'purge' option was set.

        Args:
            name: the group name
            force: boolean whether or not to actually force the removal
        """

        users = await self._get_group_users(name)

        if not force and users:
            self.log.warning(
                "Will not be able to delete this group "
                "without first removing all of its members. "
                "Use the `force` option to purge all members."
            )
            self.log.warning(f"Group members: {', '.join(users)}")

        if not force:
            return

        async with asyncio.TaskGroup() as tg:
            for user in users:
                tg.create_task(self._remove_user_from_group(user, name))

    async def _execute(self):
        name = self.option("name")
        state = self.option("state")
        force = self.option("force")

        if state == "absent":
            await self._purge_group_users(name, force)

        await self._ensure_entity(name, state)
        if state == "absent":
            return

        if self.option("inline_policies") is not None:
            await self._ensure_inline_policies(name)

        return


class Role(IAMBaseActor):
    """Manages an IAM Role.

    This actor manages the state of an Amazon IAM Role.

    Currently we can:

      * Ensure is present or absent
      * Manage the inline policies for the role
      * Manage the Assume Role Policy Document

    **Options**

    :name:
      (str) Name of the Role to manage

    :state:
      (str) Present or Absent. Default: "present"

    :inline_policies:
      (str,array) A list of strings that point to JSON files to use as inline
      policies. You can also pass in a single inline policy as a string.
      Default: None

    :assume_role_policy_document:
      (str) A string with an Amazon IAM Assume Role policy. Not providing this
      causes Kingpin to ignore the value, and Amazon defaults the role to an
      'EC2' style rule. Supplying the document will cause Kingpin to ensure the
      assume role policy is correct.

      Default:

      .. code-block:: json

          { "Version": "2012-10-17",
            "Statement": [
                { "Effect": "Allow",
                  "Principal": {
                      "Service": "ec2.amazonaws.com"
                  },
                  "Action": "sts:AssumeRole"
                }
            ]
          }

    **Example**

    .. code-block:: json

       { "actor": "aws.iam.Role",
         "desc": "Ensure that myapp exists",
         "options": {
           "name": "myapp",
           "state": "present",
           "inline_policies": [
             "read-all-s3.json",
             "create-other-stuff.json"
           ]
         }
       }

    **Dry run**

    Will let you know if the group exists or not, and what changes it would
    make to the groups policy and settings. Will also parse the inline policies
    supplied, make sure any tokens in the files are replaced, and that the
    files are valid JSON.
    """

    all_options = {
        "name": (str, REQUIRED, "The name of the role."),
        "state": (STATE, "present", "Desired state of the group: present/absent"),
        "inline_policies": (
            (str, list),
            None,
            "List of inline policy JSON files to apply.",
        ),
        "assume_role_policy_document": (
            str,
            None,
            ("The policy that grants an entity permission to assume the role"),
        ),
    }

    desc = "IAM Role {name}"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.entity_name = "Role"
        self.create_entity = self.iam_conn.create_role
        self.delete_entity = self.iam_conn.delete_role
        self.delete_entity_policy = self.iam_conn.delete_role_policy
        self.get_entity = self.iam_conn.get_role
        self.list_entity_policies = self.iam_conn.list_role_policies
        self.get_entity_policy = self.iam_conn.get_role_policy
        self.put_entity_policy = self.iam_conn.put_role_policy

        # Pre-parse the supplied inline policies
        self._parse_inline_policies(self.option("inline_policies"))

        # Pre-parse the Assume Role Policy Document if it was supplied
        self.assume_role_policy_doc = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
        if self.option("assume_role_policy_document") is not None:
            self.assume_role_policy_doc = self._parse_json(
                self.option("assume_role_policy_document")
            )

    async def _ensure_assume_role_doc(self, name):
        """Ensures that the Assume Role Policy for a Role is up to date.

        Downloads the existing Assume Role Policy for a given Role, then
        compares it against our configured policy and optionally updates it if
        they differ.

        Args:
            name: The role we're working with
        """
        # Get our existing role policy from the entity
        entity = await self._get_entity(name)

        # If the entity doesn't exist, then we must be in a Dry run and the
        # role hasn't been created yet. Just bail silently.
        if not entity:
            return

        # Parse the raw data into a dict we can compare
        exist = entity.get("AssumeRolePolicyDocument", {})
        new = self.assume_role_policy_doc

        # Now diff it against our desired policy. If no diff, then quietly
        # return.
        diff = utils.diff_dicts(exist, new)
        if not diff:
            self.log.debug("Assume Role Policy documents match")
            return

        self.log.info("Assume Role Policy differs from Amazons:")
        for line in diff.split("\n"):
            self.log.info(f"Diff: {line}")

        if self._dry:
            self.log.warning("Would have updated the Assume Role Policy Doc")
            return

        self.log.info("Updating the Assume Role Policy Document")
        await self.api_call(
            self.iam_conn.update_assume_role_policy,
            **{self.entity_kwarg_name: name, "PolicyDocument": json.dumps(new)},
        )

    async def _create_entity(self, name):
        """Creates an IAM Role.

        If the entity exists, we just warn and move on.

        Args:
            name: The IAM Entity Name
        """

        await super()._create_entity(
            name,
            AssumeRolePolicyDocument=json.dumps(self.assume_role_policy_doc),
        )

    async def _execute(self):
        name = self.option("name")
        state = self.option("state")

        await self._ensure_entity(name, state)
        if state == "absent":
            return

        if self.option("inline_policies") is not None:
            await self._ensure_inline_policies(name)

        await self._ensure_assume_role_doc(name)

        return


class InstanceProfile(IAMBaseActor):
    """Manages an IAM Instance Profile.

    This actor manages the state of an Amazon IAM Instance Profile.

    Currently we can:

      * Ensure is present or absent
      * Assign an IAM Role to the Instance Profile

    **Options**

    :name:
      (str) Name of the Role to manage

    :state:
      (str) Present or Absent. Default: "present"

    :role:
      (str) Name of an IAM Role to assign to the Instance Profile.
      Default: None

    **Example**

    .. code-block:: json

       { "actor": "aws.iam.InstanceProfile",
         "desc": "Ensure that my-ecs-servers exists",
         "options": {
           "name": "my-ecs-servers",
           "state": "present",
           "role": "some-iam-role",
         }
       }

    **Dry run**

    Will let you know if the profile exists or not, and what changes it would
    make to the profile.
    """

    all_options = {
        "name": (str, REQUIRED, "The name of the instance profile."),
        "state": (STATE, "present", "Desired state of the group: present/absent"),
        "role": (str, None, "Name of an IAM Role to assign"),
    }

    desc = "InstanceProfile {name}"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.entity_name = "InstanceProfile"
        self.create_entity = self.iam_conn.create_instance_profile
        self.delete_entity = self.iam_conn.delete_instance_profile
        self.get_entity = self.iam_conn.get_instance_profile

    @property
    def entity_kwarg_name(self):
        return "InstanceProfileName"

    async def _add_role(self, name, role):
        """Adds a role to an Instance Profile.

        Args:
            name: The name of the Instance Profile we're managing
            role: The name of the role to assign to the profile
        """

        if self._dry:
            self.log.warning(f"Would add role {role} from {name}")
            return

        try:
            self.log.info(f"Adding role {role} to {name}")
            await self.api_call(
                self.iam_conn.add_role_to_instance_profile,
                **{self.entity_kwarg_name: name, "RoleName": role},
            )
        except ClientError as e:
            if "NoSuchEntity" not in str(e):
                raise exceptions.RecoverableActorFailure(
                    f"An unexpected API error occurred: {e}"
                ) from e

    async def _remove_role(self, name, role):
        """Removes a role assigned to an Instance Profile.

        Args:
            name: The name of the InstanceProfile we're managing
            role: The name of the role to remove
        """

        if self._dry:
            self.log.warning(f"Would remove role {role} from {name}")
            return

        try:
            self.log.info(f"Removing role {role} from {name}")
            await self.api_call(
                self.iam_conn.remove_role_from_instance_profile,
                **{self.entity_kwarg_name: name, "RoleName": role},
            )
        except ClientError as e:
            if "NoSuchEntity" not in str(e):
                raise exceptions.RecoverableActorFailure(
                    f"An unexpected API error occurred: {e}"
                ) from e

    async def _ensure_role(self, name, role):
        """Ensures that an Instance Profile role is set correctly.

        Adds, Deletes or Changes the Role assigned to an Instance Profile.

        Args:
            name: The IAM Instance Profile we're managing
            role: The desired role (or None)
        """

        existing = None
        try:
            raw = await self.api_call(
                self.iam_conn.get_instance_profile, InstanceProfileName=name
            )
            existing = raw["InstanceProfile"]["Roles"][0]["RoleName"]
        except ClientError as e:
            if "NoSuchEntity" not in str(e):
                raise exceptions.RecoverableActorFailure(
                    f"An unexpected API error occurred: {e}"
                ) from e
        except (IndexError, KeyError):
            # Profile is not a member of any roles
            pass

        if not existing and not role:
            return
        elif existing and not role:
            try:
                await self._remove_role(name, existing)
            except StopIteration:  # pragma: no cover
                return  # pragma: no cover
        elif not existing and role:
            await self._add_role(name, role)
        elif existing != role:
            await self._remove_role(name, existing)
            await self._add_role(name, role)

    async def _execute(self):
        name = self.option("name")
        state = self.option("state")
        role = self.option("role")

        await self._ensure_entity(name, state)
        if state == "absent":
            return

        if role is not None:
            await self._ensure_role(name, role)
