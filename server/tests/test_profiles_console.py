"""Offline independent profile, serial and durable-console regressions."""
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import json
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import test_roles_launcher as legacy_tests
from services import profile_config as profiles, role_runtime as runtime, dialogue_service as dialogue
from launcher_console import ConsoleLogs, SerialConsole
from launcher_core import playback_path


class ProfileTests(unittest.TestCase):
    save = legacy_tests.RoleTests.save

    def setUp(self):
        legacy_tests.RoleTests.setUp(self)
        profiles.migrate_legacy("Star", self.root)
        self.persona = profiles.load_persona("Star", self.root)
        self.voice = profiles.load_voice("Star", self.root)
        runtime.activate(profiles.compose(self.persona, self.voice))
        runtime.voice_ready = True

    def test_split_and_preset_compatibility(self):
        self.assertEqual(self.voice.reference_wav, self.role.reference_wav)
        (self.root / "server/roles/Star.local.json").write_text(json.dumps({"persona_id": "Star", "voice_id": "Star"}))
        from services.role_config import load_role
        self.assertEqual(load_role("Star", self.root).voice_id, "Star")

    def test_import_auto_hash_and_reject_tamper(self):
        data = self.voice.public()
        data.update(id="NewVoice", weight_pair={})
        imported = profiles.import_voice(data, self.root)
        self.assertEqual(len(imported.weight_pair["gpt_sha256"]), 64)
        with self.assertRaises(FileExistsError):
            profiles.import_voice(data, self.root)
        (self.root / "voice.pth").write_text("tampered")
        with self.assertRaises(ValueError):
            profiles.load_voice("NewVoice", self.root)

    def test_invalid_split_paths_and_ids(self):
        for identifier in ("../escape", "CON", "1bad"):
            with self.assertRaises(ValueError):
                profiles.valid_id(identifier)
        for field, value in (("reference_text", " "), ("gpt_weights", "absent.ckpt")):
            data = self.voice.public()
            data[field] = value
            with self.assertRaises(ValueError):
                profiles.parse_voice(data, self.root)

    def test_import_persona_no_overwrite(self):
        persona = profiles.import_persona("Moon", "月亮", "月亮", "你是月亮。", self.root)
        self.assertEqual(Path(persona.prompt_file).read_text(encoding="utf-8"), "你是月亮。")
        with self.assertRaises(ValueError):
            profiles.import_persona("Moon", "X", "X", "changed", self.root)

    def test_persona_only_clears_history_no_weights(self):
        old_voice = runtime.current.gpt_weights
        persona = replace(self.persona, id="Moon", character_name="月亮", prompt="你是月亮。")
        dialogue.remember_turn("旧问题", "旧回答", "cute")
        with patch.object(profiles, "load_persona", return_value=persona), patch.object(runtime, "_load_pair") as pair:
            runtime.switch_persona("Moon")
        pair.assert_not_called()
        self.assertEqual(dialogue._conversation_history, [])
        self.assertEqual(runtime.current.gpt_weights, old_voice)
        self.assertTrue(runtime.voice_ready)

    def test_voice_only_keeps_persona_and_history(self):
        dialogue.remember_turn("问题", "回答", "cute")
        before = dialogue._conversation_history.copy()
        voice = replace(self.voice, id="Other", gpt_weights="other.ckpt", sovits_weights="other.pth")
        with patch.object(profiles, "load_voice", return_value=voice), patch.object(runtime, "_load_pair") as pair:
            runtime.switch_voice("Other")
        pair.assert_called_once()
        self.assertEqual(runtime.current.persona_id, "Star")
        self.assertEqual(dialogue._conversation_history, before)

    def test_combination_rollback_keeps_both(self):
        old = runtime.current
        candidate = replace(old, persona_id="Moon", voice_id="Other")
        with patch.object(profiles, "load_combination", return_value=candidate), patch.object(runtime, "_load_pair", side_effect=[RuntimeError("fail"), None]):
            with self.assertRaises(RuntimeError):
                runtime.apply_combination("Moon", "Other")
        self.assertIs(runtime.current, old)
        self.assertTrue(runtime.voice_ready)

    def test_cache_binds_both_ids_and_revision(self):
        old = runtime.current
        keys = {old.cache_key, replace(old, persona_id="Moon").cache_key,
                replace(old, voice_id="Other").cache_key, replace(old, phrase_voice_revision="v2").cache_key}
        self.assertEqual(len(keys), 4)


class ConsoleTests(unittest.TestCase):
    def test_routing_rotation_and_date_preserve_files(self):
        with tempfile.TemporaryDirectory() as folder:
            emitted = []
            now = [datetime(2026, 9, 29, 10, 0, 0)]
            logs = ConsoleLogs(folder, lambda *args: emitted.append(args), max_bytes=100, clock=lambda: now[0])
            for n in range(4):
                logs.supervisor("[bridge] request_id=abc " + str(n))
            files = list(Path(folder).glob("*.log"))
            snapshots = {p: p.read_bytes() for p in files}
            self.assertGreater(len(files), 2)
            self.assertTrue(all(s == "bridge" and "[abc]" in text for s, text in emitted))
            now[0] = datetime(2026, 9, 30)
            logs.write("serial", "new day")
            for path, contents in snapshots.items():
                self.assertEqual(path.read_bytes(), contents)
            self.assertTrue((Path(folder) / "2026-09-30-serial.log").exists())

    def test_serial_exclusive_busy_no_commands(self):
        port = Mock()
        port.open.side_effect = OSError("busy")
        serial = SerialConsole(Mock(), factory=Mock(return_value=port))
        with self.assertRaises(OSError):
            serial.connect("COM5")
        port.write.assert_not_called()
        port.close.assert_called_once()
        self.assertIsNone(serial.port)

    def test_serial_read_send_and_disconnect(self):
        received = threading.Event()
        port = Mock()
        def read(_):
            if not received.is_set():
                received.set()
                return b"status ok\n"
            threading.Event().wait(0.01)
            return b""
        port.readline.side_effect = read
        port.write.side_effect = len
        log = Mock()
        serial = SerialConsole(log, factory=Mock(return_value=port))
        serial.connect("COM5")
        self.assertTrue(received.wait(1))
        port.write.assert_not_called()
        serial.send("status ai bridge")
        port.write.assert_called_once_with(b"status ai bridge\n")
        with self.assertRaises(ValueError):
            serial.send("line1\nline2")
        serial.disconnect()
        self.assertIsNone(serial.port)
        self.assertFalse(serial.worker)

    def test_playback_rejects_external_and_traversal(self):
        for url in ("http://evil/x.wav", "/recordings/../x.wav", "/recordings/..%5cx.wav"):
            with self.assertRaises(ValueError):
                playback_path({"audio_url": url}, Path.cwd())


if __name__ == "__main__":
    unittest.main()
