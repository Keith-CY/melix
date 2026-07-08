from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping


NATIVE_MTP_ENABLED_EXT_KEY = "melix.native_mtp.enabled"
NATIVE_MTP_RECEIPT_SCHEMA = "melix.native_mtp.capability.v1"
_QWEN_NATIVE_MTP_MODEL_TYPES = frozenset(("qwen3_5", "qwen3_5_text"))
_MTP_WEIGHT_PREFIXES = ("language_model.mtp.", "mtp.")


@dataclass(frozen=True, slots=True)
class NativeMTPCapabilityDecision:
    enabled: bool
    compatible: bool
    patchable: bool
    weights_present: bool
    weight_count: int
    family: str
    source: str
    head_count: int
    batch_shape: str
    hardware_gate: str
    resolution: str
    refusal_reason: str

    def to_metadata(
        self,
        *,
        patch_applied: bool,
        active: bool,
        reason: str | None = None,
    ) -> dict[str, str]:
        final_reason = self._reason(patch_applied=patch_applied, active=active, override=reason)
        receipt_status = self._receipt_status(active=active, reason=final_reason)
        receipt_mode = "speculative_decode" if active else "disabled"
        draft_supported = bool(self.compatible and self.source == "native_head")
        return {
            "melix.native_mtp.enabled": _bool_string(self.enabled),
            "melix.native_mtp.compatible": _bool_string(self.compatible),
            "melix.native_mtp.weights_present": _bool_string(self.weights_present),
            "melix.native_mtp.weight_count": str(self.weight_count),
            "melix.native_mtp.patch_applied": _bool_string(patch_applied),
            "melix.native_mtp.active": _bool_string(active),
            "melix.native_mtp.reason": final_reason,
            "melix.native_mtp.family": self.family,
            "melix.native_mtp.source": self.source,
            "melix.native_mtp.head_count": str(self.head_count),
            "melix.native_mtp.batch_shape": self.batch_shape,
            "melix.native_mtp.hardware_gate": self.hardware_gate,
            "melix.native_mtp.resolution": self._resolution(active=active, reason=final_reason),
            "melix.native_mtp.refusal_reason": "" if active else final_reason,
            "melix.native_mtp.receipt.schema": NATIVE_MTP_RECEIPT_SCHEMA,
            "melix.native_mtp.receipt.enabled": _bool_string(self.enabled),
            "melix.native_mtp.receipt.status": receipt_status,
            "melix.native_mtp.receipt.mode": receipt_mode,
            "melix.native_mtp.receipt.fallback_reason": "" if active else final_reason,
            "melix.native_mtp.receipt.source": self.source,
            "melix.native_mtp.receipt.family": self.family,
            "melix.native_mtp.receipt.weights_present": _bool_string(self.weights_present),
            "melix.native_mtp.receipt.weight_count": str(self.weight_count),
            "melix.native_mtp.receipt.draft_supported": _bool_string(draft_supported and active),
            "melix.native_mtp.receipt.effective_depth": str(self.head_count if active else 0),
            "melix.native_mtp.receipt.depth_source": self.source if active else "none",
            "melix.native_mtp.receipt.batch_shape": self.batch_shape,
            "melix.native_mtp.receipt.hardware_gate": self.hardware_gate,
            "melix.native_mtp.receipt.request_gate": self._request_gate(active=active, reason=final_reason),
            "melix.native_mtp.receipt.runtime_scope": "text_only_singleton" if active else "none",
            "melix.native_mtp.receipt.draft_loaded": _bool_string(active),
            "melix.native_mtp.receipt.target_decode_started": "false",
        }

    def _reason(self, *, patch_applied: bool, active: bool, override: str | None) -> str:
        if override is not None:
            return str(override or "")
        if active:
            return ""
        if self.patchable and not patch_applied:
            return "patch_failed"
        return self.refusal_reason

    def _resolution(self, *, active: bool, reason: str) -> str:
        if active:
            return "accepted"
        if not self.enabled and self.compatible:
            return "legacy_only"
        if reason:
            return "refused"
        return self.resolution

    def _receipt_status(self, *, active: bool, reason: str) -> str:
        if active:
            return "admitted"
        if not self.enabled and self.compatible:
            return "not_requested"
        if reason:
            return "refused"
        return "fallback"

    def _request_gate(self, *, active: bool, reason: str) -> str:
        if active:
            return "native_mtp_enabled"
        if not self.enabled:
            return "operator_disabled"
        if reason == "assistant_sidecar":
            return "assistant_sidecar_refused"
        if reason == "missing_mtp_weights":
            return "missing_native_head_weights"
        if reason in {"unsupported_model", "patch_failed", "patch_error"}:
            return reason
        return "not_admitted"


def resolve_native_mtp_capability(
    model_path: str | Path,
    *,
    metadata: Mapping[str, str],
) -> NativeMTPCapabilityDecision:
    model_dir = Path(model_path)
    config_payload = _load_json_payload(model_dir / "config.json")
    model_type = _native_mtp_model_type(config_payload)
    head_count = _native_mtp_layer_count(config_payload)
    weights_present, weight_count = _native_mtp_weight_presence(model_dir)
    enabled = _truthy_string(metadata.get(NATIVE_MTP_ENABLED_EXT_KEY, ""))

    if _is_assistant_sidecar(metadata=metadata, config_payload=config_payload, model_type=model_type):
        return NativeMTPCapabilityDecision(
            enabled=enabled,
            compatible=False,
            patchable=False,
            weights_present=weights_present,
            weight_count=weight_count,
            family=_sidecar_family(metadata=metadata, model_type=model_type),
            source="assistant_sidecar",
            head_count=head_count,
            batch_shape="unsupported",
            hardware_gate="not_evaluated",
            resolution="refused",
            refusal_reason="assistant_sidecar" if enabled else "disabled",
        )

    compatible = model_type in _QWEN_NATIVE_MTP_MODEL_TYPES and head_count > 0
    if compatible:
        refusal_reason = _native_head_refusal_reason(enabled=enabled, weights_present=weights_present)
        return NativeMTPCapabilityDecision(
            enabled=enabled,
            compatible=True,
            patchable=True,
            weights_present=weights_present,
            weight_count=weight_count,
            family="qwen3_5",
            source="native_head",
            head_count=head_count,
            batch_shape="singleton_only",
            hardware_gate="not_evaluated",
            resolution="accepted" if enabled and weights_present else "legacy_only" if not enabled else "refused",
            refusal_reason=refusal_reason,
        )

    return NativeMTPCapabilityDecision(
        enabled=enabled,
        compatible=False,
        patchable=False,
        weights_present=weights_present,
        weight_count=weight_count,
        family=model_type,
        source="none",
        head_count=head_count,
        batch_shape="unsupported",
        hardware_gate="not_evaluated",
        resolution="refused" if enabled else "legacy_only",
        refusal_reason="unsupported_model" if enabled else "disabled",
    )


def _load_json_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _native_mtp_model_type(config_payload: Mapping[str, Any]) -> str:
    text_config = config_payload.get("text_config")
    if isinstance(text_config, Mapping):
        value = text_config.get("model_type") or config_payload.get("model_type")
    else:
        value = config_payload.get("model_type")
    return str(value or "").strip().lower()


def _native_mtp_layer_count(config_payload: Mapping[str, Any]) -> int:
    candidates: list[Any] = []
    text_config = config_payload.get("text_config")
    if isinstance(text_config, Mapping):
        candidates.append(text_config.get("mtp_num_hidden_layers"))
    candidates.append(config_payload.get("mtp_num_hidden_layers"))
    for value in candidates:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            continue
    return 0


def _native_mtp_weight_presence(model_dir: Path) -> tuple[bool, int]:
    index_payload = _load_json_payload(model_dir / "model.safetensors.index.json")
    weight_map = index_payload.get("weight_map")
    if not isinstance(weight_map, Mapping):
        return False, 0
    count = sum(1 for key in weight_map if str(key).startswith(_MTP_WEIGHT_PREFIXES))
    return count > 0, count


def _truthy_string(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _is_assistant_sidecar(
    *,
    metadata: Mapping[str, str],
    config_payload: Mapping[str, Any],
    model_type: str,
) -> bool:
    role = str(metadata.get("melix.speculative.role", "") or "").strip().lower()
    kind = str(metadata.get("melix.speculative.kind", "") or "").strip().lower()
    if role == "assistant" and kind == "mtp":
        return True
    if role == "assistant" and _has_mtp_shape(config_payload):
        return True
    if kind == "mtp" and "assistant" in model_type:
        return True
    return "assistant" in model_type and _has_mtp_shape(config_payload)


def _has_mtp_shape(config_payload: Mapping[str, Any]) -> bool:
    if _native_mtp_layer_count(config_payload) > 0:
        return True
    architectures = config_payload.get("architectures")
    if isinstance(architectures, list):
        return any("mtp" in str(value).lower() for value in architectures)
    return False


def _sidecar_family(*, metadata: Mapping[str, str], model_type: str) -> str:
    target_family = str(metadata.get("melix.speculative.target_family", "") or "").strip().lower()
    return target_family or model_type


def _native_head_refusal_reason(*, enabled: bool, weights_present: bool) -> str:
    if not enabled:
        return "disabled"
    if not weights_present:
        return "missing_mtp_weights"
    return ""


def _bool_string(value: bool) -> str:
    return "true" if value else "false"
