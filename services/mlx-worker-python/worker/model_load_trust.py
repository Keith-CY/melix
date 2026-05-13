from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from packages.protocol.python.worker.v1 import common_pb2


DEFAULT_SAFE_SOURCE = "default_safe"
MODEL_SETTINGS_SOURCE = "model_settings"
NOT_APPLICABLE_SOURCE = "not_applicable"
REQUEST_SOURCE = "request"
CONFIG_JSON_AUTO_MAP_SOURCE = "config_json:auto_map"
BLOCK_REASON_CUSTOM_LOADER_REQUIRES_TRUST = "custom_loader_requires_trust_remote_code"


@dataclass(frozen=True)
class ModelLoadTrustRejection(Exception):
    policy: common_pb2.ModelLoadTrustPolicy

    def __str__(self) -> str:
        return "Custom loader requires an explicit trust_remote_code opt-in."

    @property
    def details(self) -> dict[str, str]:
        return {
            "requested_mode": _mode_name(self.policy.requested_mode),
            "effective_mode": _mode_name(self.policy.effective_mode),
            "policy_source": self.policy.policy_source,
            "custom_loader_detection_source": self.policy.custom_loader_detection_source,
            "block_reason": self.policy.block_reason,
            "route_class": _route_name(self.policy.route_class),
            "loader_family": self.policy.loader_family,
        }


def resolve_model_load_trust_policy(
    model_spec: common_pb2.ModelSpec,
    *,
    request_policy: common_pb2.ModelLoadTrustPolicy | None,
    runtime_kind: str,
    runtime: Any,
) -> common_pb2.ModelLoadTrustPolicy:
    policy = common_pb2.ModelLoadTrustPolicy()
    requested_mode, policy_source = _requested_mode(model_spec, request_policy)
    policy.requested_mode = requested_mode
    policy.policy_source = _non_empty(
        getattr(request_policy, "policy_source", "") if request_policy is not None else "",
        policy_source,
    )
    policy.route_class = _route_class(model_spec, request_policy, runtime_kind)
    policy.loader_family = _loader_family(model_spec, request_policy, runtime_kind, runtime)

    if not _is_trust_applicable(runtime_kind, policy.loader_family, runtime):
        policy.effective_mode = common_pb2.MODEL_LOAD_TRUST_NOT_APPLICABLE
        policy.policy_source = NOT_APPLICABLE_SOURCE
        policy.custom_loader_detection_source = NOT_APPLICABLE_SOURCE
        return policy

    policy.effective_mode = requested_mode
    custom_loader_required, detection_source = _detect_custom_loader_requirement(model_spec)
    policy.custom_loader_required = custom_loader_required
    policy.custom_loader_detection_source = detection_source
    if custom_loader_required and requested_mode != common_pb2.MODEL_LOAD_TRUST_TRUST_REMOTE_CODE:
        policy.block_reason = BLOCK_REASON_CUSTOM_LOADER_REQUIRES_TRUST
        raise ModelLoadTrustRejection(policy)
    return policy


def load_kwargs_for_policy(policy: common_pb2.ModelLoadTrustPolicy) -> dict[str, Any]:
    if policy.effective_mode != common_pb2.MODEL_LOAD_TRUST_TRUST_REMOTE_CODE:
        return {}
    return {"trust_remote_code": True}


def _requested_mode(
    model_spec: common_pb2.ModelSpec,
    request_policy: common_pb2.ModelLoadTrustPolicy | None,
) -> tuple[int, str]:
    if request_policy is not None and request_policy.requested_mode in {
        common_pb2.MODEL_LOAD_TRUST_DEFAULT_SAFE,
        common_pb2.MODEL_LOAD_TRUST_TRUST_REMOTE_CODE,
    }:
        return request_policy.requested_mode, REQUEST_SOURCE
    if model_spec.HasField("settings") and model_spec.settings.load_trust_mode in {
        common_pb2.MODEL_LOAD_TRUST_DEFAULT_SAFE,
        common_pb2.MODEL_LOAD_TRUST_TRUST_REMOTE_CODE,
    }:
        return model_spec.settings.load_trust_mode, MODEL_SETTINGS_SOURCE
    return common_pb2.MODEL_LOAD_TRUST_DEFAULT_SAFE, DEFAULT_SAFE_SOURCE


def _route_class(
    model_spec: common_pb2.ModelSpec,
    request_policy: common_pb2.ModelLoadTrustPolicy | None,
    runtime_kind: str,
) -> int:
    if request_policy is not None and request_policy.route_class != common_pb2.WORKER_ROUTE_CLASS_UNSPECIFIED:
        return request_policy.route_class
    if model_spec.route_class != common_pb2.WORKER_ROUTE_CLASS_UNSPECIFIED:
        return model_spec.route_class
    return {
        "text": common_pb2.WORKER_ROUTE_PYTHON_TEXT_COMPATIBILITY,
        "vlm": common_pb2.WORKER_ROUTE_PYTHON_VLM,
        "ocr": common_pb2.WORKER_ROUTE_PYTHON_OCR,
        "embedding": common_pb2.WORKER_ROUTE_PYTHON_EMBEDDING,
        "rerank": common_pb2.WORKER_ROUTE_PYTHON_RERANK,
        "transcription": common_pb2.WORKER_ROUTE_PYTHON_TRANSCRIPTION,
        "speech": common_pb2.WORKER_ROUTE_PYTHON_SPEECH,
        "image": common_pb2.WORKER_ROUTE_PYTHON_IMAGE,
    }.get(runtime_kind, common_pb2.WORKER_ROUTE_CLASS_UNSPECIFIED)


def _loader_family(
    model_spec: common_pb2.ModelSpec,
    request_policy: common_pb2.ModelLoadTrustPolicy | None,
    runtime_kind: str,
    runtime: Any,
) -> str:
    runtime_name = str(getattr(runtime, "runtime_name", "") or "") if runtime is not None else ""
    requested_family = (
        str(getattr(request_policy, "loader_family", "") or "").strip()
        if request_policy is not None
        else ""
    )
    if requested_family:
        return requested_family
    if runtime_kind == "vlm":
        return model_spec.ext.get("melix.vlm.backend_id", "").strip() or str(
            runtime_name or "mlx_vlm"
        )
    if runtime_kind == "text":
        return runtime_name or "mlx-lm"
    return runtime_name or runtime_kind


def _is_trust_applicable(runtime_kind: str, loader_family: str, runtime: Any) -> bool:
    if runtime is None:
        return False
    runtime_name = str(getattr(runtime, "runtime_name", "") or "").strip().lower()
    family = loader_family.strip().lower().replace("-", "_")
    if runtime_kind == "text":
        return True
    if runtime_kind == "vlm":
        if runtime_name.startswith("deterministic"):
            return False
        return (
            family in {"mlx_vlm", "python_vlm"}
            or runtime_name in {"mlx_vlm", "mlx-vlm", "mlx-vlm-unavailable"}
            or runtime.__class__.__name__ == "MLXVLMRuntime"
        )
    return False


def _detect_custom_loader_requirement(model_spec: common_pb2.ModelSpec) -> tuple[bool, str]:
    config = _read_model_config(model_spec)
    if not config:
        return False, "config_json:absent"
    auto_map = config.get("auto_map")
    if isinstance(auto_map, dict) and any(str(value or "").strip() for value in auto_map.values()):
        return True, CONFIG_JSON_AUTO_MAP_SOURCE
    return False, "config_json"


def _read_model_config(model_spec: common_pb2.ModelSpec) -> dict[str, Any] | None:
    model_path = str(getattr(model_spec, "model_path", "") or "").strip()
    if not model_path:
        return None
    config_path = Path(model_path).expanduser() / "config.json"
    try:
        if not config_path.is_file():
            return None
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _mode_name(mode: int) -> str:
    return common_pb2.ModelLoadTrustMode.Name(mode)


def _route_name(route_class: int) -> str:
    return common_pb2.WorkerRouteClass.Name(route_class)


def _non_empty(value: str, fallback: str) -> str:
    return value if value.strip() else fallback
