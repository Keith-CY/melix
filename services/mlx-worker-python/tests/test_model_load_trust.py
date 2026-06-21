from __future__ import annotations

import json
from pathlib import Path

import pytest
import worker.model_load_trust as model_load_trust_module

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


def test_worker_rejects_trusted_custom_loader_when_backend_cannot_honor_trust(tmp_path: Path) -> None:
    service = WorkerRuntimeService(
        WorkerRegistry(
            runtime=MLXTextRuntime(backend=LegacyTrustedBackend()),
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

    assert response.ok is False
    assert response.error.code == "load_failed"
    assert "trust_remote_code" in response.error.message


def test_registry_trust_loader_rejects_runtime_that_cannot_honor_trust() -> None:
    policy = common_pb2.ModelLoadTrustPolicy(
        effective_mode=common_pb2.MODEL_LOAD_TRUST_TRUST_REMOTE_CODE,
    )

    with pytest.raises(RuntimeError, match="trust_remote_code"):
        WorkerRegistry._load_runtime_model(
            NoTrustKwargRuntime(),
            WorkerModelCatalog.dev_text_model(),
            load_trust_policy=policy,
        )


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


def test_worker_skips_latency_metric_for_non_applicable_text_loader(tmp_path: Path) -> None:
    backend = NonApplicableTextBackend()
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

    assert response.ok is True
    assert response.load_trust.effective_mode == common_pb2.MODEL_LOAD_TRUST_NOT_APPLICABLE
    assert response.load_trust.policy_source == "not_applicable"
    assert stats.last_model_load_trust_policy_resolution_ms == 0.0
    assert backend.load_calls == [False]


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


def test_trust_policy_uses_explicit_runtime_support_contract(tmp_path: Path) -> None:
    model = _custom_loader_vlm_model(tmp_path)
    trusted_request = common_pb2.ModelLoadTrustPolicy(
        requested_mode=common_pb2.MODEL_LOAD_TRUST_TRUST_REMOTE_CODE,
    )

    supported = resolve_model_load_trust_policy(
        model,
        request_policy=trusted_request,
        runtime_kind="vlm",
        runtime=ExplicitTrustRuntime(True),
    )
    unsupported = resolve_model_load_trust_policy(
        model,
        request_policy=None,
        runtime_kind="vlm",
        runtime=ExplicitTrustRuntime(False),
    )

    assert supported.effective_mode == common_pb2.MODEL_LOAD_TRUST_TRUST_REMOTE_CODE
    assert unsupported.effective_mode == common_pb2.MODEL_LOAD_TRUST_NOT_APPLICABLE


def test_trust_policy_falls_back_to_vlm_loader_family_without_runtime_contract(tmp_path: Path) -> None:
    trusted_request = common_pb2.ModelLoadTrustPolicy(
        requested_mode=common_pb2.MODEL_LOAD_TRUST_TRUST_REMOTE_CODE,
        loader_family="mlx-vlm",
    )

    policy = resolve_model_load_trust_policy(
        _custom_loader_vlm_model(tmp_path),
        request_policy=trusted_request,
        runtime_kind="vlm",
        runtime=NamedRuntime("wrapped-vlm"),
    )

    assert policy.effective_mode == common_pb2.MODEL_LOAD_TRUST_TRUST_REMOTE_CODE
    assert policy.loader_family == "mlx-vlm"


def test_trust_policy_reads_config_json_bytes_without_text_decode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _custom_loader_text_model(tmp_path)
    read_bytes_calls = 0
    original_read_bytes = model_load_trust_module.Path.read_bytes

    def counted_read_bytes(path: Path) -> bytes:
        nonlocal read_bytes_calls
        read_bytes_calls += 1
        return original_read_bytes(path)

    def fail_read_text(
        path: Path, *args, **kwargs
    ) -> str:  # pragma: no cover - only runs on regression.
        _ = path, args, kwargs
        raise AssertionError("config.json should be parsed from bytes")

    monkeypatch.setattr(model_load_trust_module.Path, "read_bytes", counted_read_bytes)
    monkeypatch.setattr(model_load_trust_module.Path, "read_text", fail_read_text)

    with pytest.raises(model_load_trust_module.ModelLoadTrustRejection) as exc_info:
        resolve_model_load_trust_policy(
            model,
            request_policy=None,
            runtime_kind="text",
            runtime=RecordingTextBackend(),
        )

    assert read_bytes_calls == 1
    assert exc_info.value.policy.custom_loader_required is True
    assert exc_info.value.policy.custom_loader_detection_source == "config_json:auto_map"


def test_trust_policy_caches_config_json_by_file_stat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_load_trust_module._read_model_config_for_stat.cache_clear()
    model = _custom_loader_text_model(tmp_path)
    read_bytes_calls = 0
    original_read_bytes = model_load_trust_module.Path.read_bytes

    def counted_read_bytes(path: Path) -> bytes:
        nonlocal read_bytes_calls
        read_bytes_calls += 1
        return original_read_bytes(path)

    monkeypatch.setattr(model_load_trust_module.Path, "read_bytes", counted_read_bytes)

    for _ in range(2):
        with pytest.raises(model_load_trust_module.ModelLoadTrustRejection) as exc_info:
            resolve_model_load_trust_policy(
                model,
                request_policy=None,
                runtime_kind="text",
                runtime=RecordingTextBackend(),
            )
        assert exc_info.value.policy.custom_loader_required is True
        assert exc_info.value.policy.custom_loader_detection_source == "config_json:auto_map"

    assert read_bytes_calls == 1


def test_trust_policy_auto_map_custom_loader_scan_avoids_string_coercion_for_strings() -> None:
    class NoisyString(str):
        def __str__(self) -> str:  # pragma: no cover - only runs on regression.
            raise AssertionError("string auto_map values should not be coerced through str()")

    assert model_load_trust_module._auto_map_has_custom_loader({"AutoModel": NoisyString("custom.Loader")}) is True


def test_trust_policy_auto_map_custom_loader_scan_preserves_blank_string_behavior() -> None:
    assert model_load_trust_module._auto_map_has_custom_loader({"AutoModel": " \t\n"}) is False
    assert model_load_trust_module._auto_map_has_custom_loader({"AutoModel": "custom.Loader"}) is True


def test_trust_policy_auto_map_custom_loader_scan_preserves_non_string_fallback() -> None:
    assert model_load_trust_module._auto_map_has_custom_loader({"AutoModel": None}) is False
    assert model_load_trust_module._auto_map_has_custom_loader({"AutoModel": 0}) is True
    assert model_load_trust_module._auto_map_has_custom_loader({"AutoModel": object()}) is True


def test_trust_policy_skips_expanduser_for_plain_model_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _custom_loader_text_model(tmp_path)

    def fail_expanduser(path: Path) -> Path:  # pragma: no cover - only runs on regression.
        raise AssertionError(f"plain model path should not call expanduser(): {path}")

    monkeypatch.setattr(model_load_trust_module.Path, "expanduser", fail_expanduser)

    with pytest.raises(model_load_trust_module.ModelLoadTrustRejection) as exc_info:
        resolve_model_load_trust_policy(
            model,
            request_policy=None,
            runtime_kind="text",
            runtime=RecordingTextBackend(),
        )

    assert exc_info.value.policy.custom_loader_required is True
    assert exc_info.value.policy.custom_loader_detection_source == "config_json:auto_map"


def test_trust_policy_stats_plain_config_path_without_path_join(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _custom_loader_text_model(tmp_path)

    def fail_path_join(path: Path, key: str) -> Path:  # pragma: no cover - only runs on regression.
        raise AssertionError(f"plain model path should not use Path join for {key}: {path}")

    monkeypatch.setattr(model_load_trust_module.Path, "__truediv__", fail_path_join)

    with pytest.raises(model_load_trust_module.ModelLoadTrustRejection) as exc_info:
        resolve_model_load_trust_policy(
            model,
            request_policy=None,
            runtime_kind="text",
            runtime=RecordingTextBackend(),
        )

    assert exc_info.value.policy.custom_loader_required is True
    assert exc_info.value.policy.custom_loader_detection_source == "config_json:auto_map"


def test_trust_policy_expands_tilde_model_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    model_dir = tmp_path / "tilde-custom-loader-model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text(
        json.dumps({"auto_map": {"AutoModelForCausalLM": "custom.Loader"}}),
        encoding="utf-8",
    )
    model = WorkerModelCatalog.dev_text_model()
    model.model_path = "~/tilde-custom-loader-model"

    with pytest.raises(model_load_trust_module.ModelLoadTrustRejection) as exc_info:
        resolve_model_load_trust_policy(
            model,
            request_policy=None,
            runtime_kind="text",
            runtime=RecordingTextBackend(),
        )

    assert exc_info.value.policy.custom_loader_required is True
    assert exc_info.value.policy.custom_loader_detection_source == "config_json:auto_map"


def test_trust_policy_treats_missing_config_json_as_absent(tmp_path: Path) -> None:
    model_dir = tmp_path / "plain-model"
    model_dir.mkdir()
    model = WorkerModelCatalog.dev_text_model()
    model.model_path = str(model_dir)

    policy = resolve_model_load_trust_policy(
        model,
        request_policy=None,
        runtime_kind="text",
        runtime=RecordingTextBackend(),
    )

    assert policy.custom_loader_required is False
    assert policy.custom_loader_detection_source == "config_json:absent"


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


class NonApplicableTextBackend(RecordingTextBackend):
    runtime_name = "fake-mlx"


class LegacyTrustedBackend:
    runtime_name = "mlx-lm"

    def load_model(self, model_spec):  # pragma: no cover - must be blocked before invocation.
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec) -> int:
        _ = model_spec
        return 4096


class ExplicitTrustRuntime:
    runtime_name = "wrapped-vlm"

    def __init__(self, supports_trust_policy: bool) -> None:
        self.supports_trust_policy = supports_trust_policy


class NoTrustKwargRuntime:
    def load_model(self, model_spec):  # pragma: no cover - must be blocked before invocation.
        return {"model_id": model_spec.model_id}


class NamedRuntime:
    def __init__(self, runtime_name: str) -> None:
        self.runtime_name = runtime_name
