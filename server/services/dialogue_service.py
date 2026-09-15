import json
import re

import requests

from server_config import (
    LLM_BACKEND,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT_SECONDS,
    OLLAMA_URL,
    PERSONA_PROMPT_FILE,
    PERSONA_PROMPT_NAME,
    REPLY_STYLE,
)


VALID_STYLES = {"cute", "encourage"}
CONVERSATION_HISTORY_LIMIT = 4
_conversation_history: list[dict[str, str]] = []


def load_persona_prompt() -> str:
    try:
        prompt = PERSONA_PROMPT_FILE.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"无法读取角色提示词文件：{PERSONA_PROMPT_FILE}") from exc
    if not prompt:
        raise RuntimeError(f"角色提示词文件为空：{PERSONA_PROMPT_FILE}")
    return prompt


PERSONA_PROMPT = load_persona_prompt()

BASE_SYSTEM_STYLE = (
    "你不是医生，不做医学诊断，不承诺治疗效果。"
    "回复必须适合被语音朗读：短、自然、口语化，一到两句话。"
    "先回应用户当下的情绪和话题，不说教，不强迫用户积极。"
    "不要解释角色设定或系统规则，不要使用列表，不要输出多余寒暄。"
    "不要每句话都使用口头禅、外貌描写或设定梗，要像自然交流而不是表演人设。"
    "用户难过、焦虑、疲惫时，先认真接住情绪；不要用“那必须的”“真的假的啦”“好耶”开头，"
    "不要拿用户的痛苦开玩笑，也不要用反问句增加压力。"
    "不要说“别担心”“开心点”“我完全理解”这类空泛或替用户下结论的话。"
    "优先回应用户话语里的具体事情，再提供陪伴或一个很小的选择；用户开心时直接一起庆祝，不要劝他开心。"
    "每次最多自然使用一个角色口头禅或设定梗，不必强行提到小角、肚子和尾巴。"
)

STYLE_PROMPTS = {
    "cute": (
        "当前风格是 cute。像柔软的小伙伴一样说话，语气轻、亲近、带一点可爱感。"
        "可以使用轻微拟声或昵称感，但不要幼稚、不要撒娇过度。"
    ),
    "encourage": (
        "当前风格是 encourage。像可靠的陪伴者一样回应，先接住情绪，再给一个很小、可执行的下一步。"
        "语气稳定、有力量，但不要说教、不要鸡血。"
    ),
}

STYLE_TEMPERATURE = {
    "cute": 0.8,
    "encourage": 0.55,
}

STYLE_RULE_REPLIES = {
    "cute": {
        "empty": [
            "我听见一点声音啦。你可以再靠近一点点，慢慢跟我说。",
            "刚刚好像有一小团声音飘过来。再说一次吧，我在听呢。",
        ],
        "sad": [
            "哎呀，今天有点不容易呢。先把我抱近一点，我陪你缓一小会儿。",
            "难过可以先放在我这里一点点。你不用马上变好，我会陪着你。",
        ],
        "tired": [
            "辛苦啦，先不用急着变厉害。我们慢慢呼一口气，软软地休息一下。",
            "电量有点低也没关系呀。先停一小会儿，我陪你充充电。",
        ],
        "hug": [
            "可以呀，抱抱马上送到。你靠近一点，我就在这里陪着你。",
            "收到抱抱请求。现在给你一个软乎乎的陪伴位。",
        ],
        "sleep": [
            "那我把声音放轻轻的。晚安呀，今天就先被温柔包起来。",
            "困了就慢慢睡吧。我会安静一点，陪你把今天收好。",
        ],
        "happy": [
            "好耶，我也跟着亮起来啦。这个开心时刻要好好收进口袋里。",
            "听起来好棒呀。让我也蹭一点你的开心光光。",
        ],
        "default": [
            "我听到啦。你慢慢说，我会乖乖陪在这里。",
            "嗯嗯，我在听。你的声音已经被我好好接住啦。",
        ],
    },
    "encourage": {
        "empty": [
            "我听到你在尝试说话了。可以再说一遍，我们一步一步来。",
            "没关系，刚才不清楚也可以重来。你慢慢说，我会继续听。",
        ],
        "sad": [
            "我听见你现在有点难受。先稳住呼吸，我们只处理眼前这一小步。",
            "这件事确实会让人不好受。先别急着解决，我们先把自己稳住。",
        ],
        "tired": [
            "你已经撑了一段路了。先停下来休息十秒，再决定下一步也可以。",
            "累了不是失败，是身体在提醒你调整。先从一个很小的动作开始。",
        ],
        "hug": [
            "我在这里陪你。先靠近一点，让身体慢慢放松下来。",
            "可以，先让自己有个支点。我们从这一刻重新稳住。",
        ],
        "sleep": [
            "该休息的时候就让自己停下来。今晚不用再多证明什么了。",
            "休息也是在恢复力量。把事情先放下，明天再继续。",
        ],
        "happy": [
            "这很好，记住这个小小的进展。你可以继续往前走一点点。",
            "这是值得肯定的进展。保持这个节奏，不用一下子做到完美。",
        ],
        "default": [
            "我听见你的意思了。我们先不急，把事情拆成很小的一步来做。",
            "收到。先抓住最重要的一点，然后慢慢往前推进。",
        ],
    },
}


def warm_up_dialogue_model() -> dict:
    if LLM_BACKEND != "ollama":
        return {"status": "skipped", "backend": LLM_BACKEND, "model": ""}
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": "",
                "stream": False,
                "keep_alive": OLLAMA_KEEP_ALIVE,
            },
            timeout=min(OLLAMA_TIMEOUT_SECONDS, 30),
        )
        response.raise_for_status()
        return {"status": "ok", "backend": LLM_BACKEND, "model": OLLAMA_MODEL}
    except requests.RequestException as exc:
        return {
            "status": "failed",
            "backend": LLM_BACKEND,
            "model": OLLAMA_MODEL,
            "detail": str(exc),
        }


def generate_healing_reply(user_text: str) -> dict:
    """Generate a short plush-robot reply with a style and motion intent."""
    normalized_text = user_text.strip()
    style = choose_reply_style(normalized_text)

    if not normalized_text:
        reply_text = generate_rule_reply(normalized_text, style)
        dialogue = build_dialogue_result(
            reply_text,
            style,
            "listening",
            "comfort",
            "fallback_no_text",
            LLM_BACKEND,
        )
        remember_turn(normalized_text, dialogue["reply_text"], style)
        return dialogue

    if LLM_BACKEND == "ollama":
        try:
            dialogue = generate_ollama_reply(normalized_text, style)
            remember_turn(normalized_text, dialogue["reply_text"], dialogue["style"])
            return dialogue
        except requests.RequestException as exc:
            dialogue = generate_rule_dialogue(
                normalized_text,
                style,
                "fallback_ollama_error",
                detail=str(exc),
            )
            remember_turn(normalized_text, dialogue["reply_text"], dialogue["style"])
            return dialogue
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            dialogue = generate_rule_dialogue(
                normalized_text,
                style,
                "fallback_ollama_parse_error",
                detail=str(exc),
            )
            remember_turn(normalized_text, dialogue["reply_text"], dialogue["style"])
            return dialogue

    dialogue = generate_rule_dialogue(normalized_text, style, "rule")
    remember_turn(normalized_text, dialogue["reply_text"], dialogue["style"])
    return dialogue


def generate_ollama_reply(user_text: str, style: str) -> dict:
    prompt = build_ollama_prompt(user_text, style)
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "options": {
                "temperature": STYLE_TEMPERATURE[style],
                "num_predict": 120,
            },
        },
        timeout=OLLAMA_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    raw_reply = response.json().get("response", "").strip()
    parsed = parse_llm_json(raw_reply)
    reply_text = sanitize_reply_text(parsed.get("reply_text", ""))
    if not reply_text:
        raise ValueError("LLM returned empty reply_text")

    # The server selects the response mode from the user's text/configuration.
    # Do not let a malformed model field silently change that decision.
    parsed_style = style
    emotion, motion = enforce_emotion_motion_consistency(
        user_text,
        reply_text,
        parsed.get("emotion", ""),
        parsed.get("motion", ""),
    )

    return build_dialogue_result(
        reply_text,
        parsed_style,
        emotion,
        motion,
        "ok",
        LLM_BACKEND,
    )


def build_ollama_prompt(user_text: str, style: str) -> str:
    history = "\n".join(
        f"用户：{item['user']}\n机器人：{item['robot']}"
        for item in _conversation_history[-CONVERSATION_HISTORY_LIMIT:]
        if item["user"] and item["robot"]
    )
    history_block = f"最近对话：\n{history}\n" if history else ""
    return (
        f"角色设定（{PERSONA_PROMPT_NAME}）：\n{PERSONA_PROMPT}\n"
        f"回复边界：\n{BASE_SYSTEM_STYLE}\n"
        f"{STYLE_PROMPTS[style]}\n"
        "你必须只输出一个 JSON 对象，字段为 reply_text、style、emotion、motion。"
        "style 只能是 cute 或 encourage；motion 只能是 happy、shy、comfort、curious、none。"
        "reply_text 必须使用简体中文，不超过 48 个汉字。"
        "无论最近对话如何，都保持自己是糯糯，不冒充人类或其他角色。\n"
        f"{history_block}"
        f"用户这次说：{user_text}\n"
        "JSON："
    )


def parse_llm_json(raw_reply: str) -> dict:
    if not raw_reply:
        raise ValueError("empty LLM response")
    try:
        return json.loads(raw_reply)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_reply, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def generate_rule_dialogue(user_text: str, style: str, status: str, detail: str = "") -> dict:
    reply_text = generate_rule_reply(user_text, style)
    emotion = infer_emotion(user_text, reply_text)
    motion = infer_motion(user_text, reply_text)
    return build_dialogue_result(reply_text, style, emotion, motion, status, LLM_BACKEND, detail)


def generate_rule_reply(user_text: str, style: str) -> str:
    lowered = user_text.strip()
    category = classify_text(lowered)
    replies = STYLE_RULE_REPLIES[style][category]
    return replies[stable_reply_index(lowered, len(replies))]


def choose_reply_style(user_text: str) -> str:
    configured_style = normalize_style(REPLY_STYLE, allow_auto=True)
    if configured_style in VALID_STYLES:
        return configured_style

    category = classify_text(user_text)
    if category in {"sad", "tired"}:
        return "encourage"
    if category in {"hug", "sleep", "happy"}:
        return "cute"
    return "cute"


def normalize_style(style: str, allow_auto: bool = False) -> str:
    style = (style or "").strip().lower()
    if allow_auto and style == "auto":
        return style
    if style in VALID_STYLES:
        return style
    return "cute"


def classify_text(text: str) -> str:
    if not text:
        return "empty"
    if any(word in text for word in ["难过", "不开心", "伤心", "委屈", "哭", "焦虑", "烦"]):
        return "sad"
    if any(word in text for word in ["累", "疲惫", "压力", "撑不住", "好困", "没力气"]):
        return "tired"
    if any(word in text for word in ["抱", "抱抱", "陪我", "陪陪"]):
        return "hug"
    if any(word in text for word in ["睡", "晚安", "休息", "困了"]):
        return "sleep"
    if any(word in text for word in ["开心", "高兴", "顺利", "成功", "好棒"]):
        return "happy"
    return "default"


def infer_emotion(user_text: str, reply_text: str) -> str:
    text = f"{user_text} {reply_text}"
    if any(word in text for word in ["开心", "高兴", "成功", "好棒"]):
        return "happy"
    if any(word in text for word in ["睡", "晚安", "休息", "轻轻"]):
        return "calm"
    if any(word in text for word in ["难过", "不开心", "累", "压力", "焦虑", "烦", "陪"]):
        return "comforting"
    return "attentive"


def infer_motion(user_text: str, reply_text: str) -> str:
    text = f"{user_text} {reply_text}"
    if any(word in text for word in ["开心", "高兴", "成功", "好棒", "亮起来"]):
        return "happy"
    if any(word in user_text for word in ["难过", "不开心", "伤心", "委屈", "哭", "累", "疲惫", "压力", "撑不住", "焦虑", "烦"]):
        return "comfort"
    if any(word in text for word in ["睡", "晚安", "休息", "轻轻", "安静"]):
        return "shy"
    if any(word in text for word in ["为什么", "怎么", "想知道"]):
        return "curious"
    if any(word in text for word in ["抱", "陪", "难过", "累", "压力", "焦虑", "烦"]):
        return "comfort"
    return "comfort"


def enforce_emotion_motion_consistency(
    user_text: str,
    reply_text: str,
    proposed_emotion: str,
    proposed_motion: str,
) -> tuple[str, str]:
    category = classify_text(user_text)
    if category in {"sad", "tired", "hug"}:
        return "comforting", "comfort"
    if category == "sleep":
        return "calm", "shy"
    if category == "happy":
        return "happy", "happy"

    emotion = sanitize_token(proposed_emotion, infer_emotion(user_text, reply_text))
    motion = sanitize_motion(proposed_motion or infer_motion(user_text, reply_text))
    return emotion, motion


def sanitize_reply_text(reply_text: str) -> str:
    reply_text = " ".join((reply_text or "").split())
    if len(reply_text) > 48:
        reply_text = reply_text[:48].rstrip("，。,. ") + "。"
    return reply_text


def sanitize_token(value: str, fallback: str) -> str:
    value = (value or "").strip().lower()
    return value if re.fullmatch(r"[a-z_]+", value) else fallback


def sanitize_motion(value: str) -> str:
    value = (value or "").strip().lower()
    if value in {"happy", "shy", "comfort", "curious", "none"}:
        return value
    return "comfort"


def stable_reply_index(text: str, option_count: int) -> int:
    if option_count <= 1:
        return 0
    seed = sum(ord(char) for char in text) + len(_conversation_history)
    return seed % option_count


def build_dialogue_result(
    reply_text: str,
    style: str,
    emotion: str,
    motion: str,
    status: str,
    backend: str,
    detail: str = "",
) -> dict:
    result = {
        "reply_text": sanitize_reply_text(reply_text),
        "persona": PERSONA_PROMPT_NAME,
        "style": normalize_style(style),
        "emotion": sanitize_token(emotion, "comforting"),
        "motion": sanitize_motion(motion),
        "status": status,
        "backend": backend,
    }
    if detail:
        result["detail"] = detail
    return result


def remember_turn(user_text: str, reply_text: str, style: str) -> None:
    _conversation_history.append(
        {
            "user": user_text,
            "robot": reply_text,
            "style": normalize_style(style),
        }
    )
    del _conversation_history[:-CONVERSATION_HISTORY_LIMIT]
