import argparse
import shutil
import sys
import wave
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from ai_bridge_server import RECORDINGS_DIR, run_ai_pipeline  # noqa: E402


def ensure_wav(input_path: Path) -> Path:
    if input_path.suffix.lower() == ".wav":
        return input_path

    output_path = RECORDINGS_DIR / f"{input_path.stem}_converted_16000hz.wav"
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        try:
            import imageio_ffmpeg

            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError as exc:
            raise RuntimeError(
                "未找到 ffmpeg，也未安装 imageio-ffmpeg，无法把非 WAV 音频转换为 16kHz WAV。"
            ) from exc

    import subprocess

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-sample_fmt",
        "s16",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_path


def print_wav_info(wav_path: Path) -> None:
    with wave.open(str(wav_path), "rb") as wav_file:
        duration = wav_file.getnframes() / wav_file.getframerate()
        print(f"音频文件: {wav_path}")
        print(f"声道数: {wav_file.getnchannels()}")
        print(f"采样率: {wav_file.getframerate()} Hz")
        print(f"采样宽度: {wav_file.getsampwidth() * 8} bit")
        print(f"时长: {duration:.2f} 秒")


def main() -> None:
    parser = argparse.ArgumentParser(description="测试本地音频文件的 ASR/回复管线")
    parser.add_argument("audio_file", type=Path, help="要测试的音频文件，支持 wav/m4a 等 ffmpeg 可读取格式")
    args = parser.parse_args()

    input_path = args.audio_file.resolve()
    if not input_path.is_file():
        raise FileNotFoundError(input_path)

    wav_path = ensure_wav(input_path)
    print_wav_info(wav_path)
    result = run_ai_pipeline(wav_path)

    print("\n识别与回复结果:")
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
