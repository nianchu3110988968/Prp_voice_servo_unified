"""Independent local personas and voices. Import hashes files, never loads models."""
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import re
import uuid
from services.role_config import ROOT, ID_PATTERN, file_sha

VERSIONS = {"v1", "v2", "v2Pro", "v2ProPlus", "v3", "v4"}
LANGUAGES = {"zh", "en", "ja", "ko", "yue", "all_zh", "all_ja", "all_ko", "all_yue", "auto", "auto_yue"}


def valid_id(value):
    if not isinstance(value, str) or not re.fullmatch(ID_PATTERN, value):
        raise ValueError("ID需以字母开头，仅字母/数字/_/-，最长64字符")
    if value.upper() in {"CON", "PRN", "AUX", "NUL", *("COM" + str(n) for n in range(1, 10)), *("LPT" + str(n) for n in range(1, 10))}:
        raise ValueError("ID不能是Windows保留文件名")
    return value


def existing_file(value, suffix, root):
    path = (Path(root) / value).resolve()
    if not path.is_file() or path.suffix.lower() != suffix or not path.stat().st_size:
        raise ValueError("文件不存在、为空或类型错误: " + str(path))
    return str(path)


def read_record(kind, identifier, root):
    valid_id(identifier)
    data = json.loads((Path(root) / "server" / kind / (identifier + ".local.json")).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("id") != identifier:
        raise ValueError("配置ID与文件名不一致")
    return data


def required(data, fields):
    if set(data) != set(fields):
        raise ValueError("配置字段缺失或多余: " + str(set(data) ^ set(fields)))
    for key in fields:
        if key != "weight_pair" and (not isinstance(data[key], str) or not data[key].strip()):
            raise ValueError("字段不能为空: " + key)
    valid_id(data["id"])


@dataclass(frozen=True)
class Persona:
    id: str
    display_name: str
    character_name: str
    prompt_file: str
    prompt: str

    def public(self):
        return {k: v for k, v in asdict(self).items() if k != "prompt"}


@dataclass(frozen=True)
class Voice:
    id: str
    display_name: str
    gpt_weights: str
    sovits_weights: str
    gpt_sovits_version: str
    reference_wav: str
    reference_text: str
    prompt_language: str
    text_language: str
    voice_revision: str
    weight_pair: dict

    def public(self):
        return asdict(self)


def parse_persona(data, root=ROOT):
    required(data, ("id", "display_name", "character_name", "prompt_file"))
    data = dict(data)
    data["prompt_file"] = existing_file(data["prompt_file"], ".txt", root)
    if not Path(data["prompt_file"]).is_relative_to(Path(root).resolve() / "server/prompts"):
        raise ValueError("人格正文必须位于server/prompts；导入会保存独立TXT")
    prompt = Path(data["prompt_file"]).read_text(encoding="utf-8-sig").strip()
    if not prompt:
        raise ValueError("人格正文不能为空")
    return Persona(**data, prompt=prompt)


def parse_voice(data, root=ROOT, calculate=False):
    required(data, Voice.__dataclass_fields__)
    data = dict(data)
    for field, suffix in (("gpt_weights", ".ckpt"), ("sovits_weights", ".pth"), ("reference_wav", ".wav")):
        data[field] = existing_file(data[field], suffix, root)
    if data["gpt_sovits_version"] not in VERSIONS or any(data[k] not in LANGUAGES for k in ("prompt_language", "text_language")):
        raise ValueError("不支持的版本或语言")
    pair = data["weight_pair"]
    if calculate:
        pair = {"id": data["id"], "version": data["gpt_sovits_version"]}
    elif not isinstance(pair, dict) or not pair.get("id") or pair.get("version") != data["gpt_sovits_version"]:
        raise ValueError("权重配对版本无效")
    pair = dict(pair)
    for key, field in (("gpt_sha256", "gpt_weights"), ("sovits_sha256", "sovits_weights")):
        actual = file_sha(data[field])
        if not calculate and pair.get(key) != actual:
            raise ValueError("权重配对哈希不匹配: " + field + "；请用导入向导重新登记确认的配对")
        pair[key] = actual
    data["weight_pair"] = pair
    return Voice(**data)


def load_persona(identifier, root=ROOT):
    return parse_persona(read_record("personas", identifier, root), root)


def load_voice(identifier, root=ROOT):
    return parse_voice(read_record("voices", identifier, root), root)


def list_profiles(kind, root=ROOT):
    if kind not in {"personas", "voices"}:
        raise ValueError("unknown profile kind")
    return sorted(p.name[:-11] for p in (Path(root) / "server" / kind).glob("*.local.json"))


def save_new(kind, data, root):
    path = Path(root) / "server" / kind / (valid_id(data["id"]) + ".local.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation: imports never overwrite existing profiles.
    with path.open("x", encoding="utf-8") as output:
        json.dump(data, output, ensure_ascii=False, indent=2)
    return path


def import_persona(identifier, display_name, character_name, text, root=ROOT):
    valid_id(identifier)
    if not text.strip() or not display_name.strip() or not character_name.strip():
        raise ValueError("显示名称、角色名称和正文均需填写")
    folder = Path(root) / "server/prompts"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (identifier + ".txt")
    if (Path(root) / "server/personas" / (identifier + ".local.json")).exists():
        raise ValueError("人格ID已存在，请使用新ID")
    with path.open("x", encoding="utf-8") as output:
        output.write(text)
    data = dict(id=identifier, display_name=display_name, character_name=character_name,
                prompt_file=str(path.resolve()))
    save_new("personas", data, root)
    return parse_persona(data, root)


def import_voice(data, root=ROOT):
    voice = parse_voice(data, root, calculate=True)
    save_new("voices", voice.public(), root)
    return voice


def compose(persona, voice):
    from services.role_config import Role
    values = voice.public()
    values.pop("id")
    values.pop("display_name")
    values["phrase_voice_revision"] = values.pop("voice_revision")
    return Role(id=persona.id, display_name=persona.display_name,
                character_name=persona.character_name, persona_prompt_file=persona.prompt_file,
                persona_prompt=persona.prompt, persona_id=persona.id, voice_id=voice.id,
                voice_display_name=voice.display_name, **values)


def load_combination(persona_id, voice_id, root=ROOT):
    return compose(load_persona(persona_id, root), load_voice(voice_id, root))


def migrate_legacy(role_id="New_ManBoo", root=ROOT):
    """Create missing split records, leaving the original role and all media intact."""
    from services.role_config import load_role
    role = load_role(role_id, root)
    persona = dict(id=role.persona_id or role.id, display_name=role.display_name,
                   character_name=role.character_name, prompt_file=role.persona_prompt_file)
    voice = {k: getattr(role, k) for k in Voice.__dataclass_fields__ if k not in {"id", "display_name", "voice_revision"}}
    voice.update(id=role.voice_id or role.id, display_name=role.voice_display_name or role.display_name,
                 voice_revision=role.phrase_voice_revision)
    for kind, data in (("personas", persona), ("voices", voice)):
        if not (Path(root) / "server" / kind / (data["id"] + ".local.json")).exists():
            save_new(kind, data, root)
    return persona["id"], voice["id"]
