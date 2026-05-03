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

from worker.model_ops import mlx_lm_runner as mlx_lm_runner_module  # noqa: E402

PREFIX = mlx_lm_runner_module._RESULT_PREFIX
PAYLOAD = {"value": 42, "weights_path": "/tmp/adapters.safetensors"}
NOISE_LINE_COUNT = 50000
ITERATION_COUNT = 12
SAMPLE_COUNT = 5


def _legacy_extract(stdout: str) -> dict[str, object] | None:
    for line in reversed(stdout.splitlines()):
        if line.startswith(PREFIX):
            return json.loads(line.removeprefix(PREFIX))
    return None


def _extract(stdout: str) -> dict[str, object] | None:
    extractor = getattr(mlx_lm_runner_module, "_extract_structured_result_payload", None)
    if extractor is not None:
        return extractor(stdout)
    return _legacy_extract(stdout)


def main() -> int:
    stdout = (
        "progress log mentioning __MELIX_MLX_RESULT__=not-a-result-line\n"
        + "".join(f"worker log {index}\n" for index in range(NOISE_LINE_COUNT))
        + f"{PREFIX}{json.dumps(PAYLOAD, sort_keys=True)}\n"
    )
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    for _ in range(SAMPLE_COUNT):
        tracemalloc.start()
        started = time.perf_counter()
        payload = None
        for _ in range(ITERATION_COUNT):
            payload = _extract(stdout)
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if payload != PAYLOAD:
            raise SystemExit("unexpected structured result payload")
        peak_samples.append(float(peak_bytes))
    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "iteration_count": float(ITERATION_COUNT),
                "line_count": float(NOISE_LINE_COUNT + 2),
                "peak_bytes_mean": round(statistics.fmean(peak_samples), 3),
                "payload_value": float(PAYLOAD["value"]),
                "sample_count": float(SAMPLE_COUNT),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
