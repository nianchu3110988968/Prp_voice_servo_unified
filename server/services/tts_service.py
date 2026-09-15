from datetime import datetime
from io import BytesIO
from pathlib import Path
import subprocess
import tempfile
import wave

import requests

from server_config import (
    GPT_SOVITS_PROMPT_LANGUAGE,
    GPT_SOVITS_PROMPT_TEXT,
    GPT_SOVITS_REFERENCE_WAV,
    GPT_SOVITS_TEXT_LANGUAGE,
    GPT_SOVITS_TIMEOUT_SECONDS,
    GPT_SOVITS_URL,
    TTS_BACKEND,
    TTS_FALLBACK_TO_SAPI,
)


def synthesize_reply(reply_text: str, output_dir: Path) -> dict:
    """Synthesize speech through the configured backend and return a common result."""
    if not reply_text.strip():
        return {
            "audio_url": "",
            "status": "skipped_empty_text",
            "backend": "windows_sapi",
            "detail": "",
        }

    output_dir.mkdir(exist_ok=True)
    if TTS_BACKEND == "gpt_sovits":
        result = _synthesize_gpt_sovits(reply_text, output_dir)
        if result["status"] == "ok" or not TTS_FALLBACK_TO_SAPI:
            return result
        fallback = _synthesize_windows_sapi(reply_text, output_dir)
        fallback["backend"] = "gpt_sovits_fallback_windows_sapi"
        fallback["detail"] = f"GPT-SoVITS: {result['detail']}; SAPI: {fallback['detail']}"
        return fallback
    return _synthesize_windows_sapi(reply_text, output_dir)


def _synthesize_windows_sapi(reply_text: str, output_dir: Path) -> dict:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    wav_path = output_dir / f"reply_{timestamp}_16000hz.wav"

    with tempfile.TemporaryDirectory() as tmp_dir:
        text_path = Path(tmp_dir) / "reply_text.txt"
        script_path = Path(tmp_dir) / "synthesize_sapi.ps1"
        text_path.write_text(reply_text, encoding="utf-8")
        script_path.write_text(
            f"""
Add-Type -AssemblyName System.Speech
$text = Get-Content -LiteralPath '{_ps_escape(text_path)}' -Raw -Encoding UTF8
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice = $synth.GetInstalledVoices() | Where-Object {{ $_.VoiceInfo.Culture.Name -like 'zh-*' }} | Select-Object -First 1
if ($voice -ne $null) {{
    $synth.SelectVoice($voice.VoiceInfo.Name)
}}
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(
    16000,
    [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
    [System.Speech.AudioFormat.AudioChannel]::Mono
)
$synth.Rate = -1
$synth.Volume = 90
$synth.SetOutputToWaveFile('{_ps_escape(wav_path)}', $format)
$synth.Speak($text)
$synth.Dispose()
""".strip(),
            encoding="utf-8",
        )

        try:
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script_path),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            return {
                "audio_url": "",
                "status": "failed",
                "backend": "windows_sapi",
                "detail": str(exc),
            }

    if not wav_path.is_file() or wav_path.stat().st_size == 0:
        return {
            "audio_url": "",
            "status": "empty_output",
            "backend": "windows_sapi",
            "detail": str(wav_path),
        }

    return {
        "audio_url": f"/recordings/{wav_path.name}",
        "status": "ok",
        "backend": "windows_sapi",
        "detail": wav_path.name,
    }


def _synthesize_gpt_sovits(reply_text: str, output_dir: Path) -> dict:
    if not GPT_SOVITS_REFERENCE_WAV:
        return {"audio_url": "", "status": "not_configured", "backend": "gpt_sovits", "detail": "PRP_GPT_SOVITS_REFERENCE_WAV is empty"}
    reference_path = Path(GPT_SOVITS_REFERENCE_WAV)
    if not reference_path.is_file():
        return {"audio_url": "", "status": "not_configured", "backend": "gpt_sovits", "detail": f"reference wav not found: {reference_path}"}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    wav_path = output_dir / f"reply_{timestamp}_16000hz.wav"
    params = {
        "text": reply_text,
        "text_lang": _gpt_sovits_language_code(GPT_SOVITS_TEXT_LANGUAGE),
        "ref_audio_path": str(reference_path),
        "prompt_text": GPT_SOVITS_PROMPT_TEXT,
        "prompt_lang": _gpt_sovits_language_code(GPT_SOVITS_PROMPT_LANGUAGE),
        "media_type": "wav",
        "streaming_mode": "false",
    }
    try:
        response = requests.get(GPT_SOVITS_URL, params=params, timeout=GPT_SOVITS_TIMEOUT_SECONDS)
        response.raise_for_status()
        _normalize_wav_bytes(response.content, wav_path)
    except (requests.RequestException, OSError, ValueError, wave.Error) as exc:
        return {"audio_url": "", "status": "failed", "backend": "gpt_sovits", "detail": str(exc)}

    if not wav_path.is_file() or wav_path.stat().st_size == 0:
        return {"audio_url": "", "status": "empty_output", "backend": "gpt_sovits", "detail": str(wav_path)}
    return {"audio_url": f"/recordings/{wav_path.name}", "status": "ok", "backend": "gpt_sovits", "detail": wav_path.name}


def _gpt_sovits_language_code(language: str) -> str:
    """Accept project-friendly language names and emit api_v2 language codes."""
    normalized = language.strip().lower()
    aliases = {
        "中文": "zh",
        "汉语": "zh",
        "普通话": "zh",
        "英文": "en",
        "英语": "en",
        "日文": "ja",
        "日语": "ja",
        "韩文": "ko",
        "韩语": "ko",
        "粤语": "yue",
    }
    return aliases.get(normalized, normalized)


def _normalize_wav_bytes(audio_bytes: bytes, output_path: Path) -> None:
    """Convert PCM WAV to mono 16-bit 16 kHz using only the standard library."""
    with wave.open(BytesIO(audio_bytes), "rb") as source:
        channels = source.getnchannels()
        sample_width = source.getsampwidth()
        sample_rate = source.getframerate()
        frame_count = source.getnframes()
        if sample_width != 2 or channels < 1 or sample_rate < 1:
            raise ValueError("GPT-SoVITS response must be PCM WAV with 16-bit samples")
        frames = source.readframes(frame_count)

    samples = memoryview(frames).cast("h")
    mono = [
        sum(samples[index + channel] for channel in range(channels)) // channels
        for index in range(0, len(samples), channels)
    ]
    if sample_rate != 16000 and mono:
        target_count = max(1, round(len(mono) * 16000 / sample_rate))
        ratio = sample_rate / 16000
        resampled = []
        for target_index in range(target_count):
            source_position = target_index * ratio
            left = min(int(source_position), len(mono) - 1)
            right = min(left + 1, len(mono) - 1)
            fraction = source_position - left
            resampled.append(round(mono[left] + (mono[right] - mono[left]) * fraction))
        mono = resampled

    with wave.open(str(output_path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16000)
        target.writeframes(b"".join(int(sample).to_bytes(2, "little", signed=True) for sample in mono))


def _ps_escape(path: Path) -> str:
    return str(path).replace("'", "''")
