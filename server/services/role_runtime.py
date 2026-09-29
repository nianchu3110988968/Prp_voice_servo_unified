"""One transaction boundary for dialogue, TTS and role activation."""
import threading
from pathlib import Path
import requests
from services.role_config import load_role

lock = threading.RLock()
current = None
voice_ready = False
last_tts = {"backend": "not_tested", "status": "not_tested"}


def _load_pair(role, restore=False):
    import server_config as config
    base = config.GPT_SOVITS_URL.rsplit("/", 1)[0]
    errors = []
    for endpoint, path in (("set_gpt_weights", role.gpt_weights), ("set_sovits_weights", role.sovits_weights)):
        try:
            response = requests.get(base + "/" + endpoint, params={"weights_path": path}, timeout=180)
            response.raise_for_status()
            if response.json().get("message") != "success":
                raise RuntimeError(endpoint + "未确认success")
        except Exception as exc:
            if not restore:
                raise
            errors.append(str(exc))
    if errors:
        raise RuntimeError("; ".join(errors))


def activate(role):
    global current, last_tts
    from services import dialogue_service
    import server_config as config
    dialogue_service.set_persona(role)
    config.PERSONA_PROMPT_NAME = role.id
    config.PERSONA_PROMPT_FILE = Path(role.persona_prompt_file)
    config.TTS_BACKEND = "gpt_sovits"
    config.GPT_SOVITS_REFERENCE_WAV = role.reference_wav
    config.GPT_SOVITS_PROMPT_TEXT = role.reference_text
    config.GPT_SOVITS_PROMPT_LANGUAGE = role.prompt_language
    config.GPT_SOVITS_TEXT_LANGUAGE = role.text_language
    config.PHRASE_VOICE_REVISION = role.phrase_voice_revision
    current = role
    last_tts = {"backend": "not_tested", "status": "not_tested"}


def switch_role(role_id, loader=load_role):
    global voice_ready
    candidate = loader(role_id)  # Fully validate before touching remote state.
    with lock:
        old = current
        try:
            voice_ready = False
            _load_pair(candidate)
            activate(candidate)
            voice_ready = True
        except Exception as exc:
            rollback_error = None
            if old is not None:
                try:
                    _load_pair(old, restore=True)
                    voice_ready = True
                except Exception as rollback:
                    rollback_error = rollback
            if rollback_error or old is None:
                voice_ready = False
                raise RuntimeError("切换失败且无法确认恢复；GPT-SoVITS已隔离，仅允许SAPI回退: " + str(exc)) from exc
            raise RuntimeError("切换失败，已恢复原角色权重对: " + str(exc)) from exc
        return status()


def status():
    # Health inspection must remain responsive while inference holds the lock.
    role = current
    return {"role": role.public() if role else None, "voice_ready": voice_ready,
            "actual_tts": dict(last_tts)}
