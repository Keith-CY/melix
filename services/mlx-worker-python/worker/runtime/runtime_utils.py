from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import importlib.metadata
import inspect
import json
import os
from pathlib import Path
from types import FunctionType
from typing import Any


_MODEL_WEIGHT_SUFFIXES = (".safetensors", ".npz", ".bin", ".gguf")
_MODEL_WEIGHT_SUFFIX_LAST_CHARS = frozenset("sSzZnNfF")


@dataclass(frozen=True, slots=True)
class CallableKwargSignature:
    parameter_names: tuple[str, ...]
    keyword_accessible_params: frozenset[str]
    accepts_var_keyword: bool

    def declares(self, keyword: str) -> bool:
        return keyword in self.keyword_accessible_params

    def accepts(self, keyword: str) -> bool:
        return keyword in self.keyword_accessible_params or self.accepts_var_keyword


_EMPTY_KWARG_SIGNATURE = CallableKwargSignature((), frozenset(), False)


def _callable_kwarg_signature_uncached(
    callable_obj: Any,
    *,
    skip_first_parameter: bool = False,
) -> CallableKwargSignature:
    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return _EMPTY_KWARG_SIGNATURE

    keyword_accessible_params: set[str] = set()
    parameter_names: list[str] = []
    accepts_var_keyword = False
    for index, (name, parameter) in enumerate(signature.parameters.items()):
        if skip_first_parameter and index == 0:
            continue
        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            accepts_var_keyword = True
        elif parameter.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            keyword_accessible_params.add(name)
            parameter_names.append(name)
    return CallableKwargSignature(
        tuple(parameter_names),
        frozenset(keyword_accessible_params),
        accepts_var_keyword,
    )


def _callable_cache_target(callable_obj: Any) -> tuple[Any, bool]:
    if type(callable_obj) is FunctionType:
        return callable_obj, False
    bound_function = getattr(callable_obj, "__func__", None)
    if bound_function is not None and getattr(callable_obj, "__self__", None) is not None:
        return bound_function, True
    return callable_obj, False


@lru_cache(maxsize=512)
def _callable_kwarg_signature_cached(
    callable_obj: Any,
    *,
    skip_first_parameter: bool = False,
) -> CallableKwargSignature:
    return _callable_kwarg_signature_uncached(
        callable_obj,
        skip_first_parameter=skip_first_parameter,
    )


def callable_kwarg_signature(callable_obj: Any) -> CallableKwargSignature:
    cache_callable, skip_first_parameter = _callable_cache_target(callable_obj)
    try:
        return _callable_kwarg_signature_cached(
            cache_callable,
            skip_first_parameter=skip_first_parameter,
        )
    except TypeError:
        return _callable_kwarg_signature_uncached(callable_obj)


def callable_declares_kwarg(callable_obj: Any, keyword: str) -> bool:
    return keyword in callable_kwarg_signature(callable_obj).keyword_accessible_params


def callable_accepts_kwarg(callable_obj: Any, keyword: str) -> bool:
    signature = callable_kwarg_signature(callable_obj)
    return keyword in signature.keyword_accessible_params or signature.accepts_var_keyword


def first_declared_kwarg(callable_obj: Any, keywords: tuple[str, ...]) -> str:
    capabilities = callable_kwarg_signature(callable_obj)
    for keyword in keywords:
        if capabilities.declares(keyword):
            return keyword
    return ""


def clear_callable_kwarg_signature_cache() -> None:
    _callable_kwarg_signature_cached.cache_clear()


@lru_cache(maxsize=128)
def installed_package_version(package_name: str) -> str:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return ""


def clear_installed_package_version_cache() -> None:
    installed_package_version.cache_clear()


def estimate_model_weight_resident_bytes(model_path: str) -> int:
    """Estimate model resident bytes from local weight artifacts."""
    if not str(model_path or "").strip():
        return 0
    root = Path(model_path).expanduser()
    try:
        if root.is_file():
            return _weight_file_size(root)
        if not root.is_dir():
            return 0
    except OSError:
        return 0

    indexed_size = _indexed_safetensors_shard_bytes(root)
    if indexed_size > 0:
        return indexed_size
    return _top_level_weight_file_bytes(root)


def _indexed_safetensors_shard_bytes(model_dir: Path) -> int:
    index_path = model_dir / "model.safetensors.index.json"
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    weight_map = payload.get("weight_map")
    if not isinstance(weight_map, dict):
        return 0
    total = 0
    seen: set[str] = set()
    for raw_shard in weight_map.values():
        shard_name = str(raw_shard or "").strip()
        if not shard_name or shard_name in seen:
            continue
        seen.add(shard_name)
        shard_path = Path(shard_name)
        if not shard_path.is_absolute():
            shard_path = model_dir / shard_path
        total += _weight_file_size(shard_path)
    return total


def _top_level_weight_file_bytes(model_dir: Path) -> int:
    total = 0
    try:
        entries = os.scandir(model_dir)
    except OSError:
        return 0
    with entries:
        for entry in entries:
            total += _weight_dir_entry_file_size(entry)
    return total


def _is_model_weight_filename(name: str) -> bool:
    if not name or name[-1] not in _MODEL_WEIGHT_SUFFIX_LAST_CHARS:
        return False
    if name.endswith(_MODEL_WEIGHT_SUFFIXES):
        return name not in _MODEL_WEIGHT_SUFFIXES
    if name.islower():
        return False
    lower_name = name.lower()
    return (
        lower_name not in _MODEL_WEIGHT_SUFFIXES
        and lower_name.endswith(_MODEL_WEIGHT_SUFFIXES)
    )


def _weight_dir_entry_file_size(entry: os.DirEntry[str]) -> int:
    if not _is_model_weight_filename(entry.name):
        return 0
    try:
        if not entry.is_file():
            return 0
        return entry.stat().st_size
    except OSError:
        return 0


def _weight_file_size(path: Path) -> int:
    if not _is_model_weight_filename(path.name):
        return 0
    try:
        if not path.is_file():
            return 0
        return path.stat().st_size
    except OSError:
        return 0
