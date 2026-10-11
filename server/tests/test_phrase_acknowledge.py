"""New motion contract, fake model and temporary catalog only; no hardware."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import motion_policy as policy
from services import phrase_library as lib
from services import dialogue_service as dialogue
from test_phrase_library import workbook


class AcknowledgeTests(unittest.TestCase):
    def test_catalog_registers_known_demo_id(self):
        path = Path(__file__).resolve().parents[1] / "configs/motion_catalog.json"
        items = json.loads(path.read_text(encoding="utf-8"))
        entry = next(item for item in items if item["id"] == "acknowledge")
        self.assertIs(type(entry["enabled"]), bool)  # User may enable after hardware validation.
        self.assertIn("acknowledge", policy.FIRMWARE_IDS)
        self.assertEqual(policy.parse_setting("轻摆回应"), "acknowledge")

    def test_fixed_and_model_actions_obey_enable_switch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "catalog.json"
            rules = root / "rules.txt"
            rules.write_text("仅在轻松确认时选择轻摆回应，否则none。", encoding="utf-8")
            sheet = root / "pairs.xlsx"
            workbook(sheet, [["用户示例输入", "标准输出", "动作"],
                             ["听到我了吗", "听到了，我在呢。", "轻摆回应"]])
            entries, _ = lib.read_entries(sheet)
            model = Mock()
            model.json.return_value = {"done": True, "response": json.dumps({
                "intent": "询问机器人是否听到自己", "match": True,
                "example": "听到我了吗", "motion": "acknowledge"})}
            with patch.object(policy, "CATALOG_FILE", catalog), patch.object(policy, "RULES_FILE", rules), \
                 patch.object(lib.config, "LLM_BACKEND", "ollama"), \
                 patch.object(lib.requests, "post", return_value=model):
                for enabled in (False, True, False):
                    catalog.write_text(json.dumps([
                        {"id": "none", "enabled": True, "description": "不动作"},
                        {"id": "acknowledge", "enabled": enabled, "description": "轻摆回应"}
                    ]), encoding="utf-8")
                    expected = "acknowledge" if enabled else "none"
                    self.assertEqual(policy.sanitize_motion("acknowledge"), expected)
                    self.assertEqual(lib.semantic_match("听到我了吗", entries).motion, expected)
                    self.assertEqual(dialogue.enforce_emotion_motion_consistency(
                        "听到我了吗", "听到了，我在呢。", "", "acknowledge")[1], expected)
                    for invalid in ("servo rl 88", {"angle": 88}, ["acknowledge"], "happy"):
                        self.assertEqual(policy.sanitize_motion(invalid), "none")


if __name__ == "__main__":
    unittest.main()
