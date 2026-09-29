"""Standard-library service supervisor. Only retained Popen handles confer ownership."""
from pathlib import Path
import json
import os
import socket
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from services.role_config import ROOT, load_role
from services.bridge_identity import mismatch

PORTS = {"ollama": 11434, "gpt_sovits": 9880, "bridge": 8000}


def request_json(url, method="GET", body=None, timeout=5, request_id=None):
    headers = {"X-PRP-Maintenance": "roles"}
    if request_id:
        headers["X-Request-ID"] = request_id
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


def probe(name, root=ROOT, expected_python=None):
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
            valid = data.get("service") == "prp-ai-bridge" and data.get("role_api") == 2
            if valid:
                detail = mismatch(data.get("bridge_identity"), root, expected_python)
                if detail:
                    return {"state": "occupied_stale_or_foreign", "detail": detail, "data": data}
        return {"state": "healthy" if valid else "occupied_unknown", "data": data}
    except Exception as exc:
        return {"state": "occupied_unhealthy", "detail": str(exc)}


def read_settings(root=ROOT):
    root = Path(root).resolve()
    settings = json.loads((root / "server/configs/launcher.local.json").read_text(encoding="utf-8-sig"))
    settings["project_root"] = str(root)
    configured = settings["bridge_python"]
    candidate = Path(configured)
    if candidate.is_absolute() or candidate.parent != Path("."):
        python = candidate if candidate.is_absolute() else root / candidate
    else:
        resolved = shutil.which(configured)
        if not resolved:
            raise ValueError("找不到AI bridge Python：" + configured)
        python = Path(resolved)
    if not python.is_file():
        raise ValueError("AI bridge Python不存在：" + str(python))
    # Scoop/Windows PATH entries may be launch shims, not sys.executable.
    # Ask the selected interpreter once, then pin its actual path for this App.
    result = subprocess.run([str(python), "-I", "-X", "utf8", "-c", "import sys; print(sys.executable)"],
                            cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=15,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    if result.returncode:
        raise ValueError("AI bridge Python无法启动：" + str(python))
    actual = Path(result.stdout.strip())
    if not actual.is_absolute() or not actual.is_file():
        raise ValueError("AI bridge Python未返回有效解释器路径：" + str(python))
    settings["bridge_python"] = str(actual.resolve())
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
    if getattr(role, "persona_id", "") and getattr(role, "voice_id", ""):
        env.update(PRP_PERSONA_ID=role.persona_id, PRP_VOICE_ID=role.voice_id)
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

    def probe(self, name):
        return probe(name, self.settings["project_root"], self.settings.get("bridge_python"))

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
        status = self.probe(name)
        if status["state"] == "healthy":
            self.log(name + "：复用现有健康服务；只能健康检查，无法取得其历史控制台输出（不取得停止权限）")
            return status
        if status["state"] != "stopped":
            raise RuntimeError(name + "：" + status.get("detail", "端口被未知或未就绪服务占用，请查看原窗口；不会终止它"))
        args, cwd, env = command_for(name, self.settings, role)
        self.log(name + "：工作目录=" + str(cwd) + "；启动参数=" + json.dumps(args, ensure_ascii=False))
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
            status = self.probe(name)
            if status["state"] == "healthy":
                return status
            self.cancel.wait(0.5)
        raise RuntimeError(name + "就绪超时；日志和自有进程仍保留，可点击停止")

    def start_all(self, role_id, voice_id=None):
        with self.mutex:
            self.cancel.clear()
            from services.profile_config import load_combination
            role = (load_combination(role_id, voice_id, Path(self.settings["project_root"])) if voice_id
                    else load_role(role_id, Path(self.settings["project_root"])))
            states = {name: self.probe(name) for name in PORTS}
            for name, state in states.items():
                if state["state"] not in {"stopped", "healthy"}:
                    raise RuntimeError(name + "：" + state.get("detail", "端口已有未知/旧版/不健康服务，请在原窗口处理"))
            self.ensure("ollama", role)
            self.ensure("gpt_sovits", role)
            bridge = self.ensure("bridge", role)["data"]
            active = bridge.get("role") or {}
            if active != role.public() or not bridge.get("voice_ready"):
                self.apply_profiles(role_id, voice_id) if voice_id else self.switch(role_id)
            health = request_json("http://127.0.0.1:8000/health")
            if health.get("warmup") != {"asr": "ok", "llm": "ok"}:
                raise RuntimeError("AI bridge已启动，但ASR/LLM预热未通过：" + str(health.get("warmup")))
            self.log("完整启动就绪；实际音色后端在首次TTS成功后确认（不会自动生成词库音频）")
            return self.health()

    def switch(self, role_id):
        with self.mutex:
            load_role(role_id, Path(self.settings["project_root"]))
            if self.probe("bridge")["state"] != "healthy" or self.probe("gpt_sovits")["state"] != "healthy":
                raise RuntimeError("仅切换需要已运行的新版AI bridge和GPT-SoVITS；请先完整启动")
            result = request_json("http://127.0.0.1:8000/roles/switch/" + role_id, "POST", timeout=780)
            self.log("角色切换成功：" + role_id + "；Ollama和ASR保持运行，短期历史已清空")
            return result

    def health(self):
        result = {name: self.probe(name) for name in PORTS}
        self.log("健康检查：" + " | ".join(name + "=" + item["state"] for name, item in result.items()))
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


    def apply_profiles(self, persona_id, voice_id):
        return self.profile_request("apply/" + persona_id + "/" + voice_id)

    def profile_request(self, route):
        with self.mutex:
            if self.probe("bridge")["state"] != "healthy":
                raise RuntimeError("需要新版AI bridge；请在原窗口停止旧服务后完整启动")
            result = request_json("http://127.0.0.1:8000/profiles/" + route, "POST", timeout=780)
            self.log("配置切换完成：" + route)
            return result

    def test_text(self, kind, text):
        from urllib.parse import urlencode
        import uuid
        if not text.strip() or len(text) > 2000:
            raise ValueError("测试文本需为1～2000字符")
        status = self.probe("bridge")
        if status["state"] != "healthy":
            raise RuntimeError(status.get("detail", "需要当前项目的新版AI bridge，请先完整启动"))
        request_id = "desktop-" + uuid.uuid4().hex[:16]
        started = time.perf_counter()
        if kind == "chain":
            result = request_json("http://127.0.0.1:8000/debug/text-chain?" + urlencode({"text": text}), "POST", timeout=300, request_id=request_id)
        else:
            endpoint = "dialogue" if kind == "dialogue" else "tts"
            result = request_json("http://127.0.0.1:8000/debug/" + endpoint + "?" + urlencode({"text": text}), timeout=300, request_id=request_id)
        result["client_elapsed_ms"] = round((time.perf_counter() - started) * 1000)
        result["request_id"] = request_id
        self.log("[bridge] request_id=" + request_id + " 测试结果：" + json.dumps(result, ensure_ascii=False))
        return result

    def start_training(self):
        if port_open(9874):
            self.log("[training] 9874已占用；请在原终端确认WebUI健康，不重复启动、不取得停止权限")
            return {"地址": "http://127.0.0.1:9874/", "状态": "端口已占用，需在外部浏览器确认"}
        root = Path(self.settings["project_root"])
        script = root / "server/tools/start_manbo_training.ps1"
        if not script.is_file():
            raise FileNotFoundError(str(script))
        # An explicitly visible interactive terminal owns the existing training
        # script. Closing this App must not terminate user-started training jobs.
        subprocess.Popen(["powershell.exe", "-NoProfile", "-NoExit", "-ExecutionPolicy", "Bypass",
                          "-File", str(script), "-GptSovitsRoot", self.settings["gpt_sovits_root"]],
                         cwd=root, creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.log("[training] 已打开可见训练终端；请查看就绪日志后用外部浏览器打开9874。停止请在该终端按Ctrl+C。")
        return {"地址": "http://127.0.0.1:9874/", "状态": "已请求启动，尚未确认就绪；日志在可见终端"}


def playback_path(result, root):
    """Only generated local WAVs served by this project's recordings endpoint."""
    from urllib.parse import urlsplit, unquote
    tts = result.get("tts", result)
    url = urlsplit(tts.get("audio_url", ""))
    if not url.path:
        return None
    path = unquote(url.path)
    if url.scheme or url.netloc or not path.startswith("/recordings/"):
        raise ValueError("拒绝播放非本地生成音频")
    name = path[len("/recordings/"):]
    if not name or "/" in name or "\\" in name or Path(name).suffix.lower() != ".wav":
        raise ValueError("生成音频路径无效")
    folder = (Path(root) / "server/recordings").resolve()
    audio = (folder / name).resolve()
    if audio.parent != folder or not audio.is_file():
        raise ValueError("生成WAV不在本项目recordings目录")
    return audio
