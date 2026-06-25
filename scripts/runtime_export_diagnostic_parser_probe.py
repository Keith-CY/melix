#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
import tracemalloc


ROOT = Path(__file__).resolve().parents[1]
WORKER_ROOT = ROOT / "services/mlx-worker-python"
for candidate in (ROOT, WORKER_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))  # pragma: no cover - script bootstrap

from worker.productization.export_target_diagnostics import (
    _SourceLine,
    _build_redacted_excerpt,
    build_diagnostic_metrics_report,
)


FIXTURE_ROOT = (
    ROOT
    / "services/mlx-worker-python/fixtures/runtime-export/target-manifests.dev.v1"
)


class _ProbeLayout:
    def __init__(self, target_root: Path) -> None:
        self.target_root = target_root


def _env_int(name: str, default: int, minimum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, value)


def _path_redaction_elapsed_ms(
    *,
    samples: int,
    iterations: int,
    path_count: int,
) -> float:
    elapsed_samples: list[float] = []
    with tempfile.TemporaryDirectory(prefix="melix-export-diagnostics-paths-") as directory:
        target_root = Path(directory) / "target"
        target_root.mkdir(parents=True)
        source_lines = [
            _SourceLine(
                source_path="logs/ollama-create.log",
                text=f"runtime load failed at {target_root / 'artifacts' / f'model-{index}.gguf'}",
            )
            for index in range(path_count)
        ]
        layout = _ProbeLayout(target_root)
        for _sample in range(samples):
            started = time.perf_counter()
            for _index in range(iterations):
                excerpt = _build_redacted_excerpt(
                    layout,  # type: ignore[arg-type]
                    source_lines,
                    bounded_bytes=max(path_count * 160, 4096),
                    bounded_lines=path_count + 4,
                )
                if excerpt.summary.redacted_absolute_path_count != path_count:
                    raise SystemExit("export diagnostic path redaction probe failed")
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)
    return statistics.fmean(elapsed_samples)


def main() -> int:
    manifests = sorted(FIXTURE_ROOT.glob("*/export-target-manifest.json"))
    iterations = _env_int("MELIX_RUNTIME_EXPORT_DIAGNOSTIC_PROBE_ITERATIONS", 30, 1)
    samples = _env_int("MELIX_RUNTIME_EXPORT_DIAGNOSTIC_PROBE_SAMPLES", 5, 1)
    path_count = _env_int("MELIX_RUNTIME_EXPORT_DIAGNOSTIC_PATH_COUNT", 200, 1)
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    target_count = 0.0
    parser_coverage = 0.0
    parsed_failure_count = 0.0
    unknown_failure_count = 0.0
    redaction_count = 0.0
    diagnostic_latency_ms = 0.0
    diagnosis_code_count = 0.0

    for _sample in range(samples):
        tracemalloc.start()
        try:
            started = time.perf_counter()
            for _index in range(iterations):
                with tempfile.TemporaryDirectory(prefix="melix-export-diagnostics-probe-") as directory:
                    report = build_diagnostic_metrics_report(manifests, Path(directory))
                if report.get("ok") is not True:
                    raise SystemExit("export diagnostic parser probe failed")
                target_count = float(report["target_count"])
                parser_coverage = float(report["diagnostic_parser_coverage"])
                parsed_failure_count = float(report["parsed_failure_count"])
                unknown_failure_count = float(report["unknown_failure_count"])
                redaction_count = float(report["redaction_count"])
                diagnostic_latency_ms = float(report["diagnostic_latency_ms"])
                diagnosis_code_count = float(report["diagnosis_code_count"])
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            _, peak_bytes = tracemalloc.get_traced_memory()
            peak_samples.append(float(peak_bytes))
        finally:
            tracemalloc.stop()

    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(elapsed_samples),
                "peak_bytes_mean": statistics.fmean(peak_samples),
                "target_count": target_count,
                "diagnostic_parser_coverage": parser_coverage,
                "parsed_failure_count": parsed_failure_count,
                "unknown_failure_count": unknown_failure_count,
                "redaction_count": redaction_count,
                "diagnostic_latency_ms": diagnostic_latency_ms,
                "path_redaction_elapsed_ms_mean": _path_redaction_elapsed_ms(
                    samples=samples,
                    iterations=iterations,
                    path_count=path_count,
                ),
                "path_redaction_count": float(path_count),
                "diagnosis_code_count": diagnosis_code_count,
                "iteration_count": float(iterations),
                "sample_count": float(samples),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI guard
    raise SystemExit(main())
