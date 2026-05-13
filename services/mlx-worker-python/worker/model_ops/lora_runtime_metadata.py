from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from packages.protocol.python.worker.v1 import common_pb2


ADAPTER_RUNTIME_BASE_REUSE_KEY = "adapter_runtime.base_reuse_key"
ADAPTER_RUNTIME_ISOLATION_KEY = "adapter_runtime.adapter_isolation_key"
ADAPTER_RUNTIME_SWITCH_MODE = "adapter_runtime.switch_mode"
ADAPTER_RUNTIME_SHARING_POLICY = "adapter_runtime.sharing_policy"
ADAPTER_RUNTIME_COMPATIBILITY_STATUS = "adapter_runtime.compatibility_status"


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
