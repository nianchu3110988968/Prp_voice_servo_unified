"""Validated local role records; no model deserialization or inference here."""
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[2]
ID_PATTERN = r"[A-Za-z][A-Za-z0-9_-]{0,63}"


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class Role:
    id: str
    display_name: str
    character_name: str
    persona_prompt_file: str
    gpt_weights: str
    sovits_weights: str
    gpt_sovits_version: str
    reference_wav: str
    reference_text: str
    prompt_language: str
    text_language: str
    phrase_voice_revision: str
    weight_pair: dict
    persona_prompt: str = ""

    @property
    def cache_key(self):
        return self.id + "/" + hashlib.sha256(json.dumps(asdict(self), sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    @property
    def url_token(self):
        # Keep ESP32's existing 160-byte audio_url buffer unchanged.
        return hashlib.sha256(self.cache_key.encode()).hexdigest()[:24]

    def public(self):
        result = asdict(self)
        result.pop("persona_prompt")
        return result


def load_role(role_id, root=ROOT):
    if not isinstance(role_id, str) or not re.fullmatch(ID_PATTERN, role_id):
        raise ValueError("角色ID只允许字母开头的字母、数字、下划线和短横线")
    root = Path(root).resolve()
    path = root / "server/roles" / (role_id + ".local.json")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    fields = set(Role.__dataclass_fields__) - {"persona_prompt"}
    if set(data) != fields or data.get("id") != role_id:
        raise ValueError("角色字段缺失、多余或ID与文件名不一致")
    for key in fields - {"weight_pair"}:
        if not isinstance(data[key], str) or not data[key].strip():
            raise ValueError("角色字段不能为空: " + key)
    if data["gpt_sovits_version"] not in {"v1", "v2", "v2Pro", "v2ProPlus", "v3", "v4"}:
        raise ValueError("不支持的GPT-SoVITS版本")
    for key in ("prompt_language", "text_language"):
        if data[key] not in {"zh", "en", "ja", "ko", "yue", "all_zh", "all_ja", "all_ko", "all_yue", "auto", "auto_yue"}:
            raise ValueError("不支持的语言代码: " + key)
    for key, suffix in (("persona_prompt_file", ".txt"), ("gpt_weights", ".ckpt"), ("sovits_weights", ".pth"), ("reference_wav", ".wav")):
        value = Path(data[key])
        value = (root / value).resolve() if not value.is_absolute() else value.resolve()
        if not value.is_file() or value.suffix.lower() != suffix:
            raise ValueError("文件不存在或类型错误: " + key + " = " + str(value))
        if key == "persona_prompt_file" and not value.is_relative_to(root / "server/prompts"):
            raise ValueError("人格文件必须位于server/prompts目录")
        data[key] = str(value)
    pair = data["weight_pair"]
    if not isinstance(pair, dict) or not pair.get("id") or pair.get("version") != data["gpt_sovits_version"]:
        raise ValueError("权重配对版本无效")
    for key, field in (("gpt_sha256", "gpt_weights"), ("sovits_sha256", "sovits_weights")):
        if not isinstance(pair.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", pair[key]) or file_sha(data[field]) != pair[key]:
            raise ValueError("权重配对哈希不匹配: " + field)
    data["persona_prompt"] = Path(data["persona_prompt_file"]).read_text(encoding="utf-8-sig").strip()
    if not data["persona_prompt"]:
        raise ValueError("人格提示词为空")
    return Role(**data)


def list_roles(root=ROOT):
    return sorted(p.name[:-11] for p in (Path(root) / "server/roles").glob("*.local.json"))
