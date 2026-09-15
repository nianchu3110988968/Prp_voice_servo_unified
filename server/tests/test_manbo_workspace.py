"""Read-only corpus checks and isolated annotation-save regression tests."""
import ast
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

PROJECT = Path(__file__).resolve().parents[2]
DATA = PROJECT / "voice_data/manbo"
GSV = Path(r"E:\AI\GPTSoVITS\GPT-SoVITS-v2pro-20250604")


class ManboWorkspaceTests(unittest.TestCase):
    def test_canonical_corpus(self):
        report = json.loads((DATA / "dataset.json").read_text(encoding="utf-8"))
        rows = [row.split("|", 3) for row in (DATA / "clips.list").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 39)
        self.assertEqual(len(list((DATA / "clips").glob("*.wav"))), 39)
        for row, clip in zip(rows, report["clips"]):
            self.assertEqual(len(row), 4)
            self.assertEqual(row[2].lower(), "zh")
            self.assertTrue(row[3].strip())
            self.assertEqual(Path(row[0]).resolve(), Path(clip["file"]).resolve())
            self.assertEqual(hashlib.sha256(Path(row[0]).read_bytes()).hexdigest(), clip["sha256"])
            with wave.open(row[0]) as wav:
                self.assertEqual((wav.getframerate(), wav.getnchannels(), wav.getsampwidth()), (32000, 1, 2))
        self.assertEqual((DATA / "full_text.txt").read_text(encoding="utf-8"), "".join(row[3].strip() for row in rows) + "\n")
        self.assertEqual(hashlib.sha256((DATA / "full_audio.wav").read_bytes()).hexdigest(), report["full_audio_sha256"])

    def test_saved_transcript_sync_is_scoped(self):
        source = (GSV / "tools/subfix_webui.py").read_text(encoding="utf-8")
        fn = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == "b_save_list")
        with tempfile.TemporaryDirectory(prefix="manbo_save_test_") as folder:
            root = Path(folder)
            canonical = root / "clips.list"
            full = root / "full_text.txt"
            namespace = {"os": os, "g_load_file": str(canonical), "g_data_json": [
                {"wav_path": "001.wav", "speaker_name": "manbo", "language": "zh", "text": "第一句。"},
                {"wav_path": "002.wav", "speaker_name": "manbo", "language": "zh", "text": "第二句。"},
            ]}
            exec(compile(ast.Module(body=[fn], type_ignores=[]), "annotation_save_test", "exec"), namespace)
            with patch.dict(os.environ, {"PRP_DATASET_LIST": str(canonical), "PRP_FULL_TEXT_PATH": str(full)}):
                namespace["b_save_list"]()
                self.assertEqual(full.read_text(encoding="utf-8"), "第一句。第二句。\n")
                self.assertEqual(len(canonical.read_text(encoding="utf-8").splitlines()), 2)
                namespace["g_load_file"] = str(root / "unrelated.list")
                namespace["g_data_json"][0]["text"] = "其它数据。"
                namespace["b_save_list"]()
                self.assertEqual(full.read_text(encoding="utf-8"), "第一句。第二句。\n")
                self.assertFalse(Path(str(full) + ".tmp").exists())


if __name__ == "__main__":
    unittest.main()
