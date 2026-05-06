#!/usr/bin/env python3
from __future__ import annotations

import json
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime.mlx_audio_runtime import _audio_to_wav_bytes  # noqa: E402


class ArrayLikeSegment:
    def __init__(self, values):
        self._values = values

    def tolist(self):
        return self._values


def _build_audio(sample_count: int):
    segments = []
    value_cycle = (-0.75, -0.25, 0.0, 0.25, 0.75)
    for offset in range(0, sample_count, 512):
        chunk = [value_cycle[(offset + index) % len(value_cycle)] for index in range(min(512, sample_count - offset))]
        if (offset // 512) % 2 == 0:
            segments.append(chunk)
        else:
            midpoint = len(chunk) // 2
            segments.append(ArrayLikeSegment((chunk[:midpoint], tuple(chunk[midpoint:]))))
    return segments


def main() -> int:
    sample_count = 240_000
    sample_rate = 24_000
    audio = _build_audio(sample_count)
    elapsed_samples = []
    peak_samples = []
    wav_sizes = []
    for _ in range(5):
        tracemalloc.start()
        started = time.perf_counter()
        wav_bytes = _audio_to_wav_bytes(audio, sample_rate=sample_rate)
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_samples.append(float(peak))
        wav_sizes.append(len(wav_bytes))
    expected_wav_size = 44 + sample_count * 2
    if set(wav_sizes) != {expected_wav_size}:
        raise RuntimeError(f"unexpected wav sizes: {wav_sizes!r} != {expected_wav_size}")
    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "elapsed_ms_min": round(min(elapsed_samples), 6),
                "peak_bytes_mean": round(statistics.fmean(peak_samples), 3),
                "sample_count": float(sample_count),
                "wav_bytes": float(expected_wav_size),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
