"""Identify this disk checkout and its startup code snapshot without loading models."""
import hashlib
import os
from pathlib import Path
import sys

PROTOCOL = "independent-phrase-motion-v1"


def source_signature(root):
    server = Path(root).resolve() / "server"
    paths = [server / "ai_bridge_server.py", server / "server_config.py"]
    paths.extend(sorted((server / "services").glob("*.py")))
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(server).as_posix().encode("utf-8") + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()


def startup_identity(root):
    return {"protocol": PROTOCOL, "project_root": str(Path(root).resolve()),
            "source_sha256": source_signature(root),
            "python_executable": str(Path(sys.executable).resolve()), "pid": os.getpid()}


def same_path(left, right):
    return bool(left and right) and os.path.normcase(str(Path(left).resolve())) == os.path.normcase(str(Path(right).resolve()))


def mismatch(identity, root, expected_python=None):
    if not isinstance(identity, dict) or identity.get("protocol") != PROTOCOL:
        return "服务缺少独立词库/起播动作版本标识，请在原窗口停止旧实例后重启"
    if not same_path(identity.get("project_root"), root):
        return "8000属于其他项目目录，不会复用或停止它"
    if identity.get("source_sha256") != source_signature(root):
        return "AI bridge启动后源码已变化，请在原窗口重启以加载当前代码"
    if expected_python and not same_path(identity.get("python_executable"), expected_python):
        return "AI bridge的Python与启动器当前配置不同，请核对原服务终端"
    return ""
