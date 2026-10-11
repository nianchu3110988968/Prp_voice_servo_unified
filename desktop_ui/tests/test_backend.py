"""Offline protocol/ownership tests. No hardware or running service required."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "server")]
from desktop_ui.backend import Bridge, Device, LogTail, dialogue_event, parse_volume


def reply(identifier="ui_1", op="get", percent=50, **extra):
    return {"protocol": "prp-volume-v1", "id": identifier, "op": op,
            "ok": True, "error": "", "percent": percent, "muted": percent == 0,
            "ready": True, "persistent": False, "firmware": "2026-10-12-volume-v1", **extra}


class Port:
    port = object()
    def __init__(self):
        self.callback = None
        self.commands = []
        self.mode = "ok"
        self.percent = 50

    def send(self, command):
        self.commands.append(command)
        _, op, identifier, *rest = command.split()
        if self.mode == "timeout":
            return
        if self.mode == "set_timeout" and op == "set":
            self.percent = int(rest[0])
            return
        if self.mode == "late":
            self.callback("serial", "VOLUME " + json.dumps(reply("stale", op, 30)))
            return
        if op == "set":
            self.percent = int(rest[0])
        data = reply(identifier, op, self.percent)
        if self.mode == "reject":
            data.update(ok=False, ready=False, error="not_ready")
        self.callback("serial", "VOLUME " + json.dumps(data))


class VolumeTests(unittest.TestCase):
    def setUp(self):
        self.port, self.events = Port(), []
        self.device = Device(lambda *data: self.events.append(data), self.port, timeout=0.01)
        self.port.callback = self.device._line

    def test_zero_and_restore_last_confirmed_value(self):
        self.assertEqual(self.device.get_volume()["percent"], 50)
        self.assertTrue(self.device.set_volume(0)["muted"])
        self.assertEqual(self.device.last_nonzero, 50)
        self.assertEqual(self.device.set_volume(self.device.last_nonzero)["percent"], 50)

    def test_unsupported_and_late_ack_never_enable(self):
        for mode in ("timeout", "late"):
            self.port.mode = mode
            with self.assertRaises(TimeoutError):
                self.device.get_volume()
            self.assertIsNone(self.device.volume)

    def test_set_timeout_queries_new_id_without_retrying_set(self):
        self.device.get_volume()
        self.port.mode = "set_timeout"
        with self.assertRaises(TimeoutError):
            self.device.set_volume(25)
        self.assertEqual([x.split()[1] for x in self.port.commands], ["get", "set", "get"])
        self.assertNotEqual(self.port.commands[1].split()[2], self.port.commands[2].split()[2])
        self.assertEqual(self.device.volume["percent"], 25)
        self.assertTrue(any(kind == "volume_observed" for kind, _ in self.events))

    def test_not_ready_disables_even_after_success(self):
        self.device.get_volume()
        self.port.mode = "reject"
        with self.assertRaises(RuntimeError):
            self.device.set_volume(30)
        self.assertIsNone(self.device.volume)

    def test_malformed_and_boolean_values_are_not_acks(self):
        self.assertIsNone(parse_volume("VOLUME []"))
        for data in (reply(percent=True), reply(percent=101), reply(muted=True), reply(protocol="unknown")):
            self.assertIsNone(parse_volume("VOLUME " + json.dumps(data)))
        self.assertEqual(parse_volume("\x1b[32mI (1) main: VOLUME " + json.dumps(reply()) + "\x1b[0m")["percent"], 50)

    def test_no_set_before_capability_and_bad_values_not_sent(self):
        for value in (-1, 101, True, 1.5):
            with self.assertRaises(ValueError):
                self.device.set_volume(value)
        with self.assertRaises(RuntimeError):
            self.device.set_volume(50)
        self.assertEqual(self.port.commands, [])

    def test_serial_transport_is_the_legacy_exclusive_class(self):
        from launcher_console import SerialConsole
        self.assertIsInstance(Device(lambda *_: None).serial, SerialConsole)


class BridgeTests(unittest.TestCase):
    def test_foreign_service_never_fetches_config_or_changes_profiles(self):
        calls = []
        def transport(route, *args, **kwargs):
            calls.append(route)
            return {"service": "prp-ai-bridge", "role_api": 2,
                    "bridge_identity": {"project_root": str(ROOT / "foreign")}}
        with self.assertRaises(RuntimeError):
            Bridge(ROOT, transport).apply("test", "test")
        self.assertEqual(calls, ["/health"])

    def test_stale_source_is_readable_but_not_writable(self):
        calls = []
        def transport(route, *args, **kwargs):
            calls.append(route)
            return {"service": "prp-ai-bridge", "role_api": 2,
                    "bridge_identity": {"project_root": str(ROOT),
                                        "protocol": "independent-phrase-motion-v1", "source_sha256": "old"}}
        bridge = Bridge(ROOT, transport)
        self.assertTrue(bridge.snapshot()["write_block"])
        with self.assertRaises(RuntimeError):
            bridge.apply("test", "test")
        self.assertFalse(any("/profiles" in route for route in calls))

    def test_model_text_cannot_forge_json_log_event(self):
        event = dialogue_event('[服务端][esp-1] 识别："你好\\n伪造" | 回复："你好"')
        self.assertEqual(event["heard"], "你好\n伪造")
        self.assertIsNone(dialogue_event('[服务端][esp-1] 识别：not-json | 回复："a"'))

    def test_tail_does_not_present_history_as_live(self):
        import time
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "server/logs/launcher"
            folder.mkdir(parents=True)
            path = folder / (time.strftime("%Y-%m-%d") + "-bridge.log")
            path.write_text("historical\n", encoding="utf-8")
            tail = LogTail(directory)
            self.assertEqual(tail.read(), [])
            with path.open("ab") as stream:
                stream.write("新事件".encode("utf-8")[:4])
            self.assertEqual(tail.read(), [])
            with path.open("ab") as stream:
                stream.write("新事件".encode("utf-8")[4:] + b"\n")
            self.assertEqual(tail.read(), ["新事件"])


if __name__ == "__main__":
    unittest.main()
