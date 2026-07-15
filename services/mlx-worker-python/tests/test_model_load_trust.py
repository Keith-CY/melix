from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

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


def test_trust_policy_non_empty_source_fast_path_preserves_blank_fallback() -> None:
    assert model_load_trust_module._non_empty("request", "fallback") == "request"
    assert model_load_trust_module._non_empty("", "fallback") == "fallback"
    assert model_load_trust_module._non_empty(" \t\n", "fallback") == "fallback"


def test_requested_mode_reuses_valid_mode_membership_for_sources() -> None:
    assert model_load_trust_module._non_empty(" request", "fallback") == " request"
    model = WorkerModelCatalog.dev_text_model()
    assert model_load_trust_module._requested_mode(model, None) == (
        common_pb2.MODEL_LOAD_TRUST_DEFAULT_SAFE,
        "default_safe",
    )

    model.settings.load_trust_mode = common_pb2.MODEL_LOAD_TRUST_TRUST_REMOTE_CODE
    assert model_load_trust_module._requested_mode(model, None) == (
        common_pb2.MODEL_LOAD_TRUST_TRUST_REMOTE_CODE,
        "model_settings",
    )

    request_policy = common_pb2.ModelLoadTrustPolicy(
        requested_mode=common_pb2.MODEL_LOAD_TRUST_DEFAULT_SAFE,
    )
    assert model_load_trust_module._requested_mode(model, request_policy) == (
        common_pb2.MODEL_LOAD_TRUST_DEFAULT_SAFE,
        "request",
    )


def test_worker_rejects_custom_loader_metadata_without_explicit_trust(tmp_path: Path) -> None:
    backend = RecordingTextBackend()
    service = WorkerRuntimeService(
        WorkerRegistry(
            runtime=MLXTextRuntime(backend=backend),
            model_catalog=WorkerModelCatalog(),
        )
    )
    model = _custom_loader_text_model(tmp_path)
    (Path(model.model_path) / "modeling_melix_demo.py").write_text(
        "class MelixDemoModel: pass\n",
        encoding="utf-8",
    )

    response = service.LoadModel(
        runtime_pb2.LoadModelRequest(model=model),
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
    assert model_load_trust_module._model_files_detection_source(
        ("configuration_melix_demo.py",)
    ) == "model_files:configuration_melix_demo.py"

    executable_response = service.LoadModel(
        runtime_pb2.LoadModelRequest(model=_executable_file_text_model(tmp_path)),
        context=None,
    )
    assert executable_response.ok is False
    assert executable_response.error.code == "unsafe_load_rejected"
    assert executable_response.error.details["block_reason"] == "custom_loader_requires_trust_remote_code"
    assert executable_response.load_trust.custom_loader_required is True
    assert executable_response.load_trust.custom_loader_detection_source == "model_files:modeling_melix_demo.py"
    assert executable_response.load_trust.block_reason == "custom_loader_requires_trust_remote_code"
    assert backend.load_calls == []


def test_custom_loader_rejection_policy_uses_isolated_cached_template(tmp_path: Path) -> None:
    model = _custom_loader_text_model(tmp_path)
    runtime = RecordingTextBackend()

    with pytest.raises(model_load_trust_module.ModelLoadTrustRejection) as first:
        resolve_model_load_trust_policy(
            model,
            request_policy=None,
            runtime_kind="text",
            runtime=runtime,
        )
    first.value.policy.policy_source = "mutated"

    with pytest.raises(model_load_trust_module.ModelLoadTrustRejection) as second:
        resolve_model_load_trust_policy(
            model,
            request_policy=None,
            runtime_kind="text",
            runtime=runtime,
        )

    assert second.value.policy is not first.value.policy
    assert second.value.policy.policy_source == "default_safe"
    assert second.value.policy.block_reason == "custom_loader_requires_trust_remote_code"


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
    model = _custom_loader_text_model(tmp_path)
    (Path(model.model_path) / "modeling_melix_demo.py").write_text(
        "class MelixDemoModel: pass\n",
        encoding="utf-8",
    )

    response = service.LoadModel(
        runtime_pb2.LoadModelRequest(
            model=model,
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

    executable_response = service.LoadModel(
        runtime_pb2.LoadModelRequest(
            model=_executable_file_text_model(tmp_path),
            load_trust=load_trust,
        ),
        context=None,
    )
    assert executable_response.ok is True
    assert executable_response.load_trust.requested_mode == common_pb2.MODEL_LOAD_TRUST_TRUST_REMOTE_CODE
    assert executable_response.load_trust.effective_mode == common_pb2.MODEL_LOAD_TRUST_TRUST_REMOTE_CODE
    assert executable_response.load_trust.custom_loader_required is True
    assert executable_response.load_trust.custom_loader_detection_source == "model_files:modeling_melix_demo.py"
    assert executable_response.load_trust.block_reason == ""
    assert backend.load_calls == [True, True]


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


def test_loader_family_text_default_bypasses_request_policy_lookup() -> None:
    model = WorkerModelCatalog.dev_text_model()

    assert (
        model_load_trust_module._loader_family(
            model,
            None,
            "text",
            runtime_name="mlx-lm",
        )
        == "mlx-lm"
    )
    assert (
        model_load_trust_module._loader_family(
            model,
            None,
            "text",
            runtime_name="",
        )
        == "mlx-lm"
    )
    assert (
        model_load_trust_module._loader_family(
            model,
            common_pb2.ModelLoadTrustPolicy(loader_family=" custom-loader "),
            "text",
            runtime_name="mlx-lm",
        )
        == "custom-loader"
    )


def test_trust_policy_common_loader_fast_path_skips_normalized_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(model_load_trust_module, "TRUST_APPLICABLE_TEXT_LOADERS", frozenset())
    monkeypatch.setattr(model_load_trust_module, "TRUST_APPLICABLE_VLM_LOADERS", frozenset())

    assert model_load_trust_module._is_trust_applicable(
        "text",
        "mlx-lm",
        "mlx-lm",
        RecordingTextBackend(),
    ) is True
    assert model_load_trust_module._is_trust_applicable(
        "text",
        "wrapped-text",
        "mlx-lm",
        RecordingTextBackend(),
    ) is True
    assert model_load_trust_module._is_trust_applicable(
        "vlm",
        "custom-vlm",
        "deterministic-vlm",
        NamedRuntime("deterministic-vlm"),
    ) is False
    assert model_load_trust_module._is_trust_applicable(
        "vlm",
        "mlx-vlm",
        "wrapped-vlm",
        NamedRuntime("wrapped-vlm"),
    ) is True


def test_trust_policy_reads_config_json_bytes_with_direct_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_load_trust_module._read_model_config_for_stat.cache_clear()
    model_load_trust_module._detect_custom_loader_requirement_for_stat.cache_clear()
    model = _custom_loader_text_model(tmp_path)
    open_calls = 0
    original_open = open

    def counted_open(*args, **kwargs):
        nonlocal open_calls
        open_calls += 1
        return original_open(*args, **kwargs)

    def fail_read_text(
        path: Path, *args, **kwargs
    ) -> str:  # pragma: no cover - only runs on regression.
        _ = path, args, kwargs
        raise AssertionError("config.json should be parsed from bytes")

    def fail_read_bytes(path: Path) -> bytes:  # pragma: no cover - only runs on regression.
        raise AssertionError(f"config.json should use direct open(), not Path.read_bytes(): {path}")

    monkeypatch.setattr(model_load_trust_module, "_OPEN", counted_open)
    monkeypatch.setattr(
        model_load_trust_module,
        "open",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("config.json should use the module-local open binding")
        ),
        raising=False,
    )
    monkeypatch.setattr(model_load_trust_module.Path, "read_bytes", fail_read_bytes)
    monkeypatch.setattr(model_load_trust_module.Path, "read_text", fail_read_text)

    with pytest.raises(model_load_trust_module.ModelLoadTrustRejection) as exc_info:
        resolve_model_load_trust_policy(
            model,
            request_policy=None,
            runtime_kind="text",
            runtime=RecordingTextBackend(),
        )

    assert open_calls == 1
    assert exc_info.value.policy.custom_loader_required is True
    assert exc_info.value.policy.custom_loader_detection_source == "config_json:auto_map"


def test_trust_policy_reads_config_json_with_bound_json_loads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_load_trust_module._read_model_config_for_stat.cache_clear()
    model_load_trust_module._detect_custom_loader_requirement_for_stat.cache_clear()
    model = _custom_loader_text_model(tmp_path)
    loads_calls = 0
    original_loads = json.loads

    def counted_loads(payload: bytes) -> object:
        nonlocal loads_calls
        loads_calls += 1
        return original_loads(payload)

    monkeypatch.setattr(model_load_trust_module, "_JSON_LOADS", counted_loads)
    monkeypatch.setattr(
        model_load_trust_module.json,
        "loads",
        lambda payload: (_ for _ in ()).throw(
            AssertionError("config.json should use the module-local JSON loads binding")
        ),
    )

    with pytest.raises(model_load_trust_module.ModelLoadTrustRejection) as exc_info:
        resolve_model_load_trust_policy(
            model,
            request_policy=None,
            runtime_kind="text",
            runtime=RecordingTextBackend(),
        )

    assert loads_calls == 1
    assert exc_info.value.policy.custom_loader_required is True
    assert exc_info.value.policy.custom_loader_detection_source == "config_json:auto_map"


def test_trust_policy_caches_config_json_by_file_stat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_load_trust_module._read_model_config_for_stat.cache_clear()
    model_load_trust_module._detect_custom_loader_requirement_for_stat.cache_clear()
    model = _custom_loader_text_model(tmp_path)
    open_calls = 0
    original_open = open

    def counted_open(*args, **kwargs):
        nonlocal open_calls
        open_calls += 1
        return original_open(*args, **kwargs)

    monkeypatch.setattr(model_load_trust_module, "_OPEN", counted_open)

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

    assert open_calls == 1


def test_trust_policy_caches_auto_map_detection_by_file_stat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_load_trust_module._read_model_config_for_stat.cache_clear()
    model_load_trust_module._detect_custom_loader_requirement_for_stat.cache_clear()
    model = _custom_loader_text_model(tmp_path)
    scan_calls = 0
    original_scan = model_load_trust_module._auto_map_has_custom_loader

    def counted_scan(auto_map: dict[object, object]) -> bool:
        nonlocal scan_calls
        scan_calls += 1
        return original_scan(auto_map)

    monkeypatch.setattr(model_load_trust_module, "_auto_map_has_custom_loader", counted_scan)

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

    assert scan_calls == 1


def test_trust_policy_auto_map_custom_loader_scan_avoids_string_coercion_for_strings() -> None:
    class NoisyString(str):
        def __str__(self) -> str:  # pragma: no cover - only runs on regression.
            raise AssertionError("string auto_map values should not be coerced through str()")

    assert model_load_trust_module._auto_map_has_custom_loader({"AutoModel": NoisyString("custom.Loader")}) is True


def test_trust_policy_auto_map_common_string_uses_leading_character_fast_path() -> None:
    class NoisyIsSpaceString(str):
        def isspace(self) -> bool:  # pragma: no cover - only runs on regression.
            raise AssertionError("non-blank auto_map values should not call isspace()")

    assert model_load_trust_module._auto_map_has_custom_loader({"AutoModel": NoisyIsSpaceString("custom.Loader")}) is True


def test_trust_policy_auto_map_custom_loader_scan_preserves_blank_string_behavior() -> None:
    assert model_load_trust_module._auto_map_has_custom_loader({"AutoModel": ""}) is False
    assert model_load_trust_module._auto_map_has_custom_loader({"AutoModel": " \t\n"}) is False
    assert model_load_trust_module._auto_map_has_custom_loader({"AutoModel": "custom.Loader"}) is True


def test_trust_policy_auto_map_custom_loader_scan_preserves_non_string_fallback() -> None:
    assert model_load_trust_module._auto_map_has_custom_loader({"AutoModel": None}) is False
    assert model_load_trust_module._auto_map_has_custom_loader({"AutoModel": 0}) is True
    assert model_load_trust_module._auto_map_has_custom_loader({"AutoModel": object()}) is True


def test_route_class_runtime_kind_map_preserves_supported_defaults() -> None:
    model = WorkerModelCatalog.dev_text_model()

    expected_routes = {
        "text": common_pb2.WORKER_ROUTE_PYTHON_TEXT_COMPATIBILITY,
        "vlm": common_pb2.WORKER_ROUTE_PYTHON_VLM,
        "ocr": common_pb2.WORKER_ROUTE_PYTHON_OCR,
        "embedding": common_pb2.WORKER_ROUTE_PYTHON_EMBEDDING,
        "rerank": common_pb2.WORKER_ROUTE_PYTHON_RERANK,
        "transcription": common_pb2.WORKER_ROUTE_PYTHON_TRANSCRIPTION,
        "speech": common_pb2.WORKER_ROUTE_PYTHON_SPEECH,
        "image": common_pb2.WORKER_ROUTE_PYTHON_IMAGE,
    }

    for runtime_kind, route_class in expected_routes.items():
        assert model_load_trust_module._route_class(model, None, runtime_kind) == route_class
    assert model_load_trust_module._route_class(model, None, "unknown") == common_pb2.WORKER_ROUTE_CLASS_UNSPECIFIED


def test_route_class_text_default_skips_runtime_kind_map(monkeypatch: pytest.MonkeyPatch) -> None:
    model = WorkerModelCatalog.dev_text_model()

    class FailingRouteMap:
        def get(self, runtime_kind: str, fallback: int) -> int:  # pragma: no cover - regression guard
            raise AssertionError(f"text route default should not query route map: {runtime_kind}")

    monkeypatch.setattr(model_load_trust_module, "ROUTE_CLASS_BY_RUNTIME_KIND", FailingRouteMap())

    assert (
        model_load_trust_module._route_class(model, None, "text")
        == common_pb2.WORKER_ROUTE_PYTHON_TEXT_COMPATIBILITY
    )


def test_trust_policy_default_source_skips_non_empty_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_dir = tmp_path / "plain-model"
    model_dir.mkdir()
    model = WorkerModelCatalog.dev_text_model()
    model.model_path = str(model_dir)

    def fail_non_empty(value: str, fallback: str) -> str:  # pragma: no cover - regression guard
        raise AssertionError(
            f"default policy source should bypass _non_empty({value!r}, {fallback!r})"
        )

    monkeypatch.setattr(model_load_trust_module, "_non_empty", fail_non_empty)

    policy = resolve_model_load_trust_policy(
        model,
        request_policy=None,
        runtime_kind="text",
        runtime=RecordingTextBackend(),
    )

    assert policy.policy_source == "default_safe"


def test_runtime_name_string_fast_path_preserves_exact_value() -> None:
    runtime = NamedRuntime("mlx-lm")

    assert model_load_trust_module._runtime_name(runtime) is runtime.runtime_name
    assert model_load_trust_module._runtime_name(None) == ""
    assert model_load_trust_module._runtime_name(type("Runtime", (), {"runtime_name": 0})()) == ""
    assert model_load_trust_module._runtime_name(type("Runtime", (), {"runtime_name": 42})()) == "42"


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


def test_trust_policy_caches_config_path_text_by_model_path(tmp_path: Path) -> None:
    model = _custom_loader_text_model(tmp_path)
    path_cache = model_load_trust_module._model_config_path_for_model_path
    path_cache.cache_clear()

    first_path = model_load_trust_module._model_config_path(model)
    second_path = model_load_trust_module._model_config_path(model)

    assert first_path == second_path
    assert path_cache.cache_info().hits == 1


def test_read_model_config_reuses_cached_config_path_text(tmp_path: Path) -> None:
    model = _custom_loader_text_model(tmp_path)
    path_cache = model_load_trust_module._model_config_path_for_model_path
    path_cache.cache_clear()
    model_load_trust_module._read_model_config_for_stat.cache_clear()

    first_config = model_load_trust_module._read_model_config(model)
    second_config = model_load_trust_module._read_model_config(model)

    assert first_config == second_config
    assert first_config is not None
    assert first_config["auto_map"] == {"AutoModelForCausalLM": "custom.Loader"}
    assert path_cache.cache_info().hits == 1


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


def test_trust_policy_auto_map_detection_does_not_scan_model_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _custom_loader_text_model(tmp_path)
    unexpected_model_file_scan = Mock(
        side_effect=AssertionError("auto_map detection should not scan model files")
    )

    monkeypatch.setattr(
        model_load_trust_module,
        "_detect_executable_model_files",
        unexpected_model_file_scan,
    )

    with pytest.raises(model_load_trust_module.ModelLoadTrustRejection) as exc_info:
        resolve_model_load_trust_policy(
            model,
            request_policy=None,
            runtime_kind="text",
            runtime=RecordingTextBackend(),
        )

    assert exc_info.value.policy.custom_loader_required is True
    assert exc_info.value.policy.custom_loader_detection_source == "config_json:auto_map"
    unexpected_model_file_scan.assert_not_called()


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

    executable_model_dir = tmp_path / "executable-no-config-model"
    executable_model_dir.mkdir()
    (executable_model_dir / "configuration_melix_demo.py").write_text(
        "class MelixDemoConfig: pass\n",
        encoding="utf-8",
    )
    executable_model = WorkerModelCatalog.dev_text_model()
    executable_model.model_path = str(executable_model_dir)

    with pytest.raises(model_load_trust_module.ModelLoadTrustRejection) as exc_info:
        resolve_model_load_trust_policy(
            executable_model,
            request_policy=None,
            runtime_kind="text",
            runtime=RecordingTextBackend(),
        )

    assert exc_info.value.policy.custom_loader_required is True
    assert exc_info.value.policy.custom_loader_detection_source == "model_files:configuration_melix_demo.py"


def test_trust_policy_single_executable_model_file_skips_sort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable_model_dir = tmp_path / "single-executable-file-model"
    executable_model_dir.mkdir()
    (executable_model_dir / "configuration_melix_demo.py").write_text(
        "class MelixDemoConfig: pass\n",
        encoding="utf-8",
    )
    executable_model = WorkerModelCatalog.dev_text_model()
    executable_model.model_path = str(executable_model_dir)

    def fail_sorted(values):  # pragma: no cover - only runs on regression.
        raise AssertionError(f"single executable file should not sort {values!r}")

    monkeypatch.setattr(model_load_trust_module, "sorted", fail_sorted, raising=False)

    with pytest.raises(model_load_trust_module.ModelLoadTrustRejection) as exc_info:
        resolve_model_load_trust_policy(
            executable_model,
            request_policy=None,
            runtime_kind="text",
            runtime=RecordingTextBackend(),
        )

    assert exc_info.value.policy.custom_loader_required is True
    assert exc_info.value.policy.custom_loader_detection_source == "model_files:configuration_melix_demo.py"


def test_trust_policy_multiple_executable_model_files_stay_sorted(tmp_path: Path) -> None:
    executable_model_dir = tmp_path / "multiple-executable-file-model"
    executable_model_dir.mkdir()
    (executable_model_dir / "modeling_z_demo.py").write_text(
        "class ZModel: pass\n",
        encoding="utf-8",
    )
    (executable_model_dir / "configuration_a_demo.py").write_text(
        "class AConfig: pass\n",
        encoding="utf-8",
    )
    executable_model = WorkerModelCatalog.dev_text_model()
    executable_model.model_path = str(executable_model_dir)

    assert model_load_trust_module._detect_executable_model_files(executable_model) == (
        "configuration_a_demo.py",
        "modeling_z_demo.py",
    )


def test_trust_policy_caches_executable_model_files_by_directory_stat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_load_trust_module._detect_executable_model_files_for_stat.cache_clear()
    executable_model_dir = tmp_path / "cached-executable-file-model"
    executable_model_dir.mkdir()
    (executable_model_dir / "modeling_melix_demo.py").write_text(
        "class MelixDemoModel: pass\n",
        encoding="utf-8",
    )
    executable_model = WorkerModelCatalog.dev_text_model()
    executable_model.model_path = str(executable_model_dir)
    scandir_calls = 0
    original_scandir = model_load_trust_module._OS_SCANDIR

    def counted_scandir(path: str):
        nonlocal scandir_calls
        scandir_calls += 1
        return original_scandir(path)

    monkeypatch.setattr(model_load_trust_module, "_OS_SCANDIR", counted_scandir)

    assert model_load_trust_module._detect_executable_model_files(executable_model) == (
        "modeling_melix_demo.py",
    )
    assert model_load_trust_module._detect_executable_model_files(executable_model) == (
        "modeling_melix_demo.py",
    )
    assert scandir_calls == 1

    file_model = WorkerModelCatalog.dev_text_model()
    file_model.model_path = str(executable_model_dir / "modeling_melix_demo.py")
    assert model_load_trust_module._detect_executable_model_files(file_model) == ()

    monkeypatch.setenv("HOME", str(tmp_path))
    tilde_model_dir = tmp_path / "tilde-executable-model"
    tilde_model_dir.mkdir()
    (tilde_model_dir / "configuration_melix_demo.py").write_text(
        "class MelixDemoConfig: pass\n",
        encoding="utf-8",
    )
    tilde_model = WorkerModelCatalog.dev_text_model()
    tilde_model.model_path = "~/tilde-executable-model"
    assert model_load_trust_module._detect_executable_model_files(tilde_model) == (
        "configuration_melix_demo.py",
    )


def test_trust_policy_treats_blank_model_path_as_absent(tmp_path: Path) -> None:
    model = WorkerModelCatalog.dev_text_model()
    model.model_path = "  "

    policy = resolve_model_load_trust_policy(
        model,
        request_policy=None,
        runtime_kind="text",
        runtime=RecordingTextBackend(),
    )

    assert policy.custom_loader_required is False
    assert policy.custom_loader_detection_source == "config_json:absent"

    empty_path_model = WorkerModelCatalog.dev_text_model()
    empty_path_model.model_path = ""
    empty_path_policy = resolve_model_load_trust_policy(
        empty_path_model,
        request_policy=None,
        runtime_kind="text",
        runtime=RecordingTextBackend(),
    )

    assert empty_path_policy.custom_loader_required is False
    assert empty_path_policy.custom_loader_detection_source == "config_json:absent"

    missing_path_model = WorkerModelCatalog.dev_text_model()
    missing_path_model.model_path = str(tmp_path / "nonexistent-subdir")
    missing_path_policy = resolve_model_load_trust_policy(
        missing_path_model,
        request_policy=None,
        runtime_kind="text",
        runtime=RecordingTextBackend(),
    )

    assert missing_path_policy.custom_loader_required is False
    assert missing_path_policy.custom_loader_detection_source == "config_json:absent"


def test_trust_policy_treats_directory_config_json_as_absent(tmp_path: Path) -> None:
    model_dir = tmp_path / "directory-config-model"
    model_dir.mkdir()
    (model_dir / "config.json").mkdir()
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

    executable_model_dir = tmp_path / "executable-directory-config-model"
    executable_model_dir.mkdir()
    (executable_model_dir / "config.json").mkdir()
    (executable_model_dir / "processing_melix_demo.py").write_text(
        "class MelixDemoProcessor: pass\n",
        encoding="utf-8",
    )
    executable_model = WorkerModelCatalog.dev_text_model()
    executable_model.model_path = str(executable_model_dir)

    with pytest.raises(model_load_trust_module.ModelLoadTrustRejection) as exc_info:
        resolve_model_load_trust_policy(
            executable_model,
            request_policy=None,
            runtime_kind="text",
            runtime=RecordingTextBackend(),
        )

    assert exc_info.value.policy.custom_loader_required is True
    assert exc_info.value.policy.custom_loader_detection_source == "model_files:processing_melix_demo.py"


def test_trust_policy_treats_empty_config_json_as_absent(tmp_path: Path) -> None:
    model_dir = tmp_path / "empty-config-model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
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


def test_trust_policy_reports_config_json_without_auto_map_loader(tmp_path: Path) -> None:
    model_dir = tmp_path / "plain-config-model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text(json.dumps({"model_type": "llama"}), encoding="utf-8")
    (model_dir / "README.py").write_text("NOT_A_LOADER = True\n", encoding="utf-8")
    nested_dir = model_dir / "nested"
    nested_dir.mkdir()
    (nested_dir / "modeling_nested.py").write_text("class NestedModel: pass\n", encoding="utf-8")
    target = model_dir / "target_loader.py"
    target.write_text("class TargetLoader: pass\n", encoding="utf-8")
    (model_dir / "modeling_symlink.py").symlink_to(target)
    model = WorkerModelCatalog.dev_text_model()
    model.model_path = str(model_dir)

    policy = resolve_model_load_trust_policy(
        model,
        request_policy=None,
        runtime_kind="text",
        runtime=RecordingTextBackend(),
    )

    assert policy.custom_loader_required is False
    assert policy.custom_loader_detection_source == "config_json"
    assert model_load_trust_module._detect_executable_model_files(model) == ()

    class BrokenEntry:
        name = "modeling_broken.py"

        def is_file(self, *, follow_symlinks: bool = True) -> bool:
            _ = follow_symlinks
            raise OSError("cannot stat entry")

    assert model_load_trust_module._is_executable_model_file_entry(BrokenEntry()) is False


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


def _executable_file_text_model(tmp_path: Path) -> common_pb2.ModelSpec:
    model_dir = tmp_path / "executable-file-model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text(json.dumps({"model_type": "llama"}), encoding="utf-8")
    (model_dir / "modeling_melix_demo.py").write_text(
        "class MelixDemoModel: pass\n",
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
