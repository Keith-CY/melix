from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class TextFamilyDescriptor:
    family_id: str
    default_architecture: str
    preferred_route_kind: str | None
    supported_parsers: tuple[str, ...]
    attention_profile: str
    rope_profile: str
    moe_enabled: bool = False
    default_expert_count: int = 0
    moe_gate_dequant: bool = False
    tool_parser_mode: str = ""
    tool_parser_namespaces: tuple[str, ...] = ()
    tool_parser_xml_fallback: bool = False


@dataclass(frozen=True)
class TextFamilyDetection:
    architecture: str
    family_id: str
    source: str


@dataclass(frozen=True)
class ResolvedTextFamilyConfig:
    family_id: str
    architecture: str
    route_kind: str
    text_backend_id: str
    supported_parsers: tuple[str, ...]
    tool_parser_mode: str
    tool_parser_namespaces: tuple[str, ...]
    tool_parser_xml_fallback: bool
    attention_profile: str
    rope_profile: str
    moe_enabled: bool
    expert_count: int
    moe_gate_dequant: bool

    def capability_metadata(self) -> dict[str, str]:
        metadata = {
            "text_backend_id": self.text_backend_id,
            "text_family_id": self.family_id,
            "model_architecture": self.architecture,
            "melix.adapter_set_hash": f"text-family-{self.family_id}",
            "melix.capability.route_kind": self.route_kind,
            "melix.capability.class": "text",
            "melix.capability.supported_modalities": "text",
            "melix.capability.supported_tasks": "generate",
            "melix.capability.supported_parsers": ",".join(self.supported_parsers),
            "melix.text.attention_profile": self.attention_profile,
            "melix.text.rope_profile": self.rope_profile,
            "melix.text.moe.enabled": "true" if self.moe_enabled else "false",
            "melix.text.moe.gate_dequant": "true" if self.moe_gate_dequant else "false",
        }
        if self.expert_count > 0:
            metadata["melix.text.moe.expert_count"] = str(self.expert_count)
        if self.tool_parser_mode:
            metadata["tool_parser_mode"] = self.tool_parser_mode
        if self.tool_parser_namespaces:
            metadata["tool_parser_namespaces"] = ",".join(self.tool_parser_namespaces)
        if self.tool_parser_xml_fallback:
            metadata["tool_parser_xml_fallback"] = "true"
        return metadata

    def runtime_metadata(self) -> dict[str, str]:
        return {
            "text_backend_id": self.text_backend_id,
            "text_family_id": self.family_id,
            "model_architecture": self.architecture,
            "text_attention_profile": self.attention_profile,
            "text_rope_profile": self.rope_profile,
            "text_moe_enabled": "true" if self.moe_enabled else "false",
            "text_moe_expert_count": str(self.expert_count),
            "text_moe_gate_dequant": "true" if self.moe_gate_dequant else "false",
        }


_DEFAULT_TEXT_FAMILY_ID = "llama"
_TEXT_FAMILY_ADAPTERS: dict[str, TextFamilyDescriptor] = {
    "llama": TextFamilyDescriptor(
        family_id="llama",
        default_architecture="llama",
        preferred_route_kind=None,
        supported_parsers=("text",),
        attention_profile="gqa",
        rope_profile="standard",
    ),
    "mistral4": TextFamilyDescriptor(
        family_id="mistral4",
        default_architecture="mistral4",
        preferred_route_kind="python_text_compatibility",
        supported_parsers=("text",),
        attention_profile="gqa",
        rope_profile="yarn_interleaved",
        moe_enabled=True,
        default_expert_count=8,
        moe_gate_dequant=True,
    ),
    "mixtral": TextFamilyDescriptor(
        family_id="mixtral",
        default_architecture="mixtral",
        preferred_route_kind="python_text_compatibility",
        supported_parsers=("text",),
        attention_profile="gqa",
        rope_profile="standard",
        moe_enabled=True,
        default_expert_count=8,
    ),
    "qwen3moe": TextFamilyDescriptor(
        family_id="qwen3moe",
        default_architecture="qwen3_moe",
        preferred_route_kind="python_text_compatibility",
        supported_parsers=("text", "qwen"),
        attention_profile="gqa",
        rope_profile="yarn_interleaved",
        moe_enabled=True,
        default_expert_count=128,
        moe_gate_dequant=True,
        tool_parser_mode="qwen",
        tool_parser_namespaces=("tools.text",),
        tool_parser_xml_fallback=True,
    ),
    "deepseek-mla": TextFamilyDescriptor(
        family_id="deepseek-mla",
        default_architecture="deepseek_v3",
        preferred_route_kind="python_text_compatibility",
        supported_parsers=("text",),
        attention_profile="mla",
        rope_profile="standard",
        moe_enabled=True,
        default_expert_count=64,
        moe_gate_dequant=True,
    ),
    "nemotron-h": TextFamilyDescriptor(
        family_id="nemotron-h",
        default_architecture="nemotron_h",
        preferred_route_kind="python_text_compatibility",
        supported_parsers=("text",),
        attention_profile="gqa",
        rope_profile="standard",
    ),
}


def detect_text_family_identity(
    *,
    model_path: str,
    config_payload: Mapping[str, Any] | None = None,
    explicit_family_id: str = "",
) -> TextFamilyDetection:
    explicit_family_id = explicit_family_id.strip().lower()
    if explicit_family_id:
        descriptor = _TEXT_FAMILY_ADAPTERS.get(explicit_family_id)
        if descriptor is None:
            raise ValueError(f"Unsupported text family adapter: {explicit_family_id}")
        architecture = _detected_architecture(config_payload) or descriptor.default_architecture
        return TextFamilyDetection(
            architecture=architecture,
            family_id=explicit_family_id,
            source="explicit_override",
        )

    architecture = _detected_architecture(config_payload)
    model_type = _model_type(config_payload)
    normalized_source = " ".join(
        value
        for value in (
            model_path.lower(),
            architecture.lower(),
            model_type.lower(),
        )
        if value
    )
    if model_type == "mistral4" or "mistral4" in normalized_source or "mistral-small-4" in normalized_source:
        return TextFamilyDetection(
            architecture=architecture or "mistral4",
            family_id="mistral4",
            source="config.model_type" if model_type == "mistral4" else "directory_name",
        )
    if "mixtral" in normalized_source:
        return TextFamilyDetection(
            architecture=architecture or "mixtral",
            family_id="mixtral",
            source="config.architecture" if architecture else "directory_name",
        )
    if (
        model_type in {"qwen3_moe", "qwen3moe"}
        or ("qwen3" in normalized_source and "moe" in normalized_source)
    ):
        return TextFamilyDetection(
            architecture=architecture or "qwen3_moe",
            family_id="qwen3moe",
            source="config.model_type" if model_type else "directory_name",
        )
    if _inferred_attention_profile(config_payload, default="") == "mla" or "deepseek" in normalized_source:
        return TextFamilyDetection(
            architecture=architecture or "deepseek_v3",
            family_id="deepseek-mla",
            source="config.architecture" if architecture else "directory_name",
        )
    if "nemotron_h" in normalized_source or "nemotron-h" in normalized_source:
        return TextFamilyDetection(
            architecture=architecture or "nemotron_h",
            family_id="nemotron-h",
            source="config.architecture" if architecture else "directory_name",
        )
    return TextFamilyDetection(
        architecture=architecture or "llama",
        family_id="llama",
        source="config.architecture" if architecture else "default",
    )


def resolve_text_family_config(
    metadata: Mapping[str, str] | None = None,
    *,
    model_path: str = "",
    config_payload: Mapping[str, Any] | None = None,
    default_route_kind: str = "swift_text",
) -> ResolvedTextFamilyConfig:
    metadata = dict(metadata or {})
    detection = detect_text_family_identity(
        model_path=model_path,
        config_payload=config_payload,
        explicit_family_id=metadata.get("text_family_id", ""),
    )
    descriptor = _TEXT_FAMILY_ADAPTERS[detection.family_id]
    configured_route_kind = _string_value(metadata, "melix.capability.route_kind", "")
    route_kind = (
        configured_route_kind
        or descriptor.preferred_route_kind
        or default_route_kind
    )
    supported_parsers = tuple(
        _split_csv(metadata.get("melix.capability.supported_parsers", ""))
        or descriptor.supported_parsers
    )
    expert_count = _int_value(
        metadata,
        "melix.text.moe.expert_count",
        default=_inferred_expert_count(config_payload, default=descriptor.default_expert_count),
    )
    moe_enabled = _bool_value(
        metadata,
        "melix.text.moe.enabled",
        default=expert_count > 0 or descriptor.moe_enabled,
    )
    return ResolvedTextFamilyConfig(
        family_id=detection.family_id,
        architecture=_string_value(metadata, "model_architecture", detection.architecture or descriptor.default_architecture),
        route_kind=route_kind,
        text_backend_id=_string_value(metadata, "text_backend_id", "mlx_lm"),
        supported_parsers=supported_parsers,
        tool_parser_mode=_string_value(metadata, "tool_parser_mode", descriptor.tool_parser_mode),
        tool_parser_namespaces=tuple(
            _split_csv(metadata.get("tool_parser_namespaces", ""))
            or descriptor.tool_parser_namespaces
        ),
        tool_parser_xml_fallback=_bool_value(
            metadata,
            "tool_parser_xml_fallback",
            default=descriptor.tool_parser_xml_fallback,
        ),
        attention_profile=_string_value(
            metadata,
            "melix.text.attention_profile",
            _inferred_attention_profile(config_payload, default=descriptor.attention_profile),
        ),
        rope_profile=_string_value(
            metadata,
            "melix.text.rope_profile",
            _inferred_rope_profile(config_payload, default=descriptor.rope_profile),
        ),
        moe_enabled=moe_enabled,
        expert_count=expert_count if moe_enabled else 0,
        moe_gate_dequant=_bool_value(
            metadata,
            "melix.text.moe.gate_dequant",
            default=_inferred_moe_gate_dequant(config_payload, default=descriptor.moe_gate_dequant),
        ),
    )


def _detected_architecture(config_payload: Mapping[str, Any] | None) -> str:
    config_payload = dict(config_payload or {})
    model_type = _model_type(config_payload)
    if model_type:
        return model_type
    architectures = config_payload.get("architectures")
    if isinstance(architectures, list):
        for item in architectures:
            if isinstance(item, str) and item.strip():
                return item.strip().lower()
    text_config = config_payload.get("text_config")
    if isinstance(text_config, Mapping):
        nested_model_type = _string(text_config.get("model_type"))
        if nested_model_type:
            return nested_model_type.lower()
    return ""


def _model_type(config_payload: Mapping[str, Any] | None) -> str:
    config_payload = dict(config_payload or {})
    model_type = _string(config_payload.get("model_type"))
    if model_type:
        return model_type.lower()
    return ""


def _inferred_attention_profile(config_payload: Mapping[str, Any] | None, *, default: str) -> str:
    config_payload = dict(config_payload or {})
    for key in ("attention_type", "attn_type", "attention_impl", "attn_impl"):
        value = _string(config_payload.get(key)).lower()
        if "mla" in value:
            return "mla"
    if _bool_from_any(config_payload.get("use_mla")):
        return "mla"
    return default


def _inferred_rope_profile(config_payload: Mapping[str, Any] | None, *, default: str) -> str:
    config_payload = dict(config_payload or {})
    rope_scaling = config_payload.get("rope_scaling")
    if isinstance(rope_scaling, Mapping):
        rope_type = _string(rope_scaling.get("rope_type") or rope_scaling.get("type")).lower()
        if "yarn" in rope_type:
            if _bool_from_any(rope_scaling.get("interleaved")) or _bool_from_any(config_payload.get("rope_interleaved")):
                return "yarn_interleaved"
            return "yarn"
    if _bool_from_any(config_payload.get("rope_interleaved")) and default.startswith("yarn"):
        return "yarn_interleaved"
    return default


def _inferred_expert_count(config_payload: Mapping[str, Any] | None, *, default: int) -> int:
    config_payload = dict(config_payload or {})
    for key in ("num_local_experts", "num_experts", "moe_num_experts", "n_routed_experts"):
        value = config_payload.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return max(0, value)
        if isinstance(value, float):
            return max(0, int(value))
        if isinstance(value, str) and value.strip():
            try:
                return max(0, int(value.strip()))
            except ValueError:
                continue
    return max(0, default)


def _inferred_moe_gate_dequant(config_payload: Mapping[str, Any] | None, *, default: bool) -> bool:
    config_payload = dict(config_payload or {})
    for key in ("moe_gate_dequant", "dequantize_router_logits", "moe_gate_requires_dequant"):
        value = config_payload.get(key)
        if value is not None:
            return _bool_from_any(value)
    return default


def _string_value(metadata: Mapping[str, str], key: str, default: str) -> str:
    value = metadata.get(key, "").strip()
    return value or default


def _split_csv(raw_value: str) -> list[str]:
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def _int_value(metadata: Mapping[str, str], key: str, *, default: int) -> int:
    raw_value = metadata.get(key, "").strip()
    if not raw_value:
        return max(0, default)
    try:
        parsed = int(raw_value)
    except ValueError:
        return max(0, default)
    return max(0, parsed)


def _bool_value(metadata: Mapping[str, str], key: str, *, default: bool) -> bool:
    raw_value = metadata.get(key, "").strip()
    if not raw_value:
        return default
    return _bool_from_any(raw_value)


def _bool_from_any(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return False


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""
