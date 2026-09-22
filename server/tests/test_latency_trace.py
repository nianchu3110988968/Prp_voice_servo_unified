"""Offline protocol/trace tests; no real ASR, LLM, TTS, network or hardware."""
import asyncio
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from starlette.requests import Request
from starlette.responses import Response
import ai_bridge_server as bridge
from services.latency_trace import RequestTrace, measure_stage


class LatencyTraceTests(unittest.TestCase):
    def invoke(self, request_id=None, fail_asr=False, fallback=False):
        body = b"\x00\x00" * 160
        headers = [(b"x-sample-rate", b"16000")]
        if request_id is not None:
            headers.append((b"x-request-id", request_id.encode()))
        sent = False

        async def receive():
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        req = Request({"type": "http", "headers": headers, "method": "POST", "path": "/voice/interact"}, receive)
        response = Response()
        output = io.StringIO()
        events = []
        original_event = RequestTrace.event

        def capture_event(trace, name, at=None, **fields):
            when = time.perf_counter() if at is None else at
            events.append({"request_id": trace.request_id, "event": name,
                           "mono_us": int(when * 1_000_000), **fields})
            return original_event(trace, name, when, **fields)

        with tempfile.TemporaryDirectory(prefix="prp_trace_test_") as directory:
            with patch.object(bridge, "RECORDINGS_DIR", Path(directory)), \
                 patch.object(RequestTrace, "event", capture_event), \
                 patch.object(bridge, "transcribe_audio", side_effect=RuntimeError("ASR test error") if fail_asr else None,
                              return_value={"text": "你好", "status": "ok", "backend": "test"}), \
                 patch.object(bridge, "generate_healing_reply", return_value={"reply_text": "你好呀", "motion": "none", "status": "ok", "backend": "test"}), \
                 patch.object(bridge, "synthesize_reply", return_value={"audio_url": "/recordings/test.wav", "status": "ok", "backend": "gpt_sovits_fallback_windows_sapi" if fallback else "test", "detail": "primary unavailable" if fallback else ""}), \
                 redirect_stdout(output):
                if fail_asr:
                    with self.assertRaisesRegex(RuntimeError, "ASR test error"):
                        asyncio.run(bridge.voice_interact(req, response))
                    payload = None
                else:
                    payload = asyncio.run(bridge.voice_interact(req, response))
                    self.assertEqual(len(list(Path(directory).glob("*.pcm"))), 1)
                    self.assertEqual(next(Path(directory).glob("*.pcm")).read_bytes(), body)
                    self.assertEqual(len(list(Path(directory).glob("*.wav"))), 1)
        self.logs = output.getvalue()
        return payload, response, events

    def test_success_correlates_existing_protocol_and_timings(self):
        payload, response, events = self.invoke("esp-test-001")
        self.assertEqual(response.headers["x-request-id"], "esp-test-001")
        self.assertTrue(all(event["request_id"] == "esp-test-001" for event in events))
        self.assertEqual(payload["recognized_text"], "你好")
        self.assertEqual(payload["reply_text"], "你好呀")
        self.assertEqual(payload["audio_url"], "/recordings/test.wav")
        self.assertEqual(payload["motion"], "none")
        durations = payload["timings_ms"]
        self.assertEqual(set(durations), {"asr", "dialogue", "tts", "total_pipeline", "body_receive", "prepare_audio", "total_request"})
        self.assertTrue(all(isinstance(v, int) and v >= 0 for v in durations.values()))
        self.assertGreaterEqual(durations["total_request"], durations["total_pipeline"])
        by_name = {event["event"]: event for event in events}
        self.assertEqual(by_name["response_ready"]["timings_ms"], durations)
        for name in ("asr", "dialogue", "tts"):
            self.assertEqual(by_name[name + "_end"]["duration_ms"], durations[name])
            self.assertLessEqual(by_name[name + "_start"]["mono_us"], by_name[name + "_end"]["mono_us"])
        self.assertEqual([e["mono_us"] for e in events], sorted(e["mono_us"] for e in events))
        self.assertLess(len(json.dumps(payload, ensure_ascii=False).encode()), 2048)

    def test_old_client_without_header_remains_compatible(self):
        payload, response, events = self.invoke()
        self.assertRegex(response.headers["x-request-id"], r"^[a-f0-9]{32}$")
        self.assertEqual(payload["tts_status"], "ok")

    def test_invalid_id_is_not_reflected(self):
        _, response, _ = self.invoke("bad id\r\nspoof")
        self.assertRegex(response.headers["x-request-id"], r"^[a-f0-9]{32}$")

    def test_failure_not_reported_as_success(self):
        payload, _, events = self.invoke("esp-test-error", fail_asr=True)
        self.assertIsNone(payload)
        self.assertEqual(events[-1]["event"], "request_failed")
        self.assertNotIn("response_ready", [e["event"] for e in events])
        self.assertEqual(next(e for e in events if e["event"] == "asr_end")["status"], "failed")
        self.assertIn("语音识别失败", self.logs)
        self.assertIn("请求失败", self.logs)
        self.assertNotIn("整请求=", self.logs)

    def test_chinese_summary_is_compact_and_uses_payload_timings(self):
        payload, _, _ = self.invoke("esp-demo-001")
        lines = self.logs.splitlines()
        self.assertEqual(len(lines), 6)
        self.assertTrue(all(line.startswith("[服务端][esp-demo-001]") for line in lines))
        self.assertNotIn("[voice_trace]", self.logs)
        self.assertNotIn("[ai_bridge]", self.logs)
        for key, label in (("asr", "语音识别"), ("dialogue", "大模型响应时间"), ("tts", "语音合成"),
                           ("body_receive", "收包"), ("prepare_audio", "音频预处理"),
                           ("total_pipeline", "AI流水线"), ("total_request", "整请求")):
            self.assertIn(f"{label}={payload['timings_ms'][key]}ms", self.logs)
        self.assertEqual(self.logs.count("识别："), 1)
        self.assertEqual(self.logs.count("回复："), 1)
        self.assertIn("归一化倍率≈0.0倍", self.logs)

    def test_fallback_is_not_hidden_by_summary(self):
        payload, _, _ = self.invoke("esp-fallback", fallback=True)
        self.assertEqual(payload["tts_status"], "ok")
        self.assertIn("TTS=ok/gpt_sovits_fallback_windows_sapi", self.logs)
        self.assertIn("合成非正常后端结果", self.logs)
        self.assertIn("primary unavailable", self.logs)

    def test_log_escapes_control_characters(self):
        from services.latency_trace import quoted
        self.assertEqual(json.loads(quoted("你好\n[伪造]\x1b")), "你好\n[伪造]\x1b")
        self.assertNotIn("\n", quoted("你好\n[伪造]"))

    def test_measure_stage_preserves_result_and_exception(self):
        marker = object()
        value, duration = measure_stage("test", lambda: marker)
        self.assertIs(value, marker)
        self.assertGreaterEqual(duration, 0)
        with patch("builtins.print", side_effect=OSError("closed log")):
            trace = RequestTrace("esp-closed-log")
            value, _ = measure_stage("test", lambda: marker, trace)
            self.assertIs(value, marker)

    def test_summary_with_closed_console_preserves_response(self):
        with patch("builtins.print", side_effect=ValueError("closed file")):
            payload, _, _ = self.invoke("esp-closed-summary")
        self.assertEqual(payload["reply_text"], "你好呀")


if __name__ == "__main__":
    unittest.main()
