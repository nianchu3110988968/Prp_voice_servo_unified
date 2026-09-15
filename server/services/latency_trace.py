"""Request-scoped diagnostic timings; never compare this clock to ESP uptime."""
from datetime import datetime, timezone
import json
import re
import time
from uuid import uuid4


class RequestTrace:
    def __init__(self, supplied_id: str | None = None):
        self.request_id = supplied_id if supplied_id and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", supplied_id) else uuid4().hex
        self.started = time.perf_counter()
        self.event("request_start", self.started)

    def event(self, event: str, at: float | None = None, **fields):
        at = time.perf_counter() if at is None else at
        record = {"request_id": self.request_id, "event": event,
                  "mono_us": int(at * 1_000_000), "since_request_ms": round((at - self.started) * 1000, 3),
                  "logged_utc": datetime.now(timezone.utc).isoformat(), **fields}
        # Telemetry failure must not turn a successful request into an error.
        try:
            print("[voice_trace] " + json.dumps(record, ensure_ascii=False), flush=True)
        except (OSError, ValueError):
            pass


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
