from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

from worker.productization import serving_diagnostics as serving_diagnostics_module
from worker.productization.serving_diagnostics import (
    BoundedServingDiagnosticsEventQueue,
    ServingDiagnosticsComparisonError,
    ServingDiagnosticsEvent,
    ServingDiagnosticsRequestSummary,
    ServingEvidenceRun,
    validate_prefill_chunk_size,
    write_baseline_accelerated_evidence,
    write_serving_diagnostics_bundle,
)


def profile_proof_request_summary() -> ServingDiagnosticsRequestSummary:
    return ServingDiagnosticsRequestSummary(
        request_id="req-profile-proof",
        task_kind="text-generation",
        model_id="melix-dev-text",
        runtime_kind="deterministic",
        acceleration_mode="baseline",
        prompt_protocol_id="chat.completions.v1",
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={},
        status="completed",
        finish_reason="stop",
    )


def test_serving_diagnostics_bundle_writes_stable_layout_and_prefill_fields(
    tmp_path: Path,
) -> None:
    summary = ServingDiagnosticsRequestSummary(
        request_id="req-1",
        task_kind="text-generation",
        model_id="mlx-community/Qwen3.5-9B-MLX-4bit",
        runtime_kind="mlx-text",
        acceleration_mode="baseline",
        prompt_protocol_id="chat.completions.v1",
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={"temperature": 0.0, "top_p": 1.0, "top_k": 1},
        status="completed",
        finish_reason="stop",
        prompt_tokens=128,
        completion_tokens=32,
        prefill_chunk_size=64,
        prefill_ms=12.5,
        decode_ms=22.0,
        prompt_tps=256.0,
        generation_tps=42.0,
        prefill_tokens_per_second=256.0,
        cache_hit_tokens=96,
        cache_miss_tokens=32,
        cache_restored_tokens=64,
        cache_computed_tokens=64,
        memory_used_bytes=1024,
        memory_total_bytes=4096,
        peak_memory_bytes=2048,
        native_acceleration={
            "schema_version": "melix.native_acceleration.status.v1",
            "runtime_active": True,
            "status": "admitted",
            "mode": "speculative_decode",
            "draft_supported": True,
            "effective_depth": 4,
            "request_gate": "media_draft_eligible",
            "runtime_scope": "vlm_mtp",
            "fallback_reason": "",
            "autoregressive_fallback": False,
            "forward_counts": {
                "rounds": 3,
                "accepted_tokens": 9,
                "rejected_tokens": 3,
            },
            "timings": {
                "draft_propose_ms": 12.5,
                "target_verify_ms": 25.0,
            },
            "acceptance_by_depth": {
                "effective_depth": 4,
                "accepted_tokens": 9,
                "rejected_tokens": 3,
                "acceptance_rate": 0.75,
                "rollback_rate": 0.25,
            },
        },
    )
    event = ServingDiagnosticsEvent(
        request_id="req-1",
        phase="prefill",
        event_index=0,
        status="completed",
        duration_ms=12.5,
        attributes={"prefill_chunk_size": 64, "cache_hit_tokens": 96},
    )

    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-1",
        invocation={"command": "melix serve --diagnostics diag-1"},
        effective_config={"runtime": {"mode": "baseline"}},
        model_refs={"model_id": summary.model_id, "snapshot": "snap-1"},
        request_summary=summary,
        events=(event,),
        diagnostics_mode="debug",
    )

    bundle_root = tmp_path / "serving-diagnostics" / "diag-1"
    assert paths["bundle_root"] == bundle_root
    assert set(paths) == {
        "bundle_root",
        "manifest",
        "effective_config",
        "request_summary",
        "events",
    }

    manifest = json.loads((bundle_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "melix.serving_diagnostics.manifest.v1"
    assert manifest["diagnostics_mode"] == "debug"
    assert manifest["artifacts"] == {
        "effective_config": "effective-config.json",
        "request_summary": "request-summary.json",
        "events": "events.jsonl",
    }
    assert manifest["public_performance_claim_eligible"] is False

    effective_config = json.loads((bundle_root / "effective-config.json").read_text(encoding="utf-8"))
    assert effective_config["runtime"]["mode"] == "baseline"

    request_payload = json.loads((bundle_root / "request-summary.json").read_text(encoding="utf-8"))
    assert request_payload["prefill_chunk_size"] == 64
    assert request_payload["prefill_tokens_per_second"] == 256.0
    assert request_payload["prompt_tps"] == 256.0
    assert request_payload["generation_tps"] == 42.0
    assert request_payload["cache_hit_tokens"] == 96
    assert request_payload["cache_miss_tokens"] == 32
    assert request_payload["cache_restored_tokens"] == 64
    assert request_payload["cache_computed_tokens"] == 64
    assert request_payload["finish_reason"] == "stop"
    assert request_payload["native_acceleration"] == {
        "acceptance_by_depth": {
            "acceptance_rate": 0.75,
            "accepted_tokens": 9,
            "effective_depth": 4,
            "rejected_tokens": 3,
            "rollback_rate": 0.25,
        },
        "autoregressive_fallback": False,
        "draft_supported": True,
        "effective_depth": 4,
        "fallback_reason": "",
        "forward_counts": {
            "accepted_tokens": 9,
            "rejected_tokens": 3,
            "rounds": 3,
        },
        "mode": "speculative_decode",
        "request_gate": "media_draft_eligible",
        "runtime_active": True,
        "runtime_scope": "vlm_mtp",
        "schema_version": "melix.native_acceleration.status.v1",
        "status": "admitted",
        "timings": {
            "draft_propose_ms": 12.5,
            "target_verify_ms": 25.0,
        },
    }
    assert not hasattr(summary, "__dict__")

    event_rows = [
        json.loads(line)
        for line in (bundle_root / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert event_rows == [
        {
            "schema_version": "melix.serving_diagnostics.event.v1",
            "request_id": "req-1",
            "phase": "prefill",
            "event_index": 0,
            "status": "completed",
            "duration_ms": 12.5,
            "attributes": {"cache_hit_tokens": 96, "prefill_chunk_size": 64},
        }
    ]


def test_serving_diagnostics_effective_config_preserves_profile_proof_receipt(
    tmp_path: Path,
) -> None:
    summary = profile_proof_request_summary()
    profile_receipt = {
        "requested_profile": "throughput",
        "effective_profile": "balanced",
        "profile_mode": "optimized",
        "proof_matrix_id": "",
        "verification_status": "missing",
        "profile_admission_status": "experimental_unverified",
        "fallback_reason": "experimental_unverified",
        "recovery_hint": "Attach a passing proof matrix row before enabling this profile.",
    }

    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-profile-proof",
        invocation={},
        effective_config={
            "serving_profile": profile_receipt,
            "runtime": {"mode": "baseline"},
        },
        model_refs={"model_id": "melix-dev-text"},
        request_summary=summary,
        events=(),
        diagnostics_mode="debug",
    )

    effective_config = json.loads(paths["effective_config"].read_text(encoding="utf-8"))
    assert effective_config["serving_profile"] == profile_receipt


def test_serving_diagnostics_effective_config_derives_profile_receipt_from_audit_metadata(
    tmp_path: Path,
) -> None:
    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-profile-proof-audit",
        invocation={},
        effective_config={
            "execution": {
                "ext": {
                    "melix.acceleration.profile.requested_profile": "throughput",
                    "melix.acceleration.profile.effective_profile": "balanced",
                    "melix.acceleration.profile.profile_mode": "optimized",
                    "melix.acceleration.profile.proof_matrix_id": "",
                    "melix.acceleration.profile.verification_status": "missing",
                    "melix.acceleration.profile.profile_admission_status": "experimental_unverified",
                    "melix.acceleration.profile.fallback_reason": "experimental_unverified",
                    "melix.acceleration.profile.recovery_hint": (
                        "Attach a passing proof matrix row before enabling this profile."
                    ),
                }
            }
        },
        model_refs={"model_id": "melix-dev-text"},
        request_summary=profile_proof_request_summary(),
        events=(),
        diagnostics_mode="debug",
    )

    effective_config = json.loads(paths["effective_config"].read_text(encoding="utf-8"))
    assert effective_config["serving_profile"] == {
        "requested_profile": "throughput",
        "effective_profile": "balanced",
        "profile_mode": "optimized",
        "proof_matrix_id": "",
        "verification_status": "missing",
        "profile_admission_status": "experimental_unverified",
        "fallback_reason": "experimental_unverified",
        "recovery_hint": "Attach a passing proof matrix row before enabling this profile.",
    }


def test_serving_diagnostics_effective_config_derives_profile_receipt_from_worker_request_ext(
    tmp_path: Path,
) -> None:
    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-profile-proof-worker-request",
        invocation={},
        effective_config={
            "worker_request": {
                "execution": {
                    "ext": {
                        "melix.acceleration.profile.requested_profile": "throughput",
                        "melix.acceleration.profile.effective_profile": "throughput",
                        "melix.acceleration.profile.profile_admission_status": "admitted",
                    }
                }
            }
        },
        model_refs={"model_id": "melix-dev-text"},
        request_summary=profile_proof_request_summary(),
        events=(),
        diagnostics_mode="debug",
    )

    effective_config = json.loads(paths["effective_config"].read_text(encoding="utf-8"))
    assert effective_config["serving_profile"] == {
        "requested_profile": "throughput",
        "effective_profile": "throughput",
        "profile_admission_status": "admitted",
    }


def test_serving_diagnostics_effective_config_skips_incomplete_profile_audit_metadata(
    tmp_path: Path,
) -> None:
    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-profile-proof-incomplete",
        invocation={},
        effective_config={
            "execution_ext": {
                "melix.acceleration.profile.requested_profile": "throughput",
                "melix.acceleration.profile.effective_profile": "balanced",
            }
        },
        model_refs={"model_id": "melix-dev-text"},
        request_summary=profile_proof_request_summary(),
        events=(),
        diagnostics_mode="debug",
    )

    effective_config = json.loads(paths["effective_config"].read_text(encoding="utf-8"))
    assert "serving_profile" not in effective_config


def test_serving_diagnostics_effective_config_keeps_explicit_serving_profile(
    tmp_path: Path,
) -> None:
    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-profile-proof-explicit",
        invocation={},
        effective_config={
            "serving_profile": {
                "requested_profile": "balanced",
                "effective_profile": "balanced",
                "profile_admission_status": "admitted",
            },
            "execution_ext": {
                "melix.acceleration.profile.requested_profile": "throughput",
                "melix.acceleration.profile.effective_profile": "balanced",
                "melix.acceleration.profile.profile_admission_status": "experimental_unverified",
            },
        },
        model_refs={"model_id": "melix-dev-text"},
        request_summary=profile_proof_request_summary(),
        events=(),
        diagnostics_mode="debug",
    )

    effective_config = json.loads(paths["effective_config"].read_text(encoding="utf-8"))
    assert effective_config["serving_profile"] == {
        "requested_profile": "balanced",
        "effective_profile": "balanced",
        "profile_admission_status": "admitted",
    }


def test_serving_diagnostics_effective_config_preserves_serving_readiness_receipt(
    tmp_path: Path,
) -> None:
    readiness_receipt = {
        "requested_model_id": "mlx-community/Qwen3.5-9B-MLX-4bit",
        "effective_model_id": "mlx-community/Qwen3.5-9B-MLX-4bit",
        "identity_source": "explicit_request",
        "budget_source": "explicit_request",
        "health_ready_at": "2026-07-04T11:00:00Z",
        "progress_source": "backend_health",
        "dependency_policy_status": "allowed",
    }

    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-readiness-explicit",
        invocation={},
        effective_config={
            "serving_readiness": readiness_receipt,
            "runtime": {"mode": "baseline"},
        },
        model_refs={"model_id": "melix-dev-text"},
        request_summary=profile_proof_request_summary(),
        events=(),
        diagnostics_mode="debug",
    )

    effective_config = json.loads(paths["effective_config"].read_text(encoding="utf-8"))
    assert effective_config["serving_readiness"] == readiness_receipt


def test_serving_diagnostics_effective_config_derives_readiness_receipt_from_metadata(
    tmp_path: Path,
) -> None:
    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-readiness-derived",
        invocation={},
        effective_config={
            "request_metadata": {
                "melix.serving.readiness.requested_model_id": "configured-alias",
                "melix.serving.readiness.effective_model_id": "mlx-community/Qwen3.5-9B-MLX-4bit",
                "melix.serving.readiness.identity_source": "cached_catalog",
                "melix.serving.readiness.budget_source": "profile_default",
                "melix.serving.readiness.health_ready_at": "2026-07-04T11:01:00Z",
                "melix.serving.readiness.progress_source": "backend_health",
                "melix.serving.readiness.dependency_policy_status": "allowed",
            }
        },
        model_refs={"model_id": "melix-dev-text"},
        request_summary=profile_proof_request_summary(),
        events=(),
        diagnostics_mode="debug",
    )

    effective_config = json.loads(paths["effective_config"].read_text(encoding="utf-8"))
    assert effective_config["serving_readiness"] == {
        "requested_model_id": "configured-alias",
        "effective_model_id": "mlx-community/Qwen3.5-9B-MLX-4bit",
        "identity_source": "cached_catalog",
        "budget_source": "profile_default",
        "health_ready_at": "2026-07-04T11:01:00Z",
        "progress_source": "backend_health",
        "dependency_policy_status": "allowed",
    }


def test_serving_diagnostics_effective_config_skips_incomplete_readiness_metadata(
    tmp_path: Path,
) -> None:
    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-readiness-incomplete",
        invocation={},
        effective_config={
            "execution_ext": {
                "melix.serving.readiness.requested_model_id": "configured-alias",
                "melix.serving.readiness.effective_model_id": "mlx-community/Qwen3.5-9B-MLX-4bit",
                "melix.serving.readiness.dependency_policy_status": "allowed",
            }
        },
        model_refs={"model_id": "melix-dev-text"},
        request_summary=profile_proof_request_summary(),
        events=(),
        diagnostics_mode="debug",
    )

    effective_config = json.loads(paths["effective_config"].read_text(encoding="utf-8"))
    assert "serving_readiness" not in effective_config


def test_serving_diagnostics_effective_config_derives_capability_receipt_from_metadata(
    tmp_path: Path,
) -> None:
    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-serving-capability",
        invocation={},
        effective_config={
            "worker_request": {
                "execution": {
                    "ext": {
                        "melix.serving.capability.schema_version": (
                            "melix.serving_capability_receipt.v1"
                        ),
                        "melix.serving.capability.capabilities": (
                            "generate_text, generate_multimodal"
                        ),
                        "melix.serving.capability.input_modalities": "text, image",
                        "melix.serving.capability.output_modalities": "text",
                        "melix.serving.capability.acceleration_profile": "balanced",
                        "melix.serving.capability.requested_mode": "baseline",
                        "melix.serving.capability.resolved_mode": "baseline",
                        "melix.serving.capability.optional_dependency_source": (
                            "not_required"
                        ),
                        "melix.serving.capability.unsupported_reason": "none",
                        "melix.serving.capability.ignored_flags": "",
                        "melix.serving.capability.fallback_policy": "fail_closed",
                    }
                }
            }
        },
        model_refs={"model_id": "melix-dev-text"},
        request_summary=profile_proof_request_summary(),
        events=(),
        diagnostics_mode="debug",
    )

    effective_config = json.loads(paths["effective_config"].read_text(encoding="utf-8"))
    assert effective_config["serving_capability"] == {
        "schema_version": "melix.serving_capability_receipt.v1",
        "capabilities": ["generate_text", "generate_multimodal"],
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"],
        "acceleration_profile": "balanced",
        "requested_mode": "baseline",
        "resolved_mode": "baseline",
        "optional_dependency_source": "not_required",
        "unsupported_reason": "none",
        "ignored_flags": [],
        "fallback_policy": "fail_closed",
    }


def test_serving_diagnostics_effective_config_materializes_control_plane_capability_metadata(
    tmp_path: Path,
) -> None:
    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-control-plane-serving-capability",
        invocation={},
        effective_config={
            "execution_ext": {
                "melix.serving.capability.schema_version": (
                    "melix.serving_capability_receipt.v1"
                ),
                "melix.serving.capability.capabilities": "generate_text",
                "melix.serving.capability.input_modalities": "text",
                "melix.serving.capability.output_modalities": "text",
                "melix.serving.capability.acceleration_profile": "throughput",
                "melix.serving.capability.requested_mode": "speculative_decode",
                "melix.serving.capability.resolved_mode": "speculative_decode",
                "melix.serving.capability.optional_dependency_source": "not_required",
                "melix.serving.capability.unsupported_reason": "none",
                "melix.serving.capability.ignored_flags": "",
                "melix.serving.capability.fallback_policy": "observable_fallback",
            }
        },
        model_refs={"model_id": "melix-dev-text"},
        request_summary=profile_proof_request_summary(),
        events=(),
        diagnostics_mode="debug",
    )

    effective_config = json.loads(paths["effective_config"].read_text(encoding="utf-8"))
    assert effective_config["serving_capability"] == {
        "schema_version": "melix.serving_capability_receipt.v1",
        "capabilities": ["generate_text"],
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "acceleration_profile": "throughput",
        "requested_mode": "speculative_decode",
        "resolved_mode": "speculative_decode",
        "optional_dependency_source": "not_required",
        "unsupported_reason": "none",
        "ignored_flags": [],
        "fallback_policy": "observable_fallback",
    }


def test_serving_diagnostics_effective_config_derives_acceleration_config_receipt_from_metadata(
    tmp_path: Path,
) -> None:
    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-control-plane-acceleration-config",
        invocation={},
        effective_config={
            "execution_ext": {
                "melix.serving.acceleration_config.schema_version": (
                    "melix.resolved_acceleration_config.v1"
                ),
                "melix.serving.acceleration_config.method": "speculative_decode",
                "melix.serving.acceleration_config.requested_method": (
                    "speculative_decode"
                ),
                "melix.serving.acceleration_config.sidecar_model": (
                    "melix-dev-draft"
                ),
                "melix.serving.acceleration_config.num_speculative_tokens": "6",
                "melix.serving.acceleration_config.profile": "throughput",
                "melix.serving.acceleration_config.conflicting_flags": (
                    "draft_model_id, acceleration_profile"
                ),
                "melix.serving.acceleration_config.controller_scope": "request",
                "melix.serving.acceleration_config.disabled_reason": "none",
            }
        },
        model_refs={"model_id": "melix-dev-text"},
        request_summary=profile_proof_request_summary(),
        events=(),
        diagnostics_mode="debug",
    )

    effective_config = json.loads(paths["effective_config"].read_text(encoding="utf-8"))
    assert effective_config["serving_acceleration_config"] == {
        "schema_version": "melix.resolved_acceleration_config.v1",
        "method": "speculative_decode",
        "requested_method": "speculative_decode",
        "sidecar_model": "melix-dev-draft",
        "num_speculative_tokens": 6,
        "profile": "throughput",
        "conflicting_flags": ["draft_model_id", "acceleration_profile"],
        "controller_scope": "request",
        "disabled_reason": "none",
    }


def test_serving_diagnostics_acceleration_config_skips_invalid_token_count() -> None:
    receipt = (
        serving_diagnostics_module._serving_acceleration_config_receipt_from_audit_metadata(
            {
                "melix.serving.acceleration_config.schema_version": (
                    "melix.resolved_acceleration_config.v1"
                ),
                "melix.serving.acceleration_config.method": "baseline",
                "melix.serving.acceleration_config.requested_method": (
                    "speculative_decode"
                ),
                "melix.serving.acceleration_config.sidecar_model": "",
                "melix.serving.acceleration_config.num_speculative_tokens": "six",
                "melix.serving.acceleration_config.profile": "balanced",
                "melix.serving.acceleration_config.conflicting_flags": "",
                "melix.serving.acceleration_config.controller_scope": "none",
                "melix.serving.acceleration_config.disabled_reason": (
                    "invalid_token_count"
                ),
            }
        )
    )

    assert receipt == {}


def test_serving_diagnostics_capability_receipt_normalizes_sequence_metadata() -> None:
    receipt = (
        serving_diagnostics_module._serving_capability_receipt_from_audit_metadata(
            {
                "melix.serving.capability.schema_version": (
                    "melix.serving_capability_receipt.v1"
                ),
                "melix.serving.capability.capabilities": (
                    None,
                    "generate_multimodal",
                    "generate_text",
                ),
                "melix.serving.capability.input_modalities": {"image", "text"},
                "melix.serving.capability.output_modalities": frozenset({"text"}),
                "melix.serving.capability.acceleration_profile": "balanced",
                "melix.serving.capability.requested_mode": "baseline",
                "melix.serving.capability.resolved_mode": "baseline",
                "melix.serving.capability.optional_dependency_source": "not_required",
                "melix.serving.capability.unsupported_reason": "none",
                "melix.serving.capability.ignored_flags": [None, "", "unknown_flag"],
                "melix.serving.capability.fallback_policy": "fail_closed",
            }
        )
    )

    assert receipt["capabilities"] == ["generate_multimodal", "generate_text"]
    assert receipt["input_modalities"] == ["image", "text"]
    assert receipt["output_modalities"] == ["text"]
    assert receipt["ignored_flags"] == ["unknown_flag"]


def test_serving_diagnostics_effective_config_skips_incomplete_capability_metadata(
    tmp_path: Path,
) -> None:
    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-serving-capability-incomplete",
        invocation={},
        effective_config={
            "execution_ext": {
                "melix.serving.capability.schema_version": (
                    "melix.serving_capability_receipt.v1"
                ),
                "melix.serving.capability.capabilities": "generate_text",
                "melix.serving.capability.input_modalities": "text",
            }
        },
        model_refs={"model_id": "melix-dev-text"},
        request_summary=profile_proof_request_summary(),
        events=(),
        diagnostics_mode="debug",
    )

    effective_config = json.loads(paths["effective_config"].read_text(encoding="utf-8"))
    assert "serving_capability" not in effective_config


def test_serving_diagnostics_effective_config_derives_privacy_policy_receipts_from_metadata(
    tmp_path: Path,
) -> None:
    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-network-fetch-policy",
        invocation={},
        effective_config={
            "execution_ext": {
                "melix.network_fetch.policy.schema_version": "melix.network_fetch_policy_receipt.v1",
                "melix.network_fetch.policy.surface": "local_proxy_external_media",
                "melix.network_fetch.policy.route_scope": "image_edit",
                "melix.network_fetch.policy.action": "blocked",
                "melix.network_fetch.policy.url_class": "private",
                "melix.network_fetch.policy.url_scheme": "https",
                "melix.network_fetch.policy.host_class": "public",
                "melix.network_fetch.policy.resolved_ip": "[REDACTED_PRIVATE_IP]",
                "melix.network_fetch.policy.resolved_ip_class": "private",
                "melix.network_fetch.policy.redirect_hops_checked": "1",
                "melix.network_fetch.policy.blocked_reason": "resolved_private_or_loopback_ip",
                "melix.network_fetch.policy.redacted_url": "https://example.test/[redacted]",
                "melix.network_fetch.policy.raw_url_included": "false",
                "melix.network_fetch.policy.fetch_attempted": "false",
                "melix.privacy.audit.schema_version": "melix.privacy_audit_counter.v1",
                "melix.privacy.audit.surface": "local_proxy_external_media",
                "melix.privacy.audit.route_scope": "image_edit",
                "melix.privacy.audit.blocked_count": "1",
                "melix.privacy.audit.redacted_count": "1",
                "melix.privacy.audit.passed_count": "0",
                "melix.privacy.audit.raw_sensitive_span_count": "0",
            }
        },
        model_refs={"model_id": "melix-dev-text"},
        request_summary=profile_proof_request_summary(),
        events=(),
        diagnostics_mode="debug",
    )

    effective_config = json.loads(paths["effective_config"].read_text(encoding="utf-8"))
    assert effective_config["network_fetch_policy"] == {
        "schema_version": "melix.network_fetch_policy_receipt.v1",
        "surface": "local_proxy_external_media",
        "route_scope": "image_edit",
        "action": "blocked",
        "url_class": "private",
        "url_scheme": "https",
        "host_class": "public",
        "resolved_ip": "[REDACTED_PRIVATE_IP]",
        "resolved_ip_class": "private",
        "redirect_hops_checked": 1,
        "blocked_reason": "resolved_private_or_loopback_ip",
        "redacted_url": "https://example.test/[redacted]",
        "raw_url_included": False,
        "fetch_attempted": False,
    }
    assert effective_config["privacy_audit_counters"] == [
        {
            "schema_version": "melix.privacy_audit_counter.v1",
            "surface": "local_proxy_external_media",
            "route_scope": "image_edit",
            "blocked_count": 1,
            "redacted_count": 1,
            "passed_count": 0,
            "raw_sensitive_span_count": 0,
        }
    ]
    payload = json.dumps(effective_config, sort_keys=True)
    assert "api_key" not in payload
    assert "sk-secret" not in payload


def test_serving_diagnostics_effective_config_derives_privacy_detector_receipts_from_metadata(
    tmp_path: Path,
) -> None:
    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-privacy-detector",
        invocation={},
        effective_config={
            "execution_ext": {
                "melix.privacy.detector.schema_version": "melix.privacy_detector_receipt.v1",
                "melix.privacy.detector.surface": "workspace_ingest",
                "melix.privacy.detector.route_scope": "source_import",
                "melix.privacy.detector.detector_id": "melix.pattern_detector.v1",
                "melix.privacy.detector.policy_id": "melix.default_privacy_policy.v1",
                "melix.privacy.detector.policy_mode": "redact",
                "melix.privacy.detector.action": "redacted",
                "melix.privacy.detector.categories": ["secret", "email"],
                "melix.privacy.detector.match_count": "3",
                "melix.privacy.detector.redacted_span_count": "3",
                "melix.privacy.detector.blocked_reason": "",
                "melix.privacy.detector.confidence_source": "deterministic_pattern",
                "melix.privacy.detector.raw_sensitive_span_count": "0",
                "melix.privacy.detector.raw_text_included": "false",
            }
        },
        model_refs={"model_id": "melix-dev-text"},
        request_summary=profile_proof_request_summary(),
        events=(),
        diagnostics_mode="debug",
    )

    effective_config = json.loads(paths["effective_config"].read_text(encoding="utf-8"))
    assert effective_config["privacy_detector_receipts"] == [
        {
            "schema_version": "melix.privacy_detector_receipt.v1",
            "surface": "workspace_ingest",
            "route_scope": "source_import",
            "detector_id": "melix.pattern_detector.v1",
            "policy_id": "melix.default_privacy_policy.v1",
            "policy_mode": "redact",
            "action": "redacted",
            "categories": ["email", "secret"],
            "match_count": 3,
            "redacted_span_count": 3,
            "blocked_reason": "",
            "confidence_source": "deterministic_pattern",
            "raw_sensitive_span_count": 0,
            "raw_text_included": False,
        }
    ]
    payload = json.dumps(effective_config, sort_keys=True)
    assert "alice@example.com" not in payload
    assert "sk-secret" not in payload


def test_serving_diagnostics_effective_config_skips_incomplete_privacy_policy_metadata(
    tmp_path: Path,
) -> None:
    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-network-fetch-policy-incomplete",
        invocation={},
        effective_config={
            "request_metadata": {
                "melix.network_fetch.policy.surface": "local_proxy_external_media",
                "melix.network_fetch.policy.action": "blocked",
                "melix.privacy.audit.surface": "local_proxy_external_media",
                "melix.privacy.audit.blocked_count": "1",
                "melix.privacy.detector.surface": "workspace_ingest",
                "melix.privacy.detector.action": "redacted",
                "melix.privacy.detector.raw_text_included": "true",
            }
        },
        model_refs={"model_id": "melix-dev-text"},
        request_summary=profile_proof_request_summary(),
        events=(),
        diagnostics_mode="debug",
    )

    effective_config = json.loads(paths["effective_config"].read_text(encoding="utf-8"))
    assert "network_fetch_policy" not in effective_config
    assert "privacy_audit_counters" not in effective_config
    assert "privacy_detector_receipts" not in effective_config


def test_serving_diagnostics_empty_effective_config_skips_profile_receipt_scan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_profile_scan(metadata: object) -> dict[str, object]:
        raise AssertionError("empty effective_config should skip profile receipt scans")

    monkeypatch.setattr(
        serving_diagnostics_module,
        "_serving_profile_receipt_from_audit_metadata",
        fail_profile_scan,
    )

    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-empty-profile-scan",
        invocation={},
        effective_config={},
        model_refs={"model_id": "melix-dev-text"},
        request_summary=profile_proof_request_summary(),
        events=(),
        diagnostics_mode="debug",
    )

    effective_config = json.loads(paths["effective_config"].read_text(encoding="utf-8"))
    assert effective_config == {}


def test_stable_json_object_empty_mapping_skips_item_iteration() -> None:
    class EmptyMapping:
        def __bool__(self) -> bool:
            return False

        def items(self) -> object:
            raise AssertionError("empty mappings should not be sorted or iterated")  # pragma: no cover

    payload = cast("Mapping[str, object]", EmptyMapping())
    assert serving_diagnostics_module._stable_json_object(payload) == {}


def test_serving_diagnostics_event_empty_attributes_match_explicit_empty_mapping() -> None:
    default_event = ServingDiagnosticsEvent(
        request_id="req-empty-default",
        phase="decode",
        event_index=1,
        status="completed",
    )
    explicit_empty_event = ServingDiagnosticsEvent(
        request_id="req-empty-explicit",
        phase="decode",
        event_index=1,
        status="completed",
        attributes={},
    )

    default_payload = default_event.to_dict()
    explicit_payload = explicit_empty_event.to_dict()

    assert default_payload["attributes"] == {}
    assert explicit_payload["attributes"] == {}


def test_serving_diagnostics_bounded_queue_drops_oldest_without_blocking(
    tmp_path: Path,
) -> None:
    queue = BoundedServingDiagnosticsEventQueue(max_events=2)
    assert queue.append(
        ServingDiagnosticsEvent(request_id="req-queue", phase="prefill", event_index=0, status="completed")
    ) is True
    assert queue.append(
        ServingDiagnosticsEvent(request_id="req-queue", phase="decode", event_index=1, status="completed")
    ) is True
    assert queue.append(
        ServingDiagnosticsEvent(request_id="req-queue", phase="decode", event_index=2, status="completed")
    ) is False
    snapshot = queue.snapshot()
    assert snapshot.dropped_count == 1
    assert [event.event_index for event in snapshot.events] == [1, 2]

    summary = ServingDiagnosticsRequestSummary(
        request_id="req-queue",
        task_kind="text-generation",
        model_id="melix-dev-text",
        runtime_kind="deterministic",
        acceleration_mode="baseline",
        prompt_protocol_id="chat.completions.v1",
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={},
        status="completed",
        finish_reason="stop",
    )
    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-queue",
        invocation={},
        effective_config={},
        model_refs={},
        request_summary=summary,
        events=snapshot,
        diagnostics_mode="debug",
    )

    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["public_performance_claim_eligible"] is False
    assert manifest["event_count"] == 2
    assert manifest["dropped_event_count"] == 1
    event_rows = [
        json.loads(line)
        for line in paths["events"].read_text(encoding="utf-8").splitlines()
    ]
    assert [row["event_index"] for row in event_rows] == [1, 2]


def test_serving_diagnostics_queue_append_uses_retained_count_without_len() -> None:
    event = ServingDiagnosticsEvent(
        request_id="req-retained-count",
        phase="decode",
        event_index=0,
        status="completed",
    )

    class NoLenBuffer:
        def __init__(self) -> None:
            self.events: list[ServingDiagnosticsEvent] = []

        def __len__(self) -> int:
            raise AssertionError(
                "append should use the retained counter, not len(_events)"
            )  # pragma: no cover

        def append(self, queued_event: ServingDiagnosticsEvent) -> None:
            self.events.append(queued_event)

    queue = BoundedServingDiagnosticsEventQueue(max_events=2)
    buffer = NoLenBuffer()
    queue._events = buffer  # type: ignore[assignment]
    queue._append_event = buffer.append  # type: ignore[method-assign]

    assert queue.append(event) is True
    assert buffer.events == [event]


def test_serving_diagnostics_event_instances_use_slots_for_debug_queue() -> None:
    event = ServingDiagnosticsEvent(
        request_id="req-slots",
        phase="decode",
        event_index=1,
        status="completed",
        duration_ms=0.25,
        attributes={"token": "***"},
    )

    assert hasattr(event, "__dict__") is False
    assert event.to_dict()["attributes"] == {"token": "***"}
    with pytest.raises(AttributeError):
        event.status = "mutated"  # type: ignore[misc]


def test_serving_diagnostics_event_preserves_dataclass_style_equality() -> None:
    first = ServingDiagnosticsEvent(
        request_id="req-eq",
        phase="decode",
        event_index=1,
        status="completed",
        duration_ms=0.25,
    )
    matching = ServingDiagnosticsEvent(
        request_id="req-eq",
        phase="decode",
        event_index=1,
        status="completed",
        duration_ms=0.25,
    )
    different = ServingDiagnosticsEvent(
        request_id="req-eq",
        phase="decode",
        event_index=2,
        status="completed",
        duration_ms=0.25,
    )

    assert first == matching
    assert first != different
    assert first != object()


def test_serving_diagnostics_queue_snapshot_uses_slots_for_debug_queue() -> None:
    event = ServingDiagnosticsEvent(
        request_id="req-snapshot-slots",
        phase="decode",
        event_index=1,
        status="completed",
    )
    queue = BoundedServingDiagnosticsEventQueue(max_events=1)
    queue.append(event)
    queue_snapshot = queue.snapshot()

    assert hasattr(queue_snapshot, "__dict__") is False
    assert queue_snapshot.events == (event,)


def test_serving_diagnostics_default_event_attributes_reuse_empty_mapping() -> None:
    first = ServingDiagnosticsEvent(
        request_id="req-empty-1",
        phase="decode",
        event_index=1,
        status="completed",
    )
    second = ServingDiagnosticsEvent(
        request_id="req-empty-2",
        phase="decode",
        event_index=2,
        status="completed",
    )

    assert first.attributes == {}
    assert first.to_dict()["attributes"] == {}
    assert first.attributes is second.attributes
    with pytest.raises(TypeError):
        first.attributes["late"] = "mutation"  # type: ignore[index]


def test_serving_diagnostics_empty_event_attributes_skip_stable_json_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = ServingDiagnosticsEvent(
        request_id="req-empty-fast-path",
        phase="decode",
        event_index=3,
        status="completed",
    )

    def fail_stable_json_object(_: object) -> dict[str, object]:  # pragma: no cover
        raise AssertionError("empty event attributes should not call _stable_json_object")

    monkeypatch.setattr(
        serving_diagnostics_module,
        "_stable_json_object",
        fail_stable_json_object,
    )

    assert event.to_dict()["attributes"] == {}


def test_serving_diagnostics_jsonl_fast_path_reuses_request_id_literal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    original_encoder = serving_diagnostics_module._json_string_literal_bytes

    def counting_encoder(value: str) -> bytes:
        calls.append(value)
        return original_encoder(value)

    monkeypatch.setattr(
        serving_diagnostics_module,
        "_json_string_literal_bytes",
        counting_encoder,
    )
    rows = tuple(
        ServingDiagnosticsEvent(
            request_id="req-shared-fast-path",
            phase="decode",
            event_index=event_index,
            status="completed",
            duration_ms=0.001,
        )
        for event_index in range(3)
    )
    path = tmp_path / "events.jsonl"

    serving_diagnostics_module._write_jsonl(path, rows)

    payloads = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [payload["event_index"] for payload in payloads] == [0, 1, 2]
    assert {payload["request_id"] for payload in payloads} == {"req-shared-fast-path"}
    assert calls == ["req-shared-fast-path"]


def test_serving_diagnostics_jsonl_extend_fast_path_appends_complete_line() -> None:
    event = ServingDiagnosticsEvent(
        request_id="req-inline-newline",
        phase="decode",
        event_index=5,
        status="completed",
        duration_ms=0.001,
    )
    payload = bytearray()

    assert serving_diagnostics_module._extend_empty_attribute_event_json_line_bytes(
        payload.extend,
        event,
        {},
    ) is True

    assert payload.endswith(b"\n")
    assert json.loads(payload)["request_id"] == "req-inline-newline"


def test_serving_diagnostics_jsonl_writer_extends_fast_path_without_join_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_join_helper(*_: object) -> None:  # pragma: no cover
        raise AssertionError("writer should extend the bytearray without per-row join")

    monkeypatch.setattr(
        serving_diagnostics_module,
        "_empty_attribute_event_json_line_bytes",
        fail_join_helper,
    )
    path = tmp_path / "events.jsonl"

    serving_diagnostics_module._write_jsonl(
        path,
        (
            ServingDiagnosticsEvent(
                request_id="req-extend-fast-path",
                phase="decode",
                event_index=4,
                status="completed",
                duration_ms=0.001,
            ),
        ),
    )

    assert json.loads(path.read_text(encoding="utf-8"))["request_id"] == "req-extend-fast-path"


def test_serving_diagnostics_jsonl_fast_path_preserves_direct_helper_call() -> None:
    event = ServingDiagnosticsEvent(
        request_id="req-direct-fast-path",
        phase="decode",
        event_index=7,
        status="completed",
        duration_ms=0.001,
    )

    line = serving_diagnostics_module._empty_attribute_event_json_line(event)

    assert line is not None
    assert json.loads(line)["request_id"] == "req-direct-fast-path"


def test_serving_diagnostics_jsonl_fast_path_populates_direct_request_id_byte_cache() -> None:
    event = ServingDiagnosticsEvent(
        request_id="req-direct-cache-fill",
        phase="decode",
        event_index=9,
        status="completed",
        duration_ms=0.001,
    )
    request_id_literals: dict[str, bytes] = {}

    line = serving_diagnostics_module._empty_attribute_event_json_line_bytes(
        event,
        request_id_literals,
    )

    assert line is not None
    assert json.loads(line)["request_id"] == "req-direct-cache-fill"
    assert request_id_literals == {"req-direct-cache-fill": b'"req-direct-cache-fill"'}


def test_serving_diagnostics_jsonl_fast_path_builds_direct_bytes() -> None:
    event = ServingDiagnosticsEvent(
        request_id="req-direct-bytes",
        phase="decode",
        event_index=11,
        status="completed",
        duration_ms=0.25,
    )

    line = serving_diagnostics_module._empty_attribute_event_json_line_bytes(event)

    assert isinstance(line, bytes)
    assert json.loads(line)["request_id"] == "req-direct-bytes"


def test_serving_diagnostics_jsonl_fast_path_uses_bound_finite_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[float] = []
    original_is_finite = serving_diagnostics_module._IS_FINITE

    def counting_is_finite(value: float) -> bool:
        calls.append(value)
        return original_is_finite(value)

    monkeypatch.setattr(serving_diagnostics_module, "_IS_FINITE", counting_is_finite)
    event = ServingDiagnosticsEvent(
        request_id="req-bound-finite",
        phase="decode",
        event_index=10,
        status="completed",
        duration_ms=0.001,
    )

    line = serving_diagnostics_module._empty_attribute_event_json_line_bytes(event)

    assert line is not None
    assert json.loads(line)["duration_ms"] == 0.001
    assert calls == [0.001]


def test_serving_diagnostics_jsonl_fast_path_reuses_duration_literal_cache() -> None:
    serving_diagnostics_module._ascii_float_literal.cache_clear()
    rows = tuple(
        ServingDiagnosticsEvent(
            request_id="req-duration-cache",
            phase="decode",
            event_index=event_index,
            status="completed",
            duration_ms=0.001,
        )
        for event_index in range(3)
    )

    for row in rows:
        line = serving_diagnostics_module._empty_attribute_event_json_line_bytes(row)
        assert line is not None
        assert json.loads(line)["duration_ms"] == 0.001

    cache_info = serving_diagnostics_module._ascii_float_literal.cache_info()
    assert cache_info.misses == 1
    assert cache_info.hits == 2


def test_serving_diagnostics_jsonl_fast_path_reuses_event_index_literal_cache() -> None:
    serving_diagnostics_module._ascii_int_literal.cache_clear()
    rows = tuple(
        ServingDiagnosticsEvent(
            request_id=f"req-index-cache-{sample_index}",
            phase="decode",
            event_index=4032,
            status="completed",
            duration_ms=0.001,
        )
        for sample_index in range(3)
    )

    for row in rows:
        line = serving_diagnostics_module._empty_attribute_event_json_line_bytes(row)
        assert line is not None
        assert json.loads(line)["event_index"] == 4032

    cache_info = serving_diagnostics_module._ascii_int_literal.cache_info()
    assert cache_info.misses == 1
    assert cache_info.hits == 2


def test_serving_diagnostics_jsonl_fast_path_preserves_generic_phase_status() -> None:
    event = ServingDiagnosticsEvent(
        request_id="req-generic-phase-status",
        phase="prefill",
        event_index=13,
        status="started",
        duration_ms=0.5,
    )

    line = serving_diagnostics_module._empty_attribute_event_json_line_bytes(event)

    assert line is not None
    assert json.loads(line) == event.to_dict()


def test_serving_diagnostics_jsonl_fast_path_direct_helper_preserves_fallback() -> None:
    event = ServingDiagnosticsEvent(
        request_id="req-direct-fallback",
        phase="decode",
        event_index=11,
        status="completed",
        duration_ms=0.25,
        attributes={"extra": True},
    )

    assert serving_diagnostics_module._empty_attribute_event_json_line(event) is None


def test_serving_diagnostics_event_to_dict_preserves_numeric_coercion() -> None:
    event = ServingDiagnosticsEvent(
        request_id="req-numeric-coercion",
        phase="decode",
        event_index=True,
        status="completed",
        duration_ms=3,
    )

    payload = event.to_dict()

    assert payload["event_index"] == 1
    assert type(payload["event_index"]) is int
    assert payload["duration_ms"] == 3.0
    assert type(payload["duration_ms"]) is float


def test_serving_diagnostics_bounded_queue_serializes_append_during_snapshot() -> None:
    first_event = ServingDiagnosticsEvent(
        request_id="req-concurrent",
        phase="prefill",
        event_index=0,
        status="completed",
    )
    second_event = ServingDiagnosticsEvent(
        request_id="req-concurrent",
        phase="decode",
        event_index=1,
        status="completed",
    )

    class InstrumentedBuffer:
        def __init__(self) -> None:
            self._events = [first_event]
            self.iteration_started = threading.Event()
            self.release_iteration = threading.Event()

        def __len__(self) -> int:
            return len(self._events)

        def append(self, event: ServingDiagnosticsEvent) -> None:
            if self.iteration_started.is_set() and not self.release_iteration.is_set():
                raise AssertionError("append entered while snapshot iteration was active")
            self._events.append(event)

        def __iter__(self):
            self.iteration_started.set()
            assert self.release_iteration.wait(timeout=2.0)
            return iter(tuple(self._events))

    queue = BoundedServingDiagnosticsEventQueue(max_events=8)
    instrumented = InstrumentedBuffer()
    queue._events = instrumented  # type: ignore[assignment]
    queue._append_event = instrumented.append  # type: ignore[method-assign]
    errors: list[BaseException] = []
    snapshots: list[tuple[int, ...]] = []

    def capture_snapshot() -> None:
        try:
            snapshot = queue.snapshot()
            snapshots.append(tuple(event.event_index for event in snapshot.events))
        except BaseException as exc:  # pragma: no cover - propagated below
            errors.append(exc)

    def append_event() -> None:
        try:
            assert queue.append(second_event) is True
        except BaseException as exc:  # pragma: no cover - propagated below
            errors.append(exc)

    snapshot_thread = threading.Thread(target=capture_snapshot)
    snapshot_thread.start()
    assert instrumented.iteration_started.wait(timeout=2.0)

    append_thread = threading.Thread(target=append_event)
    append_thread.start()
    instrumented.release_iteration.set()
    snapshot_thread.join(timeout=2.0)
    append_thread.join(timeout=2.0)

    assert snapshot_thread.is_alive() is False
    assert append_thread.is_alive() is False
    assert errors == []
    assert snapshots == [(0,)]
    assert [event.event_index for event in instrumented._events] == [0, 1]


def test_serving_diagnostics_summary_defaults_throughput_to_float_zero() -> None:
    payload = ServingDiagnosticsRequestSummary(
        request_id="req-idle",
        task_kind="text-generation",
        model_id="melix-dev-text",
        runtime_kind="deterministic",
        acceleration_mode="baseline",
        prompt_protocol_id="chat.completions.v1",
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={},
        status="completed",
        finish_reason="stop",
    ).to_dict()

    assert payload["prompt_tps"] == 0.0
    assert payload["generation_tps"] == 0.0
    assert isinstance(payload["prompt_tps"], float)
    assert isinstance(payload["generation_tps"], float)


@pytest.mark.parametrize("artifact_id", (".", "..", "", " nested/path", "bad\x00id"))
def test_serving_diagnostics_rejects_non_local_artifact_ids(
    tmp_path: Path,
    artifact_id: str,
) -> None:
    summary = ServingDiagnosticsRequestSummary(
        request_id="req-local",
        task_kind="text-generation",
        model_id="melix-dev-text",
        runtime_kind="deterministic",
        acceleration_mode="baseline",
        prompt_protocol_id="chat.completions.v1",
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={},
        status="completed",
        finish_reason="stop",
    )

    with pytest.raises(ValueError, match="path-local"):
        write_serving_diagnostics_bundle(
            output_root=tmp_path,
            bundle_id=artifact_id,
            invocation={},
            effective_config={},
            model_refs={},
            request_summary=summary,
            events=(),
            diagnostics_mode="debug",
        )


def test_serving_diagnostics_serializes_sets_as_stable_arrays(tmp_path: Path) -> None:
    summary = ServingDiagnosticsRequestSummary(
        request_id="req-set",
        task_kind="text-generation",
        model_id="melix-dev-text",
        runtime_kind="deterministic",
        acceleration_mode="baseline",
        prompt_protocol_id="chat.completions.v1",
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={},
        status="completed",
        finish_reason="stop",
    )
    event = ServingDiagnosticsEvent(
        request_id="req-set",
        phase="decode",
        event_index=0,
        status="completed",
        attributes={"tags": {"zeta", "alpha"}, "frozen": frozenset({3, 1, 2})},
    )

    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-set",
        invocation={"modes": {"accelerated", "baseline"}},
        effective_config={},
        model_refs={},
        request_summary=summary,
        events=(event,),
        diagnostics_mode="debug",
    )

    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["invocation"]["modes"] == ["accelerated", "baseline"]
    event_payload = json.loads(paths["events"].read_text(encoding="utf-8"))
    assert event_payload["attributes"]["tags"] == ["alpha", "zeta"]
    assert event_payload["attributes"]["frozen"] == [1, 2, 3]


def test_serving_diagnostics_events_jsonl_uses_compact_stable_lines(tmp_path: Path) -> None:
    summary = ServingDiagnosticsRequestSummary(
        request_id="req-compact",
        task_kind="text-generation",
        model_id="melix-dev-text",
        runtime_kind="deterministic",
        acceleration_mode="baseline",
        prompt_protocol_id="chat.completions.v1",
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={},
        status="completed",
        finish_reason="stop",
    )
    event = ServingDiagnosticsEvent(
        request_id="req-compact",
        phase="decode",
        event_index=7,
        status="completed",
        attributes={"beta": 2, "alpha": 1},
    )

    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-compact",
        invocation={},
        effective_config={},
        model_refs={},
        request_summary=summary,
        events=(event,),
        diagnostics_mode="debug",
    )

    line = paths["events"].read_text(encoding="utf-8")
    assert line == (
        '{"attributes":{"alpha":1,"beta":2},"duration_ms":0.0,'
        '"event_index":7,"phase":"decode","request_id":"req-compact",'
        '"schema_version":"melix.serving_diagnostics.event.v1",'
        '"status":"completed"}\n'
    )


def test_serving_diagnostics_events_jsonl_streams_default_attribute_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = ServingDiagnosticsRequestSummary(
        request_id="req-empty-jsonl",
        task_kind="text-generation",
        model_id="melix-dev-text",
        runtime_kind="deterministic",
        acceleration_mode="baseline",
        prompt_protocol_id="chat.completions.v1",
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={},
        status="completed",
        finish_reason="stop",
    )
    event = ServingDiagnosticsEvent(
        request_id='req-"quoted"',
        phase="decode-音声",
        event_index=7,
        status="completed",
        duration_ms=0.001,
    )

    def fail_to_dict(_: object) -> dict[str, object]:  # pragma: no cover
        raise AssertionError("default-attribute JSONL rows should not materialize event dicts")

    monkeypatch.setattr(ServingDiagnosticsEvent, "to_dict", fail_to_dict)

    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-empty-jsonl",
        invocation={},
        effective_config={},
        model_refs={},
        request_summary=summary,
        events=(event,),
        diagnostics_mode="debug",
    )

    line = paths["events"].read_text(encoding="utf-8")
    assert line == (
        '{"attributes":{},"duration_ms":0.001,"event_index":7,'
        '"phase":"decode-\\u97f3\\u58f0","request_id":"req-\\"quoted\\"",'
        '"schema_version":"melix.serving_diagnostics.event.v1",'
        '"status":"completed"}\n'
    )


def test_serving_diagnostics_events_jsonl_writes_bytearray_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = ServingDiagnosticsRequestSummary(
        request_id="req-bytearray-jsonl",
        task_kind="text-generation",
        model_id="melix-dev-text",
        runtime_kind="deterministic",
        acceleration_mode="baseline",
        prompt_protocol_id="chat.completions.v1",
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={},
        status="completed",
        finish_reason="stop",
    )
    event = ServingDiagnosticsEvent(
        request_id="req-bytearray-jsonl",
        phase="decode",
        event_index=8,
        status="completed",
        duration_ms=0.25,
    )
    observed_payload_types: list[type[object]] = []
    original_write_bytes = Path.write_bytes

    def tracked_write_bytes(path: Path, data: bytes) -> int:
        if path.name == "events.jsonl":
            observed_payload_types.append(type(data))
        return original_write_bytes(path, data)

    monkeypatch.setattr(Path, "write_bytes", tracked_write_bytes)

    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-bytearray-jsonl",
        invocation={},
        effective_config={},
        model_refs={},
        request_summary=summary,
        events=(event,),
        diagnostics_mode="debug",
    )

    assert observed_payload_types == [bytearray]
    assert paths["events"].read_text(encoding="utf-8").endswith('"status":"completed"}\n')


def test_serving_diagnostics_events_jsonl_falls_back_for_non_exact_numeric_fields(
    tmp_path: Path,
) -> None:
    summary = ServingDiagnosticsRequestSummary(
        request_id="req-fallback-jsonl",
        task_kind="text-generation",
        model_id="melix-dev-text",
        runtime_kind="deterministic",
        acceleration_mode="baseline",
        prompt_protocol_id="chat.completions.v1",
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={},
        status="completed",
        finish_reason="stop",
    )
    event = ServingDiagnosticsEvent(
        request_id="req-fallback",
        phase="decode",
        event_index=True,
        status="completed",
        duration_ms=1,
    )
    nonfinite_event = ServingDiagnosticsEvent(
        request_id="req-nonfinite",
        phase="decode",
        event_index=2,
        status="completed",
        duration_ms=float("inf"),
    )

    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-fallback-jsonl",
        invocation={},
        effective_config={},
        model_refs={},
        request_summary=summary,
        events=(event, nonfinite_event),
        diagnostics_mode="debug",
    )

    rows = [
        json.loads(line)
        for line in paths["events"].read_text(encoding="utf-8").splitlines()
    ]
    payload = rows[0]
    assert payload["event_index"] == 1
    assert type(payload["event_index"]) is int
    assert payload["duration_ms"] == 1.0
    assert type(payload["duration_ms"]) is float
    assert rows[1]["duration_ms"] == float("inf")


@pytest.mark.parametrize("value", (0, -1, "0", "bad", None))
def test_validate_prefill_chunk_size_rejects_invalid_overrides(value: object) -> None:
    with pytest.raises(ValueError, match="prefill_chunk_size"):
        validate_prefill_chunk_size(value)


def test_validate_prefill_chunk_size_accepts_positive_integer_string() -> None:
    assert validate_prefill_chunk_size("128") == 128


def test_baseline_accelerated_evidence_requires_same_protocol_and_greedy_sampler(
    tmp_path: Path,
) -> None:
    baseline = _evidence_run(
        run_id="baseline",
        acceleration_mode="baseline",
        acceleration_admitted=False,
        fallback_reason="",
    )
    accelerated = _evidence_run(
        run_id="accelerated",
        acceleration_mode="sparse_prefill",
        acceleration_admitted=True,
        fallback_reason="",
        metrics={"prefill_ms": 7.0, "decode_ms": 20.0},
        native_acceleration={
            "schema_version": "melix.native_acceleration.status.v1",
            "runtime_active": False,
            "status": "fallback",
            "mode": "verification_only",
            "fallback_reason": "non_greedy_sampling",
            "effective_depth": 4,
            "forward_counts": {"rounds": 3, "accepted_tokens": 9, "rejected_tokens": 3},
            "timings": {"draft_propose_ms": 12.5, "target_verify_ms": 25.0},
            "acceptance_by_depth": {
                "effective_depth": 4,
                "accepted_tokens": 9,
                "rejected_tokens": 3,
                "acceptance_rate": 0.75,
                "rollback_rate": 0.25,
            },
            "autoregressive_fallback": True,
        },
    )

    paths = write_baseline_accelerated_evidence(
        output_root=tmp_path,
        comparison_id="cmp-1",
        baseline=baseline,
        accelerated=accelerated,
    )

    payload = json.loads(paths["comparison"].read_text(encoding="utf-8"))
    assert payload["schema_version"] == "melix.serving_diagnostics.comparison.v1"
    assert payload["comparison_validity"] == "valid"
    assert payload["methodology"] == {
        "prompt_protocol_id": "chat.completions.v1",
        "prompt_digest": "sha256:prompt",
        "model_id": "melix-dev-text",
        "task_kind": "text-generation",
        "effective_temperature": 0.0,
        "effective_top_p": 1.0,
        "effective_top_k": 1,
        "sampler_is_greedy": True,
        "tier_stability_status": "stable",
    }
    assert payload["runs"]["accelerated"]["acceleration_admitted"] is True
    assert payload["runs"]["accelerated"]["fallback_reason"] == ""
    assert payload["runs"]["accelerated"]["native_acceleration"]["runtime_active"] is False
    assert (
        payload["runs"]["accelerated"]["native_acceleration"]["fallback_reason"]
        == "non_greedy_sampling"
    )
    assert (
        payload["runs"]["accelerated"]["native_acceleration"]["forward_counts"]["accepted_tokens"]
        == 9
    )
    assert (
        payload["runs"]["accelerated"]["native_acceleration"]["acceptance_by_depth"][
            "acceptance_rate"
        ]
        == 0.75
    )
    prefill_row = next(row for row in payload["phase_rows"] if row["phase"] == "prefill")
    assert prefill_row["baseline"] == 10.0
    assert prefill_row["accelerated"] == 7.0
    assert prefill_row["delta"] == -3.0

    with pytest.raises(ServingDiagnosticsComparisonError, match="prompt_protocol_id"):
        write_baseline_accelerated_evidence(
            output_root=tmp_path,
            comparison_id="cmp-mismatch",
            baseline=baseline,
            accelerated=_evidence_run(
                run_id="accelerated-mismatch",
                acceleration_mode="sparse_prefill",
                acceleration_admitted=True,
                prompt_protocol_id="responses.v1",
            ),
        )

    with pytest.raises(ServingDiagnosticsComparisonError, match="greedy"):
        write_baseline_accelerated_evidence(
            output_root=tmp_path,
            comparison_id="cmp-nongreedy",
            baseline=baseline,
            accelerated=_evidence_run(
                run_id="accelerated-nongreedy",
                acceleration_mode="sparse_prefill",
                acceleration_admitted=True,
                effective_temperature=0.7,
            ),
        )


@pytest.mark.parametrize(
    ("metrics", "match"),
    (
        ({"prefill_ms": 10.0}, "decode_ms"),
        ({"prefill_ms": 10.0, "decode_ms": float("nan")}, "finite number"),
        ({"prefill_ms": 10.0, "decode_ms": "bad"}, "finite number"),
    ),
)
def test_baseline_accelerated_evidence_rejects_invalid_phase_metrics(
    tmp_path: Path,
    metrics: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ServingDiagnosticsComparisonError, match=match):
        write_baseline_accelerated_evidence(
            output_root=tmp_path,
            comparison_id="cmp-invalid-metric",
            baseline=_evidence_run(
                run_id="baseline",
                acceleration_mode="baseline",
                acceleration_admitted=False,
                metrics=metrics,  # type: ignore[arg-type]
            ),
            accelerated=_evidence_run(
                run_id="accelerated",
                acceleration_mode="sparse_prefill",
                acceleration_admitted=True,
            ),
        )

    assert not (tmp_path / "serving-diagnostics" / "cmp-invalid-metric").exists()


def _evidence_run(
    *,
    run_id: str,
    acceleration_mode: str,
    acceleration_admitted: bool,
    fallback_reason: str = "",
    prompt_protocol_id: str = "chat.completions.v1",
    effective_temperature: float = 0.0,
    metrics: dict[str, float] | None = None,
    native_acceleration: dict[str, object] | None = None,
) -> ServingEvidenceRun:
    return ServingEvidenceRun(
        run_id=run_id,
        model_id="melix-dev-text",
        task_kind="text-generation",
        prompt_protocol_id=prompt_protocol_id,
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={"max_output_tokens": 32},
        acceleration_mode=acceleration_mode,
        acceleration_admitted=acceleration_admitted,
        fallback_reason=fallback_reason,
        effective_temperature=effective_temperature,
        effective_top_p=1.0,
        effective_top_k=1,
        tier_stability_status="stable",
        metrics=metrics or {"prefill_ms": 10.0, "decode_ms": 20.0},
        native_acceleration=native_acceleration or {},
    )
