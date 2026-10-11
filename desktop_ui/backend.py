"""Attach to existing services and reuse the legacy exclusive serial transport.

No service supervisor, subprocess, process termination, or firmware operations.
"""
from pathlib import Path
import json
import re
import threading
import time
import urllib.request
import urllib.error
from urllib.parse import quote
import uuid

from launcher_console import SerialConsole
from services.bridge_identity import mismatch, same_path

BASE = "http://127.0.0.1:8000"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError("本地管理请求拒绝重定向，请核对原服务")


def request(route, method="GET", timeout=5):
    req = urllib.request.Request(BASE + route, method=method,
                                 headers={"X-PRP-Maintenance": "roles"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(req, timeout=timeout) as response:
            value = json.loads(response.read(1024 * 1024).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("服务返回格式错误")
        return value
    except urllib.error.HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


class Bridge:
    def __init__(self, root, transport=request):
        self.root, self.transport = Path(root), transport

    def snapshot(self):
        health = self.transport("/health")
        identity = health.get("bridge_identity", {})
        if (health.get("service") != "prp-ai-bridge" or health.get("role_api") != 2
                or not same_path(identity.get("project_root"), self.root)):
            raise RuntimeError("8000 未确认属于本项目的 AI bridge；请由原启动窗口检查")
        config = self.transport("/config")
        return {"health": health, "config": config,
                "write_block": mismatch(identity, self.root)}

    def profiles(self, kind):
        result = {}
        for path in sorted((self.root / "server" / kind).glob("*.local.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8-sig"))
                identifier = record["id"]
                if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", identifier):
                    result[f"{record['display_name']} · {identifier}"] = identifier
            except (ValueError, KeyError, OSError):
                continue
        return result

    def apply(self, persona, voice):
        before = self.snapshot()
        if before["write_block"]:
            raise RuntimeError(before["write_block"])
        result = self.transport("/profiles/apply/" + quote(persona, safe="") + "/"
                                + quote(voice, safe=""), "POST", timeout=780)
        if (result.get("persona", {}).get("id") != persona
                or result.get("voice", {}).get("id") != voice
                or result.get("voice_ready") is not True):
            raise RuntimeError("未取得所选人格/音色的有效就绪回执，请刷新核实")
        # GET confirms actual state; a successful POST is never fabricated locally.
        after = self.snapshot()
        if (after["config"].get("persona", {}).get("id") != persona
                or after["config"].get("voice", {}).get("id") != voice):
            raise RuntimeError("复查时配置已改变，可能由其他窗口操作；请重新确认")
        return after


def parse_volume(line):
    line = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", line)
    match = re.search(r"(?:^|\s)VOLUME\s+(\{.*\})\s*$", line)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
        if not isinstance(data, dict):
            return None
        valid = (data.get("protocol") == "prp-volume-v1"
                 and isinstance(data.get("id"), str)
                 and re.fullmatch(r"[A-Za-z0-9_-]{1,32}", data["id"])
                 and data.get("op") in {"get", "set"}
                 and type(data.get("ok")) is bool
                 and type(data.get("ready")) is bool
                 and type(data.get("percent")) is int and 0 <= data["percent"] <= 100
                 and type(data.get("muted")) is bool
                 and data["muted"] == (data["percent"] == 0)
                 and data.get("persistent") is False
                 and isinstance(data.get("firmware"), str) and bool(data["firmware"])
                 and isinstance(data.get("error"), str))
        return data if valid else None
    except (ValueError, TypeError):
        return None


class Device:
    def __init__(self, emit, transport=None, timeout=2):
        self.emit, self.timeout = emit, timeout
        self.serial = transport or SerialConsole(self._line)
        self.condition = threading.Condition()
        self.pending = None
        self.reply = None
        self.volume = None
        self.last_nonzero = None

    def _line(self, source, line):
        data = parse_volume(line)
        with self.condition:
            if data and self.pending and (data["id"], data["op"]) == self.pending:
                self.reply = data
                self.condition.notify_all()
        self.emit("serial", line)

    def connect(self, port):
        self.volume = self.last_nonzero = None
        self.serial.connect(port)
        self.serial.send("status ai bridge")
        return self.get_volume()

    def transact(self, op, value=None):
        with self.condition:
            if self.pending:
                raise RuntimeError("音量请求正在进行")
            identifier = "ui_" + uuid.uuid4().hex[:20]
            self.pending, self.reply = (identifier, op), None
            self.volume = None
            try:
                self.serial.send(f"volume {op} {identifier}" + (f" {value}" if op == "set" else ""))
                deadline = time.monotonic() + self.timeout
                while self.reply is None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("2 秒未取得匹配回执；音量支持未确认或设备暂不可用")
                    self.condition.wait(remaining)
                data = self.reply
                if not data["ok"] or not data["ready"] or data["error"]:
                    raise RuntimeError("设备支持音量协议，但本次未应用：" + (data["error"] or "not_ready")
                                       + f"；回执当前值 {data['percent']}%")
                if op == "set" and data["percent"] != value:
                    raise RuntimeError("设备回执值与请求不符，请重新查询")
                self.volume = data
                if data["percent"]:
                    self.last_nonzero = data["percent"]
                return data
            finally:
                self.pending = None

    def get_volume(self):
        return self.transact("get")

    def set_volume(self, value):
        if type(value) is not int or not 0 <= value <= 100:
            raise ValueError("音量必须是 0～100 的整数")
        if self.volume is None:
            raise RuntimeError("请先取得设备音量能力回执")
        try:
            return self.transact("set", value)
        except TimeoutError as exc:
            # A fresh query can show state, but never confirms the timed-out SET.
            try:
                data = self.get_volume()
                self.emit("volume_observed", data)
            except Exception:
                pass
            raise TimeoutError(str(exc) + "；设置结果未确认，已用新 ID 尝试查询。不得自动重试设置") from exc

    def disconnect(self):
        self.serial.disconnect()
        self.volume = self.last_nonzero = None


class LogTail:
    """Only new complete lines from the existing launcher's bridge logs.

    Initial history is deliberately skipped. Never read audio, credentials or
    another project's logs. Rotation is tracked by file path and byte offset.
    """
    def __init__(self, root):
        self.folder = Path(root) / "server/logs/launcher"
        self.positions = {p: p.stat().st_size for p in self.folder.glob("*-bridge*.log")}
        self.fragments = {}

    def read(self):
        lines = []
        day = time.strftime("%Y-%m-%d")
        for path in sorted(self.folder.glob(day + "-bridge*.log")):
            size = path.stat().st_size
            position = self.positions.get(path, 0)
            if position > size:
                position = 0
                self.fragments.pop(path, None)
            # Limit a single tick to 256 KiB, continuing at the next tick.
            with path.open("rb") as stream:
                stream.seek(position)
                chunk = stream.read(262144)
                self.positions[path] = stream.tell()
            parts = (self.fragments.get(path, b"") + chunk).split(b"\n")
            self.fragments[path] = parts.pop()[-65536:]
            lines.extend(p.decode("utf-8", errors="replace") for p in parts)
        return lines


def dialogue_event(line):
    match = re.search(r'\[服务端\]\[([A-Za-z0-9_.-]+)\] (?:【词库命中】)?识别：(.*) \| 回复：(.*)$', line)
    if not match:
        return None
    try:
        heard, reply = json.loads(match[2]), json.loads(match[3])
        if not isinstance(heard, str) or not isinstance(reply, str):
            return None
        return {"id": match[1], "heard": heard, "reply": reply,
                "source": "服务日志（未确认设备已播放）"}
    except ValueError:
        return None
