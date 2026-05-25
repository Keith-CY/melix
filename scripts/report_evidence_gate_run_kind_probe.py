#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(os.environ.get("MELIX_REPORT_EVIDENCE_GATE_REPO_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.productization.report_evidence_gate import _rule_matches_report  # noqa: E402


def _measure_run_kind(iterations: int, sample_count: int) -> tuple[dict[str, float], float]:
    run_kinds = tuple(f"probe_kind_{index}" for index in range(64)) + ("target_kind",)
    rule = {"run_kinds": run_kinds}
    runs = [{"run_kind": f"observed_kind_{index}"} for index in range(79)] + [{"run_kind": "target_kind"}]
    elapsed_samples: list[float] = []
    match_count = 0

    for _ in range(sample_count):
        started = time.perf_counter()
        for _index in range(iterations):
            if not _rule_matches_report(
                rule=rule,
                runs=runs,
                targets=[],
                metrics=[],
                probe_phases=set(),
            ):
                raise RuntimeError("expected run-kind rule to match target run")
            match_count += 1
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)

    elapsed_mean = statistics.fmean(elapsed_samples)
    return (
        {
            "run_kind_elapsed_ms_mean": elapsed_mean,
            "run_kind_count": float(len(run_kinds)),
            "runs_per_call": float(len(runs)),
            "match_count": float(match_count),
        },
        elapsed_mean,
    )


def _measure_metric_prefix(iterations: int, sample_count: int) -> tuple[dict[str, float], float]:
    metric_prefixes = tuple(f"probe.metric.{index}." for index in range(64)) + ("target.metric.",)
    rule = {"metric_prefixes": metric_prefixes}
    metrics = [{"metric": f"observed.metric.{index}.latency_ms"} for index in range(79)] + [
        {"metric": "target.metric.decode_ms"}
    ]
    elapsed_samples: list[float] = []
    match_count = 0

    for _ in range(sample_count):
        started = time.perf_counter()
        for _index in range(iterations):
            if not _rule_matches_report(
                rule=rule,
                runs=[],
                targets=[],
                metrics=metrics,
                probe_phases=set(),
            ):
                raise RuntimeError("expected metric-prefix rule to match target metric")
            match_count += 1
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)

    elapsed_mean = statistics.fmean(elapsed_samples)
    return (
        {
            "metric_prefix_elapsed_ms_mean": elapsed_mean,
            "metric_prefix_count": float(len(metric_prefixes)),
            "metrics_per_call": float(len(metrics)),
            "metric_prefix_match_count": float(match_count),
        },
        elapsed_mean,
    )


def _measure(iterations: int, sample_count: int) -> dict[str, float]:
    run_kind_metrics, run_kind_elapsed = _measure_run_kind(iterations, sample_count)
    metric_prefix_metrics, metric_prefix_elapsed = _measure_metric_prefix(iterations, sample_count)
    return {
        "elapsed_ms_mean": run_kind_elapsed + metric_prefix_elapsed,
        "iterations": float(iterations),
        "sample_count": float(sample_count),
        **run_kind_metrics,
        **metric_prefix_metrics,
    }


def main() -> int:
    iterations = int(os.environ.get("MELIX_REPORT_EVIDENCE_RUN_KIND_ITERATIONS", "50000"))
    sample_count = int(os.environ.get("MELIX_REPORT_EVIDENCE_RUN_KIND_SAMPLES", "5"))
    print(json.dumps(_measure(iterations, sample_count), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
