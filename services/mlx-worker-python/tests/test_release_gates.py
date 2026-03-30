from __future__ import annotations

import json
from pathlib import Path

from worker.productization.release_gates import (
    build_release_gate_report,
    collect_benchmark_evidence,
    collect_install_evidence,
    collect_training_evidence,
    evaluate_release_gate,
    load_release_gate_policy,
)


def test_collect_install_evidence_reports_expected_artifacts(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    evidence = collect_install_evidence(repo_root)

    assert evidence["generated_asset_count"] == 5
    assert evidence["bootstrap_command_count"] == 3
    assert evidence["checks"]["manifest_exists"] is True
    assert evidence["checks"]["environment_script_exists"] is True
    assert evidence["checks"]["all_plists_exist"] is True


def test_collect_benchmark_evidence_returns_required_metrics(tmp_path: Path) -> None:
    evidence = collect_benchmark_evidence(tmp_path / "jobs")

    assert evidence["report_exists"] is True
    assert evidence["metrics"]["bench.smoke.ttft_ms"] == 24.45
    assert evidence["metrics"]["bench.smoke.tokens_per_second"] == 47.08
    assert evidence["metrics"]["bench.latency.p95_ms"] == 44.72


def test_collect_training_evidence_returns_required_metrics(tmp_path: Path) -> None:
    evidence = collect_training_evidence(tmp_path / "jobs")

    assert evidence["adapter_name"] == "melix-dev-adapter"
    assert evidence["dataset_uri"] == "datasets/melix-dev"
    assert evidence["training_duration_ms"] == 1420.0
    assert evidence["adapter_publish_ms"] == 118.0


def test_evaluate_release_gate_fails_closed_for_missing_or_regressed_evidence() -> None:
    policy = load_release_gate_policy()
    report = {
        "install": {
            "generated_asset_count": 4,
            "bootstrap_command_count": 2,
            "checks": {
                "manifest_exists": True,
                "environment_script_exists": False,
                "all_plists_exist": True,
            },
        },
        "benchmarks": {
            "report_exists": False,
            "metrics": {
                "bench.smoke.ttft_ms": 31.0,
                "bench.smoke.tokens_per_second": 40.0,
            },
        },
        "training": {
            "training_duration_ms": 2100.0,
            "adapter_publish_ms": 151.0,
        },
        "runtime_core": {
            "multi_model_ready_count": 2.0,
            "multi_model_request_success_rate": 66.0,
            "prefill_memory_guard_rejection_count": 0.0,
            "prefill_memory_guard_success_rate": 0.0,
        },
    }

    failures = evaluate_release_gate(report, policy)

    assert "checks.environment_script_exists must be true" in failures
    assert "generated_asset_count=4.00 fell below minimum 5.00" in failures
    assert "bootstrap_command_count=2.00 fell below minimum 3.00" in failures
    assert "benchmarks.report_exists must be true" in failures
    assert "bench.smoke.ttft_ms=31.00 exceeded maximum 30.00" in failures
    assert "bench.smoke.tokens_per_second=40.00 fell below minimum 45.00" in failures
    assert "bench.latency.p95_ms is missing" in failures
    assert "training_duration_ms=2100.00 exceeded maximum 2000.00" in failures
    assert "adapter_publish_ms=151.00 exceeded maximum 150.00" in failures
    assert "recovery evidence is missing" in failures
    assert "multi_model_ready_count=2.00 fell below minimum 3.00" in failures
    assert "multi_model_request_success_rate=66.00 fell below minimum 100.00" in failures
    assert "prefill_memory_guard_rejection_count=0.00 fell below minimum 1.00" in failures
    assert "prefill_memory_guard_success_rate=0.00 fell below minimum 100.00" in failures


def test_build_release_gate_report_passes_with_supplied_recovery_evidence(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    report = build_release_gate_report(
        repo_root,
        jobs_root=tmp_path / "jobs",
        recovery={
            "restart_recovery_ms": 420.0,
            "restart_recovery_success_rate": 100.0,
        },
        runtime_core={
            "multi_model_ready_count": 3.0,
            "multi_model_request_success_rate": 100.0,
            "prefill_memory_guard_rejection_count": 1.0,
            "prefill_memory_guard_success_rate": 100.0,
        },
    )

    assert report["passed"] is True
    assert report["failures"] == []


def test_load_release_gate_policy_reads_checked_in_json(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "install": {"generated_asset_count": {"min": 5}},
                "benchmarks": {},
                "training": {},
                "recovery": {},
            }
        ),
        encoding="utf-8",
    )

    policy = load_release_gate_policy(policy_path)

    assert policy["install"]["generated_asset_count"]["min"] == 5


def test_build_release_gate_report_uses_temp_jobs_root_and_reports_type_errors(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    report = build_release_gate_report(
        repo_root,
        recovery={
            "restart_recovery_ms": 420.0,
            "restart_recovery_success_rate": 100.0,
        },
        runtime_core={
            "multi_model_ready_count": 3.0,
            "multi_model_request_success_rate": 100.0,
            "prefill_memory_guard_rejection_count": 1.0,
            "prefill_memory_guard_success_rate": 100.0,
        },
    )
    assert report["passed"] is True

    failures = evaluate_release_gate(
        {
            "install": {
                "generated_asset_count": 5,
                "bootstrap_command_count": 3,
                "checks": {
                    "manifest_exists": True,
                    "all_plists_exist": True,
                },
            },
            "benchmarks": {
                "report_exists": True,
                "metrics": {
                    "bench.smoke.ttft_ms": "fast",
                    "bench.smoke.tokens_per_second": 47.08,
                    "bench.latency.p95_ms": 44.72,
                },
            },
            "training": {
                "training_duration_ms": 1420.0,
                "adapter_publish_ms": 118.0,
            },
            "recovery": {
                "restart_recovery_ms": 420.0,
                "restart_recovery_success_rate": 100.0,
            },
            "runtime_core": {
                "multi_model_ready_count": "three",
                "multi_model_request_success_rate": 100.0,
                "prefill_memory_guard_rejection_count": 1.0,
                "prefill_memory_guard_success_rate": 100.0,
            },
        },
        load_release_gate_policy(),
    )

    assert "checks.environment_script_exists is missing" in failures
    assert "bench.smoke.ttft_ms must be numeric" in failures
    assert "multi_model_ready_count must be numeric" in failures


def test_evaluate_release_gate_requires_runtime_core_evidence() -> None:
    failures = evaluate_release_gate(
        {
            "install": {
                "generated_asset_count": 5,
                "bootstrap_command_count": 3,
                "checks": {
                    "manifest_exists": True,
                    "environment_script_exists": True,
                    "all_plists_exist": True,
                },
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
                "restart_recovery_ms": 420.0,
                "restart_recovery_success_rate": 100.0,
            },
        },
        load_release_gate_policy(),
    )

    assert "runtime_core evidence is missing" in failures
