from __future__ import annotations

from pathlib import Path

from worker.productization import (
    build_family_support_matrix,
    build_phase16_video_metrics_report as exported_build_phase16_video_metrics_report,
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


def _passing_m9_report() -> dict[str, object]:
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
            "required_probe_count": 23.0,
            "missing_probe_count": 0.0,
            "failed_threshold_count": 0.0,
        }
    }


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


def test_build_phase16_video_metrics_report_includes_operator_metrics() -> None:
    report = exported_build_phase16_video_metrics_report(
        local_path={
            "success": True,
            "request_latency_ms": 28.6,
        },
        remote_url={
            "success": True,
            "request_latency_ms": 31.4,
        },
        bounded_window={
            "success": True,
            "request_latency_ms": 42.5,
            "video_first_token_ms": 12.1,
            "preprocess_latency_ms": 5.3,
            "video_frame_count": 6,
            "video_frame_budget": 6,
            "video_window_ms": 4000,
            "temp_media_artifact_count": 1,
            "temp_media_artifact_bytes": 2048,
            "temp_media_cleanup_latency_ms": 0.7,
            "temp_media_cleanup_failure_count": 0,
        },
        routing={
            "text_protection_success": True,
            "video_request_latency_ms": 58.2,
            "text_request_latency_ms": 14.9,
            "scheduler_text_ttft_under_multimodal_ms": 8.4,
            "scheduler_multimodal_queue_delay_ms": 3.7,
        },
    )

    checks = report["checks"]
    metrics = report["metrics"]
    assert checks["video.local_path_success"] is True
    assert checks["video.remote_url_success"] is True
    assert checks["video.bounded_window_success"] is True
    assert checks["video.routing.text_protection_success"] is True
    assert metrics["video.integration_success_rate"] == 100.0
    assert metrics["video.local_path.request_latency_ms"] == 28.6
    assert metrics["video.remote_url.request_latency_ms"] == 31.4
    assert metrics["video.bounded_window.request_latency_ms"] == 42.5
    assert metrics["vision.video_first_token_ms"] == 12.1
    assert metrics["vision.preprocess_latency_ms"] == 5.3
    assert metrics["vision.video_frame_count"] == 6.0
    assert metrics["vision.video_frame_budget"] == 6.0
    assert metrics["vision.video_window_ms"] == 4000.0
    assert metrics["vision.temp_media_artifact_count"] == 1.0
    assert metrics["vision.temp_media_artifact_bytes"] == 2048.0
    assert metrics["vision.temp_media_cleanup_latency_ms"] == 0.7
    assert metrics["vision.temp_media_cleanup_failure_count"] == 0.0
    assert metrics["scheduler.text_ttft_under_multimodal_ms"] == 8.4
    assert metrics["scheduler.multimodal_queue_delay_ms"] == 3.7


def test_build_phase16_video_metrics_report_defaults_missing_values() -> None:
    report = exported_build_phase16_video_metrics_report(
        local_path={"success": False, "request_latency_ms": "slow"},
        remote_url={"success": False, "request_latency_ms": None},
        bounded_window={"success": False},
        routing={"text_protection_success": False},
    )

    checks = report["checks"]
    metrics = report["metrics"]
    assert checks["video.local_path_success"] is False
    assert checks["video.remote_url_success"] is False
    assert checks["video.bounded_window_success"] is False
    assert checks["video.routing.text_protection_success"] is False
    assert metrics["video.integration_success_rate"] == 0.0
    assert metrics["video.local_path.request_latency_ms"] == 0.0
    assert metrics["video.remote_url.request_latency_ms"] == 0.0
    assert metrics["video.bounded_window.request_latency_ms"] == 0.0
    assert metrics["vision.video_first_token_ms"] == 0.0
    assert metrics["vision.preprocess_latency_ms"] == 0.0
    assert metrics["vision.video_frame_count"] == 0.0
    assert metrics["vision.video_frame_budget"] == 0.0
    assert metrics["vision.video_window_ms"] == 0.0
    assert metrics["vision.temp_media_artifact_count"] == 0.0
    assert metrics["vision.temp_media_artifact_bytes"] == 0.0
    assert metrics["vision.temp_media_cleanup_latency_ms"] == 0.0
    assert metrics["vision.temp_media_cleanup_failure_count"] == 0.0
    assert metrics["scheduler.text_ttft_under_multimodal_ms"] == 0.0
    assert metrics["scheduler.multimodal_queue_delay_ms"] == 0.0


def test_build_family_support_matrix_exposes_contract_rows_and_live_path_evidence() -> None:
    matrix = build_family_support_matrix()
    rows = {
        (row["capability"], row["family_id"]): row
        for row in matrix["families"]
    }

    assert matrix["summary"]["family_count"] == 23
    assert matrix["summary"]["text_family_count"] == 6
    assert matrix["summary"]["transcription_family_count"] == 2
    assert matrix["summary"]["speech_family_count"] == 2
    assert matrix["summary"]["image_family_count"] == 6
    assert matrix["summary"]["live_verified_count"] == 15
    assert matrix["summary"]["contract_only_count"] == 8

    qwen3moe = rows[("text", "qwen3moe")]
    assert qwen3moe["contract"]["route_kind"] == "python_text_compatibility"
    assert qwen3moe["contract"]["supported_parsers"] == ["text", "qwen"]
    assert qwen3moe["contract"]["attention_profile"] == "gqa"
    assert qwen3moe["contract"]["rope_profile"] == "yarn_interleaved"
    assert qwen3moe["contract"]["moe_enabled"] is True
    assert qwen3moe["contract"]["expert_count"] == 128
    assert qwen3moe["contract"]["moe_gate_dequant"] is True
    assert qwen3moe["live_path"]["status"] == "verified"

    bge = rows[("embedding", "bge-m3")]
    assert bge["contract"]["route_kind"] == "python_embedding"
    assert bge["contract"]["supported_tasks"] == ["embed"]
    assert bge["contract"]["supported_modalities"] == ["text"]
    assert bge["live_path"]["status"] == "verified"
    assert (
        "tests/integration/test_non_text_endpoints.py::"
        "test_embeddings_endpoint_supports_bge_and_mxbai_family_overrides"
    ) in bge["live_path"]["integration_tests"]

    whisper = rows[("transcription", "whisper")]
    assert whisper["contract"]["route_kind"] == "python_transcription"
    assert whisper["contract"]["backend_id"] == "mlx_audio.stt"
    assert whisper["contract"]["install_profile"] == "audio-stt"
    assert whisper["contract"]["languages"] == ["auto"]
    assert whisper["live_path"]["status"] == "contract_only"

    parakeet = rows[("transcription", "parakeet")]
    assert parakeet["contract"]["route_kind"] == "python_transcription"
    assert parakeet["contract"]["backend_id"] == "mlx_audio.stt"
    assert parakeet["contract"]["install_profile"] == "audio-stt"
    assert parakeet["contract"]["languages"] == ["auto"]
    assert parakeet["live_path"]["status"] == "contract_only"

    kokoro = rows[("speech", "kokoro")]
    assert kokoro["contract"]["route_kind"] == "python_speech"
    assert kokoro["contract"]["backend_id"] == "mlx_audio.tts"
    assert kokoro["contract"]["install_profile"] == "audio-tts"
    assert kokoro["contract"]["languages"] == ["en"]
    assert kokoro["contract"]["voice_mode"] == "named"
    assert kokoro["contract"]["output_formats"] == ["wav"]
    assert kokoro["contract"]["supports_instructions"] is False
    assert kokoro["contract"]["voice_catalog_summary"] == "Named English voices exposed by the Kokoro speaker catalog."
    assert kokoro["contract"]["voice_locales"] == ["en"]
    assert kokoro["contract"]["default_locale"] == "en"
    assert kokoro["contract"]["packaged_default_locale"] == "en"
    assert kokoro["contract"]["locale_policy"] == "request>model_default>packaged_default"
    assert kokoro["live_path"]["status"] == "contract_only"

    qwen3_tts = rows[("speech", "qwen3-tts")]
    assert qwen3_tts["contract"]["route_kind"] == "python_speech"
    assert qwen3_tts["contract"]["backend_id"] == "mlx_audio.tts"
    assert qwen3_tts["contract"]["install_profile"] == "audio-tts"
    assert qwen3_tts["contract"]["languages"] == ["zh", "en"]
    assert qwen3_tts["contract"]["voice_mode"] == "hybrid"
    assert qwen3_tts["contract"]["output_formats"] == ["wav"]
    assert qwen3_tts["contract"]["supports_instructions"] is True
    assert (
        qwen3_tts["contract"]["voice_catalog_summary"]
        == "Hybrid named and instruction-conditioned multilingual voices for Chinese and English synthesis."
    )
    assert qwen3_tts["contract"]["voice_locales"] == ["zh", "en"]
    assert qwen3_tts["contract"]["default_locale"] == "zh"
    assert qwen3_tts["contract"]["packaged_default_locale"] == "zh"
    assert qwen3_tts["contract"]["locale_policy"] == "request>model_default>packaged_default"
    assert qwen3_tts["live_path"]["status"] == "contract_only"

    basic = rows[("rerank", "basic")]
    assert basic["contract"]["route_kind"] == "python_rerank"
    assert basic["contract"]["supported_tasks"] == ["rerank"]
    assert basic["live_path"]["status"] == "contract_only"

    mixtral = rows[("text", "mixtral")]
    assert mixtral["contract"]["route_kind"] == "python_text_compatibility"
    assert mixtral["contract"]["moe_enabled"] is True
    assert mixtral["contract"]["expert_count"] == 8
    assert mixtral["live_path"]["status"] == "contract_only"

    causal = rows[("rerank", "causal-lm")]
    assert causal["contract"]["architecture"] == "causal-lm"
    assert causal["contract"]["scoring_mode"] == "yes-no-logits"
    assert causal["live_path"]["status"] == "verified"

    qwenimage = rows[("image", "qwenimage-v1")]
    assert qwenimage["contract"]["route_kind"] == "python_image"
    assert qwenimage["contract"]["task_kind"] == "text-to-image"
    assert qwenimage["contract"]["supports_generation"] is True
    assert qwenimage["contract"]["supports_edit"] is False
    assert qwenimage["live_path"]["status"] == "verified"

    fill = rows[("image", "fill-v1")]
    assert fill["contract"]["task_kind"] == "image-text-to-image"
    assert fill["contract"]["default_workflow_role"] == "edit"
    assert fill["contract"]["supports_generation"] is False
    assert fill["contract"]["supports_edit"] is True
    assert fill["live_path"]["status"] == "verified"

    fibo = rows[("image", "fibo-v1")]
    assert fibo["contract"]["supports_generation"] is True
    assert fibo["contract"]["supports_edit"] is False
    assert fibo["live_path"]["status"] == "contract_only"


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
        "m9": _passing_m9_report(),
    }

    assert compute_release_smoke_pass_rate(report, policy) == 100.0

    report["recovery"]["restart_recovery_success_rate"] = 0.0
    assert compute_release_smoke_pass_rate(report, policy) == 85.71


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
        "m9": _passing_m9_report(),
    }

    assert compute_release_smoke_pass_rate(report, policy) == 85.71


def test_compute_release_smoke_pass_rate_fails_non_dict_m9() -> None:
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
        "m9": "invalid",
    }

    assert compute_release_smoke_pass_rate(report, policy) == 85.71


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
            "m9": _passing_m9_report(),
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


def test_build_phase8_metrics_report_surfaces_closure_audit_counts() -> None:
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
        closure_audit={
            "metrics": {
                "closure_audit.blocker_count": 0.0,
                "closure_audit.accepted_risk_count": 1.0,
                "closure_audit.evidence_gap_count": 2.0,
                "closure_audit.deferred_work_count": 1.0,
            },
            "summary": {
                "top_unresolved_findings": [
                    "Missing required M9 metric probes: disconnect.keepalive_gap_ms",
                    "M9.8 release-gate wiring remains deferred until ecosystem evidence is consumed by the release gate.",
                ]
            },
            "findings": [
                {
                    "finding_id": "scope-only",
                    "severity": "accepted_risk",
                    "summary": "Repository-owned scope only.",
                }
            ],
        },
        policy=policy,
    )

    metrics = report["metrics"]
    assert metrics["closure_audit.blocker_count"] == 0.0
    assert metrics["closure_audit.accepted_risk_count"] == 1.0
    assert metrics["closure_audit.evidence_gap_count"] == 2.0
    assert metrics["closure_audit.deferred_work_count"] == 1.0
    assert report["closure_audit"]["summary"]["top_unresolved_findings"] == [
        "Missing required M9 metric probes: disconnect.keepalive_gap_ms",
        "M9.8 release-gate wiring remains deferred until ecosystem evidence is consumed by the release gate.",
    ]


def test_build_phase8_metrics_report_surfaces_m9_release_gate_counts() -> None:
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
            "m9": {
                "summary": {
                    "required_probe_count": 23.0,
                    "missing_probe_count": 0.0,
                    "failed_threshold_count": 0.0,
                }
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
    assert metrics["release_gate.m9_required_probe_count"] == 23.0
    assert metrics["release_gate.m9_missing_probe_count"] == 0.0
    assert metrics["release_gate.m9_failed_threshold_count"] == 0.0
