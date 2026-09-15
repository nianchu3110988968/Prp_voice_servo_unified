"""Re-export established slices without moving boundaries; add playback tail silence.

Never overwrites inputs or an existing output directory. This is not speech repair:
the appended silence contains no reconstructed phonemes.
"""
import argparse
import hashlib
import json
import subprocess
import wave
from pathlib import Path

import numpy as np


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_pcm(path):
    with wave.open(str(path), "rb") as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (32000, 1, 2):
            raise ValueError(f"Expected 32kHz mono PCM16: {path}")
        return np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--slices", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--tail-ms", type=int, default=250)
    args = parser.parse_args()
    if not 100 <= args.tail_ms <= 1000:
        raise ValueError("Tail silence must be between 100 and 1000 ms")
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"Refusing overwrite: {output}")
    files = sorted(args.slices.resolve().glob("*.wav"))
    if not files:
        raise ValueError("No source slices")
    manifest = args.manifest.read_text(encoding="utf-8-sig").splitlines()
    fields = [row.split("|", 3) for row in manifest]
    if any(len(row) != 4 or not row[3].strip() for row in fields):
        raise ValueError("Invalid input manifest")
    by_name = {p.name: p for p in files}
    manifest_names = [Path(row[0]).name for row in fields]
    if len(set(manifest_names)) != len(manifest_names):
        raise ValueError("Duplicate manifest filenames")
    for row in fields:
        if Path(row[0]).resolve() != by_name.get(Path(row[0]).name):
            raise ValueError(f"Manifest path does not match slice directory: {row[0]}")
    inputs = [args.source.resolve(), args.manifest.resolve(), *files]
    before = {str(path): sha256(path) for path in inputs}
    decoded = subprocess.check_output([
        str(args.ffmpeg), "-nostdin", "-v", "error", "-i", str(args.source),
        "-f", "f32le", "-ac", "1", "-ar", "32000", "pipe:1",
    ])
    source = np.frombuffer(decoded, dtype="<f4")
    prepared = []
    pad_frames = args.tail_ms * 32
    for index, path in enumerate(files):
        start, nominal_end = map(int, path.stem.rsplit("_", 2)[1:])
        end = min(nominal_end, len(source))
        if not 0 <= start < end:
            raise ValueError(f"Invalid boundary: {path}")
        chunk = source[start:end].copy()
        peak = np.abs(chunk).max()
        if peak > 1:
            chunk /= peak
        peak = np.abs(chunk).max()
        # Reproduce original slice_audio.py normalization (max=.9, alpha=.25).
        pcm = ((chunk / peak * 0.225 + 0.75 * chunk) * 32767).astype("<i2") if peak else np.zeros(len(chunk), dtype="<i2")
        old_pcm = read_pcm(path)
        if not np.array_equal(pcm, old_pcm):
            raise ValueError(f"Source/old-slice mismatch; inspect before re-export: {path}")
        trailing_zero = len(pcm) - np.flatnonzero(pcm)[-1] - 1 if np.any(pcm) else len(pcm)
        prepared.append((path, pcm, {
            "index": index, "filename": path.name,
            "source_start_frame": start, "source_end_frame": end,
            "filename_nominal_end_frame": nominal_end,
            "sample_rate": 32000, "old_frames": len(pcm),
            "new_frames": len(pcm) + pad_frames,
            "original_trailing_digital_silence_ms": round(float(trailing_zero) / 32, 3),
            "added_silence_ms": args.tail_ms,
            "in_chinese_manifest": path.name in manifest_names,
            "original_pcm_exact_match": True,
        }))
    output.mkdir(parents=True, exist_ok=False)
    audio_dir = output / "audio"
    audio_dir.mkdir()
    records = []
    for old_path, pcm, record in prepared:
        new_path = audio_dir / old_path.name
        with wave.open(str(new_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(32000)
            wav.writeframes(pcm.tobytes() + bytes(pad_frames * 2))
        actual = read_pcm(new_path)
        if not np.array_equal(actual[:len(pcm)], pcm) or np.any(actual[len(pcm):]) or len(actual) != len(pcm) + pad_frames:
            raise ValueError(f"Output verification failed: {new_path}")
        record["output_sha256"] = sha256(new_path)
        records.append(record)
    new_rows = [[str(audio_dir / Path(row[0]).name), *row[1:]] for row in fields]
    new_manifest = output / "training.list"
    new_manifest.write_text("\n".join("|".join(row) for row in new_rows) + "\n", encoding="utf-8")
    actual_fields = [line.split("|", 3) for line in new_manifest.read_text(encoding="utf-8").splitlines()]
    if [row[1:] for row in actual_fields] != [row[1:] for row in fields]:
        raise ValueError("Manifest content or order changed")
    if any(sha256(Path(path)) != digest for path, digest in before.items()):
        raise ValueError("An input changed during processing")
    report = {
        "operation": "same_boundaries_reexport_plus_silence_not_phoneme_reconstruction",
        "input_sha256": before, "output": str(output), "tail_ms": args.tail_ms,
        "audio_count": len(records), "chinese_manifest_count": len(fields),
        "input_files_unchanged": True, "text_and_order_unchanged": True,
        "all_output_pcm_prefixes_identical_to_old": True, "slices": records,
    }
    (output / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("input_sha256", "slices")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
