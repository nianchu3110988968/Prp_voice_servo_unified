"""Offline regressions for idle history and phrase diagnostics; no real models."""
import asyncio
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ai_bridge_server as bridge
from services import dialogue_service as dialogue
from services.phrase_library import Entry
from starlette.requests import Request


class HistoryTests(unittest.TestCase):
    def setUp(self):
        old_history = list(dialogue._conversation_history)
        old_time = dialogue._last_turn_at
        self.addCleanup(lambda: dialogue._conversation_history.__setitem__(slice(None), old_history))
        self.addCleanup(setattr, dialogue, "_last_turn_at", old_time)
        dialogue.clear_conversation_history()

    def test_active_history_preserved_and_idle_history_removed(self):
        with patch.object(dialogue.time, "monotonic", return_value=100):
            dialogue.remember_turn("上一话题", "旧句式", "cute")
        with patch.object(dialogue.time, "monotonic", return_value=219):
            self.assertIn("旧句式", dialogue.build_ollama_prompt("继续", "cute"))
        with patch.object(dialogue.time, "monotonic", return_value=220):
            prompt = dialogue.build_ollama_prompt("新话题", "cute")
        self.assertNotIn("旧句式", prompt)
        self.assertIn("新话题", prompt)
        self.assertEqual(dialogue._conversation_history, [])

    def test_cached_turn_also_expires_old_history_and_refreshes_clock(self):
        with patch.object(dialogue.time, "monotonic", return_value=10):
            dialogue.remember_turn("旧", "旧回答", "cute")
        with patch.object(dialogue.time, "monotonic", return_value=200):
            dialogue.remember_turn("新", "固定回复原文", "cute")
        self.assertEqual(len(dialogue._conversation_history), 1)
        self.assertEqual(dialogue._conversation_history[0]["robot"], "固定回复原文")
        self.assertEqual(dialogue._last_turn_at, 200)


class DiagnosticTests(unittest.TestCase):
    def request(self, host="127.0.0.1", headers=None):
        return Request({"type": "http", "client": (host, 1234), "headers":
                        [(b"x-prp-maintenance", b"roles")] if headers is None else headers})

    def test_match_uses_active_cache_without_tts_or_history(self):
        entry = Entry("a" * 24, ("示例",), "原文" * 30)
        library = Mock()
        library.ready.return_value = ([entry], {})
        library.audio_for.return_value = "/phrase-audio/test.wav"
        with patch.object(bridge, "phrase_library", library), \
             patch.object(bridge.config, "PHRASE_LIBRARY_ENABLED", True), \
             patch.object(bridge, "semantic_match", return_value=entry) as match, \
             patch.object(bridge, "synthesize_reply") as tts, \
             patch.object(bridge, "remember_turn") as history:
            result = bridge.debug_phrase_match("实际识别", self.request())
        match.assert_called_once_with("实际识别", [entry])
        tts.assert_not_called()
        history.assert_not_called()
        self.assertEqual(result["reply_text"], entry.reply)
        self.assertEqual(result["status"], "hit")

    def test_diagnostic_missing_disabled_miss_and_invalid_cache_are_distinct(self):
        library = Mock()
        with patch.object(bridge, "phrase_library", library), \
             patch.object(bridge.config, "PHRASE_LIBRARY_ENABLED", True), \
             patch.object(bridge, "semantic_match", return_value=None) as match:
            library.ready.return_value = ([], {})
            self.assertEqual(bridge.debug_phrase_match("测试", self.request())["status"], "cache_missing")
            match.assert_not_called()
            library.ready.return_value = ([Entry("a", ("测试",), "回复")], {})
            self.assertEqual(bridge.debug_phrase_match("测试", self.request())["status"], "miss")
            library.ready.side_effect = ValueError("缓存指纹变化")
            with self.assertRaises(bridge.HTTPException) as caught:
                bridge.debug_phrase_match("测试", self.request())
            self.assertEqual(caught.exception.status_code, 409)
        with patch.object(bridge.config, "PHRASE_LIBRARY_ENABLED", False):
            self.assertEqual(bridge.debug_phrase_match("测试", self.request())["status"], "disabled")

    def test_diagnostic_rejects_lan_browser_missing_header_and_bad_text(self):
        requests = [self.request("192.168.1.2"), self.request(headers=[]),
                    self.request(headers=[(b"x-prp-maintenance", b"roles"), (b"origin", b"http://localhost")])]
        for request in requests:
            with self.assertRaises(bridge.HTTPException) as caught:
                bridge.debug_phrase_match("测试", request)
            self.assertEqual(caught.exception.status_code, 403)
        for text in ("", "字" * 171):
            with self.assertRaises(bridge.HTTPException) as caught:
                bridge.debug_phrase_match(text, self.request())
            self.assertEqual(caught.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
