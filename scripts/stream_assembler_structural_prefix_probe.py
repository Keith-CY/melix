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


def _build_long_literal_assembler() -> RequestStreamAssembler:
    assembler = RequestStreamAssembler(
        request_id="probe-structural-prefix-literal",
        reasoning_enabled=True,
        structured_output_mode="",
        tool_parser_mode="qwen",
    )
    assembler._buffer = "literal-less-than-<" + ("x" * 4096)
    return assembler


def main() -> None:
    iterations = int(os.environ.get("MELIX_STREAM_PREFIX_PROBE_ITERATIONS", "250000"))
    sample_count = int(os.environ.get("MELIX_STREAM_PREFIX_PROBE_SAMPLES", "7"))
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    held_suffix_hits = 0
    partial_suffix_hits = 0
    prefix_identity_hits = 0
    partial_elapsed_samples: list[float] = []
    long_literal_elapsed_samples: list[float] = []
    close_marker_elapsed_samples: list[float] = []
    legacy_pipe_body_elapsed_samples: list[float] = []
    unclosed_reasoning_elapsed_samples: list[float] = []
    unclosed_candidate_elapsed_samples: list[float] = []
    long_literal_empty_hits = 0
    close_marker_hits = 0
    legacy_pipe_body_hits = 0
    unclosed_reasoning_hits = 0
    unclosed_candidate_hits = 0
    legacy_pipe_header = "analysis " + ("reasoning payload " * 64)
    unclosed_reasoning_body = "reasoning payload " * 64

    assembler = _build_assembler()
    long_literal_assembler = _build_long_literal_assembler()
    expected_prefixes = assembler._structural_tag_prefixes

    for _ in range(sample_count):
        tracemalloc.start()
        started = time.perf_counter()
        for _index in range(iterations):
            if assembler._partial_structural_tag_suffix():
                held_suffix_hits += 1
            if assembler._structural_tag_prefixes is expected_prefixes:
                prefix_identity_hits += 1
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_samples.append(float(peak))

        started = time.perf_counter()
        for _index in range(iterations):
            if assembler._partial_structural_tag_suffix() == "<tool":
                partial_suffix_hits += 1
        partial_elapsed_samples.append((time.perf_counter() - started) * 1000.0)

        started = time.perf_counter()
        for _index in range(iterations):
            if not long_literal_assembler._partial_structural_tag_suffix():
                long_literal_empty_hits += 1
        long_literal_elapsed_samples.append((time.perf_counter() - started) * 1000.0)

        started = time.perf_counter()
        for _index in range(iterations):
            if (
                RequestStreamAssembler._longest_marker_prefix_suffix(
                    "reasoning body </thi",
                    "</think>",
                )
                == "</thi"
            ):
                close_marker_hits += 1
        close_marker_elapsed_samples.append((time.perf_counter() - started) * 1000.0)

        started = time.perf_counter()
        for _index in range(iterations):
            if RequestStreamAssembler._legacy_pipe_channel_header_body(
                legacy_pipe_header,
                "analysis",
            ):
                legacy_pipe_body_hits += 1
        legacy_pipe_body_elapsed_samples.append((time.perf_counter() - started) * 1000.0)

        recovery_assembler = RequestStreamAssembler(
            request_id="probe-unclosed-reasoning-recovery",
            reasoning_enabled=True,
            structured_output_mode="",
            tool_parser_mode="qwen",
        )
        started = time.perf_counter()
        for _index in range(iterations):
            if recovery_assembler._recover_unclosed_reasoning_body(
                unclosed_reasoning_body,
            ) == ("", ""):
                unclosed_reasoning_hits += 1
        unclosed_reasoning_elapsed_samples.append((time.perf_counter() - started) * 1000.0)

        started = time.perf_counter()
        for _index in range(iterations):
            if RequestStreamAssembler._unclosed_reasoning_candidate_index(
                "reasoning payload " * 64 + "\nFinal: visible answer",
            ) > 0:
                unclosed_candidate_hits += 1
        unclosed_candidate_elapsed_samples.append((time.perf_counter() - started) * 1000.0)

    expected_hits = iterations * sample_count
    if held_suffix_hits != expected_hits:
        raise RuntimeError(
            f"unexpected partial suffix hits: {held_suffix_hits} != {expected_hits}"
        )
    if partial_suffix_hits != expected_hits:
        raise RuntimeError(
            f"unexpected partial suffix resolutions: {partial_suffix_hits} != {expected_hits}"
        )
    if prefix_identity_hits != expected_hits:
        raise RuntimeError(
            f"prefix tuple was not stable: {prefix_identity_hits} != {expected_hits}"
        )
    if long_literal_empty_hits != expected_hits:
        raise RuntimeError(
            "unexpected long literal structural suffix hits: "
            f"{long_literal_empty_hits} != {expected_hits}"
        )
    if close_marker_hits != expected_hits:  # pragma: no cover - probe safety guard
        raise RuntimeError(
            f"unexpected close marker prefix hits: {close_marker_hits} != {expected_hits}"
        )
    if legacy_pipe_body_hits != expected_hits:  # pragma: no cover - probe safety guard
        raise RuntimeError(
            "unexpected legacy pipe body hits: "
            f"{legacy_pipe_body_hits} != {expected_hits}"
        )
    if unclosed_reasoning_hits != expected_hits:  # pragma: no cover - probe safety guard
        raise RuntimeError(
            "unexpected unclosed reasoning recovery hits: "
            f"{unclosed_reasoning_hits} != {expected_hits}"
        )
    if unclosed_candidate_hits != expected_hits:  # pragma: no cover - probe safety guard
        raise RuntimeError(
            "unexpected unclosed reasoning candidate hits: "
            f"{unclosed_candidate_hits} != {expected_hits}"
        )

    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "elapsed_ms_min": round(min(elapsed_samples), 6),
                "partial_suffix_elapsed_ms_mean": round(
                    statistics.fmean(partial_elapsed_samples),
                    6,
                ),
                "partial_suffix_elapsed_ms_min": round(min(partial_elapsed_samples), 6),
                "long_literal_suffix_elapsed_ms_mean": round(
                    statistics.fmean(long_literal_elapsed_samples),
                    6,
                ),
                "long_literal_suffix_elapsed_ms_min": round(
                    min(long_literal_elapsed_samples),
                    6,
                ),
                "close_marker_prefix_elapsed_ms_mean": round(
                    statistics.fmean(close_marker_elapsed_samples),
                    6,
                ),
                "close_marker_prefix_elapsed_ms_min": round(
                    min(close_marker_elapsed_samples),
                    6,
                ),
                "legacy_pipe_body_elapsed_ms_mean": round(
                    statistics.fmean(legacy_pipe_body_elapsed_samples),
                    6,
                ),
                "legacy_pipe_body_elapsed_ms_min": round(
                    min(legacy_pipe_body_elapsed_samples),
                    6,
                ),
                "unclosed_reasoning_recovery_elapsed_ms_mean": round(
                    statistics.fmean(unclosed_reasoning_elapsed_samples),
                    6,
                ),
                "unclosed_reasoning_recovery_elapsed_ms_min": round(
                    min(unclosed_reasoning_elapsed_samples),
                    6,
                ),
                "unclosed_reasoning_candidate_elapsed_ms_mean": round(
                    statistics.fmean(unclosed_candidate_elapsed_samples),
                    6,
                ),
                "unclosed_reasoning_candidate_elapsed_ms_min": round(
                    min(unclosed_candidate_elapsed_samples),
                    6,
                ),
                "peak_bytes_mean": round(statistics.fmean(peak_samples), 3),
                "iteration_count": float(iterations),
                "sample_count": float(sample_count),
                "held_suffix_hits": float(held_suffix_hits),
                "partial_suffix_hits": float(partial_suffix_hits),
                "long_literal_empty_hits": float(long_literal_empty_hits),
                "close_marker_hits": float(close_marker_hits),
                "legacy_pipe_body_hits": float(legacy_pipe_body_hits),
                "unclosed_reasoning_hits": float(unclosed_reasoning_hits),
                "unclosed_reasoning_candidate_hits": float(unclosed_candidate_hits),
                "prefix_identity_hits": float(prefix_identity_hits),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
