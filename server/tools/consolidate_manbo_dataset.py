"""Consolidate an approved saved corpus; never deletes or overwrites source files."""
import hashlib
import json
import shutil
import wave
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
GSV = Path(r"E:\AI\GPTSoVITS\GPT-SoVITS-v2pro-20250604")
OLD = GSV / "output/nuonuo_mambo_video_v1"
MANIFEST = OLD / "slicer_tailpad_20260915/training.list"
DEST = PROJECT / "voice_data/manbo"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    if DEST.exists():
        raise FileExistsError(f"Will not overwrite current corpus: {DEST}")
    rows = [line.split("|", 3) for line in MANIFEST.read_text(encoding="utf-8-sig").splitlines()]
    if len(rows) != 39 or any(len(row) != 4 or row[2].lower() != "zh" or not row[3].strip() for row in rows):
        raise ValueError("Expected 39 saved Chinese annotations")
    paths = [Path(row[0]).resolve() for row in rows]
    if len(set(paths)) != 39 or any(p.parent != (OLD / "slicer_tailpad_20260915/audio").resolve() for p in paths):
        raise ValueError("Unexpected source audio mapping")
    source_full = OLD / "source/mambo_tutorial_narrator_zh_only.wav"
    with wave.open(str(source_full)) as f:
        duration = f.getnframes() / f.getframerate()
    if abs(duration - 188.1) > .02:
        raise ValueError("Unexpected continuous Chinese audio duration")
    original_manifest_hash = digest(MANIFEST)
    hashes = [digest(p) for p in paths]
    DEST.mkdir(parents=True, exist_ok=False)
    clips = DEST / "clips"
    clips.mkdir()
    new_rows = []
    records = []
    total = 0
    for index, (row, path, expected) in enumerate(zip(rows, paths, hashes), start=1):
        target = clips / f"{index:03}.wav"
        shutil.copy2(path, target)
        if digest(target) != expected:
            raise ValueError(f"Copy verification failed: {target}")
        with wave.open(str(target)) as f:
            seconds = f.getnframes() / f.getframerate()
            if (f.getframerate(), f.getnchannels(), f.getsampwidth()) != (32000, 1, 2):
                raise ValueError("Unexpected WAV format")
        total += seconds
        new_rows.append("|".join([str(target), *row[1:]]))
        records.append({"id": index, "file": str(target), "old_file": str(path), "sha256": expected, "seconds": seconds})
    (DEST / "clips.list").write_text("\n".join(new_rows) + "\n", encoding="utf-8")
    # Keep a single paragraph with the user's latest saved wording and punctuation.
    (DEST / "full_text.txt").write_text("".join(row[3].strip() for row in rows) + "\n", encoding="utf-8")
    shutil.copy2(source_full, DEST / "full_audio.wav")
    if digest(source_full) != digest(DEST / "full_audio.wav") or digest(MANIFEST) != original_manifest_hash:
        raise ValueError("Source changed while consolidating")
    check_rows = [line.split("|", 3) for line in (DEST / "clips.list").read_text(encoding="utf-8").splitlines()]
    if [r[1:] for r in check_rows] != [r[1:] for r in rows]:
        raise ValueError("Annotations changed")
    report = {"dataset": "manbo", "experiment": "manbo", "count": 39,
              "source_saved_manifest_sha256": original_manifest_hash,
              "initial_clips_list_sha256": digest(DEST / "clips.list"),
              "full_audio_sha256": digest(DEST / "full_audio.wav"),
              "full_audio_seconds": duration, "clips_total_seconds": round(total, 3),
              "note": "Continuous audio is Chinese-only source, not concatenated tail-padded slices. 250ms added silence per clip is not extra speech. Wording is the latest saved annotation, not a new ASR draft. Initial manifest hash is historical and changes after further proofreading.",
              "clips": records}
    (DEST / "dataset.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"dataset": str(DEST), "count": 39, "text_preserved": True, "audio_hash_verified": True, "full_seconds": duration}, ensure_ascii=False))


if __name__ == "__main__":
    main()
