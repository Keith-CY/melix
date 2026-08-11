from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import stat
from types import FunctionType, MethodType
from typing import Any


_MODEL_WEIGHT_SUFFIXES = (".safetensors", ".npz", ".bin", ".gguf")
_MODEL_WEIGHT_SUFFIX_LAST_CHARS = frozenset("sSzZnNfF")
_MODEL_WEIGHT_PRIMARY_SUFFIX = ".safetensors"
_MODEL_WEIGHT_SECONDARY_SUFFIXES = (".npz", ".bin", ".gguf")


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
    skip_first_parameter: bool = False,
) -> CallableKwargSignature:
    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return _EMPTY_KWARG_SIGNATURE

    keyword_accessible_params: set[str] = set()
    parameter_names: list[str] = []
    accepts_var_keyword = False
    positional_or_keyword = inspect.Parameter.POSITIONAL_OR_KEYWORD
    keyword_only = inspect.Parameter.KEYWORD_ONLY
    var_keyword = inspect.Parameter.VAR_KEYWORD
    for index, (name, parameter) in enumerate(signature.parameters.items()):
        if skip_first_parameter and index == 0:
            continue
        parameter_kind = parameter.kind
        if parameter_kind == var_keyword:
            accepts_var_keyword = True
        elif parameter_kind == positional_or_keyword or parameter_kind == keyword_only:
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
    if type(callable_obj) is MethodType:
        return callable_obj.__func__, True
    bound_function = getattr(callable_obj, "__func__", None)
    if bound_function is not None and getattr(callable_obj, "__self__", None) is not None:
        return bound_function, True
    return callable_obj, False


@lru_cache(maxsize=512)
def _callable_kwarg_signature_cached(
    callable_obj: Any,
    skip_first_parameter: bool = False,
) -> CallableKwargSignature:
    return _callable_kwarg_signature_uncached(callable_obj, skip_first_parameter)


@lru_cache(maxsize=1024)
def _callable_accepts_kwarg_cached(
    callable_obj: Any,
    skip_first_parameter: bool,
    keyword: str,
) -> bool:
    signature = _callable_kwarg_signature_cached(callable_obj, skip_first_parameter)
    return keyword in signature.keyword_accessible_params or signature.accepts_var_keyword


@lru_cache(maxsize=1024)
def _callable_declares_kwarg_cached(
    callable_obj: Any,
    skip_first_parameter: bool,
    keyword: str,
) -> bool:
    signature = _callable_kwarg_signature_cached(callable_obj, skip_first_parameter)
    return keyword in signature.keyword_accessible_params


def callable_kwarg_signature(callable_obj: Any) -> CallableKwargSignature:
    if type(callable_obj) is MethodType:
        return _callable_kwarg_signature_cached(callable_obj.__func__, True)
    cache_callable, skip_first_parameter = _callable_cache_target(callable_obj)
    try:
        return _callable_kwarg_signature_cached(cache_callable, skip_first_parameter)
    except TypeError:
        return _callable_kwarg_signature_uncached(callable_obj)


def callable_declares_kwarg(callable_obj: Any, keyword: str) -> bool:
    if type(callable_obj) is FunctionType:
        return _callable_declares_kwarg_cached(callable_obj, False, keyword)
    if type(callable_obj) is MethodType:
        return _callable_declares_kwarg_cached(callable_obj.__func__, True, keyword)
    cache_callable, skip_first_parameter = _callable_cache_target(callable_obj)
    try:
        return _callable_declares_kwarg_cached(cache_callable, skip_first_parameter, keyword)
    except TypeError:
        return keyword in _callable_kwarg_signature_uncached(callable_obj).keyword_accessible_params


def callable_accepts_kwarg(callable_obj: Any, keyword: str) -> bool:
    if type(callable_obj) is FunctionType:
        return _callable_accepts_kwarg_cached(callable_obj, False, keyword)
    if type(callable_obj) is MethodType:
        return _callable_accepts_kwarg_cached(callable_obj.__func__, True, keyword)
    cache_callable, skip_first_parameter = _callable_cache_target(callable_obj)
    try:
        return _callable_accepts_kwarg_cached(cache_callable, skip_first_parameter, keyword)
    except TypeError:
        signature = _callable_kwarg_signature_uncached(callable_obj)
        return keyword in signature.keyword_accessible_params or signature.accepts_var_keyword


def first_declared_kwarg(callable_obj: Any, keywords: tuple[str, ...]) -> str:
    capabilities = callable_kwarg_signature(callable_obj)
    for keyword in keywords:
        if capabilities.declares(keyword):
            return keyword
    return ""


def clear_callable_kwarg_signature_cache() -> None:
    _callable_kwarg_signature_cached.cache_clear()
    _callable_accepts_kwarg_cached.cache_clear()
    _callable_declares_kwarg_cached.cache_clear()


_INSTALLED_PACKAGE_VERSION_CACHE: dict[str, str] = {}


def installed_package_version(
    package_name: str,
    _cache: dict[str, str] = _INSTALLED_PACKAGE_VERSION_CACHE,
) -> str:
    try:
        return _cache[package_name]
    except KeyError:
        pass
    try:
        version = importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        version = ""
    _cache[package_name] = version
    return version


def clear_installed_package_version_cache() -> None:
    _INSTALLED_PACKAGE_VERSION_CACHE.clear()


def estimate_model_weight_resident_bytes(model_path: str) -> int:
    """Estimate model resident bytes from local weight artifacts."""
    raw_model_path = model_path or ""
    if not raw_model_path.strip():
        return 0
    root = Path(raw_model_path)
    if raw_model_path[0] == "~":
        root = root.expanduser()
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
        if not index_path.is_file():
            return 0
        payload = json.loads(index_path.read_bytes())
    except (OSError, json.JSONDecodeError):
        return 0
    weight_map = payload.get("weight_map")
    if not isinstance(weight_map, dict):
        return 0
    total = 0
    seen: set[str] = set()
    seen_add = seen.add
    os_sep = os.sep
    model_dir_path = os.fspath(model_dir)
    is_model_weight_filename = _is_model_weight_filename
    is_regular_file_mode = stat.S_ISREG
    os_path_join = os.path.join
    os_stat = os.stat
    for raw_shard in weight_map.values():
        shard_name = str(raw_shard or "").strip()
        if not shard_name or shard_name in seen or not is_model_weight_filename(shard_name):
            continue
        seen_add(shard_name)
        if shard_name[0] == os_sep:
            shard_path = shard_name
        else:
            shard_path = os_path_join(model_dir_path, shard_name)
        try:
            stat_result = os_stat(shard_path)
            if is_regular_file_mode(stat_result.st_mode):
                total += stat_result.st_size
        except OSError:
            continue
    return total


def _top_level_weight_file_bytes(model_dir: Path) -> int:
    total = 0
    try:
        entries = os.scandir(model_dir)
    except OSError:
        return 0
    entry_file_size = _weight_dir_entry_file_size
    with entries:
        for entry in entries:
            total += entry_file_size(entry)
    return total


def _is_model_weight_filename(name: str) -> bool:
    if not name or name[-1] not in _MODEL_WEIGHT_SUFFIX_LAST_CHARS:
        return False
    if name.endswith(_MODEL_WEIGHT_PRIMARY_SUFFIX):
        return name != _MODEL_WEIGHT_PRIMARY_SUFFIX
    if name.endswith(_MODEL_WEIGHT_SECONDARY_SUFFIXES):
        return name not in _MODEL_WEIGHT_SECONDARY_SUFFIXES
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
        stat_result = entry.stat()
        if not stat.S_ISREG(stat_result.st_mode):
            return 0
        return stat_result.st_size
    except OSError:
        return 0


def _weight_file_size(path: Path) -> int:
    if not _is_model_weight_filename(path.name):
        return 0
    try:
        stat_result = path.stat()
        if not stat.S_ISREG(stat_result.st_mode):
            return 0
        return stat_result.st_size
    except OSError:
        return 0
