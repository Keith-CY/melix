from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime import video_preprocessing


class CountingMedia:
    def __init__(self) -> None:
        self.byte_length_reads = 0

    def __getattribute__(self, name: str):
        if name == "byte_length":
            byte_length_reads = object.__getattribute__(self, "byte_length_reads")
            object.__setattr__(self, "byte_length_reads", byte_length_reads + 1)
            return 4096
        return object.__getattribute__(self, name)

    def __getattr__(self, name: str):
        return "" if name in {"mime_type", "format", "filename"} else 0


class CountingVideoPart:
    def __init__(self, media: CountingMedia) -> None:
        self.media = media
        self.video_bytes = b""
        self.video_uri = "https://example.com/media/probe.mov"


def run_probe(iterations: int = 50_000, sample_count: int = 5) -> dict[str, float]:
    elapsed_samples: list[float] = []
    byte_length_reads: list[float] = []
    parse_calls_per_call: list[float] = []
    checksum = 0
    original_parse = video_preprocessing._parse_video_reference
    for _ in range(sample_count):
        media = CountingMedia()
        part = CountingVideoPart(media)
        parse_calls = 0

        def counting_parse(reference: str):
            nonlocal parse_calls
            parse_calls += 1
            return original_parse(reference)

        video_preprocessing._parse_video_reference = counting_parse
        started = time.perf_counter()
        try:
            for _index in range(iterations):
                prepared = video_preprocessing.prepare_video_input(part)
                checksum += prepared.byte_length + len(prepared.sha256_hex)
        finally:
            video_preprocessing._parse_video_reference = original_parse
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        byte_length_reads.append(float(media.byte_length_reads) / float(iterations))
        parse_calls_per_call.append(float(parse_calls) / float(iterations))
    if checksum <= 0:
        raise RuntimeError("unexpected empty video preprocessing probe checksum")
    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "byte_length_getattrs_per_call": statistics.fmean(byte_length_reads),
        "parse_calls_per_call": statistics.fmean(parse_calls_per_call),
        "iterations_per_sample": float(iterations),
        "sample_count": float(sample_count),
    }


if __name__ == "__main__":
    print(json.dumps(run_probe(), sort_keys=True))
    raise SystemExit(0)
