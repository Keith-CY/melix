from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, runtime_pb2
from scripts import phase2_metrics_report


class _FakeInferenceStub:
    def Prefill(self, request, timeout: int = 120):  # noqa: ANN001
        response = inference_pb2.PrefillResponse()
        response.ok = True
        response.prompt_tokens = 12
        response.decode_handle = "decode-handle"
        response.applied_acceleration.mode = request.execution.acceleration.mode
        response.applied_acceleration.profile_id = request.execution.acceleration.profile_id
        return response

    def Decode(self, request, timeout: int = 120):  # noqa: ANN001
        yield inference_pb2.ExecuteEvent(token_delta=inference_pb2.TokenDelta(text="x"))
        yield inference_pb2.ExecuteEvent(usage_delta=inference_pb2.UsageDelta(prompt_tokens=12, completion_tokens=1))
        yield inference_pb2.ExecuteEvent(completed=inference_pb2.Completed(finish_reason="stop"))


class _FakeRuntimeStub:
    def __init__(self) -> None:
        self.load_requests: list[runtime_pb2.LoadModelRequest] = []

    def LoadModel(self, request, timeout: int = 120):  # noqa: ANN001
        self.load_requests.append(request)
        response = runtime_pb2.LoadModelResponse()
        response.ok = True
        response.model_handle = "melix-dev-text::1"
        response.estimated_resident_bytes = 4096
        return response

    def GetRuntimeStats(self, request, timeout: int = 10):  # noqa: ANN001
        response = runtime_pb2.GetRuntimeStatsResponse()
        response.stats.resident_bytes = 2048
        return response

    def UnloadModel(self, request, timeout: int = 30):  # noqa: ANN001
        response = runtime_pb2.UnloadModelResponse()
        response.ok = True
        return response


class _FakeChannel:
    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN204
        return False


def test_measure_prefill_probe_surfaces_sparse_prefill_metrics(tmp_path: Path) -> None:
    metrics_path = tmp_path / "swift-worker-metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "values": {
                    "swift_text.prefill_ms": 18.5,
                    "swift_text.accelerated_prefill_gain_pct": 42.0,
                    "swift_text.active_kv_quantization_ratio": 0.0,
                    "swift_text.sparse_prefill_accepted_skip_count": 3,
                    "swift_text.sparse_prefill_rejected_opportunity_count": 1,
                    "swift_text.sparse_prefill_protected_region_count": 2,
                }
            }
        ),
        encoding="utf-8",
    )

    result = phase2_metrics_report.measure_prefill_probe(
        _FakeInferenceStub(),
        metrics_path,
        model_handle="melix-dev-text::1",
        prompt='{"kind":"structured"}',
        label="prefill_sparse",
        policy=common_pb2.AccelerationPolicy(
            mode=common_pb2.ACCELERATION_MODE_SPARSE_PREFILL,
            profile_id="structured-user",
            allow_baseline_fallback=True,
        ),
    )

    assert result["mode"] == "ACCELERATION_MODE_SPARSE_PREFILL"
    assert result["sparse_prefill_accepted_skip_count"] == 3
    assert result["sparse_prefill_rejected_opportunity_count"] == 1
    assert result["sparse_prefill_protected_region_count"] == 2


def test_collect_direct_phase_two_metrics_includes_sparse_prefill_probe(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stack = phase2_metrics_report.StackConfiguration(
        runtime_dir=tmp_path,
        swift_socket_path=tmp_path / "swift.sock",
        python_socket_path=tmp_path / "python.sock",
        http_port=8080,
        swift_backend_mode="deterministic",
        python_backend_mode="deterministic",
        control_plane_metrics_path=tmp_path / "control-plane-metrics.json",
        swift_worker_metrics_path=tmp_path / "swift-worker-metrics.json",
    )
    stack.control_plane_metrics_path.write_text(json.dumps({"values": {}}), encoding="utf-8")
    stack.swift_worker_metrics_path.write_text(json.dumps({"values": {}}), encoding="utf-8")

    monkeypatch.setattr(phase2_metrics_report.grpc, "insecure_channel", lambda target: _FakeChannel())
    monkeypatch.setattr(
        phase2_metrics_report.runtime_pb2_grpc,
        "RuntimeServiceStub",
        lambda channel: _FakeRuntimeStub(),
    )
    monkeypatch.setattr(
        phase2_metrics_report.inference_pb2_grpc,
        "InferenceServiceStub",
        lambda channel: _FakeInferenceStub(),
    )
    monkeypatch.setattr(phase2_metrics_report, "wait_for_worker_handshake", lambda *args, **kwargs: None)

    prefill_labels: list[str] = []

    def fake_measure_prefill_probe(*args, **kwargs):  # noqa: ANN002, ANN003
        prefill_labels.append(kwargs["label"])
        return {
            "label": kwargs["label"],
            "mode": "ACCELERATION_MODE_BASELINE",
            "prompt_tokens": 12,
            "total_ms": 20.0,
            "worker_prefill_ms": 18.0,
            "accelerated_prefill_gain_pct": 0.0,
            "active_kv_quantization_ratio": 0.0,
            "sparse_prefill_accepted_skip_count": 0,
            "sparse_prefill_rejected_opportunity_count": 0,
            "sparse_prefill_protected_region_count": 0,
        }

    monkeypatch.setattr(phase2_metrics_report, "measure_prefill_probe", fake_measure_prefill_probe)
    monkeypatch.setattr(
        phase2_metrics_report,
        "measure_decode_probe",
        lambda *args, **kwargs: {"label": kwargs["label"], "mode": "baseline"},
    )
    monkeypatch.setattr(
        phase2_metrics_report,
        "measure_decode_abort",
        lambda *args, **kwargs: {"label": "decode_abort", "abort_ms": 1.0, "finish_reason": "cancelled"},
    )

    result = phase2_metrics_report.collect_direct_phase_two_metrics(
        stack=stack,
        prompt="decode",
        queue_prompt='{"kind":"structured"}',
        abort_prompt="abort prompt",
        decode_repeats=1,
        active_kv_profiles=["q4"],
    )

    assert prefill_labels == ["prefill_baseline", "prefill_accelerated", "prefill_sparse"]
    assert [entry["label"] for entry in result["swift_worker_direct"]["prefill"]] == prefill_labels


def test_collect_direct_phase_two_metrics_repeats_decode_profiles_and_compares_baseline(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stack = phase2_metrics_report.StackConfiguration(
        runtime_dir=tmp_path,
        swift_socket_path=tmp_path / "swift.sock",
        python_socket_path=tmp_path / "python.sock",
        http_port=8080,
        swift_backend_mode="deterministic",
        python_backend_mode="deterministic",
        control_plane_metrics_path=tmp_path / "control-plane-metrics.json",
        swift_worker_metrics_path=tmp_path / "swift-worker-metrics.json",
    )
    stack.control_plane_metrics_path.write_text(json.dumps({"values": {}}), encoding="utf-8")
    stack.swift_worker_metrics_path.write_text(json.dumps({"values": {}}), encoding="utf-8")

    monkeypatch.setattr(phase2_metrics_report.grpc, "insecure_channel", lambda target: _FakeChannel())
    monkeypatch.setattr(
        phase2_metrics_report.runtime_pb2_grpc,
        "RuntimeServiceStub",
        lambda channel: _FakeRuntimeStub(),
    )
    monkeypatch.setattr(
        phase2_metrics_report.inference_pb2_grpc,
        "InferenceServiceStub",
        lambda channel: _FakeInferenceStub(),
    )
    monkeypatch.setattr(phase2_metrics_report, "wait_for_worker_handshake", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        phase2_metrics_report,
        "measure_prefill_probe",
        lambda *args, **kwargs: {"label": kwargs["label"], "mode": "ACCELERATION_MODE_BASELINE"},
    )
    monkeypatch.setattr(
        phase2_metrics_report,
        "measure_decode_abort",
        lambda *args, **kwargs: {"label": "decode_abort", "abort_ms": 1.0, "finish_reason": "cancelled"},
    )

    decode_calls: list[str] = []

    def fake_measure_decode_probe(*args, **kwargs):  # noqa: ANN002, ANN003
        label = kwargs["label"]
        decode_calls.append(label)
        is_baseline = label == "decode_baseline"
        return {
            "label": label,
            "mode": "ACCELERATION_MODE_BASELINE" if is_baseline else "ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
            "ttft_ms": 10.0 if is_baseline else 12.0,
            "total_ms": 100.0 if is_baseline else 120.0,
            "tokens_per_second": 20.0 if is_baseline else 16.0,
            "worker_decode_tokens_per_second": 20.0 if is_baseline else 15.0,
            "active_kv_quantization_ratio": 0.0 if is_baseline else 25.0,
            "active_kv_backend": None if is_baseline else "affine",
            "active_kv_kernel_path": None if is_baseline else "affine_quantized_sdpa",
            "active_kv_decode_model_avg_us": 0 if is_baseline else 300,
            "active_kv_decode_token_eval_avg_us": 0 if is_baseline else 650,
            "active_kv_decode_model_eval_sync_avg_us": 0 if is_baseline else 500,
            "active_kv_fused_attention_avg_us": 0 if is_baseline else 250,
            "active_kv_fused_attention_route_avg_us": 0 if is_baseline else 300,
            "active_kv_decode_loop_total_us": 0 if is_baseline else 2_100,
            "active_kv_decode_quantize_avg_us": 0 if is_baseline else 40,
            "active_kv_cache_update_avg_us": 0 if is_baseline else 400,
            "active_kv_cache_materialize_avg_us": 0 if is_baseline else 70,
            "active_kv_estimated_memory_savings_pct": 0 if is_baseline else 75,
        }

    monkeypatch.setattr(phase2_metrics_report, "measure_decode_probe", fake_measure_decode_probe)

    result = phase2_metrics_report.collect_direct_phase_two_metrics(
        stack=stack,
        prompt="decode",
        queue_prompt='{"kind":"structured"}',
        abort_prompt="abort prompt",
        decode_repeats=2,
        active_kv_profiles=["q4"],
    )

    assert decode_calls == [
        "decode_baseline",
        "decode_affine_q4",
        "decode_baseline",
        "decode_affine_q4",
        "decode_speculative",
    ]
    comparisons = result["swift_worker_direct"]["comparisons"]
    assert comparisons["affine_q4_vs_baseline"]["worker_tps_overhead_pct"] == 25.0
    assert comparisons["affine_q4_vs_baseline"]["ttft_delta_ms"] == 2.0
    assert comparisons["affine_q4_vs_baseline"]["active_kv_decode_token_eval_avg_us"] == 650.0
    assert comparisons["affine_q4_vs_baseline"]["active_kv_decode_model_eval_sync_avg_us"] == 500.0
    assert comparisons["affine_q4_vs_baseline"]["active_kv_fused_attention_avg_us"] == 250.0
    assert comparisons["affine_q4_vs_baseline"]["active_kv_fused_attention_route_avg_us"] == 300.0
    assert comparisons["affine_q4_vs_baseline"]["active_kv_decode_loop_total_us"] == 2100.0
    assert comparisons["affine_q4_vs_baseline"]["active_kv_cache_update_avg_us"] == 400.0
    assert comparisons["affine_q4_vs_baseline"]["active_kv_cache_materialize_avg_us"] == 70.0
    assert comparisons["affine_q4_vs_baseline"]["active_kv_estimated_memory_savings_pct"] == 75.0


def test_active_kv_release_gates_block_turboquant_fallback() -> None:
    gates = phase2_metrics_report.build_active_kv_release_gates(
        [
            {
                "label": "decode_turboquant_q4",
                "active_kv_backend": "turboquant",
                "active_kv_kernel_path": "fallback",
                "active_kv_fallback_count": 0,
                "active_kv_decode_quantize_total_us": 0,
                "active_kv_estimated_memory_savings_pct": 75,
            }
        ],
        {
            "turboquant_q4_vs_baseline": {
                "worker_tps_overhead_pct": 43.55,
                "active_kv_kernel_path": "fallback",
            }
        },
    )

    gate = gates["turboquant_fused_decode"]
    assert gate["status"] == "fail"
    assert gate["observed_kernel_paths"] == ["fallback"]
    assert gate["worker_tps_overhead_pct"] == 43.55
    assert "active_kv_kernel_path=fallback" in gate["failures"]


def test_active_kv_release_gates_report_not_requested_without_turboquant_probe() -> None:
    gates = phase2_metrics_report.build_active_kv_release_gates(
        [{"label": "decode_affine_q4"}],
        {"turboquant_q4_vs_baseline": {"worker_tps_overhead_pct": 12.5}},
    )

    gate = gates["turboquant_fused_decode"]
    assert gate["status"] == "not_requested"
    assert gate["failures"] == ["decode_turboquant_q4=missing"]
    assert gate["worker_tps_overhead_pct"] == 12.5
    assert gate["decode_model_eval_sync_total_us"] == 0
    assert gate["fused_attention_total_us"] == 0
    assert gate["fused_attention_call_count"] == 0
    assert gate["fused_attention_route_total_us"] == 0


def test_active_kv_release_gates_block_incomplete_turboquant_evidence() -> None:
    gates = phase2_metrics_report.build_active_kv_release_gates(
        [
            {
                "label": "decode_turboquant_q4",
                "active_kv_backend": "turboquant",
                "active_kv_kernel_path": None,
                "active_kv_fallback_count": "invalid",
                "active_kv_decode_quantize_total_us": None,
            }
        ],
        {},
    )

    gate = gates["turboquant_fused_decode"]
    assert gate["status"] == "fail"
    assert "active_kv_kernel_path=missing" in gate["failures"]
    assert "active_kv_estimated_memory_savings_pct=missing" in gate["failures"]
    assert gate["fallback_count"] == 0
    assert gate["decode_quantize_total_us"] == 0


def test_active_kv_release_gates_block_unknown_kernel_and_decode_work() -> None:
    gates = phase2_metrics_report.build_active_kv_release_gates(
        [
            {
                "label": "decode_turboquant_q4",
                "active_kv_backend": "turboquant",
                "active_kv_kernel_path": "unknown_91",
                "active_kv_fallback_count": "2",
                "active_kv_decode_quantize_total_us": "7",
                "active_kv_estimated_memory_savings_pct": 50,
            }
        ],
        {},
    )

    gate = gates["turboquant_fused_decode"]
    assert gate["status"] == "fail"
    assert "active_kv_kernel_path=unknown_91" in gate["failures"]
    assert "active_kv_fallback_count=2" in gate["failures"]
    assert "active_kv_decode_quantize_total_us=7" in gate["failures"]
    assert "active_kv_estimated_memory_savings_pct=50.0" in gate["failures"]


def test_active_kv_release_gates_pass_nonfallback_turboquant_probe() -> None:
    gates = phase2_metrics_report.build_active_kv_release_gates(
        [
            {
                "label": "decode_turboquant_q4",
                "active_kv_backend": "turboquant",
                "active_kv_kernel_path": "tq_mse_single",
                "active_kv_fallback_count": 0,
                "active_kv_decode_quantize_total_us": 0,
                "active_kv_estimated_memory_savings_pct": 75,
            }
        ],
        {
            "turboquant_q4_vs_baseline": {
                "worker_tps_overhead_pct": 12.5,
                "active_kv_kernel_path": "tq_mse_single",
            }
        },
    )

    gate = gates["turboquant_fused_decode"]
    assert gate["status"] == "pass"
    assert gate["failures"] == []


def test_active_kv_release_gates_block_nonfallback_turboquant_with_high_overhead() -> None:
    gates = phase2_metrics_report.build_active_kv_release_gates(
        [
            {
                "label": "decode_turboquant_q4",
                "active_kv_backend": "turboquant",
                "active_kv_kernel_path": "tq_mse_single",
                "active_kv_fallback_count": 0,
                "active_kv_decode_quantize_total_us": 0,
                "active_kv_estimated_memory_savings_pct": 75,
            }
        ],
        {
            "turboquant_q4_vs_baseline": {
                "worker_tps_overhead_pct": 42.62,
                "active_kv_kernel_path": "tq_mse_single",
            }
        },
    )

    gate = gates["turboquant_fused_decode"]
    assert gate["status"] == "fail"
    assert "worker_tps_overhead_pct=42.62" in gate["failures"]


def test_active_kv_fused_candidate_probe_separates_capability_and_runtime_evidence() -> None:
    gates = phase2_metrics_report.build_active_kv_release_gates(
        [
            {
                "label": "decode_turboquant_q4",
                "active_kv_backend": "turboquant",
                "active_kv_kernel_path": "fallback",
                "active_kv_runtime_route": "blocked",
                "active_kv_runtime_block_reason": "attention_hook_unavailable",
                "active_kv_fallback_count": 1,
                "active_kv_candidate_eligibility_check_count": 64,
                "active_kv_decode_model_call_count": 63,
                "active_kv_decode_token_eval_total_us": 720_000,
                "active_kv_decode_model_eval_sync_total_us": 500_000,
                "active_kv_decode_model_eval_sync_call_count": 63,
                "active_kv_fused_attention_total_us": 12_000,
                "active_kv_fused_attention_call_count": 63,
                "active_kv_fused_attention_route_total_us": 15_000,
                "active_kv_decode_loop_total_us": 1_800_000,
                "active_kv_decode_quantize_total_us": 0,
                "active_kv_estimated_memory_savings_pct": 75,
            }
        ],
        {
            "turboquant_q4_vs_baseline": {
                "worker_tps_overhead_pct": 43.55,
                "active_kv_kernel_path": "fallback",
            }
        },
    )

    probes = phase2_metrics_report.build_active_kv_fused_candidate_probes(gates)

    probe = probes["turboquant_q4"]
    assert probe["status"] == "runtime_blocked"
    assert probe["profile_label"] == "decode_turboquant_q4"
    assert probe["capability_evidence"]["status"] == "smoke_proven"
    assert probe["capability_evidence"]["runtime_path"] == "not_connected"
    assert (
        "WorkerScaffoldTests.testTurboQuantMetalCapabilityRunsMSEQ4FusedAttentionKernel"
        in probe["capability_evidence"]["smoke_tests"]
    )
    assert (
        "WorkerScaffoldTests.testTurboQuantMetalCapabilityRunsMSEQ4FusedAttentionFromQuantizedKVCacheState"
        in probe["capability_evidence"]["smoke_tests"]
    )
    assert (
        "WorkerScaffoldTests.testTurboQuantMetalCapabilityRejectsUnsupportedQuantizedKVCacheStateInputs"
        in probe["capability_evidence"]["smoke_tests"]
    )
    assert (
        "WorkerScaffoldTests.testTurboQuantCandidateDispatchReadsQuantizedKVCacheState"
        in probe["capability_evidence"]["smoke_tests"]
    )
    assert (
        "WorkerScaffoldTests.testVendoredFusedQ4AttentionMatchesQuantizedReferenceForDecodeGQA"
        in probe["capability_evidence"]["smoke_tests"]
    )
    assert (
        "WorkerScaffoldTests.testVendoredFusedQ4AttentionPreservesQueryDTypeForDecodeGQA"
        in probe["capability_evidence"]["smoke_tests"]
    )
    assert (
        "WorkerScaffoldTests.testVendoredFusedQ4AttentionLaunchPlanUsesOnlineSoftmaxAcrossValueLanes"
        in probe["capability_evidence"]["smoke_tests"]
    )
    assert (
        "WorkerScaffoldTests.testAutoSwiftMLXBackendDecodeUsesVendoredTurboQuantRouteWhenProbeIsDisabled"
        in probe["capability_evidence"]["smoke_tests"]
    )
    assert (
        "WorkerScaffoldTests.testTurboQuantRuntimeRouteReportsRoutedAfterFusedAttentionDispatch"
        in probe["capability_evidence"]["smoke_tests"]
    )
    assert (
        "WorkerScaffoldTests.testTurboQuantRuntimeRouteReportsRoutedFromDispatchEvidenceBeforeStateRecheck"
        in probe["capability_evidence"]["smoke_tests"]
    )
    assert probe["runtime_evidence"]["release_gate_status"] == "fail"
    assert probe["runtime_evidence"]["candidate_eligibility_check_count"] == 64
    assert probe["runtime_evidence"]["decode_model_call_count"] == 63
    assert probe["runtime_evidence"]["decode_token_eval_total_us"] == 720_000
    assert probe["runtime_evidence"]["decode_model_eval_sync_total_us"] == 500_000
    assert probe["runtime_evidence"]["decode_model_eval_sync_call_count"] == 63
    assert probe["runtime_evidence"]["fused_attention_total_us"] == 12_000
    assert probe["runtime_evidence"]["fused_attention_call_count"] == 63
    assert probe["runtime_evidence"]["fused_attention_route_total_us"] == 15_000
    assert probe["runtime_evidence"]["decode_loop_total_us"] == 1_800_000
    assert "active_kv_kernel_path=fallback" in probe["runtime_evidence"]["failures"]
    assert probe["runtime_evidence"]["observed_runtime_routes"] == ["blocked"]
    assert probe["runtime_evidence"]["observed_runtime_block_reasons"] == [
        "attention_hook_unavailable"
    ]
    assert "active_kv_runtime_route=blocked" in probe["runtime_evidence"]["failures"]
    assert (
        "active_kv_runtime_block_reason=attention_hook_unavailable"
        in probe["runtime_evidence"]["failures"]
    )
    assert "active_kv_kernel_path != fallback" in probe["next_required_evidence"]


def test_active_kv_fused_candidate_probe_marks_connected_candidate_dispatch() -> None:
    gates = phase2_metrics_report.build_active_kv_release_gates(
        [
            {
                "label": "decode_turboquant_q4",
                "active_kv_backend": "turboquant",
                "active_kv_kernel_path": "fallback",
                "active_kv_fallback_count": 1,
                "active_kv_candidate_dispatch_code": 1,
                "active_kv_candidate_eligibility_check_count": 1,
                "active_kv_decode_quantize_total_us": 0,
                "active_kv_estimated_memory_savings_pct": 75,
            }
        ],
        {
            "turboquant_q4_vs_baseline": {
                "worker_tps_overhead_pct": 42.62,
                "active_kv_kernel_path": "fallback",
            }
        },
    )

    probes = phase2_metrics_report.build_active_kv_fused_candidate_probes(gates)

    probe = probes["turboquant_q4"]
    assert probe["status"] == "runtime_blocked"
    assert probe["capability_evidence"]["runtime_path"] == "candidate_dispatch_connected"
    assert probe["runtime_evidence"]["candidate_dispatch_count"] == 1
    assert probe["runtime_evidence"]["candidate_eligibility_check_count"] == 1
    assert "active_kv_kernel_path=fallback" in probe["runtime_evidence"]["failures"]
    assert "worker_tps_overhead_pct=42.62" in probe["runtime_evidence"]["failures"]


def test_active_kv_fused_candidate_probe_marks_vendored_runtime_route() -> None:
    gates = phase2_metrics_report.build_active_kv_release_gates(
        [
            {
                "label": "decode_turboquant_q4",
                "active_kv_backend": "turboquant",
                "active_kv_kernel_path": "tq_mse_single",
                "active_kv_runtime_route": "routed",
                "active_kv_fallback_count": 0,
                "active_kv_candidate_dispatch_code": 0,
                "active_kv_decode_quantize_total_us": 0,
                "active_kv_estimated_memory_savings_pct": 75,
            }
        ],
        {
            "turboquant_q4_vs_baseline": {
                "worker_tps_overhead_pct": 68.63,
                "active_kv_kernel_path": "tq_mse_single",
            }
        },
    )

    probes = phase2_metrics_report.build_active_kv_fused_candidate_probes(gates)

    probe = probes["turboquant_q4"]
    assert probe["status"] == "runtime_blocked"
    assert probe["capability_evidence"]["runtime_path"] == "vendored_attention_route_connected"
    assert probe["runtime_evidence"]["candidate_dispatch_count"] == 0
    assert probe["runtime_evidence"]["observed_kernel_paths"] == ["tq_mse_single"]
    assert probe["runtime_evidence"]["observed_runtime_routes"] == ["routed"]
    assert probe["runtime_evidence"]["failures"] == ["worker_tps_overhead_pct=68.63"]


def test_ensure_active_kv_release_gates_backfills_fused_candidate_from_existing_gate() -> None:
    report = {
        "swift_worker_direct": {
            "active_kv_release_gates": {
                "turboquant_fused_decode": {
                    "status": "pass",
                    "observed_kernel_paths": ["tq_mse_single"],
                    "fallback_count": 0,
                    "decode_quantize_total_us": 0,
                    "estimated_memory_savings_pct": 75,
                    "worker_tps_overhead_pct": 12.5,
                    "failures": [],
                }
            }
        }
    }

    phase2_metrics_report.ensure_active_kv_release_gates(report)

    probe = report["swift_worker_direct"]["active_kv_fused_candidate_probes"]["turboquant_q4"]
    assert probe["status"] == "runtime_candidate_pass"
    assert probe["runtime_evidence"]["release_gate_status"] == "pass"
    assert probe["runtime_evidence"]["observed_kernel_paths"] == ["tq_mse_single"]
    assert probe["next_required_evidence"] == []


def test_ensure_active_kv_release_gates_refreshes_existing_gate_when_raw_rows_are_present() -> None:
    report = {
        "swift_worker_direct": {
            "decode": [
                {
                    "label": "decode_turboquant_q4",
                    "active_kv_backend": "turboquant",
                    "active_kv_kernel_path": "tq_mse_single",
                    "active_kv_fallback_count": 0,
                    "active_kv_decode_quantize_total_us": 0,
                    "active_kv_estimated_memory_savings_pct": 75,
                }
            ],
            "comparisons": {
                "turboquant_q4_vs_baseline": {
                    "worker_tps_overhead_pct": 42.62,
                    "active_kv_kernel_path": "tq_mse_single",
                }
            },
            "active_kv_release_gates": {
                "turboquant_fused_decode": {
                    "status": "pass",
                    "failures": [],
                }
            },
        }
    }

    phase2_metrics_report.ensure_active_kv_release_gates(report)

    gate = report["swift_worker_direct"]["active_kv_release_gates"]["turboquant_fused_decode"]
    assert gate["status"] == "fail"
    assert "worker_tps_overhead_pct=42.62" in gate["failures"]
    probe = report["swift_worker_direct"]["active_kv_fused_candidate_probes"]["turboquant_q4"]
    assert probe["runtime_evidence"]["release_gate_status"] == "fail"


def test_fused_turboquant_gate_failure_reporting_handles_malformed_reports() -> None:
    assert phase2_metrics_report.fused_turboquant_gate_failures({}) == ["swift_worker_direct=missing"]
    assert phase2_metrics_report.fused_turboquant_gate_failures(
        {"swift_worker_direct": {"active_kv_release_gates": "bad"}}
    ) == ["active_kv_release_gates=missing"]
    assert phase2_metrics_report.fused_turboquant_gate_failures(
        {"swift_worker_direct": {"active_kv_release_gates": {}}}
    ) == ["turboquant_fused_decode=missing"]
    assert phase2_metrics_report.fused_turboquant_gate_failures(
        {
            "swift_worker_direct": {
                "active_kv_release_gates": {
                    "turboquant_fused_decode": {"status": "pass", "failures": []}
                }
            }
        }
    ) == []
    assert phase2_metrics_report.fused_turboquant_gate_failures(
        {
            "swift_worker_direct": {
                "active_kv_release_gates": {
                    "turboquant_fused_decode": {"status": "fail", "failures": []}
                }
            }
        }
    ) == ["turboquant_fused_decode=fail"]


def test_measure_decode_probe_does_not_leak_active_kv_metrics_into_baseline(tmp_path: Path) -> None:
    metrics_path = tmp_path / "swift-worker-metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "values": {
                    "swift_text.decode_ttft_ms": 12,
                    "swift_text.decode_tokens_per_second": 4,
                    "swift_text.speculative_acceptance_rate": 0,
                    "swift_text.speculative_rollback_rate": 0,
                    "swift_text.speculative_accepted_tokens": 0,
                    "swift_text.speculative_rejected_tokens": 0,
                    "swift_text.speculative_fallback_count": 0,
                    "swift_text.speculative_draft_model_configured": 0,
                    "swift_text.speculative_num_draft_tokens": 0,
                    "swift_text.active_kv_quantization_ratio": 25,
                    "swift_text.active_kv_backend_code": 1,
                    "swift_text.active_kv_kernel_path_code": 10,
                    "swift_text.active_kv_runtime_route_code": 0,
                    "swift_text.active_kv_runtime_block_reason_code": 0,
                    "swift_text.active_kv_prefill_quantize_us": 100,
                    "swift_text.active_kv_decode_model_total_us": 200,
                    "swift_text.active_kv_decode_model_call_count": 10,
                    "swift_text.active_kv_decode_model_avg_us": 20,
                    "swift_text.active_kv_decode_token_eval_total_us": 500,
                    "swift_text.active_kv_decode_token_eval_call_count": 10,
                    "swift_text.active_kv_decode_token_eval_avg_us": 50,
                    "swift_text.active_kv_decode_model_eval_sync_total_us": 1500,
                    "swift_text.active_kv_decode_model_eval_sync_call_count": 3,
                    "swift_text.active_kv_decode_model_eval_sync_avg_us": 500,
                    "swift_text.active_kv_fused_attention_total_us": 750,
                    "swift_text.active_kv_fused_attention_call_count": 3,
                    "swift_text.active_kv_fused_attention_avg_us": 250,
                    "swift_text.active_kv_fused_attention_route_total_us": 900,
                    "swift_text.active_kv_fused_attention_route_avg_us": 300,
                    "swift_text.active_kv_fused_attention_active_lane_total": 96,
                    "swift_text.active_kv_fused_attention_launched_lane_total": 128,
                    "swift_text.active_kv_fused_attention_inactive_lane_total": 32,
                    "swift_text.active_kv_fused_attention_softmax_lane_total": 4,
                    "swift_text.active_kv_fused_attention_softmax_token_lane_total": 256,
                    "swift_text.active_kv_decode_quantize_total_us": 30,
                    "swift_text.active_kv_decode_quantize_avg_us": 3,
                    "swift_text.active_kv_decode_loop_total_us": 900,
                    "swift_text.active_kv_decode_token_count": 10,
                    "swift_text.active_kv_cache_update_total_us": 120,
                    "swift_text.active_kv_cache_update_call_count": 4,
                    "swift_text.active_kv_cache_update_avg_us": 30,
                    "swift_text.active_kv_cache_expand_total_us": 5,
                    "swift_text.active_kv_cache_quantize_total_us": 70,
                    "swift_text.active_kv_cache_append_total_us": 30,
                    "swift_text.active_kv_cache_materialize_total_us": 15,
                    "swift_text.active_kv_cache_materialize_call_count": 3,
                    "swift_text.active_kv_cache_materialize_avg_us": 5,
                    "swift_text.active_kv_estimated_fp16_bytes": 400,
                    "swift_text.active_kv_estimated_quantized_bytes": 100,
                    "swift_text.active_kv_estimated_memory_savings_pct": 75,
                    "swift_text.active_kv_fallback_count": 0,
                    "swift_text.active_kv_candidate_dispatch_code": 0,
                    "swift_text.active_kv_candidate_eligibility_check_count": 7,
                }
            }
        ),
        encoding="utf-8",
    )

    baseline = phase2_metrics_report.measure_decode_probe(
        _FakeInferenceStub(),
        metrics_path,
        model_handle="melix-dev-text::1",
        prompt="decode",
        label="decode_baseline",
        policy=common_pb2.AccelerationPolicy(
            mode=common_pb2.ACCELERATION_MODE_BASELINE,
            allow_baseline_fallback=True,
        ),
    )
    active = phase2_metrics_report.measure_decode_probe(
        _FakeInferenceStub(),
        metrics_path,
        model_handle="melix-dev-text::1",
        prompt="decode",
        label="decode_affine_q4",
        policy=common_pb2.AccelerationPolicy(
            mode=common_pb2.ACCELERATION_MODE_ACTIVE_KV_QUANTIZED,
            active_kv_quant_profile="q4",
            allow_baseline_fallback=True,
        ),
    )

    assert baseline["active_kv_backend"] is None
    assert baseline["active_kv_kernel_path"] is None
    assert baseline["active_kv_runtime_route"] is None
    assert baseline["active_kv_runtime_block_reason"] is None
    assert baseline["active_kv_quantization_ratio"] == 0
    assert baseline["active_kv_estimated_memory_savings_pct"] == 0
    assert baseline["active_kv_decode_model_eval_sync_total_us"] == 0
    assert baseline["active_kv_fused_attention_total_us"] == 0
    assert baseline["active_kv_fused_attention_active_lane_total"] == 0
    assert baseline["active_kv_fused_attention_launched_lane_total"] == 0
    assert baseline["active_kv_fused_attention_inactive_lane_total"] == 0
    assert baseline["active_kv_fused_attention_softmax_lane_total"] == 0
    assert baseline["active_kv_fused_attention_softmax_token_lane_total"] == 0
    assert baseline["speculative_fallback_count"] == 0
    assert active["active_kv_backend"] == "affine"
    assert active["active_kv_kernel_path"] == "affine_quantized_sdpa"
    assert active["active_kv_runtime_route"] is None
    assert active["active_kv_runtime_block_reason"] is None
    assert active["active_kv_estimated_memory_savings_pct"] == 75
    assert active["active_kv_decode_model_call_count"] == 10
    assert active["active_kv_decode_token_eval_call_count"] == 10
    assert active["active_kv_decode_token_eval_avg_us"] == 50
    assert active["active_kv_decode_model_eval_sync_total_us"] == 1500
    assert active["active_kv_decode_model_eval_sync_call_count"] == 3
    assert active["active_kv_decode_model_eval_sync_avg_us"] == 500
    assert active["active_kv_fused_attention_total_us"] == 750
    assert active["active_kv_fused_attention_call_count"] == 3
    assert active["active_kv_fused_attention_avg_us"] == 250
    assert active["active_kv_fused_attention_route_total_us"] == 900
    assert active["active_kv_fused_attention_route_avg_us"] == 300
    assert active["active_kv_fused_attention_active_lane_total"] == 96
    assert active["active_kv_fused_attention_launched_lane_total"] == 128
    assert active["active_kv_fused_attention_inactive_lane_total"] == 32
    assert active["active_kv_fused_attention_softmax_lane_total"] == 4
    assert active["active_kv_fused_attention_softmax_token_lane_total"] == 256
    assert active["active_kv_decode_loop_total_us"] == 900
    assert active["active_kv_cache_update_total_us"] == 120
    assert active["active_kv_cache_update_call_count"] == 4
    assert active["active_kv_cache_update_avg_us"] == 30
    assert active["active_kv_cache_expand_total_us"] == 5
    assert active["active_kv_cache_quantize_total_us"] == 70
    assert active["active_kv_cache_append_total_us"] == 30
    assert active["active_kv_cache_materialize_total_us"] == 15
    assert active["active_kv_cache_materialize_call_count"] == 3
    assert active["active_kv_cache_materialize_avg_us"] == 5
    assert active["active_kv_candidate_eligibility_check_count"] == 7


def test_active_kv_helper_edges_return_stable_defaults() -> None:
    assert phase2_metrics_report.parse_active_kv_profiles("") == ["q4"]
    assert phase2_metrics_report.parse_active_kv_profiles("q4, turboquant-q4, custom.v1") == [
        "q4",
        "turboquant-q4",
        "custom.v1",
    ]
    assert phase2_metrics_report.active_kv_decode_label("turboquant-q4") == "decode_turboquant_q4"
    assert phase2_metrics_report.active_kv_decode_label("custom.v1") == "decode_active_kv_customv1"

    inactive_metrics = phase2_metrics_report.decode_active_kv_metrics(
        {},
        common_pb2.AccelerationPolicy(mode=common_pb2.ACCELERATION_MODE_BASELINE),
    )
    assert inactive_metrics["active_kv_backend"] is None
    assert inactive_metrics["active_kv_kernel_path"] is None
    assert inactive_metrics["active_kv_runtime_route"] is None
    assert inactive_metrics["active_kv_runtime_block_reason"] is None
    assert inactive_metrics["active_kv_estimated_memory_savings_pct"] == 0
    assert inactive_metrics["active_kv_decode_model_call_count"] == 0
    assert inactive_metrics["active_kv_decode_token_eval_call_count"] == 0
    assert inactive_metrics["active_kv_decode_token_eval_avg_us"] == 0
    assert inactive_metrics["active_kv_decode_model_eval_sync_total_us"] == 0
    assert inactive_metrics["active_kv_decode_model_eval_sync_call_count"] == 0
    assert inactive_metrics["active_kv_decode_model_eval_sync_avg_us"] == 0
    assert inactive_metrics["active_kv_fused_attention_total_us"] == 0
    assert inactive_metrics["active_kv_fused_attention_call_count"] == 0
    assert inactive_metrics["active_kv_fused_attention_avg_us"] == 0
    assert inactive_metrics["active_kv_fused_attention_route_total_us"] == 0
    assert inactive_metrics["active_kv_fused_attention_route_avg_us"] == 0
    assert inactive_metrics["active_kv_fused_attention_active_lane_total"] == 0
    assert inactive_metrics["active_kv_fused_attention_launched_lane_total"] == 0
    assert inactive_metrics["active_kv_fused_attention_inactive_lane_total"] == 0
    assert inactive_metrics["active_kv_fused_attention_softmax_lane_total"] == 0
    assert inactive_metrics["active_kv_fused_attention_softmax_token_lane_total"] == 0
    assert inactive_metrics["active_kv_decode_loop_total_us"] == 0
    assert inactive_metrics["active_kv_cache_update_total_us"] == 0
    assert inactive_metrics["active_kv_cache_update_call_count"] == 0
    assert inactive_metrics["active_kv_cache_update_avg_us"] == 0
    assert inactive_metrics["active_kv_cache_materialize_total_us"] == 0
    assert inactive_metrics["active_kv_cache_materialize_call_count"] == 0
    assert inactive_metrics["active_kv_cache_materialize_avg_us"] == 0
    assert inactive_metrics["active_kv_candidate_eligibility_check_count"] == 0

    assert phase2_metrics_report.active_kv_backend_name("not-an-int") is None
    assert phase2_metrics_report.active_kv_backend_name(7) == "unknown_7"
    assert phase2_metrics_report.active_kv_kernel_path_name(None) is None
    assert phase2_metrics_report.active_kv_kernel_path_name(77) == "unknown_77"
    assert phase2_metrics_report.active_kv_runtime_route_name(None) is None
    assert phase2_metrics_report.active_kv_runtime_route_name(1) == "blocked"
    assert phase2_metrics_report.active_kv_runtime_route_name(42) == "unknown_42"
    assert phase2_metrics_report.active_kv_runtime_block_reason_name(None) is None
    assert phase2_metrics_report.active_kv_runtime_block_reason_name(2) == "attention_hook_unavailable"
    assert phase2_metrics_report.active_kv_runtime_block_reason_name(42) == "unknown_42"
    assert phase2_metrics_report.overhead_percent(None, 1.0) is None
    assert phase2_metrics_report.overhead_percent(0.0, 1.0) is None
    assert phase2_metrics_report.delta(None, 1.0) is None
    assert phase2_metrics_report.quantize_share_percent(None, 1.0) is None
    assert phase2_metrics_report.quantize_share_percent(0.0, 0.0) is None
    assert phase2_metrics_report.first_non_empty([{"value": None}, {"value": ""}, {"value": 0}], "value") is None


def test_resolve_model_configuration_real_small_model_uses_hf_cache_snapshot(tmp_path: Path) -> None:
    hf_home = tmp_path / "hf"
    snapshot = (
        hf_home
        / "hub"
        / "models--mlx-community--Qwen3.5-0.8B-OptiQ-4bit"
        / "snapshots"
        / "abc123"
    )
    snapshot.mkdir(parents=True)
    refs = snapshot.parents[1] / "refs"
    refs.mkdir()
    (refs / "main").write_text("abc123\n", encoding="utf-8")

    model = phase2_metrics_report.resolve_model_configuration(
        real_small_model=True,
        model_id="",
        model_path="",
        model_revision="",
        environment={"HF_HOME": str(hf_home)},
    )

    assert model.model_id == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
    assert model.model_path == str(snapshot.resolve())
    assert model.revision == "main"
    assert model.source_resolution_mode == "hf_cache_snapshot"
    assert model.warnings == ()


def test_resolve_model_configuration_real_small_model_warns_on_hf_cache_snapshot_fallback(
    tmp_path: Path,
) -> None:
    hf_home = tmp_path / "hf"
    snapshot = (
        hf_home
        / "hub"
        / "models--mlx-community--Qwen3.5-0.8B-OptiQ-4bit"
        / "snapshots"
        / "def456"
    )
    snapshot.mkdir(parents=True)

    model = phase2_metrics_report.resolve_model_configuration(
        real_small_model=True,
        model_id="",
        model_path="",
        model_revision="",
        environment={"HF_HOME": str(hf_home)},
    )

    assert model.model_path == str(snapshot.resolve())
    assert model.source_resolution_mode == "hf_cache_snapshot"
    assert len(model.warnings) == 1
    assert "refs/main" in model.warnings[0]
    assert "def456" in model.warnings[0]


def test_resolve_model_configuration_live_pair_uses_explicit_env(tmp_path: Path) -> None:
    served = tmp_path / "served"
    draft = tmp_path / "draft"
    served.mkdir()
    draft.mkdir()
    (served / "model.safetensors.index.json").write_text("{}", encoding="utf-8")
    (draft / "model.safetensors.index.json").write_text("{}", encoding="utf-8")

    model = phase2_metrics_report.resolve_model_configuration(
        live_model=True,
        require_live_model=True,
        real_small_model=False,
        model_id="",
        model_path="",
        model_revision="",
        environment={
            "MELIX_PHASE2_LIVE_MODEL_ID": "served/live",
            "MELIX_PHASE2_LIVE_MODEL_PATH": str(served),
            "MELIX_PHASE2_DRAFT_MODEL_ID": "draft/live",
            "MELIX_PHASE2_DRAFT_MODEL_PATH": str(draft),
        },
    )

    assert model.model_id == "served/live"
    assert model.model_path == str(served.resolve())
    assert model.served_runtime_model_class == "real_local_model"
    assert model.draft_model_id == "draft/live"
    assert model.draft_model_path == str(draft.resolve())
    assert model.draft_runtime_model_class == "real_local_model"
    assert model.live_model_required is True


def test_resolve_model_configuration_live_pair_defaults_draft_to_hub_when_cache_is_missing(
    tmp_path: Path,
) -> None:
    model = phase2_metrics_report.resolve_model_configuration(
        live_model=True,
        require_live_model=True,
        real_small_model=False,
        model_id="served/live",
        model_path="",
        model_revision="",
        environment={"HF_HOME": str(tmp_path / "empty-hf-cache")},
    )

    assert model.model_id == "served/live"
    assert model.served_runtime_model_class == "hub_required"
    assert model.draft_model_id == "mlx-community/Qwen3-0.6B-4bit"
    assert model.draft_model_path == "mlx-community/Qwen3-0.6B-4bit"
    assert model.draft_source_resolution_mode == "hub_fallback"
    assert model.draft_runtime_model_class == "hub_required"


def test_resolve_model_configuration_live_pair_uses_default_draft_hf_cache_snapshot(
    tmp_path: Path,
) -> None:
    hf_home = tmp_path / "hf"
    draft_snapshot = (
        hf_home
        / "hub"
        / "models--mlx-community--Qwen3-0.6B-4bit"
        / "snapshots"
        / "draft123"
    )
    draft_snapshot.mkdir(parents=True)
    (draft_snapshot / "model.safetensors.index.json").write_text("{}", encoding="utf-8")
    refs = draft_snapshot.parents[1] / "refs"
    refs.mkdir()
    (refs / "main").write_text("draft123\n", encoding="utf-8")

    model = phase2_metrics_report.resolve_model_configuration(
        live_model=True,
        require_live_model=True,
        real_small_model=False,
        model_id="served/live",
        model_path="",
        model_revision="",
        environment={"HF_HOME": str(hf_home)},
    )

    assert model.draft_model_id == "mlx-community/Qwen3-0.6B-4bit"
    assert model.draft_model_path == str(draft_snapshot.resolve())
    assert model.draft_source_resolution_mode == "hf_cache_snapshot"
    assert model.draft_runtime_model_class == "real_local_model"


def test_resolve_model_configuration_require_live_rejects_invalid_local_draft(
    tmp_path: Path,
) -> None:
    draft = tmp_path / "empty-draft"
    draft.mkdir()

    with pytest.raises(RuntimeError, match="draft_model=missing_real_local_model"):
        phase2_metrics_report.resolve_model_configuration(
            live_model=True,
            require_live_model=True,
            real_small_model=False,
            model_id="served/live",
            model_path="",
            model_revision="",
            draft_model_id="draft/live",
            draft_model_path=str(draft),
            environment={"HF_HOME": str(tmp_path / "empty-hf-cache")},
        )


def test_collect_direct_phase_two_metrics_loads_configured_model_revision(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stack = phase2_metrics_report.StackConfiguration(
        runtime_dir=tmp_path,
        swift_socket_path=tmp_path / "swift.sock",
        python_socket_path=tmp_path / "python.sock",
        http_port=8080,
        swift_backend_mode="deterministic",
        python_backend_mode="deterministic",
        control_plane_metrics_path=tmp_path / "control-plane-metrics.json",
        swift_worker_metrics_path=tmp_path / "swift-worker-metrics.json",
    )
    stack.control_plane_metrics_path.write_text(json.dumps({"values": {}}), encoding="utf-8")
    stack.swift_worker_metrics_path.write_text(json.dumps({"values": {}}), encoding="utf-8")
    runtime_stub = _FakeRuntimeStub()

    monkeypatch.setattr(phase2_metrics_report.grpc, "insecure_channel", lambda target: _FakeChannel())
    monkeypatch.setattr(
        phase2_metrics_report.runtime_pb2_grpc,
        "RuntimeServiceStub",
        lambda channel: runtime_stub,
    )
    monkeypatch.setattr(
        phase2_metrics_report.inference_pb2_grpc,
        "InferenceServiceStub",
        lambda channel: _FakeInferenceStub(),
    )
    monkeypatch.setattr(phase2_metrics_report, "wait_for_worker_handshake", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        phase2_metrics_report,
        "measure_prefill_probe",
        lambda *args, **kwargs: {"label": kwargs["label"], "mode": "ACCELERATION_MODE_BASELINE"},
    )
    monkeypatch.setattr(
        phase2_metrics_report,
        "measure_decode_probe",
        lambda *args, **kwargs: {"label": kwargs["label"], "mode": "ACCELERATION_MODE_BASELINE"},
    )
    monkeypatch.setattr(
        phase2_metrics_report,
        "measure_decode_abort",
        lambda *args, **kwargs: {"label": "decode_abort", "abort_ms": 1.0, "finish_reason": "cancelled"},
    )

    model = phase2_metrics_report.Phase2ModelConfiguration(
        model_id="melix-dev-text",
        model_path=str(tmp_path / "qwen-real-small"),
        revision="main",
        source_resolution_mode="hf_cache_snapshot",
    )
    phase2_metrics_report.collect_direct_phase_two_metrics(
        stack=stack,
        prompt="decode",
        queue_prompt='{"kind":"structured"}',
        abort_prompt="abort prompt",
        decode_repeats=1,
        active_kv_profiles=["q4"],
        model=model,
    )

    loaded_model = runtime_stub.load_requests[0].model
    assert loaded_model.model_id == "melix-dev-text"
    assert loaded_model.model_path == str(tmp_path / "qwen-real-small")
    assert loaded_model.revision == "main"


def test_collect_direct_phase_two_metrics_loads_configured_draft_model(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stack = phase2_metrics_report.StackConfiguration(
        runtime_dir=tmp_path,
        swift_socket_path=tmp_path / "swift.sock",
        python_socket_path=tmp_path / "python.sock",
        http_port=8080,
        swift_backend_mode="swift",
        python_backend_mode="auto",
        control_plane_metrics_path=tmp_path / "control-plane-metrics.json",
        swift_worker_metrics_path=tmp_path / "swift-worker-metrics.json",
    )
    stack.control_plane_metrics_path.write_text(json.dumps({"values": {}}), encoding="utf-8")
    stack.swift_worker_metrics_path.write_text(
        json.dumps(
            {
                "values": {
                    "swift_text.speculative_fallback_count": 1,
                    "swift_text.speculative_draft_model_configured": 1,
                    "swift_text.speculative_num_draft_tokens": 6,
                }
            }
        ),
        encoding="utf-8",
    )
    runtime_stub = _FakeRuntimeStub()

    monkeypatch.setattr(phase2_metrics_report.grpc, "insecure_channel", lambda target: _FakeChannel())
    monkeypatch.setattr(phase2_metrics_report.runtime_pb2_grpc, "RuntimeServiceStub", lambda channel: runtime_stub)
    monkeypatch.setattr(phase2_metrics_report.inference_pb2_grpc, "InferenceServiceStub", lambda channel: _FakeInferenceStub())
    monkeypatch.setattr(phase2_metrics_report, "wait_for_worker_handshake", lambda *args, **kwargs: None)
    monkeypatch.setattr(phase2_metrics_report, "measure_prefill_probe", lambda *args, **kwargs: {"label": kwargs["label"]})
    monkeypatch.setattr(
        phase2_metrics_report,
        "measure_decode_abort",
        lambda *args, **kwargs: {"label": "decode_abort", "abort_ms": 1.0, "finish_reason": "cancelled"},
    )

    observed_policies: list[common_pb2.AccelerationPolicy] = []

    def fake_measure_decode_probe(*args, **kwargs):  # noqa: ANN002, ANN003
        observed_policies.append(kwargs["policy"])
        return {"label": kwargs["label"], "mode": "ACCELERATION_MODE_BASELINE"}

    monkeypatch.setattr(phase2_metrics_report, "measure_decode_probe", fake_measure_decode_probe)

    model = phase2_metrics_report.Phase2ModelConfiguration(
        model_id="served/live",
        model_path="/models/served",
        revision="main",
        source_resolution_mode="explicit_local_path",
        draft_model_id="draft/live",
        draft_model_path="/models/draft",
        draft_revision="main",
        draft_source_resolution_mode="explicit_local_path",
        num_draft_tokens=6,
    )
    result = phase2_metrics_report.collect_direct_phase_two_metrics(
        stack=stack,
        prompt="decode",
        queue_prompt='{"kind":"structured"}',
        abort_prompt="abort prompt",
        decode_repeats=1,
        active_kv_profiles=["q4"],
        model=model,
    )

    assert [request.model.model_id for request in runtime_stub.load_requests] == ["served/live", "draft/live"]
    assert runtime_stub.load_requests[0].model.tokenizer_hash == runtime_stub.load_requests[1].model.tokenizer_hash
    speculative_policy = observed_policies[-1]
    assert speculative_policy.draft_model_id == "draft/live"
    assert speculative_policy.num_draft_tokens == 6
    assert result["swift_worker_direct"]["draft_load_model_ms"] is not None
    assert result["swift_worker_direct"]["resident_bytes"] == 8192


def test_collect_direct_phase_two_metrics_can_skip_abort_probe(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stack = phase2_metrics_report.StackConfiguration(
        runtime_dir=tmp_path,
        swift_socket_path=tmp_path / "swift.sock",
        python_socket_path=tmp_path / "python.sock",
        http_port=8080,
        swift_backend_mode="deterministic",
        python_backend_mode="deterministic",
        control_plane_metrics_path=tmp_path / "control-plane-metrics.json",
        swift_worker_metrics_path=tmp_path / "swift-worker-metrics.json",
    )
    stack.control_plane_metrics_path.write_text(json.dumps({"values": {}}), encoding="utf-8")
    stack.swift_worker_metrics_path.write_text(json.dumps({"values": {}}), encoding="utf-8")

    monkeypatch.setattr(phase2_metrics_report.grpc, "insecure_channel", lambda target: _FakeChannel())
    monkeypatch.setattr(
        phase2_metrics_report.runtime_pb2_grpc,
        "RuntimeServiceStub",
        lambda channel: _FakeRuntimeStub(),
    )
    monkeypatch.setattr(
        phase2_metrics_report.inference_pb2_grpc,
        "InferenceServiceStub",
        lambda channel: _FakeInferenceStub(),
    )
    monkeypatch.setattr(phase2_metrics_report, "wait_for_worker_handshake", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        phase2_metrics_report,
        "measure_prefill_probe",
        lambda *args, **kwargs: {"label": kwargs["label"], "mode": "ACCELERATION_MODE_BASELINE"},
    )
    monkeypatch.setattr(
        phase2_metrics_report,
        "measure_decode_probe",
        lambda *args, **kwargs: {"label": kwargs["label"], "mode": "ACCELERATION_MODE_BASELINE"},
    )

    abort_probe = Mock(side_effect=AssertionError("abort probe should be skipped"))
    monkeypatch.setattr(phase2_metrics_report, "measure_decode_abort", abort_probe)

    result = phase2_metrics_report.collect_direct_phase_two_metrics(
        stack=stack,
        prompt="decode",
        queue_prompt='{"kind":"structured"}',
        abort_prompt="abort prompt",
        decode_repeats=1,
        active_kv_profiles=["q4"],
        skip_abort=True,
    )

    assert result["swift_worker_direct"]["abort"] == {
        "label": "decode_abort",
        "skipped": True,
        "reason": "disabled_by_cli",
    }
    abort_probe.assert_not_called()


def test_main_assembles_report_from_cli_model_options(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    output_path = tmp_path / "phase2.json"
    stack = phase2_metrics_report.StackConfiguration(
        runtime_dir=tmp_path / "runtime",
        swift_socket_path=tmp_path / "swift.sock",
        python_socket_path=tmp_path / "python.sock",
        http_port=8080,
        swift_backend_mode="swift-mlx",
        python_backend_mode="auto",
        control_plane_metrics_path=tmp_path / "control-plane-metrics.json",
        swift_worker_metrics_path=tmp_path / "swift-worker-metrics.json",
    )
    model = phase2_metrics_report.Phase2ModelConfiguration(
        model_id="melix-dev-text",
        model_path="/models/qwen-real-small",
        revision="main",
        source_resolution_mode="explicit",
        warnings=("cache miss",),
    )

    monkeypatch.setattr(phase2_metrics_report, "resolve_stack_configuration", lambda runtime_dir: stack)

    resolved_model_args: dict[str, object] = {}

    def fake_resolve_model_configuration(**kwargs):  # noqa: ANN003
        resolved_model_args.update(kwargs)
        return model

    monkeypatch.setattr(phase2_metrics_report, "resolve_model_configuration", fake_resolve_model_configuration)
    monkeypatch.setattr(
        phase2_metrics_report,
        "measure_http_stream",
        lambda port, prompt, *, label, model_id: {
            "label": label,
            "port": port,
            "prompt": prompt,
            "model_id": model_id,
        },
    )
    monkeypatch.setattr(
        phase2_metrics_report,
        "measure_queue_pressure",
        lambda stack, prompt, *, model_id: {"prompt": prompt, "model_id": model_id},
    )

    direct_args: dict[str, object] = {}

    def fake_collect_direct_phase_two_metrics(**kwargs):  # noqa: ANN003
        direct_args.update(kwargs)
        return {"swift_worker_direct": {"decode": [], "prefill": [], "comparisons": {}, "abort": {}}}

    monkeypatch.setattr(phase2_metrics_report, "collect_direct_phase_two_metrics", fake_collect_direct_phase_two_metrics)
    monkeypatch.setattr(phase2_metrics_report, "read_metrics_export", lambda path: {"path": str(path)})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "phase2_metrics_report.py",
            "--runtime-dir",
            str(stack.runtime_dir),
            "--decode-repeats",
            "3",
            "--active-kv-profiles",
            "q4,turboquant-q4",
            "--model-id",
            "melix-dev-text",
            "--model-path",
            "/models/qwen-real-small",
            "--model-revision",
            "main",
            "--real-small-model",
            "--skip-abort",
            "--output",
            str(output_path),
            "--json",
        ],
    )

    phase2_metrics_report.main()

    emitted = json.loads(capsys.readouterr().out)
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert emitted["model_path"] == "/models/qwen-real-small"
    assert written["model_warnings"] == ["cache miss"]
    assert resolved_model_args["real_small_model"] is True
    assert direct_args["decode_repeats"] == 3
    assert direct_args["active_kv_profiles"] == ["q4", "turboquant-q4"]
    assert direct_args["skip_abort"] is True


def test_main_can_require_fused_turboquant_after_writing_report(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    output_path = tmp_path / "phase2.json"
    stack = phase2_metrics_report.StackConfiguration(
        runtime_dir=tmp_path / "runtime",
        swift_socket_path=tmp_path / "swift.sock",
        python_socket_path=tmp_path / "python.sock",
        http_port=8080,
        swift_backend_mode="swift-mlx",
        python_backend_mode="auto",
        control_plane_metrics_path=tmp_path / "control-plane-metrics.json",
        swift_worker_metrics_path=tmp_path / "swift-worker-metrics.json",
    )
    model = phase2_metrics_report.Phase2ModelConfiguration(
        model_id="melix-dev-text",
        model_path="/models/qwen-real-small",
        revision="main",
        source_resolution_mode="explicit",
    )

    monkeypatch.setattr(phase2_metrics_report, "resolve_stack_configuration", lambda runtime_dir: stack)
    monkeypatch.setattr(phase2_metrics_report, "resolve_model_configuration", lambda **kwargs: model)
    monkeypatch.setattr(
        phase2_metrics_report,
        "measure_http_stream",
        lambda port, prompt, *, label, model_id: {"label": label},
    )
    monkeypatch.setattr(
        phase2_metrics_report,
        "measure_queue_pressure",
        lambda stack, prompt, *, model_id: {
            "leader": {"label": "queue_leader"},
            "follower": {"label": "queue_follower"},
            "scheduler": {},
        },
    )
    monkeypatch.setattr(
        phase2_metrics_report,
        "collect_direct_phase_two_metrics",
        lambda **kwargs: {
            "swift_worker_direct": {
                "decode": [
                    {
                        "label": "decode_turboquant_q4",
                        "active_kv_backend": "turboquant",
                        "active_kv_kernel_path": "fallback",
                        "active_kv_fallback_count": 0,
                        "active_kv_decode_quantize_total_us": 0,
                        "active_kv_estimated_memory_savings_pct": 75,
                    }
                ],
                "prefill": [],
                "comparisons": {
                    "turboquant_q4_vs_baseline": {
                        "worker_tps_overhead_pct": 43.55,
                        "active_kv_kernel_path": "fallback",
                    }
                },
                "abort": {},
            }
        },
    )
    monkeypatch.setattr(phase2_metrics_report, "read_metrics_export", lambda path: {"path": str(path)})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "phase2_metrics_report.py",
            "--runtime-dir",
            str(stack.runtime_dir),
            "--active-kv-profiles",
            "turboquant-q4",
            "--output",
            str(output_path),
            "--json",
            "--require-fused-turboquant",
        ],
    )

    try:
        phase2_metrics_report.main()
    except SystemExit as exc:
        assert exc.code != 0
        assert "active_kv_kernel_path=fallback" in str(exc)
    else:
        raise AssertionError("expected fused TurboQuant gate to fail")

    emitted = json.loads(capsys.readouterr().out)
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert emitted["swift_worker_direct"]["active_kv_release_gates"]["turboquant_fused_decode"]["status"] == "fail"
    assert written["swift_worker_direct"]["active_kv_release_gates"]["turboquant_fused_decode"]["status"] == "fail"
    assert emitted["swift_worker_direct"]["active_kv_fused_candidate_probes"]["turboquant_q4"]["status"] == (
        "runtime_blocked"
    )
    assert written["swift_worker_direct"]["active_kv_fused_candidate_probes"]["turboquant_q4"]["runtime_evidence"][
        "release_gate_status"
    ] == "fail"


def test_main_backfills_fused_candidate_probe_from_input_json_before_gate_failure(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    input_path = tmp_path / "postopt.json"
    output_path = tmp_path / "candidate.json"
    input_path.write_text(
        json.dumps(
            {
                "model_path": "/models/qwen-real-small",
                "swift_worker_direct": {
                    "active_kv_release_gates": {
                        "turboquant_fused_decode": {
                            "status": "fail",
                            "profile_label": "decode_turboquant_q4",
                            "observed_kernel_paths": ["fallback"],
                            "fallback_count": 5,
                            "decode_quantize_total_us": 0,
                            "estimated_memory_savings_pct": 75,
                            "worker_tps_overhead_pct": 42.62,
                            "failures": ["active_kv_kernel_path=fallback"],
                        }
                    },
                    "active_kv_fused_candidate_probes": {
                        "turboquant_q4": {
                            "status": "stale",
                            "profile_label": "decode_turboquant_q4",
                            "capability_evidence": {
                                "status": "smoke_proven",
                                "runtime_path": "not_connected",
                                "smoke_tests": ["WorkerScaffoldTests.testOldTurboQuantSmoke"],
                            },
                            "runtime_evidence": {
                                "release_gate_status": "stale",
                                "observed_kernel_paths": [],
                            },
                            "next_required_evidence": [],
                        }
                    },
                    "decode": [],
                    "prefill": [],
                    "comparisons": {},
                    "abort": {},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        phase2_metrics_report,
        "resolve_stack_configuration",
        Mock(side_effect=AssertionError("input JSON mode must not require a running stack")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "phase2_metrics_report.py",
            "--input-json",
            str(input_path),
            "--output",
            str(output_path),
            "--json",
            "--require-fused-turboquant",
        ],
    )

    try:
        phase2_metrics_report.main()
    except SystemExit as exc:
        assert exc.code != 0
        assert "active_kv_kernel_path=fallback" in str(exc)
    else:
        raise AssertionError("expected fused TurboQuant gate to fail")

    emitted = json.loads(capsys.readouterr().out)
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert emitted["model_path"] == "/models/qwen-real-small"
    assert written["swift_worker_direct"]["active_kv_fused_candidate_probes"]["turboquant_q4"]["status"] == (
        "runtime_blocked"
    )
    assert written["swift_worker_direct"]["active_kv_fused_candidate_probes"]["turboquant_q4"]["runtime_evidence"][
        "observed_kernel_paths"
    ] == ["fallback"]
    smoke_tests = written["swift_worker_direct"]["active_kv_fused_candidate_probes"]["turboquant_q4"][
        "capability_evidence"
    ]["smoke_tests"]
    assert "WorkerScaffoldTests.testOldTurboQuantSmoke" not in smoke_tests
    assert (
        "WorkerScaffoldTests.testTurboQuantMetalCapabilityRunsMSEQ4FusedAttentionFromQuantizedKVCacheState"
        in smoke_tests
    )
    assert (
        "WorkerScaffoldTests.testTurboQuantMetalCapabilityRejectsUnsupportedQuantizedKVCacheStateInputs"
        in smoke_tests
    )
    assert "WorkerScaffoldTests.testTurboQuantCandidateDispatchReadsQuantizedKVCacheState" in smoke_tests
    assert "WorkerScaffoldTests.testVendoredFusedQ4AttentionMatchesQuantizedReferenceForDecodeGQA" in smoke_tests
    assert (
        "WorkerScaffoldTests.testAttentionWithCacheUpdateUsesFusedQuantizedStorageWithoutMaterializingForDecode"
        in smoke_tests
    )
    assert "WorkerScaffoldTests.testFusedDecodeQuantizerMatchesReferenceForSingleTokenAffineQ4" in smoke_tests
    assert "WorkerScaffoldTests.testFusedDecodeQuantizerMatchesReferenceForSingleTokenBFloat16AffineQ4" in smoke_tests
    assert "WorkerScaffoldTests.testFusedDecodeQuantizerRejectsUnsupportedInputs" in smoke_tests
    assert "WorkerScaffoldTests.testFusedDecodeQuantizerDefaultReadsInjectedEnvironment" in smoke_tests
    assert (
        "WorkerScaffoldTests.testQuantizedKVCacheUsesNativeDecodeQuantizerByDefaultForSingleTokenAffineQ4"
        in smoke_tests
    )
    assert (
        "WorkerScaffoldTests.testQuantizedKVCacheUsesFusedDecodeQuantizerWhenExplicitlyEnabledForSingleTokenAffineQ4"
        in smoke_tests
    )
    assert "WorkerScaffoldTests.testVendoredFusedQ4AttentionLaunchPlanUsesOnlineSoftmaxAcrossValueLanes" in smoke_tests
    assert "WorkerScaffoldTests.testAutoSwiftMLXBackendDecodeUsesVendoredTurboQuantRouteWhenProbeIsDisabled" in smoke_tests
    assert "WorkerScaffoldTests.testTurboQuantRuntimeRouteReportsRoutedAfterFusedAttentionDispatch" in smoke_tests
    assert "WorkerScaffoldTests.testTurboQuantRuntimeRouteReportsRoutedFromDispatchEvidenceBeforeStateRecheck" in smoke_tests


def test_main_backfills_input_json_without_gate_requirement(tmp_path: Path, monkeypatch, capsys) -> None:
    input_path = tmp_path / "postopt.json"
    input_path.write_text(
        json.dumps(
            {
                "swift_worker_direct": {
                    "decode": [],
                    "prefill": [],
                    "comparisons": {},
                    "abort": {},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        phase2_metrics_report,
        "resolve_stack_configuration",
        Mock(side_effect=AssertionError("input JSON mode must not require a running stack")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "phase2_metrics_report.py",
            "--input-json",
            str(input_path),
            "--json",
        ],
    )

    phase2_metrics_report.main()

    emitted = json.loads(capsys.readouterr().out)
    assert emitted["swift_worker_direct"]["active_kv_fused_candidate_probes"]["turboquant_q4"]["status"] == (
        "not_requested"
    )


def test_turboquant_stability_summary_excludes_warmup_from_gate_stats(tmp_path: Path) -> None:
    input_paths = [tmp_path / "warmup.json", tmp_path / "measured-1.json", tmp_path / "measured-2.json"]
    reports = [
        _turboquant_stability_report(
            worker_overhead=80.0,
            wall_overhead=82.0,
            kernel_path="fallback",
            route="blocked",
            fallback_count=1,
            softmax_token_lanes=999,
        ),
        _turboquant_stability_report(worker_overhead=12.0, wall_overhead=13.0, softmax_token_lanes=64),
        _turboquant_stability_report(worker_overhead=10.0, wall_overhead=11.0, softmax_token_lanes=64),
    ]
    (tmp_path / "gate-1.log").write_text("pass", encoding="utf-8")
    for path, report in zip(input_paths, reports):
        path.write_text(json.dumps(report), encoding="utf-8")

    summary = phase2_metrics_report.build_turboquant_stability_summary(
        reports=reports,
        input_paths=input_paths,
        warmup_count=1,
        required_runs=2,
        model="mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
        runtime_dir="/tmp/runtime",
        output_dir="/tmp/output",
        committed_summary_path="docs/metrics/stability.json",
        probe_environment={"MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE": "1"},
    )

    assert summary["warmup_run"]["run"] == 0
    assert summary["warmup_run"]["gate"] == "fail"
    assert summary["warmup_run"]["worker_tps_overhead_pct"] == 80.0
    assert summary["pass_count"] == 2
    assert summary["run_count"] == 2
    assert summary["all_gate_passed"] is True
    assert summary["all_non_fallback"] is True
    assert summary["all_routed"] is True
    assert summary["worker_tps_overhead_pct"] == {"min": 10.0, "median": 11.0, "mean": 11.0, "max": 12.0}
    assert summary["runs"][0]["gate_log_path"] == str(tmp_path / "gate-1.log")
    assert summary["fused_attention_softmax_token_lane_total"] == {
        "min": 64,
        "median": 64,
        "mean": 64,
        "max": 64,
    }
    assert phase2_metrics_report.fused_turboquant_stability_failures(summary) == []


def test_turboquant_stability_summary_records_multiple_warmups(tmp_path: Path) -> None:
    reports = [
        _turboquant_stability_report(worker_overhead=50.0),
        _turboquant_stability_report(worker_overhead=40.0),
        _turboquant_stability_report(worker_overhead=9.0),
    ]

    summary = phase2_metrics_report.build_turboquant_stability_summary(
        reports=reports,
        input_paths=[tmp_path / "warmup-a.json", tmp_path / "warmup-b.json", tmp_path / "measured-1.json"],
        warmup_count=2,
        required_runs=1,
    )

    assert [run["run"] for run in summary["warmup_runs"]] == [0, 1]
    assert summary["runs"][0]["run"] == 1
    assert summary["model"] == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"


def test_main_writes_turboquant_stability_summary_and_enforces_gate(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    warmup_path = tmp_path / "warmup.json"
    measured_path = tmp_path / "measured-1.json"
    output_path = tmp_path / "summary.json"
    warmup_path.write_text(json.dumps(_turboquant_stability_report(worker_overhead=99.0)), encoding="utf-8")
    measured_path.write_text(json.dumps(_turboquant_stability_report(worker_overhead=8.0)), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "phase2_metrics_report.py",
            "--stability-input-json",
            str(warmup_path),
            "--stability-input-json",
            str(measured_path),
            "--stability-warmup-count",
            "1",
            "--stability-required-runs",
            "1",
            "--stability-model",
            "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            "--stability-probe-env",
            "MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE=1",
            "--output",
            str(output_path),
            "--require-fused-turboquant",
        ],
    )

    phase2_metrics_report.main()

    emitted = json.loads(capsys.readouterr().out)
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert emitted["measurement_protocol"].startswith("1 warmup run(s) followed by 1 measured run(s)")
    assert written["warmup_run"]["worker_tps_overhead_pct"] == 99.0
    assert written["run_count"] == 1
    assert written["all_gate_passed"] is True
    assert written["probe_environment"]["MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE"] == "1"


def test_main_rejects_conflicting_stability_and_single_input_modes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    input_path = tmp_path / "measured.json"
    input_path.write_text(json.dumps(_turboquant_stability_report(worker_overhead=8.0)), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "phase2_metrics_report.py",
            "--input-json",
            str(input_path),
            "--stability-input-json",
            str(input_path),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        phase2_metrics_report.main()
    assert "--input-json and --stability-input-json are mutually exclusive" in str(exc.value)


def test_main_rejects_failed_turboquant_stability_gate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    measured_path = tmp_path / "measured-1.json"
    measured_path.write_text(
        json.dumps(
            _turboquant_stability_report(
                worker_overhead=20.0,
                kernel_path="fallback",
                route="blocked",
                fallback_count=1,
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "phase2_metrics_report.py",
            "--stability-input-json",
            str(measured_path),
            "--stability-required-runs",
            "2",
            "--stability-probe-env",
            "bad-entry",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        phase2_metrics_report.main()
    assert "--stability-probe-env expects KEY=VALUE" in str(exc.value)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "phase2_metrics_report.py",
            "--stability-input-json",
            str(measured_path),
            "--stability-required-runs",
            "2",
            "--require-fused-turboquant",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        phase2_metrics_report.main()
    message = str(exc.value)
    assert "measured_run_count=1<required:2" in message
    assert "pass_count=0/1" in message
    assert "all_non_fallback=False" in message
    assert "run_1_gate=fail" in message


def test_turboquant_stability_helper_edges(tmp_path: Path) -> None:
    report = _turboquant_stability_report(worker_overhead=8.0)

    assert phase2_metrics_report.stability_measurement_protocol(1, 5).startswith("one warmup run")
    assert phase2_metrics_report.stability_model_label({"model_id": "custom-model", "model_path": ""}) == (
        "custom-model"
    )
    assert phase2_metrics_report.common_parent([]) is None
    assert phase2_metrics_report.common_parent([Path("/tmp/a.json"), Path("relative.json")]) is None
    assert phase2_metrics_report.inferred_gate_log_path(tmp_path / "missing.json") is None
    assert phase2_metrics_report.numeric_summary([], "missing") is None

    with pytest.raises(ValueError) as exc:
        phase2_metrics_report.build_turboquant_stability_summary(
            reports=[report],
            input_paths=[],
            warmup_count=0,
            required_runs=1,
        )
    assert "same length" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        phase2_metrics_report.build_turboquant_stability_summary(
            reports=[report],
            input_paths=[tmp_path / "warmup.json"],
            warmup_count=1,
            required_runs=1,
        )
    assert "at least one measured run" in str(exc.value)

    with pytest.raises(RuntimeError) as exc:
        phase2_metrics_report.turboquant_stability_run_entry(
            report={},
            input_path=tmp_path / "missing-direct.json",
            run_number=1,
        )
    assert "swift_worker_direct" in str(exc.value)

    with pytest.raises(RuntimeError) as exc:
        phase2_metrics_report.turboquant_stability_run_entry(
            report={"swift_worker_direct": {"active_kv_release_gates": []}},
            input_path=tmp_path / "missing-gate.json",
            run_number=1,
        )
    assert "turboquant_fused_decode" in str(exc.value)


def test_load_report_json_rejects_non_object(tmp_path: Path) -> None:
    input_path = tmp_path / "postopt.json"
    input_path.write_text("[]", encoding="utf-8")

    try:
        phase2_metrics_report.load_report_json(input_path)
    except RuntimeError as exc:
        assert "must be a JSON object" in str(exc)
    else:
        raise AssertionError("expected non-object input report to fail")


def _turboquant_stability_report(
    *,
    worker_overhead: float,
    wall_overhead: float = 9.0,
    kernel_path: str = "tq_mse_single",
    route: str = "routed",
    fallback_count: int = 0,
    softmax_token_lanes: int = 64,
) -> dict[str, object]:
    return {
        "runtime_dir": "/tmp/runtime",
        "model_id": "melix-dev-text",
        "model_path": "/models/mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
        "swift_worker_direct": {
            "decode": [
                {
                    "label": "decode_turboquant_q4",
                    "active_kv_kernel_path": kernel_path,
                    "active_kv_runtime_route": route,
                    "active_kv_runtime_block_reason": "attention_hook_unavailable" if route == "blocked" else None,
                    "active_kv_fallback_count": fallback_count,
                    "active_kv_decode_quantize_total_us": 0,
                    "active_kv_estimated_memory_savings_pct": 75,
                    "active_kv_decode_model_call_count": 1,
                    "active_kv_decode_token_eval_total_us": 2,
                    "active_kv_decode_model_eval_sync_total_us": 3,
                    "active_kv_decode_model_eval_sync_call_count": 1,
                    "active_kv_fused_attention_total_us": 4,
                    "active_kv_fused_attention_call_count": 5,
                    "active_kv_fused_attention_route_total_us": 4,
                    "active_kv_decode_loop_total_us": 6,
                    "active_kv_cache_update_total_us": 7,
                    "active_kv_cache_update_call_count": 1,
                    "active_kv_cache_expand_total_us": 8,
                    "active_kv_cache_quantize_total_us": 9,
                    "active_kv_cache_append_total_us": 10,
                    "active_kv_cache_materialize_total_us": 11,
                    "active_kv_cache_materialize_call_count": 1,
                    "active_kv_fused_attention_active_lane_total": 32,
                    "active_kv_fused_attention_launched_lane_total": 32,
                    "active_kv_fused_attention_inactive_lane_total": 0,
                    "active_kv_fused_attention_softmax_lane_total": 1,
                    "active_kv_fused_attention_softmax_token_lane_total": softmax_token_lanes,
                }
            ],
            "comparisons": {
                "turboquant_q4_vs_baseline": {
                    "worker_tps_overhead_pct": worker_overhead,
                    "wall_tps_overhead_pct": wall_overhead,
                    "active_worker_decode_tokens_per_second": 36.0,
                    "baseline_worker_decode_tokens_per_second": 40.0,
                }
            },
        },
    }


def test_emit_report_writes_json_output(tmp_path: Path) -> None:
    output_path = tmp_path / "metrics" / "phase2-affine-q4-preopt.json"
    report = {
        "runtime_dir": "/tmp/melix",
        "swift_backend_mode": "swift",
        "python_backend_mode": "auto",
        "model_id": "melix-dev-text",
        "model_path": "/models/qwen-real-small",
        "model_revision": "main",
        "http_baseline": {},
        "queue_pressure": {},
        "swift_worker_direct": {"decode": [], "prefill": [], "comparisons": {}, "abort": {}},
        "control_plane_metrics": {},
        "swift_worker_metrics": {},
    }

    rendered = phase2_metrics_report.emit_report(
        report,
        json_output=True,
        output_path=output_path,
    )

    assert json.loads(rendered)["model_revision"] == "main"
    assert json.loads(output_path.read_text(encoding="utf-8"))["model_path"] == "/models/qwen-real-small"


def test_render_report_includes_sparse_prefill_columns() -> None:
    report = {
        "runtime_dir": "/tmp/melix",
        "swift_backend_mode": "deterministic",
        "python_backend_mode": "deterministic",
        "http_baseline": {"label": "http_baseline", "ttft_ms": 1.0, "total_ms": 2.0, "tokens_per_second": 3.0, "completion_tokens": 4, "finish_reason": "stop"},
        "queue_pressure": {
            "leader": {"label": "queue_leader", "ttft_ms": 1.0, "total_ms": 2.0, "tokens_per_second": 3.0, "completion_tokens": 4, "finish_reason": "stop"},
            "follower": {"label": "queue_follower", "ttft_ms": 2.0, "total_ms": 3.0, "tokens_per_second": 4.0, "completion_tokens": 5, "finish_reason": "stop"},
            "scheduler": {"admission_latency_ms": 1.0, "queue_delay_ms": 2.0, "queued_requests": 1, "active_requests": 1, "active_lane_depth": 1, "backpressure": 0.0},
        },
        "swift_worker_direct": {
            "prefill": [
                {
                    "label": "prefill_sparse",
                    "mode": "ACCELERATION_MODE_SPARSE_PREFILL",
                    "total_ms": 20.0,
                    "worker_prefill_ms": 18.0,
                    "prompt_tokens": 12,
                    "accelerated_prefill_gain_pct": 30.0,
                    "active_kv_quantization_ratio": 0.0,
                    "sparse_prefill_accepted_skip_count": 3,
                    "sparse_prefill_rejected_opportunity_count": 1,
                    "sparse_prefill_protected_region_count": 2,
                }
            ],
            "decode": [
                {
                    "label": "decode_affine_q4",
                    "mode": "ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
                    "ttft_ms": 5.0,
                    "total_ms": 10.0,
                    "tokens_per_second": 12.0,
                    "worker_decode_tokens_per_second": 12.0,
                    "speculative_acceptance_rate": 0.0,
                    "speculative_rollback_rate": 0.0,
                    "active_kv_quantization_ratio": 25.0,
                    "active_kv_backend": "affine",
                    "active_kv_kernel_path": "affine_quantized_sdpa",
                    "active_kv_decode_model_avg_us": 300,
                    "active_kv_decode_token_eval_avg_us": 650,
                    "active_kv_decode_model_eval_sync_avg_us": 500,
                    "active_kv_fused_attention_avg_us": 250,
                    "active_kv_fused_attention_route_avg_us": 300,
                    "active_kv_decode_loop_total_us": 2_100,
                    "active_kv_decode_quantize_avg_us": 40,
                    "active_kv_estimated_memory_savings_pct": 75,
                },
                {
                    "label": "decode_turboquant_q4",
                    "mode": "ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
                    "ttft_ms": 5.0,
                    "total_ms": 10.0,
                    "tokens_per_second": 12.0,
                    "worker_decode_tokens_per_second": 12.0,
                    "speculative_acceptance_rate": 0.0,
                    "speculative_rollback_rate": 0.0,
                    "active_kv_quantization_ratio": 25.0,
                    "active_kv_backend": "turboquant",
                    "active_kv_kernel_path": "fallback",
                    "active_kv_runtime_route": "blocked",
                    "active_kv_runtime_block_reason": "attention_hook_unavailable",
                    "active_kv_decode_model_avg_us": 300,
                    "active_kv_decode_token_eval_avg_us": 650,
                    "active_kv_decode_model_eval_sync_avg_us": 500,
                    "active_kv_fused_attention_avg_us": 250,
                    "active_kv_fused_attention_route_avg_us": 300,
                    "active_kv_decode_loop_total_us": 2_100,
                    "active_kv_decode_quantize_avg_us": 0,
                    "active_kv_estimated_memory_savings_pct": 75,
                }
            ],
            "comparisons": {
                "affine_q4_vs_baseline": {
                    "worker_tps_overhead_pct": 8.0,
                    "active_kv_decode_model_eval_sync_avg_us": 500.0,
                    "active_kv_fused_attention_avg_us": 250.0,
                    "active_kv_fused_attention_route_avg_us": 300.0,
                    "active_kv_estimated_memory_savings_pct": 75.0,
                }
            },
            "abort": {"label": "decode_abort", "abort_ms": 1.0, "finish_reason": "cancelled"},
        },
    }

    rendered = phase2_metrics_report.render_report(report)

    assert "sparse_prefill_accepted_skip_count" in rendered
    assert "sparse_prefill_protected_region_count" in rendered
    assert "active_kv_kernel_path" in rendered
    assert "active_kv_runtime_route" in rendered
    assert "active_kv_decode_token_eval_avg_us" in rendered
    assert "active_kv_decode_model_eval_sync_avg_us" in rendered
    assert "active_kv_fused_attention_avg_us" in rendered
    assert "active_kv_fused_attention_route_avg_us" in rendered
    assert "active_kv_decode_loop_total_us" in rendered
    assert "attention_hook_unavailable" in rendered
    assert "affine_q4_vs_baseline" in rendered
