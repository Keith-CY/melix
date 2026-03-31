from __future__ import annotations

import json
from pathlib import Path

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


class _FakeRuntimeStub:
    def LoadModel(self, request, timeout: int = 120):  # noqa: ANN001
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
    )

    assert prefill_labels == ["prefill_baseline", "prefill_accelerated", "prefill_sparse"]
    assert [entry["label"] for entry in result["swift_worker_direct"]["prefill"]] == prefill_labels


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
                    "label": "decode_active_kv_quantized",
                    "mode": "ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
                    "ttft_ms": 5.0,
                    "total_ms": 10.0,
                    "tokens_per_second": 12.0,
                    "worker_decode_tokens_per_second": 12.0,
                    "speculative_acceptance_rate": 0.0,
                    "speculative_rollback_rate": 0.0,
                    "active_kv_quantization_ratio": 25.0,
                }
            ],
            "abort": {"label": "decode_abort", "abort_ms": 1.0, "finish_reason": "cancelled"},
        },
    }

    rendered = phase2_metrics_report.render_report(report)

    assert "sparse_prefill_accepted_skip_count" in rendered
    assert "sparse_prefill_protected_region_count" in rendered
