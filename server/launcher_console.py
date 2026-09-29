"""Durable routed logs and an exclusive serial session; no shell execution."""
from datetime import datetime
from pathlib import Path
import re
import threading

SOURCES = ("summary", "ollama", "gpt_sovits", "bridge", "serial", "training")


class ConsoleLogs:
    def __init__(self, directory, emit, max_bytes=2 * 1024 * 1024, clock=datetime.now):
        self.directory = Path(directory)
        self.emit, self.max_bytes, self.clock = emit, max_bytes, clock
        self.lock = threading.Lock()

    def write(self, source, message, request_id=None):
        source = source if source in SOURCES else "summary"
        now = self.clock()
        if request_id is None:
            match = re.search(r"(?:\[服务端\]\[|request_id[=: ]+[\"']?)([A-Za-z0-9_-]+)", message)
            request_id = match.group(1) if match else "-"
        request_id = re.sub(r"[^A-Za-z0-9_-]", "_", str(request_id))[:80]
        lines = str(message).splitlines() or [""]
        with self.lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            for line in lines:
                formatted = f"[{now:%Y-%m-%d %H:%M:%S.%f}][{source}][{request_id}] {line}"
                payload = (formatted + "\n").encode("utf-8")
                for target in ({source, "summary"} if source != "summary" else {"summary"}):
                    stem = f"{now:%Y-%m-%d}-{target}"
                    # Rotate to a new numbered segment; never delete old disk logs.
                    index = 0
                    path = self.directory / (stem + ".log")
                    while path.exists() and path.stat().st_size + len(payload) > self.max_bytes and path.stat().st_size:
                        index += 1
                        path = self.directory / (stem + f".{index:04d}.log")
                    with path.open("ab") as output:
                        output.write(payload)
                self.emit(source, formatted)

    def supervisor(self, line):
        match = re.match(r"\[(ollama|gpt_sovits|bridge|training)\] ?(.*)", line, re.DOTALL)
        if match:
            self.write(match.group(1), match.group(2))
        else:
            source = next((name for name in SOURCES if line.startswith(name + "：")), "summary")
            self.write(source, line)


class SerialConsole:
    def __init__(self, log, factory=None):
        self.log, self.factory = log, factory
        self.port = None
        self.worker = None
        self.stop = threading.Event()
        self.lock = threading.RLock()

    @staticmethod
    def ports():
        from serial.tools import list_ports
        return [(p.device, p.description) for p in list_ports.comports()]

    def connect(self, name, baud=115200):
        with self.lock:
            if self.port is not None:
                raise RuntimeError("已连接串口，请先断开")
            if not re.fullmatch(r"COM[1-9][0-9]*", name, re.IGNORECASE):
                raise ValueError("请选择实际COM端口")
            factory = self.factory
            if factory is None:
                import serial
                factory = serial.Serial
            # Windows pyserial opens an exclusive handle; busy ports raise, never
            # terminate PlatformIO or another application to acquire the port.
            port = factory(port=None, baudrate=baud, timeout=0.25, write_timeout=2)
            try:
                port.dtr = False
                port.rts = False
                port.port = name
                port.open()
            except Exception:
                port.close()
                raise
            self.port = port
            self.stop.clear()
            self.worker = threading.Thread(target=self._read, args=(port,), daemon=True)
            self.worker.start()
            self.log("serial", f"已连接{name}，{baud}；未自动发送命令")

    def _read(self, port):
        try:
            while not self.stop.is_set():
                data = port.readline(8192)
                if data:
                    self.log("serial", data.decode("utf-8", errors="replace").rstrip())
        except Exception as exc:
            if not self.stop.is_set():
                self.log("serial", "读取失败: " + str(exc))
        finally:
            with self.lock:
                port.close()
                if self.port is port:
                    self.port = None

    def send(self, command):
        command = command.strip()
        if not command or len(command.encode("utf-8")) > 240 or any(ord(c) < 32 for c in command):
            raise ValueError("请输入一条不超过240字节的单行串口命令")
        with self.lock:
            if self.port is None:
                raise RuntimeError("串口未连接")
            data = (command + "\n").encode("utf-8")
            if self.port.write(data) != len(data):
                raise IOError("串口写入不完整")
            self.log("serial", "发送: " + command)

    def disconnect(self):
        self.stop.set()
        worker = self.worker
        if worker and worker is not threading.current_thread():
            worker.join(timeout=3)
            if worker.is_alive():
                raise RuntimeError("串口读取尚未退出，请等待后重试")
        with self.lock:
            if self.port is not None:
                self.port.close()
                self.port = None
            self.worker = None
        self.log("serial", "串口已断开")
