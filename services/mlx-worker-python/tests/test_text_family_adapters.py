from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

import pytest

from worker.runtime.text_family_adapters import (
    ResolvedTextFamilyConfig,
    TextFamilyDescriptor,
    TextFamilyDetection,
    _bool_from_any,
    _bool_value,
    _inferred_attention_profile,
    _inferred_expert_count,
    _inferred_rope_profile,
    _split_csv,
    _string_value,
    detect_text_family_identity,
    resolve_text_family_config,
)


class _CopyCountingConfig(Mapping[str, Any]):
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self._payload = dict(payload)
        self.copy_attempts = 0
        self.key_accesses = 0

    def __getitem__(self, key: str) -> Any:
        self.key_accesses += 1
        return self._payload[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._payload)

    def __len__(self) -> int:
        return len(self._payload)

    def keys(self):  # type: ignore[override]
        self.copy_attempts += 1
        return self._payload.keys()


def test_text_family_dataclasses_are_slotted_for_repeated_resolution_memory() -> None:
    resolved = resolve_text_family_config(
        {"text_family_id": "qwen3moe"},
        model_path="models/qwen3-moe-128e",
        config_payload={"model_type": "qwen3_moe"},
    )
    detected = detect_text_family_identity(
        model_path="models/qwen3-moe-128e",
        config_payload={"model_type": "qwen3_moe"},
    )

    assert isinstance(resolved, ResolvedTextFamilyConfig)
    assert isinstance(detected, TextFamilyDetection)
    assert not hasattr(resolved, "__dict__")
    assert not hasattr(detected, "__dict__")
    assert not hasattr(
        TextFamilyDescriptor(
            family_id="probe",
            default_architecture="probe",
            preferred_route_kind=None,
            supported_parsers=("text",),
            attention_profile="gqa",
            rope_profile="standard",
        ),
        "__dict__",
    )


def test_split_csv_short_circuits_empty_values_without_split() -> None:
    class NoSplitEmpty(str):
        def split(self, *args: object, **kwargs: object) -> list[str]:  # pragma: no cover
            raise AssertionError("empty CSV values should not allocate split parts")

    assert _split_csv(NoSplitEmpty("")) == []
    assert _split_csv(" text, qwen ,, tools ") == ["text", "qwen", "tools"]


def test_split_csv_short_circuits_single_values_without_split() -> None:
    class NoSplitSingle(str):
        def split(self, *args: object, **kwargs: object) -> list[str]:  # pragma: no cover
            raise AssertionError("single CSV values should not allocate split parts")

    assert _split_csv(NoSplitSingle(" qwen ")) == ["qwen"]


def test_string_value_short_circuits_missing_values_without_strip() -> None:
    class NoStripEmpty(str):
        def strip(self, *args: object, **kwargs: object) -> str:  # pragma: no cover
            raise AssertionError("missing metadata values should not allocate strip results")

    class MissingMetadata(dict[str, str]):
        def get(self, key: str, default: object = None) -> object:  # type: ignore[override]
            return NoStripEmpty("")

    assert _string_value(MissingMetadata(), "missing", "fallback") == "fallback"


def test_string_value_trims_metadata_values() -> None:
    assert (
        _string_value({"text_backend_id": "mlx_lm"}, "text_backend_id", "fallback")
        == "mlx_lm"
    )
    assert (
        _string_value({"text_backend_id": " mlx_lm "}, "text_backend_id", "fallback")
        == "mlx_lm"
    )


def test_inferred_attention_profile_skips_non_string_hints_and_preserves_use_mla_fallback() -> None:
    assert (
        _inferred_attention_profile(
            {"attention_type": 0, "attn_type": None, "attention_impl": [], "use_mla": True},
            default="gqa",
        )
        == "mla"
    )
    assert _inferred_attention_profile({"attention_impl": "flash-mla"}, default="gqa") == "mla"
    assert _inferred_attention_profile({"attention_impl": 0}, default="gqa") == "gqa"


def test_inferred_rope_profile_preserves_yarn_fallback_and_non_string_defaults() -> None:
    assert (
        _inferred_rope_profile(
            {"rope_scaling": {"rope_type": "", "type": "yarn", "interleaved": True}},
            default="standard",
        )
        == "yarn_interleaved"
    )
    assert (
        _inferred_rope_profile(
            {"rope_scaling": {"rope_type": 0, "type": "yarn"}},
            default="standard",
        )
        == "yarn"
    )
    assert _inferred_rope_profile({"rope_scaling": {"type": 0}}, default="standard") == "standard"


def test_detect_text_family_identity_prefers_explicit_supported_override() -> None:
    detected = detect_text_family_identity(
        model_path="models/unknown-text-model",
        config_payload={"model_type": "llama"},
        explicit_family_id="qwen3moe",
    )

    assert detected.family_id == "qwen3moe"
    assert detected.architecture == "llama"
    assert detected.source == "explicit_override"


def test_detect_text_family_identity_explicit_override_preserves_architecture_fallbacks() -> None:
    from_architecture = detect_text_family_identity(
        model_path="models/unknown-text-model",
        config_payload={"architectures": [None, "Qwen3MoeForCausalLM"]},
        explicit_family_id="qwen3moe",
    )
    from_nested_model_type = detect_text_family_identity(
        model_path="models/unknown-text-model",
        config_payload={"text_config": {"model_type": "Mistral4"}},
        explicit_family_id="qwen3moe",
    )
    from_family_default = detect_text_family_identity(
        model_path="models/unknown-text-model",
        config_payload={"architectures": "not-a-list", "text_config": []},
        explicit_family_id="qwen3moe",
    )

    assert from_architecture.architecture == "qwen3moeforcausallm"
    assert from_nested_model_type.architecture == "mistral4"
    assert from_family_default.architecture == "qwen3_moe"


def test_detect_text_family_identity_uses_exact_explicit_family_fast_path() -> None:
    class NoNormalizeFamily(str):
        def strip(self, *args: object, **kwargs: object) -> str:  # pragma: no cover
            raise AssertionError("exact explicit family ids should avoid strip allocation")

        def lower(self) -> str:  # pragma: no cover
            raise AssertionError("exact explicit family ids should avoid lower allocation")

    detected = detect_text_family_identity(
        model_path="models/unknown-text-model",
        config_payload={"model_type": "llama"},
        explicit_family_id=NoNormalizeFamily("qwen3moe"),
    )

    assert detected.family_id == "qwen3moe"
    assert detected.architecture == "llama"
    assert detected.source == "explicit_override"


def test_detect_text_family_identity_uses_lowercase_model_type_fast_path() -> None:
    class NoLowerModelType(str):
        def lower(self) -> str:  # pragma: no cover
            raise AssertionError("lowercase model_type should avoid lower allocation")

    detected = detect_text_family_identity(
        model_path="models/unknown-text-model",
        config_payload={"model_type": NoLowerModelType("qwen3_moe")},
        explicit_family_id="qwen3moe",
    )

    assert detected.architecture == "qwen3_moe"
    assert detected.family_id == "qwen3moe"


def test_detect_text_family_identity_reuses_model_type_detection_lookup() -> None:
    config = _CopyCountingConfig({"model_type": "qwen3_moe"})

    detected = detect_text_family_identity(
        model_path="models/qwen3-moe-128e",
        config_payload=config,
    )

    assert detected.architecture == "qwen3_moe"
    assert detected.family_id == "qwen3moe"
    assert config.key_accesses == 1


def test_detect_text_family_identity_rejects_unsupported_explicit_override() -> None:
    with pytest.raises(ValueError, match="Unsupported text family adapter"):
        detect_text_family_identity(
            model_path="models/unknown-text-model",
            config_payload={"model_type": "llama"},
            explicit_family_id="unsupported-family",
        )


def test_detect_text_family_identity_covers_targeted_dense_and_moe_branches() -> None:
    assert detect_text_family_identity(
        model_path="models/mistral-small-4",
        config_payload={"model_type": "mistral4"},
    ).family_id == "mistral4"
    assert detect_text_family_identity(
        model_path="models/mixtral-8x7b",
        config_payload={"model_type": "mixtral"},
    ).family_id == "mixtral"
    assert detect_text_family_identity(
        model_path="models/qwen3-moe-128e",
        config_payload={"model_type": "qwen3_moe"},
    ).family_id == "qwen3moe"
    assert detect_text_family_identity(
        model_path="models/deepseek-v3-mla",
        config_payload={"model_type": "deepseek_v3", "use_mla": True},
    ).family_id == "deepseek-mla"
    assert detect_text_family_identity(
        model_path="models/nemotron-h",
        config_payload={"model_type": "nemotron_h"},
    ).family_id == "nemotron-h"


def test_detect_text_family_identity_uses_architecture_and_nested_model_type_fallbacks() -> None:
    nested = detect_text_family_identity(
        model_path="models/unknown",
        config_payload={"text_config": {"model_type": "mistral4"}},
    )
    from_architecture = detect_text_family_identity(
        model_path="models/unknown",
        config_payload={"architectures": [None, "Nemotron_H"]},
    )

    assert nested.family_id == "mistral4"
    assert nested.architecture == "mistral4"
    assert from_architecture.family_id == "nemotron-h"
    assert from_architecture.architecture == "nemotron_h"


def test_resolve_text_family_config_inherits_default_route_for_llama_seed_models() -> None:
    resolved = resolve_text_family_config(
        {},
        model_path="models/melix-dev-text",
        default_route_kind="swift_text",
    )

    assert resolved.family_id == "llama"
    assert resolved.route_kind == "swift_text"
    assert resolved.supported_parsers == ("text",)
    assert resolved.moe_enabled is False
    assert "melix.text.moe.expert_count_source" not in resolved.capability_metadata()
    assert "text_moe_expert_count_source" not in resolved.runtime_metadata()


def test_resolve_text_family_config_enforces_python_route_and_qwen_parser_for_qwen3moe() -> None:
    resolved = resolve_text_family_config(
        {"text_family_id": "qwen3moe"},
        model_path="models/qwen3-moe-128e",
        config_payload={
            "model_type": "qwen3_moe",
            "rope_scaling": {"type": "yarn", "interleaved": True},
            "num_local_experts": 128,
            "moe_gate_dequant": True,
        },
        default_route_kind="swift_text",
    )

    assert resolved.route_kind == "python_text_compatibility"
    assert resolved.supported_parsers == ("text", "qwen")
    assert resolved.tool_parser_mode == "qwen"
    assert resolved.attention_profile == "gqa"
    assert resolved.rope_profile == "yarn_interleaved"
    assert resolved.moe_enabled is True
    assert resolved.expert_count == 128
    assert resolved.expert_count_source == "config"
    assert resolved.runtime_metadata()["text_moe_expert_count_source"] == "config"
    assert resolved.moe_gate_dequant is True


def test_resolve_text_family_config_uses_mla_attention_for_deepseek_family() -> None:
    resolved = resolve_text_family_config(
        {"text_family_id": "deepseek-mla"},
        model_path="models/deepseek-v3-mla",
        config_payload={
            "model_type": "deepseek_v3",
            "use_mla": True,
            "n_routed_experts": 64,
        },
        default_route_kind="swift_text",
    )

    assert resolved.route_kind == "python_text_compatibility"
    assert resolved.attention_profile == "mla"
    assert resolved.moe_enabled is True
    assert resolved.expert_count == 64
    assert resolved.expert_count_source == "config"


def test_resolve_text_family_config_covers_fallback_parsing_and_bool_variants() -> None:
    yarn = resolve_text_family_config(
        {"text_family_id": "qwen3moe", "melix.text.moe.expert_count": "bogus"},
        model_path="models/qwen3-moe",
        config_payload={
            "rope_scaling": {"rope_type": "yarn"},
            "num_local_experts": True,
            "num_experts": 8.0,
            "dequantize_router_logits": "off",
        },
        default_route_kind="swift_text",
    )
    interleaved = resolve_text_family_config(
        {"text_family_id": "qwen3moe", "tool_parser_xml_fallback": "0"},
        model_path="models/qwen3-moe",
        config_payload={
            "rope_interleaved": 1,
            "moe_num_experts": "not-a-number",
            "n_routed_experts": "16",
        },
        default_route_kind="swift_text",
    )
    mla = resolve_text_family_config(
        {"text_family_id": "deepseek-mla"},
        model_path="models/deepseek-v3-mla",
        config_payload={"attention_impl": "mla", "moe_gate_requires_dequant": 1},
        default_route_kind="swift_text",
    )

    assert yarn.rope_profile == "yarn"
    assert yarn.expert_count == 8
    assert yarn.expert_count_source == "config"
    assert yarn.moe_gate_dequant is False
    assert interleaved.rope_profile == "yarn_interleaved"
    assert interleaved.expert_count == 16
    assert interleaved.expert_count_source == "config"
    assert interleaved.tool_parser_xml_fallback is False
    assert mla.attention_profile == "mla"
    assert mla.moe_gate_dequant is True


def test_bool_from_any_preserves_literal_string_variants() -> None:
    class NoStripLiteral(str):
        def strip(self, *args: object, **kwargs: object) -> str:  # pragma: no cover
            raise AssertionError("normalized bool literals should not allocate stripped copies")

    assert _bool_from_any(NoStripLiteral("true")) is True
    assert _bool_from_any(NoStripLiteral("false")) is False
    assert _bool_from_any("on") is True
    assert _bool_from_any(" YES ") is True
    assert _bool_from_any("off") is False
    assert _bool_from_any(" NO ") is False
    assert _bool_from_any("maybe") is False


def test_bool_value_uses_exact_literal_fast_path_and_preserves_blank_default() -> None:
    class NoStripLiteral(str):
        def strip(self, *args: object, **kwargs: object) -> str:  # pragma: no cover
            raise AssertionError("exact bool metadata literals should avoid strip allocation")

    assert _bool_value({"flag": NoStripLiteral("true")}, "flag", default=False) is True
    assert _bool_value({"flag": NoStripLiteral("false")}, "flag", default=True) is False
    assert _bool_value({"flag": "   "}, "flag", default=True) is True
    assert _bool_value({"flag": " YES "}, "flag", default=False) is True


def test_resolve_text_family_config_marks_family_default_expert_count_source() -> None:
    resolved = resolve_text_family_config(
        {"text_family_id": "qwen3moe"},
        model_path="models/qwen3-moe",
        config_payload={"model_type": "qwen3_moe"},
        default_route_kind="swift_text",
    )

    assert resolved.expert_count == 128
    assert resolved.expert_count_source == "family_default"
    assert resolved.capability_metadata()["melix.text.moe.expert_count_source"] == "family_default"


def test_resolve_text_family_config_prefers_live_config_over_stale_expert_metadata() -> None:
    resolved = resolve_text_family_config(
        {
            "text_family_id": "qwen3moe",
            "melix.text.moe.expert_count": "128",
            "melix.text.moe.expert_count_source": "family_default",
        },
        model_path="models/qwen3-moe",
        config_payload={"model_type": "qwen3_moe", "num_local_experts": 64},
        default_route_kind="swift_text",
    )
    stale = resolve_text_family_config(
        {
            "text_family_id": "qwen3moe",
            "melix.text.moe.expert_count": "128",
            "melix.text.moe.expert_count_source": "config",
        },
        model_path="models/qwen3-moe",
        config_payload={"model_type": "qwen3_moe"},
        default_route_kind="swift_text",
    )
    preserved_default = resolve_text_family_config(
        {
            "text_family_id": "qwen3moe",
            "melix.text.moe.expert_count": "128",
            "melix.text.moe.expert_count_source": "family_default",
        },
        model_path="models/qwen3-moe",
        config_payload={"model_type": "qwen3_moe"},
        default_route_kind="swift_text",
    )

    assert resolved.expert_count == 64
    assert resolved.expert_count_source == "config"
    assert stale.expert_count == 128
    assert stale.expert_count_source == "metadata"
    assert preserved_default.expert_count == 128
    assert preserved_default.expert_count_source == "family_default"


def test_resolve_text_family_config_skips_expert_metadata_strip_for_missing_values() -> None:
    class MissingExpertMetadata(dict[str, str]):
        def get(self, key: str, default: object = None) -> object:  # type: ignore[override]
            return super().get(key, default)

    class NoStripEmpty(str):
        def strip(self, *args: object, **kwargs: object) -> str:  # pragma: no cover
            raise AssertionError("missing expert metadata should avoid strip allocation")

    metadata = MissingExpertMetadata({"text_family_id": "qwen3moe"})
    metadata["melix.text.moe.expert_count"] = NoStripEmpty("")
    metadata["melix.text.moe.expert_count_source"] = NoStripEmpty("")

    resolved = resolve_text_family_config(
        metadata,
        model_path="models/qwen3-moe",
        config_payload={"model_type": "qwen3_moe"},
        default_route_kind="swift_text",
    )

    invalid_metadata = resolve_text_family_config(
        {"text_family_id": "qwen3moe", "melix.text.moe.expert_count": "bogus"},
        model_path="models/qwen3-moe",
        config_payload={"model_type": "qwen3_moe"},
        default_route_kind="swift_text",
    )

    assert resolved.expert_count == 128
    assert resolved.expert_count_source == "family_default"
    assert invalid_metadata.expert_count == 128
    assert invalid_metadata.expert_count_source == "family_default"


def test_inferred_expert_count_preserves_config_before_family_default() -> None:
    assert _inferred_expert_count({"num_experts": 4}, default=128) == 4
    assert _inferred_expert_count({"num_local_experts": 8.0}, default=128) == 8
    assert _inferred_expert_count({"num_local_experts": "12"}, default=128) == 12
    assert _inferred_expert_count({"num_local_experts": True, "num_experts": 4}, default=128) == 4
    assert _inferred_expert_count({"num_local_experts": "bogus", "num_experts": 4}, default=128) == 4
    assert _inferred_expert_count({"num_local_experts": " ", "num_experts": "4"}, default=128) == 4
    assert _inferred_expert_count({}, default=128) == 128


def test_resolve_text_family_config_reads_metadata_mapping_without_copying() -> None:
    metadata = _CopyCountingConfig(
        {
            **{f"unused_{index}": str(index) for index in range(512)},
            "text_family_id": "qwen3moe",
            "melix.capability.route_kind": "python_text_compatibility",
            "tool_parser_namespaces": "tools.text, tools.vision",
        }
    )

    resolved = resolve_text_family_config(
        metadata,  # type: ignore[arg-type]
        model_path="models/qwen3-moe-128e",
        config_payload={"model_type": "qwen3_moe"},
        default_route_kind="swift_text",
    )

    assert resolved.family_id == "qwen3moe"
    assert resolved.route_kind == "python_text_compatibility"
    assert resolved.tool_parser_namespaces == ("tools.text", "tools.vision")
    assert metadata.copy_attempts == 0
    assert dict(metadata)["text_family_id"] == "qwen3moe"
    assert metadata.copy_attempts == 1


def test_resolve_text_family_config_reads_config_mapping_without_copying() -> None:
    config = _CopyCountingConfig(
        {
            **{f"unused_{index}": index for index in range(512)},
            "model_type": "qwen3_moe",
            "rope_scaling": {"type": "yarn", "interleaved": True},
            "num_local_experts": 128,
            "moe_gate_dequant": True,
        }
    )

    resolved = resolve_text_family_config(
        {"text_family_id": "qwen3moe"},
        model_path="models/qwen3-moe-128e",
        config_payload=config,
        default_route_kind="swift_text",
    )

    assert resolved.family_id == "qwen3moe"
    assert resolved.rope_profile == "yarn_interleaved"
    assert resolved.expert_count == 128
    assert resolved.moe_gate_dequant is True
    assert config.copy_attempts == 0
    assert list(config)[:1] == ["unused_0"]
    assert len(config) == 516
    assert dict(config)["model_type"] == "qwen3_moe"
    assert config.copy_attempts == 1


def test_resolve_text_family_config_skips_gate_dequant_strip_for_exact_bool_metadata() -> None:
    class NoStripLiteral(str):
        def strip(self, *args: object, **kwargs: object) -> str:  # pragma: no cover
            raise AssertionError("exact gate dequant metadata literals should avoid strip allocation")

    resolved = resolve_text_family_config(
        {
            "text_family_id": "qwen3moe",
            "melix.text.moe.gate_dequant": NoStripLiteral("true"),
        },
        model_path="models/qwen3-moe-128e",
        config_payload={"model_type": "qwen3_moe", "moe_gate_dequant": False},
        default_route_kind="swift_text",
    )
    exact_false = resolve_text_family_config(
        {
            "text_family_id": "qwen3moe",
            "melix.text.moe.gate_dequant": NoStripLiteral("false"),
        },
        model_path="models/qwen3-moe-128e",
        config_payload={"model_type": "qwen3_moe", "moe_gate_dequant": True},
        default_route_kind="swift_text",
    )
    padded = resolve_text_family_config(
        {
            "text_family_id": "qwen3moe",
            "melix.text.moe.gate_dequant": " false ",
        },
        model_path="models/qwen3-moe-128e",
        config_payload={"model_type": "qwen3_moe", "moe_gate_dequant": True},
        default_route_kind="swift_text",
    )
    blank = resolve_text_family_config(
        {
            "text_family_id": "qwen3moe",
            "melix.text.moe.gate_dequant": "   ",
        },
        model_path="models/qwen3-moe-128e",
        config_payload={"model_type": "qwen3_moe", "moe_gate_dequant": True},
        default_route_kind="swift_text",
    )

    assert resolved.moe_gate_dequant is True
    assert exact_false.moe_gate_dequant is False
    assert padded.moe_gate_dequant is False
    assert blank.moe_gate_dequant is True


def test_resolve_text_family_config_skips_config_hints_when_metadata_overrides() -> None:
    class AccessCountingConfig(Mapping[str, Any]):
        def __init__(self, payload: Mapping[str, Any]) -> None:
            self._payload = dict(payload)
            self.keys_read: list[str] = []

        def __getitem__(self, key: str) -> Any:
            self.keys_read.append(key)
            return self._payload[key]

        def __iter__(self) -> Iterator[str]:
            return iter(self._payload)

        def __len__(self) -> int:
            return len(self._payload)

    config = AccessCountingConfig(
        {
            "model_type": "qwen3_moe",
            "attention_impl": "mla",
            "rope_scaling": {"type": "yarn", "interleaved": True},
            "num_local_experts": 128,
            "moe_gate_dequant": False,
        }
    )

    resolved = resolve_text_family_config(
        {
            "text_family_id": "qwen3moe",
            "melix.text.attention_profile": "gqa",
            "melix.text.rope_profile": "standard",
            "melix.text.moe.gate_dequant": "true",
        },
        model_path="models/qwen3-moe-128e",
        config_payload=config,
        default_route_kind="swift_text",
    )

    assert resolved.attention_profile == "gqa"
    assert resolved.rope_profile == "standard"
    assert resolved.moe_gate_dequant is True
    assert resolved.expert_count == 128
    assert list(config)[:1] == ["model_type"]
    assert len(config) == 5
    assert set(config.keys_read).isdisjoint(
        {
            "attention_type",
            "attn_type",
            "attention_impl",
            "attn_impl",
            "use_mla",
            "rope_scaling",
            "rope_interleaved",
            "moe_gate_dequant",
            "dequantize_router_logits",
            "moe_gate_requires_dequant",
        }
    )
