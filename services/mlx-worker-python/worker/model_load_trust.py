from __future__ import annotations

from builtins import open as _OPEN
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
CONFIG_JSON_SOURCE = "config_json"
CONFIG_JSON_ABSENT_SOURCE = "config_json:absent"
CONFIG_JSON_AUTO_MAP_SOURCE = "config_json:auto_map"
BLOCK_REASON_CUSTOM_LOADER_REQUIRES_TRUST = "custom_loader_requires_trust_remote_code"
CONFIG_JSON_DETECTION = (False, CONFIG_JSON_SOURCE)
CONFIG_JSON_ABSENT_DETECTION = (False, CONFIG_JSON_ABSENT_SOURCE)
CONFIG_JSON_AUTO_MAP_DETECTION = (True, CONFIG_JSON_AUTO_MAP_SOURCE)
MODEL_LOAD_TRUST_DEFAULT_SAFE = common_pb2.MODEL_LOAD_TRUST_DEFAULT_SAFE
MODEL_LOAD_TRUST_TRUST_REMOTE_CODE = common_pb2.MODEL_LOAD_TRUST_TRUST_REMOTE_CODE
MODEL_LOAD_TRUST_NOT_APPLICABLE = common_pb2.MODEL_LOAD_TRUST_NOT_APPLICABLE
MODEL_LOAD_TRUST_POLICY = common_pb2.ModelLoadTrustPolicy
WORKER_ROUTE_CLASS_UNSPECIFIED = common_pb2.WORKER_ROUTE_CLASS_UNSPECIFIED
WORKER_ROUTE_PYTHON_TEXT_COMPATIBILITY = common_pb2.WORKER_ROUTE_PYTHON_TEXT_COMPATIBILITY
_JSON_LOADS = json.loads
_AUTO_MAP_CONFIG_KEY_BYTES = b'"auto_map"'
_AUTO_MAP_KEY_SCAN_MIN_BYTES = 512
_OS_STAT = os.stat
_OS_SCANDIR = os.scandir
_STAT_ISREG = stat.S_ISREG
_STAT_ISDIR = stat.S_ISDIR
_LIST = list
EXECUTABLE_MODEL_FILE_PREFIXES = (
    "configuration",
    "feature_extraction",
    "generation",
    "image_processing",
    "modeling",
    "processing",
    "tokenization",
)
EXECUTABLE_MODEL_FILE_PREFIX_START_CHARS = frozenset(
    prefix[0] for prefix in EXECUTABLE_MODEL_FILE_PREFIXES
)
VALID_REQUESTED_TRUST_MODES = frozenset(
    {
        MODEL_LOAD_TRUST_DEFAULT_SAFE,
        MODEL_LOAD_TRUST_TRUST_REMOTE_CODE,
    }
)
TRUST_APPLICABLE_TEXT_LOADERS = frozenset({"mlx_lm", "mlx_lm_unavailable"})
TRUST_APPLICABLE_TEXT_LOADERS_COMMON = frozenset({"mlx-lm", "mlx_lm", "mlx_lm_unavailable"})
CANONICAL_MLX_LM_LOADER = "mlx-lm"
TRUST_APPLICABLE_VLM_LOADERS = frozenset({"mlx_vlm", "python_vlm", "mlx_vlm_unavailable"})
TRUST_APPLICABLE_VLM_LOADERS_COMMON = frozenset(
    {"mlx-vlm", "mlx_vlm", "python_vlm", "mlx_vlm_unavailable"}
)
ROUTE_CLASS_BY_RUNTIME_KIND = {
    "text": WORKER_ROUTE_PYTHON_TEXT_COMPATIBILITY,
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

    resolved_policy_source = policy_source
    if request_policy is not None:
        resolved_policy_source = _non_empty(
            getattr(request_policy, "policy_source", ""),
            policy_source,
        )
    custom_loader_required, detection_source = _detect_custom_loader_requirement(model_spec)
    if custom_loader_required and requested_mode != MODEL_LOAD_TRUST_TRUST_REMOTE_CODE:
        raise ModelLoadTrustRejection(
            _custom_loader_rejection_policy(
                requested_mode,
                resolved_policy_source,
                route_class,
                loader_family,
                detection_source,
            )
        )
    policy = MODEL_LOAD_TRUST_POLICY()
    policy.requested_mode = requested_mode
    policy.policy_source = resolved_policy_source
    policy.route_class = route_class
    policy.loader_family = loader_family
    policy.effective_mode = requested_mode
    policy.custom_loader_required = custom_loader_required
    policy.custom_loader_detection_source = detection_source
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
        MODEL_LOAD_TRUST_DEFAULT_SAFE,
        WORKER_ROUTE_PYTHON_TEXT_COMPATIBILITY,
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
        effective_mode=MODEL_LOAD_TRUST_NOT_APPLICABLE,
        policy_source=NOT_APPLICABLE_SOURCE,
        custom_loader_detection_source=NOT_APPLICABLE_SOURCE,
        route_class=route_class,
        loader_family=loader_family,
    )


def load_kwargs_for_policy(policy: common_pb2.ModelLoadTrustPolicy) -> dict[str, Any]:
    if policy.effective_mode != MODEL_LOAD_TRUST_TRUST_REMOTE_CODE:
        return {}
    return {"trust_remote_code": True}


def _custom_loader_rejection_policy(
    requested_mode: int,
    policy_source: str,
    route_class: int,
    loader_family: str,
    detection_source: str,
) -> common_pb2.ModelLoadTrustPolicy:
    policy = MODEL_LOAD_TRUST_POLICY()
    policy.CopyFrom(
        _custom_loader_rejection_policy_template(
            requested_mode,
            policy_source,
            route_class,
            loader_family,
            detection_source,
        )
    )
    return policy


@lru_cache(maxsize=128)
def _custom_loader_rejection_policy_template(
    requested_mode: int,
    policy_source: str,
    route_class: int,
    loader_family: str,
    detection_source: str,
) -> common_pb2.ModelLoadTrustPolicy:
    return MODEL_LOAD_TRUST_POLICY(
        requested_mode=requested_mode,
        effective_mode=requested_mode,
        policy_source=policy_source,
        custom_loader_required=True,
        custom_loader_detection_source=detection_source,
        block_reason=BLOCK_REASON_CUSTOM_LOADER_REQUIRES_TRUST,
        route_class=route_class,
        loader_family=loader_family,
    )


def _requested_mode(
    model_spec: common_pb2.ModelSpec,
    request_policy: common_pb2.ModelLoadTrustPolicy | None,
) -> tuple[int, str]:
    valid_requested_modes = VALID_REQUESTED_TRUST_MODES
    if request_policy is not None and request_policy.requested_mode in valid_requested_modes:
        return request_policy.requested_mode, REQUEST_SOURCE
    if (
        model_spec.HasField("settings")
        and model_spec.settings.load_trust_mode in valid_requested_modes
    ):
        return model_spec.settings.load_trust_mode, MODEL_SETTINGS_SOURCE
    return MODEL_LOAD_TRUST_DEFAULT_SAFE, DEFAULT_SAFE_SOURCE


def _route_class(
    model_spec: common_pb2.ModelSpec,
    request_policy: common_pb2.ModelLoadTrustPolicy | None,
    runtime_kind: str,
) -> int:
    if request_policy is not None and request_policy.route_class != WORKER_ROUTE_CLASS_UNSPECIFIED:
        return request_policy.route_class
    if model_spec.route_class != WORKER_ROUTE_CLASS_UNSPECIFIED:
        return model_spec.route_class
    if runtime_kind == "text":
        return WORKER_ROUTE_PYTHON_TEXT_COMPATIBILITY
    return ROUTE_CLASS_BY_RUNTIME_KIND.get(runtime_kind, WORKER_ROUTE_CLASS_UNSPECIFIED)


def _loader_family(
    model_spec: common_pb2.ModelSpec,
    request_policy: common_pb2.ModelLoadTrustPolicy | None,
    runtime_kind: str,
    *,
    runtime_name: str,
) -> str:
    if request_policy is not None:
        requested_family = str(
            getattr(request_policy, "loader_family", "") or ""
        ).strip()
        if requested_family:
            return requested_family
    if runtime_kind == "text":
        return runtime_name or "mlx-lm"
    if runtime_kind == "vlm":
        return model_spec.ext.get("melix.vlm.backend_id", "").strip() or str(
            runtime_name or "mlx_vlm"
        )
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
            loader_family == CANONICAL_MLX_LM_LOADER
            or runtime_name == CANONICAL_MLX_LM_LOADER
        ):
            return True
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
    else:
        return False
    normalized_runtime_name = runtime_name.strip().lower().replace("-", "_")
    family = loader_family.strip().lower().replace("-", "_")
    if runtime_kind == "text":
        return family in TRUST_APPLICABLE_TEXT_LOADERS or normalized_runtime_name in TRUST_APPLICABLE_TEXT_LOADERS
    if normalized_runtime_name.startswith("deterministic"):
        return False
    return family in TRUST_APPLICABLE_VLM_LOADERS or normalized_runtime_name in TRUST_APPLICABLE_VLM_LOADERS


def _runtime_name(runtime: Any) -> str:
    if runtime is None:
        return ""
    try:
        runtime_name = runtime.runtime_name
    except AttributeError:
        return ""
    if type(runtime_name) is str:
        return runtime_name
    if not runtime_name:
        return ""
    return str(runtime_name)


def _detect_custom_loader_requirement(model_spec: common_pb2.ModelSpec) -> tuple[bool, str]:
    config_path = _model_config_path(model_spec)
    config_detection = CONFIG_JSON_ABSENT_DETECTION
    if config_path is not None:
        config_path_text, stat_path = config_path
        try:
            config_stat = _OS_STAT(stat_path)
        except OSError:
            config_stat = None
        if config_stat is not None and _STAT_ISREG(config_stat.st_mode):
            config_detection = _detect_custom_loader_requirement_for_stat(
                config_path_text,
                config_stat.st_mtime_ns,
                config_stat.st_size,
            )
            if config_detection is CONFIG_JSON_AUTO_MAP_DETECTION:
                return config_detection
    executable_model_files = _detect_executable_model_files(model_spec)
    if executable_model_files:
        return True, _model_files_detection_source(executable_model_files)
    return config_detection


def _detect_executable_model_files(model_spec: common_pb2.ModelSpec) -> tuple[str, ...]:
    scan_path = _executable_model_scan_path(model_spec)
    if scan_path is None:
        return ()
    try:
        directory_stat = _OS_STAT(scan_path)
    except OSError:
        return ()
    if not _STAT_ISDIR(directory_stat.st_mode):
        return ()
    return _detect_executable_model_files_for_stat(
        scan_path,
        directory_stat.st_mtime_ns,
        directory_stat.st_size,
    )


def _executable_model_scan_path(model_spec: common_pb2.ModelSpec) -> str | None:
    model_path_value = model_spec.model_path
    if type(model_path_value) is str:
        if not model_path_value:
            return None
        if not model_path_value[0].isspace() and not model_path_value[-1].isspace():
            return _executable_model_scan_path_for_model_path(model_path_value)
    model_path = str(model_path_value or "").strip()
    if not model_path:
        return None
    return _executable_model_scan_path_for_model_path(model_path)


@lru_cache(maxsize=128)
def _executable_model_scan_path_for_model_path(model_path: str) -> str:
    if model_path[0] == "~":
        return str(Path(model_path).expanduser())
    return model_path


@lru_cache(maxsize=128)
def _detect_executable_model_files_for_stat(
    scan_path: str,
    mtime_ns: int,
    size: int,
) -> tuple[str, ...]:
    _ = (mtime_ns, size)
    is_executable_model_file_entry = _is_executable_model_file_entry
    try:
        with _OS_SCANDIR(scan_path) as entries:
            first_file_name = ""
            executable_file_names: list[str] | None = None
            for entry in entries:
                if not is_executable_model_file_entry(entry):
                    continue
                if not first_file_name:
                    first_file_name = entry.name
                    continue
                if executable_file_names is None:
                    executable_file_names = _LIST((first_file_name,))
                executable_file_names.append(entry.name)
            if executable_file_names is None:
                return (first_file_name,) if first_file_name else ()
            executable_file_names.sort()
            return tuple(executable_file_names)
    except OSError:
        return ()


def _is_executable_model_file_entry(entry: os.DirEntry[str]) -> bool:
    name = entry.name
    if len(name) <= 3:
        return False
    if name[0] not in EXECUTABLE_MODEL_FILE_PREFIX_START_CHARS:
        return False
    if name[-3:] != ".py":
        return False
    if not name.startswith(EXECUTABLE_MODEL_FILE_PREFIXES):
        return False
    try:
        return entry.is_file(follow_symlinks=False)
    except OSError:
        return False


@lru_cache(maxsize=128)
def _model_files_detection_source(file_names: tuple[str, ...]) -> str:
    return "model_files:" + ",".join(file_names)


def _auto_map_has_custom_loader(auto_map: dict[Any, Any]) -> bool:
    for value in auto_map.values():
        if type(value) is str:
            if not value:
                continue
            if not value[0].isspace() or not value.isspace():
                return True
        elif isinstance(value, str):
            if not value:
                continue
            if not value[0].isspace() or not value.isspace():
                return True
        elif value is not None and str(value).strip():
            return True
    return False


def _read_model_config(model_spec: common_pb2.ModelSpec) -> dict[str, Any] | None:
    config_path = _model_config_path(model_spec)
    if config_path is None:
        return None
    config_path_text, stat_path = config_path
    try:
        config_stat = _OS_STAT(stat_path)
        if not _STAT_ISREG(config_stat.st_mode):
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
    model_path_value = model_spec.model_path
    if type(model_path_value) is str:
        if not model_path_value:
            return None
        if not model_path_value[0].isspace() and not model_path_value[-1].isspace():
            return _model_config_path_for_model_path(model_path_value)
    model_path = str(model_path_value or "").strip()
    if not model_path:
        return None
    return _model_config_path_for_model_path(model_path)


@lru_cache(maxsize=128)
def _model_config_path_for_model_path(model_path: str) -> tuple[str, str | os.PathLike[str]]:
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
    _ = (mtime_ns, size)
    loads = _JSON_LOADS
    try:
        with _OPEN(config_path, "rb") as handle:
            payload_bytes = handle.read()
            if (
                size >= _AUTO_MAP_KEY_SCAN_MIN_BYTES
                and _AUTO_MAP_CONFIG_KEY_BYTES not in payload_bytes
            ):
                return CONFIG_JSON_DETECTION
            config = loads(payload_bytes)
    except (OSError, json.JSONDecodeError):
        return CONFIG_JSON_ABSENT_DETECTION
    if not isinstance(config, dict) or not config:
        return CONFIG_JSON_ABSENT_DETECTION
    auto_map = config.get("auto_map")
    if isinstance(auto_map, dict) and _auto_map_has_custom_loader(auto_map):
        return CONFIG_JSON_AUTO_MAP_DETECTION
    return CONFIG_JSON_DETECTION


@lru_cache(maxsize=128)
def _read_model_config_for_stat(
    config_path: str,
    mtime_ns: int,
    size: int,
) -> dict[str, Any] | None:
    _ = (mtime_ns, size)
    loads = _JSON_LOADS
    try:
        with _OPEN(config_path, "rb") as handle:
            payload = loads(handle.read())
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _mode_name(mode: int) -> str:
    return common_pb2.ModelLoadTrustMode.Name(mode)


def _route_name(route_class: int) -> str:
    return common_pb2.WorkerRouteClass.Name(route_class)


def _non_empty(value: str, fallback: str) -> str:
    if not value:
        return fallback
    if not value[0].isspace():
        return value
    return fallback if value.isspace() else value
