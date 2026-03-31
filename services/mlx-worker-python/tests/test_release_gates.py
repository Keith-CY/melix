from __future__ import annotations

import json
import sys
from pathlib import Path

from packages.protocol.python.worker.v1 import maintenance_pb2
from worker.productization.release_gates import (
    build_release_gate_report,
    collect_benchmark_evidence,
    collect_install_evidence,
    collect_training_evidence,
    evaluate_release_gate,
    load_release_gate_policy,
)
from worker.productization.quantization_gates import (
    collect_quantization_benchmark_evidence,
    evaluate_quantization_gate,
    load_quantization_gate_policy,
)
from worker.productization import release_gates as release_gates_module


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


def test_collect_quantization_benchmark_evidence_returns_profile_metrics(tmp_path: Path) -> None:
    evidence = collect_quantization_benchmark_evidence(tmp_path / "jobs")

    assert evidence["summary"]["profile_count"] == 7
    assert evidence["summary"]["smoke_pass_rate"] == 100.0
    assert evidence["profiles"]["q2"]["quant_profile_id"] == "q2"
    assert evidence["profiles"]["q8"]["quant_profile_id"] == "q8"
    assert evidence["profiles"]["q4"]["calibration_sample_count"] == 64
    assert evidence["profiles"]["q8"]["calibration_sample_count"] == 16
    assert evidence["profiles"]["q2"]["artifact_bytes"] > 0
    assert evidence["profiles"]["q2"]["manifest_bytes"] > 0
    assert evidence["profiles"]["q2"]["job_ms"] >= 0.0


def test_evaluate_quantization_gate_reports_regressions() -> None:
    policy = load_quantization_gate_policy()
    report = {
        "summary": {
            "profile_count": 2,
            "smoke_pass_rate": 50.0,
        },
        "profiles": {
            "q2": {
                "job_ms": 99.0,
                "artifact_bytes": 99999,
                "manifest_bytes": 99999,
                "calibration_sample_count": 4,
                "smoke_test_passed": False,
            }
        },
    }

    failures = evaluate_quantization_gate(report, policy)

    assert "summary.profile_count=2.00 fell below minimum 7.00" in failures
    assert "summary.smoke_pass_rate=50.00 fell below minimum 100.00" in failures
    assert "profiles.q2.job_ms=99.00 exceeded maximum 50.00" in failures
    assert "profiles.q2.artifact_bytes=99999.00 exceeded maximum 4096.00" in failures
    assert "profiles.q2.manifest_bytes=99999.00 exceeded maximum 4096.00" in failures
    assert "profiles.q2.calibration_sample_count=4.00 fell below minimum 16.00" in failures
    assert "profiles.q2.smoke_test_passed=0.00 fell below minimum 1.00" in failures


def test_collect_benchmark_evidence_includes_cache_recovery_report_when_repo_root_is_supplied(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report_path = tmp_path / "jobs" / "bench" / "bench-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("# bench\n", encoding="utf-8")

    class FakeCore:
        def bench_events(self, request: maintenance_pb2.RunBenchRequest):
            assert list(request.suites) == ["smoke", "latency"]
            yield maintenance_pb2.RunBenchEvent(
                metric=maintenance_pb2.BenchMetric(
                    name="bench.smoke.ttft_ms",
                    value=24.45,
                    unit="ms",
                )
            )
            yield maintenance_pb2.RunBenchEvent(
                metric=maintenance_pb2.BenchMetric(
                    name="bench.smoke.tokens_per_second",
                    value=47.08,
                    unit="tok/s",
                )
            )
            yield maintenance_pb2.RunBenchEvent(
                metric=maintenance_pb2.BenchMetric(
                    name="bench.latency.p95_ms",
                    value=44.72,
                    unit="ms",
                )
            )
            yield maintenance_pb2.RunBenchEvent(
                completed=maintenance_pb2.BenchCompleted(report_path=str(report_path))
            )

    monkeypatch.setattr(
        release_gates_module,
        "_build_maintenance_core",
        lambda jobs_root: FakeCore(),
    )
    monkeypatch.setattr(
        release_gates_module,
        "collect_cache_recovery_benchmark_evidence",
        lambda repo_root: {
            "metrics": {
                "bench.recovery.hot_followup_ttft_delta_ms": 12.5,
                "bench.recovery.cold_l2_hit_rate": 100.0,
                "bench.recovery.partial_restore_ratio_pct": 80.0,
            },
            "report_path": str(tmp_path / "jobs" / "bench" / "cache-recovery-report.json"),
            "report_exists": True,
            "hot_tier": {"followup_ttft_delta_ms": 12.5},
            "cold_tier": {"l2_hit_rate": 100.0},
            "partial_restore": {"restore_ratio_pct": 80.0},
            "restart": {"restart_recovery_ms": 580.0},
        },
        raising=False,
    )

    evidence = collect_benchmark_evidence(tmp_path / "jobs", repo_root=tmp_path / "repo")

    assert evidence["report_exists"] is True
    assert evidence["recovery_report_exists"] is True
    assert evidence["recovery_metrics"]["bench.recovery.hot_followup_ttft_delta_ms"] == 12.5
    assert evidence["recovery_metrics"]["bench.recovery.cold_l2_hit_rate"] == 100.0
    assert evidence["recovery_metrics"]["bench.recovery.partial_restore_ratio_pct"] == 80.0


def test_collect_cache_recovery_benchmark_evidence_delegates_to_runtime_probes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setitem(
        sys.modules,
        "phase8_runtime_probes",
        type(
            "FakeRuntimeProbes",
            (),
            {
                "collect_cache_recovery_benchmark_evidence": staticmethod(
                    lambda repo_root: {"metrics": {"bench.recovery.hot_followup_ttft_delta_ms": 9.5}}
                )
            },
        ),
    )

    evidence = release_gates_module.collect_cache_recovery_benchmark_evidence(tmp_path / "repo")

    assert evidence["metrics"]["bench.recovery.hot_followup_ttft_delta_ms"] == 9.5


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
    assert "quantization evidence is missing" in failures


def test_build_release_gate_report_passes_with_supplied_recovery_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(
        release_gates_module,
        "collect_cache_recovery_benchmark_evidence",
        lambda repo_root: {
            "metrics": {
                "bench.recovery.hot_followup_ttft_delta_ms": 12.5,
                "bench.recovery.cold_l2_hit_rate": 100.0,
                "bench.recovery.partial_restore_ratio_pct": 80.0,
            }
        },
    )
    monkeypatch.setattr(
        release_gates_module,
        "collect_quantization_benchmark_evidence",
        lambda jobs_root: {
            "summary": {"profile_count": 7, "smoke_pass_rate": 100.0},
            "profiles": {
                profile_id: {
                    "job_ms": 1.0,
                    "artifact_bytes": 670,
                    "manifest_bytes": 1747,
                    "calibration_sample_count": 16 if profile_id == "q8" else 32,
                    "smoke_test_passed": True,
                }
                for profile_id in ("q2", "q3", "q4", "q5", "q6", "q7", "q8")
            },
        },
    )

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


def test_build_release_gate_report_uses_temp_jobs_root_and_reports_type_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(
        release_gates_module,
        "collect_cache_recovery_benchmark_evidence",
        lambda repo_root: {
            "metrics": {
                "bench.recovery.hot_followup_ttft_delta_ms": 12.5,
                "bench.recovery.cold_l2_hit_rate": 100.0,
                "bench.recovery.partial_restore_ratio_pct": 80.0,
            }
        },
    )
    monkeypatch.setattr(
        release_gates_module,
        "collect_quantization_benchmark_evidence",
        lambda jobs_root: {
            "summary": {"profile_count": 7, "smoke_pass_rate": 100.0},
            "profiles": {
                profile_id: {
                    "job_ms": 1.0,
                    "artifact_bytes": 670,
                    "manifest_bytes": 1747,
                    "calibration_sample_count": 16 if profile_id == "q8" else 32,
                    "smoke_test_passed": True,
                }
                for profile_id in ("q2", "q3", "q4", "q5", "q6", "q7", "q8")
            },
        },
    )

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
            "quantization": {
                "summary": {
                    "profile_count": 7,
                    "smoke_pass_rate": 100.0,
                },
                "profiles": {
                    "q2": {
                        "job_ms": "fast",
                        "artifact_bytes": 670.0,
                        "manifest_bytes": 1747.0,
                        "calibration_sample_count": 96.0,
                        "smoke_test_passed": 1.0,
                    }
                },
            },
        },
        load_release_gate_policy(),
    )

    assert "checks.environment_script_exists is missing" in failures
    assert "bench.smoke.ttft_ms must be numeric" in failures
    assert "multi_model_ready_count must be numeric" in failures
    assert "profiles.q2.job_ms is missing" in failures


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
            "quantization": {
                "summary": {
                    "profile_count": 7,
                    "smoke_pass_rate": 100.0,
                },
                "profiles": {
                    profile_id: {
                        "job_ms": 1.0,
                        "artifact_bytes": 670.0,
                        "manifest_bytes": 1747.0,
                        "calibration_sample_count": 16.0,
                        "smoke_test_passed": 1.0,
                    }
                    for profile_id in ("q2", "q3", "q4", "q5", "q6", "q7", "q8")
                },
            },
        },
        load_release_gate_policy(),
    )

    assert "runtime_core evidence is missing" in failures
