"""Visible desktop control surface; no service is started by opening the App."""
from pathlib import Path
import argparse
import json
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from launcher_core import Supervisor, read_settings, probe
from launcher_console import ConsoleLogs, SerialConsole
from launcher_imports import show_import
from services.role_config import ROOT
from services.profile_config import list_profiles, load_combination, migrate_legacy


class Launcher:
    def __init__(self, window, root, smoke=False):
        self.window, self.root, self.smoke = window, Path(root), smoke
        self.events = queue.Queue()
        self.busy = self.closing = self.stop_pending = self.poll_pending = False
        self.audio_path = None
        self.destroyed = False
        self.settings = read_settings(root)
        self.logbook = ConsoleLogs(self.root / "server/logs/launcher", lambda s, line: self.events.put(("log", (s, line))))
        self.supervisor = Supervisor(self.settings, self.logbook.supervisor)
        self.serial = SerialConsole(self.logbook.write)
        window.title("PRP 人格 · 音色 · 项目控制台")
        window.geometry("1180x900")
        frame = ttk.Frame(window, padding=10)
        frame.pack(fill="both", expand=True)
        self.state = tk.StringVar(value="服务端实际激活：未确认；下拉框仅表示选择")
        ttk.Label(frame, textvariable=self.state, wraplength=1130).pack(anchor="w")
        pages = ttk.Notebook(frame)
        pages.pack(fill="x", pady=6)
        controls, tests, training = [ttk.Frame(pages, padding=8) for _ in range(3)]
        for page, title in ((controls, "人格与音色"), (tests, "交互测试"), (training, "音色训练")):
            pages.add(page, text=title)
        self.persona = tk.StringVar(value=self.settings.get("default_persona", self.settings.get("default_role", "New_ManBoo")))
        self.voice = tk.StringVar(value=self.settings.get("default_voice", self.settings.get("default_role", "New_ManBoo")))
        self.selectors = []
        self.actions = []
        for label, variable, kind in (("已选择人格提示词", self.persona, "persona"), ("已选择GPT-SoVITS音色", self.voice, "voice")):
            row = ttk.Frame(controls)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=label, width=25).pack(side="left")
            selector = ttk.Combobox(row, textvariable=variable, state="readonly", width=40)
            selector.pack(side="left", fill="x", expand=True)
            self.selectors.append(selector)
            self.button(row, "新建/导入人格" if kind == "persona" else "导入音色", lambda k=kind: show_import(self, k))
        row = ttk.Frame(controls)
        row.pack(fill="x", pady=5)
        for label, action in (("完整启动", self.start), ("切换人格", self.switch_persona), ("切换音色", self.switch_voice),
                              ("应用组合", self.apply), ("验证选择/显示路径", self.preview),
                              ("健康检查", lambda: self.run(self.supervisor.health))):
            self.button(row, label, action)
        ttk.Button(row, text="停止托管服务", command=self.stop).pack(side="left", padx=3)
        self.details = self.text_area(controls, 8)
        ttk.Label(tests, text="使用服务端实际激活的人格/音色；试听只在电脑播放，不发送给ESP32。").pack(anchor="w")
        self.input = tk.Text(tests, height=3, wrap="word")
        self.input.pack(fill="x")
        self.input.insert("1.0", "你好，今天过得怎么样？")
        row = ttk.Frame(tests)
        row.pack(fill="x")
        for label, kind in (("人格对话测试", "dialogue"), ("音色试听（生成）", "tts"), ("完整文字链路测试", "chain")):
            self.button(row, label, lambda k=kind: self.test(k))
        ttk.Button(row, text="电脑播放结果", command=self.play).pack(side="left", padx=3)
        ttk.Button(row, text="停止播放", command=self.stop_audio).pack(side="left", padx=3)
        self.test_output = self.text_area(tests, 8)
        ttk.Label(training, text="训练准备：有授权的素材 → 3～10秒切片 → 逐句标注 → 格式化 → SoVITS训练 → GPT训练。\n训练完成后导入成对.ckpt/.pth、参考WAV与逐字原文。这里不会自动训练、覆盖数据或清理模型。\nWebUI地址：http://127.0.0.1:9874/；使用系统外部浏览器。训练日志在新开的可见终端。", wraplength=1100).pack(anchor="w", pady=12)
        row = ttk.Frame(training)
        row.pack(fill="x")
        self.button(row, "启动训练WebUI（可见终端）", lambda: self.run(self.supervisor.start_training))
        ttk.Button(row, text="外部浏览器打开9874", command=self.open_training).pack(side="left", padx=3)
        ttk.Button(row, text="打开数据目录", command=lambda: self.open_path(self.root / "voice_data/manbo")).pack(side="left", padx=3)
        ttk.Button(row, text="打开训练教学", command=lambda: self.open_path(self.root / "docs/项目指南/GPT-SoVITS网页训练教学.md")).pack(side="left", padx=3)
        self.button(row, "导入训练结果", lambda: show_import(self, "voice"))
        serial_row = ttk.LabelFrame(frame, text="ESP32串口（独占；先退出PlatformIO监视器）", padding=5)
        serial_row.pack(fill="x")
        self.com = tk.StringVar()
        self.com_selector = ttk.Combobox(serial_row, textvariable=self.com, state="readonly", width=12)
        self.com_selector.pack(side="left")
        self.button(serial_row, "刷新COM", self.refresh_ports)
        self.button(serial_row, "连接115200", self.connect_serial)
        self.button(serial_row, "断开", lambda: self.run(self.serial.disconnect))
        self.serial_state = tk.StringVar(value="未连接")
        ttk.Label(serial_row, textvariable=self.serial_state).pack(side="left")
        self.command = tk.StringVar()
        ttk.Entry(serial_row, textvariable=self.command).pack(side="left", fill="x", expand=True)
        self.button(serial_row, "发送文本", lambda: self.send_serial(self.command.get()))
        row = ttk.Frame(frame)
        row.pack(fill="x")
        for command in ("status ai bridge", "test audio", "retry wifi", "start machine control", "end machine control"):
            self.button(row, command, lambda c=command: self.send_serial(c))
        log_row = ttk.Frame(frame)
        log_row.pack(fill="x", pady=4)
        ttk.Label(log_row, text="控制台：本机时间 / 来源 / 请求ID；新日志不自动滚动；磁盘日志保留").pack(side="left")
        ttk.Button(log_row, text="清空当前显示（保留文件）", command=self.clear_logs).pack(side="right")
        self.log_tabs = ttk.Notebook(frame)
        self.log_tabs.pack(fill="both", expand=True)
        self.log_widgets = {}
        for source, label in (("summary", "汇总"), ("ollama", "Ollama"), ("gpt_sovits", "GPT-SoVITS"), ("bridge", "AI bridge"), ("serial", "ESP32串口")):
            page = ttk.Frame(self.log_tabs)
            self.log_tabs.add(page, text=label)
            self.log_widgets[source] = self.text_area(page, 12)
        self.refresh_profiles()
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.after(100, self.drain)
        if not smoke:
            window.after(200, self.initialize)
            window.after(3000, self.poll)

    def text_area(self, parent, height):
        row = ttk.Frame(parent)
        row.pack(fill="both", expand=True)
        text = tk.Text(row, height=height, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(row, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        return text

    def button(self, parent, label, action):
        button = ttk.Button(parent, text=label, command=action)
        button.pack(side="left", padx=3, pady=3)
        self.actions.append(button)

    def initialize(self):
        def work():
            if not list_profiles("personas", self.root) or not list_profiles("voices", self.root):
                migrate_legacy(self.settings.get("default_role", "New_ManBoo"), self.root)
            return {"提示": "选择与激活分开；点击验证选择查看完整路径和自动哈希检查结果"}
        self.run(work, lambda result: (self.refresh_profiles(), self.show_result(result)))

    def refresh_profiles(self):
        for selector, kind in zip(self.selectors, ("personas", "voices")):
            selector.configure(values=list_profiles(kind, self.root))

    def start(self):
        p, v = self.persona.get(), self.voice.get()
        self.run(lambda: self.supervisor.start_all(p, v))

    def switch_persona(self):
        p = self.persona.get()
        self.run(lambda: self.supervisor.profile_request("persona/" + p))

    def switch_voice(self):
        v = self.voice.get()
        self.run(lambda: self.supervisor.profile_request("voice/" + v))

    def apply(self):
        p, v = self.persona.get(), self.voice.get()
        self.run(lambda: self.supervisor.apply_profiles(p, v))

    def preview(self):
        p, v = self.persona.get(), self.voice.get()
        self.run(lambda: {"已选择并验证（不代表激活）": load_combination(p, v, self.root).public()})

    def show_result(self, result, widget=None):
        widget = widget or self.details
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", json.dumps(result, ensure_ascii=False, indent=2))
        widget.configure(state="disabled")

    def append(self, source, line):
        for name in ({source, "summary"} if source in self.log_widgets else {"summary"}):
            text = self.log_widgets[name]
            text.configure(state="normal")
            text.insert("end", line + "\n")
            if int(text.index("end-1c").split(".")[0]) > 4000:
                text.delete("1.0", "1000.0")
            # Do not call see('end'): incoming logs must not move the reading position.
            text.configure(state="disabled")

    def clear_logs(self):
        widget = list(self.log_widgets.values())[self.log_tabs.index("current")]
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.configure(state="disabled")

    def run(self, action, completed=None):
        if self.busy or (self.closing and not self.stop_pending):
            return
        self.busy = True
        for widget in self.actions + self.selectors:
            widget.configure(state="disabled")
        def work():
            try:
                self.events.put(("result", (action(), completed)))
            except Exception as exc:
                self.events.put(("error", str(exc)))
            finally:
                self.events.put(("done", None))
        threading.Thread(target=work, daemon=True).start()

    def error(self, message):
        self.logbook.write("summary", "错误：" + message)
        messagebox.showerror("操作失败", message, parent=self.window)

    def stop(self):
        if self.stop_pending:
            return
        self.stop_pending = True
        self.supervisor.cancel.set()
        self._stop_when_idle()

    def _stop_when_idle(self):
        if self.busy:
            self.window.after(300, self._stop_when_idle)
            return
        def work():
            self.supervisor.stop_owned()
            if self.closing:
                self.serial.disconnect()
            return {"停止": "仅停止本App持有的服务进程；外部服务与训练终端保持运行"}
        self.run(work, self._stopped)

    def _stopped(self, result):
        self.stop_pending = False
        self.show_result(result)
        if self.closing:
            self.stop_audio()
            self.destroyed = True
            self.window.destroy()

    def close(self):
        if self.closing:
            return
        self.closing = True
        self.stop()

    def poll(self):
        if not self.busy and not self.closing and not self.poll_pending:
            self.poll_pending = True
            threading.Thread(target=lambda: self.events.put(("observed", probe("bridge"))), daemon=True).start()
        if not self.closing:
            self.window.after(5000, self.poll)

    def drain(self):
        for _ in range(300):
            try:
                kind, data = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.append(*data)
            elif kind == "observed":
                self.poll_pending = False
                health = data.get("data", {})
                persona, voice = health.get("persona") or {}, health.get("voice") or {}
                actual = health.get("actual_tts") or {}
                self.state.set("服务端实际激活 | " + data["state"] + " | 人格: " + persona.get("id", "未确认") + " | 音色: " + voice.get("id", "未确认") + " | 权重: " + ("就绪" if health.get("voice_ready") else "未确认") + " | 实际TTS: " + actual.get("backend", "未测试") + "/" + actual.get("status", "未测试"))
            elif kind == "result":
                result, callback = data
                try:
                    if callback:
                        callback(result)
                    elif result is not None:
                        self.show_result(result)
                except Exception as exc:
                    self.error(str(exc))
                if self.destroyed:
                    return
            elif kind == "error":
                self.closing = self.stop_pending = False
                self.error(data)
            elif kind == "done":
                self.busy = False
                for widget in self.actions:
                    widget.configure(state="normal")
                for widget in self.selectors:
                    widget.configure(state="readonly")
        serial_port = self.serial.port
        self.serial_state.set("已连接 " + str(serial_port.port) if serial_port else "未连接")
        self.window.after(100, self.drain)

    def refresh_ports(self):
        def completed(ports):
            self.com_selector.configure(values=[p[0] for p in ports])
            self.show_result({"串口": ports})
        self.run(self.serial.ports, completed)

    def connect_serial(self):
        port = self.com.get()
        self.run(lambda: self.serial.connect(port))

    def send_serial(self, command):
        self.run(lambda: self.serial.send(command))

    def test(self, kind):
        text = self.input.get("1.0", "end").strip()
        self.audio_path = None
        def completed(result):
            from launcher_core import playback_path
            self.audio_path = playback_path(result, self.root)
            if self.audio_path:
                result["本地生成文件"] = str(self.audio_path)
            self.show_result(result, self.test_output)
        self.run(lambda: self.supervisor.test_text(kind, text), completed)

    def play(self):
        try:
            if not self.audio_path:
                raise ValueError("尚无成功生成的本地WAV，请先运行音色试听或完整文字链路测试")
            import winsound
            winsound.PlaySound(str(self.audio_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception as exc:
            self.error(str(exc))

    def stop_audio(self):
        if os.name == "nt":
            import winsound
            winsound.PlaySound(None, 0)

    def open_path(self, path):
        try:
            if not path.exists():
                raise FileNotFoundError(str(path))
            os.startfile(str(path))
        except Exception as exc:
            self.error(str(exc))

    def open_training(self):
        import webbrowser
        webbrowser.open("http://127.0.0.1:9874/", new=0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args()
    root = args.project_root.resolve() if args.project_root else (Path(sys.executable).resolve().parent.parent if getattr(sys, "frozen", False) else ROOT)
    window = tk.Tk()
    try:
        launcher = Launcher(window, root, smoke=args.smoke_test)
    except Exception as exc:
        messagebox.showerror("启动器配置错误", str(exc))
        window.destroy()
        raise SystemExit(1)
    if args.smoke_test:
        window.after(1800, launcher.close)
    window.mainloop()


if __name__ == "__main__":
    main()
