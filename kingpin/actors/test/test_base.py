import unittest

"""Tests for the actors.base package."""

import asyncio
import json
import logging
import os
from importlib import reload
from unittest import mock

# Unusual placement -- but we override the environment so that we can test that
# the urllib debugger works.
os.environ["URLLIB_DEBUG"] = "1"

from kingpin.actors import base

reload(base)
from unittest.mock import AsyncMock

from kingpin.actors import exceptions
from kingpin.constants import REQUIRED, STATE


class FakeEnsurableBaseActor(base.EnsurableBaseActor):

    all_options = {
        "name": (str, REQUIRED, "Name of thing"),
        "description": (str, None, "Some description"),
        "unmanaged": (str, None, "some unmanaged option"),
    }

    unmanaged_options = ["unmanaged"]

    async def _precache(self):
        # Call our parent class precache.. no real need here other than for
        # unit test coverage.
        await super()._precache()

        # These do not match -- so we'll trigger the setters
        self.state = "absent"
        self.name = "Old name"

        # This matches the desired description on purpose.
        self.description = "Some description"

        # Start out with no calls recorded
        self.set_state_called = False
        self.set_name_called = False
        self.set_description_called = False

        # Make it easy to check that this was called
        self._precache_called = True

    async def _set_state(self):
        self.state = True
        self.set_state_called = True

    async def _get_state(self):
        return self.state

    async def _set_name(self):
        self.name = self.option("name")
        self.set_name_called = True

    async def _get_name(self):
        return self.name

    async def _compare_name(self):
        exist = await self._get_name()
        new = self.option("name")
        return exist == new

    async def _set_description(self):
        self.set_description_called = True

    async def _get_description(self):
        return self.description


class TestBaseActor(unittest.IsolatedAsyncioTestCase):
    async def true(self):
        await asyncio.sleep(0.01)
        return True

    async def false(self):
        await asyncio.sleep(0.01)
        return False

    def setUp(self):
        super().setUp()

        # Create a BaseActor object
        self.actor = base.BaseActor("Unit Test Action", {})

        # Mock out the actors ._execute() method so that we have something to
        # test
        self.actor._execute = self.true

    def test_user_defined_desc(self):
        self.assertEqual("Unit Test Action", str(self.actor))

    def test_default_desc(self):
        self.actor._desc = None
        self.assertEqual("kingpin.actors.base.BaseActor", str(self.actor))

    async def test_timer(self):
        # Create a function and wrap it in our timer
        self.actor._execute = self.true

        # Mock out the logger so we can track it
        self.actor.log = mock.MagicMock()

        # Now call the execute() wrapper that leverages the @timer decorator.
        await self.actor.execute()

        # Search for a logged message. Don't explicitly set the execution time
        # because some computers and compilers are slow.
        msg = "kingpin.actors.base.BaseActor.execute() execution time"
        msg_is_in_calls = False
        for call in self.actor.log.debug.mock_calls:
            if msg in str(call):
                msg_is_in_calls = True
        self.assertEqual(msg_is_in_calls, True)

    async def test_timeout(self):
        # Create a quick mock.. so we can track whether or not API calls were
        # actually made.
        tracker = mock.MagicMock(name="tracker")

        # Create a function and wrap it in our timeout
        async def _execute():
            tracker.reset_mock()
            await asyncio.sleep(0.2)
            tracker.call_me()

        self.actor._execute = _execute

        # Set our timeout to 2s, test should work
        self.actor._timeout = 1
        await self.actor.timeout(_execute)
        tracker.assert_has_calls([mock.call.call_me()])

        # Now set our timeout to 500ms. Exception should be raised, and the
        # tracker should NOT be called.
        self.actor._timeout = 0.1
        with self.assertRaises(exceptions.ActorTimedOut):
            await self.actor.timeout(_execute)

        # Set the timeout to 0, which disables it. No exception should be
        # raised
        self.actor._timeout = 0
        await self.actor.timeout(_execute)
        self.actor_timeout = None
        await self.actor.timeout(_execute)

    def test_httplib_debugging(self):
        # Get the logger now and validate that its level was set right
        requests_logger = logging.getLogger("requests.packages.urllib3")
        self.assertEqual(logging.DEBUG, requests_logger.level)

    def test_validate_options(self):
        self.actor.all_options = {"test": (str, REQUIRED, "")}
        self.actor._options = {"a": "b"}
        with self.assertRaises(exceptions.InvalidOptions):
            ret = self.actor._validate_options()

        self.actor.all_options = {"test": (str, REQUIRED, "")}
        self.actor._options = {"test": "b"}
        ret = self.actor._validate_options()
        self.assertEqual(None, ret)

        self.actor.all_options = {"test": (bool, REQUIRED, "")}
        self.actor._options = {"test": "junk_text"}
        with self.assertRaises(exceptions.InvalidOptions):
            self.actor._validate_options()

        self.actor.all_options = {
            "test": (str, REQUIRED, ""),
            "test2": (str, REQUIRED, ""),
        }
        self.actor._options = {"test": "b", "test2": "b"}
        ret = self.actor._validate_options()
        self.assertEqual(None, ret)

        # The STATE type requires either 'present' or 'absent' to be passed in.
        self.actor.all_options = {"test": (STATE, REQUIRED, "")}
        self.actor._options = {"test": "present"}
        ret = self.actor._validate_options()
        self.assertEqual(None, ret)

        self.actor._options = {"test": "absent"}
        ret = self.actor._validate_options()
        self.assertEqual(None, ret)

        with self.assertRaises(exceptions.InvalidOptions):
            self.actor._options = {"test": "abse"}
            ret = self.actor._validate_options()

    def test_validation_issues(self):
        self.actor.all_options = {
            "needed": (str, REQUIRED, ""),
            "optional": (str, "", ""),
        }

        # Requirement not satisfied
        self.actor._options = {"optional": "b"}
        with self.assertRaises(exceptions.InvalidOptions):
            self.actor._validate_options()

        # Invalid option type:
        self.actor._options = {"needed": 1, "optional": "b"}
        with self.assertRaises(exceptions.InvalidOptions):
            self.actor._validate_options()

        # Unexpected option passed
        self.actor._options = {"needed": "a", "unexpected": "b"}
        # Should work w/out raising an exception.
        self.actor._validate_options()

    def test_validate_defaults(self):
        # Default is not a permitted type
        self.actor.all_options = {"name": (str, False, "String!")}
        self.actor._setup_defaults()
        with self.assertRaises(exceptions.InvalidOptions):
            self.actor._validate_options()

    def test_option(self):
        self.actor._options["foo"] = "bar"
        opt = self.actor.option("foo")
        self.assertEqual(opt, "bar")

    def test_readfile(self):
        with self.assertRaises(exceptions.InvalidOptions):
            self.actor.readfile("notfound")

        open_patcher = mock.patch(f"{self.actor.__module__}.open", create=True)
        with open_patcher as mock_open:
            self.actor.readfile("somefile")
            self.assertEqual(mock_open.call_count, 1)
            # using __enter__ here because it's opened as a context manager.
            self.assertEqual(mock_open().__enter__().read.call_count, 1)

    async def test_execute(self):
        res = await self.actor.execute()
        self.assertEqual(res, True)

    async def test_check_condition(self):
        conditions = {
            "FOobar": True,
            "True": True,
            "TRUE": True,
            1: True,
            "1": True,
            0: False,
            "0": False,
            "False": False,
            "FALSE": False,
        }
        for value, should_execute in conditions.items():
            self.actor._condition = value
            self.actor._execute = AsyncMock()
            await self.actor.execute()
            str_value = json.dumps(value)
            if should_execute:
                self.assertEqual(
                    self.actor._execute.await_count,
                    1,
                    f"Value `{str_value}` should allow actor execution",
                )
            else:
                self.assertEqual(
                    self.actor._execute.await_count,
                    0,
                    f"Value `{str_value}` should not allow actor execution",
                )

    async def test_execute_fail(self):
        self.actor._execute = self.false
        res = await self.actor.execute()
        self.assertEqual(res, False)

    async def test_execute_catches_expected_exception(self):
        async def raise_exc():
            raise exceptions.ActorException("Test")

        self.actor._execute = raise_exc
        with self.assertRaises(exceptions.ActorException):
            await self.actor.execute()

    async def test_execute_catches_unexpected_exception(self):
        async def raise_exc():
            raise Exception("Test")

        self.actor._execute = raise_exc
        with self.assertRaises(exceptions.ActorException):
            await self.actor.execute()

    async def test_execute_with_warn_on_failure(self):
        async def raise_exc():
            raise exceptions.RecoverableActorFailure("should just warn")

        self.actor._execute = raise_exc

        # First test, should raise an exc...
        with self.assertRaises(exceptions.RecoverableActorFailure):
            await self.actor.execute()

        # Second test, turn on 'warn_on_failure'
        self.actor._warn_on_failure = True
        res = await self.actor.execute()
        self.assertEqual(res, None)

    def test_fill_in_contexts_desc(self):
        base.BaseActor.all_options = {"test_opt": (str, REQUIRED, "Test option")}

        self.actor = base.BaseActor(
            desc="Unit Test Action - {NAME}",
            options={"test_opt": "Foo bar"},
            condition="{NAME}",
            init_context={"NAME": "TEST"},
        )
        self.assertEqual("Unit Test Action - TEST", self.actor._desc)
        self.assertEqual("TEST", self.actor._condition)

        with self.assertRaises(exceptions.InvalidOptions):
            self.actor = base.BaseActor(
                desc="Unit Test Action",
                options={"test_opt": "Foo {BAZ} bar"},
                init_context={},
            )

        with self.assertRaises(exceptions.InvalidOptions):
            self.actor = base.BaseActor(
                desc="Unit Test Action - {NAME}", options={}, init_context={}
            )

        with self.assertRaises(exceptions.InvalidOptions):
            self.actor = base.BaseActor(
                desc="Unit Test Action",
                options={"test_opt": "Foo bar"},
                condition="{NAME}",
                init_context={},
            )

        # Reset the all options so we dont break other tests
        base.BaseActor.all_options = {}

    def test_fill_in_contexts_options(self):
        base.BaseActor.all_options = {"test_opt": (str, REQUIRED, "Test option")}

        self.actor = base.BaseActor(
            desc="Unit Test Action",
            options={"test_opt": "Foo bar - {NAME}"},
            init_context={"NAME": "TEST"},
        )
        self.assertEqual("Foo bar - TEST", self.actor.option("test_opt"))

        # Reset the all options so we dont break other tests
        base.BaseActor.all_options = {}

    def test_fill_in_contexts_options_escape(self):
        base.BaseActor.all_options = {"test_opt": (str, REQUIRED, "Test option")}

        self.actor = base.BaseActor(
            desc="Unit Test Action",
            options={"test_opt": "Foo bar - \\{NAME\\}"},
            init_context={"NAME": "TEST"},
        )
        self.assertEqual("Foo bar - {NAME}", self.actor.option("test_opt"))

        # Reset the all options so we dont break other tests
        base.BaseActor.all_options = {}


class TestEnsurableBaseActor(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.actor = FakeEnsurableBaseActor(
            "Unit Test Actor",
            {
                "name": "new name",
                "state": "present",
                "unmanaged": "nothing happens with this",
                "description": "Some description",
            },
        )

    async def test_precache(self):
        await self.actor._precache()

    async def test_execute(self):
        await self.actor._execute()

        # Did the precache execute?
        self.assertTrue(self.actor._precache_called)

        # First test -- the description should have matched, so
        # we should not have called self._set_description().
        self.assertFalse(self.actor.set_description_called)

        # We _should_ have called the setters for the state, and
        # for the name.
        self.assertTrue(self.actor.set_state_called)
        self.assertTrue(self.actor.set_name_called)

    async def test_execute_absent(self):
        self.actor._options["state"] = "absent"
        await self.actor._execute()

        # Make sure that the set_name and set_state were NOT called
        self.assertFalse(self.actor.set_state_called)
        self.assertFalse(self.actor.set_name_called)

    def test_gather_methods_throws_exception(self):
        # Mock out the set_name method by replacing it with an attribute
        self.actor._set_name = False
        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            self.actor._gather_methods()


class TestHTTPBaseActor(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.actor = base.HTTPBaseActor("Unit Test Action", {})

    def test_get_method(self):
        self.assertEqual("POST", self.actor._get_method("foobar"))
        self.assertEqual("POST", self.actor._get_method("True"))
        self.assertEqual("POST", self.actor._get_method(""))
        self.assertEqual("GET", self.actor._get_method(None))

    def test_generate_escaped_url(self):
        result = self.actor._generate_escaped_url("http://unittest", {"foo": "bar"})
        self.assertEqual("http://unittest?foo=bar", result)

        result = self.actor._generate_escaped_url("http://unittest", {"foo": True})
        self.assertEqual("http://unittest?foo=true", result)

        result = self.actor._generate_escaped_url(
            "http://unittest", {"foo": "bar", "xyz": "abc"}
        )
        self.assertEqual("http://unittest?foo=bar&xyz=abc", result)

        result = self.actor._generate_escaped_url(
            "http://unittest", {"foo": "bar baz", "xyz": "abc"}
        )
        self.assertEqual("http://unittest?foo=bar+baz&xyz=abc", result)

    async def test_fetch(self):
        response_dict = {"foo": "asdf"}
        response_body = json.dumps(response_dict).encode()

        mock_response = mock.Mock()
        mock_response.read.return_value = response_body

        with mock.patch("urllib.request.urlopen", return_value=mock_response):
            response = await self.actor._fetch("http://example.com/")
            self.assertEqual(response_dict, response)

        mock_response.read.return_value = b"Something bad happened"

        with mock.patch("urllib.request.urlopen", return_value=mock_response):
            with self.assertRaises(exceptions.UnparseableResponseFromEndpoint):
                await self.actor._fetch("http://example.com/")

    async def test_fetch_with_auth(self):
        response_dict = {"foo": "asdf"}
        response_body = json.dumps(response_dict).encode()

        mock_response = mock.Mock()
        mock_response.read.return_value = response_body

        with mock.patch("urllib.request.urlopen", return_value=mock_response) as m:
            await self.actor._fetch(
                "http://example.com/",
                auth_username="foo",
                auth_password="bar",
            )
            req = m.call_args[0][0]
            self.assertIn("Authorization", req.headers)
            self.assertTrue(req.headers["Authorization"].startswith("Basic "))


class TestActualEnsurableBaseActor(unittest.IsolatedAsyncioTestCase):
    def setUp(self):

        super().setUp()
        self.actor = base.EnsurableBaseActor(
            "Unit Test Actor",
            {
                "name": "new name",
                "state": "present",
                "unmanaged": "nothing happens with this",
                "description": "Some description",
            },
        )

    async def test_set_state(self):
        with self.assertRaises(NotImplementedError):
            await self.actor._set_state()

    async def test_get_state(self):
        with self.assertRaises(NotImplementedError):
            await self.actor._get_state()
