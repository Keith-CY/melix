from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from packages.protocol.python.worker.v1 import maintenance_pb2
from worker.productization.evaluation_schemas import (
    build_evaluation_compare_job_record,
    build_evaluation_compare_summary_record,
)
from worker.productization.evaluation_store import EvaluationStore
from worker.productization.release_gates import (
    DEFAULT_RELEASE_GATE_POLICY,
    build_release_gate_report,
    collect_evaluation_compare_evidence,
    collect_audio_product_evidence,
    collect_benchmark_evidence,
    collect_evaluation_evidence,
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


def _m9_probe_count(policy: dict[str, object] | None = None) -> float:
    active_policy = policy or DEFAULT_RELEASE_GATE_POLICY["m9"]
    return float(
        sum(
            len(section_rules)
            for section_rules in active_policy.values()
            if isinstance(section_rules, dict)
        )
    )


def _passing_m9_evidence(policy: dict[str, object] | None = None) -> dict[str, object]:
    required_probe_count = _m9_probe_count(policy)
    return {
        "mcp": {
            "metrics": {
                "mcp.tool_injection_count": 1.0,
                "mcp.configured_tool_count": 2.0,
                "mcp.tool_injection_success_rate": 1.0,
            }
        },
        "agent_export": {
            "metrics": {
                "integration.export_generation_ms": 125.0,
                "integration.setup_success_rate": 1.0,
                "integration.export_target_count": 5.0,
            }
        },
        "shared_access": {
            "metrics": {
                "gateway.auth_validation_failures": 2.0,
                "gateway.accepted_api_key_count": 2.0,
                "shared_access.accepted_client_count": 2.0,
                "shared_access.rejected_request_count": 1.0,
            }
        },
        "persistent_session": {
            "metrics": {
                "persistent_session.active_session_count": 0.0,
                "persistent_session.remembered_session_count": 0.0,
                "persistent_session.expired_session_count": 0.0,
                "persistent_session.restore_success_rate": 100.0,
                "persistent_session.sign_out_latency_ms": 128.0,
            }
        },
        "sanitization": {
            "metrics": {
                "sanitized_output.enforcement_count": 2.0,
                "sanitized_output.blocked_html_fragment_count": 4.0,
                "sanitized_output.unsafe_uri_rejection_count": 4.0,
            }
        },
        "connection_lifecycle": {
            "metrics": {
                "disconnect.keepalive_gap_ms": 8.0,
                "disconnect.recovery_latency_ms": 12.0,
                "disconnect.resume_success_rate": 100.0,
                "disconnect.terminal_failure_count": 1.0,
            }
        },
        "closure_audit": {
            "metrics": {
                "closure_audit.blocker_count": 0.0,
                "closure_audit.evidence_gap_count": 0.0,
            }
        },
        "summary": {
            "required_probe_count": required_probe_count,
            "missing_probe_count": 0.0,
            "failed_threshold_count": 0.0,
        },
    }


def _passing_evaluation_compare_evidence(verdict: str = "improvement") -> dict[str, object]:
    return {
        "suite_id": "mmlu",
        "base_model_id": "melix-dev-text",
        "target_model_id": "melix-dev-text-lora-a",
        "sample_size": 8,
        "effect_threshold": 0.1,
        "verdict": verdict,
        "metrics": {
            "eval.compare.delta_accuracy": 0.5,
            "eval.compare.effect_threshold": 0.1,
        },
        "category_breakdown": {
            "math": {
                "sample_size": 8,
                "base_accuracy": 0.5,
                "target_accuracy": 1.0,
                "delta_accuracy": 0.5,
            }
        },
        "statistical_evidence": {
            "sample_size": 8,
            "delta_accuracy": 0.5,
            "bootstrap": {
                "method": "paired_bootstrap_percentile",
                "confidence_level": 0.95,
                "lower_bound": 0.12,
                "upper_bound": 0.84,
                "crosses_zero": False,
                "iterations": 400,
                "seed": 9,
            },
            "analytical": {
                "method": "paired_difference_normal_approximation",
                "confidence_level": 0.95,
                "lower_bound": 0.18,
                "upper_bound": 0.82,
                "crosses_zero": False,
            },
        },
        "release_gate_summary": {
            "verdict": verdict,
            "reason": "delta_exceeds_threshold_with_supported_intervals"
            if verdict != "inconclusive"
            else "confidence_intervals_cross_zero",
            "effect_threshold": 0.1,
            "delta_accuracy": 0.5 if verdict != "regression" else -0.5,
            "threshold_passed": verdict != "inconclusive",
            "both_intervals_same_side": verdict != "inconclusive",
        },
        "report_path": "/tmp/evaluation-compare-report.md",
    }


def _passing_real_workload_evidence() -> dict[str, object]:
    return {
        "summary": {
            "pass_count": 3.0,
            "failure_count": 0.0,
            "family_count": 3.0,
        },
        "families": {
            "qwen": {
                "family_id": "qwen",
                "model_id": "melix-dev-qwen-local",
                "scenario_id": "support-triage",
                "dataset_id": "melix.release.real_workload.qwen.v1",
                "metrics": {
                    "passed": 1.0,
                    "sample_count": 24.0,
                    "latency_ms": 842.0,
                    "throughput_tps": 31.4,
                    "peak_memory_gb": 8.6,
                },
            },
            "gemma": {
                "family_id": "gemma",
                "model_id": "melix-dev-gemma-local",
                "scenario_id": "product-qa",
                "dataset_id": "melix.release.real_workload.gemma.v1",
                "metrics": {
                    "passed": 1.0,
                    "sample_count": 18.0,
                    "latency_ms": 918.0,
                    "throughput_tps": 28.7,
                    "peak_memory_gb": 10.4,
                },
            },
            "kimi": {
                "family_id": "kimi",
                "model_id": "melix-dev-kimi-local",
                "scenario_id": "long-context-rewrite",
                "dataset_id": "melix.release.real_workload.kimi.v1",
                "metrics": {
                    "passed": 1.0,
                    "sample_count": 20.0,
                    "latency_ms": 887.0,
                    "throughput_tps": 29.9,
                    "peak_memory_gb": 9.8,
                },
            },
        },
    }


def _write_persisted_real_workload_evidence(jobs_root: Path) -> None:
    real_workload_root = jobs_root / "real_workload"
    real_workload_root.mkdir(parents=True, exist_ok=True)
    for family_id, payload in _passing_real_workload_evidence()["families"].items():
        (real_workload_root / f"{family_id}.json").write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )


def _write_persisted_evaluation_compare_evidence(
    jobs_root: Path,
    *,
    job_id: str = "eval-compare-release-gate",
    suite_id: str = "mmlu",
    target_model_id: str = "melix-dev-text-lora-a",
    verdict: str = "improvement",
    effect_threshold: float = 0.1,
    confidence_level: float = 0.95,
    bootstrap_iterations: int = 400,
    created_at_unix_ms: int = 1712600000000,
) -> dict[str, object]:
    evaluation_root = jobs_root / "evaluation"
    run_root = evaluation_root / "runs" / job_id
    store = EvaluationStore()
    compare_job = build_evaluation_compare_job_record(
        job_id=job_id,
        base_model_id="melix-dev-text",
        target_model_ids=(target_model_id,),
        task_kind="text-generation",
        source_repo="melix.release-gate.fixture",
        suite_id=suite_id,
        dataset_id=f"{suite_id}.dev.v1",
        sample_size=8,
        scoring_mode="multiple_choice_accuracy",
        parameters={"compare_mode": "base_vs_targets"},
        status="completed",
        output_dir=str(run_root),
        created_at_unix_ms=created_at_unix_ms,
        updated_at_unix_ms=created_at_unix_ms + 500,
    )
    compare_summary = build_evaluation_compare_summary_record(
        job_id=job_id,
        base_model_id="melix-dev-text",
        target_model_id=target_model_id,
        suite_id=suite_id,
        dataset_id=f"{suite_id}.dev.v1",
        sample_size=8,
        scoring_mode="multiple_choice_accuracy",
        win_count=6 if verdict == "improvement" else 1,
        loss_count=1 if verdict == "improvement" else 6,
        tie_count=1,
        regression_count=0 if verdict == "improvement" else 5,
        base_accuracy=0.5,
        target_accuracy=0.75 if verdict == "improvement" else 0.25,
        delta_accuracy=0.25 if verdict == "improvement" else -0.25,
        effect_threshold=effect_threshold,
        verdict=verdict,
        category_breakdown={
            "math": {
                "sample_size": 8,
                "base_accuracy": 0.5,
                "target_accuracy": 0.75 if verdict == "improvement" else 0.25,
                "delta_accuracy": 0.25 if verdict == "improvement" else -0.25,
            }
        },
        statistical_evidence={
            "sample_size": 8,
            "delta_accuracy": 0.25 if verdict == "improvement" else -0.25,
            "bootstrap": {
                "method": "paired_bootstrap_percentile",
                "confidence_level": confidence_level,
                "lower_bound": 0.12 if verdict == "improvement" else -0.41,
                "upper_bound": 0.41 if verdict == "improvement" else -0.12,
                "crosses_zero": False,
                "iterations": bootstrap_iterations,
                "seed": 9,
            },
            "analytical": {
                "method": "paired_difference_normal_approximation",
                "confidence_level": confidence_level,
                "lower_bound": 0.1 if verdict == "improvement" else -0.38,
                "upper_bound": 0.38 if verdict == "improvement" else -0.1,
                "crosses_zero": False,
            },
        },
        release_gate_summary={
            "verdict": verdict,
            "reason": "delta_exceeds_threshold_with_supported_intervals",
            "effect_threshold": effect_threshold,
            "delta_accuracy": 0.25 if verdict == "improvement" else -0.25,
            "threshold_passed": True,
            "both_intervals_same_side": True,
        },
        duration_seconds=0.25,
        metrics={"eval.compare.delta_accuracy": 0.25 if verdict == "improvement" else -0.25},
        report_path=str(run_root / "evaluation-compare-report.md"),
    )
    store.persist_compare_result(
        jobs_root=evaluation_root,
        job=compare_job,
        summaries=(compare_summary,),
    )
    return compare_summary.to_dict()


def _write_persisted_multi_target_evaluation_compare_evidence(
    jobs_root: Path,
    *,
    job_id: str = "eval-compare-multi-target",
    suite_id: str = "mmlu",
    targets: tuple[tuple[str, str], ...] = (
        ("melix-dev-text-lora-a", "improvement"),
        ("melix-dev-text-lora-b", "regression"),
    ),
    created_at_unix_ms: int = 1712600000000,
) -> tuple[dict[str, object], ...]:
    evaluation_root = jobs_root / "evaluation"
    run_root = evaluation_root / "runs" / job_id
    store = EvaluationStore()
    compare_job = build_evaluation_compare_job_record(
        job_id=job_id,
        base_model_id="melix-dev-text",
        target_model_ids=tuple(target_model_id for target_model_id, _ in targets),
        task_kind="text-generation",
        source_repo="melix.release-gate.fixture",
        suite_id=suite_id,
        dataset_id=f"{suite_id}.dev.v1",
        sample_size=8,
        scoring_mode="multiple_choice_accuracy",
        parameters={"compare_mode": "base_vs_targets"},
        status="completed",
        output_dir=str(run_root),
        created_at_unix_ms=created_at_unix_ms,
        updated_at_unix_ms=created_at_unix_ms + 500,
    )
    summaries = tuple(
        build_evaluation_compare_summary_record(
            job_id=job_id,
            base_model_id="melix-dev-text",
            target_model_id=target_model_id,
            suite_id=suite_id,
            dataset_id=f"{suite_id}.dev.v1",
            sample_size=8,
            scoring_mode="multiple_choice_accuracy",
            win_count=6 if verdict == "improvement" else 1,
            loss_count=1 if verdict == "improvement" else 6,
            tie_count=1,
            regression_count=0 if verdict == "improvement" else 5,
            base_accuracy=0.5,
            target_accuracy=0.75 if verdict == "improvement" else 0.25,
            delta_accuracy=0.25 if verdict == "improvement" else -0.25,
            effect_threshold=0.1,
            verdict=verdict,
            category_breakdown={
                "math": {
                    "sample_size": 8,
                    "base_accuracy": 0.5,
                    "target_accuracy": 0.75 if verdict == "improvement" else 0.25,
                    "delta_accuracy": 0.25 if verdict == "improvement" else -0.25,
                }
            },
            statistical_evidence={
                "sample_size": 8,
                "delta_accuracy": 0.25 if verdict == "improvement" else -0.25,
                "bootstrap": {
                    "method": "paired_bootstrap_percentile",
                    "confidence_level": 0.95,
                    "lower_bound": 0.12 if verdict == "improvement" else -0.41,
                    "upper_bound": 0.41 if verdict == "improvement" else -0.12,
                    "crosses_zero": False,
                    "iterations": 400,
                    "seed": 9,
                },
                "analytical": {
                    "method": "paired_difference_normal_approximation",
                    "confidence_level": 0.95,
                    "lower_bound": 0.1 if verdict == "improvement" else -0.38,
                    "upper_bound": 0.38 if verdict == "improvement" else -0.1,
                    "crosses_zero": False,
                },
            },
            release_gate_summary={
                "verdict": verdict,
                "reason": "delta_exceeds_threshold_with_supported_intervals",
                "effect_threshold": 0.1,
                "delta_accuracy": 0.25 if verdict == "improvement" else -0.25,
                "threshold_passed": True,
                "both_intervals_same_side": True,
            },
            duration_seconds=0.25,
            metrics={"eval.compare.delta_accuracy": 0.25 if verdict == "improvement" else -0.25},
            report_path=str(run_root / "evaluation-compare-report.md"),
        )
        for target_model_id, verdict in targets
    )
    store.persist_compare_result(
        jobs_root=evaluation_root,
        job=compare_job,
        summaries=summaries,
    )
    return tuple(summary.to_dict() for summary in summaries)


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
    assert evidence["metrics"]["bench.smoke.ttft_ms"] >= 0.0
    assert evidence["metrics"]["bench.smoke.tokens_per_second"] >= 45.0
    assert evidence["metrics"]["bench.latency.p95_ms"] <= 50.0
    assert evidence["metrics"]["bench.latency.p95_ms"] >= evidence["metrics"]["bench.latency.p50_ms"]
    assert evidence["job"]["schema_version"] == "melix.serving_benchmark_job.v1"
    assert evidence["job"]["job_id"] == "model-ops-0001"
    assert evidence["job"]["suites"] == ["smoke", "latency"]
    assert evidence["job"]["output_dir"].endswith("/bench/runs/model-ops-0001")
    assert [row["suite"] for row in evidence["results"]] == ["latency", "smoke"]


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


def test_release_gate_benchmark_fetcher_covers_curated_splits_pagination_and_errors() -> None:
    smoke_splits = release_gates_module._release_gate_benchmark_fetcher(
        "splits",
        {"dataset": "HuggingFaceH4/ultrachat_200k"},
    )
    latency_splits = release_gates_module._release_gate_benchmark_fetcher(
        "splits",
        {"dataset": "databricks/databricks-dolly-15k"},
    )
    paged_rows = release_gates_module._release_gate_benchmark_fetcher(
        "rows",
        {"dataset": "HuggingFaceH4/ultrachat_200k", "offset": "100"},
    )

    assert smoke_splits["splits"][0]["split"] == "train_sft"
    assert latency_splits["splits"][0]["split"] == "train"
    assert paged_rows == {"rows": []}

    with pytest.raises(RuntimeError) as error:
        release_gates_module._release_gate_benchmark_fetcher(
            "splits",
            {"dataset": "missing/dataset"},
        )

    assert "Unsupported release-gate benchmark dataset" in str(error.value)


def test_collect_training_evidence_returns_required_metrics(tmp_path: Path) -> None:
    evidence = collect_training_evidence(tmp_path / "jobs")

    assert evidence["adapter_name"] == "melix-dev-adapter"
    assert evidence["dataset_uri"] == str(tmp_path / "jobs" / "datasets" / "melix-dev")
    assert evidence["training_duration_ms"] == 1420.0
    assert evidence["adapter_publish_ms"] == 118.0


def test_load_release_gate_policy_includes_real_workload_family_rules() -> None:
    policy = load_release_gate_policy()

    assert policy["real_workload"]["summary"]["pass_count"]["min"] == 3.0
    assert policy["real_workload"]["summary"]["failure_count"]["max"] == 0.0
    assert set(policy["real_workload"]["families"].keys()) == {"qwen", "gemma", "kimi"}


def test_collect_real_workload_evidence_reports_qwen_gemma_and_kimi_families(
    tmp_path: Path,
) -> None:
    _write_persisted_real_workload_evidence(tmp_path / "jobs")
    evidence = release_gates_module.collect_real_workload_evidence(tmp_path / "jobs")

    assert evidence["summary"]["pass_count"] == 3.0
    assert evidence["summary"]["failure_count"] == 0.0
    assert evidence["summary"]["family_count"] == 3.0
    assert set(evidence["families"].keys()) == {"qwen", "gemma", "kimi"}
    assert evidence["families"]["qwen"]["metrics"]["throughput_tps"] >= 20.0
    assert evidence["families"]["gemma"]["metrics"]["latency_ms"] <= 1500.0
    assert evidence["families"]["kimi"]["metrics"]["sample_count"] >= 16.0


def test_collect_real_workload_evidence_handles_policy_fallback_and_unknown_families(
    tmp_path: Path,
) -> None:
    fallback = release_gates_module.collect_real_workload_evidence(
        tmp_path / "jobs",
        policy={"families": {}},
    )
    unknown_family = release_gates_module.collect_real_workload_evidence(
        tmp_path / "jobs",
        policy={"families": {"unknown": {"passed": {"min": 1.0}}}},
    )

    assert fallback["summary"]["family_count"] == 0.0
    assert fallback["families"] == {}
    assert unknown_family["summary"]["family_count"] == 0.0
    assert unknown_family["families"] == {}


def test_evaluate_real_workload_evidence_reports_missing_family_metrics_and_summary_issues() -> None:
    policy = {
        "summary": {"pass_count": {"min": 1.0}},
        "families": {
            "skip": "invalid",
            "qwen": {"passed": {"min": 1.0}},
            "gemma": {"passed": {"min": 1.0}},
        },
    }

    missing_metrics = release_gates_module.evaluate_real_workload_evidence(
        {
            "summary": {"pass_count": 1.0, "failure_count": 0.0, "family_count": 1.0},
            "families": {"qwen": {"family_id": "qwen"}},
        },
        policy,
    )
    assert "real_workload.families.qwen.metrics is missing" in missing_metrics
    assert "real_workload.families.gemma is missing" in missing_metrics

    missing_summary = release_gates_module.evaluate_real_workload_evidence(
        {
            "summary": {"pass_count": 1.0},
            "families": {
                "qwen": {
                    "metrics": {"passed": 1.0},
                }
            },
        },
        {"summary": {}, "families": {"qwen": {"passed": {"min": 1.0}}}},
    )
    assert "real_workload.summary.failure_count is missing" in missing_summary
    assert "real_workload.summary.family_count is missing" in missing_summary

    malformed_summary = release_gates_module.evaluate_real_workload_evidence(
        {
            "summary": {
                "pass_count": "one",
                "failure_count": 0.0,
                "family_count": 5.0,
            },
            "families": {
                "qwen": {
                    "metrics": {"passed": 1.0},
                }
            },
        },
        {"summary": {}, "families": {"qwen": {"passed": {"min": 1.0}}}},
    )
    assert "real_workload.summary.pass_count must be numeric" in malformed_summary
    assert any("did not match computed" in failure for failure in malformed_summary)


def test_collect_m9_collectors_delegate_to_expected_smoke_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    delegated_calls: list[tuple[str, tuple[str, ...]]] = []

    def fake_run_python_json_script(
        root: Path,
        script_relative_path: str,
        *script_args: str,
    ) -> dict[str, object]:
        delegated_calls.append((script_relative_path, script_args))
        return {"metrics": {script_relative_path: 1.0}}

    class FakeClosureAudit:
        def to_dict(self) -> dict[str, object]:
            return {
                "metrics": {
                    "closure_audit.blocker_count": 0.0,
                    "closure_audit.evidence_gap_count": 0.0,
                }
            }

    monkeypatch.setattr(
        release_gates_module,
        "_run_python_json_script",
        fake_run_python_json_script,
    )
    monkeypatch.setattr(
        release_gates_module,
        "build_closure_audit",
        lambda root: FakeClosureAudit(),
    )
    policy = {
        "mcp": {"scripts/m9_mcp_smoke.py": {"min": 1.0}},
        "agent_export": {"scripts/m9_agent_export_smoke.py": {"min": 1.0}},
        "shared_access": {"scripts/m9_shared_access_smoke.py": {"min": 1.0}},
        "persistent_session": {"scripts/m9_persistent_session_smoke.py": {"min": 1.0}},
        "sanitization": {
            "sanitized_output.enforcement_count": {"min": 1.0},
            "sanitized_output.blocked_html_fragment_count": {"min": 1.0},
            "sanitized_output.unsafe_uri_rejection_count": {"min": 1.0},
        },
        "connection_lifecycle": {"scripts/m9_connection_smoke.py": {"min": 1.0}},
        "closure_audit": {
            "closure_audit.blocker_count": {"max": 0.0},
            "closure_audit.evidence_gap_count": {"max": 0.0},
        },
    }

    report = release_gates_module.collect_m9_evidence(repo_root, policy=policy)

    assert report["summary"]["required_probe_count"] == 10.0
    assert report["summary"]["missing_probe_count"] == 0.0
    assert report["summary"]["failed_threshold_count"] == 0.0
    assert delegated_calls == [
        (
            "scripts/m9_mcp_smoke.py",
            ("--repo-root", str(repo_root.resolve()), "--json"),
        ),
        ("scripts/m9_agent_export_smoke.py", ("--json",)),
        ("scripts/m9_shared_access_smoke.py", ("--json",)),
        (
            "scripts/m9_persistent_session_smoke.py",
            ("--repo-root", str(repo_root.resolve()), "--json"),
        ),
        (
            "scripts/m9_connection_smoke.py",
            ("--repo-root", str(repo_root.resolve()), "--json"),
        ),
    ]
    assert report["sanitization"]["metrics"]["sanitized_output.enforcement_count"] == 2.0
    assert (
        report["closure_audit"]["metrics"]["closure_audit.blocker_count"] == 0.0
    )


def test_evaluate_m9_release_evidence_ignores_non_dict_policy_entries() -> None:
    failures, summary = release_gates_module.evaluate_m9_release_evidence(
        {"mcp": {"metrics": {"mcp.tool_injection_count": 1.0}}},
        {
            "mcp": {"mcp.tool_injection_count": {"min": 1.0}},
            "notes": "ignore me",
        },
    )

    assert failures == []
    assert summary["required_probe_count"] == 1.0
    assert summary["missing_probe_count"] == 0.0
    assert summary["failed_threshold_count"] == 0.0


def test_run_python_json_script_sets_repo_pythonpath_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    existing_pythonpath = "existing-pythonpath"
    monkeypatch.setenv("PYTHONPATH", existing_pythonpath)

    captured_env: dict[str, str] = {}

    def fake_subprocess_run(command, **kwargs):
        nonlocal captured_env
        captured_env = dict(kwargs["env"])

        class Completed:
            stdout = json.dumps({"ok": True})

        return Completed()

    monkeypatch.setattr(release_gates_module.subprocess, "run", fake_subprocess_run)

    payload = release_gates_module._run_python_json_script(
        repo_root,
        "scripts/fake.py",
        "--json",
    )

    assert payload == {"ok": True}
    assert captured_env["PYTHONPATH"].split(":")[0] == str(repo_root.resolve())
    assert captured_env["PYTHONPATH"].split(":")[1] == str(
        repo_root.resolve() / "services" / "mlx-worker-python"
    )
    assert captured_env["PYTHONPATH"].split(":")[-1] == existing_pythonpath


def test_run_python_json_script_requires_stdout_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    def fake_subprocess_run(command, **kwargs):
        class Completed:
            stdout = ""

        return Completed()

    monkeypatch.setattr(release_gates_module.subprocess, "run", fake_subprocess_run)

    with pytest.raises(RuntimeError, match="did not emit JSON output"):
        release_gates_module._run_python_json_script(repo_root, "scripts/fake.py", "--json")


def test_collect_audio_product_evidence_distinguishes_slim_and_full_builds(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    evidence = collect_audio_product_evidence(repo_root)

    checks = evidence["checks"]
    metrics = evidence["metrics"]
    variants = evidence["variants"]

    assert checks["slim_requires_runtime_pack_download"] is True
    assert checks["full_runtime_pack_preinstalled"] is True
    assert checks["slim_runtime_pack_metadata_exists"] is True
    assert checks["full_runtime_pack_metadata_exists"] is True
    assert checks["slim_managed_model_metadata_exists"] is True
    assert checks["full_managed_model_metadata_exists"] is True
    assert metrics["slim.audio_first_use_blocked_runtime_pack_count"] == 1.0
    assert metrics["slim.audio_first_use_blocked_model_count"] == 1.0
    assert metrics["full.audio_first_use_blocked_runtime_pack_count"] == 0.0
    assert metrics["full.audio_first_use_blocked_model_count"] == 1.0
    assert metrics["slim.audio_runtime_pack_recovery_success_rate"] == 100.0
    assert metrics["full.audio_runtime_pack_recovery_success_rate"] == 100.0
    assert variants["slim"]["runtime_pack"]["pack_id"] == "melix-audio-runtime-pack"
    assert variants["full"]["runtime_pack"]["version"] == "0.3.0"


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
        "audio": {
            "checks": {
                "slim_requires_runtime_pack_download": False,
                "full_runtime_pack_preinstalled": False,
                "slim_runtime_pack_metadata_exists": False,
                "full_runtime_pack_metadata_exists": False,
                "slim_managed_model_metadata_exists": False,
                "full_managed_model_metadata_exists": False,
            },
            "metrics": {
                "slim.audio_runtime_pack_install_ms": 999.0,
                "slim.audio_model_download_ms": 999.0,
                "slim.audio_first_use_blocked_runtime_pack_count": 0.0,
                "slim.audio_first_use_blocked_model_count": 0.0,
                "slim.audio_runtime_pack_recovery_success_rate": 0.0,
                "full.audio_runtime_pack_install_ms": 1.0,
                "full.audio_model_download_ms": 999.0,
                "full.audio_first_use_blocked_runtime_pack_count": 1.0,
                "full.audio_first_use_blocked_model_count": 0.0,
                "full.audio_runtime_pack_recovery_success_rate": 0.0,
            },
        },
        "real_workload": _passing_real_workload_evidence(),
        "m9": _passing_m9_evidence(),
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
    assert "checks.slim_requires_runtime_pack_download must be true" in failures
    assert "checks.full_runtime_pack_preinstalled must be true" in failures
    assert "slim.audio_first_use_blocked_runtime_pack_count=0.00 fell below minimum 1.00" in failures
    assert "full.audio_runtime_pack_install_ms=1.00 exceeded maximum 0.00" in failures
    assert "quantization evidence is missing" in failures


def test_evaluate_release_gate_fails_closed_for_missing_real_workload_evidence() -> None:
    policy = load_release_gate_policy()
    report = {
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
        "audio": {
            "checks": {
                "slim_requires_runtime_pack_download": True,
                "full_runtime_pack_preinstalled": True,
                "slim_runtime_pack_metadata_exists": True,
                "full_runtime_pack_metadata_exists": True,
                "slim_managed_model_metadata_exists": True,
                "full_managed_model_metadata_exists": True,
            },
            "metrics": {
                "slim.audio_runtime_pack_install_ms": 10.0,
                "slim.audio_model_download_ms": 15.0,
                "slim.audio_first_use_blocked_runtime_pack_count": 1.0,
                "slim.audio_first_use_blocked_model_count": 1.0,
                "slim.audio_runtime_pack_recovery_success_rate": 100.0,
                "full.audio_runtime_pack_install_ms": 0.0,
                "full.audio_model_download_ms": 15.0,
                "full.audio_first_use_blocked_runtime_pack_count": 0.0,
                "full.audio_first_use_blocked_model_count": 1.0,
                "full.audio_runtime_pack_recovery_success_rate": 100.0,
            },
        },
        "runtime_core": {
            "multi_model_ready_count": 3.0,
            "multi_model_request_success_rate": 100.0,
            "prefill_memory_guard_rejection_count": 1.0,
            "prefill_memory_guard_success_rate": 100.0,
        },
        "quantization": {
            "summary": {"profile_count": 7, "smoke_pass_rate": 100.0},
            "profiles": {
                pid: {
                    "job_ms": 1.0,
                    "artifact_bytes": 670.0,
                    "manifest_bytes": 1747.0,
                    "calibration_sample_count": 32.0,
                    "smoke_test_passed": 1.0,
                }
                for pid in ("q2", "q3", "q4", "q5", "q6", "q7", "q8")
            },
        },
        "evaluation": {
            "metrics": {
                "eval.mmlu.accuracy": 0.75,
            },
        },
        "evaluation_compare": _passing_evaluation_compare_evidence(),
        "m9": _passing_m9_evidence(),
    }

    failures = evaluate_release_gate(report, policy)

    assert "real_workload evidence is missing" in failures


def test_build_release_gate_report_includes_m9_summary_when_collectors_pass(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_persisted_real_workload_evidence(tmp_path / "jobs")
    _write_persisted_evaluation_compare_evidence(tmp_path / "jobs")
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
    monkeypatch.setattr(
        release_gates_module,
        "collect_m9_evidence",
        lambda repo_root, policy=None: _passing_m9_evidence(policy),
        raising=False,
    )

    report = build_release_gate_report(
        repo_root,
        jobs_root=tmp_path / "jobs",
        policy={
            **DEFAULT_RELEASE_GATE_POLICY,
            "m9": {
                "mcp": {"mcp.tool_injection_success_rate": {"min": 1.0}},
                "agent_export": {"integration.setup_success_rate": {"min": 1.0}},
                "shared_access": {"shared_access.accepted_client_count": {"min": 1.0}},
                "persistent_session": {
                    "persistent_session.restore_success_rate": {"min": 100.0}
                },
                "sanitization": {"sanitized_output.enforcement_count": {"min": 1.0}},
                "connection_lifecycle": {
                    "disconnect.resume_success_rate": {"min": 100.0}
                },
                "closure_audit": {
                    "closure_audit.blocker_count": {"max": 0.0},
                    "closure_audit.evidence_gap_count": {"max": 0.0},
                },
            },
        },
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

    assert report["m9"]["summary"]["required_probe_count"] == 8.0
    assert report["m9"]["summary"]["missing_probe_count"] == 0.0
    assert report["m9"]["summary"]["failed_threshold_count"] == 0.0
    assert report["passed"] is True


def test_evaluate_release_gate_fails_closed_for_missing_or_regressed_m9_evidence() -> None:
    policy = {
        **DEFAULT_RELEASE_GATE_POLICY,
        "m9": {
            "mcp": {"mcp.tool_injection_success_rate": {"min": 1.0}},
            "agent_export": {"integration.setup_success_rate": {"min": 1.0}},
            "shared_access": {"shared_access.accepted_client_count": {"min": 1.0}},
            "persistent_session": {"persistent_session.restore_success_rate": {"min": 100.0}},
            "sanitization": {"sanitized_output.enforcement_count": {"min": 1.0}},
            "connection_lifecycle": {"disconnect.resume_success_rate": {"min": 100.0}},
            "closure_audit": {
                "closure_audit.blocker_count": {"max": 0.0},
                "closure_audit.evidence_gap_count": {"max": 0.0},
            },
        },
    }
    report = {
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
        "audio": {
            "checks": {
                "slim_requires_runtime_pack_download": True,
                "full_runtime_pack_preinstalled": True,
                "slim_runtime_pack_metadata_exists": True,
                "full_runtime_pack_metadata_exists": True,
                "slim_managed_model_metadata_exists": True,
                "full_managed_model_metadata_exists": True,
            },
            "metrics": {
                "slim.audio_runtime_pack_install_ms": 12.0,
                "slim.audio_model_download_ms": 18.0,
                "slim.audio_first_use_blocked_runtime_pack_count": 1.0,
                "slim.audio_first_use_blocked_model_count": 1.0,
                "slim.audio_runtime_pack_recovery_success_rate": 100.0,
                "full.audio_runtime_pack_install_ms": 0.0,
                "full.audio_model_download_ms": 17.0,
                "full.audio_first_use_blocked_runtime_pack_count": 0.0,
                "full.audio_first_use_blocked_model_count": 1.0,
                "full.audio_runtime_pack_recovery_success_rate": 100.0,
            },
        },
        "runtime_core": {
            "multi_model_ready_count": 3.0,
            "multi_model_request_success_rate": 100.0,
            "prefill_memory_guard_rejection_count": 1.0,
            "prefill_memory_guard_success_rate": 100.0,
        },
        "quantization": {
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
        "m9": {
            "mcp": {"metrics": {"mcp.tool_injection_success_rate": 1.0}},
            "agent_export": {"metrics": {"integration.setup_success_rate": 1.0}},
            "shared_access": {"metrics": {}},
            "persistent_session": {
                "metrics": {"persistent_session.restore_success_rate": 100.0}
            },
            "sanitization": {"metrics": {"sanitized_output.enforcement_count": 2.0}},
            "connection_lifecycle": {
                "metrics": {"disconnect.resume_success_rate": 0.0}
            },
            "closure_audit": {
                "metrics": {
                    "closure_audit.blocker_count": 1.0,
                    "closure_audit.evidence_gap_count": 0.0,
                }
            },
            "summary": {
                "required_probe_count": 7.0,
                "missing_probe_count": 1.0,
                "failed_threshold_count": 2.0,
            },
        },
    }

    failures = evaluate_release_gate(report, policy)

    assert "m9.shared_access.shared_access.accepted_client_count is missing" in failures
    assert (
        "m9.connection_lifecycle.disconnect.resume_success_rate=0.00 fell below minimum 100.00"
        in failures
    )
    assert "m9.closure_audit.closure_audit.blocker_count=1.00 exceeded maximum 0.00" in failures


def test_build_release_gate_report_passes_with_supplied_recovery_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_persisted_real_workload_evidence(tmp_path / "jobs")
    _write_persisted_evaluation_compare_evidence(tmp_path / "jobs")
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
    monkeypatch.setattr(
        release_gates_module,
        "collect_m9_evidence",
        lambda repo_root, policy=None: _passing_m9_evidence(policy),
        raising=False,
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
    assert report["audio"]["checks"]["slim_requires_runtime_pack_download"] is True
    assert report["audio"]["checks"]["full_runtime_pack_preinstalled"] is True


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
    monkeypatch.setattr(
        release_gates_module,
        "collect_m9_evidence",
        lambda repo_root, policy=None: _passing_m9_evidence(policy),
        raising=False,
    )
    monkeypatch.setattr(
        release_gates_module,
        "collect_evaluation_compare_evidence",
        lambda jobs_root, policy=None: _passing_evaluation_compare_evidence(),
    )
    monkeypatch.setattr(
        release_gates_module,
        "collect_real_workload_evidence",
        lambda jobs_root, policy=None: _passing_real_workload_evidence(),
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
            "audio": {
                "checks": {
                    "slim_requires_runtime_pack_download": True,
                    "full_runtime_pack_preinstalled": True,
                    "slim_runtime_pack_metadata_exists": True,
                    "full_runtime_pack_metadata_exists": True,
                    "slim_managed_model_metadata_exists": True,
                    "full_managed_model_metadata_exists": True,
                },
                "metrics": {
                    "slim.audio_runtime_pack_install_ms": "fast",
                    "slim.audio_model_download_ms": 15.0,
                    "slim.audio_first_use_blocked_runtime_pack_count": 1.0,
                    "slim.audio_first_use_blocked_model_count": 1.0,
                    "slim.audio_runtime_pack_recovery_success_rate": 100.0,
                    "full.audio_runtime_pack_install_ms": 0.0,
                    "full.audio_model_download_ms": 15.0,
                    "full.audio_first_use_blocked_runtime_pack_count": 0.0,
                    "full.audio_first_use_blocked_model_count": 1.0,
                    "full.audio_runtime_pack_recovery_success_rate": 100.0,
                },
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
            "real_workload": _passing_real_workload_evidence(),
            "m9": _passing_m9_evidence(),
        },
        load_release_gate_policy(),
    )

    assert "checks.environment_script_exists is missing" in failures
    assert "bench.smoke.ttft_ms must be numeric" in failures
    assert "multi_model_ready_count must be numeric" in failures
    assert "slim.audio_runtime_pack_install_ms must be numeric" in failures
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
            "audio": {
                "checks": {
                    "slim_requires_runtime_pack_download": True,
                    "full_runtime_pack_preinstalled": True,
                    "slim_runtime_pack_metadata_exists": True,
                    "full_runtime_pack_metadata_exists": True,
                    "slim_managed_model_metadata_exists": True,
                    "full_managed_model_metadata_exists": True,
                },
                "metrics": {
                    "slim.audio_runtime_pack_install_ms": 10.0,
                    "slim.audio_model_download_ms": 15.0,
                    "slim.audio_first_use_blocked_runtime_pack_count": 1.0,
                    "slim.audio_first_use_blocked_model_count": 1.0,
                    "slim.audio_runtime_pack_recovery_success_rate": 100.0,
                    "full.audio_runtime_pack_install_ms": 0.0,
                    "full.audio_model_download_ms": 15.0,
                    "full.audio_first_use_blocked_runtime_pack_count": 0.0,
                    "full.audio_first_use_blocked_model_count": 1.0,
                    "full.audio_runtime_pack_recovery_success_rate": 100.0,
                },
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


def test_default_policy_includes_audio_section() -> None:
    assert "audio" in DEFAULT_RELEASE_GATE_POLICY
    assert "slim.audio_first_use_blocked_runtime_pack_count" in DEFAULT_RELEASE_GATE_POLICY["audio"]
    assert DEFAULT_RELEASE_GATE_POLICY["audio"]["full.audio_runtime_pack_install_ms"]["max"] == 0.0


def test_default_policy_includes_evaluation_section() -> None:
    assert "evaluation" in DEFAULT_RELEASE_GATE_POLICY
    assert "eval.mmlu.typed_score_mean" in DEFAULT_RELEASE_GATE_POLICY["evaluation"]
    assert DEFAULT_RELEASE_GATE_POLICY["evaluation"]["eval.mmlu.typed_score_mean"]["min"] == 0.5
    assert "evaluation_compare" in DEFAULT_RELEASE_GATE_POLICY
    assert DEFAULT_RELEASE_GATE_POLICY["evaluation_compare"]["mmlu"]["effect_threshold"] == 0.1
    assert DEFAULT_RELEASE_GATE_POLICY["evaluation_compare"]["mmlu"]["required_verdict"] == "improvement"


def test_checked_in_release_gate_policy_includes_evaluation_thresholds() -> None:
    repo_root = Path(__file__).resolve().parents[3]

    policy = load_release_gate_policy(repo_root / "infra" / "release" / "phase8-release-gate-policy.json")

    assert "audio" in policy
    assert policy["audio"]["slim.audio_runtime_pack_recovery_success_rate"]["min"] == 100.0
    assert "evaluation" in policy
    assert policy["evaluation"]["eval.mmlu.typed_score_mean"]["min"] == 0.5
    assert "evaluation_compare" in policy
    assert policy["evaluation_compare"]["mmlu"]["bootstrap_iterations"] == 400
    assert "m9" in policy
    assert policy["m9"]["agent_export"]["integration.export_generation_ms"]["min"] == 0.0
    assert policy["m9"]["shared_access"]["gateway.auth_validation_failures"]["min"] == 1.0


def test_collect_evaluation_evidence_returns_metrics(tmp_path: Path) -> None:
    evidence = collect_evaluation_evidence(tmp_path / "jobs")

    assert "metrics" in evidence
    assert evidence["metrics"]["eval.mmlu.typed_score_mean"] == 1.0
    assert evidence["job"]["suite_id"] == "mmlu"
    assert evidence["result"]["suite_id"] == "mmlu"


def test_release_gate_evaluation_backend_covers_cancel_and_non_arithmetic_prompt() -> None:
    backend = release_gates_module._ReleaseGateEvaluationBackend()
    canceled = type("CancelEvent", (), {"is_set": lambda self: True})()
    active = type("CancelEvent", (), {"is_set": lambda self: False})()

    assert list(backend.generate_tokens({}, "2 + 2 ?", None, canceled)) == []
    assert list(backend.generate_tokens({}, "hello world", None, active)) == ["Answer: 0"]


def test_collect_evaluation_compare_evidence_returns_release_summary(tmp_path: Path) -> None:
    expected = _write_persisted_evaluation_compare_evidence(
        tmp_path / "jobs",
        job_id="eval-compare-real-artifact",
        target_model_id="melix-dev-text-lora-real",
        verdict="regression",
        effect_threshold=0.2,
        confidence_level=0.99,
        bootstrap_iterations=512,
    )
    evidence = collect_evaluation_compare_evidence(tmp_path / "jobs")

    assert evidence["suite_id"] == "mmlu"
    assert evidence["job_id"] == expected["job_id"]
    assert evidence["target_model_id"] == "melix-dev-text-lora-real"
    assert evidence["verdict"] == "regression"
    assert evidence["effect_threshold"] == 0.2
    assert evidence["statistical_evidence"]["bootstrap"]["iterations"] == 512
    assert evidence["statistical_evidence"]["bootstrap"]["confidence_level"] == 0.99
    assert evidence["release_gate_summary"]["both_intervals_same_side"] is True


def test_collect_evaluation_compare_evidence_prefers_custom_policy_suite_when_present(
    tmp_path: Path,
) -> None:
    _write_persisted_evaluation_compare_evidence(
        tmp_path / "jobs",
        job_id="eval-compare-gsm8k-artifact",
        suite_id="gsm8k",
        target_model_id="melix-dev-text-lora-gsm8k",
        verdict="improvement",
    )

    evidence = collect_evaluation_compare_evidence(
        tmp_path / "jobs",
        policy={
            "gsm8k": {
                "effect_threshold": 0.05,
                "confidence_level": 0.9,
                "bootstrap_iterations": 200,
                "required_verdict": "improvement",
            }
        },
    )

    assert evidence["suite_id"] == "gsm8k"
    assert evidence["job_id"] == "eval-compare-gsm8k-artifact"
    assert evidence["target_model_id"] == "melix-dev-text-lora-gsm8k"


def test_collect_evaluation_compare_evidence_returns_all_target_summaries_for_latest_job(
    tmp_path: Path,
) -> None:
    _write_persisted_multi_target_evaluation_compare_evidence(
        tmp_path / "jobs",
        job_id="eval-compare-multi-target-artifact",
    )

    evidence = collect_evaluation_compare_evidence(tmp_path / "jobs")

    assert evidence["suite_id"] == "mmlu"
    assert evidence["job_id"] == "eval-compare-multi-target-artifact"
    target_summaries = evidence["target_summaries"]
    assert len(target_summaries) == 2
    assert {summary["target_model_id"] for summary in target_summaries} == {
        "melix-dev-text-lora-a",
        "melix-dev-text-lora-b",
    }


def test_collect_evaluation_compare_evidence_fails_closed_without_persisted_compare_artifacts(
    tmp_path: Path,
) -> None:
    evidence = collect_evaluation_compare_evidence(tmp_path / "jobs")

    assert evidence["suite_id"] == "mmlu"
    assert evidence["artifact_status"] == "missing"
    assert "persisted evaluation_compare artifacts" in evidence["reason"]
    assert "statistical_evidence" not in evidence


def test_evaluate_evaluation_compare_evidence_requires_suite_policy_and_statistical_shapes() -> None:
    assert release_gates_module._evaluate_evaluation_compare_evidence({}, {"mmlu": {}}) == [
        "evaluation_compare.suite_id is missing"
    ]
    assert release_gates_module._evaluate_evaluation_compare_evidence(
        {"suite_id": "mmlu"},
        {"mmlu": []},
    ) == [
        "evaluation_compare.mmlu policy is missing"
    ]
    assert release_gates_module._evaluate_evaluation_compare_evidence(
        {"suite_id": "mmlu", "statistical_evidence": []},
        {"mmlu": {}},
    ) == [
        "evaluation_compare.mmlu verdict= did not satisfy required verdict improvement",
        "evaluation_compare.mmlu effect_threshold=0.00 fell below policy threshold 0.10",
        "evaluation_compare.mmlu statistical_evidence is missing",
    ]

    report = _passing_evaluation_compare_evidence()
    report["statistical_evidence"] = {
        "bootstrap": [],
        "analytical": [],
    }

    failures = release_gates_module._evaluate_evaluation_compare_evidence(
        report,
        {"mmlu": {}},
    )

    assert "evaluation_compare.mmlu bootstrap evidence is missing" in failures
    assert "evaluation_compare.mmlu analytical evidence is missing" in failures


def test_evaluate_evaluation_compare_evidence_enforces_threshold_iterations_and_confidence() -> None:
    report = _passing_evaluation_compare_evidence()
    report["effect_threshold"] = 0.05
    report["statistical_evidence"]["bootstrap"]["iterations"] = 399
    report["statistical_evidence"]["bootstrap"]["confidence_level"] = 0.94

    failures = release_gates_module._evaluate_evaluation_compare_evidence(
        report,
        {
            "mmlu": {
                "required_verdict": "improvement",
                "effect_threshold": 0.1,
                "bootstrap_iterations": 400,
                "confidence_level": 0.95,
            }
        },
    )

    assert (
        "evaluation_compare.mmlu effect_threshold=0.05 fell below policy threshold 0.10"
        in failures
    )
    assert (
        "evaluation_compare.mmlu bootstrap_iterations=399 fell below required 400"
        in failures
    )


def test_evaluate_evaluation_compare_evidence_falls_back_to_default_suite_policy() -> None:
    report = _passing_evaluation_compare_evidence()
    report["effect_threshold"] = 0.05
    report["statistical_evidence"]["bootstrap"]["iterations"] = 399
    report["statistical_evidence"]["bootstrap"]["confidence_level"] = 0.94

    failures = release_gates_module._evaluate_evaluation_compare_evidence(
        report,
        {"other-suite": {"required_verdict": "regression"}},
    )

    assert (
        "evaluation_compare.mmlu effect_threshold=0.05 fell below policy threshold 0.10"
        in failures
    )
    assert (
        "evaluation_compare.mmlu bootstrap_iterations=399 fell below required 400"
        in failures
    )
    assert (
        "evaluation_compare.mmlu confidence_level=0.94 fell below required 0.95"
        in failures
    )
    assert (
        "evaluation_compare.mmlu confidence_level=0.94 fell below required 0.95"
        in failures
    )


def test_evaluate_evaluation_compare_evidence_checks_each_target_summary() -> None:
    report = {
        "suite_id": "mmlu",
        "job_id": "eval-compare-multi-target-artifact",
        "target_summaries": [
            _passing_evaluation_compare_evidence(),
            {
                **_passing_evaluation_compare_evidence(verdict="regression"),
                "target_model_id": "melix-dev-text-lora-b",
            },
        ],
    }

    failures = release_gates_module._evaluate_evaluation_compare_evidence(
        report,
        {"mmlu": {"required_verdict": "improvement"}},
    )

    assert (
        "evaluation_compare.mmlu target_model_id=melix-dev-text-lora-b verdict=regression "
        "did not satisfy required verdict improvement"
        in failures
    )


def test_evaluate_release_gate_fails_on_low_eval_primary_score() -> None:
    policy = load_release_gate_policy()
    report = {
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
        "audio": {
            "checks": {
                "slim_requires_runtime_pack_download": True,
                "full_runtime_pack_preinstalled": True,
                "slim_runtime_pack_metadata_exists": True,
                "full_runtime_pack_metadata_exists": True,
                "slim_managed_model_metadata_exists": True,
                "full_managed_model_metadata_exists": True,
            },
            "metrics": {
                "slim.audio_runtime_pack_install_ms": 10.0,
                "slim.audio_model_download_ms": 15.0,
                "slim.audio_first_use_blocked_runtime_pack_count": 1.0,
                "slim.audio_first_use_blocked_model_count": 1.0,
                "slim.audio_runtime_pack_recovery_success_rate": 100.0,
                "full.audio_runtime_pack_install_ms": 0.0,
                "full.audio_model_download_ms": 15.0,
                "full.audio_first_use_blocked_runtime_pack_count": 0.0,
                "full.audio_first_use_blocked_model_count": 1.0,
                "full.audio_runtime_pack_recovery_success_rate": 100.0,
            },
        },
        "runtime_core": {
            "multi_model_ready_count": 3.0,
            "multi_model_request_success_rate": 100.0,
            "prefill_memory_guard_rejection_count": 1.0,
            "prefill_memory_guard_success_rate": 100.0,
        },
        "quantization": {
            "summary": {"profile_count": 7, "smoke_pass_rate": 100.0},
            "profiles": {
                pid: {
                    "job_ms": 1.0,
                    "artifact_bytes": 670.0,
                    "manifest_bytes": 1747.0,
                    "calibration_sample_count": 32.0,
                    "smoke_test_passed": 1.0,
                }
                for pid in ("q2", "q3", "q4", "q5", "q6", "q7", "q8")
            },
        },
        "evaluation": {
            "metrics": {
                "eval.mmlu.typed_score_mean": 0.3,
            },
        },
        "evaluation_compare": _passing_evaluation_compare_evidence(),
        "real_workload": _passing_real_workload_evidence(),
        "m9": _passing_m9_evidence(),
    }

    failures = evaluate_release_gate(report, policy)

    assert "eval.mmlu.typed_score_mean=0.30 fell below minimum 0.50" in failures


def test_evaluate_release_gate_fails_on_compare_regression_verdict() -> None:
    policy = load_release_gate_policy()
    report = {
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
        "audio": {
            "checks": {
                "slim_requires_runtime_pack_download": True,
                "full_runtime_pack_preinstalled": True,
                "slim_runtime_pack_metadata_exists": True,
                "full_runtime_pack_metadata_exists": True,
                "slim_managed_model_metadata_exists": True,
                "full_managed_model_metadata_exists": True,
            },
            "metrics": {
                "slim.audio_runtime_pack_install_ms": 10.0,
                "slim.audio_model_download_ms": 15.0,
                "slim.audio_first_use_blocked_runtime_pack_count": 1.0,
                "slim.audio_first_use_blocked_model_count": 1.0,
                "slim.audio_runtime_pack_recovery_success_rate": 100.0,
                "full.audio_runtime_pack_install_ms": 0.0,
                "full.audio_model_download_ms": 15.0,
                "full.audio_first_use_blocked_runtime_pack_count": 0.0,
                "full.audio_first_use_blocked_model_count": 1.0,
                "full.audio_runtime_pack_recovery_success_rate": 100.0,
            },
        },
        "runtime_core": {
            "multi_model_ready_count": 3.0,
            "multi_model_request_success_rate": 100.0,
            "prefill_memory_guard_rejection_count": 1.0,
            "prefill_memory_guard_success_rate": 100.0,
        },
        "quantization": {
            "summary": {"profile_count": 7, "smoke_pass_rate": 100.0},
            "profiles": {
                pid: {
                    "job_ms": 1.0,
                    "artifact_bytes": 670.0,
                    "manifest_bytes": 1747.0,
                    "calibration_sample_count": 32.0,
                    "smoke_test_passed": 1.0,
                }
                for pid in ("q2", "q3", "q4", "q5", "q6", "q7", "q8")
            },
        },
        "evaluation": {
            "metrics": {
                "eval.mmlu.typed_score_mean": 0.75,
            },
        },
        "evaluation_compare": _passing_evaluation_compare_evidence(verdict="regression"),
        "real_workload": _passing_real_workload_evidence(),
        "m9": _passing_m9_evidence(),
    }

    failures = evaluate_release_gate(report, policy)

    assert "evaluation_compare.mmlu verdict=regression did not satisfy required verdict improvement" in failures


def test_evaluate_release_gate_passes_with_sufficient_eval_primary_score() -> None:
    policy = load_release_gate_policy()
    report = {
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
        "runtime_core": {
            "multi_model_ready_count": 3.0,
            "multi_model_request_success_rate": 100.0,
            "prefill_memory_guard_rejection_count": 1.0,
            "prefill_memory_guard_success_rate": 100.0,
        },
        "quantization": {
            "summary": {"profile_count": 7, "smoke_pass_rate": 100.0},
            "profiles": {
                pid: {
                    "job_ms": 1.0,
                    "artifact_bytes": 670.0,
                    "manifest_bytes": 1747.0,
                    "calibration_sample_count": 32.0,
                    "smoke_test_passed": 1.0,
                }
                for pid in ("q2", "q3", "q4", "q5", "q6", "q7", "q8")
            },
        },
        "evaluation": {
            "metrics": {
                "eval.mmlu.typed_score_mean": 0.75,
            },
        },
        "evaluation_compare": _passing_evaluation_compare_evidence(),
        "real_workload": _passing_real_workload_evidence(),
        "m9": _passing_m9_evidence(),
    }

    failures = evaluate_release_gate(report, policy)

    eval_failures = [f for f in failures if "eval." in f]
    assert eval_failures == []
