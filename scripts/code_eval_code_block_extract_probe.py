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

from worker.engine import code_eval_runner


def _build_response(block_count: int) -> str:
    blocks = []
    for index in range(block_count):
        tag = "PyThOn" if index % 2 else "python"
        blocks.append(
            f"analysis chunk {index}\n```{tag}\ndef candidate_{index}():\n    return {index}\n```"
        )
    trailing_commentary = "\n".join(f"post answer note {index}" for index in range(block_count))
    return "\n  " + "\n\n".join(blocks) + "\n" + trailing_commentary + "   \n\t"


def _build_empty_trailing_block_response(block_count: int) -> str:
    response = _build_response(block_count)
    trailing_commentary = "\n" + ("post-answer whitespace scan guard " * 4096)
    return response + "\n```python\n```" + trailing_commentary


def main() -> None:
    block_count = 2500
    response = _build_response(block_count)
    expected_code = f"def candidate_{block_count - 1}():\n    return {block_count - 1}"
    sample_count = 7
    elapsed_ms: list[float] = []
    empty_fallback_elapsed_ms: list[float] = []
    peak_bytes: list[float] = []
    extracted_lengths: list[float] = []
    empty_response = _build_empty_trailing_block_response(block_count)

    for _ in range(sample_count):
        tracemalloc.start()
        started = time.perf_counter()
        code, parse_status = code_eval_runner.extract_candidate_code(response)
        elapsed_ms.append((time.perf_counter() - started) * 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_bytes.append(float(peak))
        if parse_status != "parsed_code_block" or code != expected_code:
            raise RuntimeError("unexpected extracted code block")
        extracted_lengths.append(float(len(code)))

        empty_started = time.perf_counter()
        empty_code, empty_status = code_eval_runner.extract_candidate_code(empty_response)
        empty_fallback_elapsed_ms.append((time.perf_counter() - empty_started) * 1000.0)
        if empty_status != "parsed_code_block" or empty_code != "":  # pragma: no cover - probe corruption guard
            raise RuntimeError("unexpected empty trailing code block extraction")

    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(elapsed_ms),
                "empty_fallback_elapsed_ms_mean": statistics.fmean(empty_fallback_elapsed_ms),
                "peak_bytes_mean": statistics.fmean(peak_bytes),
                "block_count": float(block_count),
                "sample_count": float(sample_count),
                "extracted_chars_mean": statistics.fmean(extracted_lengths),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
