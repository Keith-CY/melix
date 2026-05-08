from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1] if "__file__" in globals() else Path.cwd()
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from packages.protocol.python.worker.v1 import maintenance_pb2
from worker.productization import quantization_gates as quantization_gates_module
from worker.productization.quantization_gates import collect_quantization_benchmark_evidence


PROFILE_COUNT = 6
POST_MANIFEST_EVENT_COUNT = 2000
SAMPLE_COUNT = 7


PAYLOAD = {
    "artifact_bytes": 128,
    "manifest_bytes": 96,
    "calibration": {"sample_count": 16},
    "compatibility": {"smoke_test_passed": True},
    "manifest_path": "/tmp/melix-quantization-gate-probe/manifest.json",
    "artifact_path": "/tmp/melix-quantization-gate-probe/artifact.bin",
}


class CountingCore:
    def __init__(self) -> None:
        self.consumed_events = 0

    def convert_model(self, request: maintenance_pb2.ConvertModelRequest):
        self.consumed_events += 1
        yield maintenance_pb2.ConvertModelEvent(started=maintenance_pb2.ConvertStarted())
        self.consumed_events += 1
        yield maintenance_pb2.ConvertModelEvent(
            manifest=maintenance_pb2.ConvertManifest(manifest_json=json.dumps(PAYLOAD))
        )
        for _ in range(POST_MANIFEST_EVENT_COUNT):
            self.consumed_events += 1
            yield maintenance_pb2.ConvertModelEvent(started=maintenance_pb2.ConvertStarted())


def main() -> None:
    profiles = tuple(f"q{index}" for index in range(PROFILE_COUNT))
    elapsed_samples: list[float] = []
    consumed_samples: list[float] = []
    original_build_core = quantization_gates_module._build_maintenance_core
    try:
        with tempfile.TemporaryDirectory(prefix="melix-quant-gate-probe-") as temp_dir:
            jobs_root = Path(temp_dir) / "jobs"
            for _ in range(SAMPLE_COUNT):
                core = CountingCore()
                quantization_gates_module._build_maintenance_core = lambda jobs_root: core
                started_at = time.perf_counter()
                evidence = collect_quantization_benchmark_evidence(jobs_root, profiles=profiles)
                elapsed_samples.append((time.perf_counter() - started_at) * 1000.0)
                consumed_samples.append(float(core.consumed_events))
                if evidence["summary"]["profile_count"] != PROFILE_COUNT:
                    raise AssertionError("unexpected profile count")
                if evidence["summary"]["smoke_pass_rate"] != 100.0:
                    raise AssertionError("unexpected smoke pass rate")
    finally:
        quantization_gates_module._build_maintenance_core = original_build_core

    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "elapsed_ms_min": round(min(elapsed_samples), 6),
                "events_consumed_mean": round(statistics.fmean(consumed_samples), 6),
                "profile_count": float(PROFILE_COUNT),
                "post_manifest_event_count": float(POST_MANIFEST_EVENT_COUNT),
                "sample_count": float(SAMPLE_COUNT),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
