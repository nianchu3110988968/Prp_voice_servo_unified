"""Run with python -X utf8 server/launcher_app.py, or the packaged executable."""
from pathlib import Path
import argparse
import json
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from launcher_core import Supervisor, read_settings
from services.role_config import ROOT, load_role, list_roles


class Launcher:
    def __init__(self, window, root):
        self.window, self.root = window, root
        self.events = queue.Queue()
        self.busy = False
        self.closing = False
        self.stop_pending = False
        self.poll_pending = False
        self.settings = read_settings(root)
        self.supervisor = Supervisor(self.settings, lambda line: self.events.put(("log", line)))
        window.title("PRP 多角色服务启动器")
        window.geometry("1080x780")
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="角色配置（仅本地 .local.json）").pack(anchor="w")
        self.role = tk.StringVar(value=self.settings.get("default_role", "New_ManBoo"))
        self.selector = ttk.Combobox(frame, textvariable=self.role, values=list_roles(root), state="readonly")
        self.selector.pack(fill="x", pady=5)
        self.selector.bind("<<ComboboxSelected>>", lambda _: self.preview())
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=5)
        self.actions = []
        for label, action in (("启动全部（完整启动）", lambda rid: self.supervisor.start_all(rid)),
                              ("切换角色（仅切换）", lambda rid: self.supervisor.switch(rid)),
                              ("健康检查", lambda _: self.supervisor.health())):
            button = ttk.Button(buttons, text=label, command=lambda f=action: self.run(f))
            button.pack(side="left", padx=4)
            self.actions.append(button)
        ttk.Button(buttons, text="停止托管服务", command=self.stop).pack(side="left", padx=4)
        self.state = tk.StringVar(value="未启动；选中配置不等于已激活角色")
        ttk.Label(frame, textvariable=self.state, wraplength=1020).pack(anchor="w", pady=5)
        self.details = tk.Text(frame, height=12, wrap="word")
        self.details.pack(fill="x")
        ttk.Label(frame, text="持续服务日志（stdout / stderr）").pack(anchor="w", pady=5)
        area = ttk.Frame(frame)
        area.pack(fill="both", expand=True)
        self.logs = tk.Text(area, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(area, command=self.logs.yview)
        self.logs.configure(yscrollcommand=scroll.set)
        self.logs.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.after(100, self.drain)
        window.after(100, self.preview)
        window.after(3000, self.poll)

    def append(self, line):
        self.logs.configure(state="normal")
        self.logs.insert("end", str(line) + "\n")
        if int(self.logs.index("end-1c").split(".")[0]) > 4000:
            self.logs.delete("1.0", "1000.0")
        self.logs.see("end")
        self.logs.configure(state="disabled")

    def preview(self):
        if self.busy:
            return
        self.run(lambda rid: {"preview": load_role(rid, self.root).public()})

    def run(self, action):
        if self.busy:
            return
        self.busy = True
        role_id = self.role.get()
        for button in self.actions:
            button.configure(state="disabled")
        self.selector.configure(state="disabled")
        self.state.set("正在处理，请查看日志；服务启动和切换可能需要数分钟")
        def work():
            try:
                self.events.put(("result", action(role_id)))
            except Exception as exc:
                self.events.put(("error", str(exc)))
            finally:
                self.events.put(("done", None))
        threading.Thread(target=work, daemon=True).start()

    def stop(self):
        if self.stop_pending:
            return
        self.stop_pending = True
        self._stop_when_idle()

    def _stop_when_idle(self):
        self.supervisor.cancel.set()
        if self.busy:
            self.events.put(("log", "已请求停止，等待当前模型切换/调用结束后停止自有服务"))
            self.window.after(300, self._stop_when_idle)
            return
        self.stop_pending = False
        self.run(lambda _: self.supervisor.stop_owned())

    def close(self):
        self.closing = True
        self.stop()

    def poll(self):
        if not self.busy and not self.closing and not self.poll_pending:
            self.poll_pending = True
            # Display observed backend without synthesizing any audio.
            from launcher_core import probe
            threading.Thread(target=lambda: self.events.put(("observed", probe("bridge"))), daemon=True).start()
        self.window.after(5000, self.poll)

    def drain(self):
        for _ in range(300):
            try:
                kind, data = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.append(data)
            elif kind == "observed":
                self.poll_pending = False
                health = data.get("data", {})
                active = health.get("role") or {}
                actual = health.get("actual_tts", {})
                self.state.set("AI bridge: " + data["state"] + " | 当前角色: " + active.get("display_name", "未确认")
                               + " | 权重: " + ("已确认" if health.get("voice_ready") else "未确认")
                               + " | 实际TTS: " + actual.get("backend", "未测试") + "/" + actual.get("status", "未测试"))
            elif kind == "result":
                if data:
                    self.details.delete("1.0", "end")
                    self.details.insert("end", json.dumps(data, ensure_ascii=False, indent=2))
                self.state.set("操作完成；配置预览不代表服务已激活，实际状态会自动刷新")
            elif kind == "error":
                self.append("错误：" + data)
                self.state.set("操作失败：" + data)
            elif kind == "done":
                self.busy = False
                for button in self.actions:
                    button.configure(state="normal")
                self.selector.configure(state="readonly")
                if self.closing and not self.supervisor.owned:
                    self.window.destroy()
                    return
        self.window.after(100, self.drain)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--smoke-test", action="store_true", help="Open real Tk window then exit without starting services")
    args = parser.parse_args()
    if args.project_root:
        root = args.project_root.resolve()
    elif getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent.parent
    else:
        root = ROOT
    window = tk.Tk()
    try:
        launcher = Launcher(window, root)
    except Exception as exc:
        messagebox.showerror("启动器配置错误", str(exc))
        window.destroy()
        raise SystemExit(1)
    if args.smoke_test:
        window.after(1800, launcher.close)
    window.mainloop()


if __name__ == "__main__":
    main()
