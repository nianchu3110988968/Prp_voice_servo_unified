"""Visible-terminal, single rl/7 stop test after the user's motion authorization.

Close the launcher's serial connection first. Keep the robot supported and the
previously checked 5V supply/rl wiring unchanged. Never builds or flashes.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys
import time

import serial
from serial.tools import list_ports

ROOT = Path(__file__).resolve().parents[1]
VERSION = "2026-10-11-rl-ack-v1"


class Session:
    def __init__(self, port, log):
        self.port = port
        self.log = log
        self.buffer = bytearray()

    def report(self, text):
        line = f"[{datetime.now().isoformat(timespec='milliseconds')}] {text}"
        print(line, flush=True)
        self.log.write(line + "\n")
        self.log.flush()

    def send(self, command):
        # Every caller below uses a fixed command; no model/user sequence executes.
        self.report("SEND: " + command)
        data = (command + "\n").encode("ascii")
        if self.port.write(data) != len(data):
            raise RuntimeError("Incomplete serial write")

    def line(self, deadline):
        while time.monotonic() < deadline:
            if b"\n" in self.buffer:
                raw, _, tail = self.buffer.partition(b"\n")
                self.buffer = bytearray(tail)
                text = raw.decode("utf-8", errors="replace").rstrip("\r")
                self.report(text)
                return text
            self.buffer.extend(self.port.read(max(1, min(self.port.in_waiting, 4096))))
        return None

    def expect(self, text, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.line(deadline)
            if line is not None and text in line:
                return line
        raise RuntimeError("No fresh acknowledgement: " + text)


def board_ms(line):
    match = re.search(r"\((\d+)\)", line)
    if not match:
        raise RuntimeError("Board timestamp missing; cannot verify mid-motion stop")
    return int(match.group(1))


def run_test(session):
    session.send("status ai bridge")
    version_line = session.expect("Firmware:")
    if f"({VERSION})" not in version_line:
        raise RuntimeError("Unexpected firmware; no motion was requested")
    # Firmware status consists of five lines; do not overlap the next command
    # with its response. This improves transaction pacing, not a root-cause claim.
    session.expect("AI server URL:")
    time.sleep(0.15)
    session.send("end machine control")
    session.expect("servo PWM outputs disabled (FULL OFF)")
    session.expect("Machine control disabled; all servo PWM outputs are off")
    session.send("start motion demo")
    session.expect("单路调试：仅通道7启用，其余15路PWM关闭")
    session.expect("动作演示已启用：仅rl/7，90度保持")
    # Give the observer time to focus on rl before the short 2-degree movement.
    # No angle or motion duration is changed and motion commands are never retried.
    for remaining in (3, 2, 1):
        session.report(f"WATCH rl/channel 7: motion + audio in {remaining}s")
        time.sleep(1)
    session.send("test motion audio")
    started = session.expect("acknowledge started: rl channel=7", timeout=4)
    start_ms = board_ms(started)
    stop_at = time.monotonic() + 0.250
    # Observe during the delay as well: buffered/late start lines cannot earn PASS.
    while time.monotonic() < stop_at:
        line = session.line(stop_at)
        if line and ("acknowledge complete:" in line or "self-test completed:" in line):
            raise RuntimeError("Playback/motion already completed; no mid-motion result")
    session.send("end machine control")
    stop_ms = None
    audio_ms = None
    disabled = False
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        line = session.line(deadline)
        if line is None:
            break
        if "acknowledge complete:" in line:
            raise RuntimeError("Motion completed normally; interruption was not verified")
        if "servo PWM outputs disabled (FULL OFF)" in line:
            stop_ms = board_ms(line)
        if "Machine control disabled; all servo PWM outputs are off" in line:
            disabled = True
        if "Local audio self-test completed:" in line:
            if "completed: ESP_OK" not in line:
                raise RuntimeError("Local audio failed during the stop test")
            audio_ms = board_ms(line)
        if stop_ms is not None and disabled and audio_ms is not None:
            # Listen beyond the normal 900ms end; a late completion is a failure.
            tail_deadline = time.monotonic() + 0.5
            while time.monotonic() < tail_deadline:
                tail = session.line(tail_deadline)
                if tail and "acknowledge complete:" in tail:
                    raise RuntimeError("Old motion resumed/completed after stop")
            break
    if stop_ms is None or not disabled or audio_ms is None:
        raise RuntimeError("Missing PWM-off or audio completion evidence")
    elapsed = stop_ms - start_ms
    if not 0 < elapsed < 900 or not stop_ms < audio_ms:
        raise RuntimeError(f"Stop did not precede motion/audio end (board delta={elapsed}ms)")
    return {"firmware": VERSION, "board_start_ms": start_ms,
            "board_full_off_ms": stop_ms, "stop_after_start_ms": elapsed,
            "board_audio_done_ms": audio_ms, "physical_observation": "pending user feedback"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    args = parser.parse_args()
    port_name = args.port.strip().upper()
    found = next((p for p in list_ports.comports() if p.device.upper() == port_name), None)
    if found is None or (found.vid, found.pid) != (0x1A86, 0x55D3):
        parser.error("Select the currently connected CH343 ESP32 port; no serial port opened")
    folder = ROOT / ".pio" / "motion_stop_test"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    log_path = folder / f"stop_{stamp}.log"
    result = {"port": port_name, "log": str(log_path), "result": "FAIL"}
    with log_path.open("w", encoding="utf-8") as log:
        port = serial.Serial(port=None, baudrate=115200, timeout=0.02, write_timeout=1)
        port.dtr = False
        port.rts = False
        port.port = port_name
        session = Session(port, log)
        try:
            port.open()  # Windows exclusive handle: never evict the launcher's owner.
            port.reset_input_buffer()
            result.update(run_test(session))
            result["result"] = "PASS_SERIAL_EVIDENCE_ONLY"
        except (Exception, KeyboardInterrupt) as exc:
            result["error"] = str(exc) or "Interrupted by user"
            session.report("STOP TEST FAILED: " + result["error"])
        finally:
            if port.is_open:
                try:
                    session.send("end machine control")
                    session.expect("servo PWM outputs disabled (FULL OFF)", timeout=2)
                    result["cleanup_full_off"] = True
                except (Exception, KeyboardInterrupt) as exc:
                    result["result"] = "FAIL"
                    result["cleanup_full_off"] = False
                    result["cleanup_error"] = str(exc)
                    session.report("PWM OFF NOT CONFIRMED: disconnect external servo 5V now")
                finally:
                    port.close()
        session.report(result["result"] + "; serial port released; physical observation still required")
    result_path = log_path.with_suffix(".json")
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Result: {result_path}", flush=True)
    return 0 if result["result"] == "PASS_SERIAL_EVIDENCE_ONLY" else 1


if __name__ == "__main__":
    sys.exit(main())
