"""Editable selection rules; the model selects IDs, never servo angles."""
import json
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_FILE = ROOT / "configs" / "motion_catalog.json"
RULES_FILE = ROOT / "prompts" / "motion_selection.txt"
FIRMWARE_IDS = frozenset({"none", "happy", "shy", "comfort", "curious"})
ALIASES = {"自动": "auto", "不动作": "none", "无": "none", "开心": "happy",
           "害羞": "shy", "安慰": "comfort", "好奇": "curious"}
_last_error = None


def parse_setting(value: str) -> str:
    """Validate Excel values without silently turning a typo into a movement."""
    value = value.strip().lower()
    value = ALIASES.get(value, value) or "auto"
    if value not in FIRMWARE_IDS | {"auto"}:
        raise ValueError("动作只能填自动、不动作、开心、害羞、安慰、好奇或对应英文ID")
    return value


def load_policy() -> tuple[list[dict], str]:
    data = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("动作目录必须为JSON数组")
    seen, enabled = set(), []
    for item in data:
        if not isinstance(item, dict) or item.get("id") not in FIRMWARE_IDS:
            raise ValueError("动作目录含固件不支持的ID")
        if item["id"] in seen or type(item.get("enabled")) is not bool:
            raise ValueError("动作目录ID重复或enabled不是布尔值")
        if not isinstance(item.get("description"), str) or not item["description"].strip():
            raise ValueError("动作说明不能为空")
        seen.add(item["id"])
        if item["enabled"]:
            enabled.append({"id": item["id"], "description": item["description"]})
    if "none" not in {item["id"] for item in enabled}:
        raise ValueError("none必须始终启用")
    rules = RULES_FILE.read_text(encoding="utf-8").strip()
    if not rules or len(rules) > 6000:
        raise ValueError("动作选择提示词不能为空或超过6000字")
    return enabled, rules


def policy() -> tuple[list[dict], str]:
    global _last_error
    try:
        result = load_policy()
        _last_error = None
        return result
    except (OSError, ValueError, TypeError) as exc:
        # Bad maintenance input must never break speech or enable extra motion.
        error = str(exc)
        if error != _last_error:
            logging.getLogger(__name__).warning("动作配置无效，本轮仅允许不动作：%s", error)
            _last_error = error
        return [{"id": "none", "description": "不动作"}], "只选择none。"


def selection_prompt() -> str:
    catalogue, rules = policy()
    return ("动作选择规则（只影响motion字段，不改写固定回复）：\n" + rules +
            "\n允许动作：" + json.dumps(catalogue, ensure_ascii=False) + "\n")


def sanitize_motion(value) -> str:
    allowed = {item["id"] for item in policy()[0]}
    if not isinstance(value, str):
        return "none"
    value = value.strip().lower()
    return value if value in allowed else "none"
