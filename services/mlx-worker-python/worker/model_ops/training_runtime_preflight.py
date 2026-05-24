from __future__ import annotations

import gc
import importlib
import importlib.util
import platform
import traceback
from typing import Any, Callable, TypeVar

from worker.model_ops.errors import ModelOperationError

_MEDIA_DECODER_MODULES = ("PIL", "imageio", "av", "soundfile")
_T = TypeVar("_T")


def truthy(raw_value: str) -> bool:
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def training_runtime_preflight_fields(
    *,
    source_model: Any,
    adapter_scope: dict[str, str],
    inspection_only: bool = False,
) -> dict[str, Any]:
    native_available = _module_spec_available("mlx") and _module_spec_available("mlx_lm")
    media_dependency = _media_decoder_dependency_state()
    disabled_decoder_paths: list[str] = []
    if media_dependency["state"] != "healthy":
        disabled_decoder_paths.append("media")

    host_supported = platform.system() == "Darwin"
    runtime_gate = "ready" if host_supported and native_available else "unsupported"
    unsupported_reason = ""
    if not host_supported:
        unsupported_reason = "non_apple_host"
    elif not native_available:
        unsupported_reason = "missing_native_runtime"

    if inspection_only:
        native_load_status = "disabled"
        fallback_reader = "metadata_only"
    else:
        native_load_status = "available" if native_available else "unavailable"
        fallback_reader = "none" if native_available else "subprocess"

    return {
        "runtime_gate": runtime_gate,
        "inspection_only_import": inspection_only,
        "media_decoder_dependency": media_dependency,
        "native_load_status": native_load_status,
        "disabled_decoder_paths": disabled_decoder_paths,
        "fallback_reader": fallback_reader,
        "unsupported_reason": unsupported_reason,
        "traceback_cleanup_result": "not_applicable",
        "retained_tensor_bytes_after_failure": 0,
        "training_runtime_preflight": {
            "schema_version": "melix.training_runtime_preflight.v1",
            "source_model_kind": source_model.model_kind,
            "training_surface": adapter_scope.get("training_surface", ""),
            "runtime_gate": runtime_gate,
            "native_load_status": native_load_status,
            "media_decoder_dependency": media_dependency,
            "disabled_decoder_paths": list(disabled_decoder_paths),
            "fallback_reader": fallback_reader,
            "unsupported_reason": unsupported_reason,
        },
    }


def call_with_training_failure_cleanup(
    callback: Callable[[], _T],
    *,
    details: dict[str, str] | None = None,
) -> _T:
    try:
        return callback()
    except Exception as exc:
        raise_with_training_failure_cleanup(exc, details=details)


def raise_with_training_failure_cleanup(
    exc: Exception,
    *,
    details: dict[str, str] | None = None,
) -> None:
    cleanup = _cleanup_training_failure_exception(exc)
    if details:
        cleanup = {**details, **cleanup}
    if isinstance(exc, ModelOperationError):
        error_details = dict(exc.details)
        error_details.update(cleanup)
        raise ModelOperationError(
            code=exc.code,
            message=exc.message,
            retriable=exc.retriable,
            details=error_details,
        ) from exc.__cause__
    raise ModelOperationError(
        code="backend_training_failure",
        message=str(exc),
        details=cleanup,
    ) from None


def runtime_preflight_failure_details(fields: dict[str, Any]) -> dict[str, str]:
    dependency = fields.get("media_decoder_dependency", {})
    if not isinstance(dependency, dict):
        dependency = {}
    disabled_decoder_paths = fields.get("disabled_decoder_paths", [])
    if isinstance(disabled_decoder_paths, list):
        disabled_paths = ",".join(str(path) for path in disabled_decoder_paths)
    else:
        disabled_paths = str(disabled_decoder_paths)
    return {
        "runtime_gate": str(fields.get("runtime_gate", "")),
        "inspection_only_import": str(fields.get("inspection_only_import", "")).lower(),
        "native_load_status": str(fields.get("native_load_status", "")),
        "disabled_decoder_paths": disabled_paths,
        "fallback_reader": str(fields.get("fallback_reader", "")),
        "unsupported_reason": str(fields.get("unsupported_reason", "")),
        "media_decoder_dependency_state": str(dependency.get("state", "")),
        "media_decoder_dependency_module": str(dependency.get("module", "")),
    }


def _module_spec_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def _media_decoder_dependency_state() -> dict[str, Any]:
    modules: dict[str, dict[str, str]] = {}
    for module_name in _MEDIA_DECODER_MODULES:
        try:
            spec = importlib.util.find_spec(module_name)
        except (ImportError, AttributeError, ValueError) as exc:
            modules[module_name] = {"state": "broken", "message": str(exc)}
            return {
                "state": "broken",
                "module": module_name,
                "message": str(exc),
                "modules": modules,
            }
        if spec is None:
            modules[module_name] = {
                "state": "missing",
                "message": f"Optional media decoder dependency is not installed: {module_name}.",
            }
            continue
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            modules[module_name] = {"state": "broken", "message": str(exc)}
            return {
                "state": "broken",
                "module": module_name,
                "message": str(exc),
                "modules": modules,
            }
        modules[module_name] = {"state": "healthy", "message": ""}
    missing_modules = [
        module_name
        for module_name, module_state in modules.items()
        if module_state["state"] == "missing"
    ]
    healthy_modules = [
        module_name
        for module_name, module_state in modules.items()
        if module_state["state"] == "healthy"
    ]
    if not missing_modules:
        return {
            "state": "healthy",
            "module": healthy_modules[0] if healthy_modules else "",
            "message": "",
            "modules": modules,
        }
    if healthy_modules:
        first_missing = missing_modules[0]
        return {
            "state": "partial",
            "module": first_missing,
            "message": f"Missing optional media decoder dependency: {first_missing}.",
            "modules": modules,
        }
    return {
        "state": "missing",
        "module": "",
        "message": "No optional media decoder dependency is installed.",
        "modules": modules,
    }


def _cleanup_training_failure_exception(exc: BaseException) -> dict[str, str]:
    traceback_summary = _traceback_summary_before_cleanup(exc)
    cleared_count = 0
    visited: set[int] = set()
    pending: list[BaseException] = [exc]
    while pending:
        current = pending.pop()
        current_id = id(current)
        if current_id in visited:
            continue
        visited.add(current_id)
        if current.__traceback__ is not None:
            cleared_count += 1
            current.__traceback__ = None
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    gc.collect()
    retained_bytes = _retained_tensor_bytes_after_failure()
    return {
        "traceback_cleanup_result": "cleared" if cleared_count else "not_needed",
        "retained_tensor_bytes_after_failure": str(retained_bytes),
        "traceback_summary_before_cleanup": traceback_summary,
    }


def _retained_tensor_bytes_after_failure() -> int:
    try:
        import mlx.core as mx
    except ModuleNotFoundError:
        return 0
    try:
        if hasattr(mx, "metal") and hasattr(mx.metal, "get_active_memory"):
            return int(float(mx.metal.get_active_memory() or 0.0))
    except Exception:
        return 0
    return 0


def _traceback_summary_before_cleanup(exc: BaseException) -> str:
    rendered: list[str] = []
    visited: set[int] = set()
    pending: list[BaseException] = [exc]
    while pending:
        current = pending.pop()
        current_id = id(current)
        if current_id in visited:
            continue
        visited.add(current_id)
        rendered.extend(traceback.format_exception(type(current), current, current.__traceback__, limit=8))
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    return "".join(rendered)[-4096:]
