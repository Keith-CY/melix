from __future__ import annotations

from dataclasses import dataclass
import json
import platform
from pathlib import Path
import subprocess
from typing import Any, Mapping


NATIVE_MTP_ENABLED_EXT_KEY = "melix.native_mtp.enabled"
NATIVE_MTP_DEVICE_POLICY_EXT_KEY = "melix.native_mtp.device_policy"
NATIVE_MTP_RECEIPT_SCHEMA = "melix.native_mtp.capability.v1"
NATIVE_MTP_RECEIPT_JSON_KEY = "melix.native_mtp.receipt_json"
_SYSCTL_TIMEOUT_SECONDS = 5


@dataclass(frozen=True, slots=True)
class NativeMTPHardwareProfile:
    system: str = ""
    machine: str = ""
    chip_family: str = ""
    model_identifier: str = ""


_CACHED_HARDWARE_PROFILE: NativeMTPHardwareProfile | None = None


@dataclass(frozen=True, slots=True)
class _NativeMTPHardwareDecision:
    gate: str
    policy: str
    reason: str
    source: str
    operator_override: str = ""

    @property
    def admitted(self) -> bool:
        return self.gate == "admitted"


@dataclass(frozen=True, slots=True)
class _NativeMTPCapabilitySpec:
    family: str
    model_types: frozenset[str]
    layer_count_keys: tuple[str, ...]
    text_layer_count_keys: tuple[str, ...]
    weight_prefixes: tuple[str, ...]
    weight_substrings: tuple[str, ...]
    cache_shape: str
    patchable: bool
    batch_shape: str = "singleton_only"
    batch_state_policy: str = "singleton_timeline_safe"
    batch_filter_policy: str = "preserve_when_singleton_uid_matches"
    batch_extend_policy: str = "reconcile_then_drop"
    batch_multi_row_policy: str = "multi_row_decode_unsupported"
    source: str = "native_head"
    runtime_scope: str = "text_only_singleton"


_QWEN_NATIVE_MTP_SPEC = _NativeMTPCapabilitySpec(
    family="qwen3_5",
    model_types=frozenset(("qwen3_5", "qwen3_5_text")),
    layer_count_keys=("mtp_num_hidden_layers",),
    text_layer_count_keys=("mtp_num_hidden_layers",),
    weight_prefixes=("language_model.mtp.", "mtp."),
    weight_substrings=(),
    cache_shape="qwen3_5_native_mtp",
    patchable=True,
)
_DEEPSEEK_V3_NEXTN_MTP_SPEC = _NativeMTPCapabilitySpec(
    family="deepseek_v3_nextn",
    model_types=frozenset(("deepseek_v3", "deepseek-v3", "deepseek_v3_text")),
    layer_count_keys=("num_nextn_predict_layers",),
    text_layer_count_keys=("num_nextn_predict_layers",),
    weight_prefixes=(),
    weight_substrings=(".shared_head.", ".eh_proj."),
    cache_shape="deepseek_v3_nextn_native_mtp",
    patchable=False,
)
_NATIVE_MTP_CAPABILITY_SPECS = (
    _QWEN_NATIVE_MTP_SPEC,
    _DEEPSEEK_V3_NEXTN_MTP_SPEC,
)


@dataclass(frozen=True, slots=True)
class NativeMTPCapabilityReceipt:
    schema_version: str
    status: str
    requested_method: str
    resolved_method: str
    mode: str
    source: str
    family: str
    compatible: bool
    weights_present: bool
    weight_count: int
    draft_supported: bool
    effective_depth: int
    depth_source: str
    cache_shape: str
    batch_shape: str
    batch_state_policy: str
    batch_filter_policy: str
    batch_extend_policy: str
    batch_multi_row_policy: str
    hardware_gate: str
    hardware_policy: str
    hardware_policy_reason: str
    hardware_policy_source: str
    operator_override: str
    request_gate: str
    runtime_scope: str
    patch_applied: bool
    draft_loaded: bool
    target_decode_started: bool
    fallback_reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "requested_method": self.requested_method,
            "resolved_method": self.resolved_method,
            "mode": self.mode,
            "source": self.source,
            "family": self.family,
            "compatible": self.compatible,
            "weights_present": self.weights_present,
            "weight_count": self.weight_count,
            "draft_supported": self.draft_supported,
            "effective_depth": self.effective_depth,
            "depth_source": self.depth_source,
            "cache_shape": self.cache_shape,
            "batch_shape": self.batch_shape,
            "batch_state_policy": self.batch_state_policy,
            "batch_filter_policy": self.batch_filter_policy,
            "batch_extend_policy": self.batch_extend_policy,
            "batch_multi_row_policy": self.batch_multi_row_policy,
            "hardware_gate": self.hardware_gate,
            "hardware_policy": self.hardware_policy,
            "hardware_policy_reason": self.hardware_policy_reason,
            "hardware_policy_source": self.hardware_policy_source,
            "operator_override": self.operator_override,
            "request_gate": self.request_gate,
            "runtime_scope": self.runtime_scope,
            "patch_applied": self.patch_applied,
            "draft_loaded": self.draft_loaded,
            "target_decode_started": self.target_decode_started,
            "fallback_reason": self.fallback_reason,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), sort_keys=True)

    def to_flat_metadata(self) -> dict[str, str]:
        return {
            "melix.native_mtp.receipt.schema": self.schema_version,
            "melix.native_mtp.receipt.status": self.status,
            "melix.native_mtp.receipt.mode": self.mode,
            "melix.native_mtp.receipt.fallback_reason": self.fallback_reason,
            "melix.native_mtp.receipt.source": self.source,
            "melix.native_mtp.receipt.family": self.family,
            "melix.native_mtp.receipt.weights_present": _bool_string(self.weights_present),
            "melix.native_mtp.receipt.weight_count": str(self.weight_count),
            "melix.native_mtp.receipt.draft_supported": _bool_string(self.draft_supported),
            "melix.native_mtp.receipt.effective_depth": str(self.effective_depth),
            "melix.native_mtp.receipt.depth_source": self.depth_source,
            "melix.native_mtp.receipt.batch_shape": self.batch_shape,
            "melix.native_mtp.receipt.batch_state_policy": self.batch_state_policy,
            "melix.native_mtp.receipt.batch_filter_policy": self.batch_filter_policy,
            "melix.native_mtp.receipt.batch_extend_policy": self.batch_extend_policy,
            "melix.native_mtp.receipt.batch_multi_row_policy": self.batch_multi_row_policy,
            "melix.native_mtp.receipt.hardware_gate": self.hardware_gate,
            "melix.native_mtp.receipt.hardware_policy": self.hardware_policy,
            "melix.native_mtp.receipt.hardware_policy_reason": self.hardware_policy_reason,
            "melix.native_mtp.receipt.hardware_policy_source": self.hardware_policy_source,
            "melix.native_mtp.receipt.operator_override": self.operator_override,
            "melix.native_mtp.receipt.request_gate": self.request_gate,
            "melix.native_mtp.receipt.runtime_scope": self.runtime_scope,
            "melix.native_mtp.receipt.draft_loaded": _bool_string(self.draft_loaded),
            "melix.native_mtp.receipt.target_decode_started": _bool_string(
                self.target_decode_started
            ),
        }


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
    cache_shape: str = "none"
    batch_state_policy: str = "none"
    batch_filter_policy: str = "none"
    batch_extend_policy: str = "none"
    batch_multi_row_policy: str = "none"
    hardware_policy: str = "auto"
    hardware_policy_reason: str = "unclassified_device"
    hardware_policy_source: str = "auto"
    operator_override: str = ""
    runtime_scope: str = "text_only_singleton"

    def to_metadata(
        self,
        *,
        patch_applied: bool,
        active: bool,
        reason: str | None = None,
    ) -> dict[str, str]:
        final_reason = self._reason(patch_applied=patch_applied, active=active, override=reason)
        receipt = self.to_receipt(
            patch_applied=patch_applied,
            active=active,
            reason=final_reason,
        )
        metadata = {
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
            "melix.native_mtp.batch_state_policy": self.batch_state_policy,
            "melix.native_mtp.batch_filter_policy": self.batch_filter_policy,
            "melix.native_mtp.batch_extend_policy": self.batch_extend_policy,
            "melix.native_mtp.batch_multi_row_policy": self.batch_multi_row_policy,
            "melix.native_mtp.hardware_gate": self.hardware_gate,
            "melix.native_mtp.hardware_policy": self.hardware_policy,
            "melix.native_mtp.hardware_policy_reason": self.hardware_policy_reason,
            "melix.native_mtp.hardware_policy_source": self.hardware_policy_source,
            "melix.native_mtp.operator_override": self.operator_override,
            "melix.native_mtp.resolution": self._resolution(active=active, reason=final_reason),
            "melix.native_mtp.refusal_reason": "" if active else final_reason,
            "melix.native_mtp.receipt.enabled": _bool_string(self.enabled),
            NATIVE_MTP_RECEIPT_JSON_KEY: receipt.to_json(),
        }
        metadata.update(receipt.to_flat_metadata())
        return metadata

    def to_receipt(
        self,
        *,
        patch_applied: bool,
        active: bool,
        reason: str | None = None,
    ) -> NativeMTPCapabilityReceipt:
        final_reason = self._reason(patch_applied=patch_applied, active=active, override=reason)
        return NativeMTPCapabilityReceipt(
            schema_version=NATIVE_MTP_RECEIPT_SCHEMA,
            status=self._receipt_status(active=active, reason=final_reason),
            requested_method="native_mtp" if self.enabled else "none",
            resolved_method="native_mtp" if active else "disabled",
            mode="speculative_decode" if active else "disabled",
            source=self.source,
            family=self.family,
            compatible=self.compatible,
            weights_present=self.weights_present,
            weight_count=self.weight_count,
            draft_supported=bool(self.compatible and self.source == "native_head" and active),
            effective_depth=self.head_count if active else 0,
            depth_source=self.source if active else "none",
            cache_shape=self._cache_shape(),
            batch_shape=self.batch_shape,
            batch_state_policy=self._batch_state_policy(),
            batch_filter_policy=self._batch_filter_policy(),
            batch_extend_policy=self._batch_extend_policy(),
            batch_multi_row_policy=self._batch_multi_row_policy(),
            hardware_gate=self.hardware_gate,
            hardware_policy=self.hardware_policy,
            hardware_policy_reason=self.hardware_policy_reason,
            hardware_policy_source=self.hardware_policy_source,
            operator_override=self.operator_override,
            request_gate=self._request_gate(active=active, reason=final_reason),
            runtime_scope=self.runtime_scope if active else "none",
            patch_applied=bool(patch_applied),
            draft_loaded=bool(active),
            target_decode_started=False,
            fallback_reason="" if active else final_reason,
        )

    def _reason(self, *, patch_applied: bool, active: bool, override: str | None) -> str:
        if override is not None:
            return str(override or "")
        if active:
            return ""
        if self.refusal_reason:
            return self.refusal_reason
        if self.patchable and not patch_applied:
            return "patch_failed"
        return ""

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
        if reason == "device_policy_disabled":
            return "device_policy_disabled"
        if reason == "patch_unsupported":
            return "patch_unsupported"
        if reason in {"unsupported_model", "patch_failed", "patch_error"}:
            return reason
        return "not_admitted"

    def _cache_shape(self) -> str:
        if self.source == "native_head" and self.compatible:
            return self.cache_shape
        return "none"

    def _batch_state_policy(self) -> str:
        if self.compatible and self.batch_shape == "singleton_only":
            return self.batch_state_policy
        return "none"

    def _batch_filter_policy(self) -> str:
        if self.compatible and self.batch_shape == "singleton_only":
            return self.batch_filter_policy
        return "none"

    def _batch_extend_policy(self) -> str:
        if self.compatible and self.batch_shape == "singleton_only":
            return self.batch_extend_policy
        return "none"

    def _batch_multi_row_policy(self) -> str:
        if self.compatible and self.batch_shape == "singleton_only":
            return self.batch_multi_row_policy
        return "none"


def resolve_native_mtp_capability(
    model_path: str | Path,
    *,
    metadata: Mapping[str, str],
    hardware_profile: Any | None = None,
) -> NativeMTPCapabilityDecision:
    model_dir = Path(model_path)
    config_payload = _load_json_payload(model_dir / "config.json")
    model_type = _native_mtp_model_type(config_payload)
    weight_map = _native_mtp_weight_map(model_dir)
    spec, head_count = _resolve_native_mtp_spec(
        model_type=model_type,
        config_payload=config_payload,
    )
    weights_present, weight_count = _native_mtp_weight_presence(weight_map, spec=spec)
    enabled = _truthy_string(metadata.get(NATIVE_MTP_ENABLED_EXT_KEY, ""))
    hardware = _resolve_native_mtp_hardware_policy(
        metadata=metadata,
        hardware_profile=hardware_profile,
    )

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
            hardware_gate=hardware.gate,
            resolution="refused",
            refusal_reason="assistant_sidecar" if enabled else "disabled",
            hardware_policy=hardware.policy,
            hardware_policy_reason=hardware.reason,
            hardware_policy_source=hardware.source,
            operator_override=hardware.operator_override,
            runtime_scope="none",
        )

    if spec is not None:
        refusal_reason = _native_head_refusal_reason(
            enabled=enabled,
            weights_present=weights_present,
            patchable=spec.patchable,
            hardware_admitted=hardware.admitted,
        )
        resolution = (
            "accepted"
            if enabled and weights_present and spec.patchable and hardware.admitted
            else "legacy_only" if not enabled else "refused"
        )
        return NativeMTPCapabilityDecision(
            enabled=enabled,
            compatible=True,
            patchable=spec.patchable,
            weights_present=weights_present,
            weight_count=weight_count,
            family=spec.family,
            source=spec.source,
            head_count=head_count,
            batch_shape=spec.batch_shape,
            hardware_gate=hardware.gate,
            resolution=resolution,
            refusal_reason=refusal_reason,
            cache_shape=spec.cache_shape,
            batch_state_policy=spec.batch_state_policy,
            batch_filter_policy=spec.batch_filter_policy,
            batch_extend_policy=spec.batch_extend_policy,
            batch_multi_row_policy=spec.batch_multi_row_policy,
            hardware_policy=hardware.policy,
            hardware_policy_reason=hardware.reason,
            hardware_policy_source=hardware.source,
            operator_override=hardware.operator_override,
            runtime_scope=spec.runtime_scope,
        )

    head_count = _native_mtp_layer_count(config_payload)
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
        hardware_gate=hardware.gate,
        resolution="refused" if enabled else "legacy_only",
        refusal_reason="unsupported_model" if enabled else "disabled",
        hardware_policy=hardware.policy,
        hardware_policy_reason=hardware.reason,
        hardware_policy_source=hardware.source,
        operator_override=hardware.operator_override,
        runtime_scope="none",
    )


def _load_json_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _native_mtp_model_type(config_payload: Mapping[str, Any]) -> str:
    text_config = config_payload.get("text_config")
    if isinstance(text_config, Mapping):
        value = text_config.get("model_type") or config_payload.get("model_type")
    else:
        value = config_payload.get("model_type")
    return str(value or "").strip().lower()


def _resolve_native_mtp_spec(
    *,
    model_type: str,
    config_payload: Mapping[str, Any],
) -> tuple[_NativeMTPCapabilitySpec | None, int]:
    for spec in _NATIVE_MTP_CAPABILITY_SPECS:
        if model_type not in spec.model_types:
            continue
        layer_count = _native_mtp_layer_count(config_payload, spec=spec)
        if layer_count > 0:
            return spec, layer_count
    return None, _native_mtp_layer_count(config_payload)


def _native_mtp_layer_count(
    config_payload: Mapping[str, Any],
    *,
    spec: _NativeMTPCapabilitySpec | None = None,
) -> int:
    candidates: list[Any] = []
    root_keys: tuple[str, ...]
    text_keys: tuple[str, ...]
    if spec is None:
        root_keys = tuple(
            dict.fromkeys(key for item in _NATIVE_MTP_CAPABILITY_SPECS for key in item.layer_count_keys)
        )
        text_keys = tuple(
            dict.fromkeys(
                key for item in _NATIVE_MTP_CAPABILITY_SPECS for key in item.text_layer_count_keys
            )
        )
    else:
        root_keys = spec.layer_count_keys
        text_keys = spec.text_layer_count_keys
    text_config = config_payload.get("text_config")
    if isinstance(text_config, Mapping):
        candidates.extend(text_config.get(key) for key in text_keys)
    candidates.extend(config_payload.get(key) for key in root_keys)
    for value in candidates:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            continue
    return 0


def _native_mtp_weight_map(model_dir: Path) -> Mapping[Any, Any]:
    index_payload = _load_json_payload(model_dir / "model.safetensors.index.json")
    weight_map = index_payload.get("weight_map")
    if not isinstance(weight_map, Mapping):
        return {}
    return weight_map


def _native_mtp_weight_presence(
    weight_map: Mapping[Any, Any],
    *,
    spec: _NativeMTPCapabilitySpec | None,
) -> tuple[bool, int]:
    count = sum(1 for key in weight_map if _is_native_mtp_weight_key(key, spec=spec))
    return count > 0, count


def _is_native_mtp_weight_key(key: object, *, spec: _NativeMTPCapabilitySpec | None) -> bool:
    key_str = str(key)
    if spec is not None:
        if spec.weight_prefixes and key_str.startswith(spec.weight_prefixes):
            return True
        return bool(spec.weight_substrings and any(part in key_str for part in spec.weight_substrings))
    for candidate in _NATIVE_MTP_CAPABILITY_SPECS:
        if candidate.weight_prefixes and key_str.startswith(candidate.weight_prefixes):
            return True
        if candidate.weight_substrings and any(part in key_str for part in candidate.weight_substrings):
            return True
    return False


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

def _resolve_native_mtp_hardware_policy(
    *,
    metadata: Mapping[str, str],
    hardware_profile: Any | None,
) -> _NativeMTPHardwareDecision:
    policy = _native_mtp_device_policy(metadata)
    if policy == "force_on":
        return _NativeMTPHardwareDecision(
            gate="admitted",
            policy="force_on",
            reason="operator_force_on",
            source="operator",
            operator_override="force_on",
        )
    if policy == "force_off":
        return _NativeMTPHardwareDecision(
            gate="disabled",
            policy="force_off",
            reason="operator_force_off",
            source="operator",
            operator_override="force_off",
        )

    profile = _coerce_hardware_profile(hardware_profile) or _detect_native_mtp_hardware_profile()
    if _is_lower_end_m1_m2(profile):
        return _NativeMTPHardwareDecision(
            gate="disabled",
            policy="auto",
            reason="m1_m2_compute_bound",
            source="auto",
        )
    if _is_high_end_apple_silicon(profile):
        return _NativeMTPHardwareDecision(
            gate="admitted",
            policy="auto",
            reason="supported_apple_silicon",
            source="auto",
        )
    if _is_unclassified_apple_silicon(profile):
        return _NativeMTPHardwareDecision(
            gate="disabled",
            policy="auto",
            reason="unclassified_apple_silicon",
            source="auto",
        )
    return _NativeMTPHardwareDecision(
        gate="admitted",
        policy="auto",
        reason="unclassified_device",
        source="auto",
    )


def _native_mtp_device_policy(metadata: Mapping[str, str]) -> str:
    value = str(
        metadata.get(NATIVE_MTP_DEVICE_POLICY_EXT_KEY)
        or metadata.get("melix.native_mtp.hardware_policy")
        or "auto"
    ).strip().lower()
    if value in {"force_on", "on", "enabled", "always"}:
        return "force_on"
    if value in {"force_off", "off", "disabled", "never"}:
        return "force_off"
    return "auto"


def _coerce_hardware_profile(profile: Any | None) -> NativeMTPHardwareProfile | None:
    if profile is None:
        return None
    return NativeMTPHardwareProfile(
        system=str(getattr(profile, "system", "") or ""),
        machine=str(getattr(profile, "machine", "") or ""),
        chip_family=str(getattr(profile, "chip_family", "") or ""),
        model_identifier=str(getattr(profile, "model_identifier", "") or ""),
    )


def _detect_native_mtp_hardware_profile() -> NativeMTPHardwareProfile:
    global _CACHED_HARDWARE_PROFILE
    if _CACHED_HARDWARE_PROFILE is not None:
        return _CACHED_HARDWARE_PROFILE

    system = platform.system()
    machine = platform.machine()
    if system != "Darwin" or machine not in {"arm64", "aarch64"}:
        _CACHED_HARDWARE_PROFILE = NativeMTPHardwareProfile(system=system, machine=machine)
        return _CACHED_HARDWARE_PROFILE
    _CACHED_HARDWARE_PROFILE = NativeMTPHardwareProfile(
        system=system,
        machine=machine,
        chip_family=_sysctl_string("machdep.cpu.brand_string"),
        model_identifier=_sysctl_string("hw.model"),
    )
    return _CACHED_HARDWARE_PROFILE


def _sysctl_string(name: str) -> str:
    try:
        result = subprocess.run(
            ["sysctl", "-n", name],
            check=False,
            capture_output=True,
            text=True,
            timeout=_SYSCTL_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _is_lower_end_m1_m2(profile: NativeMTPHardwareProfile) -> bool:
    chip = profile.chip_family.lower()
    if not chip:
        return False
    if "m1" not in chip and "m2" not in chip:
        return False
    return "max" not in chip and "ultra" not in chip


def _is_high_end_apple_silicon(profile: NativeMTPHardwareProfile) -> bool:
    chip = profile.chip_family.lower()
    if not chip:
        return False
    if "m3" in chip or "m4" in chip:
        return True
    return ("m1" in chip or "m2" in chip) and ("max" in chip or "ultra" in chip)


def _is_unclassified_apple_silicon(profile: NativeMTPHardwareProfile) -> bool:
    if profile.system != "Darwin":
        return False
    return profile.machine in {"arm64", "aarch64"} and not profile.chip_family


def _native_head_refusal_reason(
    *,
    enabled: bool,
    weights_present: bool,
    patchable: bool,
    hardware_admitted: bool,
) -> str:
    if not enabled:
        return "disabled"
    if not weights_present:
        return "missing_mtp_weights"
    if not patchable:
        return "patch_unsupported"
    if not hardware_admitted:
        return "device_policy_disabled"
    return ""


def _bool_string(value: bool) -> str:
    return "true" if value else "false"
