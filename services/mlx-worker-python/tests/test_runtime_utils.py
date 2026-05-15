from __future__ import annotations

import importlib.metadata
import inspect
import json
import os
from pathlib import Path
from typing import Any

import pytest

from worker.runtime import runtime_utils


def test_callable_accepts_kwarg_returns_false_for_non_introspectable_object() -> None:
    assert runtime_utils.callable_accepts_kwarg(object(), "temperature") is False
    assert runtime_utils.callable_declares_kwarg(object(), "temperature") is False


def test_callable_kwarg_signature_caches_structured_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_utils.clear_callable_kwarg_signature_cache()
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
    assert runtime_utils.callable_declares_kwarg(sample, "temperature") is True
    assert runtime_utils.callable_accepts_kwarg(sample, "top_p") is False
    assert runtime_utils.callable_declares_kwarg(sample, "top_p") is False
    capabilities = runtime_utils.callable_kwarg_signature(sample)
    assert capabilities.parameter_names == ("temperature",)
    assert capabilities.keyword_accessible_params == frozenset({"temperature"})
    assert capabilities.accepts_var_keyword is False
    assert signature_calls == 1

    runtime_utils.clear_callable_kwarg_signature_cache()


def test_callable_accepts_kwarg_caches_bound_methods_by_underlying_function(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_utils.clear_callable_kwarg_signature_cache()
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
    assert runtime_utils.callable_declares_kwarg(second.generate, "self") is False
    assert signature_calls == 1
    assert inspected_objects == [SampleRuntime.generate]

    runtime_utils.clear_callable_kwarg_signature_cache()


def test_callable_accepts_kwarg_bound_methods_preserve_parameter_scan_behavior() -> None:
    runtime_utils.clear_callable_kwarg_signature_cache()

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
    assert runtime_utils.callable_declares_kwarg(method, "prompt") is True
    assert runtime_utils.callable_declares_kwarg(method, "max_tokens") is True
    assert runtime_utils.callable_declares_kwarg(method, "temperature") is True
    assert runtime_utils.callable_declares_kwarg(method, "top_p") is True
    capabilities = runtime_utils.callable_kwarg_signature(method)
    assert capabilities.parameter_names == (
        "prompt",
        "max_tokens",
        "temperature",
        "top_p",
    )
    assert capabilities.keyword_accessible_params == frozenset(
        {"prompt", "max_tokens", "temperature", "top_p"}
    )

    runtime_utils.clear_callable_kwarg_signature_cache()


def test_callable_accepts_kwarg_bound_methods_preserve_var_keyword_behavior() -> None:
    runtime_utils.clear_callable_kwarg_signature_cache()

    class SampleRuntime:
        def generate(self, **kwargs: object) -> object:
            return kwargs

    assert runtime_utils.callable_accepts_kwarg(SampleRuntime().generate, "temperature") is True
    assert runtime_utils.callable_accepts_kwarg(SampleRuntime().generate, "self") is True
    assert runtime_utils.callable_declares_kwarg(SampleRuntime().generate, "temperature") is False
    assert runtime_utils.callable_declares_kwarg(SampleRuntime().generate, "self") is False
    assert runtime_utils.callable_kwarg_signature(SampleRuntime().generate).accepts_var_keyword is True

    runtime_utils.clear_callable_kwarg_signature_cache()


def test_first_declared_kwarg_ignores_variadic_kwargs() -> None:
    runtime_utils.clear_callable_kwarg_signature_cache()

    def explicit(*, stop_words: list[str] | None = None, **kwargs: object) -> None:
        _ = (stop_words, kwargs)

    def variadic(**kwargs: object) -> None:
        _ = kwargs

    assert runtime_utils.first_declared_kwarg(explicit, ("stop", "stop_words", "stop_sequences")) == "stop_words"
    assert runtime_utils.first_declared_kwarg(variadic, ("stop", "stop_words", "stop_sequences")) == ""
    assert runtime_utils.callable_accepts_kwarg(variadic, "stop") is True
    assert runtime_utils.callable_declares_kwarg(variadic, "stop") is False

    runtime_utils.clear_callable_kwarg_signature_cache()


def test_callable_accepts_kwarg_falls_back_for_unhashable_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_utils.clear_callable_kwarg_signature_cache()
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
    runtime_utils.clear_installed_package_version_cache()

    def fake_version(package_name: str) -> str:
        _ = package_name
        raise importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(runtime_utils.importlib.metadata, "version", fake_version)

    assert runtime_utils.installed_package_version("missing-package") == ""

    runtime_utils.clear_installed_package_version_cache()


def test_installed_package_version_caches_successful_lookups(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_utils.clear_installed_package_version_cache()
    version_calls: list[str] = []

    def fake_version(package_name: str) -> str:
        version_calls.append(package_name)
        return f"{package_name}-1.0"

    monkeypatch.setattr(runtime_utils.importlib.metadata, "version", fake_version)

    assert runtime_utils.installed_package_version("mlx") == "mlx-1.0"
    assert runtime_utils.installed_package_version("mlx") == "mlx-1.0"
    assert runtime_utils.installed_package_version("mlx-lm") == "mlx-lm-1.0"
    assert runtime_utils.installed_package_version("mlx") == "mlx-1.0"

    assert version_calls == ["mlx", "mlx-lm"]

    runtime_utils.clear_installed_package_version_cache()


def test_installed_package_version_caches_missing_lookups(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_utils.clear_installed_package_version_cache()
    version_calls = 0

    def fake_version(package_name: str) -> str:
        nonlocal version_calls
        version_calls += 1
        _ = package_name
        raise importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(runtime_utils.importlib.metadata, "version", fake_version)

    assert runtime_utils.installed_package_version("missing-package") == ""
    assert runtime_utils.installed_package_version("missing-package") == ""
    assert version_calls == 1

    runtime_utils.clear_installed_package_version_cache()


def test_estimate_model_weight_resident_bytes_uses_indexed_unique_shards(tmp_path) -> None:
    bundle = tmp_path / "indexed-model"
    bundle.mkdir()
    shard_a = bundle / "model-00001-of-00002.safetensors"
    shard_b = bundle / "model-00002-of-00002.safetensors"
    shard_a.write_bytes(b"a" * 7)
    shard_b.write_bytes(b"b" * 11)
    (bundle / "model.safetensors.index.json").write_text(
        json.dumps(
            {
                "weight_map": {
                    "layers.0.weight": shard_a.name,
                    "layers.empty.weight": "",
                    "layers.1.weight": shard_b.name,
                    "layers.2.weight": shard_a.name,
                }
            }
        ),
        encoding="utf-8",
    )
    (bundle / "tokenizer.json").write_text("{}", encoding="utf-8")

    assert runtime_utils.estimate_model_weight_resident_bytes(str(bundle)) == 18


def test_estimate_model_weight_resident_bytes_falls_back_to_top_level_weights(tmp_path) -> None:
    bundle = tmp_path / "flat-model"
    bundle.mkdir()
    (bundle / "model.safetensors.index.json").write_text("{not-json", encoding="utf-8")
    (bundle / "model.safetensors").write_bytes(b"weights")
    (bundle / "adapter.npz").write_bytes(b"adapter")
    (bundle / "README.md").write_text("ignore", encoding="utf-8")
    nested = bundle / "nested"
    nested.mkdir()
    (nested / "ignored.safetensors").write_bytes(b"ignored")

    assert runtime_utils.estimate_model_weight_resident_bytes(str(bundle)) == len(b"weightsadapter")


def test_top_level_weight_file_bytes_streams_iterdir_entries(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = tmp_path / "flat-model"
    bundle.mkdir()
    (bundle / "model.safetensors").write_bytes(b"weights")
    (bundle / "adapter.npz").write_bytes(b"adapter-bytes")
    (bundle / "README.md").write_text("ignore", encoding="utf-8")
    log: list[str] = []
    original_scandir = runtime_utils.os.scandir

    def fail_iterdir(self: Path):  # pragma: no cover - must stay uncalled for this regression
        raise AssertionError("top-level weight scan should avoid Path.iterdir allocations")

    def tracked_scandir(path: str | os.PathLike[str]) -> os.ScandirIterator[str]:
        assert Path(path) == bundle
        log.append("scandir")
        return original_scandir(path)

    def fail_splitext(path: str):  # pragma: no cover - must stay uncalled for this regression
        raise AssertionError("top-level weight scan should avoid splitext allocation")

    monkeypatch.setattr(runtime_utils.Path, "iterdir", fail_iterdir)
    monkeypatch.setattr(runtime_utils.os.path, "splitext", fail_splitext)
    monkeypatch.setattr(runtime_utils.os, "scandir", tracked_scandir)

    assert runtime_utils._top_level_weight_file_bytes(bundle) == len(b"weightsadapter-bytes")
    assert log == ["scandir"]


def test_top_level_weight_file_bytes_handles_direntry_non_files_and_errors() -> None:
    class FakeStat:
        st_size = 13

    class FakeEntry:
        def __init__(
            self,
            name: str,
            *,
            is_file: bool = True,
            is_file_raises: bool = False,
            stat_raises: bool = False,
        ) -> None:
            self.name = name
            self._is_file = is_file
            self._is_file_raises = is_file_raises
            self._stat_raises = stat_raises

        def is_file(self) -> bool:
            if self._is_file_raises:
                raise OSError("entry unavailable")
            return self._is_file

        def stat(self) -> FakeStat:
            if self._stat_raises:
                raise OSError("stat unavailable")
            return FakeStat()

    assert runtime_utils._weight_dir_entry_file_size(FakeEntry("README.md")) == 0
    assert runtime_utils._weight_dir_entry_file_size(FakeEntry(".bin")) == 0
    assert runtime_utils._weight_dir_entry_file_size(FakeEntry("nested.safetensors", is_file=False)) == 0
    assert runtime_utils._weight_dir_entry_file_size(FakeEntry("broken.safetensors", is_file_raises=True)) == 0
    assert runtime_utils._weight_dir_entry_file_size(FakeEntry("missing.safetensors", stat_raises=True)) == 0
    assert runtime_utils._weight_dir_entry_file_size(FakeEntry("model.safetensors")) == 13
    assert runtime_utils._weight_dir_entry_file_size(FakeEntry("adapter.SAFEtensors")) == 13


def test_estimate_model_weight_resident_bytes_ignores_malformed_index_and_unreadable_directory(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert runtime_utils.estimate_model_weight_resident_bytes("") == 0
    missing_weight_map = tmp_path / "missing-weight-map"
    missing_weight_map.mkdir()
    (missing_weight_map / "model.safetensors.index.json").write_text("{}", encoding="utf-8")
    assert runtime_utils.estimate_model_weight_resident_bytes(str(missing_weight_map)) == 0

    original_is_file = runtime_utils.Path.is_file
    original_is_dir = runtime_utils.Path.is_dir
    original_scandir = runtime_utils.os.scandir
    unreadable_path = tmp_path / "unreadable"
    unreadable_path.mkdir()

    def fake_is_file(path):
        if path == unreadable_path:
            raise OSError("no file check")
        return original_is_file(path)

    def fake_is_dir(path):
        if path == missing_weight_map:
            return True
        return original_is_dir(path)

    def fake_scandir(path):
        if Path(path) == missing_weight_map:
            raise OSError("no list")
        return original_scandir(path)

    monkeypatch.setattr(runtime_utils.Path, "is_file", fake_is_file)
    monkeypatch.setattr(runtime_utils.Path, "is_dir", fake_is_dir)
    monkeypatch.setattr(runtime_utils.os, "scandir", fake_scandir)

    assert runtime_utils.estimate_model_weight_resident_bytes(str(unreadable_path)) == 0
    assert runtime_utils.estimate_model_weight_resident_bytes(str(missing_weight_map)) == 0
    assert runtime_utils.estimate_model_weight_resident_bytes(str(tmp_path)) == 0


def test_estimate_model_weight_resident_bytes_handles_file_missing_and_stat_errors(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    weight_file = tmp_path / "model.safetensors"
    weight_file.write_bytes(b"abc")
    suffix_only = tmp_path / ".bin"
    suffix_only.write_bytes(b"suffix-only")
    assert runtime_utils.estimate_model_weight_resident_bytes(str(weight_file)) == 3
    assert runtime_utils.estimate_model_weight_resident_bytes(str(suffix_only)) == 0
    assert runtime_utils.estimate_model_weight_resident_bytes(str(tmp_path / "missing")) == 0

    original_stat = runtime_utils.Path.stat

    def fake_stat(path):
        if path == weight_file:
            raise OSError("no stat")
        return original_stat(path)

    monkeypatch.setattr(runtime_utils.Path, "stat", fake_stat)

    assert runtime_utils.estimate_model_weight_resident_bytes(str(weight_file)) == 0
