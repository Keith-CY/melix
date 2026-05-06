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
        blocks.append(
            f"analysis chunk {index}\n```python\ndef candidate_{index}():\n    return {index}\n```"
        )
    return "\n\n".join(blocks)


def main() -> None:
    block_count = 2500
    response = _build_response(block_count)
    expected_code = f"def candidate_{block_count - 1}():\n    return {block_count - 1}"
    sample_count = 7
    elapsed_ms: list[float] = []
    peak_bytes: list[float] = []
    extracted_lengths: list[float] = []

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

    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(elapsed_ms),
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
