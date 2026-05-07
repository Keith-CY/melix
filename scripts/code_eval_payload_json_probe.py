#!/usr/bin/env python3
from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.engine import code_eval_runner


def _build_payload() -> dict[str, object]:
    return {
        "runtime_status": "ok",
        "timeout_status": "ok",
        "test_status": "passed",
        "tests_passed": 128,
        "tests_total": 128,
        "failure_detail": "",
        "stdout_tail": "x" * 8192,
        "stderr_tail": "",
        "metadata": {
            f"case_{index}": {
                "status": "passed",
                "duration_ms": index % 17,
                "message": f"synthetic payload row {index}",
            }
            for index in range(512)
        },
    }


def main() -> None:
    sample_count = 7
    iteration_count = 1200
    elapsed_ms: list[float] = []
    peak_bytes: list[float] = []

    with tempfile.TemporaryDirectory(prefix="melix-code-eval-payload-probe-") as temp_dir:
        payload_path = Path(temp_dir) / "payload.json"
        payload_path.write_text(json.dumps(_build_payload(), sort_keys=True), encoding="utf-8")
        payload_bytes = float(payload_path.stat().st_size)

        for _ in range(sample_count):
            tracemalloc.start()
            started = time.perf_counter()
            for _iteration in range(iteration_count):
                payload = code_eval_runner._load_payload_file(payload_path)
                if not payload or payload.get("runtime_status") != "ok":
                    raise RuntimeError("unexpected payload")
            elapsed_ms.append((time.perf_counter() - started) * 1000.0)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peak_bytes.append(float(peak))

    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(elapsed_ms),
                "peak_bytes_mean": statistics.fmean(peak_bytes),
                "payload_bytes": payload_bytes,
                "sample_count": float(sample_count),
                "iteration_count": float(iteration_count),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
