from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_ops.quantization_metadata import EXPLICIT_QUANTIZED_PROFILE_IDS


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

_AUXILIARY_MODULE_PATTERNS = (
    "modeling_*.py",
    "configuration_*.py",
    "tokenization_*.py",
    "processing_*.py",
)
_AUXILIARY_MODULE_PREFIXES = tuple(
    pattern.removesuffix("*.py") for pattern in _AUXILIARY_MODULE_PATTERNS
)
_AUXILIARY_MODULE_PREFIX_CHARS = frozenset(
    prefix[0] for prefix in _AUXILIARY_MODULE_PREFIXES
)
_PROCESSOR_RESUME_FILENAMES = (
    ("processor_config.json", "processor_config"),
    ("preprocessor_config.json", "preprocessor_config"),
    ("tokenizer_config.json", "tokenizer_only"),
)

_QUANTIZED_KIND_ORDER = ("4bit", "8bit", "q4", "q8", "optiq")
_QUANTIZED_KIND_PATTERNS = tuple(
    (kind, re.compile(rf"(?<![a-z0-9]){re.escape(kind)}(?![a-z0-9])"))
    for kind in _QUANTIZED_KIND_ORDER
)


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


def build_lora_canary_receipt_fields(
    *,
    source_model: common_pb2.ModelSpec,
    adapter_output_dir: str | Path,
    adapter_config_path: str | Path,
    weights_path: str | Path,
    training_metrics: Any,
) -> dict[str, object]:
    base_model_dir = Path(source_model.model_path).expanduser()
    adapter_dir = Path(adapter_output_dir)
    adapter_config = _load_json_mapping(Path(adapter_config_path))
    tokenizer_config_path = base_model_dir / "tokenizer_config.json"
    source_tokenizer_config = _load_json_mapping(tokenizer_config_path)
    saved_tokenizer_config = _saved_tokenizer_config(adapter_config, adapter_dir)
    source_eos_token = _str_value(source_tokenizer_config.get("eos_token"))
    saved_eos_token = _str_value(saved_tokenizer_config.get("eos_token"))
    base_config_present = (base_model_dir / "config.json").is_file()
    source_tokenizer_present = tokenizer_config_path.is_file()
    processor_resume_mode = _processor_resume_mode(base_model_dir)
    aux_modules_restored = _aux_modules_restored(base_model_dir)
    merge_export_canary_failures: list[str] = []
    if not base_config_present:
        merge_export_canary_failures.append("missing_base_config")
    if not source_tokenizer_present:
        merge_export_canary_failures.append("missing_tokenizer_config")
    elif not source_eos_token:
        merge_export_canary_failures.append("missing_source_eos_token")
    if not Path(weights_path).is_file():
        merge_export_canary_failures.append("missing_adapter_weights")
    if saved_tokenizer_config and not saved_eos_token:
        merge_export_canary_failures.append("missing_saved_eos_token")
    if source_eos_token and saved_eos_token and source_eos_token != saved_eos_token:
        merge_export_canary_failures.append("eos_token_mismatch")
    if not aux_modules_restored:
        merge_export_canary_failures.append("missing_auxiliary_modules")

    callback_api_drift_result = "pass"
    callback_arity = _optional_int(adapter_config.get("callback_arity"))
    expected_callback_arity = _optional_int(adapter_config.get("expected_callback_arity"))
    if (
        callback_arity is not None
        and expected_callback_arity is not None
        and callback_arity != expected_callback_arity
    ):
        callback_api_drift_result = "fail:callback_arity_mismatch"

    return {
        "source_eos_token": source_eos_token,
        "saved_eos_token": saved_eos_token,
        "tokenizer_config_path": str(tokenizer_config_path) if source_tokenizer_present else "",
        "base_config_present": base_config_present,
        "processor_resume_mode": processor_resume_mode,
        "aux_modules_restored": aux_modules_restored,
        "merge_export_canary_result": _canary_result(merge_export_canary_failures),
        "callback_api_drift_result": callback_api_drift_result,
        "completion_loss": _optional_float(
            getattr(training_metrics, "completion_loss", None),
            adapter_config.get("completion_loss"),
            getattr(training_metrics, "loss_final", None),
        ),
        "round_trip_passed": bool(
            getattr(training_metrics, "round_trip_passed", False)
            or adapter_config.get("round_trip_passed", False)
        ),
        "grad_norm": _optional_float(
            getattr(training_metrics, "grad_norm", None),
            adapter_config.get("grad_norm"),
        )
        or 0.0,
    }


def detect_quantized_base(source_model: common_pb2.ModelSpec) -> dict[str, object]:
    profile_id = source_model.quant_profile_id.strip()
    if profile_id:
        kind = _quantized_kind_from_text(profile_id)
        if kind != "unknown" or profile_id.lower() in EXPLICIT_QUANTIZED_PROFILE_IDS:
            return {
                QUANTIZED_BASE_DETECTED: True,
                QUANTIZED_BASE_KIND: kind,
                QUANTIZATION_PROFILE_ID: profile_id,
                QUANTIZED_BASE_EVIDENCE_SOURCE: "quant_profile_id",
            }
        return _not_quantized_detection(quantization_profile_id=profile_id)

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
        if kind != "unknown" or ext_value.lower() in EXPLICIT_QUANTIZED_PROFILE_IDS:
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


def _saved_tokenizer_config(
    adapter_config: Mapping[str, Any],
    adapter_dir: Path,
) -> Mapping[str, Any]:
    embedded = adapter_config.get("tokenizer_config")
    if isinstance(embedded, Mapping):
        return embedded
    saved_path = adapter_dir / "tokenizer_config.json"
    return _load_json_mapping(saved_path)


def _processor_resume_mode(base_model_dir: Path) -> str:
    base_model_path = os.fspath(base_model_dir)
    join = os.path.join
    isfile = os.path.isfile
    for filename, resume_mode in _PROCESSOR_RESUME_FILENAMES:
        if isfile(join(base_model_path, filename)):
            return resume_mode
    return "missing"


def _aux_modules_restored(base_model_dir: Path) -> bool:
    auxiliary_prefixes = _AUXILIARY_MODULE_PREFIXES
    auxiliary_prefix_chars = _AUXILIARY_MODULE_PREFIX_CHARS
    scandir = os.scandir
    try:
        with scandir(base_model_dir) as entries:
            for entry in entries:
                name = entry.name
                if (
                    name[0] in auxiliary_prefix_chars
                    and name.endswith(".py")
                    and name.startswith(auxiliary_prefixes)
                ):
                    return True
    except OSError:
        return False
    return False


def _canary_result(failures: list[str]) -> str:
    return "pass" if not failures else "fail:" + ",".join(failures)


def _load_json_mapping(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, Mapping) else {}


def _optional_int(raw_value: Any) -> int | None:
    if raw_value is None:
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _optional_float(*raw_values: Any) -> float | None:
    for raw_value in raw_values:
        if raw_value is None:
            continue
        try:
            return float(raw_value)
        except (TypeError, ValueError):
            continue
    return None


def _not_quantized_detection(*, quantization_profile_id: str = "") -> dict[str, object]:
    return {
        QUANTIZED_BASE_DETECTED: False,
        QUANTIZED_BASE_KIND: "unknown",
        QUANTIZATION_PROFILE_ID: quantization_profile_id,
        QUANTIZED_BASE_EVIDENCE_SOURCE: "",
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
    # The boundary regex already treats leading/trailing whitespace as a
    # non-alphanumeric delimiter, so avoid an extra full-string strip in this
    # hot parser loop.
    normalized = raw_value.lower()
    for kind, pattern in _QUANTIZED_KIND_PATTERNS:
        if kind in normalized and pattern.search(normalized):
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
