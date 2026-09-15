from pathlib import Path
import os


SERVER_ROOT = Path(__file__).resolve().parent
RECORDINGS_DIR = SERVER_ROOT / "recordings"

# 国内网络下 Hugging Face 默认域名和 Xet 下载通道可能不稳定。
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

# ASR_BACKEND:
# - "placeholder": do not transcribe, but keep the pipeline running.
# - "faster_whisper": use faster-whisper if installed.
ASR_BACKEND = "faster_whisper"
ASR_MODEL_NAME = os.getenv("PRP_ASR_MODEL_NAME", "small")
ASR_DEVICE = "cpu"
ASR_COMPUTE_TYPE = "int8"
ASR_VAD_FILTER = False
ASR_BEAM_SIZE = int(os.getenv("PRP_ASR_BEAM_SIZE", "5"))
ASR_BEST_OF = int(os.getenv("PRP_ASR_BEST_OF", "5"))
# Keep prompt/hotwords empty until a labelled test set proves they help.
# Strong hints can be hallucinated into short or unclear recordings.
ASR_INITIAL_PROMPT = os.getenv("PRP_ASR_INITIAL_PROMPT", "")
ASR_HOTWORDS = os.getenv("PRP_ASR_HOTWORDS", "")
ASR_CONDITION_ON_PREVIOUS_TEXT = False
AUDIO_NORMALIZE_TARGET_PEAK = 0.75

# LLM_BACKEND:
# - "rule": local rule-based healing reply.
# - "ollama": call a local Ollama server if available.
LLM_BACKEND = os.getenv("PRP_LLM_BACKEND", "ollama")
OLLAMA_URL = os.getenv("PRP_OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
OLLAMA_MODEL = os.getenv("PRP_OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("PRP_OLLAMA_TIMEOUT_SECONDS", "90"))
OLLAMA_KEEP_ALIVE = os.getenv("PRP_OLLAMA_KEEP_ALIVE", "10m")
MODEL_WARMUP_ENABLED = os.getenv("PRP_MODEL_WARMUP_ENABLED", "true").lower() in {
    "1", "true", "yes", "on"
}

# Persona prompts are kept outside the dialogue logic so the character can be
# changed without editing Python code. Relative paths are resolved from server/.
PERSONA_PROMPT_NAME = os.getenv("PRP_PERSONA_PROMPT_NAME", "nuonuo_v1")
_persona_prompt_value = os.getenv(
    "PRP_PERSONA_PROMPT_FILE",
    str(SERVER_ROOT / "prompts" / f"{PERSONA_PROMPT_NAME}.txt"),
)
PERSONA_PROMPT_FILE = Path(_persona_prompt_value)
if not PERSONA_PROMPT_FILE.is_absolute():
    PERSONA_PROMPT_FILE = SERVER_ROOT / PERSONA_PROMPT_FILE

# REPLY_STYLE:
# - "auto": choose between cute and encourage from the user's text.
# - "cute": soft, playful, plush-toy-like companionship.
# - "encourage": firmer emotional support and gentle action guidance.
REPLY_STYLE = os.getenv("PRP_REPLY_STYLE", "auto")

# TTS_BACKEND:
# - "windows_sapi": built-in Windows voice, useful as a fallback.
# - "gpt_sovits": call a locally running GPT-SoVITS API.
TTS_BACKEND = os.getenv("PRP_TTS_BACKEND", "windows_sapi")
TTS_FALLBACK_TO_SAPI = os.getenv("PRP_TTS_FALLBACK_TO_SAPI", "true").lower() in {
    "1", "true", "yes", "on"
}
GPT_SOVITS_URL = os.getenv("PRP_GPT_SOVITS_URL", "http://127.0.0.1:9880/tts")
GPT_SOVITS_TIMEOUT_SECONDS = float(os.getenv("PRP_GPT_SOVITS_TIMEOUT_SECONDS", "60"))
GPT_SOVITS_REFERENCE_WAV = os.getenv("PRP_GPT_SOVITS_REFERENCE_WAV", "")
GPT_SOVITS_PROMPT_TEXT = os.getenv("PRP_GPT_SOVITS_PROMPT_TEXT", "")
GPT_SOVITS_PROMPT_LANGUAGE = os.getenv("PRP_GPT_SOVITS_PROMPT_LANGUAGE", "zh")
GPT_SOVITS_TEXT_LANGUAGE = os.getenv("PRP_GPT_SOVITS_TEXT_LANGUAGE", "zh")
