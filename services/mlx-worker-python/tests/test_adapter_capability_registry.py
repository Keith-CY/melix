from __future__ import annotations

from pathlib import Path

import pytest

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_ops.adapter_capabilities import (
    DEFAULT_ADAPTER_CAPABILITY_REGISTRY,
    UNSUPPORTED_REASON_MISSING_ADAPTER_PROVIDER,
    UNSUPPORTED_REASON_MISSING_QUANTIZATION_PROVIDER,
    UNSUPPORTED_REASON_UNSUPPORTED_BACKEND,
    UNSUPPORTED_REASON_UNSUPPORTED_QUANTIZED_BASE,
    AdapterCapabilities,
    AdapterCapabilityRecord,
    AdapterCapabilityRegistry,
)
from worker.model_ops.errors import ModelOperationError
from worker.model_ops import mlx_lm_runner as mlx_lm_runner_module
from worker.model_ops import training_config as training_config_module


def _text_model(
    *,
    model_path: str = "models/plain-llama",
    quant_profile_id: str = "",
) -> common_pb2.ModelSpec:
    model = common_pb2.ModelSpec(
        model_id="melix-test-text",
        model_path=model_path,
        model_kind="text",
        revision="main",
        quant_profile_id=quant_profile_id,
        max_context=4096,
    )
    model.ext["text_layer_count"] = "2"
    return model


def _normalize(
    *,
    source_model: common_pb2.ModelSpec | None = None,
    ext: dict[str, str] | None = None,
    adapter_registry: AdapterCapabilityRegistry | None = None,
):
    return training_config_module.normalize_training_config(
        source_model=source_model or _text_model(),
        ext=ext or {},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
        adapter_registry=adapter_registry,
    )


def _fake_registry(
    *,
    mergeable: bool = False,
    quantized_base_supported: bool = False,
    backend_supported: bool = True,
    unsupported_reason: str = "",
) -> AdapterCapabilityRegistry:
    return AdapterCapabilityRegistry(
        [
            AdapterCapabilityRecord(
                adapter_family="fake_relora",
                adapter_algorithm="fake_relora",
                capabilities=AdapterCapabilities(
                    lora_like=True,
                    mergeable=mergeable,
                    relora_compatible=True,
                    quantized_base_supported=quantized_base_supported,
                ),
                backend_supported=backend_supported,
                unsupported_reason=unsupported_reason,
                loader_kwargs={"extension_loader": "fake_relora_loader"},
            )
        ]
    )


def test_default_registry_declares_builtin_adapter_capabilities() -> None:
    lora = DEFAULT_ADAPTER_CAPABILITY_REGISTRY.resolve("lora")
    qlora = DEFAULT_ADAPTER_CAPABILITY_REGISTRY.resolve("qlora")
    dora = DEFAULT_ADAPTER_CAPABILITY_REGISTRY.resolve("dora")

    assert lora is not None
    assert qlora is not None
    assert dora is not None
    assert lora.adapter_algorithm == "lora"
    assert qlora.adapter_algorithm == "lora"
    assert dora.adapter_algorithm == "dora"
    assert lora.capabilities.as_manifest() == {
        "lora_like": True,
        "mergeable": True,
        "relora_compatible": True,
        "quantized_base_supported": True,
    }
    assert dora.capabilities.relora_compatible is False
    assert DEFAULT_ADAPTER_CAPABILITY_REGISTRY.resolve("missing") is None


def test_normalize_training_config_uses_extension_registry_for_fake_adapter(tmp_path: Path) -> None:
    config = _normalize(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        ext={"adapter_family": "fake_relora"},
        adapter_registry=_fake_registry(),
    )

    assert config.adapter_family == "fake_relora"
    assert config.adapter_algorithm == "fake_relora"
    assert config.adapter_capabilities == {
        "lora_like": True,
        "mergeable": False,
        "relora_compatible": True,
        "quantized_base_supported": False,
    }
    assert config.adapter_loader_kwargs == {"extension_loader": "fake_relora_loader"}
    assert config.backend_supported is True
    assert config.unsupported_reason == ""


def test_normalize_training_config_rejects_missing_adapter_provider() -> None:
    with pytest.raises(ModelOperationError) as exc:
        _normalize(ext={"adapter_family": "unknown_extension"})

    assert exc.value.code == UNSUPPORTED_REASON_MISSING_ADAPTER_PROVIDER
    assert exc.value.details["adapter_family"] == "unknown_extension"


def test_normalize_training_config_rejects_backend_unsupported_adapter() -> None:
    registry = _fake_registry(
        backend_supported=False,
        unsupported_reason=UNSUPPORTED_REASON_UNSUPPORTED_BACKEND,
    )

    with pytest.raises(ModelOperationError) as exc:
        _normalize(ext={"adapter_family": "fake_relora"}, adapter_registry=registry)

    assert exc.value.code == UNSUPPORTED_REASON_UNSUPPORTED_BACKEND
    assert exc.value.details["adapter_family"] == "fake_relora"


def test_normalize_training_config_rejects_quantized_base_when_adapter_cannot_support_it() -> None:
    with pytest.raises(ModelOperationError) as exc:
        _normalize(
            source_model=_text_model(model_path="mlx-community/Tiny-4bit", quant_profile_id="q4"),
            ext={"adapter_family": "fake_relora"},
            adapter_registry=_fake_registry(quantized_base_supported=False),
        )

    assert exc.value.code == UNSUPPORTED_REASON_UNSUPPORTED_QUANTIZED_BASE
    assert exc.value.details["adapter_family"] == "fake_relora"
    assert exc.value.details["base_quantization_method"] == "quant_profile"


def test_normalize_training_config_rejects_missing_quantization_provider() -> None:
    source_model = _text_model(model_path="models/custom-quant")
    source_model.ext["melix.quantization.method"] = "vendor_nf4"

    with pytest.raises(ModelOperationError) as exc:
        _normalize(source_model=source_model, ext={"training_mode": "qlora"})

    assert exc.value.code == UNSUPPORTED_REASON_MISSING_QUANTIZATION_PROVIDER
    assert exc.value.details["base_quantization_method"] == "vendor_nf4"


def test_normalize_training_config_accepts_registered_quantization_provider() -> None:
    source_model = _text_model(model_path="models/custom-quant")
    source_model.ext["melix.quantization.method"] = "vendor_nf4"
    source_model.ext["melix.quantization.provider"] = "vendor-provider"

    config = _normalize(source_model=source_model, ext={"training_mode": "qlora"})

    assert config.base_quantization_method == "vendor_nf4"
    assert config.adapter_family == "qlora"


def test_quantization_helpers_report_path_hints_and_legacy_boolean() -> None:
    source_model = _text_model(model_path="mlx-community/Tiny-Q4")

    assert training_config_module._base_quantization_method(source_model) == "path_hint"
    assert training_config_module._is_quantized_base_model(source_model) is True


def test_mlx_lora_namespace_forwards_extension_loader_kwargs(tmp_path: Path) -> None:
    config = _normalize(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        ext={"adapter_family": "fake_relora"},
        adapter_registry=_fake_registry(),
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-extension",
        base_model_id="melix-dev-text",
        model_path=tmp_path / "base-model",
        model_revision="main",
        adapter_output_dir=tmp_path / "adapter-output",
        normalized_dataset_dir=tmp_path / "normalized",
        config=config,
        dataset_format="chat_messages",
    )

    namespace = mlx_lm_runner_module._mlx_lora_namespace(request)

    assert namespace.fine_tune_type == "fake_relora"
    assert namespace.adapter_family == "fake_relora"
    assert namespace.adapter_capabilities["relora_compatible"] is True
    assert namespace.adapter_loader_kwargs == {"extension_loader": "fake_relora_loader"}
