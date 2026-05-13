from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from packages.protocol.python.worker.v1 import common_pb2


ADAPTER_RUNTIME_BASE_REUSE_KEY = "adapter_runtime.base_reuse_key"
ADAPTER_RUNTIME_ISOLATION_KEY = "adapter_runtime.adapter_isolation_key"
ADAPTER_RUNTIME_SWITCH_MODE = "adapter_runtime.switch_mode"
ADAPTER_RUNTIME_SHARING_POLICY = "adapter_runtime.sharing_policy"
ADAPTER_RUNTIME_COMPATIBILITY_STATUS = "adapter_runtime.compatibility_status"
QUANTIZED_BASE_DETECTED = "quantized_base_detected"
QUANTIZED_BASE_KIND = "quantized_base_kind"
QUANTIZATION_PROFILE_ID = "quantization_profile_id"
QUANTIZED_BASE_EVIDENCE_SOURCE = "quantized_base_evidence_source"
QLORA_COMPATIBILITY_STATUS = "qlora_compatibility_status"
QUANTIZED_TARGET_MODULE_GUARD = "quantized_target_module_guard"

_QUANTIZED_KIND_ORDER = ("4bit", "8bit", "q4", "q8", "optiq")


ADAPTER_RUNTIME_EXT_KEY_MAP: tuple[tuple[str, str], ...] = (
    (ADAPTER_RUNTIME_BASE_REUSE_KEY, "melix.adapter_runtime.base_reuse_key"),
    (ADAPTER_RUNTIME_ISOLATION_KEY, "melix.adapter_runtime.adapter_isolation_key"),
    (ADAPTER_RUNTIME_SWITCH_MODE, "melix.adapter_runtime.switch_mode"),
    (ADAPTER_RUNTIME_SHARING_POLICY, "melix.adapter_runtime.sharing_policy"),
    (
        ADAPTER_RUNTIME_COMPATIBILITY_STATUS,
        "melix.adapter_runtime.compatibility_status",
    ),
)


def build_adapter_runtime_manifest_fields(
    *,
    source_model: common_pb2.ModelSpec,
    adapter_manifest: Mapping[str, Any],
    adapter_manifest_path: str | Path,
    adapter_weights_path: str,
    activation_mode: str,
    adapter_scope: Mapping[str, str],
) -> dict[str, str]:
    """Build stable runtime keys for adapter-backed LoRA activation.

    The base key intentionally excludes adapter identity so multiple adapters
    trained against the same base can share a resident base model. The adapter
    isolation key includes adapter package identity and scope so concurrent
    requests can distinguish adapter state while retaining the shared-base key.
    """
    normalized_activation_mode = activation_mode.strip() or "fused_derived_model"
    base_reuse_key = adapter_base_reuse_key(
        source_model=source_model,
        adapter_scope=adapter_scope,
    )
    isolation_key = adapter_isolation_key(
        base_reuse_key=base_reuse_key,
        adapter_manifest=adapter_manifest,
        adapter_manifest_path=adapter_manifest_path,
        adapter_weights_path=adapter_weights_path,
        adapter_scope=adapter_scope,
    )
    if normalized_activation_mode == "adapter_backed_runtime":
        switch_mode = "base_reuse_adapter_swap"
        sharing_policy = "shared_base_isolated_adapter"
        compatibility_status = "compatible"
    else:
        switch_mode = "full_model_load"
        sharing_policy = "isolated_fused_model"
        compatibility_status = "not_applicable"
    return {
        ADAPTER_RUNTIME_BASE_REUSE_KEY: base_reuse_key,
        ADAPTER_RUNTIME_ISOLATION_KEY: isolation_key,
        ADAPTER_RUNTIME_SWITCH_MODE: switch_mode,
        ADAPTER_RUNTIME_SHARING_POLICY: sharing_policy,
        ADAPTER_RUNTIME_COMPATIBILITY_STATUS: compatibility_status,
    }


def adapter_base_reuse_key(
    *,
    source_model: common_pb2.ModelSpec,
    adapter_scope: Mapping[str, str],
) -> str:
    return _stable_sha256(
        {
            "schema_version": "melix.lora_runtime_base_reuse_key.v1",
            "source_model": {
                "model_id": source_model.model_id,
                "model_path": source_model.model_path,
                "model_kind": source_model.model_kind,
                "revision": source_model.revision,
                "tokenizer_hash": source_model.tokenizer_hash,
                "quant_profile_id": source_model.quant_profile_id,
                "parser_mode": source_model.parser_mode,
                "reasoning_mode": source_model.reasoning_mode,
                "max_context": source_model.max_context,
            },
            "adapter_scope": _scope_payload(adapter_scope),
        }
    )


def adapter_isolation_key(
    *,
    base_reuse_key: str,
    adapter_manifest: Mapping[str, Any],
    adapter_manifest_path: str | Path,
    adapter_weights_path: str,
    adapter_scope: Mapping[str, str],
) -> str:
    return _stable_sha256(
        {
            "schema_version": "melix.lora_runtime_adapter_isolation_key.v1",
            "base_reuse_key": base_reuse_key,
            "adapter": {
                "adapter_set_hash": _str_value(adapter_manifest.get("adapter_set_hash")),
                "adapter_name": _str_value(adapter_manifest.get("adapter_name")),
                "manifest_path": str(adapter_manifest_path),
                "weights_path": adapter_weights_path,
                "source_adapter_job_id": _str_value(adapter_manifest.get("job_id")),
            },
            "adapter_scope": _scope_payload(adapter_scope),
        }
    )


def adapter_runtime_ext_fields(
    manifest: Mapping[str, Any],
) -> dict[str, str]:
    fields: dict[str, str] = {}
    for manifest_key, ext_key in ADAPTER_RUNTIME_EXT_KEY_MAP:
        value = _str_value(manifest.get(manifest_key))
        if value:
            fields[ext_key] = value
    return fields


def build_quantized_lora_manifest_fields(
    *,
    source_model: common_pb2.ModelSpec,
    training_mode: str,
    quantization_mode: str,
    target_modules: list[str] | tuple[str, ...],
) -> dict[str, object]:
    detection = detect_quantized_base(source_model)
    normalized_training_mode = training_mode.strip().lower()
    quantized_base_detected = bool(detection[QUANTIZED_BASE_DETECTED])
    if normalized_training_mode == "qlora":
        qlora_compatibility_status = "compatible" if quantized_base_detected else "incompatible"
    elif quantized_base_detected:
        qlora_compatibility_status = "quantized_base_compatible"
    else:
        qlora_compatibility_status = "not_applicable"

    return {
        QUANTIZED_BASE_DETECTED: quantized_base_detected,
        QUANTIZED_BASE_KIND: detection[QUANTIZED_BASE_KIND],
        QUANTIZATION_PROFILE_ID: detection[QUANTIZATION_PROFILE_ID],
        QUANTIZED_BASE_EVIDENCE_SOURCE: detection[QUANTIZED_BASE_EVIDENCE_SOURCE],
        QLORA_COMPATIBILITY_STATUS: qlora_compatibility_status,
        QUANTIZED_TARGET_MODULE_GUARD: _quantized_target_module_guard_status(
            quantized_base_detected=quantized_base_detected,
            training_mode=normalized_training_mode,
            quantization_mode=quantization_mode,
            target_modules=target_modules,
        ),
    }


def detect_quantized_base(source_model: common_pb2.ModelSpec) -> dict[str, object]:
    profile_id = source_model.quant_profile_id.strip()
    if profile_id:
        return {
            QUANTIZED_BASE_DETECTED: True,
            QUANTIZED_BASE_KIND: _quantized_kind_from_text(profile_id),
            QUANTIZATION_PROFILE_ID: profile_id,
            QUANTIZED_BASE_EVIDENCE_SOURCE: "quant_profile_id",
        }

    for ext_key in (
        "melix.quantization.profile_id",
        "melix.quant_profile_id",
        "quant_profile_id",
        "melix.quantization_mode",
        "quantization_mode",
    ):
        ext_value = source_model.ext.get(ext_key, "").strip()
        if not ext_value:
            continue
        kind = _quantized_kind_from_text(ext_value)
        if kind != "unknown" or ext_value.lower() in {"quantized", "quantized_base"}:
            return {
                QUANTIZED_BASE_DETECTED: True,
                QUANTIZED_BASE_KIND: kind,
                QUANTIZATION_PROFILE_ID: ext_value,
                QUANTIZED_BASE_EVIDENCE_SOURCE: ext_key,
            }

    searchable = " ".join(
        [
            source_model.model_id.lower(),
            source_model.model_path.lower(),
            source_model.revision.lower(),
        ]
    )
    kind = _quantized_kind_from_text(searchable)
    return {
        QUANTIZED_BASE_DETECTED: kind != "unknown",
        QUANTIZED_BASE_KIND: kind,
        QUANTIZATION_PROFILE_ID: "",
        QUANTIZED_BASE_EVIDENCE_SOURCE: "model_identity" if kind != "unknown" else "",
    }


def _scope_payload(adapter_scope: Mapping[str, str]) -> dict[str, str]:
    return {
        "adapter_scope": _str_value(adapter_scope.get("adapter_scope")),
        "training_surface": _str_value(adapter_scope.get("training_surface")),
        "component_model_type": _str_value(adapter_scope.get("component_model_type")),
        "component_family": _str_value(adapter_scope.get("component_family")),
        "component_model_path": _str_value(adapter_scope.get("component_model_path")),
    }


def _stable_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _str_value(raw_value: Any) -> str:
    if raw_value is None:
        return ""
    return str(raw_value).strip()


def _quantized_kind_from_text(raw_value: str) -> str:
    normalized = raw_value.strip().lower()
    for kind in _QUANTIZED_KIND_ORDER:
        if re.search(rf"(?<![a-z0-9]){re.escape(kind)}(?![a-z0-9])", normalized):
            return kind
    return "unknown"


def _quantized_target_module_guard_status(
    *,
    quantized_base_detected: bool,
    training_mode: str,
    quantization_mode: str,
    target_modules: list[str] | tuple[str, ...],
) -> str:
    if training_mode == "qlora" or quantized_base_detected:
        return "accepted" if target_modules else "accepted_no_targets"
    if quantization_mode.strip() == "quantized_base":
        return "accepted"
    return "not_required"
