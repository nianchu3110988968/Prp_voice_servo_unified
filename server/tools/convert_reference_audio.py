"""Convert a reference recording to a GPT-SoVITS-friendly PCM WAV."""

import argparse
import wave
from pathlib import Path

import av


def convert(source_path: Path, target_path: Path) -> dict:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(source_path)) as container:
        audio_stream = next(stream for stream in container.streams if stream.type == "audio")
        resampler = av.audio.resampler.AudioResampler(
            format="s16",
            layout="mono",
            rate=16000,
        )
        pcm_chunks = []
        for frame in container.decode(audio_stream):
            for converted in resampler.resample(frame):
                pcm_chunks.append(converted.to_ndarray().tobytes())
        for converted in resampler.resample(None):
            pcm_chunks.append(converted.to_ndarray().tobytes())

    pcm = b"".join(pcm_chunks)
    with wave.open(str(target_path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(pcm)
    return {"path": str(target_path), "bytes": len(pcm), "duration_seconds": round(len(pcm) / 32000, 1)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    print(convert(args.source, args.target))
