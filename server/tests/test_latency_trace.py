"""Offline protocol/trace tests; no real ASR, LLM, TTS, network or hardware."""
import asyncio
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from starlette.requests import Request
from starlette.responses import Response
import ai_bridge_server as bridge
from services.latency_trace import RequestTrace, measure_stage


class LatencyTraceTests(unittest.TestCase):
    def invoke(self, request_id=None, fail_asr=False):
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
        with tempfile.TemporaryDirectory(prefix="prp_trace_test_") as directory:
            with patch.object(bridge, "RECORDINGS_DIR", Path(directory)), \
                 patch.object(bridge, "transcribe_audio", side_effect=RuntimeError("ASR test error") if fail_asr else None,
                              return_value={"text": "你好", "status": "ok", "backend": "test"}), \
                 patch.object(bridge, "generate_healing_reply", return_value={"reply_text": "你好呀", "motion": "none", "status": "ok", "backend": "test"}), \
                 patch.object(bridge, "synthesize_reply", return_value={"audio_url": "/recordings/test.wav", "status": "ok", "backend": "test"}), \
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
        events = [json.loads(line[len("[voice_trace] "):]) for line in output.getvalue().splitlines() if line.startswith("[voice_trace] ")]
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

    def test_measure_stage_preserves_result_and_exception(self):
        marker = object()
        value, duration = measure_stage("test", lambda: marker)
        self.assertIs(value, marker)
        self.assertGreaterEqual(duration, 0)
        with patch("builtins.print", side_effect=OSError("closed log")):
            trace = RequestTrace("esp-closed-log")
            value, _ = measure_stage("test", lambda: marker, trace)
            self.assertIs(value, marker)


if __name__ == "__main__":
    unittest.main()
