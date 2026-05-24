from __future__ import annotations

import gc
import importlib
import importlib.util
import platform
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


def call_with_training_failure_cleanup(callback: Callable[[], _T]) -> _T:
    try:
        return callback()
    except Exception as exc:
        raise_with_training_failure_cleanup(exc)


def raise_with_training_failure_cleanup(exc: Exception) -> None:
    cleanup = _cleanup_training_failure_exception(exc)
    if isinstance(exc, ModelOperationError):
        details = dict(exc.details)
        details.update(cleanup)
        raise ModelOperationError(
            code=exc.code,
            message=exc.message,
            retriable=exc.retriable,
            details=details,
        ) from exc.__cause__
    raise ModelOperationError(
        code="backend_training_failure",
        message=str(exc),
        details=cleanup,
    ) from None


def _module_spec_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def _media_decoder_dependency_state() -> dict[str, str]:
    for module_name in _MEDIA_DECODER_MODULES:
        try:
            spec = importlib.util.find_spec(module_name)
        except (ImportError, AttributeError, ValueError) as exc:
            return {
                "state": "broken",
                "module": module_name,
                "message": str(exc),
            }
        if spec is None:
            continue
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            return {
                "state": "broken",
                "module": module_name,
                "message": str(exc),
            }
        return {
            "state": "healthy",
            "module": module_name,
            "message": "",
        }
    return {
        "state": "missing",
        "module": "",
        "message": "No optional media decoder dependency is installed.",
    }


def _cleanup_training_failure_exception(exc: BaseException) -> dict[str, str]:
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
    }


def _retained_tensor_bytes_after_failure() -> int:
    try:
        import mlx.core as mx
    except ModuleNotFoundError:
        return 0
    try:
        if hasattr(mx, "metal") and hasattr(mx.metal, "get_peak_memory"):
            return int(float(mx.metal.get_peak_memory() or 0.0))
    except Exception:
        return 0
    return 0
