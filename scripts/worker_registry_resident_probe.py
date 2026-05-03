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
    request_stats_elapsed_samples: list[float] = []
    preloaded_count = 2000
    loop_count = 250
    request_count = 3000

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

        request_registry = build_registry()
        for index in range(request_count):
            runtime_kind = "ocr" if index % 5 == 0 else "text"
            request_registry.start_request(f"req-{index}", runtime_kind=runtime_kind)
            if index % 3 == 0:
                request_registry.set_request_phase(f"req-{index}", "prefill")
            elif index % 3 == 1:
                request_registry.set_request_phase(f"req-{index}", "decode")
        started = time.perf_counter()
        for _ in range(loop_count):
            stats = request_registry.runtime_stats()
            if (
                stats.active_requests != request_count
                or stats.active_prefills != 1000
                or stats.active_decodes != 1000
                or stats.active_multimodal_requests != 600
            ):
                raise AssertionError("runtime_stats request counters drifted during the probe")
        request_stats_elapsed_samples.append((time.perf_counter() - started) * 1000.0 / loop_count)

    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "loop_count": float(loop_count),
                "preloaded_model_count": float(preloaded_count),
                "request_count": float(request_count),
                "request_stats_elapsed_ms_mean": round(statistics.fmean(request_stats_elapsed_samples), 6),
                "resident_bytes_mean": round(statistics.fmean(resident_samples), 3),
                "sample_count": float(len(elapsed_samples)),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
