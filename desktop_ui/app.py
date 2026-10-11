"""PRP 陪伴台. Launch from its own entry point; never launches model services."""
from pathlib import Path
import argparse
import ctypes
import json
import queue
import re
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, font

SOURCE_ROOT = Path(__file__).resolve().parents[1]
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(SOURCE_ROOT / "server"))
    sys.path.insert(0, str(SOURCE_ROOT))
from desktop_ui.backend import Bridge, Device, LogTail, dialogue_event

BG, WHITE, INK, MUTED, GREEN = "#f3f5f1", "#ffffff", "#233c3b", "#687b78", "#2e685b"
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class Companion:
    def __init__(self, window, root, smoke=False):
        self.window, self.root, self.smoke = window, Path(root), smoke
        self.events = queue.Queue()
        self.device = Device(lambda kind, data: self.events.put((kind, data)))
        self.bridge, self.tail = Bridge(root), LogTail(root)
        self.busy = self.closing = False
        self.snapshot = None
        self.observed = 0
        self.device_id = None
        self.status_lines = {}
        self.serial_seen = False
        self.controls = []
        self.last_volume_check = 0
        window.title("PRP 陪伴台 · Companion")
        window.geometry("1120x800")
        window.minsize(740, 540)
        window.configure(bg=BG)
        window.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style(window)
        style.theme_use("clam")
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            font.nametofont(name).configure(family="Microsoft YaHei UI", size=11)
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=INK)
        style.configure("TButton", padding=(12, 8), font=("Microsoft YaHei UI", 11))
        style.configure("Accent.TButton", background=GREEN, foreground=WHITE)
        style.map("Accent.TButton", background=[("disabled", "#d8dfda"), ("active", "#235448")])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(22, 10))
        top = ttk.Frame(window, padding=(24, 18, 24, 12))
        top.pack(fill="x")
        ttk.Label(top, text="PRP 陪伴台", font=("Microsoft YaHei UI", 25, "bold")).pack(side="left")
        ttk.Label(top, text="听见你的话，陪伴每一天", foreground=MUTED).pack(side="left", padx=18)
        self.tabs = ttk.Notebook(window)
        self.tabs.pack(fill="both", expand=True, padx=20)
        self.home = self.scroll_page("陪伴首页")
        self.diag = self.scroll_page("连接与诊断")
        self.service = tk.StringVar(value="电脑服务：尚未查询")
        self.connection = tk.StringVar(value="设备：未连接 · 本窗口没有占用串口")
        self.feedback = tk.StringVar(value="仅连接已有服务；请在原控制台或原 VS Code 终端启动服务。")
        self.persona = tk.StringVar(value="等待服务确认")
        self.voice = tk.StringVar(value="等待服务确认")
        self.interaction = tk.StringVar(value="当前交互状态：未知，尚未收到设备事件")
        self.origin = tk.StringVar(value="仅显示打开本窗口后收到的真实内容")
        self.volume_info = tk.StringVar(value="音量能力未确认，调节暂不可用")
        self.volume_value = tk.DoubleVar(value=0)
        self.requested = tk.StringVar(value="拟设置：—")
        self.bridge_info = tk.StringVar(value="尚未取得服务响应")
        status = self.card(self.home, "连接状态", background="#e1ece5")
        self.label(status, self.connection, size=13)
        self.label(status, self.service)
        self.button_row(status, ("检查电脑服务", self.refresh),
                        ("设备连接设置", lambda: self.tabs.select(1)))
        self.label(status, self.feedback, color=MUTED)
        columns = ttk.Frame(self.home)
        columns.pack(fill="x")
        columns.columnconfigure(0, weight=3, uniform="main")
        columns.columnconfigure(1, weight=2, uniform="main")
        left, right = ttk.Frame(columns), ttk.Frame(columns)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        right.grid(row=0, column=1, sticky="nsew")
        partner = self.card(right, "你的伙伴")
        self.label(partner, self.persona, size=14)
        self.label(partner, self.voice, size=14)
        self.button(partner, "更换人格 / 音色", self.profile_dialog)
        conversation = self.card(left, "最近一次对话")
        self.label(conversation, self.interaction, color=MUTED)
        self.heard = self.text_box(conversation, "你说", 2)
        self.reply = self.text_box(conversation, "伙伴回复", 3)
        self.replace(self.heard, "等待本次连接的真实识别内容")
        self.replace(self.reply, "等待实际回复；不会用示例冒充结果")
        self.label(conversation, self.origin, color=MUTED)
        volume = self.card(right, "设备音量")
        self.label(volume, self.volume_info)
        self.scale = ttk.Scale(volume, from_=0, to=100, variable=self.volume_value,
                               command=lambda v: self.requested.set(f"拟设置：{round(float(v))}%（尚未发送）"))
        self.scale.pack(fill="x", pady=(10, 6))
        self.label(volume, self.requested, color=MUTED)
        self.set_button, self.mute_button = self.button_row(
            volume, ("应用音量", self.set_volume), ("静音", self.mute))
        self.restore_button, self.query_button = self.button_row(
            volume, ("取消静音", self.restore_volume), ("查询音量", self.query_volume))
        self.label(volume, "取消静音恢复上次非零值。静音不会停止舵机。", color=MUTED)
        connection = self.card(self.diag, "设备连接")
        self.port = tk.StringVar()
        self.port_box = ttk.Combobox(connection, textvariable=self.port, state="readonly")
        self.port_box.pack(fill="x", pady=8)
        self.button(connection, "刷新端口", self.refresh_ports)
        self.connect_button = self.button(connection, "连接所选设备", self.connect)
        self.disconnect_button = self.button(connection, "释放本窗口串口", self.disconnect)
        self.label(connection, "只有点击连接才打开串口。若原控制台正在使用，请先在那里断开；不会抢占或结束其进程。", color=MUTED)
        ownership = self.card(self.diag, "服务与关闭权")
        self.label(ownership, "本窗口只连接现有 8000 服务，不启动或停止 Ollama / GPT-SoVITS / bridge。\n服务仍由原启动窗口管理；退出只释放本窗口串口，不发送动作命令。")
        self.label(ownership, self.bridge_info, color=MUTED)
        self.details = self.text_box(ownership, "真实服务响应（路径仅显示在此处）", 9)
        logs = self.card(self.diag, "诊断记录")
        self.log = self.text_box(logs, "本窗口事件；最多保留 200 行，不保存对话录音", 10)
        self.button(logs, "清空本窗口显示", lambda: self.replace(self.log, ""))
        footer = ttk.Frame(window, padding=(22, 8))
        footer.pack(fill="x")
        ttk.Label(footer, text="关闭仅释放自身串口 · 服务由原窗口管理", foreground=MUTED).pack(side="left")
        zoom = ttk.Combobox(footer, values=["100%", "125%", "150%"], state="readonly", width=6)
        zoom.set("100%")
        zoom.pack(side="right")
        zoom.bind("<<ComboboxSelected>>", lambda e: self.zoom(int(zoom.get()[:-1]) / 100))
        self.update_controls()
        window.after(100, self.drain)
        if not smoke:
            window.after(200, self.refresh)
            window.after(1000, self.tick)

    def scroll_page(self, title):
        outer = ttk.Frame(self.tabs)
        self.tabs.add(outer, text=title)
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        content = ttk.Frame(canvas, padding=(4, 6, 12, 10))
        item = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(item, width=e.width))
        # Binding on the toplevel preserves Text/Combobox native wheel handling.
        def wheel(event):
            if str(event.widget).startswith(str(content)) and not isinstance(event.widget, (tk.Text, ttk.Combobox)):
                canvas.yview_scroll(-int(event.delta / 120), "units")
        self.window.bind("<MouseWheel>", wheel, add="+")
        return content

    def card(self, parent, title, background=WHITE):
        box = tk.Frame(parent, bg=background, padx=18, pady=10)
        box.pack(fill="x", pady=(0, 12))
        tk.Label(box, text=title, bg=background, fg=INK, font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w", pady=(0, 8))
        return box

    def label(self, parent, value, size=11, color=INK):
        label = tk.Label(parent, textvariable=value if isinstance(value, tk.Variable) else None,
                         text=value if isinstance(value, str) else "", bg=parent.cget("background"), fg=color,
                         font=("Microsoft YaHei UI", size), anchor="w", justify="left")
        label.pack(fill="x", pady=3)
        label.bind("<Configure>", lambda e: label.configure(wraplength=max(150, e.width - 4)))
        return label

    def button(self, parent, text, command):
        button = ttk.Button(parent, text=text, command=command)
        button.pack(anchor="w", pady=4)
        self.controls.append(button)
        return button

    def button_row(self, parent, *entries):
        row = tk.Frame(parent, bg=parent.cget("background"))
        row.pack(anchor="w", pady=3)
        buttons = []
        for text, command in entries:
            button = ttk.Button(row, text=text, command=command,
                                style="Accent.TButton" if text in {"检查电脑服务", "应用音量"} else "TButton")
            button.pack(side="left", padx=(0, 8))
            self.controls.append(button)
            buttons.append(button)
        return buttons

    def text_box(self, parent, title, height):
        self.label(parent, title, color=MUTED)
        text = tk.Text(parent, height=height, width=1, wrap="word", bg=BG, fg=INK,
                       relief="flat", padx=12, pady=8, font=("Microsoft YaHei UI", 12), state="disabled")
        text.pack(fill="x", pady=(3, 8))
        return text

    @staticmethod
    def replace(widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def log_line(self, line):
        self.log.configure(state="normal")
        self.log.insert("end", time.strftime("%H:%M:%S ") + str(line)[:6000] + "\n")
        if int(self.log.index("end-1c").split(".")[0]) > 200:
            self.log.delete("1.0", "2.0")
        self.log.configure(state="disabled")

    def run(self, title, action, completed):
        if self.busy or self.closing:
            return
        self.busy = True
        self.feedback.set(title + "，请等待实际响应…")
        self.update_controls()
        def work():
            try:
                value = action()
                self.events.put(("done", (completed, value)))
            except Exception as exc:
                self.events.put(("failed", (title, str(exc))))
        threading.Thread(target=work, daemon=True).start()

    def update_controls(self):
        for item in self.controls:
            item.configure(state="disabled" if self.busy or self.closing else "normal")
        connected = self.device.serial.port is not None
        enabled = connected and self.device.volume is not None and not self.busy and not self.closing
        for item in (self.scale, self.set_button, self.mute_button):
            item.configure(state="normal" if enabled else "disabled")
        self.restore_button.configure(state="normal" if enabled and self.device.last_nonzero else "disabled")
        self.query_button.configure(state="normal" if connected and not self.busy else "disabled")
        self.connect_button.configure(state="normal" if not connected and not self.busy else "disabled")
        self.disconnect_button.configure(state="normal" if connected and not self.busy else "disabled")

    def show_snapshot(self, value):
        self.snapshot = value
        config, identity = value["config"], value["health"]["bridge_identity"]
        self.service.set("电脑服务：已收到本项目响应 · " + time.strftime("%H:%M:%S"))
        self.persona.set("当前人格：" + (config.get("persona") or {}).get("display_name", "未确认"))
        self.voice.set("当前音色：" + (config.get("voice") or {}).get("display_name", "未确认")
                       + (" · 服务报告就绪" if config.get("voice_ready") else " · 尚未就绪"))
        self.feedback.set(value["write_block"] or "服务响应已更新；设备连接与播放状态须由设备回执确认。")
        self.bridge_info.set(f"服务 PID：{identity.get('pid', '未知')}；本窗口无关闭权。\n" + (value["write_block"] or "服务源码身份核对通过"))
        self.replace(self.details, json.dumps({"identity": identity, "voice": config.get("voice"),
                     "llm": config.get("llm"), "actual_tts": config.get("actual_tts")}, ensure_ascii=False, indent=2))

    def refresh(self):
        self.run("检查电脑服务", self.bridge.snapshot, self.show_snapshot)

    def refresh_ports(self):
        self.run("枚举串口", self.device.serial.ports,
                 lambda ports: self.port_box.configure(values=[p[0] for p in ports]))

    def connect(self):
        if not self.port.get():
            self.feedback.set("请先刷新端口并选择实际设备")
            return
        self.status_lines, self.device_id = {}, None
        self.volume_info.set("正在查询音量能力…")
        selected_port = self.port.get()
        self.run("连接串口并查询设备", lambda: self.device.connect(selected_port), self.show_volume)

    def disconnect(self):
        self.run("释放本窗口串口", self.device.disconnect, lambda _: self.disconnected())

    def disconnected(self):
        self.device.volume = None
        self.device_id = None
        self.connection.set("设备：未连接 · 本窗口没有占用串口")
        self.interaction.set("当前交互状态：未知（本窗口未连接设备）")
        self.volume_info.set("实际音量未知；下次连接将重新查询")
        self.requested.set("拟设置：—")
        self.feedback.set("已释放本窗口串口；原服务继续由原启动窗口管理")

    def query_volume(self):
        self.last_volume_check = time.monotonic()
        self.run("查询设备音量", self.device.get_volume, self.show_volume)

    def show_volume(self, data):
        self.last_volume_check = time.monotonic()
        self.volume_value.set(data["percent"])
        self.requested.set("拟设置：—")
        self.volume_info.set(f"设备确认：{data['percent']}%" + (" · 静音" if data["muted"] else "")
                             + " · " + time.strftime("%H:%M:%S") + "（软件系数）")
        self.feedback.set("已收到匹配的设备音量回执；实际听感仍以扬声器为准。")

    def set_volume(self, value=None):
        value = round(self.volume_value.get()) if value is None else value
        previous = self.device.volume["percent"] if self.device.volume else "未知"
        self.volume_info.set(f"请求 {value}% · 上次确认 {previous}% · 正在等待设备回执")
        self.run("设置设备音量", lambda: self.device.set_volume(value), self.show_volume)

    def mute(self):
        self.set_volume(0)

    def restore_volume(self):
        if self.device.last_nonzero:
            self.set_volume(self.device.last_nonzero)

    def profile_dialog(self):
        if not self.snapshot or self.snapshot["write_block"]:
            self.feedback.set("请先检查电脑服务；只有身份通过的现有服务可切换配置")
            return
        dialog = tk.Toplevel(self.window)
        dialog.title("更换伙伴配置")
        dialog.transient(self.window)
        dialog.grab_set()
        content = ttk.Frame(dialog, padding=24)
        content.pack(fill="both", expand=True)
        selectors, choices = [], []
        for title, kind in (("人格", "personas"), ("音色", "voices")):
            ttk.Label(content, text=title).pack(anchor="w")
            items = self.bridge.profiles(kind)
            box = ttk.Combobox(content, values=list(items), state="readonly", width=42)
            box.pack(fill="x", pady=8)
            current = self.snapshot["config"].get("persona" if kind == "personas" else "voice") or {}
            box.set(next((label for label, identifier in items.items() if identifier == current.get("id")), ""))
            selectors.append(box)
            choices.append(items)
        ttk.Label(content, text="选择不会立即生效。应用后影响当前共享服务，可能清空短期对话历史。\n音色加载期间请不要在其他窗口同时切换。", wraplength=460).pack(pady=12)
        def apply():
            try:
                p, v = [items[box.get()] for box, items in zip(selectors, choices)]
            except KeyError:
                return
            dialog.destroy()
            self.run("应用人格与音色（等待实际加载）", lambda: self.bridge.apply(p, v), self.show_snapshot)
        ttk.Button(content, text="应用到现有服务", command=apply).pack(fill="x")

    def process_line(self, line, serial=False):
        line = ANSI.sub("", line).strip()
        if serial:
            self.log_line(line)
            if line.startswith("发送:"):
                return
            if "已连接" in line:
                self.connection.set("串口已打开；等待设备状态回执")
            for key in ("Firmware", "Wi-Fi status", "AI bridge ready", "AI server URL"):
                if key + ": " in line:
                    self.status_lines[key] = line.split(key + ": ", 1)[1]
            if "AI server URL: " in line and all(k in self.status_lines for k in ("Firmware", "Wi-Fi status", "AI bridge ready")):
                self.connection.set("设备已回执 · Wi-Fi " + self.status_lines["Wi-Fi status"]
                                    + " · bridge ready=" + self.status_lines["AI bridge ready"] + " · " + time.strftime("%H:%M:%S"))
            match = re.search(r"\[(esp-[A-Za-z0-9_-]+)\] (?:【词库命中】)?(识别|回复)：(.*)$", line)
            if match:
                if self.device_id != match[1]:
                    self.device_id = match[1]
                    self.replace(self.heard, "本轮识别待回执")
                    self.replace(self.reply, "本轮回复待回执")
                self.replace(self.heard if match[2] == "识别" else self.reply, match[3])
                self.origin.set("设备串口 · " + match[1] + " · " + time.strftime("%H:%M:%S") + "（文本回执不等于已播放）")
                self.observed = time.monotonic()
                self.interaction.set("最近设备事件：已收到" + match[2] + "文本")
            trace = re.search(r"\[(esp-[A-Za-z0-9_-]+)\] (.*)$", line)
            if trace:
                stages = (("开始监听=", "正在监听（含等待开口）"),
                          ("录音结束=", "录音完成，等待服务回复"),
                          ("播放开始=", "设备开始播放（软件事件）"),
                          ("播放结束=", "设备播放结束（软件事件）"),
                          ("本轮结果=", "本轮结果：" + trace[2].split(" | ", 1)[0].removeprefix("本轮结果=")))
                for marker, title in stages:
                    if marker in trace[2] and "后台（不播放）" not in trace[2]:
                        self.observed = time.monotonic()
                        self.interaction.set("最近设备事件：" + title + " · " + time.strftime("%H:%M:%S"))
                        break
            if "读取失败:" in line:
                self.device.volume = None
                self.connection.set("设备连接中断；请检查连接后重连")
                self.volume_info.set("连接中断，实际音量未知")
        else:
            event = dialogue_event(line)
            if event and self.device.serial.port is None:
                self.replace(self.heard, event["heard"])
                self.replace(self.reply, event["reply"])
                self.origin.set(event["source"] + " · " + event["id"] + " · " + time.strftime("%H:%M:%S"))
                self.interaction.set("服务已产生回复；设备当前交互状态未知")

    def drain(self):
        try:
            for _ in range(300):
                kind, data = self.events.get_nowait()
                if kind == "done":
                    callback, value = data
                    self.busy = False
                    callback(value)
                elif kind == "failed":
                    self.busy = False
                    title, error = data
                    self.feedback.set(title + "未确认：" + error)
                    self.log_line(title + ": " + error)
                    if title == "检查电脑服务":
                        self.snapshot = None
                        self.service.set("电脑服务：不可用或身份未确认；请检查原启动窗口")
                        self.persona.set("当前人格：未确认（服务未响应）")
                        self.voice.set("当前音色：未确认（服务未响应）")
                    if "音量" in title or "串口并查询" in title:
                        self.volume_info.set("本次操作未确认：" + error)
                elif kind == "serial":
                    self.process_line(data, serial=True)
                elif kind == "volume_observed":
                    self.show_volume(data)
                    self.volume_info.set(self.volume_info.get() + " · 来自超时后独立查询，原设置未确认")
        except queue.Empty:
            pass
        self.update_controls()
        if self.closing and not self.busy:
            try:
                self.device.disconnect()
            except Exception as exc:
                self.closing = False
                self.feedback.set("串口尚未释放，窗口保持打开：" + str(exc))
            else:
                self.window.destroy()
                return
        self.window.after(100, self.drain)

    def tick(self):
        if self.closing:
            return
        try:
            for line in self.tail.read():
                self.process_line(line)
        except OSError as exc:
            self.log_line("服务日志暂不可读：" + str(exc))
        connected = self.device.serial.port is not None
        if self.serial_seen and not connected:
            self.disconnected()
        self.serial_seen = connected
        if self.observed and time.monotonic() - self.observed > 15:
            self.interaction.set("最近事件已超过 15 秒；当前交互状态未知")
        if not self.busy:
            if connected and self.device.volume and time.monotonic() - self.last_volume_check > 15:
                self.query_volume()
            elif int(time.monotonic()) % 5 == 0:
                self.refresh()
        self.window.after(1000, self.tick)

    def zoom(self, factor):
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            font.nametofont(name).configure(size=round(11 * factor))
        def walk(widget):
            for child in widget.winfo_children():
                if isinstance(child, (tk.Label, tk.Text)):
                    current = font.Font(font=child.cget("font"))
                    base = getattr(child, "_base_font_size", current.actual("size"))
                    child._base_font_size = base
                    child.configure(font=("Microsoft YaHei UI", round(base * factor), current.actual("weight")))
                walk(child)
        walk(self.window)

    def close(self):
        if self.busy:
            messagebox.showinfo("请求仍在进行", "请等待当前请求返回或超时后再退出。关闭界面不会撤销服务端已收到的操作。", parent=self.window)
            return
        self.closing = True
        self.feedback.set("正在释放本窗口串口…")
        self.update_controls()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, help="Optional when EXE stays in project dist/PRPCompanion")
    parser.add_argument("--smoke-test", action="store_true", help="Visible offline window; no HTTP, serial or model service calls")
    args = parser.parse_args()
    if args.project_root is None:
        args.project_root = Path(sys.executable).resolve().parents[2] if getattr(sys, "frozen", False) else SOURCE_ROOT
    if not (args.project_root / "server/launcher_console.py").is_file():
        notice = tk.Tk()
        notice.withdraw()
        messagebox.showerror("找不到项目资源", "请将陪伴台保留在工程 dist/PRPCompanion 目录，或使用启动脚本指定正确工程根目录。", parent=notice)
        notice.destroy()
        raise SystemExit("项目根目录无效")
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    window = tk.Tk()
    app = Companion(window, args.project_root, args.smoke_test)
    callback_errors = []
    def callback_exception(kind, value, traceback):
        import traceback as trace_module
        callback_errors.append(str(value))
        trace_module.print_exception(kind, value, traceback)
        app.feedback.set("界面内部错误，请保存终端日志：" + str(value))
    window.report_callback_exception = callback_exception
    if args.smoke_test:
        # This is a real visible offline window. It proves no hardware behavior.
        window.after(1500, lambda: app.zoom(1.25))
        window.after(3000, lambda: (app.zoom(1.5), window.geometry("800x600")))
        window.after(4500, lambda: app.tabs.select(1))
        window.after(6000, app.close)
    window.mainloop()
    if callback_errors:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
