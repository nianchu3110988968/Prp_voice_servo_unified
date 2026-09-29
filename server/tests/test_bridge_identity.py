"""Offline stale-process / foreign-checkout guards; no service or serial I/O."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.bridge_identity import startup_identity, mismatch
import launcher_core as launcher


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "server/services").mkdir(parents=True)
        for name in ("ai_bridge_server.py", "server_config.py", "services/motion_policy.py"):
            (self.root / "server" / name).write_text("# startup code\n", encoding="utf-8")
        self.identity = startup_identity(self.root)

    def test_startup_snapshot_rejects_changed_code_and_foreign_root(self):
        self.assertEqual(mismatch(self.identity, self.root, sys.executable), "")
        self.assertIn("其他项目", mismatch(self.identity, self.root / "other"))
        self.assertIn("Python", mismatch(self.identity, self.root, self.root / "other.exe"))
        (self.root / "server/services/motion_policy.py").write_text("# new code\n")
        self.assertIn("源码已变化", mismatch(self.identity, self.root))

    def test_prompt_changes_do_not_require_code_restart(self):
        folder = self.root / "server/prompts"
        folder.mkdir()
        (folder / "motion_selection.txt").write_text("new dynamic policy")
        self.assertEqual(mismatch(self.identity, self.root), "")

    def test_old_role_api_cannot_be_reused_or_receive_text_tests(self):
        old = {"service": "prp-ai-bridge", "role_api": 2}
        supervisor = launcher.Supervisor({"project_root": str(self.root)}, log=lambda _: None)
        with patch.object(launcher, "port_open", return_value=True), patch.object(launcher, "request_json", return_value=old) as request, patch.object(launcher.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(RuntimeError, "旧实例"):
                supervisor.ensure("bridge", None)
            with self.assertRaisesRegex(RuntimeError, "旧实例"):
                supervisor.test_text("chain", "hello")
        popen.assert_not_called()
        self.assertTrue(all(call.args[0].endswith("/health") for call in request.call_args_list))
        self.assertEqual(supervisor.owned, {})

    def test_matching_bridge_is_reused_without_ownership(self):
        health = {"service": "prp-ai-bridge", "role_api": 2, "bridge_identity": self.identity}
        supervisor = launcher.Supervisor({"project_root": str(self.root), "bridge_python": sys.executable}, log=lambda _: None)
        with patch.object(launcher, "port_open", return_value=True), patch.object(launcher, "request_json", return_value=health), patch.object(launcher.subprocess, "Popen") as popen:
            self.assertEqual(supervisor.ensure("bridge", None)["state"], "healthy")
        popen.assert_not_called()
        self.assertEqual(supervisor.owned, {})

    def test_python_resolved_once_without_rewriting_local_config(self):
        folder = self.root / "server/configs"
        folder.mkdir()
        path = folder / "launcher.local.json"
        original = json.dumps({"bridge_python": "python", "project_root": "old-root"})
        path.write_text(original)
        with patch.object(launcher.shutil, "which", return_value=sys.executable), patch.object(launcher.subprocess, "run", return_value=Mock(returncode=0, stdout=sys.executable + "\n")) as run:
            settings = launcher.read_settings(self.root)
        self.assertEqual(settings["bridge_python"], str(Path(sys.executable).resolve()))
        self.assertEqual(settings["project_root"], str(self.root.resolve()))
        self.assertEqual(path.read_text(), original)
        self.assertEqual(run.call_args.args[0][-1], "import sys; print(sys.executable)")


if __name__ == "__main__":
    unittest.main()
