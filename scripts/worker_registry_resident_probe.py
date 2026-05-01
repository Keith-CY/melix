#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import statistics
import sys
import time


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from tests.test_runtime_edges import build_registry  # noqa: E402
from worker.model_registry.catalog import WorkerModelCatalog  # noqa: E402


def main() -> int:
    spec = WorkerModelCatalog.dev_text_model()
    elapsed_samples: list[float] = []
    resident_samples: list[float] = []
    preloaded_count = 2000
    loop_count = 250

    for _ in range(3):
        registry = build_registry()
        for _ in range(preloaded_count):
            registry.load_model(spec)
        started = time.perf_counter()
        for _ in range(loop_count):
            loaded = registry.load_model(spec)
            resident_samples.append(float(registry.runtime_stats().model_resident_bytes))
            registry.unload_model(loaded.handle)
        elapsed_samples.append((time.perf_counter() - started) * 1000.0 / loop_count)

    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "loop_count": float(loop_count),
                "preloaded_model_count": float(preloaded_count),
                "resident_bytes_mean": round(statistics.fmean(resident_samples), 3),
                "sample_count": float(len(elapsed_samples)),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
