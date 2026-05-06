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

from worker.model_ops.hub_catalog import _next_cursor_from_link


def _link_header(index: int) -> tuple[str, str]:
    cursor = f"page/{index}+batch {index % 17}"
    encoded = cursor.replace("/", "%2F").replace("+", "%2B").replace(" ", "+")
    header = (
        f'<https://huggingface.co/api/models?cursor=prev-{index}>; rel="prev", '
        f'<https://huggingface.co/api/models?limit=50&full=true&cursor={encoded}&cardData=true>; rel="next"'
    )
    return header, cursor


def _run_sample(iterations: int) -> tuple[float, int]:
    checksum = 0
    started = time.perf_counter()
    for index in range(iterations):
        header, expected = _link_header(index)
        parsed = _next_cursor_from_link(header)
        if parsed != expected:
            raise SystemExit(f"unexpected cursor at {index}: {parsed!r} != {expected!r}")
        checksum += len(parsed) + ord(parsed[0])
    return (time.perf_counter() - started) * 1000.0, checksum


def main() -> int:
    iterations = int(os.environ.get("MELIX_HUB_CATALOG_CURSOR_ITERATIONS", "50000"))
    sample_count = int(os.environ.get("MELIX_HUB_CATALOG_CURSOR_SAMPLES", "5"))
    elapsed_samples: list[float] = []
    peak_samples: list[int] = []
    checksum = 0

    for _ in range(sample_count):
        tracemalloc.start()
        elapsed_ms, checksum = _run_sample(iterations)
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        elapsed_samples.append(elapsed_ms)
        peak_samples.append(peak_bytes)

    metrics = {
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "peak_bytes_mean": statistics.fmean(peak_samples),
        "cursor_parse_calls_mean": float(iterations),
        "checksum": float(checksum),
        "sample_count": float(sample_count),
    }
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
