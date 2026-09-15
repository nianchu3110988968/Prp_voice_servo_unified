from array import array
from sys import byteorder


def pcm_s16le_stats(pcm_bytes: bytes) -> dict:
    samples = _samples_from_pcm_s16le(pcm_bytes)
    if not samples:
        return {
            "sample_count": 0,
            "peak": 0,
            "peak_ratio": 0.0,
            "rms": 0.0,
            "rms_ratio": 0.0,
        }

    peak = max(abs(sample) for sample in samples)
    square_sum = sum(sample * sample for sample in samples)
    rms = (square_sum / len(samples)) ** 0.5
    return {
        "sample_count": len(samples),
        "peak": peak,
        "peak_ratio": peak / 32768,
        "rms": rms,
        "rms_ratio": rms / 32768,
    }


def normalize_pcm_s16le(pcm_bytes: bytes, target_peak_ratio: float) -> bytes:
    samples = _samples_from_pcm_s16le(pcm_bytes)
    if not samples:
        return pcm_bytes

    peak = max(abs(sample) for sample in samples)
    if peak == 0:
        return pcm_bytes

    target_peak = max(1, min(32767, int(32767 * target_peak_ratio)))
    gain = target_peak / peak

    normalized = array("h")
    for sample in samples:
        value = int(sample * gain)
        if value > 32767:
            value = 32767
        elif value < -32768:
            value = -32768
        normalized.append(value)

    if byteorder != "little":
        normalized.byteswap()
    return normalized.tobytes()


def _samples_from_pcm_s16le(pcm_bytes: bytes) -> array:
    even_len = len(pcm_bytes) - (len(pcm_bytes) % 2)
    samples = array("h")
    samples.frombytes(pcm_bytes[:even_len])
    if byteorder != "little":
        samples.byteswap()
    return samples

