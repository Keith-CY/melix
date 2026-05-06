from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import importlib.metadata
import inspect
from typing import Any


@dataclass(frozen=True)
class CallableKwargSignature:
    parameter_names: tuple[str, ...]
    keyword_accessible_params: frozenset[str]
    accepts_var_keyword: bool

    def declares(self, keyword: str) -> bool:
        return keyword in self.keyword_accessible_params

    def accepts(self, keyword: str) -> bool:
        return self.declares(keyword) or self.accepts_var_keyword


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
    return callable_kwarg_signature(callable_obj).declares(keyword)


def callable_accepts_kwarg(callable_obj: Any, keyword: str) -> bool:
    return callable_kwarg_signature(callable_obj).accepts(keyword)


def first_declared_kwarg(callable_obj: Any, keywords: tuple[str, ...]) -> str:
    capabilities = callable_kwarg_signature(callable_obj)
    for keyword in keywords:
        if capabilities.declares(keyword):
            return keyword
    return ""


def clear_callable_kwarg_signature_cache() -> None:
    _callable_kwarg_signature_cached.cache_clear()


def installed_package_version(package_name: str) -> str:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return ""
