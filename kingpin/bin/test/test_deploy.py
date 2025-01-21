import importlib
import os
import sys
import unittest
from unittest import mock
from kingpin.actors.exceptions import ActorException
from kingpin.actors.misc import Macro, Sleep


class TestDeploy(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(TestDeploy, self).__init__(*args, **kwargs)

        self.kingpin_bin_deploy = None

    def setUp(self):
        """
        Loading the kingpin.bin.deploy module will call argparse.ArgumentParser.parse_args() which
        needs specific arguments to be passed in sys.argv. We need to save the original sys.argv here
        and restore it in tearDown. Furthermore, we will then patch sys.argv to have the correct
        values during import of the kingpin.bin.deploy module.
        """
        self.original_argv = sys.argv

    def tearDown(self):
        if self.kingpin_bin_deploy:
            del self.kingpin_bin_deploy
        sys.argv = self.original_argv

    def _import_kingpin_bin_deploy(self):
        if self.kingpin_bin_deploy:
            del self.kingpin_bin_deploy
        self.kingpin_bin_deploy = importlib.import_module("kingpin.bin.deploy")
        importlib.reload(self.kingpin_bin_deploy)

    ############################################################################
    #  kingpin_fail
    ############################################################################

    @mock.patch("sys.argv", ["kingpin"])
    def test_kingpin_fail(self):
        self._import_kingpin_bin_deploy()
        with self.assertRaises(SystemExit) as cm:
            self.kingpin_bin_deploy.kingpin_fail("testing")
            self.assertEqual(cm.exception.code, 1)

    ############################################################################
    #  get_main_actor
    ############################################################################

    @mock.patch("sys.argv", ["kingpin", "--script", "examples/test/sleep.yaml"])
    def test_get_main_actor_with_script(self):
        self._import_kingpin_bin_deploy()
        result = self.kingpin_bin_deploy.get_main_actor(True)
        self.assertEqual(str(type(result)), str(Macro))
        self.assertEqual(result.option("macro"), "examples/test/sleep.yaml")

    @mock.patch(
        "sys.argv", ["kingpin", "--actor", "misc.Sleep", "--option", "sleep=0.1"]
    )
    def test_get_main_actor_with_actor(self):
        self._import_kingpin_bin_deploy()
        result = self.kingpin_bin_deploy.get_main_actor(True)
        self.assertEqual(str(type(result)), str(Sleep))
        self.assertEqual(result.option("sleep"), "0.1")

    @mock.patch(
        "sys.argv",
        ["kingpin", "--script", "examples/test/sleep.yaml", "--actor", "misc.Sleep"],
    )
    def test_get_main_actor_with_both_script_and_actor(self):
        self._import_kingpin_bin_deploy()
        with self.assertRaises(SystemExit) as cm:
            self.kingpin_bin_deploy.get_main_actor(True)
        self.assertEqual(cm.exception.code, 1)

    @mock.patch("sys.argv", ["kingpin"])
    def test_get_main_actor_with_neither_script_nor_actor(self):
        self._import_kingpin_bin_deploy()
        with self.assertRaises(SystemExit) as cm:
            self.kingpin_bin_deploy.get_main_actor(True)
        self.assertEqual(cm.exception.code, 1)

    ############################################################################
    #  main
    ############################################################################

    @mock.patch("sys.argv", ["kingpin"])
    def test_main_with_good_runner(self):
        self._import_kingpin_bin_deploy()
        with mock.patch("kingpin.bin.deploy.get_main_actor") as mock_get_main_actor:
            mock_get_main_actor.return_value = Sleep(options={"sleep": 0.1}, dry=True)
            self.kingpin_bin_deploy.main()
            mock_get_main_actor.assert_called()

    @mock.patch("sys.argv", ["kingpin"])
    @mock.patch.dict(os.environ, {"SKIP_DRY": "True"})
    def test_main_with_skip_dry(self):
        self._import_kingpin_bin_deploy()
        with mock.patch("kingpin.bin.deploy.get_main_actor") as mock_get_main_actor:
            mock_get_main_actor.return_value = Sleep(options={"sleep": 0.1}, dry=True)
            self.kingpin_bin_deploy.main()
            mock_get_main_actor.assert_called()

    @mock.patch("sys.argv", ["kingpin"])
    @mock.patch.dict(os.environ, {"SKIP_DRY": "not-a-boolean-like-string"})
    def test_main_with_skip_dry_invalid(self):
        self._import_kingpin_bin_deploy()
        with mock.patch("kingpin.bin.deploy.get_main_actor") as mock_get_main_actor:
            mock_get_main_actor.return_value = Sleep(options={"sleep": 0.1}, dry=True)
            self.kingpin_bin_deploy.main()
            mock_get_main_actor.assert_called()

    @mock.patch("sys.argv", ["kingpin"])
    def test_main_with_bad_runner(self):
        self._import_kingpin_bin_deploy()
        with mock.patch("kingpin.bin.deploy.get_main_actor") as mock_get_main_actor:
            mock_get_main_actor.side_effect = ActorException("testing")
            with self.assertRaises(SystemExit) as cm:
                self.kingpin_bin_deploy.main()
                self.assertEqual(cm.exception.code, 2)
            mock_get_main_actor.assert_called()

    @mock.patch("sys.argv", ["kingpin", "--dry"])
    def test_main_with_bad_runner_dry(self):
        self._import_kingpin_bin_deploy()
        with mock.patch("kingpin.bin.deploy.get_main_actor") as mock_get_main_actor:
            mock_get_main_actor.side_effect = ActorException("testing")
            with self.assertRaises(SystemExit) as cm:
                self.kingpin_bin_deploy.main()
                self.assertEqual(cm.exception.code, 2)
            mock_get_main_actor.assert_called()

    @mock.patch("sys.argv", ["kingpin", "--actor", "misc.Sleep", "--explain"])
    def test_main_with_actor_and_explain(self):
        self._import_kingpin_bin_deploy()
        with self.assertRaises(SystemExit) as cm:
            self.kingpin_bin_deploy.main()
            self.assertEqual(cm.exception.code, 0)

    @mock.patch(
        "sys.argv",
        ["kingpin", "--build-only", "--actor", "misc.Sleep", "--option", "sleep=0.1"],
    )
    def test_main_with_build_only_good_actor(self):
        self._import_kingpin_bin_deploy()
        with self.assertRaises(SystemExit) as cm:
            self.kingpin_bin_deploy.main()
            self.assertEqual(cm.exception.code, 0)

    @mock.patch(
        "sys.argv",
        ["kingpin", "--build-only", "--actor", "somefakeactor"],
    )
    def test_main_with_build_only_bad_actor(self):
        self._import_kingpin_bin_deploy()
        with self.assertRaises(SystemExit) as cm:
            self.kingpin_bin_deploy.main()
            self.assertEqual(cm.exception.code, 1)

    @mock.patch(
        "sys.argv",
        [
            "kingpin",
            "--build-only",
            "--orgchart",
            "orgchart.tmp~",
            "--actor",
            "misc.Sleep",
            "--option",
            "sleep=0.1",
        ],
    )
    def test_main_with_build_only_and_org_chart(self):
        self._import_kingpin_bin_deploy()
        with self.assertRaises(SystemExit) as cm:
            self.kingpin_bin_deploy.main()
            self.assertEqual(cm.exception.code, 0)

    @mock.patch(
        "sys.argv",
        [
            "kingpin",
            "--build-only",
            "--orgchart",
            "orgchart.tmp~",
            "--actor",
            "misc.Sleep",
            "--option",
            "sleep=0.1",
        ],
    )
    def test_main_with_build_only_and_bad_org_chart(self):
        self._import_kingpin_bin_deploy()
        actor = Sleep(options={"sleep": 0.1}, dry=True)
        actor.get_orgchart = mock.Mock(side_effect=Exception("testing"))
        with mock.patch("kingpin.bin.deploy.get_main_actor") as mock_get_main_actor:
            mock_get_main_actor.return_value = actor
            with self.assertRaises(SystemExit) as cm:
                self.kingpin_bin_deploy.main()
                self.assertEqual(cm.exception.code, 2)

    ############################################################################
    #  begin
    ############################################################################

    @mock.patch(
        "sys.argv", ["kingpin", "--actor", "misc.Sleep", "--option", "sleep=0.1"]
    )
    def test_begin(self):
        self._import_kingpin_bin_deploy()
        with mock.patch("kingpin.bin.deploy.main"):
            with self.assertRaises(SystemExit) as cm:
                self.kingpin_bin_deploy.begin()
                self.assertEqual(cm.exception.code, 0)

    @mock.patch(
        "sys.argv",
        ["kingpin", "--actor", "misc.Sleep", "--option", "sleep=0.1", "--debug"],
    )
    def test_begin_with_debug(self):
        self._import_kingpin_bin_deploy()
        with mock.patch("kingpin.bin.deploy.main"):
            with self.assertRaises(SystemExit) as cm:
                self.kingpin_bin_deploy.begin()
                self.assertEqual(cm.exception.code, 0)
                self.assertEqual(self.kingpin_bin_deploy.log.level, 10)

    @mock.patch(
        "sys.argv", ["kingpin", "--actor", "misc.Sleep", "--option", "sleep=0.1"]
    )
    def test_begin_keyboard_interrupt(self):
        self._import_kingpin_bin_deploy()
        with mock.patch("tornado.ioloop.IOLoop.instance") as mock_ioloop_instance:
            mock_ioloop_instance.side_effect = KeyboardInterrupt()
            with self.assertRaises(SystemExit) as cm:
                self.kingpin_bin_deploy.begin()
                self.assertEqual(cm.exception.code, 130)
