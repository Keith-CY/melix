from __future__ import annotations

from pathlib import Path

from worker.productization.acceptance_metrics import (
    build_phase8_metrics_report,
    collect_operator_action_evidence,
    compute_benchmark_regression_pct,
    compute_install_success_rate,
    compute_release_smoke_pass_rate,
)
from worker.productization.release_gates import load_release_gate_policy


def test_collect_operator_action_evidence_reports_registry_counts(tmp_path: Path) -> None:
    evidence = collect_operator_action_evidence(tmp_path / "jobs")

    assert evidence["operator_action_latency_ms"] >= 0
    assert evidence["registry_job_count"] >= 2
    assert evidence["registry_adapter_count"] >= 1


def test_compute_install_success_rate_returns_percentage() -> None:
    install = {
        "checks": {
            "manifest_exists": True,
            "environment_script_exists": True,
            "all_plists_exist": False,
        }
    }

    assert compute_install_success_rate(install) == (2 / 3) * 100.0
    assert compute_install_success_rate({}) == 0.0


def test_compute_benchmark_regression_pct_reflects_policy_slippage() -> None:
    policy = load_release_gate_policy()

    assert (
        compute_benchmark_regression_pct(
            {
                "metrics": {
                    "bench.smoke.ttft_ms": 24.45,
                    "bench.smoke.tokens_per_second": 47.08,
                    "bench.latency.p95_ms": 44.72,
                }
            },
            policy,
        )
        == 0.0
    )

    regression = compute_benchmark_regression_pct(
        {
            "metrics": {
                "bench.smoke.ttft_ms": 24.45,
                "bench.smoke.tokens_per_second": 40.0,
                "bench.latency.p95_ms": 44.72,
            }
        },
        policy,
    )
    assert regression > 0.0

    max_regression = compute_benchmark_regression_pct(
        {
            "metrics": {
                "bench.smoke.ttft_ms": 31.0,
                "bench.smoke.tokens_per_second": 47.08,
                "bench.latency.p95_ms": 44.72,
            }
        },
        policy,
    )
    assert max_regression > 0.0

    assert compute_benchmark_regression_pct({"metrics": []}, policy) == 100.0
    assert (
        compute_benchmark_regression_pct(
            {
                "metrics": {
                    "bench.smoke.ttft_ms": "slow",
                    "bench.smoke.tokens_per_second": 47.08,
                    "bench.latency.p95_ms": 44.72,
                }
            },
            policy,
        )
        == 100.0
    )


def test_compute_release_smoke_pass_rate_uses_all_gate_sections() -> None:
    policy = load_release_gate_policy()
    report = {
        "install": {
            "checks": {
                "manifest_exists": True,
                "environment_script_exists": True,
                "all_plists_exist": True,
            }
        },
        "benchmarks": {
            "report_exists": True,
            "metrics": {
                "bench.smoke.ttft_ms": 24.45,
                "bench.smoke.tokens_per_second": 47.08,
                "bench.latency.p95_ms": 44.72,
            },
        },
        "training": {
            "training_duration_ms": 1420.0,
            "adapter_publish_ms": 118.0,
        },
        "recovery": {
            "restart_recovery_ms": 13550.49,
            "restart_recovery_success_rate": 100.0,
        },
    }

    assert compute_release_smoke_pass_rate(report, policy) == 100.0

    report["recovery"]["restart_recovery_success_rate"] = 0.0
    assert compute_release_smoke_pass_rate(report, policy) == 75.0


def test_build_phase8_metrics_report_includes_required_probe_names() -> None:
    policy = load_release_gate_policy()
    report = build_phase8_metrics_report(
        cold_boot={
            "cold_boot_to_ready_ms": 812.3,
            "http_ready_ms": 812.3,
            "background_preload_ms": 944.8,
            "background_preload_success": 1.0,
            "first_text_model_warm_ms": 143.2,
            "text_model_load_estimated_resident_bytes": 4096,
            "text_model_load_resident_bytes": 8192,
        },
        operator={
            "operator_action_latency_ms": 38.4,
            "registry_job_count": 2,
            "registry_adapter_count": 1,
        },
        release_gate_report={
            "install": {
                "checks": {
                    "manifest_exists": True,
                    "environment_script_exists": True,
                    "all_plists_exist": True,
                }
            },
            "benchmarks": {
                "report_exists": True,
                "metrics": {
                    "bench.smoke.ttft_ms": 24.45,
                    "bench.smoke.tokens_per_second": 47.08,
                    "bench.latency.p95_ms": 44.72,
                },
            },
            "training": {
                "training_duration_ms": 1420.0,
                "adapter_publish_ms": 118.0,
            },
            "recovery": {
                "restart_to_ready_ms": 624.6,
                "snapshot_restore_ms": 109.7,
                "restart_recovery_ms": 13550.49,
                "restart_recovery_success_rate": 100.0,
            },
            "passed": True,
            "failures": [],
        },
        policy=policy,
    )

    metrics = report["metrics"]
    assert metrics["desktop.cold_boot_to_ready_ms"] == 812.3
    assert metrics["desktop.http_ready_ms"] == 812.3
    assert metrics["desktop.background_preload_ms"] == 944.8
    assert metrics["desktop.first_text_model_warm_ms"] == 143.2
    assert metrics["desktop.text_model_load_estimated_resident_bytes"] == 4096.0
    assert metrics["desktop.text_model_load_resident_bytes"] == 8192.0
    assert metrics["desktop.operator_action_latency_ms"] == 38.4
    assert metrics["desktop.restart_to_ready_ms"] == 624.6
    assert metrics["desktop.snapshot_restore_ms"] == 109.7
    assert metrics["desktop.restart_recovery_ms"] == 13550.49
    assert metrics["desktop.crash_recovery_success_rate"] == 100.0
    assert metrics["release.benchmark_regression_pct"] == 0.0
    assert metrics["release.smoke_pass_rate"] == 100.0
    assert metrics["install.success_rate"] == 100.0
    assert metrics["training.job_duration_ms"] == 1420.0
    assert metrics["training.adapter_publish_ms"] == 118.0
