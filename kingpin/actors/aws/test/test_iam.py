import logging
import importlib
import json

from datetime import datetime

import mock

from botocore.stub import Stubber
from tornado import gen, testing

from kingpin.actors import exceptions
from kingpin.actors.aws import iam, settings

log = logging.getLogger(__name__)


@gen.coroutine
def tornado_value(*args):
    """Returns whatever is passed in. Used for testing."""
    raise gen.Return(*args)


class TestIAMBaseActor(testing.AsyncTestCase):
    def setUp(self):
        super(TestIAMBaseActor, self).setUp()
        settings.AWS_ACCESS_KEY_ID = "unit-test"
        settings.AWS_SECRET_ACCESS_KEY = "unit-test"
        settings.AWS_SESSION_TOKEN = "unit-test"
        importlib.reload(iam)

        # Create our actor object with some basics... then mock out the IAM
        # connections..
        self.actor = iam.IAMBaseActor(
            "Unit Test",
            {
                "name": "test",
                "state": "present",
                "inline_policies": "examples/aws.iam.user/s3_example.json",
            },
        )
        self.iam_stubber = Stubber(self.actor.iam_conn)

        # The base class defines these as None -- but in order to test them, we
        # need to have more realistic and trackable method names.
        self.actor.entity_name = "User"
        self.actor.create_entity = self.actor.iam_conn.create_user
        self.actor.delete_entity = self.actor.iam_conn.delete_user
        self.actor.delete_entity_policy = self.actor.iam_conn.delete_user_policy
        self.actor.get_entity = self.actor.iam_conn.get_user
        self.actor.list_entity_policies = self.actor.iam_conn.list_user_policies
        self.actor.get_entity_policy = self.actor.iam_conn.get_user_policy
        self.actor.put_entity_policy = self.actor.iam_conn.put_user_policy

        # Pretend like we're a more full featured actor (User/Group/Role) that
        # has inline policies. This could be abstracted differently by making
        # another BaseActor for Users/Groups/Roles thats separate from
        # InstanceProfiles -- but for now this will do.
        self.actor._parse_inline_policies(self.actor.option("inline_policies"))

    @testing.gen_test
    def test_generate_policy_name(self):
        name = "/some-?funky*-directory/with.my.policy.json"
        parsed = self.actor._generate_policy_name(name)
        self.assertEqual(parsed, "some-funky-directory-with.my.policy")

    @testing.gen_test
    def test_get_entity_policies_500(self):
        self.iam_stubber = Stubber(self.actor.iam_conn)
        self.iam_stubber.add_client_error("list_user_policies", "500", "Server Error!")
        self.iam_stubber.activate()
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._get_entity_policies("test")

    @testing.gen_test
    def test_get_entity_policies_400(self):
        self.iam_stubber.add_client_error("list_user_policies", "400", "NoSuchEntity")
        self.iam_stubber.activate()
        ret = yield self.actor._get_entity_policies("test")
        self.assertEqual(ret, {})

    @testing.gen_test
    def test_get_entities_other_500(self):
        self.iam_stubber.add_response(
            # API Call
            "list_user_policies",
            # Response
            # Use one policy here so we do not have to deal with extra calls
            # and multiple Stubber responses.
            {"PolicyNames": ["test1"]},
            # Call Params
            {"UserName": "test"},
        )
        self.iam_stubber.add_client_error("get_user_policy", "500", "SomeError")
        self.iam_stubber.activate()
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._get_entity_policies("test")

    @testing.gen_test
    def test_get_entity_policies(self):
        policy_str = "".join(
            [
                "%7B%22Version%22%3A%20%222012-10-17%22%2C%20",
                "%22Statement%22%3A%20%5B%7B%22Action%22%3A%20%5B",
                "%22s3%3ACreate%2A%22%2C%20%22s3%3AGet%2A%22%2C%20",
                "%22s3%3APut%2A%22%2C%20%22s3%3AList%2A%22%5D%2C%20",
                "%22Resource%22%3A%20%5B",
                "%22arn%3Aaws%3As3%3A%3A%3Akingpin%2A%2F%2A%22%2C%20",
                "%22arn%3Aaws%3As3%3A%3A%3Akingpin%2A%22%5D%2C%20",
                "%22Effect%22%3A%20%22Allow%22%7D%5D%7D",
            ]
        )
        policy_dict = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": ["s3:Create*", "s3:Get*", "s3:Put*", "s3:List*"],
                    "Resource": ["arn:aws:s3:::kingpin*/*", "arn:aws:s3:::kingpin*"],
                    "Effect": "Allow",
                }
            ],
        }

        # Return a list of entity policy names...
        fake_pols = ["test1", "test2", "test3"]
        self.iam_stubber.add_response(
            # API Call
            "list_user_policies",
            # Response
            {"PolicyNames": fake_pols},
            # Call Params
            {"UserName": "test"},
        )

        for pol in fake_pols:
            self.iam_stubber.add_response(
                # API Call
                "get_user_policy",
                # Response
                {"UserName": "test", "PolicyName": pol, "PolicyDocument": policy_str},
                # Call Params
                # Disable expected parameters because calls to
                # api_call(self.get_entity_policy, [...]) can come in out of order but boto3 Subber
                # expects them to be in order if you use this parameter. We do our own checks below
                # to ensure we have all the data we expected.
                # {"UserName": "test", "PolicyName": pol},
            )

        # Finally, make the call and see if we get all the policies
        self.iam_stubber.activate()
        ret = yield self.actor._get_entity_policies("test")
        self.assertEqual(len(ret), 3)
        self.assertEqual(ret["test1"], policy_dict)
        self.assertEqual(ret["test2"], policy_dict)
        self.assertEqual(ret["test3"], policy_dict)

    @testing.gen_test
    def test_parse_inline_policies(self):
        parsed_policy = self.actor.inline_policies["examples-aws.iam.user-s3_example"]
        self.assertEqual(parsed_policy["Version"], "2012-10-17")

    @testing.gen_test
    def test_parse_inline_policies_none(self):
        self.actor._parse_inline_policies(None)
        self.assertEqual(self.actor.inline_policies, None)

    @testing.gen_test
    def test_ensure_inline_policies(self):
        # First, pretend like there are a few policies in place and we're not
        # passing any in, however we are purging policies we don't manage.
        fake_pol = {
            "Policy1": {"junk": "policy"},
            "Policy2": {"more": "junk"},
        }
        self.actor._get_entity_policies = mock.MagicMock()
        self.actor._get_entity_policies.side_effect = [tornado_value(fake_pol)]

        # Mock out the delete_entity_policy and put_entity_policy methods
        self.actor._delete_entity_policy = mock.MagicMock()
        self.actor._delete_entity_policy.side_effect = [
            tornado_value(None),
            tornado_value(None),
        ]
        self.actor._put_entity_policy = mock.MagicMock()
        self.actor._put_entity_policy.side_effect = [tornado_value(None)]

        # Ensure that the new policy was pushed, and the old policies were
        # deleted
        yield self.actor._ensure_inline_policies("test")
        self.assertEqual(1, self.actor._put_entity_policy.call_count)
        self.actor._delete_entity_policy.assert_has_calls(
            [
                mock.call("test", "Policy1"),
                mock.call("test", "Policy2"),
            ],
            any_order=True,
        )

    @testing.gen_test
    def test_ensure_inline_policies_updated(self):
        # First, pretend like there are a few policies in place and we're not
        # passing any in, however we are purging policies we don't manage.
        fake_pol = {
            "Policy1": {"junk": "policy"},
            "examples-aws.iam.user-s3_example": {"more": "junk"},
        }
        self.actor._get_entity_policies = mock.MagicMock()
        self.actor._get_entity_policies.side_effect = [tornado_value(fake_pol)]
        self.actor._put_entity_policy = mock.MagicMock()
        self.actor._put_entity_policy.side_effect = [tornado_value(None)]

        self.iam_stubber.add_response(
            # API Call
            "delete_user_policy",
            # Response
            {},
            # Call Params
            {"UserName": "test", "PolicyName": "Policy1"},
        )
        self.iam_stubber.activate()
        yield self.actor._ensure_inline_policies("test")
        self.assertEqual(1, self.actor._put_entity_policy.call_count)

    @testing.gen_test
    def test_delete_entity_policy_dry(self):
        self.actor._dry = True
        self.iam_stubber.activate()
        yield self.actor._delete_entity_policy("test", "test-policy")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_delete_entity_policy(self):
        self.iam_stubber.add_response(
            # API Call
            "delete_user_policy",
            # Response
            {},
            # Call Params
            {"UserName": "test", "PolicyName": "test-policy"},
        )
        self.iam_stubber.activate()
        yield self.actor._delete_entity_policy("test", "test-policy")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_delete_entity_policy_exception(self):
        self.iam_stubber.activate()
        self.iam_stubber.add_client_error("delete_user_policy", 500, "Yikes!")
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._delete_entity_policy("test", "test-policy")

    @testing.gen_test
    def test_put_entity_policy_dry(self):
        self.actor._dry = True
        self.iam_stubber.activate()
        yield self.actor._put_entity_policy("test", "test-policy", {})
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_put_entity_policy(self):
        self.iam_stubber.add_response(
            # API CALL
            "put_user_policy",
            # Response
            {},
            # Call Params
            {"UserName": "test", "PolicyName": "test-policy", "PolicyDocument": "{}"},
        )
        self.iam_stubber.activate()
        yield self.actor._put_entity_policy("test", "test-policy", {})
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_put_entity_policy_exception(self):
        self.iam_stubber.add_client_error("put_user_policy", 500, "Yikes!")
        self.iam_stubber.activate()
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._put_entity_policy("test", "test-policy", {})

    @testing.gen_test
    def test_get_entity_500(self):
        # Test a random unexpected failure
        self.iam_stubber.add_client_error("get_user", 500, "Yikes!")
        self.iam_stubber.activate()
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._get_entity("test")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_get_entity_404(self):
        # Test a random unexpected failure
        self.iam_stubber.add_client_error("get_user", 404, "NoSuchEntity")
        self.iam_stubber.activate()
        ret = yield self.actor._get_entity("test")
        self.assertIsNone(ret)
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_get_entity(self):
        # Create some valid test user objects...
        self.iam_stubber.add_response(
            # API Call
            "get_user",
            # Response
            {
                "User": {
                    "Path": "/",
                    "CreateDate": "2016-04-05T22:15:24Z",
                    "UserName": "test",
                    "UserId": "AIDAXXCXXXXXXXXXAAC2E",
                    "Arn": "arn:aws:iam::123123123123:base/test",
                }
            },
            # Call Params
            {"UserName": "test"},
        )
        self.iam_stubber.activate()
        ret = yield self.actor._get_entity("test")
        self.assertEqual(ret["UserName"], "test")

    @testing.gen_test
    def test_ensure_entity(self):
        create_mock = mock.MagicMock(name="_create_entity")
        delete_mock = mock.MagicMock(name="_delete_entity")
        get_mock = mock.MagicMock(name="_get_entity")
        self.actor._create_entity = create_mock
        self.actor._delete_entity = delete_mock
        self.actor._get_entity = get_mock
        self.actor._create_entity.side_effect = [tornado_value(None)]
        self.actor._delete_entity.side_effect = [tornado_value(None)]
        self.actor._get_entity.side_effect = [tornado_value(None)]

        # Mock out that the entity doesn't exist, and we're creating it
        self.actor._get_entity.side_effect = [tornado_value(None)]
        yield self.actor._ensure_entity("test", "present")
        create_mock.assert_called_with("test")
        self.assertFalse(delete_mock.called)
        create_mock.reset_mock()
        delete_mock.reset_mock()

        # Pretend like the entity already exists..
        entity = {
            "get_base_response": {"get_base_result": {"base": {"arn": "fake_arn"}}}
        }
        self.actor._get_entity.side_effect = [tornado_value(entity)]

        # Now if we ask to create the entity, make sure we don't make those
        # calls since the entity already exists
        self.actor._get_entity.side_effect = [tornado_value(entity)]
        yield self.actor._ensure_entity("test", "present")
        self.assertFalse(create_mock.called)
        self.assertFalse(delete_mock.called)
        create_mock.reset_mock()
        delete_mock.reset_mock()

        # Since the entity is there, lets test deleting them.. do they get
        # deleted?
        self.actor._get_entity.side_effect = [tornado_value(entity)]
        yield self.actor._ensure_entity("test", "absent")
        self.assertFalse(create_mock.called)
        delete_mock.assert_called_with("test")
        create_mock.reset_mock()
        delete_mock.reset_mock()

        # If the entity doesn't exist, make sure we don't try to delete them
        self.actor._get_entity.side_effect = [tornado_value(None)]
        yield self.actor._ensure_entity("test", "absent")
        self.assertFalse(create_mock.called)
        self.assertFalse(delete_mock.called)
        create_mock.reset_mock()
        delete_mock.reset_mock()

    @testing.gen_test
    def test_delete_entity(self):
        # stub out the get_entity_policies to return one policy name. This ensures that we first have to delete the
        # policies from the entity, then tne entity.
        self.iam_stubber.add_response(
            # API Call
            "list_user_policies",
            # Response
            {"PolicyNames": ["test"]},
            # Call Params
            {"UserName": "test"},
        )
        # Stub out getting the actual policy contents
        self.iam_stubber.add_response(
            # API Call
            "get_user_policy",
            # Response
            {
                "UserName": "test",
                "PolicyName": "test",
                "PolicyDocument": str(json.dumps({})),
            },
            # Call Params
            {"UserName": "test", "PolicyName": "test"},
        )

        # Now stub out the delete call to that particular policy
        self.iam_stubber.add_response(
            # API Call
            "delete_user_policy",
            # Response
            {},
            # Call Params
            {"UserName": "test", "PolicyName": "test"},
        )

        # Finally stub out the delete call to the user
        self.iam_stubber.add_response(
            # API Call
            "delete_user",
            # Response
            {},
            # Call Params
            {"UserName": "test"},
        )
        # Pretend it worked...
        self.iam_stubber.activate()
        yield self.actor._delete_entity("test")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_delete_entity_already_deleted(self):
        # Exception raised? Handle it!
        self.actor._get_entity_policies = mock.MagicMock()
        self.actor._get_entity_policies.side_effect = [tornado_value([])]
        self.iam_stubber.add_client_error("delete_user", 400, "NoSuchEntity")
        self.iam_stubber.activate()
        yield self.actor._delete_entity("test")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_delete_entity_other_exception(self):
        # Exception raised? Handle it!
        self.actor._get_entity_policies = mock.MagicMock()
        self.actor._get_entity_policies.side_effect = [tornado_value([])]
        self.iam_stubber.add_client_error("delete_user", 500, "Yikes!")
        self.iam_stubber.activate()
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._delete_entity("test")

    @testing.gen_test
    def test_delete_entity_dry(self):
        # Make sure we did not call the delete function!
        self.actor._dry = True
        self.iam_stubber.activate()
        yield self.actor._delete_entity("test")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_create_entity(self):
        self.iam_stubber.add_response(
            # API Call
            "create_user",
            # Response,
            {
                "User": {
                    "Arn": "arn:.................",
                    "Path": "/",
                    "UserName": "test",
                    "UserId": "AQ..............C...",
                    "CreateDate": datetime(2015, 1, 1),
                }
            },
            # Call Params
            {"UserName": "test"},
        )
        self.iam_stubber.activate()
        yield self.actor._create_entity("test")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_create_entity_already_exists(self):
        self.iam_stubber.add_client_error("create_user", 409, "EntityAlreadyExists")
        self.iam_stubber.activate()
        yield self.actor._create_entity("test")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_create_entity_other_exception(self):
        self.iam_stubber.add_client_error("create_user", 500, "ServerError")
        self.iam_stubber.activate()
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._create_entity("test")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_create_entity_dry(self):
        # Make sure we did not call the create function!
        self.actor._dry = True
        self.iam_stubber.activate()
        yield self.actor._create_entity("test")
        self.iam_stubber.assert_no_pending_responses()


class TestUser(testing.AsyncTestCase):
    def setUp(self):
        super(TestUser, self).setUp()
        settings.AWS_ACCESS_KEY_ID = "unit-test"
        settings.AWS_SECRET_ACCESS_KEY = "unit-test"
        settings.AWS_SESSION_TOKEN = "unit-test"
        importlib.reload(iam)

        # Create our actor object with some basics... then mock out the IAM
        # connections..
        self.actor = iam.User(
            "Unit Test",
            {
                "name": "test",
                "state": "present",
                "inline_policies": "examples/aws.iam.user/s3_example.json",
                "groups": "foo",
            },
        )

        self.iam_stubber = Stubber(self.actor.iam_conn)

    @testing.gen_test
    def test_ensure_groups(self):
        # Stub out a fake list of groups that the user is already attached to
        self.iam_stubber.add_response(
            # API Call
            "list_groups_for_user",
            # Response
            {
                "Groups": [
                    {
                        "Path": "/",
                        "GroupName": "test-group-1",
                        "GroupId": "................",
                        "Arn": "....................",
                        "CreateDate": datetime(2015, 1, 1),
                    },
                ]
            },
            # Call Params
            {"UserName": "test"},
        )
        self.iam_stubber.add_response(
            # API Call
            "add_user_to_group",
            # Response
            {},
            # Call Params
            {"UserName": "test", "GroupName": "ng1"},
        )

        # Now stub out the calls that are delete calls...
        self.iam_stubber.add_response(
            # API Call
            "remove_user_from_group",
            # Response
            {},
            # Call Params
            {"UserName": "test", "GroupName": "test-group-1"},
        )

        self.iam_stubber.activate()
        yield self.actor._ensure_groups("test", "ng1")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_ensure_groups_with_not_yet_created_user(self):
        # Create mocks for the add/remove user group methods
        self.actor._add_user_to_group = mock.MagicMock()
        self.actor._add_user_to_group.side_effect = [tornado_value(None)]
        self.actor._remove_user_from_group = mock.MagicMock()
        self.actor._remove_user_from_group.side_effect = [tornado_value(None)]

        # The user doesn't exist? No problem.. we'll move forward anyways and
        # assume we're in a dry run and the user hasn't been created, and thus
        # there are no groups.
        self.iam_stubber.add_client_error("list_groups_for_user", 404, "NoSuchEntity")
        self.iam_stubber.activate()
        yield self.actor._ensure_groups("test", ["ng1", "ng2"])
        self.actor._add_user_to_group.assert_has_calls(
            [mock.call("test", "ng1"), mock.call("test", "ng2")], any_order=True
        )
        self.assertFalse(self.actor._remove_user_from_group.called)

    @testing.gen_test
    def test_ensure_groups_with_500(self):
        self.iam_stubber.add_client_error("list_groups_for_user", 500, "Server Error")
        self.iam_stubber.activate()
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._ensure_groups("test", ["ng1", "ng2"])
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_add_user_to_group(self):
        self.iam_stubber.add_response(
            # API Call
            "add_user_to_group",
            # Response
            {},
            # Call Params
            {"GroupName": "group", "UserName": "test"},
        )
        self.iam_stubber.activate()
        yield self.actor._add_user_to_group("test", "group")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_add_user_to_group_dry(self):
        self.iam_stubber.activate()
        self.actor._dry = True
        yield self.actor._add_user_to_group("test", "group")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_add_user_to_group_500(self):
        self.iam_stubber.add_client_error("add_user_to_group", 500, "Yikes!")
        self.iam_stubber.activate()
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._add_user_to_group("test", "group")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_remove_user_from_group(self):
        self.iam_stubber.add_response(
            # API Call
            "remove_user_from_group",
            # Response
            {},
            # Call Params
            {"UserName": "test", "GroupName": "group"},
        )
        self.iam_stubber.activate()
        yield self.actor._remove_user_from_group("test", "group")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_remove_user_from_group_dry(self):
        self.iam_stubber.activate()
        self.actor._dry = True
        yield self.actor._remove_user_from_group("test", "group")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_remove_user_from_group_500(self):
        self.iam_stubber.add_client_error("remove_user_from_group", 500, "Yikes!")
        self.iam_stubber.activate()
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._remove_user_from_group("test", "group")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_execute_absent(self):
        self.actor._options["state"] = "absent"
        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_entity.called)

    @testing.gen_test
    def test_execute_present(self):
        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]
        self.actor._ensure_inline_policies = mock.MagicMock()
        self.actor._ensure_inline_policies.side_effect = [tornado_value(None)]
        self.actor._ensure_groups = mock.MagicMock()
        self.actor._ensure_groups.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_entity.called)
        self.assertTrue(self.actor._ensure_inline_policies.called)
        self.assertTrue(self.actor._ensure_groups.called)

    @testing.gen_test
    def test_execute_present_no_policies_or_groups(self):
        self.actor._options["inline_policies"] = None
        self.actor._options["groups"] = None

        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]

        self.actor._ensure_inline_policies = mock.MagicMock()
        self.actor._ensure_groups = mock.MagicMock()

        yield self.actor._execute()

        self.assertTrue(self.actor._ensure_entity.called)
        self.assertFalse(self.actor._ensure_inline_policies.called)
        self.assertFalse(self.actor._ensure_groups.called)


class TestGroup(testing.AsyncTestCase):
    def setUp(self):
        super(TestGroup, self).setUp()
        settings.AWS_ACCESS_KEY_ID = "unit-test"
        settings.AWS_SECRET_ACCESS_KEY = "unit-test"
        settings.AWS_SESSION_TOKEN = "unit-test"
        importlib.reload(iam)

        # Create our actor object with some basics... then mock out the IAM
        # connections..
        self.actor = iam.Group(
            "Unit Test",
            {
                "name": "test",
                "state": "present",
                "inline_policies": "examples/aws.iam.user/s3_example.json",
            },
        )

        self.iam_stubber = Stubber(self.actor.iam_conn)

    @testing.gen_test
    def test_get_group_users(self):
        self.iam_stubber.add_response(
            # API Call
            "get_group",
            # Response
            {
                "Group": {
                    "GroupName": "test",
                    "Path": "/",
                    "Arn": ".........................",
                    "GroupId": ".................",
                    "CreateDate": datetime(2015, 1, 1),
                },
                "Users": [
                    {
                        "UserName": "user1",
                        "UserId": ".............................",
                        "Path": "/",
                        "Arn": ".............................",
                        "CreateDate": datetime(2015, 1, 1),
                    },
                    {
                        "UserName": "user2",
                        "UserId": ".............................",
                        "Path": "/",
                        "Arn": ".............................",
                        "CreateDate": datetime(2015, 1, 1),
                    },
                ],
            },
            # Request
            {"GroupName": "test"},
        )
        self.iam_stubber.activate()
        ret = yield self.actor._get_group_users("test")
        self.assertEqual(ret, ["user1", "user2"])
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_get_group_users_500(self):
        self.iam_stubber.add_client_error("get_group", 500, "Yikes")
        self.iam_stubber.activate()
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._get_group_users("test")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_get_group_users_no_users(self):
        self.iam_stubber.add_response(
            # API Call
            "get_group",
            # Response
            {
                "Group": {
                    "GroupName": "test",
                    "Path": "/",
                    "Arn": ".........................",
                    "GroupId": ".................",
                    "CreateDate": datetime(2015, 1, 1),
                },
                "Users": [],
            },
            # Request
            {"GroupName": "test"},
        )
        self.iam_stubber.activate()
        ret = yield self.actor._get_group_users("test")
        self.assertEqual(ret, [])
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_purge_group_users_false(self):
        users = ["user1", "user2"]
        self.actor._get_group_users = mock.MagicMock()
        self.actor._get_group_users.side_effect = [tornado_value(users)]

        self.actor._remove_user_from_group = mock.MagicMock()
        self.actor._remove_user_from_group.side_effect = [
            tornado_value(None),
            tornado_value(None),
        ]

        yield self.actor._purge_group_users("test", False)

        self.assertFalse(self.actor._remove_user_from_group.called)

    @testing.gen_test
    def test_purge_group_users_true(self):
        users = ["user1", "user2"]
        self.actor._get_group_users = mock.MagicMock()
        self.actor._get_group_users.side_effect = [tornado_value(users)]

        self.actor._remove_user_from_group = mock.MagicMock()
        self.actor._remove_user_from_group.side_effect = [
            tornado_value(None),
            tornado_value(None),
        ]

        yield self.actor._purge_group_users("test", True)

        self.actor._remove_user_from_group.assert_has_calls(
            [mock.call("user1", "test"), mock.call("user2", "test")]
        )

    @testing.gen_test
    def test_execute_absent(self):
        self.actor._options["state"] = "absent"
        self.actor._purge_group_users = mock.MagicMock()
        self.actor._purge_group_users.side_effect = [tornado_value(None)]
        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_entity.called)
        self.assertTrue(self.actor._purge_group_users.called)

    @testing.gen_test
    def test_execute_present(self):
        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_inline_policies = mock.MagicMock()
        self.actor._purge_group_users = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]
        self.actor._ensure_inline_policies.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_entity.called)
        self.assertFalse(self.actor._purge_group_users.called)

    @testing.gen_test
    def test_execute_present_no_policies_or_groups(self):
        self.actor._options["inline_policies"] = None
        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_inline_policies = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]
        self.actor._ensure_inline_policies.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_entity.called)
        self.assertFalse(self.actor._ensure_inline_policies.called)


class TestRole(testing.AsyncTestCase):
    def setUp(self):
        super(TestRole, self).setUp()
        settings.AWS_ACCESS_KEY_ID = "unit-test"
        settings.AWS_SECRET_ACCESS_KEY = "unit-test"
        settings.AWS_SESSION_TOKEN = "unit-test"
        importlib.reload(iam)

        # Create our actor object with some basics... then mock out the IAM
        # connections..
        self.actor = iam.Role(
            "Unit Test",
            {
                "name": "test",
                "state": "present",
                "assume_role_policy_document": "examples/aws.iam.role/lambda.json",
                "inline_policies": "examples/aws.iam.user/s3_example.json",
            },
        )

        self.iam_stubber = Stubber(self.actor.iam_conn)

    @testing.gen_test
    def test_ensure_assume_role_doc_no_entity(self):
        fake_entity = None
        self.actor._get_entity = mock.MagicMock()
        self.actor._get_entity.side_effect = [tornado_value(fake_entity)]

        yield self.actor._ensure_assume_role_doc("test")

    @testing.gen_test
    def test_ensure_assume_role_doc_matches(self):
        # This is the desired doc...
        self.actor.assume_role_policy_doc = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }

        self.iam_stubber.add_response(
            # API Call
            "get_role",
            # Response
            {
                "Role": {
                    "Arn": "....................................",
                    "Path": "/",
                    "RoleId": ".........................",
                    "RoleName": "test",
                    "CreateDate": datetime(2019, 2, 19, 21, 3, 20),
                    "AssumeRolePolicyDocument": json.dumps(
                        self.actor.assume_role_policy_doc
                    ),
                }
            },
            # Call Params
            {"RoleName": "test"},
        )
        self.iam_stubber.activate()
        yield self.actor._ensure_assume_role_doc("test")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_ensure_assume_role_doc_mismatch(self):
        # This is the desired doc...
        self.actor.assume_role_policy_doc = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }

        self.iam_stubber.add_response(
            # API Call
            "get_role",
            # Response
            {
                "Role": {
                    "Arn": "....................................",
                    "Path": "/",
                    "RoleId": ".........................",
                    "RoleName": "test",
                    "CreateDate": datetime(2019, 2, 19, 21, 3, 20),
                    "AssumeRolePolicyDocument": "{}",
                }
            },
            # Call Params
            {"RoleName": "test"},
        )

        self.iam_stubber.add_response(
            # API Call
            "update_assume_role_policy",
            # Response
            {},
            # Call Params
            {
                "RoleName": "test",
                "PolicyDocument": json.dumps(self.actor.assume_role_policy_doc),
            },
        )
        self.iam_stubber.activate()
        yield self.actor._ensure_assume_role_doc("test")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_ensure_assume_role_doc_mismatch_dry(self):
        self.actor._dry = True
        self.actor.assume_role_policy_doc = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
        self.iam_stubber.add_response(
            # API Call
            "get_role",
            # Response
            {
                "Role": {
                    "Arn": "....................................",
                    "Path": "/",
                    "RoleId": ".........................",
                    "RoleName": "test",
                    "CreateDate": datetime(2019, 2, 19, 21, 3, 20),
                    "AssumeRolePolicyDocument": "{}",
                }
            },
            # Call Params
            {"RoleName": "test"},
        )
        self.iam_stubber.activate()
        yield self.actor._ensure_assume_role_doc("test")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_execute_absent(self):
        self.actor._options["state"] = "absent"
        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]
        self.actor._ensure_assume_role_doc = mock.MagicMock()
        self.actor._ensure_assume_role_doc.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_entity.called)
        self.assertFalse(self.actor._ensure_assume_role_doc.called)

    @testing.gen_test
    def test_execute_no_policy(self):
        self.actor._options["assume_role_policy_document"] = None
        self.actor._options["inline_policies"] = None
        self.iam_stubber.activate()
        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]
        self.actor._ensure_assume_role_doc = mock.MagicMock()
        self.actor._ensure_assume_role_doc.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_entity.called)
        self.assertTrue(self.actor._ensure_assume_role_doc.called)
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_execute(self):
        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]
        self.actor._ensure_inline_policies = mock.MagicMock()
        self.actor._ensure_inline_policies.side_effect = [tornado_value(None)]
        self.actor._ensure_assume_role_doc = mock.MagicMock()
        self.actor._ensure_assume_role_doc.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_entity.called)
        self.assertTrue(self.actor._ensure_inline_policies.called)
        self.assertTrue(self.actor._ensure_assume_role_doc.called)

    @testing.gen_test
    def test_create_entity(self):
        self.actor.assume_role_policy_doc = "{}"
        self.actor._dry = False
        self.iam_stubber.add_response(
            # API Call
            "create_role",
            # Response,
            {
                "Role": {
                    "Arn": "arn:.................",
                    "Path": "/",
                    "RoleName": "test",
                    "RoleId": "AQ..............C...",
                    "CreateDate": datetime(2015, 1, 1),
                }
            },
            # Call Params
            {"RoleName": "test", "AssumeRolePolicyDocument": '"{}"'},
        )
        self.iam_stubber.activate()
        yield self.actor._create_entity("test")
        self.iam_stubber.assert_no_pending_responses()


class TestInstanceProfile(testing.AsyncTestCase):
    def setUp(self):
        super(TestInstanceProfile, self).setUp()
        settings.AWS_ACCESS_KEY_ID = "unit-test"
        settings.AWS_SECRET_ACCESS_KEY = "unit-test"
        settings.AWS_SESSION_TOKEN = "unit-test"
        importlib.reload(iam)

        # Create our actor object with some basics... then mock out the IAM
        # connections..
        self.actor = iam.InstanceProfile(
            "Unit Test", {"name": "test", "state": "present", "role": "test"}
        )

        self.iam_stubber = Stubber(self.actor.iam_conn)

    @testing.gen_test
    def test_add_role(self):
        self.iam_stubber.add_response(
            # API Call
            "add_role_to_instance_profile",
            # Response
            {},
            # Call Params
            {"InstanceProfileName": "test", "RoleName": "testrole"},
        )
        self.iam_stubber.activate()
        yield self.actor._add_role("test", "testrole")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_add_role_409(self):
        self.iam_stubber.add_client_error(
            "add_role_to_instance_profile", 409, "NoSuchEntity"
        )
        self.iam_stubber.activate()
        yield self.actor._add_role("test", "testrole")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_add_role_500(self):
        self.iam_stubber.add_client_error("add_role_to_instance_profile", 500, "Yikes")
        self.iam_stubber.activate()
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._add_role("test", "testrole")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_add_role_dry(self):
        self.actor._dry = True
        self.iam_stubber.activate()
        yield self.actor._add_role("test", "testrole")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_remove_role(self):
        self.iam_stubber.add_response(
            # API Call
            "remove_role_from_instance_profile",
            # Response
            {},
            # Call Params
            {"InstanceProfileName": "test", "RoleName": "testrole"},
        )
        self.iam_stubber.activate()
        yield self.actor._remove_role("test", "testrole")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_remove_role_404(self):
        self.iam_stubber.add_client_error(
            "remove_role_from_instance_profile", 404, "NoSuchEntity"
        )
        self.iam_stubber.activate()
        yield self.actor._remove_role("test", "testrole")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_remove_role_500(self):
        self.iam_stubber.add_client_error(
            "remove_role_from_instance_profile", 500, "Yikes"
        )
        self.iam_stubber.activate()
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._remove_role("test", "testrole")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_remove_role_dry(self):
        self.actor._dry = True
        self.iam_stubber.activate()
        yield self.actor._remove_role("test", "testrole")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_ensure_role_matching(self):
        self.iam_stubber.add_response(
            # API Call
            "get_instance_profile",
            # Response
            {
                "InstanceProfile": {
                    "Arn": "arn:aws:iam::...:instance-profile/...",
                    "CreateDate": datetime(2016, 9, 28, 19, 23, 4),
                    "InstanceProfileId": "...................",
                    "InstanceProfileName": "test",
                    "Path": "/",
                    "Roles": [
                        {
                            "Arn": "......................................",
                            "AssumeRolePolicyDocument": "{}",
                            "CreateDate": datetime(2016, 9, 28, 19, 23, 4),
                            "Path": "/",
                            "RoleId": ".....................",
                            "RoleName": "test-role",
                        }
                    ],
                    "Tags": [],
                },
            },
            # Call Params
            {"InstanceProfileName": "test"},
        )
        self.iam_stubber.activate()
        yield self.actor._ensure_role("test", "test-role")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_ensure_role_with_no_role_set_and_is_missing_correctly(self):
        self.iam_stubber.add_response(
            # API Call
            "get_instance_profile",
            # Response
            {
                "InstanceProfile": {
                    "Arn": "arn:aws:iam::...:instance-profile/...",
                    "CreateDate": datetime(2016, 9, 28, 19, 23, 4),
                    "InstanceProfileId": "...................",
                    "InstanceProfileName": "test",
                    "Path": "/",
                    "Roles": [],
                    "Tags": [],
                },
            },
            # Call Params
            {"InstanceProfileName": "test"},
        )
        self.iam_stubber.activate()
        yield self.actor._ensure_role("test", None)
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_ensure_role_existing_role_but_want_none(self):
        self.iam_stubber.add_response(
            # API Call
            "get_instance_profile",
            # Response
            {
                "InstanceProfile": {
                    "Arn": "arn:aws:iam::...:instance-profile/...",
                    "CreateDate": datetime(2016, 9, 28, 19, 23, 4),
                    "InstanceProfileId": "...................",
                    "InstanceProfileName": "test",
                    "Path": "/",
                    "Roles": [
                        {
                            "Arn": "......................................",
                            "AssumeRolePolicyDocument": "{}",
                            "CreateDate": datetime(2016, 9, 28, 19, 23, 4),
                            "Path": "/",
                            "RoleId": ".....................",
                            "RoleName": "wrong-role",
                        }
                    ],
                    "Tags": [],
                },
            },
            # Call Params
            {"InstanceProfileName": "test"},
        )

        self.iam_stubber.add_response(
            # API Call
            "remove_role_from_instance_profile",
            # Response
            {},
            # Call Params
            {"InstanceProfileName": "test", "RoleName": "wrong-role"},
        )
        self.iam_stubber.activate()
        yield self.actor._ensure_role("test", None)
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_ensure_role_not_matching(self):
        self.iam_stubber.add_response(
            # API Call
            "get_instance_profile",
            # Response
            {
                "InstanceProfile": {
                    "Arn": "arn:aws:iam::...:instance-profile/...",
                    "CreateDate": datetime(2016, 9, 28, 19, 23, 4),
                    "InstanceProfileId": "...................",
                    "InstanceProfileName": "test",
                    "Path": "/",
                    "Roles": [
                        {
                            "Arn": "......................................",
                            "AssumeRolePolicyDocument": "{}",
                            "CreateDate": datetime(2016, 9, 28, 19, 23, 4),
                            "Path": "/",
                            "RoleId": ".....................",
                            "RoleName": "wrong-role",
                        }
                    ],
                    "Tags": [],
                },
            },
            # Call Params
            {"InstanceProfileName": "test"},
        )

        self.iam_stubber.add_response(
            # API Call
            "remove_role_from_instance_profile",
            # Response
            {},
            # Call Params
            {"InstanceProfileName": "test", "RoleName": "wrong-role"},
        )

        self.iam_stubber.add_response(
            # API Call
            "add_role_to_instance_profile",
            # Response
            {},
            # Call Params
            {"InstanceProfileName": "test", "RoleName": "test-role"},
        )
        self.iam_stubber.activate()
        yield self.actor._ensure_role("test", "test-role")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_ensure_role_matching_404(self):
        self.iam_stubber.add_client_error("get_instance_profile", 404, "NoSuchEntity")
        self.iam_stubber.add_response(
            # API Call
            "add_role_to_instance_profile",
            # Response
            {},
            # Call parms
            {"InstanceProfileName": "test", "RoleName": "test-role"},
        )
        self.iam_stubber.activate()
        yield self.actor._ensure_role("test", "test-role")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_ensure_role_matching_500(self):
        self.iam_stubber.add_client_error("get_instance_profile", 500, "Yikes")
        self.iam_stubber.activate()
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._ensure_role("test", "test-role")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_ensure_role_matching_key_error(self):
        self.iam_stubber.add_response(
            # API Call
            "get_instance_profile",
            # Response
            {
                "InstanceProfile": {
                    "Arn": "arn:aws:iam::...:instance-profile/...",
                    "CreateDate": datetime(2016, 9, 28, 19, 23, 4),
                    "InstanceProfileId": "...................",
                    "InstanceProfileName": "test",
                    "Path": "/",
                    "Roles": [],
                    "Tags": [],
                },
            },
            # Call Params
            {"InstanceProfileName": "test"},
        )

        self.iam_stubber.add_response(
            # API Call
            "add_role_to_instance_profile",
            # Response
            {},
            # Call parms
            {"InstanceProfileName": "test", "RoleName": "test-role"},
        )
        self.iam_stubber.activate()
        yield self.actor._ensure_role("test", "test-role")
        self.iam_stubber.assert_no_pending_responses()

    @testing.gen_test
    def test_execute_absent(self):
        self.actor._options["state"] = "absent"
        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_entity.called)

    @testing.gen_test
    def test_execute(self):
        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_role = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]
        self.actor._ensure_role.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_entity.called)
        self.assertTrue(self.actor._ensure_role.called)

    @testing.gen_test
    def test_execute_no_role(self):
        self.actor._options["role"] = None
        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]
        self.actor._ensure_role = mock.MagicMock()
        self.actor._ensure_role.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_entity.called)
        self.assertFalse(self.actor._ensure_role.called)
