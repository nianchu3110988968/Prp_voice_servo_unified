"""Compatibility foreground service entry; intended for the user's visible terminal."""
from pathlib import Path
import argparse
import os
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from launcher_core import read_settings, command_for, probe
from services.role_config import ROOT, load_role


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("service", choices=["gpt_sovits", "bridge"])
    parser.add_argument("--role", default="New_ManBoo")
    parser.add_argument("--gpt-sovits-root")
    args = parser.parse_args()
    settings = read_settings()
    if args.gpt_sovits_root:
        settings["gpt_sovits_root"] = args.gpt_sovits_root
    role = load_role(args.role)
    state = probe(args.service)
    if state["state"] == "healthy":
        print("复用现有健康服务；切换角色请用启动器。")
        return
    if state["state"] != "stopped":
        raise SystemExit("端口已有未知/旧版/不健康进程；请在原窗口处理，不重复启动。")
    command, cwd, env = command_for(args.service, settings, role)
    # Inherit the visible PowerShell terminal. No detached/background process.
    child = subprocess.Popen(command, cwd=cwd, env=env)
    try:
        raise SystemExit(child.wait())
    except KeyboardInterrupt:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=15)


if __name__ == "__main__":
    main()
