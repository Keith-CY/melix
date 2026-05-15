#!/usr/bin/env python3
"""Probe M9 release-gate failure classification work."""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services" / "mlx-worker-python"))

from worker.productization import release_gates  # noqa: E402

PACKAGED_LAUNCH_POLICY = {
    "connect_host_resolution.connect_host_loopback": {"min": 1.0},
    "health_probe_reuse.reused_client_count": {"min": 1.0},
    "health_probe_reuse.time_wait_socket_count": {"max": 4.0},
    "installed_app_audit.audit_passed": {"min": 1.0},
}


class CountingFailure(str):
    endswith_calls = 0

    def endswith(self, suffix: str | tuple[str, ...], *args: Any) -> bool:  # type: ignore[override]
        type(self).endswith_calls += 1
        return super().endswith(suffix, *args)  # type: ignore[arg-type]


def _build_workload(section_count: int, failures_per_section: int) -> tuple[dict[str, Any], dict[str, Any]]:
    report: dict[str, Any] = {}
    policy: dict[str, Any] = {}
    for section_index in range(section_count):
        section_name = f"section_{section_index:03d}"
        metrics: dict[str, float] = {}
        rules: dict[str, dict[str, float]] = {}
        for failure_index in range(failures_per_section):
            metric_name = f"metric_{failure_index:03d}"
            full_metric_name = f"m9.{section_name}.{metric_name}"
            if failure_index % 2 == 0:
                rules[full_metric_name] = {"min": 1.0}
            else:
                metrics[full_metric_name] = 0.0
                rules[full_metric_name] = {"min": 1.0}
        report[section_name] = {"metrics": metrics}
        policy[section_name] = rules
    return report, policy


def _exercise_packaged_launch_release_gate() -> None:
    install_evidence = release_gates.collect_install_evidence(REPO_ROOT)
    packaged_launch = install_evidence["packaged_launch"]
    policy = {
        "packaged_launch": PACKAGED_LAUNCH_POLICY,
    }

    failures = release_gates.evaluate_release_gate(
        {"install": {"packaged_launch": packaged_launch}},
        policy,
    )
    if any("packaged_launch" in failure for failure in failures):  # pragma: no cover
        raise SystemExit(f"packaged launch evidence unexpectedly failed: {failures}")

    top_level_failures = release_gates.evaluate_release_gate(
        {"packaged_launch": packaged_launch},
        policy,
    )
    if any("packaged_launch" in failure for failure in top_level_failures):  # pragma: no cover
        raise SystemExit(f"top-level packaged launch evidence unexpectedly failed: {top_level_failures}")

    missing_failures = release_gates.evaluate_release_gate({}, policy)
    if "packaged_launch evidence is missing" not in missing_failures:  # pragma: no cover
        raise SystemExit(f"missing packaged launch evidence was not reported: {missing_failures}")

    malformed_failures = release_gates.evaluate_release_gate(
        {
            "packaged_launch": {
                "runtime_source": {"packaging_target_id": "", "runtime_layout": ""},
                "connect_host_resolution": None,
                "health_probe_reuse": packaged_launch["health_probe_reuse"],
            }
        },
        policy,
    )
    expected_malformed = {
        "packaged_launch.connect_host_resolution is missing",
        "packaged_launch.installed_app_audit is missing",
        "packaged_launch.runtime_source.packaging_target_id is missing",
        "packaged_launch.runtime_source.runtime_layout is missing",
        "connect_host_resolution.connect_host_loopback is missing",
        "installed_app_audit.audit_passed is missing",
    }
    if not expected_malformed.issubset(set(malformed_failures)):  # pragma: no cover
        raise SystemExit(f"malformed packaged launch evidence was not fully reported: {malformed_failures}")

    regressed = {
        **packaged_launch,
        "connect_host_resolution": {
            **packaged_launch["connect_host_resolution"],
            "connect_host_loopback": 0.0,
        },
        "health_probe_reuse": {
            **packaged_launch["health_probe_reuse"],
            "reused_client_count": 0.0,
            "time_wait_socket_count": 6.0,
        },
        "installed_app_audit": {
            **packaged_launch["installed_app_audit"],
            "audit_passed": 0.0,
        },
    }
    regressed_failures = release_gates.evaluate_release_gate(
        {"install": {"packaged_launch": regressed}},
        policy,
    )
    expected_regressions = {
        "connect_host_resolution.connect_host_loopback=0.00 fell below minimum 1.00",
        "health_probe_reuse.reused_client_count=0.00 fell below minimum 1.00",
        "health_probe_reuse.time_wait_socket_count=6.00 exceeded maximum 4.00",
        "installed_app_audit.audit_passed=0.00 fell below minimum 1.00",
    }
    if not expected_regressions.issubset(set(regressed_failures)):  # pragma: no cover
        raise SystemExit(f"regressed packaged launch evidence was not fully reported: {regressed_failures}")


def main() -> None:
    _exercise_packaged_launch_release_gate()

    section_count = int(os.environ.get("MELIX_RELEASE_GATES_M9_PROBE_SECTIONS", "160"))
    failures_per_section = int(os.environ.get("MELIX_RELEASE_GATES_M9_PROBE_FAILURES", "80"))
    sample_count = int(os.environ.get("MELIX_RELEASE_GATES_M9_PROBE_SAMPLES", "5"))
    expected_failures = section_count * failures_per_section
    expected_missing = section_count * ((failures_per_section + 1) // 2)
    expected_failed = expected_failures - expected_missing
    report, policy = _build_workload(section_count, failures_per_section)

    original_evaluate_section_metrics = release_gates._evaluate_section_metrics

    def counting_evaluate_section_metrics(*args: Any, **kwargs: Any) -> list[CountingFailure]:
        return [CountingFailure(failure) for failure in original_evaluate_section_metrics(*args, **kwargs)]

    elapsed_samples: list[float] = []
    endswith_samples: list[float] = []
    failure_samples: list[float] = []
    release_gates._evaluate_section_metrics = counting_evaluate_section_metrics
    try:
        for _ in range(sample_count):
            CountingFailure.endswith_calls = 0
            started = time.perf_counter()
            failures, summary = release_gates.evaluate_m9_release_evidence(report, policy)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if len(failures) != expected_failures:
                raise SystemExit(f"unexpected failure count: {len(failures)} != {expected_failures}")
            if summary["missing_probe_count"] != float(expected_missing):
                raise SystemExit(
                    f"unexpected missing count: {summary['missing_probe_count']} != {expected_missing}"
                )
            if summary["failed_threshold_count"] != float(expected_failed):
                raise SystemExit(
                    f"unexpected threshold count: {summary['failed_threshold_count']} != {expected_failed}"
                )
            elapsed_samples.append(elapsed_ms)
            endswith_samples.append(float(CountingFailure.endswith_calls))
            failure_samples.append(float(len(failures)))
    finally:
        release_gates._evaluate_section_metrics = original_evaluate_section_metrics

    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(elapsed_samples),
                "endswith_checks_mean": statistics.fmean(endswith_samples),
                "failure_count_mean": statistics.fmean(failure_samples),
                "section_count": float(section_count),
                "failures_per_section": float(failures_per_section),
                "sample_count": float(sample_count),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
