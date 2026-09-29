"""Offline role/supervisor regressions: temporary files, fake HTTP and fake processes."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.role_config import load_role, file_sha, list_roles
from services import role_runtime as runtime, dialogue_service as dialogue, phrase_library as library
import launcher_core as launcher
import ai_bridge_server as bridge
from starlette.requests import Request


class RoleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "server/roles").mkdir(parents=True)
        (self.root / "server/prompts").mkdir()
        for name, value in (("server/prompts/Star.txt", "你是星星，简洁温暖。"), ("voice.ckpt", "GPT"), ("voice.pth", "SoVITS"), ("ref.wav", "fake")):
            (self.root / name).write_text(value, encoding="utf-8")
        self.data = dict(id="Star", display_name="星星", character_name="星星", persona_prompt_file="server/prompts/Star.txt",
            gpt_weights="voice.ckpt", sovits_weights="voice.pth", gpt_sovits_version="v2ProPlus",
            reference_wav="ref.wav", reference_text="参考原文", prompt_language="zh", text_language="zh",
            phrase_voice_revision="v1", weight_pair=dict(id="same-experiment", version="v2ProPlus",
                gpt_sha256=file_sha(self.root / "voice.ckpt"), sovits_sha256=file_sha(self.root / "voice.pth")))
        self.save()
        self.role = load_role("Star", self.root)
        for target, field in ((runtime, "current"), (runtime, "voice_ready"), (runtime, "last_tts"),
                              (dialogue, "PERSONA_PROMPT"), (dialogue, "PERSONA_PROMPT_NAME"),
                              (dialogue, "CHARACTER_NAME"), (dialogue, "_conversation_history")):
            p = patch.object(target, field, getattr(target, field).copy() if isinstance(getattr(target, field), (dict, list)) else getattr(target, field))
            p.start()
            self.addCleanup(p.stop)
        import server_config
        for field in ("PERSONA_PROMPT_NAME", "PERSONA_PROMPT_FILE", "TTS_BACKEND", "GPT_SOVITS_REFERENCE_WAV",
                      "GPT_SOVITS_PROMPT_TEXT", "GPT_SOVITS_PROMPT_LANGUAGE", "GPT_SOVITS_TEXT_LANGUAGE", "PHRASE_VOICE_REVISION"):
            p = patch.object(server_config, field, getattr(server_config, field))
            p.start()
            self.addCleanup(p.stop)
        runtime.current = None
        runtime.voice_ready = False

    def save(self):
        (self.root / "server/roles/Star.local.json").write_text(json.dumps(self.data), encoding="utf-8")

    def test_parse_relative_files_and_list_only_local(self):
        self.assertEqual(self.role.persona_prompt, "你是星星，简洁温暖。")
        self.assertTrue(Path(self.role.gpt_weights).is_absolute())
        self.assertLess(len(("/phrase-audio/" + self.role.url_token + "/" + "a" * 64 + ".wav").encode()), 160)
        (self.root / "server/roles/Other.example.json").write_text("{}")
        self.assertEqual(list_roles(self.root), ["Star"])

    def test_reject_invalid_id(self):
        for name in ("../Star", "bad/name", "", "1Star", "a.b"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                load_role(name, self.root)

    def test_missing_file_empty_reference_and_mismatched_pair(self):
        for key, value in (("reference_wav", "missing.wav"), ("reference_text", "  "),
                           ("id", "Another"), ("gpt_sovits_version", "bad")):
            original = self.data[key]
            self.data[key] = value
            self.save()
            with self.subTest(key=key), self.assertRaises(ValueError):
                load_role("Star", self.root)
            self.data[key] = original
        self.data["weight_pair"]["gpt_sha256"] = "0" * 64
        self.save()
        with self.assertRaisesRegex(ValueError, "配对"):
            load_role("Star", self.root)

    def test_tampered_weight_rejected(self):
        (self.root / "voice.pth").write_text("different-character")
        with self.assertRaisesRegex(ValueError, "配对"):
            load_role("Star", self.root)

    def test_switch_clears_history_and_removes_old_identity(self):
        dialogue._conversation_history.append({"user": "糯糯", "robot": "旧回答", "style": "cute"})
        with patch.object(runtime, "_load_pair"):
            runtime.switch_role("Star", loader=lambda _: self.role)
        self.assertEqual(dialogue._conversation_history, [])
        prompt = dialogue.build_ollama_prompt("你好", "cute")
        self.assertIn("星星", prompt)
        self.assertNotIn("糯糯", prompt)
        for word in ("小角", "肚子", "尾巴"):
            self.assertNotIn(word, prompt)
        with patch.object(dialogue, "LLM_BACKEND", "rule"):
            result = dialogue.generate_healing_reply("你是谁")
        self.assertIn("星星", result["reply_text"])
        self.assertTrue({"reply_text", "style", "emotion", "motion"} <= result.keys())

    def test_second_weight_failure_rolls_back_both_and_preserves_history(self):
        runtime.activate(self.role)
        dialogue.remember_turn("原对话", "原回答", "cute")
        before = dialogue._conversation_history.copy()
        candidate = replace(self.role, id="Moon", gpt_weights="moon.ckpt", sovits_weights="moon.pth")
        good = Mock()
        good.json.return_value = {"message": "success"}
        with patch.object(runtime.requests, "get", side_effect=[good, RuntimeError("SoVITS failed"), good, good]) as get:
            with self.assertRaisesRegex(RuntimeError, "已恢复"):
                runtime.switch_role("Moon", loader=lambda _: candidate)
        self.assertEqual([c.kwargs["params"]["weights_path"] for c in get.call_args_list],
                         [candidate.gpt_weights, candidate.sovits_weights, self.role.gpt_weights, self.role.sovits_weights])
        self.assertIs(runtime.current, self.role)
        self.assertTrue(runtime.voice_ready)
        self.assertEqual(dialogue._conversation_history, before)

    def test_rollback_failure_blocks_primary_tts(self):
        runtime.activate(self.role)
        with patch.object(runtime, "_load_pair", side_effect=RuntimeError("offline")):
            with self.assertRaisesRegex(RuntimeError, "隔离"):
                runtime.switch_role("Star", loader=lambda _: self.role)
        self.assertFalse(runtime.voice_ready)
        from services import tts_service
        with patch.object(tts_service.requests, "get") as request:
            result = tts_service._synthesize_gpt_sovits("hello", self.root)
        request.assert_not_called()
        self.assertEqual(result["status"], "unverified_weights")

    def test_validation_failure_never_touches_weights(self):
        with patch.object(runtime, "_load_pair") as pair:
            with self.assertRaises(ValueError):
                runtime.switch_role("bad", loader=Mock(side_effect=ValueError("bad config")))
        pair.assert_not_called()

    def test_role_revision_cache_isolation_preserves_old_files(self):
        cache = library.PhraseLibrary(self.root / "unused.xlsx", self.root / "cache")
        runtime.current = self.role
        runtime.voice_ready = True
        first = cache.cache_dir
        first.mkdir(parents=True)
        (first / "manifest.json").write_text("old")
        first_signature = library.voice_signature()
        runtime.current = replace(self.role, phrase_voice_revision="v2")
        self.assertNotEqual(first, cache.cache_dir)
        self.assertNotEqual(first_signature, library.voice_signature())
        self.assertEqual(cache.ready(), ([], {}))
        self.assertTrue((first / "manifest.json").exists())
        runtime.current = replace(self.role, id="Moon")
        self.assertNotEqual(first, cache.cache_dir)
        with self.assertRaises(bridge.HTTPException):
            bridge.get_role_phrase_audio(self.role.url_token, "a" * 64 + ".wav")

    def test_dynamic_reference_and_actual_fallback_backend(self):
        from services import tts_service as tts
        runtime.activate(self.role)
        runtime.voice_ready = True
        response = Mock(content=b"fake WAV")
        def normalize(data, destination):
            destination.write_bytes(b"normalized")
        with patch.object(tts.requests, "get", return_value=response) as get, patch.object(tts, "_normalize_wav_bytes", side_effect=normalize):
            result = tts.synthesize_reply("测试", self.root)
        self.assertEqual(get.call_args.kwargs["params"]["ref_audio_path"], self.role.reference_wav)
        self.assertEqual(get.call_args.kwargs["params"]["prompt_text"], self.role.reference_text)
        self.assertEqual(runtime.last_tts["backend"], "gpt_sovits")
        runtime.voice_ready = False
        with patch.object(tts, "TTS_FALLBACK_TO_SAPI", True), patch.object(tts, "_synthesize_windows_sapi", return_value={"audio_url": "/recordings/fake.wav", "status": "ok", "backend": "windows_sapi", "detail": ""}):
            result = tts.synthesize_reply("测试", self.root)
        self.assertEqual(result["backend"], "gpt_sovits_fallback_windows_sapi")
        self.assertEqual(runtime.last_tts["backend"], result["backend"])

    def test_generated_yaml_uses_role_and_does_not_edit_legacy(self):
        folder = self.root / "server/configs"
        folder.mkdir()
        legacy = folder / "gpt_sovits_v2proplus.yaml"
        legacy.write_text("user edits")
        path = launcher.generated_yaml({"project_root": str(self.root)}, self.role)
        data = json.loads(path.read_text(encoding="utf-8"))["custom"]
        self.assertEqual(data["t2s_weights_path"], self.role.gpt_weights)
        self.assertEqual(data["vits_weights_path"], self.role.sovits_weights)
        self.assertEqual(legacy.read_text(), "user edits")

    def test_switch_maintenance_rejects_browser_and_lan(self):
        for host, headers in (("192.168.0.2", []), ("127.0.0.1", [(b"origin", b"http://evil.test")])):
            req = Request({"type": "http", "client": (host, 10), "headers": [(b"x-prp-maintenance", b"roles")] + headers})
            with self.assertRaises(bridge.HTTPException):
                bridge.switch_role("Star", req)


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.supervisor = launcher.Supervisor({"project_root": self.temp.name}, log=lambda _: None)

    def test_healthy_port_reused_without_ownership(self):
        with patch.object(launcher, "probe", return_value={"state": "healthy"}), patch.object(launcher.subprocess, "Popen") as popen:
            self.supervisor.ensure("ollama", None)
        popen.assert_not_called()
        self.assertEqual(self.supervisor.owned, {})

    def test_unknown_port_never_started_or_killed(self):
        with patch.object(launcher, "probe", return_value={"state": "occupied_unknown"}), patch.object(launcher.subprocess, "Popen") as popen:
            with self.assertRaises(RuntimeError):
                self.supervisor.ensure("bridge", None)
        popen.assert_not_called()

    def test_stop_only_live_owned_handles_ignores_pid_file(self):
        own, exited = Mock(pid=123), Mock(pid=456)
        own.poll.return_value = None
        exited.poll.return_value = 0
        self.supervisor.owned = {"bridge": own, "gpt_sovits": exited}
        self.supervisor.audit_path.parent.mkdir(parents=True)
        self.supervisor.audit_path.write_text('{"ollama":{"pid":999}}')
        with patch.object(launcher, "port_open", return_value=True):
            self.supervisor.stop_owned()
        own.terminate.assert_called_once()
        exited.terminate.assert_not_called()
        self.assertEqual(self.supervisor.owned, {})

    def test_start_order_and_reuse_of_active_role(self):
        role = Mock()
        role.public.return_value = {"id": "Star"}
        events = []
        health = {"role": role.public(), "voice_ready": True, "warmup": {"asr": "ok", "llm": "ok"}}
        def ensure(name, candidate):
            events.append(name)
            return {"data": health}
        with patch.object(launcher, "load_role", return_value=role), patch.object(launcher, "probe", return_value={"state": "healthy"}), patch.object(self.supervisor, "ensure", side_effect=ensure), patch.object(launcher, "request_json", return_value=health), patch.object(self.supervisor, "switch") as switch:
            self.supervisor.start_all("Star")
        self.assertEqual(events, ["ollama", "gpt_sovits", "bridge"])
        switch.assert_not_called()

    def test_port_identity_requires_expected_api(self):
        with patch.object(launcher, "port_open", return_value=True), patch.object(launcher, "request_json", return_value={"status": "ok"}):
            self.assertEqual(launcher.probe("bridge")["state"], "occupied_unknown")
            self.assertEqual(launcher.probe("gpt_sovits")["state"], "occupied_unknown")


if __name__ == "__main__":
    unittest.main()
