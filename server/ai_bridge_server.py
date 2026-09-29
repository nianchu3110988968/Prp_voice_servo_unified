from datetime import datetime
from pathlib import Path
import sys
import time
import wave
import re
import threading
import asyncio
import os
from services import role_runtime
from services.role_config import load_role, list_roles

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from services.asr_service import transcribe_audio, warm_up_asr
from services.audio_utils import normalize_pcm_s16le, pcm_s16le_stats
from services.dialogue_service import generate_healing_reply, warm_up_dialogue_model
from services.dialogue_service import choose_reply_style, enforce_emotion_motion_consistency, remember_turn
from services.tts_service import synthesize_reply
from services.latency_trace import RequestTrace, measure_stage, log_line, quoted
from server_config import AUDIO_NORMALIZE_TARGET_PEAK
import server_config as config
from services.phrase_library import PhraseLibrary, semantic_match
from services.phrase_jobs import PhraseJobs


def configure_stdio_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


configure_stdio_encoding()

APP_ROOT = Path(__file__).resolve().parent
RECORDINGS_DIR = APP_ROOT / "recordings"
RECORDINGS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="PRP Plush Robot AI Bridge")
@app.middleware("http")
async def desktop_request_trace(request: Request, call_next):
    # Correlate controlled desktop HTTP operations without changing ESP32's flow.
    if request.url.path.startswith(("/debug/dialogue", "/debug/tts", "/debug/text-chain", "/profiles/")):
        trace = RequestTrace(request.headers.get("x-request-id"))
        log_line(f"[服务端][{trace.request_id}] 桌面请求开始: {request.url.path}")
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = trace.request_id
            log_line(f"[服务端][{trace.request_id}] 桌面请求结束: HTTP {response.status_code}, {round((time.perf_counter() - trace.started) * 1000)}ms")
            return response
        except Exception:
            log_line(f"[服务端][{trace.request_id}] 桌面请求失败")
            raise
    return await call_next(request)


phrase_library = PhraseLibrary(config.PHRASE_WORKBOOK, config.PHRASE_CACHE_DIR)
phrase_jobs = PhraseJobs()
# Preserve the existing single ordered ASR/dialogue/history lane. Long TTS jobs
# leave this lane after a cache hit, while file GETs remain responsive.
interaction_lock = threading.Lock()
warmup_status = {"asr": "pending", "llm": "pending"}


@app.on_event("shutdown")
def close_phrase_jobs():
    phrase_jobs.close()


@app.on_event("startup")
def warm_up_models() -> None:
    from server_config import MODEL_WARMUP_ENABLED

    role_id = os.getenv("PRP_ROLE_ID", "New_ManBoo")
    # Configuration errors fail fast. A model-service failure may use the existing
    # SAPI fallback, but must never silently use unconfirmed remote weights.
    # Split selections override optional legacy preset at process startup.
    from services.profile_config import load_combination
    initial = (load_combination(os.environ["PRP_PERSONA_ID"], os.environ["PRP_VOICE_ID"])
               if os.getenv("PRP_PERSONA_ID") and os.getenv("PRP_VOICE_ID") else load_role(role_id))
    role_runtime.activate(initial)
    try:
        role_runtime.switch_role(role_id, loader=lambda _: initial)
    except Exception as exc:
        log_line("[服务端] 音色未就绪：" + str(exc))
    if not MODEL_WARMUP_ENABLED:
        warmup_status.update(asr="skipped", llm="skipped")
        log_line("[服务端] 模型预热已关闭")
        return
    started = time.perf_counter()
    asr_result = warm_up_asr()
    llm_result = warm_up_dialogue_model()
    warmup_status.update(asr=asr_result["status"], llm=llm_result["status"])
    elapsed = time.perf_counter() - started
    log_line(f"[服务端] 模型预热：ASR={asr_result['status']} | LLM={llm_result['status']} | 耗时={elapsed:.1f}s")
    for label, result in (("ASR", asr_result), ("LLM", llm_result)):
        if result["status"] != "ok":
            log_line(f"[服务端] {label}预热提示：{quoted(result.get('detail', ''))}")


def pcm_to_wav(pcm_bytes: bytes, wav_path: Path, sample_rate: int) -> None:
    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)


def run_ai_pipeline(wav_path: Path, audio_stats: dict | None = None, trace: RequestTrace | None = None,
                    allow_phrases: bool = False, prepared_timings: dict | None = None) -> dict:
    pipeline_start = time.perf_counter()

    asr_result, asr_ms = measure_stage("asr", lambda: transcribe_audio(wav_path), trace)

    recognized_text = asr_result["text"]
    cache = {}

    def select_dialogue():
        if allow_phrases and config.PHRASE_LIBRARY_ENABLED and asr_result["status"] == "ok":
            try:
                entries, manifest = phrase_library.ready()
                entry = semantic_match(recognized_text, entries)
                if entry:
                    audio_url = phrase_library.audio_for(entry, manifest)
                    style = choose_reply_style(recognized_text)
                    emotion, motion = enforce_emotion_motion_consistency(recognized_text, entry.reply, "", "")
                    cache.update(id=entry.id, audio_url=audio_url)
                    # Do not pass fixed replies through the ordinary 48-char truncation.
                    return {"reply_text": entry.reply, "style": style, "emotion": emotion, "motion": motion,
                            "persona": config.PERSONA_PROMPT_NAME, "status": "ok", "backend": "ollama"}
            except Exception as exc:
                log_line(f"[服务端][{trace.request_id if trace else '-'}] 词库不可用，回正常回复：{quoted(str(exc))}")
        return generate_healing_reply(recognized_text)

    dialogue, dialogue_ms = measure_stage("dialogue", select_dialogue, trace)

    if cache and trace:
        # Immutable snapshots per request; no worker reads mutable global history.
        synthesizer = synthesize_reply
        request_role = role_runtime.current

        def synthesize_snapshot(text, directory):
            with role_runtime.lock:
                if role_runtime.current is not request_role:
                    return {"audio_url": "", "status": "cancelled_role_changed", "backend": "none", "detail": "角色已切换"}
                return synthesizer(text, directory)
        output_dir = RECORDINGS_DIR
        ready_to_run = threading.Event()
        early_ms = -1

        def complete_background():
            # Publish the first response and its real timestamp before the worker
            # reads it. Also ensures the one hit/text log precedes background logs.
            if not ready_to_run.wait(5):
                raise RuntimeError("first response preparation failed")
            tts, tts_ms = measure_stage("tts", lambda: synthesize_snapshot(dialogue["reply_text"], output_dir), trace)
            result = pipeline_response(wav_path, audio_stats, asr_result, dialogue, tts,
                                       asr_ms, dialogue_ms, tts_ms, pipeline_start)
            result["timings_ms"].update(prepared_timings or {})
            result["timings_ms"]["total_request"] = early_ms
            result["timings_ms"]["background_total"] = int((time.perf_counter() - trace.started) * 1000)
            result.update(phrase_hit=True, phrase_id=cache["id"])
            trace.event("background_ready", timings_ms=result["timings_ms"], response=result, recording=wav_path.name)
            return result

        job_id = phrase_jobs.submit(trace.request_id, complete_background)
        if job_id:
            remember_turn(recognized_text, dialogue["reply_text"], dialogue["style"])
            result = pipeline_response(wav_path, audio_stats, asr_result, dialogue,
                                       {"audio_url": cache["audio_url"], "status": "pending", "backend": config.TTS_BACKEND},
                                       asr_ms, dialogue_ms, -1, pipeline_start)
            result["timings_ms"].update(prepared_timings or {})
            result["timings_ms"]["total_pipeline"] = -1
            result["timings_s"].update(tts=-1, total=-1)
            result.update(phrase_hit=True, phrase_id=cache["id"], job_url=f"/voice/jobs/{job_id}")
            early_ms = int((time.perf_counter() - trace.started) * 1000)
            result["timings_ms"]["total_request"] = early_ms
            trace.event("phrase_ready", response=result)
            ready_to_run.set()
            return result
        log_line(f"[服务端][{trace.request_id}] 词库后台队列已满，回正常回复")
        fallback_start = time.perf_counter()
        dialogue = generate_healing_reply(recognized_text)
        dialogue_ms += int((time.perf_counter() - fallback_start) * 1000)

    tts_result, tts_ms = measure_stage("tts", lambda: synthesize_reply(dialogue["reply_text"], RECORDINGS_DIR), trace)
    return pipeline_response(wav_path, audio_stats, asr_result, dialogue, tts_result,
                             asr_ms, dialogue_ms, tts_ms, pipeline_start)


def pipeline_response(wav_path, audio_stats, asr_result, dialogue, tts_result,
                      asr_ms, dialogue_ms, tts_ms, pipeline_start):
    total_ms = int((time.perf_counter() - pipeline_start) * 1000)
    timings_s = {
        "understand": round(asr_ms / 1000, 1),
        "reply": round(dialogue_ms / 1000, 1),
        "tts": round(tts_ms / 1000, 1),
        "total": round(total_ms / 1000, 1),
    }

    return {
        "recognized_text": asr_result["text"],
        "asr_status": asr_result["status"],
        "asr_backend": asr_result["backend"],
        "asr_model": asr_result.get("model", ""),
        "asr_simplified_chinese": asr_result.get("simplified_chinese", False),
        "asr_detail": asr_result.get("detail", ""),
        "reply_text": dialogue["reply_text"],
        "reply_persona": dialogue.get("persona", ""),
        "reply_style": dialogue.get("style", ""),
        "reply_emotion": dialogue.get("emotion", ""),
        "motion": dialogue["motion"],
        "llm_status": dialogue["status"],
        "llm_backend": dialogue["backend"],
        "llm_detail": dialogue.get("detail", ""),
        "audio_url": tts_result["audio_url"],
        "tts_status": tts_result["status"],
        "tts_backend": tts_result["backend"],
        "tts_detail": tts_result.get("detail", ""),
        "timings_ms": {
            "asr": asr_ms,
            "dialogue": dialogue_ms,
            "tts": tts_ms,
            "total_pipeline": total_ms,
        },
        "timings_s": timings_s,
        "debug_recording": wav_path.name,
        "audio_stats": audio_stats or {},
    }


def ordered_pipeline(*args, **kwargs):
    with role_runtime.lock, interaction_lock:
        return run_ai_pipeline(*args, **kwargs)


@app.get("/voice/jobs/{job_id}")
async def get_voice_job(job_id: str, request: Request, http_response: Response):
    deadline = time.monotonic() + 20
    while True:
        result = phrase_jobs.get(job_id) if re.fullmatch(r"[0-9a-f]{32}", job_id) else None
        if result is None or request.headers.get("x-request-id") != result["request_id"]:
            raise HTTPException(status_code=404, detail="job not found or expired")
        if result["job_status"] != "pending" or time.monotonic() >= deadline:
            break
        # Long-poll asynchronously: no busy access-log spam, no occupied TTS lane.
        await asyncio.sleep(0.1)
    http_response.headers["X-Request-ID"] = result["request_id"]
    # Background polling does not retransmit recognized text/audio stats every time.
    keys = {"job_status", "request_id", "error", "audio_url", "tts_status", "tts_backend", "timings_ms"}
    return {key: value for key, value in result.items() if key in keys}


@app.get("/phrase-audio/{file_name}")
def get_phrase_audio(file_name: str):
    if role_runtime.current:
        raise HTTPException(status_code=404, detail="role cache requires namespace")
    if not re.fullmatch(r"[0-9a-f]{64}\.wav", file_name):
        raise HTTPException(status_code=404, detail="audio not found")
    path = phrase_library.cache_dir / file_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="audio not found")
    return FileResponse(path, media_type="audio/wav")


@app.post("/phrase-library/rebuild")
def rebuild_phrase_library(request: Request):
    # This local maintenance operation is not an anonymous LAN/browser action.
    if not request.client or request.client.host not in {"127.0.0.1", "::1"} or request.headers.get("origin"):
        raise HTTPException(status_code=403, detail="local CLI only")
    if request.headers.get("x-prp-maintenance") != "phrase-library":
        raise HTTPException(status_code=403, detail="maintenance header required")
    try:
        with role_runtime.lock:
            return phrase_library.rebuild(synthesize_reply)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/health")
def health():
    return {"status": "ok", "service": "prp-ai-bridge", "role_api": 2,
            "warmup": dict(warmup_status), **role_runtime.status()}




@app.get("/roles")
def get_roles(request: Request):
    require_role_maintenance(request)
    return {"available": list_roles(), **role_runtime.status()}


def require_role_maintenance(request):
    if (not request.client or request.client.host not in {"127.0.0.1", "::1"}
            or request.headers.get("origin") or request.headers.get("x-prp-maintenance") != "roles"):
        raise HTTPException(status_code=403, detail="local role maintenance only")


@app.post("/roles/switch/{role_id}")
def switch_role(role_id: str, request: Request):
    require_role_maintenance(request)
    try:
        return role_runtime.switch_role(role_id)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/phrase-audio/{role_token}/{file_name}")
def get_role_phrase_audio(role_token: str, file_name: str):
    # Do not wait behind background synthesis: this GET is the cache-first path.
    role = role_runtime.current
    if not role or not role_runtime.voice_ready or role.url_token != role_token:
        raise HTTPException(status_code=404, detail="inactive role cache")
    if not re.fullmatch(r"[0-9a-f]{64}\.wav", file_name):
        raise HTTPException(status_code=404, detail="audio not found")
    path = config.PHRASE_CACHE_DIR / role.cache_key / file_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="audio not found")
    return FileResponse(path, media_type="audio/wav")


@app.get("/config")
def get_config():
    from server_config import (
        ASR_BACKEND,
        ASR_BEAM_SIZE,
        ASR_BEST_OF,
        ASR_HOTWORDS,
        ASR_INITIAL_PROMPT,
        ASR_MODEL_NAME,
        LLM_BACKEND,
        MODEL_WARMUP_ENABLED,
        OLLAMA_KEEP_ALIVE,
        OLLAMA_MODEL,
        OLLAMA_TIMEOUT_SECONDS,
        PERSONA_PROMPT_FILE,
        PERSONA_PROMPT_NAME,
        REPLY_STYLE,
        GPT_SOVITS_PROMPT_LANGUAGE,
        GPT_SOVITS_REFERENCE_WAV,
        GPT_SOVITS_TEXT_LANGUAGE,
        GPT_SOVITS_TIMEOUT_SECONDS,
        GPT_SOVITS_URL,
        TTS_BACKEND,
        TTS_FALLBACK_TO_SAPI,
    )

    return {
        **role_runtime.status(),
        "asr_backend": ASR_BACKEND,
        "asr_model_name": ASR_MODEL_NAME,
        "asr_beam_size": ASR_BEAM_SIZE,
        "asr_best_of": ASR_BEST_OF,
        "asr_initial_prompt": ASR_INITIAL_PROMPT,
        "asr_hotwords": ASR_HOTWORDS,
        "llm_backend": LLM_BACKEND,
        "model_warmup_enabled": MODEL_WARMUP_ENABLED,
        "ollama_model": OLLAMA_MODEL,
        "ollama_timeout_seconds": OLLAMA_TIMEOUT_SECONDS,
        "ollama_keep_alive": OLLAMA_KEEP_ALIVE,
        "persona_prompt_name": PERSONA_PROMPT_NAME,
        "persona_prompt_file": str(PERSONA_PROMPT_FILE),
        "persona_prompt_file_exists": PERSONA_PROMPT_FILE.is_file(),
        "reply_style": REPLY_STYLE,
        "tts_backend": TTS_BACKEND,
        "tts_fallback_to_sapi": TTS_FALLBACK_TO_SAPI,
        "gpt_sovits_url": GPT_SOVITS_URL,
        "gpt_sovits_timeout_seconds": GPT_SOVITS_TIMEOUT_SECONDS,
        "gpt_sovits_reference_wav_configured": bool(GPT_SOVITS_REFERENCE_WAV),
        "gpt_sovits_prompt_language": GPT_SOVITS_PROMPT_LANGUAGE,
        "gpt_sovits_text_language": GPT_SOVITS_TEXT_LANGUAGE,
        "phrase_library_enabled": config.PHRASE_LIBRARY_ENABLED,
        "phrase_workbook": str(config.PHRASE_WORKBOOK),
        "phrase_cache_published": (phrase_library.cache_dir / "manifest.json").is_file(),
        "phrase_voice_revision": config.PHRASE_VOICE_REVISION,
    }


@app.get("/debug/dialogue")
def debug_dialogue(text: str):
    with role_runtime.lock, interaction_lock:
        return generate_healing_reply(text)


@app.get("/debug/tts")
def debug_tts(text: str):
    """Synthesize text without requiring an ESP32 request."""
    return synthesize_reply(text, RECORDINGS_DIR)


@app.get("/recordings")
def list_recordings():
    files = sorted(RECORDINGS_DIR.glob("*"), key=lambda item: item.stat().st_mtime, reverse=True)
    return {
        "recordings": [
            {
                "name": file.name,
                "size": file.stat().st_size,
                "url": f"/recordings/{file.name}",
            }
            for file in files
            if file.is_file()
        ]
    }


@app.get("/recordings/{file_name}")
def get_recording(file_name: str):
    file_path = RECORDINGS_DIR / file_name
    if not file_path.is_file() or file_path.parent != RECORDINGS_DIR:
        raise HTTPException(status_code=404, detail="recording not found")

    media_type = "audio/wav" if file_path.suffix.lower() == ".wav" else "application/octet-stream"
    return FileResponse(file_path, media_type=media_type, filename=file_path.name)


@app.get("/debug/pipeline/{file_name}")
def debug_pipeline(file_name: str):
    file_path = RECORDINGS_DIR / file_name
    if not file_path.is_file() or file_path.parent != RECORDINGS_DIR:
        raise HTTPException(status_code=404, detail="recording not found")
    if file_path.suffix.lower() != ".wav":
        raise HTTPException(status_code=400, detail="debug pipeline requires a wav file")

    return ordered_pipeline(file_path)


@app.post("/voice/interact")
async def voice_interact(request: Request, http_response: Response):
    trace = RequestTrace(request.headers.get("x-request-id"))
    http_response.headers["X-Request-ID"] = trace.request_id
    try:
        receive_start = time.perf_counter()
        body = await request.body()
        receive_end = time.perf_counter()
        trace.event("body_receive_start", receive_start)
        trace.event("body_receive_end", receive_end, bytes=len(body))
        prepare_start = time.perf_counter()
        sample_rate = int(request.headers.get("x-sample-rate", "16000"))
        audio_format = request.headers.get("x-audio-format", "pcm_s16le_mono")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        pcm_path = RECORDINGS_DIR / f"recording_{timestamp}_{sample_rate}hz.pcm"
        wav_path = RECORDINGS_DIR / f"recording_{timestamp}_{sample_rate}hz.wav"

        raw_stats = pcm_s16le_stats(body)
        normalized_body = normalize_pcm_s16le(body, AUDIO_NORMALIZE_TARGET_PEAK)
        normalized_stats = pcm_s16le_stats(normalized_body)

        pcm_path.write_bytes(body)
        pcm_to_wav(normalized_body, wav_path, sample_rate)
        prepare_end = time.perf_counter()
        trace.event("prepare_audio_start", prepare_start)
        trace.event("prepare_audio_end", prepare_end, recording=wav_path.name)

        prepared_timings = {
            "body_receive": int((receive_end - receive_start) * 1000),
            "prepare_audio": int((prepare_end - prepare_start) * 1000),
        }
        response = await run_in_threadpool(ordered_pipeline, wav_path, audio_stats={
            "raw": raw_stats, "normalized": normalized_stats,
            "normalize_target_peak": AUDIO_NORMALIZE_TARGET_PEAK,
        }, trace=trace, prepared_timings=prepared_timings,
            allow_phrases=request.headers.get("x-voice-capabilities") == "phrase-cache-v1")
        if response.get("phrase_hit"):
            return response
        response["timings_ms"].update(prepared_timings)
        ready = time.perf_counter()
        # Handler entry -> response dict ready. NOT HTTP serialization/send time.
        response["timings_ms"]["total_request"] = int((ready - trace.started) * 1000)
        trace.event("response_ready", ready, status="ok", timings_ms=response["timings_ms"],
                    recording=wav_path.name, audio_url=response["audio_url"], response=response)
        return response
    except Exception as exc:
        trace.event("request_failed", status="failed", error_type=type(exc).__name__)
        raise


@app.post("/profiles/persona/{persona_id}")
def switch_persona_profile(persona_id: str, request: Request):
    require_role_maintenance(request)
    try:
        return role_runtime.switch_persona(persona_id)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/profiles/voice/{voice_id}")
def switch_voice_profile(voice_id: str, request: Request):
    require_role_maintenance(request)
    try:
        return role_runtime.switch_voice(voice_id)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/profiles/apply/{persona_id}/{voice_id}")
def apply_profiles(persona_id: str, voice_id: str, request: Request):
    require_role_maintenance(request)
    try:
        return role_runtime.apply_combination(persona_id, voice_id)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/debug/text-chain")
def debug_text_chain(text: str, request: Request):
    require_role_maintenance(request)
    with role_runtime.lock, interaction_lock:
        started = time.perf_counter()
        dialogue = generate_healing_reply(text)
        dialogue_ms = round((time.perf_counter() - started) * 1000)
        tts = synthesize_reply(dialogue["reply_text"], RECORDINGS_DIR)
        return {"dialogue": dialogue, "tts": tts, "dialogue_ms": dialogue_ms,
                "total_ms": round((time.perf_counter() - started) * 1000), **role_runtime.status()}
