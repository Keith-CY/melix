from __future__ import annotations

from functools import lru_cache
import importlib.metadata
import inspect
from typing import Any


def _callable_accepts_kwarg_uncached(
    callable_obj: Any,
    keyword: str,
    *,
    skip_first_parameter: bool = False,
) -> bool:
    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return False

    matching_parameter: inspect.Parameter | None = None
    for index, (name, parameter) in enumerate(signature.parameters.items()):
        if skip_first_parameter and index == 0:
            continue
        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            return True
        if name == keyword:
            matching_parameter = parameter

    if matching_parameter is None:
        return False
    return matching_parameter.kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    )


@lru_cache(maxsize=512)
def _callable_accepts_kwarg_cached(
    callable_obj: Any,
    keyword: str,
    *,
    skip_first_parameter: bool = False,
) -> bool:
    return _callable_accepts_kwarg_uncached(
        callable_obj,
        keyword,
        skip_first_parameter=skip_first_parameter,
    )


def callable_accepts_kwarg(callable_obj: Any, keyword: str) -> bool:
    cache_callable = callable_obj
    skip_first_parameter = False
    bound_function = getattr(callable_obj, "__func__", None)
    if bound_function is not None and getattr(callable_obj, "__self__", None) is not None:
        cache_callable = bound_function
        skip_first_parameter = True

    try:
        return _callable_accepts_kwarg_cached(
            cache_callable,
            keyword,
            skip_first_parameter=skip_first_parameter,
        )
    except TypeError:
        return _callable_accepts_kwarg_uncached(callable_obj, keyword)


def clear_callable_accepts_kwarg_cache() -> None:
    _callable_accepts_kwarg_cached.cache_clear()


def installed_package_version(package_name: str) -> str:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return ""
