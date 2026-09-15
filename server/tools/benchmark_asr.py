import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from services.asr_service import transcribe_audio  # noqa: E402


def normalize_text(text: str) -> str:
    return "".join(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", (text or "").lower()))


def edit_distance(reference: str, hypothesis: str) -> int:
    previous = list(range(len(hypothesis) + 1))
    for row, reference_char in enumerate(reference, start=1):
        current = [row]
        for column, hypothesis_char in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (reference_char != hypothesis_char),
                )
            )
        previous = current
    return previous[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description="使用标注清单计算 ASR 字错误率和整句正确率")
    parser.add_argument("manifest", type=Path, help="UTF-8 CSV，字段为 audio_file,reference")
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    total_characters = 0
    total_errors = 0
    exact_matches = 0
    samples = []

    with manifest_path.open("r", encoding="utf-8-sig", newline="") as manifest_file:
        for row in csv.DictReader(manifest_file):
            audio_path = Path(row["audio_file"])
            if not audio_path.is_absolute():
                audio_path = (manifest_path.parent / audio_path).resolve()
            reference = row["reference"].strip()

            started = time.perf_counter()
            result = transcribe_audio(audio_path)
            elapsed_seconds = time.perf_counter() - started
            hypothesis = result.get("text", "")
            normalized_reference = normalize_text(reference)
            normalized_hypothesis = normalize_text(hypothesis)
            errors = edit_distance(normalized_reference, normalized_hypothesis)
            reference_length = max(1, len(normalized_reference))

            total_characters += reference_length
            total_errors += errors
            exact_matches += int(normalized_reference == normalized_hypothesis)
            samples.append(
                {
                    "audio_file": str(audio_path),
                    "reference": reference,
                    "hypothesis": hypothesis,
                    "cer": round(errors / reference_length, 4),
                    "seconds": round(elapsed_seconds, 3),
                    "status": result.get("status", ""),
                    "model": result.get("model", ""),
                }
            )

    sample_count = len(samples)
    report = {
        "sample_count": sample_count,
        "cer": round(total_errors / max(1, total_characters), 4),
        "sentence_accuracy": round(exact_matches / max(1, sample_count), 4),
        "samples": samples,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
