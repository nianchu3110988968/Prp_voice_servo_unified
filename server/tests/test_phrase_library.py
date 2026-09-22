"""Offline tests; only temporary workbooks/audio and fake model calls."""
import asyncio
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import wave
from xml.sax.saxutils import escape
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from starlette.requests import Request
from starlette.responses import Response
import ai_bridge_server as bridge
from services import phrase_library as lib
from services.phrase_jobs import PhraseJobs
from services.latency_trace import RequestTrace


def workbook(path, rows, formula=False):
    cells = []
    for n, row in enumerate(rows, 1):
        body = "".join(f'<c r="{chr(65+c)}{n}" t="inlineStr"><is><t>{escape(v)}</t></is>'
                       + ('<f>1+1</f>' if formula and n == 2 and c == 0 else '') + '</c>'
                       for c, v in enumerate(row))
        cells.append(f'<row r="{n}">{body}</row>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                   '<sheets><sheet name="Sheet1" sheetId="1" r:id="r1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<sheetData>' + ''.join(cells) + '</sheetData></worksheet>')


def fake_tts(text, directory):
    target = directory / "reply.wav"
    with wave.open(str(target), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x01\x00" * 1600)
    return {"audio_url": "/recordings/reply.wav", "status": "ok", "backend": lib.config.TTS_BACKEND}


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="prp_phrase_test_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "library.xlsx"
        self.library = lib.PhraseLibrary(self.path, self.root / "cache")
        self.rows = [["用户示例输入", "标准输出"], ["你好", "你好呀"], ["早上好", "你好呀"]]
        workbook(self.path, self.rows)

    def test_group_examples_and_never_modify_workbook(self):
        before = self.path.read_bytes()
        entries, _ = lib.read_entries(self.path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].examples, ("你好", "早上好"))
        self.assertEqual(self.path.read_bytes(), before)

    def test_blank_missing_headers_partial_duplicate_formula_long_rejected(self):
        cases = [[], [["a", "b"]], [self.rows[0], ["你好", ""]],
                 self.rows + [["你好", "不同回复"]], [self.rows[0], ["你好", "字" * 81]]]
        for rows in cases:
            with self.subTest(rows=rows):
                workbook(self.path, rows)
                with self.assertRaises(lib.LibraryError):
                    lib.read_entries(self.path)
        workbook(self.path, self.rows, formula=True)
        with self.assertRaises(lib.LibraryError):
            lib.read_entries(self.path)

    def test_fixed_reply_above_48_chars_is_preserved(self):
        text = "长" * 60
        workbook(self.path, [self.rows[0], ["测试", text]])
        self.assertEqual(lib.read_entries(self.path)[0][0].reply, text)

    def test_publish_validate_and_detect_excel_change(self):
        result = self.library.rebuild(fake_tts)
        self.assertEqual(result["replies"], 1)
        entries, manifest = self.library.ready()
        url = self.library.audio_for(entries[0], manifest)
        self.assertRegex(url, r"^/phrase-audio/[a-f0-9]{64}\.wav$")
        workbook(self.path, self.rows + [["再见", "拜拜"]])
        with self.assertRaisesRegex(lib.LibraryError, "改变"):
            self.library.ready()

    def test_cache_missing_corrupt_and_voice_revision(self):
        self.assertEqual(self.library.ready(), ([], {}))
        self.library.rebuild(fake_tts)
        entries, manifest = self.library.ready()
        audio = self.library.cache_dir / (manifest["audio"][entries[0].id] + ".wav")
        audio.write_bytes(b"bad")
        with self.assertRaises(lib.LibraryError):
            self.library.audio_for(entries[0], manifest)
        with patch.object(lib.config, "PHRASE_VOICE_REVISION", "different-model"):
            with self.assertRaises(lib.LibraryError):
                self.library.ready()

    def test_failed_rebuild_preserves_previous_manifest_and_source(self):
        self.library.rebuild(fake_tts)
        manifest = (self.library.cache_dir / "manifest.json").read_bytes()
        before = self.path.read_bytes()
        with self.assertRaises(lib.LibraryError):
            self.library.rebuild(lambda *_: {"status": "ok", "backend": "gpt_sovits_fallback_windows_sapi"})
        self.assertEqual((self.library.cache_dir / "manifest.json").read_bytes(), manifest)
        self.assertEqual(self.path.read_bytes(), before)

    def test_signature_change_during_generation_not_published(self):
        self.library.rebuild(fake_tts)
        before = (self.library.cache_dir / "manifest.json").read_bytes()
        with patch.object(lib, "voice_signature", side_effect=["old", "new"]):
            with self.assertRaisesRegex(lib.LibraryError, "生成期间"):
                self.library.rebuild(fake_tts)
        self.assertEqual((self.library.cache_dir / "manifest.json").read_bytes(), before)

    def test_llm_id_validation_and_no_keyword_shortcut(self):
        entries, _ = lib.read_entries(self.path)
        model = Mock()
        model.json.return_value = {"response": json.dumps({"id": entries[0].id})}
        with patch.object(lib.config, "LLM_BACKEND", "ollama"), patch.object(lib.requests, "post", return_value=model) as post:
            self.assertIs(lib.semantic_match("您好呀", entries), entries[0])
            post.assert_called_once()
            self.assertIn("您好呀", post.call_args.kwargs["json"]["prompt"])
            model.json.return_value = {"response": '{"id": null}'}
            self.assertIsNone(lib.semantic_match("完全无关", entries))
            for bad in ['{"id":"../../bad"}', '[]', '{}']:
                model.json.return_value = {"response": bad}
                with self.assertRaises(lib.LibraryError):
                    lib.semantic_match("你好", entries)

    def test_no_model_request_for_empty_text_or_library(self):
        with patch.object(lib.requests, "post") as post:
            self.assertIsNone(lib.semantic_match("", lib.read_entries(self.path)[0]))
            self.assertIsNone(lib.semantic_match("你好", []))
            post.assert_not_called()


class JobTests(unittest.TestCase):
    def test_bounded_pending_expired_failed_and_cleanup(self):
        jobs = PhraseJobs(capacity=1, retention=0, timeout=-1)
        release, started = threading.Event(), threading.Event()
        def operation():
            started.set()
            release.wait(2)
            raise ValueError("fake")
        try:
            key = jobs.submit("esp-one", operation)
            self.assertTrue(started.wait(1))
            self.assertIsNone(jobs.submit("esp-two", lambda: {}))
            self.assertEqual(jobs.get(key)["error"], "timeout")
            # Timed out running jobs retain capacity; no unlimited stranded workers.
            self.assertIsNone(jobs.submit("esp-three", lambda: {}))
        finally:
            release.set()
            jobs.close()
        self.assertIsNone(jobs.get(key))

    def test_exception_is_failure_not_ready(self):
        jobs = PhraseJobs()
        key = jobs.submit("esp-error", lambda: 1 / 0)
        jobs.close()
        self.assertEqual(jobs.get(key)["job_status"], "failed")


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="prp_phrase_pipeline_")
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.jobs = PhraseJobs()
        self.addCleanup(self.jobs.close)
        self.entry = lib.Entry("a" * 24, ("你好",), "固定" * 30)
        self.library = Mock()
        self.library.ready.return_value = ([self.entry], {})
        self.library.audio_for.return_value = "/phrase-audio/" + "b" * 64 + ".wav"
        self.asr = {"text": "您好呀这是实际识别", "status": "ok", "backend": "fake_asr"}
        self.dialogue = {"reply_text": "正常回复", "motion": "none", "status": "ok", "backend": "fake_llm"}
        self.logs = io.StringIO()
        for target, name, value in ((bridge, "phrase_library", self.library), (bridge, "phrase_jobs", self.jobs),
                                    (bridge, "RECORDINGS_DIR", self.directory), (bridge.config, "PHRASE_LIBRARY_ENABLED", True)):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def request(self, capability=True):
        headers = [(b"x-request-id", b"esp-phrase-test")]
        if capability:
            headers.append((b"x-voice-capabilities", b"phrase-cache-v1"))
        async def receive():
            return {"type": "http.request", "body": b"\x01\x00" * 160, "more_body": False}
        return Request({"type": "http", "method": "POST", "path": "/voice/interact", "headers": headers}, receive)

    def invoke(self, match=True, capability=True, tts=fake_tts):
        with patch.object(bridge, "transcribe_audio", return_value=self.asr), \
             patch.object(bridge, "semantic_match", return_value=self.entry if match else None) as semantic, \
             patch.object(bridge, "generate_healing_reply", return_value=self.dialogue) as normal, \
             patch.object(bridge, "remember_turn") as memory, \
             patch.object(bridge, "synthesize_reply", side_effect=tts), redirect_stdout(self.logs):
            result = asyncio.run(bridge.voice_interact(self.request(capability), Response()))
            # Drain ordinary instantaneous fakes while patch/console scope is alive.
            if result.get("phrase_hit") and tts is fake_tts:
                self.jobs.close()
        return result, semantic, normal, memory

    def test_legacy_unchanged_and_no_semantic_call(self):
        result, semantic, normal, _ = self.invoke(capability=False)
        self.assertNotIn("phrase_hit", result)
        self.assertEqual(result["reply_text"], "正常回复")
        semantic.assert_not_called()
        normal.assert_called_once()

    def test_hit_preserves_asr_fixed_reply_and_calls_tts_with_exact_text(self):
        result, semantic, normal, memory = self.invoke()
        self.assertTrue(result["phrase_hit"])
        self.assertEqual(result["recognized_text"], self.asr["text"])
        self.assertEqual(result["reply_text"], self.entry.reply)
        self.assertEqual(result["tts_status"], "pending")
        self.assertEqual(result["timings_ms"]["tts"], -1)
        normal.assert_not_called()
        memory.assert_called_once_with(self.asr["text"], self.entry.reply, "cute")
        final = self.jobs.get(result["job_url"].rsplit("/", 1)[1])
        self.assertEqual(final["job_status"], "ready")
        self.assertGreaterEqual(final["timings_ms"]["tts"], 0)
        self.assertGreaterEqual(final["timings_ms"]["background_total"], final["timings_ms"]["total_request"])
        self.assertEqual(self.logs.getvalue().count("【词库命中】"), 1)
        self.assertEqual(self.logs.getvalue().count("识别："), 1)
        self.assertNotIn("预设演示文本", self.logs.getvalue())
        self.assertIn("[后台]", self.logs.getvalue())

    def test_response_does_not_wait_for_tts_and_audio_route_stays_available(self):
        started, release = threading.Event(), threading.Event()
        def slow_tts(text, directory):
            self.assertEqual(text, self.entry.reply)
            started.set()
            self.assertTrue(release.wait(3))
            return fake_tts(text, directory)
        try:
            result, _, _, _ = self.invoke(tts=slow_tts)
            self.assertTrue(started.wait(1))
            self.assertFalse(release.is_set())
            self.assertEqual(self.jobs.get(result["job_url"].rsplit("/", 1)[1])["job_status"], "pending")
            self.library.cache_dir = self.directory
            file_name = "b" * 64 + ".wav"
            (self.directory / file_name).write_bytes(b"fake-route-only")
            self.assertIsInstance(bridge.get_phrase_audio(file_name), bridge.FileResponse)
        finally:
            release.set()
            self.jobs.close()

    def test_miss_and_missing_cache_return_normal(self):
        result, _, normal, _ = self.invoke(match=False)
        self.assertNotIn("phrase_hit", result)
        normal.assert_called_once()
        self.library.audio_for.side_effect = FileNotFoundError("missing")
        result, _, normal, _ = self.invoke()
        self.assertNotIn("phrase_hit", result)
        normal.assert_called_once()

    def test_saturated_jobs_return_normal_without_duplicate_history(self):
        with patch.object(self.jobs, "submit", return_value=None):
            result, _, normal, memory = self.invoke()
        self.assertNotIn("phrase_hit", result)
        normal.assert_called_once()
        memory.assert_not_called()

    def test_job_route_requires_same_request_id_and_returns_compact_timings(self):
        result, _, _, _ = self.invoke()
        job_id = result["job_url"].rsplit("/", 1)[1]
        response = Response()
        final = asyncio.run(bridge.get_voice_job(job_id, self.request(), response))
        self.assertEqual(response.headers["x-request-id"], "esp-phrase-test")
        self.assertNotIn("recognized_text", final)
        self.assertEqual(final["timings_ms"]["asr"], result["timings_ms"]["asr"])
        req = Request({"type": "http", "headers": [(b"x-request-id", b"wrong")]})
        with self.assertRaises(bridge.HTTPException) as exc:
            asyncio.run(bridge.get_voice_job(job_id, req, Response()))
        self.assertEqual(exc.exception.status_code, 404)

    def test_maintenance_rejects_lan_and_browser_origin(self):
        for host, extra in (("192.168.1.2", []), ("127.0.0.1", [(b"origin", b"http://example.test")])):
            req = Request({"type": "http", "headers": [(b"x-prp-maintenance", b"phrase-library")] + extra,
                           "client": (host, 1234)})
            with self.assertRaises(bridge.HTTPException) as exc:
                bridge.rebuild_phrase_library(req)
            self.assertEqual(exc.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
