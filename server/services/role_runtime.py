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


def activate(role, update_persona=True, update_voice=True):
    global current, last_tts
    from services import dialogue_service
    import server_config as config
    if update_persona:
        dialogue_service.set_persona(role)
        config.PERSONA_PROMPT_NAME = role.persona_id or role.id
        config.PERSONA_PROMPT_FILE = Path(role.persona_prompt_file)
    config.TTS_BACKEND = "gpt_sovits"
    config.GPT_SOVITS_REFERENCE_WAV = role.reference_wav
    config.GPT_SOVITS_PROMPT_TEXT = role.reference_text
    config.GPT_SOVITS_PROMPT_LANGUAGE = role.prompt_language
    config.GPT_SOVITS_TEXT_LANGUAGE = role.text_language
    config.PHRASE_VOICE_REVISION = role.phrase_voice_revision
    current = role
    if update_voice:
        last_tts = {"backend": "not_tested", "status": "not_tested"}


def switch_role(role_id, loader=load_role):
    global voice_ready
    candidate = loader(role_id)  # Fully validate before touching remote state.
    with lock:
        old = current
        try:
            voice_ready = False
            _load_pair(candidate)
            activate(candidate, update_persona=(old is None or (candidate.persona_prompt, candidate.persona_id or candidate.id, candidate.character_name) != (old.persona_prompt, old.persona_id or old.id, old.character_name)))
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
    return {"role": role.public() if role else None,
            "persona": {"id": role.persona_id or role.id, "display_name": role.display_name,
                        "character_name": role.character_name, "prompt_file": role.persona_prompt_file} if role else None,
            "voice": {"id": role.voice_id or role.id, "display_name": role.voice_display_name or role.display_name,
                      "voice_revision": role.phrase_voice_revision, "gpt_weights": role.gpt_weights,
                      "sovits_weights": role.sovits_weights, "reference_wav": role.reference_wav} if role else None,
            "voice_ready": voice_ready,
            "actual_tts": dict(last_tts)}


def switch_persona(persona_id):
    from dataclasses import replace
    from services.profile_config import load_persona
    persona = load_persona(persona_id)
    with lock:
        if current is None:
            raise ValueError("请先完整启动服务")
        candidate = replace(current, id=persona.id, persona_id=persona.id,
                            display_name=persona.display_name, character_name=persona.character_name,
                            persona_prompt_file=persona.prompt_file, persona_prompt=persona.prompt)
        activate(candidate, update_voice=False)
        return status()


def switch_voice(voice_id):
    from dataclasses import replace
    from services.profile_config import load_voice
    voice = load_voice(voice_id)
    with lock:
        if current is None:
            raise ValueError("请先完整启动服务")
        data = voice.public()
        data.pop("id")
        data.pop("display_name")
        data["phrase_voice_revision"] = data.pop("voice_revision")
        candidate = replace(current, voice_id=voice.id, voice_display_name=voice.display_name, **data)
        return switch_role(voice_id, loader=lambda _: candidate)


def apply_combination(persona_id, voice_id):
    from services.profile_config import load_combination
    candidate = load_combination(persona_id, voice_id)
    with lock:
        voice_fields = ("gpt_sovits_version", "voice_id", "gpt_weights", "sovits_weights", "weight_pair", "reference_wav",
                        "reference_text", "prompt_language", "text_language", "phrase_voice_revision")
        if current and voice_ready and all(getattr(current, k) == getattr(candidate, k) for k in voice_fields):
            activate(candidate, update_voice=False)
            return status()
        return switch_role(persona_id, loader=lambda _: candidate)
