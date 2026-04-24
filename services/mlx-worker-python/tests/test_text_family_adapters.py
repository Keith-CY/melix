from __future__ import annotations

import pytest

from worker.runtime.text_family_adapters import (
    _inferred_expert_count,
    detect_text_family_identity,
    resolve_text_family_config,
)


def test_detect_text_family_identity_prefers_explicit_supported_override() -> None:
    detected = detect_text_family_identity(
        model_path="models/unknown-text-model",
        config_payload={"model_type": "llama"},
        explicit_family_id="qwen3moe",
    )

    assert detected.family_id == "qwen3moe"
    assert detected.architecture == "llama"
    assert detected.source == "explicit_override"


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


def test_inferred_expert_count_preserves_config_before_family_default() -> None:
    assert _inferred_expert_count({"num_experts": 4}, default=128) == 4
    assert _inferred_expert_count({}, default=128) == 128
