"""Independent pairs and editable motion policy; fake LLM/TTS, no services."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import motion_policy as policy
from services import dialogue_service as dialogue
from services import phrase_library as lib
from test_phrase_library import workbook, fake_tts


class PhraseMotionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "pairs.xlsx"
        self.rows = [["用户示例输入", "标准输出", "动作"],
                     ["开始面试", "请坐", "不动作"],
                     ["你的特长", "我会摸鱼", "自动"],
                     ["你被录用了", "我会摸鱼", "开心"]]
        workbook(self.path, self.rows)
        # Always isolate from local user edits to the editable catalogue.
        self.catalog = self.root / "motion.json"
        self.catalog.write_text(json.dumps([
            {"id": id, "enabled": True, "description": id} for id in sorted(policy.FIRMWARE_IDS)
        ]), encoding="utf-8")
        self.rules = self.root / "rules.txt"
        self.rules.write_text("测试选择规则：认怂时选shy", encoding="utf-8")
        for name, value in (("CATALOG_FILE", self.catalog), ("RULES_FILE", self.rules)):
            p = patch.object(policy, name, value); p.start(); self.addCleanup(p.stop)

    def test_optional_motion_and_equal_reply_different_action(self):
        before = self.path.read_bytes()
        entries, _ = lib.read_entries(self.path)
        self.assertEqual([e.motion for e in entries], ["none", "auto", "happy"])
        self.assertEqual(len({e.id for e in entries}), 3)
        self.assertEqual(self.path.read_bytes(), before)
        workbook(self.path, [["触发台词", "固定回复"], ["你好", "你好呀"]])
        e = lib.read_entries(self.path)[0][0]
        self.assertEqual(e.motion, "auto")
        self.assertEqual(e.id, lib.digest(e.reply.encode())[:24])

    def test_same_reply_synthesized_once_with_distinct_action_ids(self):
        library = lib.PhraseLibrary(self.path, self.root / "cache")
        tts = Mock(side_effect=fake_tts)
        result = library.rebuild(tts)
        self.assertEqual(result["replies"], 2)
        self.assertEqual(tts.call_count, 2)
        entries, manifest = library.ready()
        self.assertEqual(manifest["audio"][entries[1].id], manifest["audio"][entries[2].id])

    def test_bad_action_conflicts_and_duplicate_headers_rejected(self):
        for rows in [self.rows + [["开始面试", "请坐", "开心"]],
                     [self.rows[0], ["你好", "你好呀", "随便跳舞"]],
                     [["用户输入", "标准输出", "动作", "反馈动作"], ["你好", "好", "", ""]],
                     [self.rows[0], ["", "", "开心"]]]:
            with self.subTest(rows=rows):
                workbook(self.path, rows)
                with self.assertRaises(lib.LibraryError): lib.read_entries(self.path)

    def test_arbitrary_order_repeat_and_unrelated_turn_do_not_gate_pairs(self):
        entries, _ = lib.read_entries(self.path)
        model = Mock()
        with patch.object(lib.config, "LLM_BACKEND", "ollama"), patch.object(lib.requests, "post", return_value=model) as post:
            for index in (2, 0, None, 1, 2):
                model.json.return_value = {"response": json.dumps({"id": None if index is None else entries[index].id,
                                                                   "motion": "shy"})}
                selected = lib.semantic_match("无关句" if index is None else entries[index].examples[0], entries)
                if index is None: self.assertIsNone(selected)
                else:
                    self.assertEqual(selected.reply, entries[index].reply)
                    self.assertEqual(selected.motion, ["none", "shy", "happy"][index])
                    self.assertIn("测试选择规则", post.call_args.kwargs["json"]["prompt"])
            self.assertEqual(post.call_count, 5) # Actual calls, no manufactured LLM duration.

    def test_model_action_is_not_overridden_by_keywords(self):
        for text in ("我不开心", "我很开心", "我想睡觉"):
            self.assertEqual(dialogue.enforce_emotion_motion_consistency(text, "听到了", "", "shy")[1], "shy")
        for bad in (None, {}, [], "dance", "", 12):
            self.assertEqual(policy.sanitize_motion(bad), "none")
        model = Mock()
        model.json.return_value = {"response": json.dumps({"reply_text": "坏了", "motion": "shy"})}
        with patch.object(dialogue.requests, "post", return_value=model) as post:
            self.assertEqual(dialogue.generate_ollama_reply("我好开心", "cute")["motion"], "shy")
            post.assert_called_once()
            self.assertIn("测试选择规则", post.call_args.kwargs["json"]["prompt"])
        self.assertEqual(dialogue.generate_rule_dialogue("很开心", "cute", "rule")["motion"], "none")

    def test_policy_reload_disabled_actions_and_invalid_configuration_fail_closed(self):
        items = json.loads(self.catalog.read_text(encoding="utf-8"))
        for item in items:
            if item["id"] == "happy": item["enabled"] = False
        self.catalog.write_text(json.dumps(items), encoding="utf-8")
        self.assertEqual(policy.sanitize_motion("happy"), "none")
        self.assertNotIn('"id": "happy"', policy.selection_prompt())
        entries, _ = lib.read_entries(self.path)
        model = Mock()
        model.json.return_value = {"response": json.dumps({"id": entries[2].id, "motion": "shy"})}
        with patch.object(lib.config, "LLM_BACKEND", "ollama"), patch.object(lib.requests, "post", return_value=model):
            self.assertEqual(lib.semantic_match("你被录用了", entries).motion, "none")
        self.catalog.write_text("invalid", encoding="utf-8")
        with self.assertLogs(policy.__name__, level="WARNING"):
            self.assertEqual(policy.sanitize_motion("shy"), "none")
        # Ordinary speech still has a usable prompt even if maintenance input is bad.
        self.assertIn('"id": "none"', dialogue.build_ollama_prompt("你好", "cute"))


if __name__ == "__main__":
    unittest.main()
