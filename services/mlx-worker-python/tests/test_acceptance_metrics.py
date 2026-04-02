from __future__ import annotations

from pathlib import Path

from worker.productization import (
    build_family_support_matrix,
    build_phase6_vision_metrics_report as exported_build_phase6_vision_metrics_report,
)
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


def test_build_phase6_vision_metrics_report_includes_machine_readable_checks() -> None:
    report = exported_build_phase6_vision_metrics_report(
        ingress={
            "local_image_success": True,
            "remote_image_success": True,
            "multi_image_success": True,
        },
        ocr={
            "request_latency_ms": 18.4,
            "default_stop_success": True,
        },
        vlm={
            "request_latency_ms": 24.1,
            "tool_call_success": True,
        },
        metrics_snapshot={
            "values": {
                "vision.ocr_latency_ms": 4.2,
                "vision.vlm_first_token_ms": 7.6,
                "vision.preprocess_latency_ms": 2.5,
                "vision.preprocess_peak_memory_bytes": 4096,
                "vision.cache_memory_bytes": 8192,
                "vision.cache_hit_rate": 75.0,
            }
        },
    )

    metrics = report["metrics"]
    checks = report["checks"]
    assert checks["vision.ingress.local_image_success"] is True
    assert checks["vision.ingress.remote_image_success"] is True
    assert checks["vision.ingress.multi_image_success"] is True
    assert checks["vision.ocr.default_stop_success"] is True
    assert checks["vision.vlm.tool_call_success"] is True
    assert metrics["vision.integration_success_rate"] == 100.0
    assert metrics["vision.ingress.local_image_success_rate"] == 100.0
    assert metrics["vision.ingress.remote_image_success_rate"] == 100.0
    assert metrics["vision.ingress.multi_image_success_rate"] == 100.0
    assert metrics["vision.ocr.default_stop_success_rate"] == 100.0
    assert metrics["vision.vlm.tool_call_success_rate"] == 100.0
    assert metrics["vision.ocr.request_latency_ms"] == 18.4
    assert metrics["vision.vlm.request_latency_ms"] == 24.1
    assert metrics["vision.ocr_latency_ms"] == 4.2
    assert metrics["vision.vlm_first_token_ms"] == 7.6
    assert metrics["vision.preprocess_latency_ms"] == 2.5
    assert metrics["vision.preprocess_peak_memory_bytes"] == 4096.0
    assert metrics["vision.cache_memory_bytes"] == 8192.0
    assert metrics["vision.cache_hit_rate"] == 75.0


def test_build_phase6_vision_metrics_report_defaults_missing_values() -> None:
    report = exported_build_phase6_vision_metrics_report(
        ingress={
            "local_image_success": False,
            "remote_image_success": False,
            "multi_image_success": False,
        },
        ocr={
            "request_latency_ms": "slow",
            "default_stop_success": False,
        },
        vlm={
            "request_latency_ms": None,
            "tool_call_success": False,
        },
        metrics_snapshot={"values": []},
    )

    metrics = report["metrics"]
    assert metrics["vision.integration_success_rate"] == 0.0
    assert metrics["vision.ingress.local_image_success_rate"] == 0.0
    assert metrics["vision.ingress.remote_image_success_rate"] == 0.0
    assert metrics["vision.ingress.multi_image_success_rate"] == 0.0
    assert metrics["vision.ocr.default_stop_success_rate"] == 0.0
    assert metrics["vision.vlm.tool_call_success_rate"] == 0.0
    assert metrics["vision.ocr.request_latency_ms"] == 0.0
    assert metrics["vision.vlm.request_latency_ms"] == 0.0
    assert metrics["vision.ocr_latency_ms"] == 0.0
    assert metrics["vision.vlm_first_token_ms"] == 0.0
    assert metrics["vision.preprocess_latency_ms"] == 0.0
    assert metrics["vision.preprocess_peak_memory_bytes"] == 0.0
    assert metrics["vision.cache_memory_bytes"] == 0.0
    assert metrics["vision.cache_hit_rate"] == 0.0


def test_build_family_support_matrix_exposes_contract_rows_and_live_path_evidence() -> None:
    matrix = build_family_support_matrix()
    rows = {
        (row["capability"], row["family_id"]): row
        for row in matrix["families"]
    }

    assert matrix["summary"]["family_count"] == 7
    assert matrix["summary"]["live_verified_count"] == 6
    assert matrix["summary"]["contract_only_count"] == 1

    bge = rows[("embedding", "bge-m3")]
    assert bge["contract"]["route_kind"] == "python_embedding"
    assert bge["contract"]["supported_tasks"] == ["embed"]
    assert bge["contract"]["supported_modalities"] == ["text"]
    assert bge["live_path"]["status"] == "verified"
    assert (
        "tests/integration/test_non_text_endpoints.py::"
        "test_embeddings_endpoint_supports_bge_and_mxbai_family_overrides"
    ) in bge["live_path"]["integration_tests"]

    basic = rows[("rerank", "basic")]
    assert basic["contract"]["route_kind"] == "python_rerank"
    assert basic["contract"]["supported_tasks"] == ["rerank"]
    assert basic["live_path"]["status"] == "contract_only"

    causal = rows[("rerank", "causal-lm")]
    assert causal["contract"]["architecture"] == "causal-lm"
    assert causal["contract"]["scoring_mode"] == "yes-no-logits"
    assert causal["live_path"]["status"] == "verified"


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
    }

    assert compute_release_smoke_pass_rate(report, policy) == 100.0

    report["recovery"]["restart_recovery_success_rate"] = 0.0
    assert compute_release_smoke_pass_rate(report, policy) == 83.33


def test_compute_release_smoke_pass_rate_fails_non_dict_runtime_core() -> None:
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
        "runtime_core": "invalid",
    }

    assert compute_release_smoke_pass_rate(report, policy) == 83.33


def test_build_phase8_metrics_report_includes_required_probe_names() -> None:
    policy = load_release_gate_policy()
    report = build_phase8_metrics_report(
        cold_boot={
            "cold_boot_to_ready_ms": 812.3,
            "swift_text_worker_ready_ms": 4100.0,
            "python_worker_ready_ms": 5200.0,
            "control_plane_spawn_to_ready_ms": 1100.0,
            "swift_text_worker_spawn_to_bootstrap_ms": 4900.0,
            "swift_text_worker_registry_init_ms": 6.0,
            "swift_text_worker_services_init_ms": 4.0,
            "swift_text_worker_server_construct_ms": 3.0,
            "swift_text_worker_bootstrap_ms": 15.0,
            "python_worker_spawn_to_bootstrap_ms": 5000.0,
            "python_worker_arg_parse_ms": 1.0,
            "python_worker_registry_init_ms": 7.0,
            "python_worker_server_build_ms": 5.0,
            "python_worker_server_start_ms": 2.0,
            "python_worker_bootstrap_ms": 16.0,
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
                "restart_swift_text_worker_ready_ms": 4200.0,
                "restart_python_worker_ready_ms": 5100.0,
                "restart_control_plane_spawn_to_ready_ms": 1292.3,
                "snapshot_restore_ms": 109.7,
                "restart_recovery_ms": 13550.49,
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
                    "slim.audio_runtime_pack_install_ms": 12.3,
                    "slim.audio_model_download_ms": 18.4,
                    "slim.audio_first_use_blocked_runtime_pack_count": 1.0,
                    "slim.audio_first_use_blocked_model_count": 1.0,
                    "slim.audio_runtime_pack_recovery_success_rate": 100.0,
                    "full.audio_runtime_pack_install_ms": 0.0,
                    "full.audio_model_download_ms": 17.2,
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
            "passed": True,
            "failures": [],
        },
        runtime_core={
            "multi_model_ready_count": 3.0,
            "multi_model_request_success_rate": 100.0,
            "prefill_memory_guard_rejection_count": 1.0,
            "prefill_memory_guard_success_rate": 100.0,
        },
        policy=policy,
    )

    metrics = report["metrics"]
    assert metrics["desktop.cold_boot_to_ready_ms"] == 812.3
    assert metrics["desktop.swift_text_worker_ready_ms"] == 4100.0
    assert metrics["desktop.python_worker_ready_ms"] == 5200.0
    assert metrics["desktop.control_plane_spawn_to_ready_ms"] == 1100.0
    assert metrics["desktop.swift_text_worker_spawn_to_bootstrap_ms"] == 4900.0
    assert metrics["desktop.swift_text_worker_registry_init_ms"] == 6.0
    assert metrics["desktop.swift_text_worker_services_init_ms"] == 4.0
    assert metrics["desktop.swift_text_worker_server_construct_ms"] == 3.0
    assert metrics["desktop.swift_text_worker_bootstrap_ms"] == 15.0
    assert metrics["desktop.python_worker_spawn_to_bootstrap_ms"] == 5000.0
    assert metrics["desktop.python_worker_arg_parse_ms"] == 1.0
    assert metrics["desktop.python_worker_registry_init_ms"] == 7.0
    assert metrics["desktop.python_worker_server_build_ms"] == 5.0
    assert metrics["desktop.python_worker_server_start_ms"] == 2.0
    assert metrics["desktop.python_worker_bootstrap_ms"] == 16.0
    assert metrics["desktop.http_ready_ms"] == 812.3
    assert metrics["desktop.background_preload_ms"] == 944.8
    assert metrics["desktop.first_text_model_warm_ms"] == 143.2
    assert metrics["desktop.text_model_load_estimated_resident_bytes"] == 4096.0
    assert metrics["desktop.text_model_load_resident_bytes"] == 8192.0
    assert metrics["desktop.operator_action_latency_ms"] == 38.4
    assert metrics["desktop.restart_to_ready_ms"] == 624.6
    assert metrics["desktop.restart_swift_text_worker_ready_ms"] == 4200.0
    assert metrics["desktop.restart_python_worker_ready_ms"] == 5100.0
    assert metrics["desktop.restart_control_plane_spawn_to_ready_ms"] == 1292.3
    assert metrics["desktop.snapshot_restore_ms"] == 109.7
    assert metrics["desktop.restart_recovery_ms"] == 13550.49
    assert metrics["desktop.crash_recovery_success_rate"] == 100.0
    assert metrics["runtime.multi_model_ready_count"] == 3.0
    assert metrics["runtime.multi_model_request_success_rate"] == 100.0
    assert metrics["runtime.prefill_memory_guard_rejection_count"] == 1.0
    assert metrics["runtime.prefill_memory_guard_success_rate"] == 100.0
    assert metrics["release.benchmark_regression_pct"] == 0.0
    assert metrics["release.smoke_pass_rate"] == 100.0
    assert metrics["install.success_rate"] == 100.0
    assert metrics["audio.slim_runtime_pack_install_ms"] == 12.3
    assert metrics["audio.slim_model_download_ms"] == 18.4
    assert metrics["audio.slim_first_use_blocked_runtime_pack_count"] == 1.0
    assert metrics["audio.slim_first_use_blocked_model_count"] == 1.0
    assert metrics["audio.slim_runtime_pack_recovery_success_rate"] == 100.0
    assert metrics["audio.full_runtime_pack_install_ms"] == 0.0
    assert metrics["audio.full_model_download_ms"] == 17.2
    assert metrics["audio.full_first_use_blocked_runtime_pack_count"] == 0.0
    assert metrics["audio.full_first_use_blocked_model_count"] == 1.0
    assert metrics["audio.full_runtime_pack_recovery_success_rate"] == 100.0
    assert metrics["training.job_duration_ms"] == 1420.0
    assert metrics["training.adapter_publish_ms"] == 118.0


def test_build_phase8_metrics_report_surfaces_cache_recovery_benchmark_metrics() -> None:
    policy = load_release_gate_policy()

    report = build_phase8_metrics_report(
        cold_boot={"cold_boot_to_ready_ms": 700.0, "http_ready_ms": 700.0},
        operator={
            "operator_action_latency_ms": 1.0,
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
                "recovery_metrics": {
                    "bench.recovery.hot_followup_ttft_delta_ms": 14.2,
                    "bench.recovery.hot_prefix_affinity_hit_rate": 100.0,
                    "bench.recovery.cold_l2_hit_rate": 100.0,
                    "bench.recovery.partial_restore_ratio_pct": 81.82,
                },
            },
            "training": {
                "training_duration_ms": 1420.0,
                "adapter_publish_ms": 118.0,
            },
            "recovery": {
                "restart_recovery_ms": 600.0,
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
                    "slim.audio_runtime_pack_install_ms": 12.3,
                    "slim.audio_model_download_ms": 18.4,
                    "slim.audio_first_use_blocked_runtime_pack_count": 1.0,
                    "slim.audio_first_use_blocked_model_count": 1.0,
                    "slim.audio_runtime_pack_recovery_success_rate": 100.0,
                    "full.audio_runtime_pack_install_ms": 0.0,
                    "full.audio_model_download_ms": 17.2,
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
            "passed": True,
            "failures": [],
        },
        runtime_core={
            "multi_model_ready_count": 3.0,
            "multi_model_request_success_rate": 100.0,
            "prefill_memory_guard_rejection_count": 1.0,
            "prefill_memory_guard_success_rate": 100.0,
        },
        policy=policy,
    )

    metrics = report["metrics"]
    assert metrics["cache_recovery.hot_followup_ttft_delta_ms"] == 14.2
    assert metrics["cache_recovery.hot_prefix_affinity_hit_rate"] == 100.0
    assert metrics["cache_recovery.cold_l2_hit_rate"] == 100.0
    assert metrics["cache_recovery.partial_restore_ratio_pct"] == 81.82


def test_build_phase8_metrics_report_accepts_cold_boot_metric_parameter() -> None:
    policy = load_release_gate_policy()

    report = build_phase8_metrics_report(
        cold_boot_to_ready_ms=700.0,
        cold_boot={},
        operator={
            "operator_action_latency_ms": 1.0,
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
                "restart_recovery_ms": 600.0,
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
                    "slim.audio_runtime_pack_install_ms": 12.3,
                    "slim.audio_model_download_ms": 18.4,
                    "slim.audio_first_use_blocked_runtime_pack_count": 1.0,
                    "slim.audio_first_use_blocked_model_count": 1.0,
                    "slim.audio_runtime_pack_recovery_success_rate": 100.0,
                    "full.audio_runtime_pack_install_ms": 0.0,
                    "full.audio_model_download_ms": 17.2,
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
            "passed": True,
            "failures": [],
        },
        runtime_core={
            "multi_model_ready_count": 3.0,
            "multi_model_request_success_rate": 100.0,
            "prefill_memory_guard_rejection_count": 1.0,
            "prefill_memory_guard_success_rate": 100.0,
        },
        policy=policy,
    )

    assert report["metrics"]["desktop.cold_boot_to_ready_ms"] == 700.0
