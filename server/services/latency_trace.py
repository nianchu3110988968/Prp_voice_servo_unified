"""Request-scoped diagnostic timings; never compare this clock to ESP uptime."""
import json
import re
import time
from uuid import uuid4


def log_line(message: str):
    """A closed/broken console must not change the voice interaction result."""
    try:
        print(message, flush=True)
    except (OSError, ValueError):
        pass


def quoted(value) -> str:
    # Escape newlines/control characters so model output cannot forge log lines.
    return json.dumps(str(value), ensure_ascii=False)


class RequestTrace:
    def __init__(self, supplied_id: str | None = None):
        self.request_id = supplied_id if supplied_id and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", supplied_id) else uuid4().hex
        self.started = time.perf_counter()
        self.event("request_start", self.started)

    def event(self, event: str, at: float | None = None, **fields):
        at = time.perf_counter() if at is None else at
        prefix = f"[服务端][{self.request_id}]"
        if event == "request_start":
            log_line(f"{prefix} 收到语音请求")
        elif event == "request_failed":
            log_line(f"{prefix} 请求失败：{fields.get('error_type', 'unknown')}")
        elif event.endswith("_end") and fields.get("status") == "failed":
            label = {"asr_end": "语音识别", "dialogue_end": "回复生成", "tts_end": "语音合成"}.get(event, event)
            log_line(f"{prefix} {label}失败，已耗时={fields.get('duration_ms', -1)}ms")
        elif event == "phrase_ready":
            result = fields["response"]
            log_line(f"{prefix} 【词库命中】识别：{quoted(result['recognized_text'])} | 回复：{quoted(result['reply_text'])}")
        elif event in {"response_ready", "background_ready"}:
            timings = fields["timings_ms"]
            result = fields["response"]
            if event == "response_ready":
                log_line(f"{prefix} 识别：{quoted(result['recognized_text'])} | 回复：{quoted(result['reply_text'])}")
            else:
                prefix += "[后台]"
            log_line(f"{prefix} 语音识别={timings['asr']}ms | 大模型响应时间={timings['dialogue']}ms | 语音合成={timings['tts']}ms")
            log_line(f"{prefix} 收包={timings['body_receive']}ms | 音频预处理={timings['prepare_audio']}ms | "
                     f"AI流水线={timings['total_pipeline']}ms | "
                     + (f"首包就绪={timings['total_request']}ms | 后台完成={timings['background_total']}ms"
                        if event == "background_ready" else f"整请求={timings['total_request']}ms"))
            log_line(f"{prefix} 后端：ASR={result['asr_status']}/{result['asr_backend']} | "
                     f"LLM={result['llm_status']}/{result['llm_backend']} | TTS={result['tts_status']}/{result['tts_backend']}")
            raw = result["audio_stats"].get("raw", {})
            normalized = result["audio_stats"].get("normalized", {})
            peak = raw.get("peak", 0)
            gain = normalized.get("peak", 0) / peak if peak else 0
            log_line(f"{prefix} 输入音频：RMS={raw.get('rms', 0):.1f} | 峰值={peak} | 归一化倍率≈{gain:.1f}倍 | "
                     f"录音={fields['recording']}")
            for stage, label in (("asr", "识别"), ("llm", "回复"), ("tts", "合成")):
                if result[stage + "_status"] != "ok" or "fallback" in result[stage + "_backend"]:
                    log_line(f"{prefix} 注意：{label}非正常后端结果，详情={quoted(result.get(stage + '_detail', ''))}")
        # Successful start/end events still delimit measurements, but are not
        # printed individually. timings_ms is the single source for summaries.


def measure_stage(name, operation, trace: RequestTrace | None = None):
    started = time.perf_counter()
    try:
        result = operation()
    except Exception:
        ended = time.perf_counter()
        if trace:
            trace.event(name + "_start", started)
            trace.event(name + "_end", ended, status="failed", duration_ms=int((ended - started) * 1000))
        raise
    ended = time.perf_counter()
    duration_ms = int((ended - started) * 1000)
    if trace:
        trace.event(name + "_start", started)
        trace.event(name + "_end", ended, status="ok", duration_ms=duration_ms)
    return result, duration_ms
