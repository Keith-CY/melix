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

from worker.productization.report_evidence_gate import (  # noqa: E402
    _release_matrix_rows,
    _report_matrix_roles,
    _rule_matches_report,
    _slowest_probe_phases,
)


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


def _measure_target_fields(iterations: int, sample_count: int) -> tuple[dict[str, float], float]:
    target_fields = tuple(f"probe_field_{index}" for index in range(64)) + ("target_field",)
    rule = {"target_fields": target_fields}
    targets = [{f"observed_field_{index}": f"value-{index}"} for index in range(79)] + [
        {"target_field": "adapter-snapshot"}
    ]
    elapsed_samples: list[float] = []
    match_count = 0

    for _ in range(sample_count):
        started = time.perf_counter()
        for _index in range(iterations):
            if not _rule_matches_report(
                rule=rule,
                runs=[],
                targets=targets,
                metrics=[],
                probe_phases=set(),
            ):
                raise RuntimeError("expected target-field rule to match target payload")  # pragma: no cover
            match_count += 1
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)

    elapsed_mean = statistics.fmean(elapsed_samples)
    return (
        {
            "target_field_elapsed_ms_mean": elapsed_mean,
            "target_field_count": float(len(target_fields)),
            "targets_per_call": float(len(targets)),
            "target_field_match_count": float(match_count),
        },
        elapsed_mean,
    )


def _measure_release_matrix_rows(iterations: int, sample_count: int) -> tuple[dict[str, float], float]:
    matrix = {
        f"role_{index}": {"run_kinds": (f"kind_{index}",), "description": "probe role"}
        for index in range(32)
    }
    reports = [
        {
            "release_matrix_roles": [f"role_{index % 32}"],
            "source_evidence_ids": [f"evidence_{index % 48}", f"evidence_{(index + 7) % 48}"],
        }
        for index in range(96)
    ]
    elapsed_samples: list[float] = []
    emitted_rows = 0

    for _ in range(sample_count):
        started = time.perf_counter()
        for _index in range(iterations):
            rows = _release_matrix_rows(reports, matrix)
            if len(rows) != len(matrix):
                raise RuntimeError("expected one release-matrix row per role")
            emitted_rows += len(rows)
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)

    elapsed_mean = statistics.fmean(elapsed_samples)
    return (
        {
            "release_matrix_elapsed_ms_mean": elapsed_mean,
            "release_matrix_role_count": float(len(matrix)),
            "release_matrix_report_count": float(len(reports)),
            "release_matrix_emitted_rows": float(emitted_rows),
        },
        elapsed_mean,
    )


def _measure_matrix_roles(iterations: int, sample_count: int) -> tuple[dict[str, float], float]:
    matrix = {
        f"role_{index}": {"run_kinds": (f"kind_{index}",), "description": "probe role"}
        for index in range(32)
    }
    report = {
        "runs": [{"run_kind": f"kind_{index}"} for index in range(32)],
        "probe_summary": {
            side: {
                bucket: [
                    {"phase": f"probe_phase_{index}", "duration_ms": float(index)}
                    for index in range(256)
                ]
                for bucket in (
                    "slowest_phases",
                    "failed_phases",
                    "skipped_phases",
                    "fallback_phases",
                )
            }
            for side in ("baseline", "candidate")
        },
    }
    elapsed_samples: list[float] = []
    emitted_roles = 0

    for _ in range(sample_count):
        started = time.perf_counter()
        for _index in range(iterations):
            roles = _report_matrix_roles(report, matrix)
            if len(roles) != len(matrix):
                raise RuntimeError("expected one matrix role per run kind")
            emitted_roles += len(roles)
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)

    elapsed_mean = statistics.fmean(elapsed_samples)
    return (
        {
            "matrix_roles_elapsed_ms_mean": elapsed_mean,
            "matrix_roles_report_count": 1.0,
            "matrix_roles_role_count": float(len(matrix)),
            "matrix_roles_probe_phase_rows": 2048.0,
            "matrix_roles_emitted_roles": float(emitted_roles),
        },
        elapsed_mean,
    )


def _measure_slowest_probe_phases(iterations: int, sample_count: int) -> tuple[dict[str, float], float]:
    slowest_phases = [
        {"phase": f"probe_phase_{index}", "duration_ms": float((index * 37) % 997)}
        for index in range(2000)
    ]
    report = {
        "probe_summary": {
            "baseline": {"slowest_phases": slowest_phases[:1000]},
            "candidate": {"slowest_phases": slowest_phases[1000:]},
        }
    }
    elapsed_samples: list[float] = []
    checksum = 0.0

    for _ in range(sample_count):
        started = time.perf_counter()
        for _index in range(iterations):
            rows = _slowest_probe_phases(report)
            if len(rows) != 5:
                raise RuntimeError("expected five slowest probe phases")
            checksum += sum(float(row["duration_ms"]) for row in rows)
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)

    elapsed_mean = statistics.fmean(elapsed_samples)
    return (
        {
            "slowest_probe_phase_elapsed_ms_mean": elapsed_mean,
            "slowest_probe_phase_rows_per_call": float(len(slowest_phases)),
            "slowest_probe_phase_checksum": checksum,
        },
        elapsed_mean,
    )


def _measure(iterations: int, sample_count: int) -> dict[str, float]:
    run_kind_metrics, run_kind_elapsed = _measure_run_kind(iterations, sample_count)
    metric_prefix_metrics, metric_prefix_elapsed = _measure_metric_prefix(iterations, sample_count)
    target_field_metrics, target_field_elapsed = _measure_target_fields(iterations, sample_count)
    release_matrix_iterations = max(1, iterations // 100)
    release_matrix_metrics, release_matrix_elapsed = _measure_release_matrix_rows(
        release_matrix_iterations,
        sample_count,
    )
    matrix_roles_iterations = max(1, iterations // 200)
    matrix_roles_metrics, matrix_roles_elapsed = _measure_matrix_roles(
        matrix_roles_iterations,
        sample_count,
    )
    slowest_probe_phase_iterations = max(1, iterations // 500)
    slowest_probe_phase_metrics, slowest_probe_phase_elapsed = _measure_slowest_probe_phases(
        slowest_probe_phase_iterations,
        sample_count,
    )
    return {
        "elapsed_ms_mean": run_kind_elapsed
        + metric_prefix_elapsed
        + target_field_elapsed
        + matrix_roles_elapsed
        + slowest_probe_phase_elapsed,
        "iterations": float(iterations),
        "sample_count": float(sample_count),
        **run_kind_metrics,
        **metric_prefix_metrics,
        **target_field_metrics,
        **release_matrix_metrics,
        **matrix_roles_metrics,
        **slowest_probe_phase_metrics,
    }


def main() -> int:
    iterations = int(os.environ.get("MELIX_REPORT_EVIDENCE_RUN_KIND_ITERATIONS", "50000"))
    sample_count = int(os.environ.get("MELIX_REPORT_EVIDENCE_RUN_KIND_SAMPLES", "5"))
    print(json.dumps(_measure(iterations, sample_count), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
