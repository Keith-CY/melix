#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
import tracemalloc


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(repo_root / "services/mlx-worker-python"))

    from packages.protocol.python.worker.v1 import maintenance_pb2
    from worker.productization import release_gates as release_gates_module

    benchmark_metric_total = 2048
    training_progress_total = 4096
    sample_count = 3
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    benchmark_metric_count = 0.0
    training_artifact_count = 0.0

    class FakeCore:
        def __init__(self, jobs_root: Path) -> None:
            self.jobs_root = jobs_root

        def bench_events(self, request: maintenance_pb2.RunBenchRequest):
            del request
            report_path = self.jobs_root / "bench" / "runs" / "probe-bench" / "bench-report.md"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text("# probe bench\n", encoding="utf-8")
            yield maintenance_pb2.RunBenchEvent(
                started=maintenance_pb2.BenchStarted(job_id="probe-bench")
            )
            for index in range(benchmark_metric_total - 3):
                yield maintenance_pb2.RunBenchEvent(
                    metric=maintenance_pb2.BenchMetric(
                        name=f"bench.synthetic.metric_{index:04d}",
                        value=float(index),
                        unit="count",
                    )
                )
            yield maintenance_pb2.RunBenchEvent(
                metric=maintenance_pb2.BenchMetric(
                    name="bench.smoke.ttft_ms",
                    value=22.5,
                    unit="ms",
                )
            )
            yield maintenance_pb2.RunBenchEvent(
                metric=maintenance_pb2.BenchMetric(
                    name="bench.smoke.tokens_per_second",
                    value=48.0,
                    unit="tok/s",
                )
            )
            yield maintenance_pb2.RunBenchEvent(
                metric=maintenance_pb2.BenchMetric(
                    name="bench.latency.p95_ms",
                    value=44.0,
                    unit="ms",
                )
            )
            yield maintenance_pb2.RunBenchEvent(
                completed=maintenance_pb2.BenchCompleted(report_path=str(report_path))
            )

        def convert_model(self, request: maintenance_pb2.ConvertModelRequest):
            output_dir = Path(request.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            adapter_path = output_dir / "adapter-final"
            manifest = {
                "job_id": "probe-train-final",
                "adapter_name": request.ext.get("adapter_name", "probe-adapter"),
                "dataset_uri": request.ext.get("dataset_uri", ""),
                "training_duration_ms": 1500.0,
                "adapter_publish_ms": 120.0,
            }
            yield maintenance_pb2.ConvertModelEvent(
                manifest=maintenance_pb2.ConvertManifest(
                    manifest_json=json.dumps({**manifest, "job_id": "probe-train-initial", "training_duration_ms": 1420.0})
                )
            )
            yield maintenance_pb2.ConvertModelEvent(
                completed=maintenance_pb2.ConvertCompleted(output_path=str(output_dir / "adapter-initial"))
            )
            for index in range(training_progress_total):
                yield maintenance_pb2.ConvertModelEvent(
                    progress=maintenance_pb2.ConvertProgress(
                        stage=f"progress-{index:04d}",
                        pct=min(1.0, (index + 1) / training_progress_total),
                    )
                )
            yield maintenance_pb2.ConvertModelEvent(
                manifest=maintenance_pb2.ConvertManifest(manifest_json=json.dumps(manifest))
            )
            yield maintenance_pb2.ConvertModelEvent(
                completed=maintenance_pb2.ConvertCompleted(output_path=str(adapter_path))
            )

    original_builder = release_gates_module._build_maintenance_core
    try:
        for _ in range(sample_count):
            with tempfile.TemporaryDirectory(prefix="melix-release-gates-event-stream-") as temp_dir:
                jobs_root = Path(temp_dir) / "jobs"
                release_gates_module._build_maintenance_core = lambda path, _jobs_root=jobs_root: FakeCore(Path(path or _jobs_root))
                tracemalloc.start()
                started = time.perf_counter()
                benchmark = release_gates_module.collect_benchmark_evidence(jobs_root)
                training = release_gates_module.collect_training_evidence(jobs_root)
                elapsed_samples.append((time.perf_counter() - started) * 1000.0)
                _, peak_bytes = tracemalloc.get_traced_memory()
                peak_samples.append(float(peak_bytes))
                tracemalloc.stop()
                benchmark_metric_count = float(len(benchmark["metrics"]))
                training_artifact_count = 1.0 if training["artifact_path"] else 0.0
                if benchmark["report_exists"] is not True:
                    raise RuntimeError("benchmark report was not produced")
                if training["artifact_path"] != str(jobs_root / "train-lora" / "adapter-final"):
                    raise RuntimeError("training artifact path did not use the latest completed event")
    finally:
        release_gates_module._build_maintenance_core = original_builder

    print(
        json.dumps(
            {
                "benchmark_metric_count": benchmark_metric_count,
                "benchmark_metric_total": float(benchmark_metric_total),
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "peak_bytes_mean": round(statistics.fmean(peak_samples), 1),
                "sample_count": float(sample_count),
                "training_artifact_count": training_artifact_count,
                "training_progress_total": float(training_progress_total),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
