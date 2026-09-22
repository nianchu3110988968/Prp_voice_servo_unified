"""Bounded background jobs. No fabricated timing, unbounded queue or LLM rerun."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time
from uuid import uuid4


class PhraseJobs:
    def __init__(self, capacity=4, retention=300, timeout=180):
        self.capacity, self.retention, self.timeout = capacity, retention, timeout
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="phrase-tts")
        self._lock = threading.Lock()
        self._jobs = {}

    def _cleanup(self):
        now = time.monotonic()
        for key, job in list(self._jobs.items()):
            if job["finished"] is not None and now - job["finished"] > self.retention:
                del self._jobs[key]

    def submit(self, request_id, operation):
        with self._lock:
            self._cleanup()
            if len(self._jobs) >= 32 or sum(j["finished"] is None for j in self._jobs.values()) >= self.capacity:
                return None
            key = uuid4().hex
            self._jobs[key] = {"request_id": request_id, "created": time.monotonic(),
                               "finished": None, "result": None, "error": ""}
            try:
                self._pool.submit(self._run, key, operation)
            except Exception:
                del self._jobs[key]
                raise
            return key

    def _run(self, key, operation):
        try:
            # The result is written once, never read while partially populated.
            result, error = operation(), ""
        except Exception as exc:
            result, error = None, type(exc).__name__
        with self._lock:
            job = self._jobs[key]
            job.update(result=result, error=error, finished=time.monotonic())

    def get(self, key):
        with self._lock:
            self._cleanup()
            job = self._jobs.get(key)
            if job is None:
                return None
            common = {"request_id": job["request_id"]}
            if job["finished"] is None:
                # Expired running work still holds its slot until it really ends.
                # Python cannot safely kill an in-flight TTS thread.
                if time.monotonic() - job["created"] > self.timeout:
                    return {**common, "job_status": "failed", "error": "timeout"}
                return {**common, "job_status": "pending"}
            if job["error"]:
                return {**common, "job_status": "failed", "error": job["error"]}
            return {**common, "job_status": "ready", **job["result"]}

    def close(self):
        self._pool.shutdown(wait=True)
