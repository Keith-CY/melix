from __future__ import annotations

import importlib.metadata
import inspect
from typing import Any

import pytest

from worker.runtime import runtime_utils


def test_callable_accepts_kwarg_returns_false_for_non_introspectable_object() -> None:
    assert runtime_utils.callable_accepts_kwarg(object(), "temperature") is False


def test_callable_accepts_kwarg_caches_signature_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_utils.clear_callable_accepts_kwarg_cache()
    original_signature = inspect.signature
    signature_calls = 0

    def tracked_signature(callable_obj: Any) -> inspect.Signature:
        nonlocal signature_calls
        signature_calls += 1
        return original_signature(callable_obj)

    def sample(*, temperature: float = 0.0) -> None:
        _ = temperature

    monkeypatch.setattr(runtime_utils.inspect, "signature", tracked_signature)

    assert runtime_utils.callable_accepts_kwarg(sample, "temperature") is True
    assert runtime_utils.callable_accepts_kwarg(sample, "temperature") is True
    assert signature_calls == 1
    assert runtime_utils.callable_accepts_kwarg(sample, "top_p") is False
    assert signature_calls == 2

    runtime_utils.clear_callable_accepts_kwarg_cache()


def test_callable_accepts_kwarg_caches_bound_methods_by_underlying_function(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_utils.clear_callable_accepts_kwarg_cache()
    original_signature = inspect.signature
    signature_calls = 0
    inspected_objects: list[Any] = []

    class SampleRuntime:
        def generate(self, prompt: str, *, temperature: float = 0.0) -> str:
            return f"{prompt}:{temperature}"

    def tracked_signature(callable_obj: Any) -> inspect.Signature:
        nonlocal signature_calls
        signature_calls += 1
        inspected_objects.append(callable_obj)
        return original_signature(callable_obj)

    monkeypatch.setattr(runtime_utils.inspect, "signature", tracked_signature)

    first = SampleRuntime()
    second = SampleRuntime()
    assert runtime_utils.callable_accepts_kwarg(first.generate, "temperature") is True
    assert runtime_utils.callable_accepts_kwarg(second.generate, "temperature") is True
    assert runtime_utils.callable_accepts_kwarg(second.generate, "self") is False
    assert signature_calls == 2
    assert inspected_objects == [SampleRuntime.generate, SampleRuntime.generate]

    runtime_utils.clear_callable_accepts_kwarg_cache()


def test_callable_accepts_kwarg_bound_methods_preserve_parameter_scan_behavior() -> None:
    runtime_utils.clear_callable_accepts_kwarg_cache()

    class SampleRuntime:
        def generate(
            self,
            prompt: str,
            max_tokens: int = 128,
            *,
            temperature: float = 0.0,
            top_p: float = 1.0,
        ) -> str:
            return f"{prompt}:{max_tokens}:{temperature}:{top_p}"

    method = SampleRuntime().generate

    assert runtime_utils.callable_accepts_kwarg(method, "self") is False
    assert runtime_utils.callable_accepts_kwarg(method, "prompt") is True
    assert runtime_utils.callable_accepts_kwarg(method, "max_tokens") is True
    assert runtime_utils.callable_accepts_kwarg(method, "temperature") is True
    assert runtime_utils.callable_accepts_kwarg(method, "top_p") is True
    assert runtime_utils.callable_accepts_kwarg(method, "missing") is False

    runtime_utils.clear_callable_accepts_kwarg_cache()


def test_callable_accepts_kwarg_bound_methods_preserve_var_keyword_behavior() -> None:
    runtime_utils.clear_callable_accepts_kwarg_cache()

    class SampleRuntime:
        def generate(self, **kwargs: object) -> object:
            return kwargs

    assert runtime_utils.callable_accepts_kwarg(SampleRuntime().generate, "temperature") is True
    assert runtime_utils.callable_accepts_kwarg(SampleRuntime().generate, "self") is True

    runtime_utils.clear_callable_accepts_kwarg_cache()


def test_callable_accepts_kwarg_falls_back_for_unhashable_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_utils.clear_callable_accepts_kwarg_cache()
    original_signature = inspect.signature
    signature_calls = 0

    class UnhashableCallable:
        __hash__ = None

        def __call__(self, *, temperature: float = 0.0) -> None:
            _ = temperature

    def tracked_signature(callable_obj: Any) -> inspect.Signature:
        nonlocal signature_calls
        signature_calls += 1
        return original_signature(callable_obj)

    callable_obj = UnhashableCallable()
    monkeypatch.setattr(runtime_utils.inspect, "signature", tracked_signature)

    assert runtime_utils.callable_accepts_kwarg(callable_obj, "temperature") is True
    assert runtime_utils.callable_accepts_kwarg(callable_obj, "temperature") is True
    assert signature_calls == 2


def test_installed_package_version_returns_empty_for_missing_package(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_version(package_name: str) -> str:
        _ = package_name
        raise importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(runtime_utils.importlib.metadata, "version", fake_version)

    assert runtime_utils.installed_package_version("missing-package") == ""
