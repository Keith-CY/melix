from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import os
from pathlib import Path
import stat
from typing import Any

from packages.protocol.python.worker.v1 import common_pb2


DEFAULT_SAFE_SOURCE = "default_safe"
MODEL_SETTINGS_SOURCE = "model_settings"
NOT_APPLICABLE_SOURCE = "not_applicable"
REQUEST_SOURCE = "request"
CONFIG_JSON_AUTO_MAP_SOURCE = "config_json:auto_map"
BLOCK_REASON_CUSTOM_LOADER_REQUIRES_TRUST = "custom_loader_requires_trust_remote_code"
TRUST_APPLICABLE_TEXT_LOADERS = frozenset({"mlx_lm", "mlx_lm_unavailable"})
TRUST_APPLICABLE_TEXT_LOADERS_COMMON = frozenset({"mlx-lm", "mlx_lm", "mlx_lm_unavailable"})
TRUST_APPLICABLE_VLM_LOADERS = frozenset({"mlx_vlm", "python_vlm", "mlx_vlm_unavailable"})
TRUST_APPLICABLE_VLM_LOADERS_COMMON = frozenset(
    {"mlx-vlm", "mlx_vlm", "python_vlm", "mlx_vlm_unavailable"}
)
ROUTE_CLASS_BY_RUNTIME_KIND = {
    "text": common_pb2.WORKER_ROUTE_PYTHON_TEXT_COMPATIBILITY,
    "vlm": common_pb2.WORKER_ROUTE_PYTHON_VLM,
    "ocr": common_pb2.WORKER_ROUTE_PYTHON_OCR,
    "embedding": common_pb2.WORKER_ROUTE_PYTHON_EMBEDDING,
    "rerank": common_pb2.WORKER_ROUTE_PYTHON_RERANK,
    "transcription": common_pb2.WORKER_ROUTE_PYTHON_TRANSCRIPTION,
    "speech": common_pb2.WORKER_ROUTE_PYTHON_SPEECH,
    "image": common_pb2.WORKER_ROUTE_PYTHON_IMAGE,
}


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
    runtime_name = _runtime_name(runtime)
    requested_mode, policy_source = _requested_mode(model_spec, request_policy)
    route_class = _route_class(model_spec, request_policy, runtime_kind)
    loader_family = _loader_family(
        model_spec,
        request_policy,
        runtime_kind,
        runtime_name=runtime_name,
    )

    if not _is_trust_applicable(runtime_kind, loader_family, runtime_name, runtime):
        return _not_applicable_policy(requested_mode, route_class, loader_family)

    policy = common_pb2.ModelLoadTrustPolicy()
    policy.requested_mode = requested_mode
    policy.policy_source = _non_empty(
        getattr(request_policy, "policy_source", "") if request_policy is not None else "",
        policy_source,
    )
    policy.route_class = route_class
    policy.loader_family = loader_family
    policy.effective_mode = requested_mode
    custom_loader_required, detection_source = _detect_custom_loader_requirement(model_spec)
    policy.custom_loader_required = custom_loader_required
    policy.custom_loader_detection_source = detection_source
    if custom_loader_required and requested_mode != common_pb2.MODEL_LOAD_TRUST_TRUST_REMOTE_CODE:
        policy.block_reason = BLOCK_REASON_CUSTOM_LOADER_REQUIRES_TRUST
        raise ModelLoadTrustRejection(policy)
    return policy


def default_not_applicable_load_trust_policy(
    *,
    runtime_kind: str,
    runtime: Any,
) -> common_pb2.ModelLoadTrustPolicy | None:
    runtime_name = _runtime_name(runtime)
    if not runtime_name:
        return None
    if runtime_kind != "text":
        return None
    if _is_trust_applicable(runtime_kind, runtime_name, runtime_name, runtime):
        return None
    return _not_applicable_policy(
        common_pb2.MODEL_LOAD_TRUST_DEFAULT_SAFE,
        common_pb2.WORKER_ROUTE_PYTHON_TEXT_COMPATIBILITY,
        runtime_name,
    )


@lru_cache(maxsize=128)
def _not_applicable_policy(
    requested_mode: int,
    route_class: int,
    loader_family: str,
) -> common_pb2.ModelLoadTrustPolicy:
    return common_pb2.ModelLoadTrustPolicy(
        requested_mode=requested_mode,
        effective_mode=common_pb2.MODEL_LOAD_TRUST_NOT_APPLICABLE,
        policy_source=NOT_APPLICABLE_SOURCE,
        custom_loader_detection_source=NOT_APPLICABLE_SOURCE,
        route_class=route_class,
        loader_family=loader_family,
    )


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
    return ROUTE_CLASS_BY_RUNTIME_KIND.get(runtime_kind, common_pb2.WORKER_ROUTE_CLASS_UNSPECIFIED)


def _loader_family(
    model_spec: common_pb2.ModelSpec,
    request_policy: common_pb2.ModelLoadTrustPolicy | None,
    runtime_kind: str,
    *,
    runtime_name: str,
) -> str:
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


def _is_trust_applicable(
    runtime_kind: str,
    loader_family: str,
    runtime_name: str,
    runtime: Any,
) -> bool:
    if runtime is None:
        return False
    supports_trust_policy = getattr(runtime, "supports_trust_policy", None)
    if supports_trust_policy is not None:
        return bool(supports_trust_policy)
    if runtime_kind == "text":
        if (
            loader_family in TRUST_APPLICABLE_TEXT_LOADERS_COMMON
            or runtime_name in TRUST_APPLICABLE_TEXT_LOADERS_COMMON
        ):
            return True
    elif runtime_kind == "vlm":
        if runtime_name.startswith("deterministic"):
            return False
        if (
            loader_family in TRUST_APPLICABLE_VLM_LOADERS_COMMON
            or runtime_name in TRUST_APPLICABLE_VLM_LOADERS_COMMON
        ):
            return True
    normalized_runtime_name = runtime_name.strip().lower().replace("-", "_")
    family = loader_family.strip().lower().replace("-", "_")
    if runtime_kind == "text":
        return family in TRUST_APPLICABLE_TEXT_LOADERS or normalized_runtime_name in TRUST_APPLICABLE_TEXT_LOADERS
    if runtime_kind == "vlm":
        if normalized_runtime_name.startswith("deterministic"):
            return False
        return family in TRUST_APPLICABLE_VLM_LOADERS or normalized_runtime_name in TRUST_APPLICABLE_VLM_LOADERS
    return False


def _runtime_name(runtime: Any) -> str:
    return str(getattr(runtime, "runtime_name", "") or "") if runtime is not None else ""


def _detect_custom_loader_requirement(model_spec: common_pb2.ModelSpec) -> tuple[bool, str]:
    config_path = _model_config_path(model_spec)
    if config_path is None:
        return False, "config_json:absent"
    config_path_text, stat_path = config_path
    try:
        config_stat = os.stat(stat_path)
        if not stat.S_ISREG(config_stat.st_mode):
            return False, "config_json:absent"
    except OSError:
        return False, "config_json:absent"
    return _detect_custom_loader_requirement_for_stat(
        config_path_text,
        config_stat.st_mtime_ns,
        config_stat.st_size,
    )


def _auto_map_has_custom_loader(auto_map: dict[Any, Any]) -> bool:
    for value in auto_map.values():
        if isinstance(value, str):
            if value and not value.isspace():
                return True
        elif value is not None and str(value).strip():
            return True
    return False


def _read_model_config(model_spec: common_pb2.ModelSpec) -> dict[str, Any] | None:
    model_path = str(model_spec.model_path or "").strip()
    if not model_path:
        return None
    if model_path[0] == "~":
        config_path = Path(model_path).expanduser() / "config.json"
        config_path_text = str(config_path)
        stat_path: str | os.PathLike[str] = config_path
    else:
        separator = "" if model_path[-1] == os.sep else os.sep
        config_path_text = f"{model_path}{separator}config.json"
        stat_path = config_path_text
    try:
        config_stat = os.stat(stat_path)
        if not stat.S_ISREG(config_stat.st_mode):
            return None
    except OSError:
        return None
    payload = _read_model_config_for_stat(
        config_path_text,
        config_stat.st_mtime_ns,
        config_stat.st_size,
    )
    return payload if isinstance(payload, dict) else None


def _model_config_path(model_spec: common_pb2.ModelSpec) -> tuple[str, str | os.PathLike[str]] | None:
    model_path = str(model_spec.model_path or "").strip()
    if not model_path:
        return None
    if model_path[0] == "~":
        config_path = Path(model_path).expanduser() / "config.json"
        return str(config_path), config_path
    separator = "" if model_path[-1] == os.sep else os.sep
    config_path_text = f"{model_path}{separator}config.json"
    return config_path_text, config_path_text


@lru_cache(maxsize=128)
def _detect_custom_loader_requirement_for_stat(
    config_path: str,
    mtime_ns: int,
    size: int,
) -> tuple[bool, str]:
    config = _read_model_config_for_stat(config_path, mtime_ns, size)
    if not config:
        return False, "config_json:absent"
    auto_map = config.get("auto_map")
    if isinstance(auto_map, dict) and _auto_map_has_custom_loader(auto_map):
        return True, CONFIG_JSON_AUTO_MAP_SOURCE
    return False, "config_json"


@lru_cache(maxsize=128)
def _read_model_config_for_stat(
    config_path: str,
    mtime_ns: int,
    size: int,
) -> dict[str, Any] | None:
    _ = (mtime_ns, size)
    try:
        with open(config_path, "rb") as handle:
            payload = json.loads(handle.read())
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _mode_name(mode: int) -> str:
    return common_pb2.ModelLoadTrustMode.Name(mode)


def _route_name(route_class: int) -> str:
    return common_pb2.WorkerRouteClass.Name(route_class)


def _non_empty(value: str, fallback: str) -> str:
    return value if value and not value.isspace() else fallback
