from __future__ import annotations

import json
from pathlib import Path

from packages.protocol.python.worker.v1 import common_pb2, runtime_pb2

from worker.grpc_server import WorkerRuntimeService
from worker.model_load_trust import resolve_model_load_trust_policy
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime.mlx_text_runtime import MLXTextRuntime


class RecordingTextBackend:
    runtime_name = "mlx-lm"

    def __init__(self) -> None:
        self.load_calls: list[bool] = []

    def load_model(self, model_spec, *, trust_remote_code: bool = False):
        self.load_calls.append(trust_remote_code)
        return {"model_id": model_spec.model_id, "trust_remote_code": trust_remote_code}

    def estimate_resident_bytes(self, model_spec) -> int:
        _ = model_spec
        return 4096


def test_worker_rejects_custom_loader_metadata_without_explicit_trust(tmp_path: Path) -> None:
    backend = RecordingTextBackend()
    service = WorkerRuntimeService(
        WorkerRegistry(
            runtime=MLXTextRuntime(backend=backend),
            model_catalog=WorkerModelCatalog(),
        )
    )

    response = service.LoadModel(
        runtime_pb2.LoadModelRequest(model=_custom_loader_text_model(tmp_path)),
        context=None,
    )
    stats = service.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), context=None).stats

    assert response.ok is False
    assert response.error.code == "unsafe_load_rejected"
    assert response.error.details["block_reason"] == "custom_loader_requires_trust_remote_code"
    assert response.load_trust.requested_mode == common_pb2.MODEL_LOAD_TRUST_DEFAULT_SAFE
    assert response.load_trust.effective_mode == common_pb2.MODEL_LOAD_TRUST_DEFAULT_SAFE
    assert response.load_trust.custom_loader_required is True
    assert response.load_trust.custom_loader_detection_source == "config_json:auto_map"
    assert response.load_trust.block_reason == "custom_loader_requires_trust_remote_code"
    assert stats.model_load_trust_blocked_count == 1
    assert stats.last_model_load_trust_policy_resolution_ms >= 0.0
    assert backend.load_calls == []


def test_worker_trusted_custom_loader_receipt_passes_trust_remote_code(tmp_path: Path) -> None:
    backend = RecordingTextBackend()
    service = WorkerRuntimeService(
        WorkerRegistry(
            runtime=MLXTextRuntime(backend=backend),
            model_catalog=WorkerModelCatalog(),
        )
    )
    load_trust = common_pb2.ModelLoadTrustPolicy(
        requested_mode=common_pb2.MODEL_LOAD_TRUST_TRUST_REMOTE_CODE,
        policy_source="model_settings",
        route_class=common_pb2.WORKER_ROUTE_PYTHON_TEXT_COMPATIBILITY,
        loader_family="mlx-lm",
    )

    response = service.LoadModel(
        runtime_pb2.LoadModelRequest(
            model=_custom_loader_text_model(tmp_path),
            load_trust=load_trust,
        ),
        context=None,
    )
    stats = service.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), context=None).stats

    assert response.ok is True
    assert response.load_trust.requested_mode == common_pb2.MODEL_LOAD_TRUST_TRUST_REMOTE_CODE
    assert response.load_trust.effective_mode == common_pb2.MODEL_LOAD_TRUST_TRUST_REMOTE_CODE
    assert response.load_trust.policy_source == "model_settings"
    assert response.load_trust.custom_loader_required is True
    assert response.load_trust.custom_loader_detection_source == "config_json:auto_map"
    assert response.load_trust.block_reason == ""
    assert backend.load_calls == [True]
    assert stats.model_load_trust_blocked_count == 0


def test_worker_reports_not_applicable_receipt_for_non_custom_loader_runtime() -> None:
    service = WorkerRuntimeService(WorkerRegistry(model_catalog=WorkerModelCatalog()))

    response = service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_embedding_model()),
        context=None,
    )

    assert response.ok is True
    assert response.load_trust.requested_mode == common_pb2.MODEL_LOAD_TRUST_DEFAULT_SAFE
    assert response.load_trust.effective_mode == common_pb2.MODEL_LOAD_TRUST_NOT_APPLICABLE
    assert response.load_trust.policy_source == "not_applicable"
    assert response.load_trust.custom_loader_detection_source == "not_applicable"
    assert response.load_trust.custom_loader_required is False


def test_trust_policy_treats_non_mlx_text_loader_as_not_applicable(tmp_path: Path) -> None:
    model = _custom_loader_text_model(tmp_path)

    policy = resolve_model_load_trust_policy(
        model,
        request_policy=None,
        runtime_kind="text",
        runtime=FakeTextRuntime(),
    )

    assert policy.requested_mode == common_pb2.MODEL_LOAD_TRUST_DEFAULT_SAFE
    assert policy.effective_mode == common_pb2.MODEL_LOAD_TRUST_NOT_APPLICABLE
    assert policy.policy_source == "not_applicable"
    assert policy.loader_family == "fake-mlx"
    assert policy.custom_loader_detection_source == "not_applicable"
    assert policy.custom_loader_required is False


def test_trust_policy_treats_missing_runtime_as_not_applicable(tmp_path: Path) -> None:
    model = _custom_loader_vlm_model(tmp_path)

    policy = resolve_model_load_trust_policy(
        model,
        request_policy=None,
        runtime_kind="vlm",
        runtime=None,
    )

    assert policy.requested_mode == common_pb2.MODEL_LOAD_TRUST_DEFAULT_SAFE
    assert policy.effective_mode == common_pb2.MODEL_LOAD_TRUST_NOT_APPLICABLE
    assert policy.policy_source == "not_applicable"
    assert policy.loader_family == "mlx_vlm"
    assert policy.custom_loader_detection_source == "not_applicable"
    assert policy.custom_loader_required is False


def _custom_loader_text_model(tmp_path: Path) -> common_pb2.ModelSpec:
    model_dir = tmp_path / "custom-loader-model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text(
        json.dumps({"auto_map": {"AutoModelForCausalLM": "custom.Loader"}}),
        encoding="utf-8",
    )
    model = WorkerModelCatalog.dev_text_model()
    model.model_path = str(model_dir)
    return model


def _custom_loader_vlm_model(tmp_path: Path) -> common_pb2.ModelSpec:
    model_dir = tmp_path / "custom-loader-vlm"
    model_dir.mkdir()
    (model_dir / "config.json").write_text(
        json.dumps({"auto_map": {"AutoModel": "custom.VisionLoader"}}),
        encoding="utf-8",
    )
    model = WorkerModelCatalog.dev_vlm_model()
    model.model_path = str(model_dir)
    model.ext["melix.vlm.backend_id"] = ""
    return model


class FakeTextRuntime:
    runtime_name = "fake-mlx"
