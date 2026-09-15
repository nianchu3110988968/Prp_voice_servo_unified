from datetime import datetime
from pathlib import Path
import sys
import time
import wave

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse

from services.asr_service import transcribe_audio, warm_up_asr
from services.audio_utils import normalize_pcm_s16le, pcm_s16le_stats
from services.dialogue_service import generate_healing_reply, warm_up_dialogue_model
from services.tts_service import synthesize_reply
from services.latency_trace import RequestTrace, measure_stage
from server_config import AUDIO_NORMALIZE_TARGET_PEAK


def configure_stdio_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


configure_stdio_encoding()

APP_ROOT = Path(__file__).resolve().parent
RECORDINGS_DIR = APP_ROOT / "recordings"
RECORDINGS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="PRP Plush Robot AI Bridge")


@app.on_event("startup")
def warm_up_models() -> None:
    from server_config import MODEL_WARMUP_ENABLED

    if not MODEL_WARMUP_ENABLED:
        print("[ai_bridge] model warm-up disabled", flush=True)
        return
    started = time.perf_counter()
    asr_result = warm_up_asr()
    llm_result = warm_up_dialogue_model()
    elapsed = time.perf_counter() - started
    print(
        f"[ai_bridge] model warm-up: asr={asr_result}, llm={llm_result}, elapsed={elapsed:.1f}s",
        flush=True,
    )


def pcm_to_wav(pcm_bytes: bytes, wav_path: Path, sample_rate: int) -> None:
    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)


def run_ai_pipeline(wav_path: Path, audio_stats: dict | None = None, trace: RequestTrace | None = None) -> dict:
    pipeline_start = time.perf_counter()

    asr_result, asr_ms = measure_stage("asr", lambda: transcribe_audio(wav_path), trace)

    recognized_text = asr_result["text"]
    dialogue, dialogue_ms = measure_stage("dialogue", lambda: generate_healing_reply(recognized_text), trace)

    tts_result, tts_ms = measure_stage("tts", lambda: synthesize_reply(dialogue["reply_text"], RECORDINGS_DIR), trace)
    total_ms = int((time.perf_counter() - pipeline_start) * 1000)
    timings_s = {
        "understand": round(asr_ms / 1000, 1),
        "reply": round(dialogue_ms / 1000, 1),
        "tts": round(tts_ms / 1000, 1),
        "total": round(total_ms / 1000, 1),
    }

    return {
        "recognized_text": recognized_text,
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


@app.get("/health")
def health():
    return {"status": "ok"}


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
    }


@app.get("/debug/dialogue")
def debug_dialogue(text: str):
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

    return run_ai_pipeline(file_path)


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

        print(
            f"[ai_bridge] received {len(body)} bytes, request_id={trace.request_id}, "
            f"format={audio_format}, sample_rate={sample_rate}, "
            f"pcm={pcm_path.name}, wav={wav_path.name}", flush=True,
        )
        response = run_ai_pipeline(wav_path, audio_stats={
            "raw": raw_stats, "normalized": normalized_stats,
            "normalize_target_peak": AUDIO_NORMALIZE_TARGET_PEAK,
        }, trace=trace)
        response["timings_ms"].update({
            "body_receive": int((receive_end - receive_start) * 1000),
            "prepare_audio": int((prepare_end - prepare_start) * 1000),
        })
        print(
            f"[ai_bridge] request_id={trace.request_id}, recognized='{response['recognized_text']}', "
            f"asr={response['asr_status']}/{response['asr_backend']}/{response['asr_model']}, "
            f"reply='{response['reply_text']}', "
            f"persona={response['reply_persona']}, style={response['reply_style']}, "
            f"emotion={response['reply_emotion']}, "
            f"llm={response['llm_status']}/{response['llm_backend']}, "
            f"tts={response['tts_status']}/{response['tts_backend']}, "
            f"audio_url={response['audio_url']}, timings_ms={response['timings_ms']}, "
            f"motion={response['motion']}", flush=True,
        )
        timings = response["timings_s"]
        print(
            "[ai_bridge] timings: "
            f"understand={timings['understand']:.1f}s, reply={timings['reply']:.1f}s, "
            f"tts={timings['tts']:.1f}s, total={timings['total']:.1f}s", flush=True,
        )
        ready = time.perf_counter()
        # Handler entry -> response dict ready. NOT HTTP serialization/send time.
        response["timings_ms"]["total_request"] = int((ready - trace.started) * 1000)
        trace.event("response_ready", ready, status="ok", timings_ms=response["timings_ms"],
                    recording=wav_path.name, audio_url=response["audio_url"])
        return response
    except Exception as exc:
        trace.event("request_failed", status="failed", error_type=type(exc).__name__)
        raise
