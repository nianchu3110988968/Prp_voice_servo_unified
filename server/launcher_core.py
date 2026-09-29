"""Standard-library service supervisor. Only retained Popen handles confer ownership."""
from pathlib import Path
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from services.role_config import ROOT, load_role

PORTS = {"ollama": 11434, "gpt_sovits": 9880, "bridge": 8000}


def request_json(url, method="GET", body=None, timeout=5):
    headers = {"X-PRP-Maintenance": "roles"}
    data = None if body is None else json.dumps(body).encode()
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    # Local control must not pass through a machine-wide HTTP proxy.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as response:
        return json.load(response)


def port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def probe(name):
    if not port_open(PORTS[name]):
        return {"state": "stopped"}
    try:
        if name == "ollama":
            data = request_json("http://127.0.0.1:11434/api/tags")
            valid = isinstance(data.get("models"), list)
        elif name == "gpt_sovits":
            data = request_json("http://127.0.0.1:9880/openapi.json")
            valid = all(p in data.get("paths", {}) for p in ("/tts", "/set_gpt_weights", "/set_sovits_weights"))
        else:
            data = request_json("http://127.0.0.1:8000/health")
            valid = data.get("service") == "prp-ai-bridge" and data.get("role_api") == 1
        return {"state": "healthy" if valid else "occupied_unknown", "data": data}
    except Exception as exc:
        return {"state": "occupied_unhealthy", "detail": str(exc)}


def read_settings(root=ROOT):
    root = Path(root).resolve()
    settings = json.loads((root / "server/configs/launcher.local.json").read_text(encoding="utf-8-sig"))
    settings["project_root"] = str(root)
    return settings


def generated_yaml(settings, role):
    """Derived disposable YAML, never the user's legacy hand-edited YAML."""
    root = Path(settings["project_root"])
    folder = root / "server/.runtime"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "gpt_sovits.generated.yaml"
    data = {"custom": {"bert_base_path": "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large",
        "cnhuhbert_base_path": "GPT_SoVITS/pretrained_models/chinese-hubert-base",
        "device": settings.get("device", "cuda"), "is_half": settings.get("is_half", True),
        "version": role.gpt_sovits_version, "t2s_weights_path": role.gpt_weights,
        "vits_weights_path": role.sovits_weights}}
    # JSON is also valid YAML, and safely escapes Windows paths.
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def command_for(name, settings, role):
    root = Path(settings["project_root"])
    env = os.environ.copy()
    env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONUNBUFFERED="1", PRP_ROLE_ID=role.id,
               PRP_TTS_BACKEND="gpt_sovits", PRP_MODEL_WARMUP_ENABLED="true")
    if name == "ollama":
        env["OLLAMA_HOST"] = "127.0.0.1:11434"
        return [settings["ollama_executable"], "serve"], root, env
    if name == "gpt_sovits":
        location = Path(settings["gpt_sovits_root"])
        python = location / "runtime/python.exe"
        api = location / "api_v2.py"
        if not python.is_file() or not api.is_file():
            raise ValueError("GPT-SoVITS运行时或api_v2.py不存在")
        return [str(python), "-u", str(api), "-a", "127.0.0.1", "-p", "9880", "-c", str(generated_yaml(settings, role))], location, env
    return [settings["bridge_python"], "-u", "-m", "uvicorn", "ai_bridge_server:app", "--app-dir",
            str(root / "server"), "--host", "0.0.0.0", "--port", "8000"], root, env


class Supervisor:
    def __init__(self, settings, log=print):
        self.settings, self.log = settings, log
        self.owned = {}
        self.cancel = threading.Event()
        self.mutex = threading.RLock()
        self.audit_path = Path(settings["project_root"]) / "server/.runtime/owned-processes.json"

    def audit(self):
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_path.write_text(json.dumps({name: {"pid": p.pid, "running": p.poll() is None}
                                              for name, p in self.owned.items()}, indent=2), encoding="utf-8")

    def _output(self, name, process):
        try:
            for line in process.stdout:
                self.log("[" + name + "] " + line.rstrip())
        finally:
            process.stdout.close()
            self.log("[" + name + "] 日志结束")

    def ensure(self, name, role):
        status = probe(name)
        if status["state"] == "healthy":
            self.log(name + "：复用现有健康服务（不取得停止权限）")
            return status
        if status["state"] != "stopped":
            raise RuntimeError(name + "端口被未知或未就绪服务占用，请查看原窗口；不会终止它")
        args, cwd, env = command_for(name, self.settings, role)
        # Piped output is continuously displayed in the owning App, not a hidden log file.
        process = subprocess.Popen(args, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.owned[name] = process
        self.audit()
        threading.Thread(target=self._output, args=(name, process), daemon=True).start()
        self.log(name + "：启动PID=" + str(process.pid))
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            if self.cancel.is_set():
                raise RuntimeError("启动已取消")
            if process.poll() is not None:
                raise RuntimeError(name + "退出，代码=" + str(process.returncode))
            status = probe(name)
            if status["state"] == "healthy":
                return status
            self.cancel.wait(0.5)
        raise RuntimeError(name + "就绪超时；日志和自有进程仍保留，可点击停止")

    def start_all(self, role_id):
        with self.mutex:
            self.cancel.clear()
            role = load_role(role_id, Path(self.settings["project_root"]))
            states = {name: probe(name) for name in PORTS}
            for name, state in states.items():
                if state["state"] not in {"stopped", "healthy"}:
                    raise RuntimeError(name + "端口已有未知/旧版/不健康服务，请在原窗口处理")
            self.ensure("ollama", role)
            self.ensure("gpt_sovits", role)
            bridge = self.ensure("bridge", role)["data"]
            active = bridge.get("role") or {}
            if active != role.public() or not bridge.get("voice_ready"):
                self.switch(role_id)
            health = request_json("http://127.0.0.1:8000/health")
            if health.get("warmup") != {"asr": "ok", "llm": "ok"}:
                raise RuntimeError("AI bridge已启动，但ASR/LLM预热未通过：" + str(health.get("warmup")))
            self.log("完整启动就绪；实际音色后端在首次TTS成功后确认（不会自动生成词库音频）")
            return self.health()

    def switch(self, role_id):
        with self.mutex:
            load_role(role_id, Path(self.settings["project_root"]))
            if probe("bridge")["state"] != "healthy" or probe("gpt_sovits")["state"] != "healthy":
                raise RuntimeError("仅切换需要已运行的新版AI bridge和GPT-SoVITS；请先完整启动")
            result = request_json("http://127.0.0.1:8000/roles/switch/" + role_id, "POST", timeout=780)
            self.log("角色切换成功：" + role_id + "；Ollama和ASR保持运行，短期历史已清空")
            return result

    def health(self):
        result = {name: probe(name) for name in PORTS}
        self.log(json.dumps(result, ensure_ascii=False, indent=2))
        return result

    def stop_owned(self):
        self.cancel.set()
        with self.mutex:
            for name in ("bridge", "gpt_sovits", "ollama"):
                process = self.owned.get(name)
                if process is None:
                    continue
                if process.poll() is None:
                    # Never look up a PID from disk or kill by port/name.
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                self.log(name + "：自有进程已退出；端口" + ("仍占用（不会杀未知进程）" if port_open(PORTS[name]) else "已释放"))
                del self.owned[name]
            self.audit()
