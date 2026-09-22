"""Run from VS Code: ask the already configured AI bridge to prepare its library.

No services are started. TTS uses the running bridge's model/reference settings,
not a second terminal's potentially different environment variables.
"""
import argparse
import sys
import requests


def main():
    parser = argparse.ArgumentParser(description="从已保存Excel生成服务端预制音频（不启动服务）")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be 1..65535")
    url = f"http://127.0.0.1:{args.port}"
    session = requests.Session()
    session.trust_env = False  # Loopback maintenance never goes through a proxy.
    try:
        status = session.get(url + "/config", timeout=5)
        status.raise_for_status()
        settings = status.json()
        if "phrase_workbook" not in settings:
            raise RuntimeError("AI bridge尚未加载词库代码，请在原VS Code终端重启一次8000服务")
        print(f"词库：{settings['phrase_workbook']}", flush=True)
        print(f"当前TTS：{settings['tts_backend']}；请确认正在使用你要的音色。", flush=True)
        print("开始逐条生成，期间不要修改Excel、热切换模型或做演示；不重复启动服务。", flush=True)
        response = session.post(url + "/phrase-library/rebuild",
                                headers={"X-PRP-Maintenance": "phrase-library"}, timeout=(5, 7200))
        if response.status_code != 200:
            raise RuntimeError(f"生成未发布：HTTP {response.status_code} {response.text}")
        result = response.json()
        print(f"完成：{result['examples']}个示例，{result['replies']}份标准回复音频。请逐条试听后演示。", flush=True)
        return 0
    except (requests.RequestException, RuntimeError, KeyError, ValueError) as exc:
        print(f"失败：{exc}。旧音频未删除；修正后再运行，不要同时重复生成。", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
