from __future__ import annotations

import importlib.metadata

import pytest

from worker.runtime import runtime_utils


def test_callable_accepts_kwarg_returns_false_for_non_introspectable_object() -> None:
    assert runtime_utils.callable_accepts_kwarg(object(), "temperature") is False


def test_installed_package_version_returns_empty_for_missing_package(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_version(package_name: str) -> str:
        _ = package_name
        raise importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(runtime_utils.importlib.metadata, "version", fake_version)

    assert runtime_utils.installed_package_version("missing-package") == ""
