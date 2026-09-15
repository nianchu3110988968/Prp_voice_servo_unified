from pathlib import Path

from server_config import (
    ASR_BACKEND,
    ASR_BEAM_SIZE,
    ASR_BEST_OF,
    ASR_COMPUTE_TYPE,
    ASR_CONDITION_ON_PREVIOUS_TEXT,
    ASR_DEVICE,
    ASR_HOTWORDS,
    ASR_INITIAL_PROMPT,
    ASR_MODEL_NAME,
    ASR_VAD_FILTER,
)


_whisper_model = None
_whisper_load_error = None

try:
    from opencc import OpenCC

    _traditional_to_simplified = OpenCC("t2s")
except ImportError:
    _traditional_to_simplified = None


def _load_faster_whisper_model():
    global _whisper_load_error, _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    if _whisper_load_error is not None:
        return None

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        _whisper_load_error = "未安装 faster-whisper，请安装 server/requirements-asr.txt。"
        return None

    try:
        _whisper_model = WhisperModel(
            ASR_MODEL_NAME,
            device=ASR_DEVICE,
            compute_type=ASR_COMPUTE_TYPE,
        )
    except Exception as exc:
        _whisper_load_error = str(exc)
        return None

    return _whisper_model


def warm_up_asr() -> dict:
    if ASR_BACKEND != "faster_whisper":
        return {"status": "skipped", "backend": ASR_BACKEND, "model": ASR_MODEL_NAME}
    model = _load_faster_whisper_model()
    return {
        "status": "ok" if model is not None else "failed",
        "backend": ASR_BACKEND,
        "model": ASR_MODEL_NAME,
        "detail": _whisper_load_error or "",
    }


def transcribe_audio(wav_path: Path) -> dict:
    """把 WAV 转成文字。当前支持占位模式和可选 faster-whisper。"""
    if ASR_BACKEND == "placeholder":
        return {
            "text": "",
            "status": "disabled",
            "backend": ASR_BACKEND,
            "detail": "ASR 尚未启用，当前只验证服务器链路。",
        }

    if ASR_BACKEND == "faster_whisper":
        model = _load_faster_whisper_model()
        if model is None:
            return {
                "text": "",
                "status": "model_load_failed" if _whisper_load_error else "missing_dependency",
                "backend": ASR_BACKEND,
                "detail": _whisper_load_error or "未安装 faster-whisper，请安装 server/requirements-asr.txt。",
            }

        try:
            segments, info = model.transcribe(
                str(wav_path),
                language="zh",
                vad_filter=ASR_VAD_FILTER,
                beam_size=ASR_BEAM_SIZE,
                best_of=ASR_BEST_OF,
                condition_on_previous_text=ASR_CONDITION_ON_PREVIOUS_TEXT,
                initial_prompt=ASR_INITIAL_PROMPT or None,
                hotwords=ASR_HOTWORDS or None,
            )
            text = "".join(segment.text.strip() for segment in segments).strip()
            if _traditional_to_simplified is not None:
                text = _traditional_to_simplified.convert(text)
            return {
                "text": text,
                "status": "ok",
                "backend": ASR_BACKEND,
                "model": ASR_MODEL_NAME,
                "language": info.language,
                "language_probability": info.language_probability,
                "simplified_chinese": _traditional_to_simplified is not None,
            }
        except Exception as exc:
            return {
                "text": "",
                "status": "transcribe_failed",
                "backend": ASR_BACKEND,
                "detail": str(exc),
            }

    return {
        "text": "",
        "status": "unsupported_backend",
        "backend": ASR_BACKEND,
        "detail": f"未知 ASR_BACKEND: {ASR_BACKEND}",
    }
