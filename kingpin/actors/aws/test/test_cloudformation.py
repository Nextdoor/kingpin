import datetime
import importlib
import json
import logging
import unittest
from unittest import mock
from unittest.mock import AsyncMock

import boto3
from botocore.exceptions import ClientError

from kingpin.actors.aws import base, cloudformation, settings

log = logging.getLogger(__name__)


def create_fake_stack(name, status):
    fake_stack = {
        "StackId": f"arn:aws:cloudformation:us-east-1:xxxx:stack/{name}/x",
        "LastUpdatedTime": datetime.datetime.now(),
        "TemplateDescription": f"Fake Template {name}",
        "CreationTime": datetime.datetime.now(),
        "StackName": name,
        "StackStatus": status,
        "StackStatusReason": "Fake Reason",
        "EnableTerminationProtection": False,
        "Parameters": [{"ParameterKey": "key1", "ParameterValue": "value1"}],
    }
    return fake_stack


def create_fake_stack_event(name, resource, status, reason=None):
    fake_event = {
        "EventId": "264322b0-2426-11e6-aaa1-500c28b32ed2",
        "LogicalResourceId": resource,
        "PhysicalResourceId": f"arn:aws:cfn:us-east-1:x:stack/{name}/abc",
        "ResourceStatus": status,
        "ResourceType": "AWS::CloudFormation::Stack",
        "StackId": f"arn:aws:cfn:us-east-1:xxx:stack/{name}/xyz",
        "StackName": name,
        "Timestamp": datetime.datetime.now(),
    }

    if reason:
        fake_event["ResourceStatusReason"] = reason

    return fake_event


class TestCloudFormationBaseActor(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        settings.AWS_ACCESS_KEY_ID = "unit-test"
        settings.AWS_SECRET_ACCESS_KEY = "unit-test"
        settings.AWS_SESSION_TOKEN = "unit-test"
        importlib.reload(cloudformation)

        self.actor = cloudformation.CloudFormationBaseActor(
            "unittest", {"region": "us-east-1"}
        )
        self.actor.cfn_conn = mock.MagicMock(name="cfn_conn")

        # Need to recreate the api call queues between tests
        # because nose creates a new ioloop per test run.
        base.NAMED_API_CALL_QUEUES = {}

    def test_discover_noecho_params(self):
        file = "examples/test/aws.cloudformation/cfn.integration.json"
        body, url = self.actor._get_template_body(file, None)
        ret = self.actor._discover_noecho_params(body)
        self.assertEqual(ret, ["BucketPassword"])

    def test_get_template_body(self):
        file = "examples/test/aws.cloudformation/cfn.unittest.json"

        # Should work...
        ret = self.actor._get_template_body(file, None)
        expected = ('{"blank": "json"}', None)
        self.assertEqual(ret, expected)

        # Should return None
        ret = self.actor._get_template_body(None, None)
        expected = (None, None)
        self.assertEqual(ret, expected)

    def test_get_template_body_s3(self):
        url = "s3://bucket/foobar.json"
        self.actor.s3_conn = mock.MagicMock(name="s3_conn")
        self.actor.s3_conn.get_bucket_location.return_value = {
            "LocationConstraint": None
        }

        expected_template = '{"fake": "template"}'
        with mock.patch.object(self.actor, "get_s3_client") as mock_get:
            mock_s3 = mock.MagicMock()
            mock_body = mock.MagicMock()
            mock_body.read.return_value = expected_template
            mock_s3.get_object.return_value = {"Body": mock_body}
            mock_get.return_value = mock_s3

            ret = self.actor._get_template_body(url, None)
            expected = (
                expected_template,
                "https://bucket.s3.us-east-1.amazonaws.com/foobar.json",
            )
            self.assertEqual(ret, expected)

        # Should raise exception
        with self.assertRaises(cloudformation.InvalidTemplate):
            self.actor._get_template_body("missing", None)

    def test_get_template_body_s3_read_failure(self):
        url = "s3://bucket/foobar.json"
        self.actor.s3_conn = mock.MagicMock(name="s3_conn")
        self.actor.s3_conn.get_bucket_location.return_value = {
            "LocationConstraint": None
        }

        with mock.patch.object(self.actor, "get_s3_client") as mock_get:
            mock_s3 = mock.MagicMock()
            mock_s3.get_object.side_effect = ClientError({}, "FakeOperation")
            mock_get.return_value = mock_s3

            with self.assertRaises(cloudformation.InvalidTemplate):
                self.actor._get_template_body(url, None)

    def test_get_template_body_bad_s3_path(self):
        url = "s3://bucket-foobar.json"
        with self.assertRaises(cloudformation.InvalidTemplate):
            self.actor._get_template_body(url, None)

    def test_get_s3_client(self):
        self.actor.get_s3_client("us-east-1")

    async def test_validate_template_body(self):
        await self.actor._validate_template(body="test body")
        self.actor.cfn_conn.validate_template.assert_called_with(
            TemplateBody="test body"
        )

    async def test_validate_template_url(self):
        await self.actor._validate_template(url="http://foobar.json")
        self.actor.cfn_conn.validate_template.assert_called_with(
            TemplateURL="http://foobar.json"
        )

    async def test_validate_template_raises_boto_error(self):
        fake_exc = {
            "ResponseMetadata": {
                "HTTPStatusCode": 400,
                "RequestId": "dfc1a12c-22c1-11e6-80b1-8fd4cf167f54",
            },
            "Error": {
                "Message": "Template format error: JSON not well-formed",
                "Code": "ValidationError",
                "Type": "Sender",
            },
        }

        self.actor.cfn_conn.validate_template.side_effect = ClientError(
            fake_exc, "FakeOperation"
        )
        with self.assertRaises(cloudformation.InvalidTemplate):
            await self.actor._validate_template(url="junk")

        with self.assertRaises(cloudformation.InvalidTemplate):
            await self.actor._validate_template(body="junk")

    def test_create_parameters(self):
        params = {
            "Key1": "Value1",
            "Key2": "Value2",
        }

        expected = [
            {"ParameterKey": "Key1", "ParameterValue": "Value1"},
            {"ParameterKey": "Key2", "ParameterValue": "Value2"},
        ]

        actor = cloudformation.CloudFormationBaseActor(
            "unittest", {"region": "us-east-1"}
        )

        ret = actor._create_parameters(params)
        self.assertEqual(ret, expected)

    async def test_get_stack(self):
        self.actor.cfn_conn.describe_stacks.return_value = {
            "Stacks": [create_fake_stack("s1", "UPDATE_COMPLETE")]
        }

        ret = await self.actor._get_stack("s1")
        self.assertEqual(ret["StackName"], "s1")

    async def test_get_stack_not_found(self):
        fake_exc = {
            "ResponseMetadata": {
                "HTTPStatusCode": 400,
                "RequestId": "dfc1a12c-22c1-11e6-80b1-8fd4cf167f54",
            },
            "Error": {
                "Message": "Stack with id s1 does not exist",
                "Code": "ExecutionFailure",
                "Type": "Sender",
            },
        }
        self.actor.cfn_conn.describe_stacks.side_effect = ClientError(
            fake_exc, "Failure"
        )

        ret = await self.actor._get_stack("s1")
        self.assertEqual(ret, None)

    async def test_get_stack_exc(self):
        fake_exc = {
            "ResponseMetadata": {
                "HTTPStatusCode": 400,
                "RequestId": "dfc1a12c-22c1-11e6-80b1-8fd4cf167f54",
            },
            "Error": {
                "Message": "Some other error",
                "Code": "ExecutionFailure",
                "Type": "Sender",
            },
        }
        self.actor.cfn_conn.describe_stacks.side_effect = ClientError(
            fake_exc, "Failure"
        )

        with self.assertRaises(cloudformation.CloudFormationError):
            await self.actor._get_stack("s1")

    async def test_get_stack_template(self):
        fake_stack_template = {
            "ResponseMetadata": {
                "HTTPStatusCode": 200,
                "RequestId": "6dcafb4c-2768-11e6-b748-295d1284a76f",
            },
            "TemplateBody": {"Fake": "Stack"},
        }
        self.actor.cfn_conn.get_template.return_value = fake_stack_template

        ret = await self.actor._get_stack_template("test")

        self.actor.cfn_conn.get_template.assert_has_calls(
            [mock.call(StackName="test", TemplateStage="Original")]
        )
        self.assertEqual(ret, {"Fake": "Stack"})

    async def test_get_stack_template_exc(self):
        fake_exc = {
            "ResponseMetadata": {
                "HTTPStatusCode": 400,
                "RequestId": "dfc1a12c-22c1-11e6-80b1-8fd4cf167f54",
            },
            "Error": {
                "Message": "Some other error",
                "Code": "ExecutionFailure",
                "Type": "Sender",
            },
        }
        self.actor.cfn_conn.get_template.side_effect = ClientError(fake_exc, "Failure")
        with self.assertRaises(cloudformation.CloudFormationError):
            await self.actor._get_stack_template("test")

    async def test_wait_until_state_complete(self):
        create_in_progress = create_fake_stack("test", "CREATE_IN_PROGRESS")
        create_complete = create_fake_stack("test", "CREATE_COMPLETE")

        # Make _get_stack() await back 2 in-progress states, then await a
        # successfull execution.
        self.actor._get_stack = AsyncMock(name="FakeStack")
        self.actor._get_stack.side_effect = [
            create_in_progress,
            create_in_progress,
            create_complete,
        ]
        await self.actor._wait_until_state("test", cloudformation.COMPLETE, sleep=0.01)
        self.actor._get_stack.assert_has_calls(
            [mock.call("test"), mock.call("test"), mock.call("test")]
        )

    async def test_wait_until_state_stack_failed(self):
        create_in_progress = create_fake_stack("test", "CREATE_IN_PROGRESS")
        create_complete = create_fake_stack("test", "CREATE_COMPLETE")

        # Make sure a cloudformationerror is raised if we ask for a deleted
        # state rather than a created one.
        self.actor._get_stack = AsyncMock(name="FakeStack")
        self.actor._get_stack.side_effect = [
            create_in_progress,
            create_in_progress,
            create_complete,
        ]
        with self.assertRaises(cloudformation.StackFailed):
            await self.actor._wait_until_state(
                "test", cloudformation.DELETED, sleep=0.1
            )

    async def test_wait_until_state_stack_not_found(self):
        # Lastly, test that if wait_until_state returns no actor, we bail
        # appropriately.
        self.actor._get_stack = AsyncMock(name="FakeStack")
        self.actor._get_stack.return_value = None
        with self.assertRaises(cloudformation.StackNotFound):
            await self.actor._wait_until_state(
                "test", cloudformation.COMPLETE, sleep=0.1
            )

    async def test_get_stack_events(self):
        fake_events = {
            "StackEvents": [
                create_fake_stack_event("test", "test", "DELETE_COMPLETE"),
                create_fake_stack_event("test", "s3", "DELETE_COMPLETE"),
                create_fake_stack_event("test", "s3", "DELETE_IN_PROGRESS"),
                create_fake_stack_event("test", "s3", "CREATE_FAILED", "bad"),
                create_fake_stack_event("test", "s3", "CREATE_IN_PROGRESS"),
                create_fake_stack_event("test", "test", "CREATE_IN_PROGRESS"),
            ]
        }
        expected = [
            "AWS::CloudFormation::Stack test (CREATE_IN_PROGRESS): ",
            "AWS::CloudFormation::Stack s3 (CREATE_IN_PROGRESS): ",
            "AWS::CloudFormation::Stack s3 (CREATE_FAILED): bad",
            "AWS::CloudFormation::Stack s3 (DELETE_IN_PROGRESS): ",
            "AWS::CloudFormation::Stack s3 (DELETE_COMPLETE): ",
            "AWS::CloudFormation::Stack test (DELETE_COMPLETE): ",
        ]
        self.actor.cfn_conn.describe_stack_events.return_value = fake_events
        ret = await self.actor._get_stack_events("test")

        self.assertEqual(ret, expected)

    async def test_get_stack_events_exc(self):
        fake_exc = {
            "ResponseMetadata": {
                "HTTPStatusCode": 400,
                "RequestId": "dfc1a12c-22c1-11e6-80b1-8fd4cf167f54",
            },
            "Error": {
                "Message": "Some other error",
                "Code": "ExecutionFailure",
                "Type": "Sender",
            },
        }
        self.actor.cfn_conn.describe_stack_events.side_effect = ClientError(
            fake_exc, "Failure"
        )
        ret = await self.actor._get_stack_events("test")
        self.assertEqual(ret, [])

    async def test_delete_stack(self):
        self.actor.cfn_conn.delete_stack.return_value = {
            "ResponseMetadata": {"RequestId": "req-id-1"}
        }
        self.actor._wait_until_state = AsyncMock(name="_wait_until_state")
        exc = cloudformation.StackNotFound()
        self.actor._wait_until_state.side_effect = exc

        await self.actor._delete_stack(stack="stack")

        self.assertTrue(self.actor.cfn_conn.delete_stack.called)
        self.assertTrue(self.actor._wait_until_state.called)

    async def test_delete_stack_raises_boto_error(self):
        self.actor.cfn_conn.delete_stack = mock.MagicMock(name="delete_stack")

        fake_exc = {
            "ResponseMetadata": {
                "HTTPStatusCode": 400,
                "RequestId": "dfc1a12c-22c1-11e6-80b1-8fd4cf167f54",
            },
            "Error": {
                "Message": "Something failed",
                "Code": "ExecutionFailure",
                "Type": "Sender",
            },
        }

        self.actor.cfn_conn.delete_stack.side_effect = ClientError(fake_exc, "Error")
        with self.assertRaises(cloudformation.CloudFormationError):
            await self.actor._delete_stack(stack="stack")


class TestCreate(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        settings.AWS_ACCESS_KEY_ID = "unit-test"
        settings.AWS_SECRET_ACCESS_KEY = "unit-test"
        settings.AWS_SESSION_TOKEN = "unit-test"
        settings.KINGPIN_CFN_DEFAULT_ROLE_ARN = None
        importlib.reload(cloudformation)
        # Need to recreate the api call queues between tests
        # because nose creates a new ioloop per test run.
        base.NAMED_API_CALL_QUEUES = {}

    async def test_create_stack_file(self):
        actor = cloudformation.Create(
            "Unit Test Action",
            {
                "name": "unit-test-cfn",
                "region": "us-west-2",
                "template": "examples/test/aws.cloudformation/cfn.integration.json",
            },
        )
        actor._wait_until_state = AsyncMock(name="_wait_until_state")
        actor._wait_until_state.side_effect = [None]
        actor.cfn_conn.create_stack = mock.MagicMock(name="create_stack_mock")
        actor.cfn_conn.create_stack.return_value = {"StackId": "arn:123"}
        ret = await actor._create_stack(stack="test")
        self.assertEqual(ret, "arn:123")

    async def test_create_stack_file_with_role(self):
        stack = "examples/test/aws.cloudformation/cfn.integration.json"
        actor = cloudformation.Create(
            "Unit Test Action",
            {
                "name": "unit-test-cfn",
                "region": "us-west-2",
                "role_arn": "test_role_arn",
                "template": stack,
            },
        )
        actor._wait_until_state = AsyncMock(name="_wait_until_state")
        actor._wait_until_state.side_effect = [None]
        actor.cfn_conn.create_stack = mock.MagicMock(name="create_stack_mock")
        actor.cfn_conn.create_stack.return_value = {"StackId": "arn:123"}
        ret = await actor._create_stack(stack="test")
        self.assertEqual(ret, "arn:123")
        actor.cfn_conn.create_stack.assert_called_with(
            TemplateBody=mock.ANY,
            EnableTerminationProtection=False,
            Parameters=[],
            RoleARN="test_role_arn",
            TimeoutInMinutes=60,
            Capabilities=[],
            StackName="test",
            OnFailure="DELETE",
        )

    async def test_create_stack_file_with_default_role(self):
        settings.KINGPIN_CFN_DEFAULT_ROLE_ARN = "test-default-role-arn"
        importlib.reload(cloudformation)

        stack = "examples/test/aws.cloudformation/cfn.integration.json"
        actor = cloudformation.Create(
            "Unit Test Action",
            {
                "name": "unit-test-cfn",
                "region": "us-west-2",
                "template": stack,
            },
        )
        actor._wait_until_state = AsyncMock(name="_wait_until_state")
        actor._wait_until_state.side_effect = [None]
        actor.cfn_conn.create_stack = mock.MagicMock(name="create_stack_mock")
        actor.cfn_conn.create_stack.return_value = {"StackId": "arn:123"}
        ret = await actor._create_stack(stack="test")
        self.assertEqual(ret, "arn:123")
        actor.cfn_conn.create_stack.assert_called_with(
            TemplateBody=mock.ANY,
            EnableTerminationProtection=False,
            Parameters=[],
            RoleARN="test-default-role-arn",
            TimeoutInMinutes=60,
            Capabilities=[],
            StackName="test",
            OnFailure="DELETE",
        )

    async def test_create_stack_file_with_role_yaml(self):
        stack = "examples/test/aws.cloudformation/cfn.integration.yaml"
        actor = cloudformation.Create(
            "Unit Test Action",
            {
                "name": "unit-test-cfn",
                "region": "us-west-2",
                "role_arn": "test_role_arn",
                "template": stack,
            },
        )
        actor._wait_until_state = AsyncMock(name="_wait_until_state")
        actor._wait_until_state.side_effect = [None]
        actor.cfn_conn.create_stack = mock.MagicMock(name="create_stack_mock")
        actor.cfn_conn.create_stack.return_value = {"StackId": "arn:123"}
        ret = await actor._create_stack(stack="test")
        self.assertEqual(ret, "arn:123")
        actor.cfn_conn.create_stack.assert_called_with(
            TemplateBody=mock.ANY,
            EnableTerminationProtection=False,
            Parameters=[],
            RoleARN="test_role_arn",
            TimeoutInMinutes=60,
            Capabilities=[],
            StackName="test",
            OnFailure="DELETE",
        )

    async def test_create_stack_file_with_termination_protection_true(self):
        stack = "examples/test/aws.cloudformation/cfn.integration.json"
        actor = cloudformation.Create(
            "Unit Test Action",
            {
                "name": "unit-test-cfn",
                "region": "us-west-2",
                "role_arn": "test_role_arn",
                "template": stack,
            },
        )
        actor._options["enable_termination_protection"] = True
        actor._wait_until_state = AsyncMock(name="_wait_until_state")
        actor._wait_until_state.side_effect = [None]
        actor.cfn_conn.create_stack = mock.MagicMock(name="create_stack_mock")
        actor.cfn_conn.create_stack.return_value = {"StackId": "arn:123"}
        ret = await actor._create_stack(stack="test")
        self.assertEqual(ret, "arn:123")
        actor.cfn_conn.create_stack.assert_called_with(
            TemplateBody=mock.ANY,
            EnableTerminationProtection=True,
            Parameters=[],
            RoleARN="test_role_arn",
            TimeoutInMinutes=60,
            Capabilities=[],
            StackName="test",
            OnFailure="DELETE",
        )

    async def test_create_stack_url(self):
        with mock.patch.object(boto3, "client"):
            with mock.patch.object(
                cloudformation.CloudFormationBaseActor,
                "_get_template_body",
                return_value=(
                    '{"fake": "template"}',
                    "https://bucket.s3.us-west-2.amazonaws.com/key",
                ),
            ):
                actor = cloudformation.Create(
                    "Unit Test Action",
                    {
                        "name": "unit-test-cfn",
                        "region": "us-west-2",
                        "template": "s3://bucket/key",
                    },
                )
        actor._wait_until_state = AsyncMock(name="_wait_until_state")
        actor._wait_until_state.side_effect = [None]
        actor.cfn_conn.create_stack = mock.MagicMock(name="create_stack_mock")
        actor.cfn_conn.create_stack.return_value = {"StackId": "arn:123"}
        ret = await actor._create_stack(stack="unit-test-cfn")
        self.assertEqual(ret, "arn:123")

    async def test_create_stack_raises_boto_error(self):
        actor = cloudformation.Create(
            "Unit Test Action",
            {
                "name": "unit-test-cfn",
                "region": "us-west-2",
                "template": "examples/test/aws.cloudformation/cfn.integration.json",
            },
        )
        actor.cfn_conn.create_stack = mock.MagicMock(name="create_stack_mock")

        fake_exc = {
            "ResponseMetadata": {
                "HTTPStatusCode": 400,
                "RequestId": "dfc1a12c-22c1-11e6-80b1-8fd4cf167f54",
            },
            "Error": {
                "Message": "Something failed",
                "Code": "ExecutionFailure",
                "Type": "Sender",
            },
        }

        actor.cfn_conn.create_stack.side_effect = ClientError(fake_exc, "Failure")
        with self.assertRaises(cloudformation.CloudFormationError):
            await actor._create_stack(stack="test")

    async def test_create_stack_wait_until_raises_boto_error(self):
        actor = cloudformation.Create(
            "Unit Test Action",
            {
                "name": "unit-test-cfn",
                "region": "us-west-2",
                "template": "examples/test/aws.cloudformation/cfn.integration.json",
            },
        )
        actor.cfn_conn.create_stack = mock.MagicMock(name="create_stack_mock")
        actor.cfn_conn.create_stack.return_value = {"StackId": "arn:123"}

        actor._wait_until_state = AsyncMock(name="_wait_until_state")
        actor._wait_until_state.side_effect = cloudformation.StackFailed()

        actor._get_stack_events = AsyncMock(name="_get_stack_events")
        actor._get_stack_events.return_value = ["Log Message"]

        with self.assertRaises(cloudformation.StackFailed):
            await actor._create_stack(stack="test")

    async def test_execute(self):
        actor = cloudformation.Create(
            "Unit Test Action",
            {
                "name": "unit-test-cfn",
                "region": "us-west-2",
                "template": "examples/test/aws.cloudformation/cfn.integration.json",
            },
        )

        actor._validate_template = AsyncMock(name="_validate_template")
        actor._validate_template.return_value = True

        actor._get_stack = AsyncMock(name="_get_stack")
        actor._get_stack.return_value = None

        actor._create_stack = AsyncMock(name="_create_stack")
        actor._create_stack.return_value = None

        actor._wait_until_state = AsyncMock(name="_wait_until_state")
        actor._wait_until_state.return_value = None
        await actor._execute()

    async def test_execute_exists(self):
        actor = cloudformation.Create(
            "Unit Test Action",
            {
                "name": "unit-test-cfn",
                "region": "us-west-2",
                "template": "examples/test/aws.cloudformation/cfn.integration.json",
            },
        )

        actor._validate_template = AsyncMock(name="_validate_template")
        actor._validate_template.return_value = True

        actor._get_stack = AsyncMock(name="_get_stack")
        actor._get_stack.return_value = True

        with self.assertRaises(cloudformation.StackAlreadyExists):
            await actor._execute()

    async def test_execute_dry(self):
        actor = cloudformation.Create(
            "Unit Test Action",
            {
                "name": "unit-test-cfn",
                "region": "us-west-2",
                "template": "examples/test/aws.cloudformation/cfn.integration.json",
            },
            dry=True,
        )

        actor._validate_template = AsyncMock(name="_validate_template")
        actor._validate_template.return_value = True

        actor._get_stack = AsyncMock(name="_get_stack")
        actor._get_stack.return_value = None

        await actor._execute()


class TestDelete(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        settings.AWS_ACCESS_KEY_ID = "unit-test"
        settings.AWS_SECRET_ACCESS_KEY = "unit-test"
        settings.AWS_SESSION_TOKEN = "unit-test"
        importlib.reload(cloudformation)
        # Need to recreate the api call queues between tests
        # because nose creates a new ioloop per test run.
        base.NAMED_API_CALL_QUEUES = {}

    async def test_execute(self):
        actor = cloudformation.Delete(
            "Unit Test Action", {"name": "unit-test-cfn", "region": "us-west-2"}
        )
        actor._get_stack = AsyncMock(name="_get_stack")
        actor._get_stack.return_value = True
        actor._delete_stack = AsyncMock(name="_delete_stack")
        actor._delete_stack.return_value = None
        actor._wait_until_state = AsyncMock(name="_wait_until_state")
        actor._wait_until_state.side_effect = cloudformation.StackNotFound()
        await actor._execute()

    async def test_execute_dry(self):
        actor = cloudformation.Delete(
            "Unit Test Action",
            {"name": "unit-test-cfn", "region": "us-west-2"},
            dry=True,
        )
        actor._get_stack = AsyncMock(name="_get_stack")
        actor._get_stack.return_value = True
        await actor._execute()

    async def test_execute_not_exists(self):
        actor = cloudformation.Delete(
            "Unit Test Action", {"name": "unit-test-cfn", "region": "us-west-2"}
        )
        actor._get_stack = AsyncMock(name="_get_stack")
        actor._get_stack.return_value = None
        with self.assertRaises(cloudformation.StackNotFound):
            await actor._execute()

    async def test_delete_stack_file_with_role(self):
        stack = "examples/test/aws.cloudformation/cfn.integration.json"
        actor = cloudformation.Delete(
            "Unit Test Action",
            {
                "name": "unit-test-cfn",
                "region": "us-west-2",
                "role_arn": "test_role_arn",
                "template": stack,
            },
        )
        actor.cfn_conn.describe_stacks = mock.MagicMock(name="describe_stacks_mock")
        actor.cfn_conn.describe_stacks.return_value = {
            "Stacks": [{"StackId": "arn:123"}]
        }
        actor.cfn_conn.delete_stack = mock.MagicMock(name="delete_stack_mock")
        actor.cfn_conn.delete_stack.return_value = {
            "ResponseMetadata": {"RequestId": "1234"}
        }
        actor._wait_until_state = AsyncMock(name="_wait_until_state")
        actor._wait_until_state.side_effect = [None]

        await actor._delete_stack(stack="test")
        actor.cfn_conn.delete_stack.assert_called_with(
            RoleARN="test_role_arn",
            StackName="test",
        )

    async def test_delete_stack_file_with_default_role(self):
        settings.KINGPIN_CFN_DEFAULT_ROLE_ARN = "test-default-role-arn"
        importlib.reload(cloudformation)

        stack = "examples/test/aws.cloudformation/cfn.integration.json"
        actor = cloudformation.Delete(
            "Unit Test Action",
            {
                "name": "unit-test-cfn",
                "region": "us-west-2",
                "template": stack,
            },
        )
        actor.cfn_conn.describe_stacks = mock.MagicMock(name="describe_stacks_mock")
        actor.cfn_conn.describe_stacks.return_value = {
            "Stacks": [{"StackId": "arn:123"}]
        }
        actor.cfn_conn.delete_stack = mock.MagicMock(name="delete_stack_mock")
        actor.cfn_conn.delete_stack.return_value = {
            "ResponseMetadata": {"RequestId": "1234"}
        }
        actor._wait_until_state = AsyncMock(name="_wait_until_state")
        actor._wait_until_state.side_effect = [None]

        await actor._delete_stack(stack="test")
        actor.cfn_conn.delete_stack.assert_called_with(
            RoleARN="test-default-role-arn",
            StackName="test",
        )


class TestStack(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        settings.AWS_ACCESS_KEY_ID = "unit-test"
        settings.AWS_SECRET_ACCESS_KEY = "unit-test"
        settings.AWS_SESSION_TOKEN = "unit-test"
        settings.KINGPIN_CFN_HASH_OUTPUT_KEY = "KingpinCfnHash"
        settings.KINGPIN_CFN_DEFAULT_ROLE_ARN = None
        importlib.reload(cloudformation)
        # Need to recreate the api call queues between tests
        # because nose creates a new ioloop per test run.
        base.NAMED_API_CALL_QUEUES = {}

        self.actor = cloudformation.Stack(
            options={
                "name": "unit-test-cfn",
                "state": "present",
                "region": "us-west-2",
                "template": "examples/test/aws.cloudformation/cfn.unittest.json",
                "parameters": {"key1": "value1"},
            }
        )
        self.actor.cfn_conn = mock.MagicMock(name="cfn_conn")
        self.actor.s3_conn = mock.MagicMock(name="s3_conn")

    def test_diff_params_safely(self):
        self.actor = cloudformation.Stack(
            options={
                "name": "unit-test-cfn",
                "state": "present",
                "region": "us-west-2",
                "template": "examples/test/aws.cloudformation/cfn.integration.json",
                "parameters": {
                    "BucketName": "name",
                    "BucketPassword": "test_password",
                    "Metadata": "1.0",
                },
            }
        )

        # Pretend that the parameters are the same
        # (BucketName, DefaultParam, and Metadata), and the BucketPassword
        # came back with stars.
        # We should still return False to indicate that the parameters
        # are the same.
        remote = [
            {"ParameterKey": "BucketName", "ParameterValue": "name"},
            {"ParameterKey": "BucketPassword", "ParameterValue": "***"},
            {"ParameterKey": "DefaultParam", "ParameterValue": "DefaultValue"},
            {"ParameterKey": "Metadata", "ParameterValue": "1.0"},
        ]
        ret = self.actor._diff_params_safely(remote, self.actor._parameters)
        self.assertEqual(False, ret)

        # Now pretend that the Metadata is different ... Should return True
        # indicating that the lists are different.
        remote = [
            {"ParameterKey": "BucketName", "ParameterValue": "name"},
            {"ParameterKey": "BucketPassword", "ParameterValue": "***"},
            {
                "ParameterKey": "Metadata",
                "ParameterValue": "2.0",
                "ResolvedValue": "Resolved",
            },
        ]
        ret = self.actor._diff_params_safely(remote, self.actor._parameters)
        self.assertEqual(True, ret)

        # Now try updating the parameter with a default and
        # pretend the remote had a different value. Should return True.
        self.actor._options["parameters"]["DefaultParam"] = "NewValue"
        self.actor._parameters = self.actor._create_parameters(
            self.actor._options["parameters"]
        )
        remote = [
            {"ParameterKey": "BucketName", "ParameterValue": "name"},
            {"ParameterKey": "BucketPassword", "ParameterValue": "***"},
            {"ParameterKey": "Metadata", "ParameterValue": "2.0"},
            {
                "ParameterKey": "DefaultParam",
                "ParameterValue": "EntirelyDifferentValue",
            },
        ]
        ret = self.actor._diff_params_safely(remote, self.actor._parameters)
        self.assertEqual(True, ret)

        # Now try updating the parameter with a default and
        # pretend the remote had the default value. Should still return True.
        self.actor._options["parameters"]["DefaultParam"] = "AnotherNewValue"
        self.actor._parameters = self.actor._create_parameters(
            self.actor._options["parameters"]
        )
        remote = [
            {"ParameterKey": "BucketName", "ParameterValue": "name"},
            {"ParameterKey": "BucketPassword", "ParameterValue": "***"},
            {"ParameterKey": "Metadata", "ParameterValue": "2.0"},
            {"ParameterKey": "DefaultParam", "ParameterValue": "DefaultValue"},
        ]
        ret = self.actor._diff_params_safely(remote, self.actor._parameters)
        self.assertEqual(True, ret)

    async def test_update_stack_in_failed_state(self):
        fake_stack = create_fake_stack("fake", "CREATE_FAILED")
        self.actor._get_stack = AsyncMock(name="_get_stack")
        self.actor._get_stack.return_value = fake_stack
        self.actor._delete_stack = AsyncMock(name="_delete_stack")
        self.actor._delete_stack.return_value = fake_stack
        self.actor._create_stack = AsyncMock(name="_create_stack")
        self.actor._create_stack.return_value = fake_stack
        await self.actor._update_stack(fake_stack)
        self.actor._delete_stack.assert_called_with(
            stack="arn:aws:cloudformation:us-east-1:xxxx:stack/fake/x"
        )
        self.actor._create_stack.assert_called_with(stack="fake")

    async def test_update_stack_in_delete_failed_state(self):
        fake_stack = create_fake_stack("fake", "DELETE_FAILED")
        self.actor._get_stack = AsyncMock(name="_get_stack")
        with self.assertRaises(cloudformation.StackFailed):
            await self.actor._update_stack(fake_stack)

    async def test_update_stack_ensure_template(self):
        fake_stack = create_fake_stack("fake", "CREATE_COMPLETE")
        self.actor._ensure_template = AsyncMock(name="_ensure_stack")
        self.actor._ensure_template.return_value = None
        await self.actor._update_stack(fake_stack)
        self.actor._ensure_template.assert_called_with(fake_stack)

    async def test_update_stack_ensure_termination_protection_default_to_true(self):
        fake_stack = create_fake_stack("fake", "CREATE_COMPLETE")
        self.actor._options["enable_termination_protection"] = True

        self.actor._update_termination_protection = AsyncMock(
            name="_update_termination_protection"
        )
        self.actor._update_termination_protection.return_value = None

        self.actor._ensure_template = AsyncMock(name="_ensure_stack")
        self.actor._ensure_template.return_value = None

        await self.actor._update_stack(fake_stack)
        self.actor._update_termination_protection.assert_called_with(fake_stack, True)

    async def test_update_stack_ensure_termination_protection_true_to_false(self):
        fake_stack = create_fake_stack("fake", "CREATE_COMPLETE")
        fake_stack["EnableTerminationProtection"] = True
        self.actor._options["enable_termination_protection"] = False

        self.actor._update_termination_protection = AsyncMock(
            name="_update_termination_protection"
        )
        self.actor._update_termination_protection.return_value = None

        self.actor._ensure_template = AsyncMock(name="_ensure_stack")
        self.actor._ensure_template.return_value = None

        await self.actor._update_stack(fake_stack)
        self.actor._update_termination_protection.assert_called_with(fake_stack, False)

    async def test_update_stack_ensure_termination_protection_true_to_true(self):
        fake_stack = create_fake_stack("fake", "CREATE_COMPLETE")
        fake_stack["EnableTerminationProtection"] = True
        self.actor._options["enable_termination_protection"] = True

        self.actor._update_termination_protection = AsyncMock(
            name="_update_termination_protection"
        )
        self.actor._update_termination_protection.return_value = None

        self.actor._ensure_template = AsyncMock(name="_ensure_stack")
        self.actor._ensure_template.return_value = None

        await self.actor._update_stack(fake_stack)
        self.assertFalse(self.actor._update_termination_protection.called)

    async def test_update_stack_update_termination_protection(self):
        fake_stack = create_fake_stack("fake", "CREATE_COMPLETE")
        self.actor._options["enable_termination_protection"] = True

        self.actor.cfn_conn.update_termination_protection.return_value = None

        self.actor._ensure_template = AsyncMock(name="_ensure_stack")
        self.actor._ensure_template.return_value = None

        await self.actor._update_stack(fake_stack)
        self.actor.cfn_conn.update_termination_protection.assert_has_calls(
            [mock.call(StackName="fake", EnableTerminationProtection=True)]
        )

    async def test_update_stack_update_termination_protection_error(self):
        fake_stack = create_fake_stack("fake", "CREATE_COMPLETE")
        self.actor._options["enable_termination_protection"] = True

        fake_update = {
            "ResponseMetadata": {
                "HTTPStatusCode": 400,
                "RequestId": "dfc1a12c-22c1-11e6-80b1-8fd4cf167f54",
            },
            "Error": {
                "Message": "Template format error: JSON not well-formed",
                "Code": "ValidationError",
                "Type": "Sender",
            },
        }

        self.actor.cfn_conn.update_termination_protection.side_effect = ClientError(
            fake_update, "FakeOperation"
        )
        with self.assertRaises(cloudformation.StackFailed):
            await self.actor._update_stack(fake_stack)

    async def test_ensure_template_with_url_works(self):
        self.actor._template_body = json.dumps({})
        self.actor._template_url = "s3://some.bucket.name/template.json"
        expected_body = (
            '{"AWSTemplateFormatVersion": "2010-09-09", "Resources": '
            '{"ImageRepository": {"Type": "AWS::ECR::Repository"}}}'
        )
        body_io = mock.MagicMock()
        body_io.read.return_value = expected_body
        self.actor.s3_conn.get_object.return_value = {"Body": body_io}

        self.actor._create_change_set = AsyncMock(name="_create_change")
        self.actor._create_change_set.return_value = {"Id": "abcd"}
        self.actor._wait_until_change_set_ready = AsyncMock(name="_wait")
        self.actor._wait_until_change_set_ready.return_value = {"Changes": []}
        self.actor._execute_change_set = AsyncMock(name="_execute_change")
        self.actor._execute_change_set.return_value = None
        self.actor.cfn_conn.delete_change_set.return_value = None

        # Change the actors parameters from the first time it was run -- this
        # ensures all the lines on the ensure_template method are called
        self.actor._parameters = self.actor._create_parameters({})

        fake_stack = create_fake_stack("fake", "CREATE_COMPLETE")

        # Grab the raw stack body from the test actor -- this is what it should
        # compare against, so this test should cause the method to bail out and
        # not make any changes.
        template = {"Fake": "Stack"}
        get_temp_mock = AsyncMock(name="_get_stack_template")
        self.actor._get_stack_template = get_temp_mock
        self.actor._get_stack_template.return_value = template

        # We run three tests in here because the setup takes so many lines
        # (above). First test is a normal execution with changes detected.
        ret = await self.actor._ensure_template(fake_stack)
        self.assertEqual(None, ret)
        self.actor._create_change_set.assert_has_calls([mock.call(fake_stack)])
        self.actor._wait_until_change_set_ready.assert_has_calls(
            [mock.call("abcd", "Status", "CREATE_COMPLETE")]
        )
        self.assertFalse(self.actor.cfn_conn.delete_change_set.called)

        # Quick second execution with _dry set. In this case, we SHOULD call
        # the delete changset function.
        self.actor._dry = True
        await self.actor._ensure_template(fake_stack)
        self.actor.cfn_conn.delete_change_set.assert_has_calls(
            [mock.call(ChangeSetName="abcd")]
        )

    async def test_ensure_template_no_diff(self):
        self.actor._create_change_set = AsyncMock(name="_create_change")
        self.actor._wait_until_change_set_ready = AsyncMock(name="_wait")
        fake_stack = create_fake_stack("fake", "CREATE_COMPLETE")

        # Grab the raw stack body from the test actor -- this is what it should
        # compare against, so this test should cause the method to bail out and
        # not make any changes.
        template = json.loads(self.actor._template_body)
        get_temp_mock = AsyncMock(name="_get_stack_template")
        self.actor._get_stack_template = get_temp_mock
        self.actor._get_stack_template.return_value = template

        ret = await self.actor._ensure_template(fake_stack)
        self.assertEqual(None, ret)

        self.assertFalse(self.actor._create_change_set.called)
        self.assertFalse(self.actor._wait_until_change_set_ready.called)

    async def test_ensure_template_different(self):
        self.actor._create_change_set = AsyncMock(name="_create_change")
        self.actor._create_change_set.return_value = {"Id": "abcd"}
        self.actor._wait_until_change_set_ready = AsyncMock(name="_wait")
        self.actor._wait_until_change_set_ready.return_value = {"Changes": []}
        self.actor._execute_change_set = AsyncMock(name="_execute_change")
        self.actor._execute_change_set.return_value = None
        self.actor.cfn_conn.delete_change_set.return_value = None

        # Change the actors parameters from the first time it was run -- this
        # ensures all the lines on the ensure_template method are called
        self.actor._parameters = self.actor._create_parameters({})

        fake_stack = create_fake_stack("fake", "CREATE_COMPLETE")

        # Grab the raw stack body from the test actor -- this is what it should
        # compare against, so this test should cause the method to bail out and
        # not make any changes.
        template = {"Fake": "Stack"}
        get_temp_mock = AsyncMock(name="_get_stack_template")
        self.actor._get_stack_template = get_temp_mock
        self.actor._get_stack_template.return_value = template

        # We run three tests in here because the setup takes so many lines
        # (above). First test is a normal execution with changes detected.
        ret = await self.actor._ensure_template(fake_stack)
        self.assertEqual(None, ret)
        self.actor._create_change_set.assert_has_calls([mock.call(fake_stack)])
        self.actor._wait_until_change_set_ready.assert_has_calls(
            [mock.call("abcd", "Status", "CREATE_COMPLETE")]
        )
        self.assertFalse(self.actor.cfn_conn.delete_change_set.called)

        # Quick second execution with _dry set. In this case, we SHOULD call
        # the delete changset function.
        self.actor._dry = True
        await self.actor._ensure_template(fake_stack)
        self.actor.cfn_conn.delete_change_set.assert_has_calls(
            [mock.call(ChangeSetName="abcd")]
        )

    async def test_ensure_template_exc(self):
        self.actor._create_change_set = AsyncMock(name="_create_change")
        self.actor._create_change_set.return_value = {"Id": "abcd"}
        self.actor._wait_until_change_set_ready = AsyncMock(name="_wait")
        self.actor._wait_until_change_set_ready.return_value = {"Changes": []}
        self.actor._execute_change_set = AsyncMock(name="_execute_change")
        fake_exc = {
            "ResponseMetadata": {
                "HTTPStatusCode": 400,
                "RequestId": "dfc1a12c-22c1-11e6-80b1-8fd4cf167f54",
            },
            "Error": {
                "Message": "Template format error: JSON not well-formed",
                "Code": "ValidationError",
                "Type": "Sender",
            },
        }
        self.actor._execute_change_set.side_effect = ClientError(
            fake_exc, "FakeOperation"
        )

        fake_stack = create_fake_stack("fake", "CREATE_COMPLETE")

        # Grab the raw stack body from the test actor -- this is what it should
        # compare against, so this test should cause the method to bail out and
        # not make any changes.
        template = {"Fake": "Stack"}
        get_temp_mock = AsyncMock(name="_get_stack_template")
        self.actor._get_stack_template = get_temp_mock
        self.actor._get_stack_template.return_value = template

        # Ensure we raise an exception if something bad happens
        with self.assertRaises(cloudformation.StackFailed):
            await self.actor._ensure_template(fake_stack)

    def test_hash_feature_disabled(self):
        settings.KINGPIN_CFN_HASH_OUTPUT_KEY = ""
        importlib.reload(cloudformation)
        self.actor = cloudformation.Stack(
            options={
                "name": "unit-test-cfn",
                "state": "present",
                "region": "us-west-2",
                "template": "examples/test/aws.cloudformation/cfn.unittest.json",
                "parameters": {"key1": "value1"},
            }
        )
        self.actor._template_body = json.dumps({"blank": "json"})

        ret1 = self.actor._template_body_with_hash()
        ret2 = self.actor._strip_hash_str(self.actor._template_body)

        self.assertEqual(ret1, json.dumps({"blank": "json"}))
        self.assertEqual(ret2, json.dumps({"blank": "json"}))

    def test_strip_hash_str(self):
        self.actor._template_body = json.dumps(
            {
                "blank": "json",
                "Outputs": {
                    "KingpinCfnHash": {"Value": "251693d288f81514f8f49b594fc83e47"}
                },
            }
        )

        ret = self.actor._strip_hash_str(self.actor._template_body)

        self.assertEqual(ret, json.dumps({"blank": "json"}))

    async def test_create_change_set_body(self):
        self.actor.cfn_conn.create_change_set.return_value = {"Id": "abcd"}
        fake_stack = create_fake_stack("fake", "CREATE_COMPLETE")
        ret = await self.actor._create_change_set(fake_stack, "uuid")
        self.assertEqual(ret, {"Id": "abcd"})
        self.actor.cfn_conn.create_change_set.assert_has_calls(
            [
                mock.call(
                    StackName="arn:aws:cloudformation:us-east-1:xxxx:stack/fake/x",
                    TemplateBody='{"blank": "json", "Outputs": {"KingpinCfnHash": {"Value": "251693d288f81514f8f49b594fc83e47"}}}',
                    Capabilities=[],
                    ChangeSetName="kingpin-uuid",
                    Parameters=[{"ParameterValue": "value1", "ParameterKey": "key1"}],
                    UsePreviousTemplate=False,
                )
            ]
        )

    async def test_create_change_set_body_with_role(self):
        self.actor.cfn_conn.create_change_set.return_value = {"Id": "abcd"}
        fake_stack = create_fake_stack("fake", "CREATE_COMPLETE")
        self.actor._options["role_arn"] = "test_role_arn"
        ret = await self.actor._create_change_set(fake_stack, "uuid")
        self.assertEqual(ret, {"Id": "abcd"})
        self.actor.cfn_conn.create_change_set.assert_has_calls(
            [
                mock.call(
                    StackName="arn:aws:cloudformation:us-east-1:xxxx:stack/fake/x",
                    TemplateBody='{"blank": "json", "Outputs": {"KingpinCfnHash": {"Value": "251693d288f81514f8f49b594fc83e47"}}}',
                    RoleARN="test_role_arn",
                    Capabilities=[],
                    ChangeSetName="kingpin-uuid",
                    Parameters=[{"ParameterValue": "value1", "ParameterKey": "key1"}],
                    UsePreviousTemplate=False,
                )
            ]
        )

    async def test_create_change_set_body_with_default_role(self):
        self.actor.cfn_conn.create_change_set.return_value = {"Id": "abcd"}
        fake_stack = create_fake_stack("fake", "CREATE_COMPLETE")

        settings.KINGPIN_CFN_DEFAULT_ROLE_ARN = "test_default_role_arn"
        importlib.reload(cloudformation)

        ret = await self.actor._create_change_set(fake_stack, "uuid")
        self.assertEqual(ret, {"Id": "abcd"})
        self.actor.cfn_conn.create_change_set.assert_has_calls(
            [
                mock.call(
                    StackName="arn:aws:cloudformation:us-east-1:xxxx:stack/fake/x",
                    TemplateBody='{"blank": "json", "Outputs": {"KingpinCfnHash": {"Value": "251693d288f81514f8f49b594fc83e47"}}}',
                    RoleARN="test_default_role_arn",
                    Capabilities=[],
                    ChangeSetName="kingpin-uuid",
                    Parameters=[{"ParameterValue": "value1", "ParameterKey": "key1"}],
                    UsePreviousTemplate=False,
                )
            ]
        )

    async def test_create_change_set_url(self):
        self.actor.cfn_conn.create_change_set.return_value = {"Id": "abcd"}
        template_body = json.dumps({})
        self.actor._template_body = template_body
        self.actor._template_url = "https://foobar.s3.us-east-1.amazonaws.com/bin"
        fake_stack = create_fake_stack("fake", "CREATE_COMPLETE")
        ret = await self.actor._create_change_set(fake_stack, "uuid")
        self.assertEqual(ret, {"Id": "abcd"})
        self.actor.cfn_conn.create_change_set.assert_has_calls(
            [
                mock.call(
                    StackName="arn:aws:cloudformation:us-east-1:xxxx:stack/fake/x",
                    TemplateURL="https://foobar.s3.us-east-1.amazonaws.com/bin",
                    Capabilities=[],
                    ChangeSetName="kingpin-uuid",
                    Parameters=[{"ParameterValue": "value1", "ParameterKey": "key1"}],
                    UsePreviousTemplate=False,
                )
            ]
        )

    async def test_create_change_set_exc(self):
        self.actor.cfn_conn.create_change_set.return_value = {"Id": "abcd"}
        fake_exc = {
            "ResponseMetadata": {
                "HTTPStatusCode": 400,
                "RequestId": "dfc1a12c-22c1-11e6-80b1-8fd4cf167f54",
            },
            "Error": {
                "Message": "Template format error: JSON not well-formed",
                "Code": "ValidationError",
                "Type": "Sender",
            },
        }
        self.actor.cfn_conn.create_change_set.side_effect = ClientError(
            fake_exc, "FakeOperation"
        )
        fake_stack = create_fake_stack("fake", "CREATE_COMPLETE")
        with self.assertRaises(cloudformation.CloudFormationError):
            await self.actor._create_change_set(fake_stack, "uuid")

    async def test_wait_until_change_set_ready_complete(self):
        available = {"Status": "AVAILABLE"}
        update_in_progress = {"Status": "UPDATE_IN_PROGRESS"}
        update_complete = {"Status": "UPDATE_COMPLETE"}
        fake_exc = {
            "ResponseMetadata": {
                "HTTPStatusCode": 400,
                "RequestId": "dfc1a12c-22c1-11e6-80b1-8fd4cf167f54",
            },
            "Error": {
                "Message": "Template format error: JSON not well-formed",
                "Code": "ValidationError",
                "Type": "Sender",
            },
        }
        self.actor.cfn_conn.describe_change_set.side_effect = [
            available,
            update_in_progress,
            update_in_progress,
            ClientError(fake_exc, "Failure"),
            update_complete,
        ]
        await self.actor._wait_until_change_set_ready(
            "test", "Status", "UPDATE_COMPLETE", sleep=0.01
        )
        self.actor.cfn_conn.describe_change_set.assert_has_calls(
            [
                mock.call(ChangeSetName="test"),
                mock.call(ChangeSetName="test"),
                mock.call(ChangeSetName="test"),
                mock.call(ChangeSetName="test"),
            ]
        )

    async def test_wait_until_change_set_ready_failed_status(self):
        available = {"Status": "AVAILABLE"}
        update_in_progress = {"Status": "UPDATE_IN_PROGRESS"}
        update_failed = {"Status": "UPDATE_FAILED", "StatusReason": "Template error"}
        self.actor.cfn_conn.describe_change_set.side_effect = [
            available,
            update_in_progress,
            update_in_progress,
            update_failed,
        ]
        with self.assertRaises(cloudformation.StackFailed):
            await self.actor._wait_until_change_set_ready(
                "test", "Status", "UPDATE_COMPLETE", sleep=0.01
            )

    async def test_wait_until_change_set_ready_failed_status_no_reason(self):
        available = {"Status": "AVAILABLE"}
        update_in_progress = {"Status": "UPDATE_IN_PROGRESS"}
        update_failed = {"Status": "UPDATE_FAILED"}
        self.actor.cfn_conn.describe_change_set.side_effect = [
            available,
            update_in_progress,
            update_in_progress,
            update_failed,
        ]
        with self.assertRaises(cloudformation.StackFailed):
            await self.actor._wait_until_change_set_ready(
                "test", "Status", "UPDATE_COMPLETE", sleep=0.01
            )

    def test_print_change_set(self):
        fake_change_set = {
            "Changes": [
                {
                    "ResourceChange": {
                        "Action": "Created",
                        "ResourceType": "S3::Bucket",
                        "LogicalResourceId": "MyBucket",
                        "PhysicalResourceId": "arn:123",
                        "Replacement": True,
                    }
                },
                {
                    "ResourceChange": {
                        "Action": "Created",
                        "ResourceType": "S3::Bucket",
                        "LogicalResourceId": "MySecondBucket",
                    }
                },
            ]
        }
        self.actor.log = mock.MagicMock(name="log")
        self.actor._print_change_set(fake_change_set)
        self.actor.log.warning.assert_has_calls(
            [
                mock.call(
                    "Change: Created S3::Bucket MyBucket/arn:123 (Replacement? True)"
                ),
                mock.call(
                    "Change: Created S3::Bucket MySecondBucket/N/A "
                    "(Replacement? False)"
                ),
            ]
        )

    async def test_execute_change_set(self):
        fake = {"StackId": "arn::fake_set"}
        self.actor._wait_until_change_set_ready = AsyncMock(name="_wait")
        self.actor._wait_until_change_set_ready.return_value = fake
        self.actor._wait_until_state = AsyncMock(name="_wait_until_state")
        self.actor._wait_until_state.return_value = None

        await self.actor._execute_change_set(change_set_name="fake_set")

        self.actor.cfn_conn.execute_change_set.assert_has_calls(
            [mock.call(ChangeSetName="fake_set")]
        )

        self.actor._wait_until_change_set_ready.assert_has_calls(
            [mock.call("fake_set", "ExecutionStatus", "EXECUTE_COMPLETE")]
        )
        self.actor._wait_until_state.assert_has_calls(
            [
                mock.call(
                    "arn::fake_set",
                    (
                        cloudformation.COMPLETE
                        + cloudformation.FAILED
                        + cloudformation.DELETED
                    ),
                )
            ]
        )

    async def test_execute_change_set_exc(self):
        fake_exc = {
            "ResponseMetadata": {
                "HTTPStatusCode": 400,
                "RequestId": "dfc1a12c-22c1-11e6-80b1-8fd4cf167f54",
            },
            "Error": {
                "Message": "Template format error: JSON not well-formed",
                "Code": "ValidationError",
                "Type": "Sender",
            },
        }

        self.actor.cfn_conn.execute_change_set = AsyncMock(name="_wait")
        self.actor.cfn_conn.execute_change_set.side_effect = ClientError(
            fake_exc, "FakeOperation"
        )

        with self.assertRaises(cloudformation.StackFailed):
            await self.actor._execute_change_set(change_set_name="fake_set")

    async def test_ensure_stack_is_absent_and_wants_absent(self):
        self.actor._options["state"] = "absent"
        self.actor._get_stack = AsyncMock(name="_get_stack")
        self.actor._get_stack.return_value = None
        self.actor._delete_stack = AsyncMock(name="_delete_stack")
        self.actor._delete_stack.return_value = None
        self.actor._create_stack = AsyncMock(name="_create_stack")
        self.actor._create_stack.return_value = None

        await self.actor._ensure_stack()

        self.assertFalse(self.actor._create_stack.called)
        self.assertFalse(self.actor._delete_stack.called)

    async def test_ensure_stack_is_present_and_wants_absent(self):
        self.actor._options["state"] = "absent"
        fake_stack = create_fake_stack("unit-test-cfn", "CREATE_COMPLETE")
        self.actor._get_stack = AsyncMock(name="_get_stack")
        self.actor._get_stack.return_value = fake_stack
        self.actor._delete_stack = AsyncMock(name="_delete_stack")
        self.actor._delete_stack.return_value = None
        self.actor._create_stack = AsyncMock(name="_create_stack")
        self.actor._create_stack.return_value = None

        await self.actor._ensure_stack()

        self.assertTrue(self.actor._delete_stack.called)
        self.assertFalse(self.actor._create_stack.called)

    async def test_ensure_stack_is_absent_and_wants_present(self):
        self.actor._options["state"] = "present"
        self.actor._get_stack = AsyncMock(name="_get_stack")
        self.actor._get_stack.return_value = None
        self.actor._delete_stack = AsyncMock(name="_delete_stack")
        self.actor._delete_stack.return_value = None
        self.actor._create_stack = AsyncMock(name="_create_stack")
        self.actor._create_stack.return_value = None

        await self.actor._ensure_stack()

        self.assertFalse(self.actor._delete_stack.called)
        self.assertTrue(self.actor._create_stack.called)

    async def test_ensure_stack_is_present_and_wants_update_create_failed(self):
        self.actor._options["state"] = "present"
        fake_stack = create_fake_stack("fake", "CREATE_FAILED")
        self.actor._get_stack = AsyncMock(name="_get_stack")
        self.actor._get_stack.return_value = fake_stack
        self.actor._delete_stack = AsyncMock(name="_delete_stack")
        self.actor._delete_stack.return_value = None
        self.actor._create_stack = AsyncMock(name="_create_stack")
        self.actor._create_stack.return_value = None
        self.actor._update_stack = AsyncMock(name="_update_stack")
        self.actor._update_stack.return_value = None

        await self.actor._ensure_stack()

        self.assertFalse(self.actor._delete_stack.called)
        self.assertFalse(self.actor._create_stack.called)
        self.assertTrue(self.actor._update_stack.called)

    async def test_execute(self):
        self.actor._validate_template = AsyncMock(return_value=None)
        self.actor._ensure_stack = AsyncMock(return_value=None)
        await self.actor._execute()
