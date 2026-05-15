#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "mlx-worker-python"))

from worker.productization.release_gates import (
    evaluate_m9_release_evidence,
    evaluate_release_gate,
    load_release_gate_policy,
)


def run_smoke(repo_root: Path, fixture_mode: str) -> dict[str, object]:
    policy = load_release_gate_policy(
        repo_root / "infra" / "release" / "phase8-release-gate-policy.json"
    )
    report = _build_fixture_report(policy, fixture_mode)
    failures = evaluate_release_gate(report, policy)
    m9_summary = dict(report["m9"]["summary"])
    observability_evidence = dict(report.get("observability", {}).get("evidence", {}))
    packaged_launch = dict(report.get("install", {}).get("packaged_launch", {}))
    packaged_launch_audit = dict(packaged_launch.get("installed_app_audit", {}))

    return {
        "passed": not failures,
        "fixture_mode": fixture_mode,
        "failures": failures,
        "metrics": {
            "release_gate.m9_required_probe_count": float(
                m9_summary.get("required_probe_count", 0.0)
            ),
            "release_gate.m9_missing_probe_count": float(
                m9_summary.get("missing_probe_count", 0.0)
            ),
            "release_gate.m9_failed_threshold_count": float(
                m9_summary.get("failed_threshold_count", 0.0)
            ),
            "release_gate.observability_required_artifact_validity_passed": float(
                observability_evidence.get("required_artifact_validity_passed", 0.0)
            ),
            "release_gate.packaged_launch_installed_app_audit_passed": float(
                packaged_launch_audit.get("audit_passed", 0.0)
            ),
        },
    }


def _build_fixture_report(
    policy: dict[str, object],
    fixture_mode: str,
) -> dict[str, object]:
    if fixture_mode not in {"passing", "failing"}:
        raise ValueError(f"Unsupported fixture mode: {fixture_mode}")

    m9 = _build_passing_m9_report()
    if fixture_mode == "failing":
        m9["shared_access"]["metrics"].pop("shared_access.accepted_client_count", None)
        m9["connection_lifecycle"]["metrics"]["disconnect.resume_success_rate"] = 0.0
        m9["closure_audit"]["metrics"]["closure_audit.blocker_count"] = 1.0

    m9_failures, m9_summary = evaluate_m9_release_evidence(
        m9,
        dict(policy.get("m9", {})),
    )
    m9["summary"] = m9_summary

    report = {
        "install": {
            "generated_asset_count": 5,
            "bootstrap_command_count": 3,
            "checks": {
                "manifest_exists": True,
                "environment_script_exists": True,
                "all_plists_exist": True,
            },
            "packaged_launch": _build_passing_packaged_launch_report(),
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
                    "artifact_bytes": 670.0,
                    "manifest_bytes": 1747.0,
                    "calibration_sample_count": 16.0 if profile_id == "q8" else 32.0,
                    "smoke_test_passed": 1.0,
                }
                for profile_id in ("q2", "q3", "q4", "q5", "q6", "q7", "q8")
            },
        },
        "evaluation": {
            "metrics": {
                "eval.mmlu.typed_score_mean": 1.0,
                "eval.mmlu.accuracy": 1.0,
            },
        },
        "evaluation_compare": _build_passing_evaluation_compare_report(),
        "real_workload": _build_passing_real_workload_report(),
        "m9": m9,
        "observability": _build_passing_observability_report(),
        "lora_path": _build_passing_lora_path_report(),
    }
    if fixture_mode == "passing" and m9_failures:
        raise RuntimeError(f"Passing M9 fixture unexpectedly failed: {m9_failures}")
    return report


def _build_passing_m9_report() -> dict[str, object]:
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
    }


def _build_passing_packaged_launch_report() -> dict[str, object]:
    return {
        "runtime_source": {
            "packaging_target_id": "launch_agents_checkout",
            "packaging_kind": "launch_agents",
            "runtime_layout": "repo_checkout",
        },
        "connect_host_resolution": {
            "bind_host": "0.0.0.0",
            "connect_host": "127.0.0.1",
            "expected_connect_host": "127.0.0.1",
            "service_base_url": "http://127.0.0.1:12436/v1",
            "connect_host_loopback": 1.0,
        },
        "health_probe_reuse": {
            "health_probe_url": "http://127.0.0.1:12436/health",
            "health_probe_url_matches_connect_host": 1.0,
            "reused_client_count": 1.0,
            "time_wait_socket_count": 0.0,
        },
        "installed_app_audit": {
            "audit_schema_version": "melix.packaged_launch.installed_app_audit.v1",
            "install_manifest_path": "/tmp/melix/install-manifest.json",
            "expected_logical_product_identity": "io.melix",
            "logical_product_identity": "io.melix",
            "logical_product_identity_matches": 1.0,
            "audit_passed": 1.0,
        },
    }


def _build_passing_evaluation_compare_report() -> dict[str, object]:
    return {
        "suite_id": "mmlu",
        "base_model_id": "melix-dev-text",
        "target_model_id": "melix-dev-text-lora-a",
        "sample_size": 8,
        "effect_threshold": 0.1,
        "verdict": "improvement",
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
            "verdict": "improvement",
            "reason": "delta_exceeds_threshold_with_supported_intervals",
            "effect_threshold": 0.1,
            "delta_accuracy": 0.5,
            "threshold_passed": True,
            "both_intervals_same_side": True,
        },
        "report_path": "/tmp/evaluation-compare-report.md",
    }


def _build_passing_real_workload_report() -> dict[str, object]:
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


def _build_passing_lora_path_report() -> dict[str, object]:
    stage_durations_ms = {
        "dataset_build": 0.5,
        "train": 1420.0,
        "activate": 1.0,
        "compare": 0.5,
        "publish": 118.0,
    }
    return {
        "stages": {
            stage_name: {
                "success": 1.0,
                "duration_ms": duration_ms,
            }
            for stage_name, duration_ms in stage_durations_ms.items()
        },
        "summary": {
            "stages_success_count": float(len(stage_durations_ms)),
            "stages_failure_count": 0.0,
            "full_path_success": 1.0,
        },
    }


def _build_passing_observability_report() -> dict[str, object]:
    return {
        "probe_policy": {
            "noop_overhead_threshold_passed": 1.0,
            "noop_recorder_overhead_pct": 0.5,
            "noop_policy_check_overhead_pct": 0.5,
            "production_sampler_invocations": 0.0,
        },
        "evidence": {
            "required_artifact_validity_passed": 1.0,
        },
        "serving_diagnostics": {
            "debug_queue_bounded": 1.0,
            "debug_queue_dropped_event_count": 24.0,
            "debug_queue_retained_event_count": 8.0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the deterministic M9.8 release-gate smoke."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=ROOT,
        help="Repository root used to resolve the checked-in release-gate policy.",
    )
    parser.add_argument(
        "--fixture-mode",
        choices=("passing", "failing"),
        default="passing",
        help="Deterministic fixture scenario to evaluate.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = run_smoke(args.repo_root.resolve(), args.fixture_mode)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
