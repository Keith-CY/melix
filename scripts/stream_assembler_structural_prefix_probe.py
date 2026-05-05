#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime.stream_assembler import RequestStreamAssembler  # noqa: E402


def _build_assembler() -> RequestStreamAssembler:
    assembler = RequestStreamAssembler(
        request_id="probe-structural-prefixes",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )
    assembler._buffer = "chunk-ending-with-partial-<tool"
    return assembler


def main() -> None:
    iterations = int(os.environ.get("MELIX_STREAM_PREFIX_PROBE_ITERATIONS", "250000"))
    sample_count = int(os.environ.get("MELIX_STREAM_PREFIX_PROBE_SAMPLES", "7"))
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    held_suffix_hits = 0
    prefix_identity_hits = 0

    assembler = _build_assembler()
    expected_prefixes = assembler._structural_tag_prefixes

    for _ in range(sample_count):
        tracemalloc.start()
        started = time.perf_counter()
        for _index in range(iterations):
            if assembler._has_partial_structural_tag_suffix():
                held_suffix_hits += 1
            if assembler._structural_tag_prefixes is expected_prefixes:
                prefix_identity_hits += 1
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_samples.append(float(peak))

    expected_hits = iterations * sample_count
    if held_suffix_hits != expected_hits:
        raise RuntimeError(
            f"unexpected partial suffix hits: {held_suffix_hits} != {expected_hits}"
        )
    if prefix_identity_hits != expected_hits:
        raise RuntimeError(
            f"prefix tuple was not stable: {prefix_identity_hits} != {expected_hits}"
        )

    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "elapsed_ms_min": round(min(elapsed_samples), 6),
                "peak_bytes_mean": round(statistics.fmean(peak_samples), 3),
                "iteration_count": float(iterations),
                "sample_count": float(sample_count),
                "held_suffix_hits": float(held_suffix_hits),
                "prefix_identity_hits": float(prefix_identity_hits),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
