from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

from packages.protocol.python.worker.v1 import common_pb2
from worker.model_registry import catalog as catalog_module
from worker.model_registry.catalog import (
    WorkerModelCatalog,
    _apply_registry_identity_metadata,
    _config_positive_int,
    _default_embedding_family_for_backend,
    _gemma4_mtp_assistant_metadata,
    _gemma4_index_has_vision_weights,
    _has_mlx_signal,
    _has_model_weight_files,
    _hf_cache_repo_id,
    _hf_cache_revision,
    _hf_cache_revision_map,
    _infer_embedding_identity,
    _is_hf_cache_pruned_subtree,
    _is_hf_cache_snapshot_dir,
    _load_json_dict_file,
    _local_model_id,
    _metadata_payload_has_mlx_signal,
    _read_text_prefix,
    _text_layer_count,
    _text_lora_support_metadata,
)


def _write_registry_manifest(
    variant_dir: Path,
    *,
    model_id: str,
    model_kind: str = "text",
    quant_profile_id: str = "q4",
    max_context: int = 8192,
    ext: dict[str, str] | None = None,
    manifest_fields: dict[str, object] | None = None,
) -> None:
    variant_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "schema_version": "melix.model_registry_manifest.v1",
        "model_id": model_id,
        "model_kind": model_kind,
        "quant_profile_id": quant_profile_id,
        "max_context": max_context,
        "ext": ext or {},
    }
    if manifest_fields:
        payload.update(manifest_fields)
    (variant_dir / "manifest.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _expected_root_id(root: Path) -> str:
    digest = hashlib.sha1(os.fspath(root.resolve()).encode("utf-8")).hexdigest()[:12]
    return f"root-{digest}"


def _write_model_config(variant_dir: Path, payload: dict[str, object]) -> None:
    variant_dir.mkdir(parents=True, exist_ok=True)
    (variant_dir / "config.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _write_weight_index(variant_dir: Path, payload: dict[str, object]) -> None:
    variant_dir.mkdir(parents=True, exist_ok=True)
    (variant_dir / "model.safetensors.index.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _write_processor_config(variant_dir: Path, payload: dict[str, object]) -> None:
    variant_dir.mkdir(parents=True, exist_ok=True)
    (variant_dir / "processor_config.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _write_weights(variant_dir: Path) -> None:
    variant_dir.mkdir(parents=True, exist_ok=True)
    (variant_dir / "model.safetensors").write_bytes(b"weights")


def test_read_text_prefix_reads_only_requested_prefix(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "README.md"
    target.write_text("placeholder", encoding="utf-8")
    read_sizes: list[int] = []

    class _Reader:
        def __enter__(self) -> _Reader:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def read(self, size: int = -1) -> str:
            read_sizes.append(size)
            if size == -1:
                raise AssertionError("expected bounded prefix read")
            return "library_name: mlx\nEXTRA"[:size]

    def fake_open(self: Path, mode: str = "r", *args: object, **kwargs: object) -> _Reader:
        assert self == target
        assert mode == "r"
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["errors"] == "ignore"
        return _Reader()

    monkeypatch.setattr(Path, "open", fake_open)

    assert _read_text_prefix(target, max_chars=17) == "library_name: mlx"
    assert read_sizes == [17]



def test_read_text_prefix_returns_empty_string_on_open_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "README.md"
    target.write_text("placeholder", encoding="utf-8")
    text_prefix_cache: dict[Path, tuple[int, int, int, int, str]] = {}

    def fake_open(self: Path, mode: str = "r", *args: object, **kwargs: object) -> object:
        assert self == target
        raise OSError("boom")

    monkeypatch.setattr(Path, "open", fake_open)

    assert _read_text_prefix(target, text_prefix_cache=text_prefix_cache) == ""
    assert text_prefix_cache == {}



def test_read_text_prefix_returns_empty_string_and_clears_cache_for_non_file_path(tmp_path: Path) -> None:
    target = tmp_path / "README.d"
    target.mkdir()
    text_prefix_cache: dict[Path, tuple[int, int, int, int, str]] = {
        target: (1, 2, 3, 4, "stale payload")
    }

    assert _read_text_prefix(target, text_prefix_cache=text_prefix_cache) == ""
    assert text_prefix_cache == {}



def test_read_text_prefix_uses_stat_result_without_path_is_file_call(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "README.md"
    target.write_text("library_name: mlx\n", encoding="utf-8")
    original_is_file = Path.is_file

    def fail_is_file(self: Path) -> bool:
        if self == target:
            raise AssertionError("expected file-type detection from stat_result")
        return original_is_file(self)

    monkeypatch.setattr(Path, "is_file", fail_is_file)

    assert _read_text_prefix(target) == "library_name: mlx\n"



def test_load_json_dict_file_returns_empty_and_clears_cache_for_non_file_path(tmp_path: Path) -> None:
    target = tmp_path / "config.json"
    target.mkdir()
    json_cache: dict[Path, tuple[int, int, dict[str, object]]] = {
        target: (1, 2, {"stale": True})
    }

    assert _load_json_dict_file(target, json_cache=json_cache) == {}
    assert json_cache == {}



def test_load_json_dict_file_reads_json_bytes_without_text_decode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "config.json"
    target.write_bytes(b'{"model_type":"qwen3","library_name":"mlx"}\n')
    json_cache: dict[Path, tuple[int, int, dict[str, object]]] = {}
    read_bytes_calls: list[Path] = []
    original_read_bytes = Path.read_bytes

    def tracking_read_bytes(self: Path) -> bytes:
        if self == target:
            read_bytes_calls.append(self)
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_text", pytest.fail)
    monkeypatch.setattr(Path, "read_bytes", tracking_read_bytes)

    assert _load_json_dict_file(target, json_cache=json_cache) == {
        "model_type": "qwen3",
        "library_name": "mlx",
    }
    assert _load_json_dict_file(target, json_cache=json_cache) == {
        "model_type": "qwen3",
        "library_name": "mlx",
    }
    assert read_bytes_calls == [target]



def test_read_text_prefix_does_not_cache_transient_open_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "README.md"
    target.write_text("library_name: mlx\n", encoding="utf-8")
    text_prefix_cache: dict[Path, tuple[int, int, int, int, str]] = {}
    open_attempts: list[str] = []

    class _Reader:
        def __init__(self, payload: str) -> None:
            self._payload = payload

        def __enter__(self) -> _Reader:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def read(self, size: int = -1) -> str:
            return self._payload[:size]

    def fake_open(self: Path, mode: str = "r", *args: object, **kwargs: object) -> _Reader:
        assert self == target
        open_attempts.append(mode)
        if len(open_attempts) == 1:
            raise OSError("transient boom")
        return _Reader("library_name: mlx\n")

    monkeypatch.setattr(Path, "open", fake_open)

    assert _read_text_prefix(target, text_prefix_cache=text_prefix_cache) == ""
    assert text_prefix_cache == {}

    assert _read_text_prefix(target, text_prefix_cache=text_prefix_cache) == "library_name: mlx\n"
    assert target in text_prefix_cache

    assert _read_text_prefix(target, text_prefix_cache=text_prefix_cache) == "library_name: mlx\n"
    assert open_attempts == ["r", "r"]



def test_read_text_prefix_invalidates_cache_when_stat_mode_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "README.md"
    target.write_text("library_name: mlx\n", encoding="utf-8")
    text_prefix_cache: dict[Path, tuple[int, int, int, int, str]] = {}
    open_attempts: list[str] = []
    stat_modes = [0o100644, 0o100200]

    class _Reader:
        def __enter__(self) -> _Reader:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def read(self, size: int = -1) -> str:
            return "library_name: mlx\n"[:size]

    original_stat = Path.stat

    def fake_stat(self: Path, *args: object, **kwargs: object):
        stat_result = original_stat(self, *args, **kwargs)
        if self != target:
            return stat_result
        mode = stat_modes[min(len(open_attempts), len(stat_modes) - 1)]
        return os.stat_result((mode, *stat_result[1:]))

    def fake_open(self: Path, mode: str = "r", *args: object, **kwargs: object) -> _Reader:
        assert self == target
        open_attempts.append(mode)
        return _Reader()

    monkeypatch.setattr(Path, "stat", fake_stat)
    monkeypatch.setattr(Path, "open", fake_open)

    assert _read_text_prefix(target, text_prefix_cache=text_prefix_cache) == "library_name: mlx\n"
    assert _read_text_prefix(target, text_prefix_cache=text_prefix_cache) == "library_name: mlx\n"
    assert open_attempts == ["r", "r"]



def test_has_mlx_signal_returns_false_without_repo_hint_or_metadata(tmp_path: Path) -> None:
    model_dir = tmp_path / "plain-transformers-model"
    model_dir.mkdir()
    assert _has_mlx_signal(model_dir=model_dir, repo_id="google/bert-base") is False



def test_has_mlx_signal_detects_metadata_signal_from_readme(tmp_path: Path) -> None:
    model_dir = tmp_path / "plain-transformers-model"
    model_dir.mkdir()
    (model_dir / "README.md").write_text("---\nlibrary_name: mlx\n---\n", encoding="utf-8")

    assert _has_mlx_signal(model_dir=model_dir, repo_id="google/bert-base") is True



def test_has_mlx_signal_stops_after_first_matching_metadata_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "plain-transformers-model"
    model_dir.mkdir()
    calls: list[str] = []

    def fake_read_text_prefix(
        path: Path,
        *,
        max_chars: int = 16_384,
        text_prefix_cache: dict[Path, tuple[int, int, int, int, str]] | None = None,
    ) -> str:
        calls.append(path.name)
        if path.name == "README.md":
            return "---\nlibrary_name: mlx\n---\n"
        raise AssertionError("metadata scan should short-circuit after README.md")

    monkeypatch.setattr(catalog_module, "_read_text_prefix", fake_read_text_prefix)

    assert _has_mlx_signal(model_dir=model_dir, repo_id="google/bert-base") is True
    assert calls == ["README.md"]



def test_has_mlx_signal_falls_back_to_config_text_for_empty_supplied_payload(tmp_path: Path) -> None:
    model_dir = tmp_path / "plain-transformers-model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text('{"library_name": "mlx"\n', encoding="utf-8")

    assert _has_mlx_signal(model_dir=model_dir, repo_id="google/bert-base", config_payload={}) is True



def test_has_mlx_signal_skips_config_text_fallback_for_nonempty_payload_without_mlx_signal(tmp_path: Path) -> None:
    model_dir = tmp_path / "plain-transformers-model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text('{"library_name": "mlx"\n', encoding="utf-8")

    assert _has_mlx_signal(
        model_dir=model_dir,
        repo_id="google/bert-base",
        config_payload={"model_type": "bert"},
    ) is False



def test_has_mlx_signal_falls_back_to_config_text_for_unserializable_nonempty_payload(tmp_path: Path) -> None:
    model_dir = tmp_path / "plain-transformers-model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text('{"library_name": "mlx"\n', encoding="utf-8")

    assert _has_mlx_signal(
        model_dir=model_dir,
        repo_id="google/bert-base",
        config_payload={"tags": {"mlx"}},
    ) is True



def test_metadata_payload_has_mlx_signal_does_not_request_sorted_json(monkeypatch: pytest.MonkeyPatch) -> None:
    kwargs_seen: list[dict[str, object]] = []
    original_dumps = catalog_module.json.dumps

    def fake_dumps(payload: object, *args: object, **kwargs: object) -> str:
        kwargs_seen.append(dict(kwargs))
        return original_dumps(payload, *args, **kwargs)

    monkeypatch.setattr(catalog_module.json, "dumps", fake_dumps)

    assert _metadata_payload_has_mlx_signal({"library_name": "mlx", "tags": ["text"]}) is True
    assert kwargs_seen == [{}]



def test_has_mlx_signal_config_payload_fast_path_avoids_json_dump(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "plain-transformers-model"
    model_dir.mkdir()

    def fail_dumps(*args: object, **kwargs: object) -> str:  # pragma: no cover - sentinel
        raise AssertionError("direct config metadata signal should avoid json.dumps")

    monkeypatch.setattr(catalog_module.json, "dumps", fail_dumps)

    assert _has_mlx_signal(
        model_dir=model_dir,
        repo_id="google/bert-base",
        config_payload={"architectures": ["Qwen3ForCausalLM"], "library_name": "mlx"},
    ) is True
    assert _has_mlx_signal(
        model_dir=model_dir,
        repo_id="google/bert-base",
        config_payload={"tags": ["text", " MLX "]},
    ) is True



def test_metadata_payload_has_mlx_signal_returns_false_for_unserializable_payload() -> None:
    assert _metadata_payload_has_mlx_signal({"tags": {"mlx"}}) is False



def test_has_model_weight_files_uses_os_scandir_single_pass_without_path_glob_or_iterdir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "hf-snapshot"
    model_dir.mkdir()

    class _FakeDirEntry:
        def __init__(self, name: str, *, is_file_result: bool) -> None:
            self.name = name
            self._is_file_result = is_file_result

        def is_file(self) -> bool:
            return self._is_file_result

    scandir_calls: list[str] = []

    class _FakeScandir:
        def __enter__(self) -> _FakeScandir:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def __iter__(self):
            return iter(
                [
                    _FakeDirEntry("config.json", is_file_result=True),
                    _FakeDirEntry("model.safetensors", is_file_result=True),
                ]
            )

    def fake_scandir(path: str):
        scandir_calls.append(path)
        assert path == os.fspath(model_dir)
        return _FakeScandir()

    def fail_iterdir(self: Path):
        if self == model_dir:
            raise AssertionError("expected os.scandir single-pass directory scan")
        return iter(())

    def fail_glob(self: Path, pattern: str):
        if self == model_dir:
            raise AssertionError("expected os.scandir single-pass directory scan")
        return []

    monkeypatch.setattr(os, "scandir", fake_scandir)
    monkeypatch.setattr(Path, "iterdir", fail_iterdir)
    monkeypatch.setattr(Path, "glob", fail_glob)

    assert _has_model_weight_files(model_dir) is True
    assert scandir_calls == [os.fspath(model_dir)]


def test_has_model_weight_files_requires_indexed_safetensor_shards(tmp_path: Path) -> None:
    model_dir = tmp_path / "indexed-model"
    model_dir.mkdir()
    (model_dir / "model.safetensors.index.json").write_text(
        json.dumps(
            {
                "metadata": {},
                "weight_map": {
                    "model.embed_tokens.weight": "model-00001-of-00002.safetensors",
                    "model.layers.0.self_attn.q_proj.weight": "model-00002-of-00002.safetensors",
                },
            }
        ),
        encoding="utf-8",
    )
    (model_dir / "model-00001-of-00002.safetensors").write_bytes(b"weights")

    assert _has_model_weight_files(model_dir) is False

    (model_dir / "model-00002-of-00002.safetensors").write_bytes(b"weights")

    assert _has_model_weight_files(model_dir) is True


def test_huggingface_cache_snapshot_skips_incomplete_indexed_weights(tmp_path: Path) -> None:
    cache_root = tmp_path / "hub"
    snapshot_dir = cache_root / "models--org--demo-mlx" / "snapshots" / "abc123"
    snapshot_dir.mkdir(parents=True)
    (cache_root / "models--org--demo-mlx" / "refs").mkdir()
    (cache_root / "models--org--demo-mlx" / "refs" / "main").write_text("abc123\n", encoding="utf-8")
    (snapshot_dir / "config.json").write_text('{"model_type":"qwen3"}\n', encoding="utf-8")
    (snapshot_dir / "tokenizer.json").write_text("{}\n", encoding="utf-8")
    (snapshot_dir / "README.md").write_text("---\nlibrary_name: mlx\n---\n", encoding="utf-8")
    (snapshot_dir / "model.safetensors.index.json").write_text(
        json.dumps({"weight_map": {"model.embed_tokens.weight": "model-00001-of-00001.safetensors"}}),
        encoding="utf-8",
    )

    catalog = WorkerModelCatalog(
        environment={
            "HOME": str(tmp_path),
            "MELIX_MODEL_ROOTS": str(cache_root),
        }
    )

    assert [model.model_id for model in catalog.registry_snapshot(rescan=True).models] == []

    (snapshot_dir / "model-00001-of-00001.safetensors").write_bytes(b"weights")

    assert [model.model_id for model in catalog.registry_snapshot(rescan=True).models] == ["org/demo-mlx"]



def test_has_model_weight_files_returns_false_when_scandir_raises_oserror(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    model_dir = tmp_path / "unreadable-model"
    model_dir.mkdir()

    original_scandir = os.scandir

    def fake_scandir(path: str):
        if path == os.fspath(model_dir):
            raise OSError("boom")
        return original_scandir(path)

    monkeypatch.setattr(os, "scandir", fake_scandir)

    assert _has_model_weight_files(model_dir) is False



def test_has_model_weight_files_skips_unreadable_candidate_entries_and_finds_later_valid_weight(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "partially-unreadable-model"
    model_dir.mkdir()
    unreadable_weight = model_dir / "broken.safetensors"
    unreadable_weight.write_bytes(b"broken")
    valid_weight = model_dir / "model.npz"
    valid_weight.write_bytes(b"weights")

    class _FakeDirEntry:
        def __init__(self, name: str, *, error: OSError | None = None, is_file_result: bool = False) -> None:
            self.name = name
            self._error = error
            self._is_file_result = is_file_result

        def is_file(self) -> bool:
            if self._error is not None:
                raise self._error
            return self._is_file_result

    class _FakeScandir:
        def __enter__(self) -> _FakeScandir:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def __iter__(self):
            return iter(
                [
                    _FakeDirEntry(unreadable_weight.name, error=OSError("boom")),
                    _FakeDirEntry(valid_weight.name, is_file_result=True),
                ]
            )

    def fake_scandir(path: str):
        assert path == os.fspath(model_dir)
        return _FakeScandir()

    monkeypatch.setattr(os, "scandir", fake_scandir)

    assert _has_model_weight_files(model_dir) is True



def test_registry_catalog_helper_fallback_paths(tmp_path: Path) -> None:
    refs_dir = tmp_path / "models--org--demo" / "refs"
    refs_dir.mkdir(parents=True)
    unreadable_ref = refs_dir / "main"
    unreadable_ref.write_text("abc123\n", encoding="utf-8")

    original_read_text = Path.read_text

    def fake_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == unreadable_ref:
            raise OSError("boom")
        return original_read_text(self, *args, **kwargs)

    assert _hf_cache_repo_id(Path("repo-without-prefix")) is None
    assert _hf_cache_repo_id(Path("models--missing-suffix")) is None
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(Path, "read_text", fake_read_text)
        assert _hf_cache_revision_map(refs_dir.parent) == {}
        assert _hf_cache_revision(refs_dir.parent, "abc123") == "abc123"
    finally:
        monkeypatch.undo()
    assert _is_hf_cache_snapshot_dir(tmp_path / "other-root", refs_dir) is False
    assert _local_model_id(tmp_path / "other-root", refs_dir) == refs_dir.name


def test_hf_cache_revision_map_reads_refs_once_and_preserves_nested_ref_names(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache_repo_dir = tmp_path / "models--org--demo"
    refs_dir = cache_repo_dir / "refs"
    nested_ref = refs_dir / "heads" / "main"
    nested_ref.parent.mkdir(parents=True, exist_ok=True)
    nested_ref.write_text("abc123\n", encoding="utf-8")
    stable_ref = refs_dir / "tags" / "stable"
    stable_ref.parent.mkdir(parents=True, exist_ok=True)
    stable_ref.write_text("def456\n", encoding="utf-8")

    original_read_text = Path.read_text
    read_paths: list[Path] = []

    def tracking_read_text(self: Path, *args: object, **kwargs: object) -> str:
        read_paths.append(self)
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", tracking_read_text)

    revision_map = _hf_cache_revision_map(cache_repo_dir)

    assert revision_map == {"abc123": "heads/main", "def456": "tags/stable"}
    assert read_paths == [nested_ref, stable_ref]
    assert _hf_cache_revision(cache_repo_dir, "abc123", revision_map=revision_map) == "heads/main"
    assert _hf_cache_revision(cache_repo_dir, "missing", revision_map=revision_map) == "missing"



def test_hf_cache_revision_map_reads_only_needed_snapshot_refs_and_can_early_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_repo_dir = tmp_path / "models--org--demo"
    refs_dir = cache_repo_dir / "refs"
    (refs_dir / "heads" / "feature").parent.mkdir(parents=True, exist_ok=True)
    (refs_dir / "heads" / "feature").write_text("def456\n", encoding="utf-8")
    target_ref = refs_dir / "heads" / "main"
    target_ref.write_text("abc123\n", encoding="utf-8")
    (refs_dir / "tags" / "release").parent.mkdir(parents=True, exist_ok=True)
    (refs_dir / "tags" / "release").write_text("999999\n", encoding="utf-8")

    original_read_text = Path.read_text
    original_scandir = os.scandir
    read_paths: list[Path] = []
    scandir_calls: list[str] = []

    def tracking_read_text(self: Path, *args: object, **kwargs: object) -> str:
        read_paths.append(self)
        return original_read_text(self, *args, **kwargs)

    def tracking_scandir(path: str):
        scandir_calls.append(path)
        return original_scandir(path)

    monkeypatch.setattr(Path, "read_text", tracking_read_text)
    monkeypatch.setattr(os, "scandir", tracking_scandir)

    revision_map = _hf_cache_revision_map(cache_repo_dir, snapshot_ids={"abc123"})

    assert revision_map == {"abc123": "heads/main"}
    assert read_paths == [refs_dir / "heads" / "feature", refs_dir / "heads" / "main"]
    assert scandir_calls == [os.fspath(refs_dir), os.fspath(refs_dir / "heads")]


def test_hf_cache_revision_map_uses_recursive_scandir_without_rglob(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_repo_dir = tmp_path / "models--org--demo"
    refs_dir = cache_repo_dir / "refs"
    nested_ref = refs_dir / "heads" / "main"
    nested_ref.parent.mkdir(parents=True, exist_ok=True)
    nested_ref.write_text("abc123\n", encoding="utf-8")
    stable_ref = refs_dir / "tags" / "stable"
    stable_ref.parent.mkdir(parents=True, exist_ok=True)
    stable_ref.write_text("def456\n", encoding="utf-8")

    original_scandir = os.scandir
    scandir_calls: list[str] = []

    def tracking_scandir(path: str):
        scandir_calls.append(path)
        return original_scandir(path)

    def fail_rglob(self: Path, pattern: str):
        raise AssertionError("expected os.scandir-based recursive scan")

    monkeypatch.setattr(os, "scandir", tracking_scandir)
    monkeypatch.setattr(Path, "rglob", fail_rglob)

    assert _hf_cache_revision_map(cache_repo_dir) == {"abc123": "heads/main", "def456": "tags/stable"}
    assert scandir_calls == [os.fspath(refs_dir), os.fspath(refs_dir / "heads"), os.fspath(refs_dir / "tags")]



def test_hf_cache_revision_map_returns_empty_mapping_when_ref_enumeration_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache_repo_dir = tmp_path / "models--org--demo"
    refs_dir = cache_repo_dir / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)

    original_scandir = os.scandir

    def fake_scandir(path: str):
        if path == os.fspath(refs_dir):
            raise OSError("boom")
        return original_scandir(path)

    monkeypatch.setattr(os, "scandir", fake_scandir)

    assert _hf_cache_revision_map(cache_repo_dir) == {}



def test_hf_cache_revision_map_returns_empty_mapping_when_entry_type_probe_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_repo_dir = tmp_path / "models--org--demo"
    refs_dir = cache_repo_dir / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)

    class _BrokenDirEntry:
        name = "broken"

        def is_dir(self) -> bool:
            raise OSError("boom")

        def is_file(self) -> bool:
            raise AssertionError("is_file should not be reached after is_dir failure")

    class _FakeScandir:
        def __enter__(self) -> _FakeScandir:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def __iter__(self):
            return iter([_BrokenDirEntry()])

    original_scandir = os.scandir

    def fake_scandir(path: str):
        if path == os.fspath(refs_dir):
            return _FakeScandir()
        return original_scandir(path)

    monkeypatch.setattr(os, "scandir", fake_scandir)

    assert _hf_cache_revision_map(cache_repo_dir) == {}



def test_hf_cache_revision_map_skips_blank_snapshot_ids(tmp_path: Path) -> None:
    cache_repo_dir = tmp_path / "models--org--demo"
    refs_dir = cache_repo_dir / "refs"
    blank_ref = refs_dir / "heads" / "blank"
    blank_ref.parent.mkdir(parents=True, exist_ok=True)
    blank_ref.write_text("\n", encoding="utf-8")
    valid_ref = refs_dir / "tags" / "stable"
    valid_ref.parent.mkdir(parents=True, exist_ok=True)
    valid_ref.write_text("def456\n", encoding="utf-8")

    assert _hf_cache_revision_map(cache_repo_dir) == {"def456": "tags/stable"}


def test_apply_registry_identity_metadata_rejects_missing_required_parts() -> None:
    model = common_pb2.ModelSpec()
    model.ext["melix.registry_organization_id"] = "org"
    model.ext["melix.registry_model_name"] = ""
    model.ext["melix.registry_variant_id"] = "main"

    assert _apply_registry_identity_metadata(model, relative_parts=("org", "model", "variant")) is True

    broken = common_pb2.ModelSpec()
    broken.ext["melix.registry_organization_id"] = "org"
    broken.ext["melix.registry_model_name"] = ""
    broken.ext["melix.registry_variant_id"] = ""
    assert _apply_registry_identity_metadata(broken, relative_parts=("", "", "")) is False



def test_text_lora_support_metadata_covers_moe_and_fallback_families() -> None:
    mixtral = _text_lora_support_metadata("mixtral", moe_enabled=True, expert_count_source="config")
    unknown = _text_lora_support_metadata("custom-family", moe_enabled=False, expert_count_source="")

    assert mixtral["melix.lora.family_kind"] == "moe"
    assert mixtral["melix.lora.default_target_preset"] == "attention"
    assert unknown["melix.lora.family_kind"] == "advanced_text"
    assert unknown["melix.lora.training_ready"] == "false"



def test_embedding_identity_helpers_cover_directory_name_variants() -> None:
    assert _infer_embedding_identity("models/mxbai-large")["family_id"] == "mxbai-embed"
    assert _infer_embedding_identity("models/bge-m3")["family_id"] == "bge-m3"
    assert _infer_embedding_identity("models/xlm-r-base")["family_id"] == "xlmr"
    assert _infer_embedding_identity("models/bert-base")["family_id"] == "bert"
    assert _default_embedding_family_for_backend("xlmr-v1", "bert") == "xlmr"
    assert _default_embedding_family_for_backend("bert-v1", "not-known") == "bert"



def test_catalog_overlay_registration_and_snapshot_payload(tmp_path: Path) -> None:
    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(tmp_path)})
    overlay = common_pb2.ModelSpec(model_id="overlay-model", model_path=str(tmp_path / "overlay"), model_kind="text")

    registered = catalog.register_model(overlay)
    payload = catalog.registry_snapshot_payload()

    assert registered.model_id == "overlay-model"
    assert catalog.get("overlay-model") is registered
    assert "scanned_at_unix_ms" in payload
    assert isinstance(payload["models"], list)
    assert catalog.remove_model("overlay-model") is True
    assert catalog.remove_model("overlay-model") is False



def test_registry_snapshot_skips_runtime_rebuild_when_cached_snapshot_is_current(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(tmp_path), "HOME": str(tmp_path / "home")})
    rebuild_calls: list[str] = []
    original_rebuild = catalog._rebuild_runtime_models

    def tracking_rebuild(*, snapshot: catalog_module.RegistrySnapshot | None = None) -> None:
        rebuild_calls.append("rebuild")
        original_rebuild(snapshot=snapshot)

    monkeypatch.setattr(catalog, "_rebuild_runtime_models", tracking_rebuild)

    warm_snapshot = catalog.registry_snapshot()
    current_models = catalog._models
    assert rebuild_calls == ["rebuild"]

    assert catalog.registry_snapshot() is warm_snapshot
    assert catalog.registry_snapshot_payload()["models"] == []
    assert rebuild_calls == ["rebuild"]
    assert catalog._models is current_models

    overlay = common_pb2.ModelSpec(model_id="overlay-model", model_path=str(tmp_path / "overlay"), model_kind="text")
    catalog.register_model(overlay)
    assert rebuild_calls == ["rebuild", "rebuild"]
    assert catalog.registry_snapshot() is warm_snapshot
    assert rebuild_calls == ["rebuild", "rebuild"]
    assert catalog.remove_model("overlay-model") is True
    assert rebuild_calls == ["rebuild", "rebuild", "rebuild"]

    rescanned_snapshot = catalog.registry_snapshot(rescan=True)
    assert rescanned_snapshot is not warm_snapshot
    assert rebuild_calls == ["rebuild", "rebuild", "rebuild", "rebuild"]



def test_catalog_rescan_prunes_text_prefix_cache_for_disappeared_metadata_path(tmp_path: Path) -> None:
    root = tmp_path / "root"
    model_dir = root / "plain-local"
    _write_model_config(model_dir, {"model_type": "qwen3", "architectures": ["Qwen3ForCausalLM"]})
    _write_weights(model_dir)
    readme_path = model_dir / "README.md"
    readme_path.write_text("---\nlibrary_name: mlx\n---\n", encoding="utf-8")

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root), "HOME": str(tmp_path / "home")})

    assert readme_path.resolve() in catalog._text_prefix_cache

    shutil.rmtree(model_dir)
    catalog.registry_snapshot(rescan=True)

    assert readme_path.resolve() not in catalog._text_prefix_cache



def test_catalog_scan_helpers_skip_invalid_huggingface_and_unreadable_directories(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "root"
    invalid_repo = root / "models--missing-snapshots"
    invalid_repo.mkdir(parents=True)
    valid_repo = root / "models--mlx-community--Tiny"
    snapshots_dir = valid_repo / "snapshots"
    snapshots_dir.mkdir(parents=True)
    (snapshots_dir / "note.txt").write_text("not a directory", encoding="utf-8")
    unreadable_plain = root / "unreadable-plain"
    unreadable_plain.mkdir(parents=True)
    unreadable_manifest = root / "unreadable-manifest"
    unreadable_manifest.mkdir(parents=True)

    original_iterdir = Path.iterdir

    def fake_iterdir(self: Path):
        if self in {unreadable_plain, unreadable_manifest}:
            raise OSError("boom")
        return original_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root), "HOME": str(tmp_path / "home")})
    assert list(catalog._scan_huggingface_cache_models(root=root)) == []
    assert unreadable_plain not in WorkerModelCatalog._iter_plain_local_model_dirs(root)
    assert list(WorkerModelCatalog._iter_registry_manifest_paths(root)) == []


def test_scan_huggingface_cache_models_uses_os_scandir_without_glob_or_iterdir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    cache_repo_dir = root / "models--mlx-community--Tiny"
    snapshots_dir = cache_repo_dir / "snapshots"
    refs_dir = cache_repo_dir / "refs"
    snapshot_dir = snapshots_dir / "abc123"
    _write_model_config(snapshot_dir, {"model_type": "qwen3", "architectures": ["Qwen3ForCausalLM"]})
    _write_weights(snapshot_dir)
    (snapshot_dir / "README.md").write_text("---\nlibrary_name: mlx\ntags:\n- mlx\n---\n", encoding="utf-8")
    refs_dir.mkdir(parents=True, exist_ok=True)
    (refs_dir / "main").write_text("abc123\n", encoding="utf-8")

    original_scandir = os.scandir
    scandir_calls: list[str] = []

    def tracking_scandir(path: str):
        scandir_calls.append(path)
        return original_scandir(path)

    def fail_glob(self: Path, pattern: str):
        if self in {root, snapshots_dir}:
            raise AssertionError("expected os.scandir-based Hugging Face cache traversal")
        return []

    def fail_iterdir(self: Path):
        if self == snapshots_dir:
            raise AssertionError("expected os.scandir-based Hugging Face cache traversal")
        return iter(())

    monkeypatch.setattr(os, "scandir", tracking_scandir)
    monkeypatch.setattr(Path, "glob", fail_glob)
    monkeypatch.setattr(Path, "iterdir", fail_iterdir)

    catalog = WorkerModelCatalog.__new__(WorkerModelCatalog)
    catalog._text_prefix_cache = {}

    models = list(catalog._scan_huggingface_cache_models(root=root))

    assert [model.model_id for model in models] == ["mlx-community/Tiny"]
    assert os.fspath(root) in scandir_calls
    assert os.fspath(snapshots_dir) in scandir_calls


def test_registry_directory_iterators_use_os_scandir_and_preserve_sorted_depth_first_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    manifest_dir = root / "alpha-provider" / "AlphaModel" / "q4"
    _write_registry_manifest(manifest_dir, model_id="alpha-provider/AlphaModel/q4")
    plain_a = root / "beta-local-a"
    plain_b = root / "beta-local-b"
    _write_model_config(plain_a, {"model_type": "qwen3"})
    _write_model_config(plain_b, {"model_type": "qwen3"})

    original_scandir = os.scandir
    scandir_calls: list[str] = []

    def tracking_scandir(path: str):
        scandir_calls.append(path)
        return original_scandir(path)

    def fail_iterdir(self: Path):
        if self == root or self == root / "alpha-provider":
            raise AssertionError("expected os.scandir-based directory traversal")
        return iter(())

    monkeypatch.setattr(os, "scandir", tracking_scandir)
    monkeypatch.setattr(Path, "iterdir", fail_iterdir)

    plain_dirs = list(WorkerModelCatalog._iter_plain_local_model_dirs(root))
    manifest_paths = list(WorkerModelCatalog._iter_registry_manifest_paths(root))

    assert plain_dirs == [plain_a.resolve(), plain_b.resolve()]
    assert manifest_paths == [manifest_dir.resolve() / "manifest.json"]
    assert os.fspath(root.resolve()) in scandir_calls



def test_registry_root_tree_detects_descriptors_during_single_scandir_pass(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    manifest_dir = root / "manifest-model"
    config_dir = root / "plain-model"
    _write_registry_manifest(manifest_dir, model_id="manifest-model")
    _write_model_config(config_dir, {"model_type": "qwen3"})

    original_is_file = Path.is_file

    def fail_descriptor_is_file(self: Path) -> bool:
        if self.name in {"manifest.json", "config.json"}:
            raise AssertionError("expected descriptor detection from os.scandir entries")
        return original_is_file(self)

    monkeypatch.setattr(Path, "is_file", fail_descriptor_is_file)

    manifest_paths, plain_dirs = WorkerModelCatalog._scan_registry_root_tree(root)

    assert manifest_paths == (manifest_dir.resolve() / "manifest.json",)
    assert plain_dirs == (config_dir.resolve(),)



def test_registry_root_tree_records_plain_local_weight_presence_during_single_scandir_pass(tmp_path: Path) -> None:
    root = tmp_path / "root"
    config_dir = root / "plain-model"
    _write_model_config(config_dir, {"model_type": "qwen3"})
    _write_weights(config_dir)

    manifest_paths, plain_scans, hf_cache_repo_dirs = WorkerModelCatalog._scan_registry_root_tree_with_hf_repos(root)

    assert manifest_paths == ()
    assert hf_cache_repo_dirs == ()
    assert [(scan.model_dir, scan.has_model_weight_files, scan.has_generation_config) for scan in plain_scans] == [
        (config_dir.resolve(), True, False)
    ]
    assert not hasattr(plain_scans[0], "__dict__")



def test_registry_root_tree_skips_hf_prune_relative_probe_for_plain_dirs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    for index in range(3):
        config_dir = root / f"plain-model-{index}"
        _write_model_config(config_dir, {"model_type": "qwen3"})
        _write_weights(config_dir)

    def fail_plain_prune_probe(root_path: Path, current: Path) -> bool:  # pragma: no cover
        raise AssertionError(f"plain registry scans should not run HF prune relative checks: {root_path} {current}")

    monkeypatch.setattr(catalog_module, "_is_hf_cache_pruned_subtree", fail_plain_prune_probe)

    manifest_paths, plain_scans, hf_cache_repo_dirs = WorkerModelCatalog._scan_registry_root_tree_with_hf_repos(root)

    assert manifest_paths == ()
    assert hf_cache_repo_dirs == ()
    assert [scan.model_dir for scan in plain_scans] == [
        (root / "plain-model-0").resolve(),
        (root / "plain-model-1").resolve(),
        (root / "plain-model-2").resolve(),
    ]



def test_registry_snapshot_reuses_plain_local_tree_scan_and_config_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    model_dir = root / "plain-model"
    _write_model_config(
        model_dir,
        {
            "model_type": "qwen3",
            "architectures": ["Qwen3ForCausalLM"],
            "library_name": "mlx",
        },
    )
    _write_weights(model_dir)

    original_scandir = os.scandir
    scandir_calls: list[str] = []

    def tracking_scandir(path: str):
        scandir_calls.append(path)
        return original_scandir(path)

    original_load_model_config_payload = catalog_module._load_model_config_payload
    config_load_count = 0

    def tracking_load_model_config_payload(
        model_dir_path: Path,
        *,
        json_cache: dict[Path, tuple[int, int, dict[str, object]]] | None = None,
    ) -> dict[str, object]:
        nonlocal config_load_count
        if model_dir_path.resolve() == model_dir.resolve():
            config_load_count += 1
        return original_load_model_config_payload(model_dir_path, json_cache=json_cache)

    monkeypatch.setattr(os, "scandir", tracking_scandir)
    monkeypatch.setattr(catalog_module, "_load_model_config_payload", tracking_load_model_config_payload)

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root), "HOME": str(tmp_path / "home")})
    snapshot = catalog.registry_snapshot()

    assert [model.model_id for model in snapshot.models] == ["plain-model"]
    assert scandir_calls.count(os.fspath(model_dir.resolve())) == 1
    assert config_load_count == 1
    dev_vlm = WorkerModelCatalog.dev_vlm_model()
    assert dev_vlm.ext["melix.capability.supported_modalities"] == "text,image,video"

    tensor_cases_root = tmp_path / "tensor-index-cases"
    test_registry_snapshot_promotes_gemma4_text_manifest_to_vlm_text_backed(tensor_cases_root / "text-manifest")
    test_registry_snapshot_keeps_multimodal_gemma4_manifest_in_multimodal_mode(tensor_cases_root / "multimodal")
    test_registry_snapshot_promotes_gemma4_from_text_config_with_processor_hint(tensor_cases_root / "processor")
    test_registry_snapshot_uses_gemma4_weight_index_to_keep_multimodal_mode(tensor_cases_root / "weight-index")
    test_registry_snapshot_uses_tensor_index_to_fall_back_for_config_only_vision(tensor_cases_root / "config-only")
    test_registry_snapshot_uses_tensor_index_to_enable_vision_and_audio_routes(tensor_cases_root / "many-modal")
    test_registry_snapshot_falls_back_when_declared_vision_lacks_tensor_evidence(tensor_cases_root / "mismatch")
    test_registry_snapshot_malformed_tensor_index_falls_back_with_warning(tensor_cases_root / "malformed")
    _assert_tensor_index_defensive_branches(tensor_cases_root / "defensive", monkeypatch)
    test_registry_snapshot_records_multimodal_processor_and_nested_config_receipts(
        tensor_cases_root / "processor-receipts"
    )
    test_registry_snapshot_accepts_metadata_matched_renamed_projector_receipt(
        tensor_cases_root / "renamed-projector"
    )
    test_registry_snapshot_rejects_cross_family_projector_receipt(tensor_cases_root / "cross-family")
    test_registry_snapshot_rejects_missing_projector_receipt(tensor_cases_root / "missing-projector")
    test_registry_snapshot_rejects_generic_adapter_as_renamed_projector(tensor_cases_root / "generic-adapter")
    test_registry_snapshot_records_draft_model_type_optional_head_receipt(tensor_cases_root / "draft-model-type")
    test_multimodal_receipt_helpers_handle_defensive_branches(tensor_cases_root / "receipt-defensive")



def test_registry_snapshot_reuses_hf_cache_config_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    snapshot_dir = root / "models--mlx-community--Tiny" / "snapshots" / "abc123"
    _write_model_config(
        snapshot_dir,
        {
            "model_type": "qwen3",
            "architectures": ["Qwen3ForCausalLM"],
            "library_name": "mlx",
        },
    )
    _write_weights(snapshot_dir)
    refs_dir = snapshot_dir.parent.parent / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    (refs_dir / "main").write_text("abc123\n", encoding="utf-8")

    original_load_model_config_payload = catalog_module._load_model_config_payload
    config_load_count = 0

    def tracking_load_model_config_payload(
        model_dir_path: Path,
        *,
        json_cache: dict[Path, tuple[int, int, dict[str, object]]] | None = None,
    ) -> dict[str, object]:
        nonlocal config_load_count
        if model_dir_path.resolve() == snapshot_dir.resolve():
            config_load_count += 1
        return original_load_model_config_payload(model_dir_path, json_cache=json_cache)

    monkeypatch.setattr(catalog_module, "_load_model_config_payload", tracking_load_model_config_payload)

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root), "HOME": str(tmp_path / "home")})
    snapshot = catalog.registry_snapshot()

    assert [model.model_id for model in snapshot.models] == ["mlx-community/Tiny"]
    assert config_load_count == 1



def test_raw_model_spec_loads_config_payload_when_not_supplied(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "plain-model"
    _write_model_config(
        model_dir,
        {
            "model_type": "qwen3",
            "architectures": ["Qwen3ForCausalLM"],
            "library_name": "mlx",
        },
    )
    _write_weights(model_dir)

    original_load_model_config_payload = catalog_module._load_model_config_payload
    config_load_count = 0

    def tracking_load_model_config_payload(
        model_dir_path: Path,
        *,
        json_cache: dict[Path, tuple[int, int, dict[str, object]]] | None = None,
    ) -> dict[str, object]:
        nonlocal config_load_count
        if model_dir_path.resolve() == model_dir.resolve():
            config_load_count += 1
        return original_load_model_config_payload(model_dir_path, json_cache=json_cache)

    monkeypatch.setattr(catalog_module, "_load_model_config_payload", tracking_load_model_config_payload)

    catalog = WorkerModelCatalog(environment={"HOME": str(tmp_path / "home")})
    model = catalog._raw_model_spec(
        model_id="plain-model",
        model_dir=model_dir.resolve(),
        revision="local",
        source_kind="local_mlx_directory",
        metadata={},
    )

    assert model.model_id == "plain-model"
    assert model.model_kind == "text"
    assert model.ext["melix.model_path"] == str(model_dir.resolve())
    assert config_load_count == 1



def test_registry_snapshot_does_not_stat_plain_local_manifest_after_tree_scan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    model_dir = root / "plain-model"
    manifest_probe = (model_dir / "manifest.json").resolve()
    _write_model_config(
        model_dir,
        {
            "model_type": "qwen3",
            "architectures": ["Qwen3ForCausalLM"],
            "library_name": "mlx",
        },
    )
    _write_weights(model_dir)

    original_is_file = Path.is_file
    manifest_probe_calls = 0

    def tracking_is_file(self: Path) -> bool:
        nonlocal manifest_probe_calls
        if self.resolve() == manifest_probe:
            manifest_probe_calls += 1
        return original_is_file(self)

    assert tracking_is_file(manifest_probe) is False
    manifest_probe_calls = 0
    monkeypatch.setattr(Path, "is_file", tracking_is_file)

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root), "HOME": str(tmp_path / "home")})
    snapshot = catalog.registry_snapshot()

    assert [model.model_id for model in snapshot.models] == ["plain-model"]
    assert manifest_probe_calls == 0



def test_registry_snapshot_does_not_stat_missing_plain_local_generation_config_after_tree_scan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    model_dir = root / "plain-model"
    generation_probe = (model_dir / "generation_config.json").resolve()
    _write_model_config(
        model_dir,
        {
            "model_type": "qwen3",
            "architectures": ["Qwen3ForCausalLM"],
            "library_name": "mlx",
        },
    )
    _write_weights(model_dir)

    original_stat = Path.stat
    generation_probe_calls = 0

    def tracking_stat(self: Path, *args: object, **kwargs: object) -> os.stat_result:
        nonlocal generation_probe_calls
        if os.fspath(self) == os.fspath(generation_probe):
            generation_probe_calls += 1
        return original_stat(self, *args, **kwargs)

    try:
        tracking_stat(generation_probe)
    except FileNotFoundError:
        pass
    assert generation_probe_calls == 1
    generation_probe_calls = 0
    monkeypatch.setattr(Path, "stat", tracking_stat)

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root), "HOME": str(tmp_path / "home")})
    snapshot = catalog.registry_snapshot()

    assert [model.model_id for model in snapshot.models] == ["plain-model"]
    assert generation_probe_calls == 0



def test_registry_snapshot_imports_plain_local_generation_config_when_seen_during_tree_scan(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    model_dir = root / "plain-model"
    _write_model_config(
        model_dir,
        {
            "model_type": "qwen3",
            "architectures": ["Qwen3ForCausalLM"],
            "library_name": "mlx",
        },
    )
    _write_weights(model_dir)
    (model_dir / "generation_config.json").write_text(
        json.dumps({"temperature": 0.2, "top_p": 0.9, "max_new_tokens": 128}) + "\n",
        encoding="utf-8",
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root), "HOME": str(tmp_path / "home")})
    snapshot = catalog.registry_snapshot()

    assert [model.model_id for model in snapshot.models] == ["plain-model"]
    model = snapshot.models[0]
    assert model.ext["melix.generation_config.temperature"] == "0.2"
    assert model.ext["melix.generation_config.top_p"] == "0.9"
    assert model.ext["melix.generation_config.max_tokens"] == "128"
    assert model.ext["melix.generation_config.source"].endswith("generation_config.json")


def test_registry_snapshot_skips_invalid_depth_manifests_without_parsing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    invalid_manifest_dir = root / "manifest-model"
    valid_manifest_dir = root / "provider" / "org" / "demo" / "q4"
    _write_registry_manifest(invalid_manifest_dir, model_id="invalid-manifest")
    _write_registry_manifest(valid_manifest_dir, model_id="provider/org/demo/q4")

    original_parse_registry_manifest = WorkerModelCatalog._parse_registry_manifest
    parsed_manifest_paths: list[Path] = []

    def tracking_parse_registry_manifest(self: WorkerModelCatalog, manifest_path: Path):
        parsed_manifest_paths.append(manifest_path.resolve())
        return original_parse_registry_manifest(self, manifest_path)

    monkeypatch.setattr(WorkerModelCatalog, "_parse_registry_manifest", tracking_parse_registry_manifest)

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root), "HOME": str(tmp_path / "home")})

    assert [model.model_id for model in catalog.registry_snapshot().models] == ["provider/org/demo/q4"]
    assert invalid_manifest_dir.resolve() / "manifest.json" not in parsed_manifest_paths
    assert parsed_manifest_paths == [valid_manifest_dir.resolve() / "manifest.json"]



def test_registry_snapshot_skips_plain_local_config_dirs_without_weights(tmp_path: Path) -> None:
    root = tmp_path / "root"
    model_dir = root / "plain-model"
    _write_model_config(
        model_dir,
        {
            "model_type": "qwen3",
            "architectures": ["Qwen3ForCausalLM"],
            "library_name": "mlx",
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root), "HOME": str(tmp_path / "home")})

    assert catalog.registry_snapshot().models == ()



def test_registry_root_tree_prunes_hf_cache_snapshot_and_refs_subtrees(tmp_path: Path) -> None:
    root = tmp_path / "root"
    snapshot_dir = root / "models--mlx-community--Tiny" / "snapshots" / "abc123"
    refs_dir = root / "models--mlx-community--Tiny" / "refs"
    plain_model_dir = root / "plain-local"
    _write_model_config(snapshot_dir, {"model_type": "qwen3", "architectures": ["Qwen3ForCausalLM"]})
    _write_weights(snapshot_dir)
    (snapshot_dir / "README.md").write_text("library_name: mlx\n", encoding="utf-8")
    refs_dir.mkdir(parents=True, exist_ok=True)
    (refs_dir / "main").write_text("abc123\n", encoding="utf-8")
    _write_model_config(plain_model_dir, {"model_type": "qwen3"})

    plain_dirs = list(WorkerModelCatalog._iter_plain_local_model_dirs(root))
    manifest_paths = list(WorkerModelCatalog._iter_registry_manifest_paths(root))

    assert plain_dirs == [plain_model_dir.resolve()]
    assert snapshot_dir.resolve() not in plain_dirs
    assert manifest_paths == []



def test_registry_root_tree_does_not_prune_invalid_models_prefix_dirs(tmp_path: Path) -> None:
    root = tmp_path / "root"
    invalid_snapshot_dir = root / "models--custom" / "snapshots" / "v1"
    invalid_refs_dir = root / "models--custom" / "refs"
    _write_model_config(invalid_snapshot_dir, {"model_type": "qwen3", "architectures": ["Qwen3ForCausalLM"]})
    _write_weights(invalid_snapshot_dir)
    (invalid_snapshot_dir / "README.md").write_text("library_name: mlx\n", encoding="utf-8")
    invalid_refs_dir.mkdir(parents=True, exist_ok=True)
    (invalid_refs_dir / "main").write_text("v1\n", encoding="utf-8")

    plain_dirs = list(WorkerModelCatalog._iter_plain_local_model_dirs(root))
    manifest_paths = list(WorkerModelCatalog._iter_registry_manifest_paths(root))

    assert _is_hf_cache_pruned_subtree(root.resolve(), (root / "models--custom" / "snapshots").resolve()) is False
    assert _is_hf_cache_pruned_subtree(root.resolve(), invalid_refs_dir.resolve()) is False
    assert _is_hf_cache_snapshot_dir(root.resolve(), invalid_snapshot_dir.resolve()) is False
    assert invalid_snapshot_dir.resolve() in plain_dirs
    assert manifest_paths == []

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": os.fspath(root)})
    snapshot = catalog.registry_snapshot()

    assert [model.model_id for model in snapshot.models] == ["models--custom/snapshots/v1"]
    model = snapshot.models[0]
    assert model.model_path == str(invalid_snapshot_dir.resolve())
    assert model.ext["melix.source_kind"] == "local_mlx_directory"
    assert "melix.hf_repo_id" not in model.ext


def test_is_hf_cache_pruned_subtree_returns_false_for_paths_outside_root(tmp_path: Path) -> None:
    root = (tmp_path / "root").resolve()
    outside_snapshot_dir = (tmp_path / "outside" / "models--mlx-community--Tiny" / "snapshots").resolve()

    assert _is_hf_cache_pruned_subtree(root, outside_snapshot_dir) is False


def test_registry_snapshot_reuses_single_tree_walk_for_plain_manifest_and_hf_cache_repos(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    manifest_dir = root / "alpha-provider" / "AlphaModel" / "q4"
    _write_registry_manifest(manifest_dir, model_id="alpha-provider/AlphaModel/q4")
    hf_snapshot_dir = root / "models--mlx-community--Tiny" / "snapshots" / "abc123"
    _write_model_config(hf_snapshot_dir, {"model_type": "qwen3", "architectures": ["Qwen3ForCausalLM"]})
    _write_weights(hf_snapshot_dir)
    (hf_snapshot_dir / "README.md").write_text("library_name: mlx\n", encoding="utf-8")
    hf_refs_dir = hf_snapshot_dir.parent.parent / "refs"
    hf_refs_dir.mkdir(parents=True, exist_ok=True)
    (hf_refs_dir / "main").write_text("abc123\n", encoding="utf-8")

    original_scandir = os.scandir
    scandir_calls: list[str] = []

    def tracking_scandir(path: str):
        scandir_calls.append(path)
        return original_scandir(path)

    monkeypatch.setattr(os, "scandir", tracking_scandir)

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": os.fspath(root)})

    snapshot = catalog.registry_snapshot()

    discovered_ids = [model.model_id for model in snapshot.models]
    resolved_root = os.fspath(root.resolve())
    provider_dir = os.fspath((root / "alpha-provider").resolve())
    hf_cache_dir = os.fspath((root / "models--mlx-community--Tiny").resolve())
    hf_snapshots_dir = os.fspath((root / "models--mlx-community--Tiny" / "snapshots").resolve())

    assert discovered_ids == ["alpha-provider/AlphaModel/q4", "mlx-community/Tiny"]
    assert scandir_calls.count(resolved_root) == 1
    assert scandir_calls.count(provider_dir) == 1
    assert hf_cache_dir not in scandir_calls
    assert hf_snapshots_dir in scandir_calls



def test_dev_models_honor_configured_text_embedding_and_rerank_overrides() -> None:
    text_model = WorkerModelCatalog.dev_text_model(
        {
            "MELIX_DEV_TEXT_FAMILY_ID": "llama",
            "MELIX_DEV_TEXT_ROUTE_KIND": "python_text",
        }
    )
    embedding_model = WorkerModelCatalog.dev_embedding_model(
        {
            "MELIX_DEV_EMBED_FAMILY_ID": "xlmr",
        }
    )
    rerank_model = WorkerModelCatalog.dev_rerank_model(
        {
            "MELIX_DEV_RERANK_FAMILY_ID": "causal-lm",
            "MELIX_DEV_RERANK_YES_NO_LABELS": "affirmative,negative",
        }
    )

    assert text_model.ext["text_family_id"] == "llama"
    assert text_model.ext["melix.capability.route_kind"] == "python_text"
    assert embedding_model.ext["embedding_family_id"] == "xlmr"
    assert embedding_model.ext["embedding_backend_id"] == "xlmr-v1"
    assert rerank_model.ext["rerank_yes_no_labels"] == "affirmative,negative"



def test_registry_snapshot_discovers_mlx_models_from_default_huggingface_cache(tmp_path: Path) -> None:
    home = tmp_path / "home"
    hf_cache = home / ".cache" / "huggingface" / "hub"
    snapshot_dir = hf_cache / "models--mlx-community--Qwen3-0.6B-4bit" / "snapshots" / "abc123"
    refs_dir = hf_cache / "models--mlx-community--Qwen3-0.6B-4bit" / "refs"
    _write_model_config(snapshot_dir, {"model_type": "qwen3", "architectures": ["Qwen3ForCausalLM"]})
    _write_weights(snapshot_dir)
    refs_dir.mkdir(parents=True, exist_ok=True)
    (refs_dir / "main").write_text("abc123\n", encoding="utf-8")

    non_mlx_snapshot = hf_cache / "models--google--bert-base" / "snapshots" / "def456"
    _write_model_config(non_mlx_snapshot, {"model_type": "bert"})
    _write_weights(non_mlx_snapshot)

    catalog = WorkerModelCatalog(environment={"HOME": str(home)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}

    assert [root.root_path for root in snapshot.roots] == [str(hf_cache.resolve())]
    assert "mlx-community/Qwen3-0.6B-4bit" in discovered
    assert "google/bert-base" not in discovered
    model = discovered["mlx-community/Qwen3-0.6B-4bit"]
    assert model.model_path == str(snapshot_dir.resolve())
    assert model.revision == "main"
    assert model.ext["melix.source_kind"] == "hf_cache_snapshot"
    assert model.ext["melix.hf_repo_id"] == "mlx-community/Qwen3-0.6B-4bit"
    assert model.ext["melix.hf_revision"] == "main"
    assert model.ext["melix.model_path"] == str(snapshot_dir.resolve())
    assert "melix.registry_descriptor_path" not in model.ext


def test_registry_snapshot_discovers_existing_default_managed_model_root(tmp_path: Path) -> None:
    home = tmp_path / "home"
    managed_root = home / ".melix" / "models" / "default-managed"
    _write_registry_manifest(
        managed_root / "huggingface" / "mlx-community" / "ManagedTiny" / "main",
        model_id="mlx-community/ManagedTiny",
        ext={"source_root": "default-managed"},
    )

    catalog = WorkerModelCatalog(environment={"HOME": str(home)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}

    assert [root.root_path for root in snapshot.roots] == [str(managed_root.resolve())]
    assert discovered["mlx-community/ManagedTiny"].ext["source_root"] == "default-managed"
    assert discovered["mlx-community/ManagedTiny"].ext["melix.registry_root_order"] == "1"


def test_registry_snapshot_rescan_reuses_cached_text_prefixes_for_unchanged_mlx_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    model_dir = root / "plain-qwen-model"
    model_dir.mkdir(parents=True)
    _write_weights(model_dir)
    (model_dir / "README.md").write_text("---\nlibrary_name: mlx\n---\n", encoding="utf-8")
    (model_dir / "config.json").write_text('{"architectures": ["Qwen3ForCausalLM"]}\n', encoding="utf-8")
    (model_dir / "model_index.json").write_text('{"tags": ["mlx"]}\n', encoding="utf-8")

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    metadata_paths = {
        model_dir / "README.md": 0,
        model_dir / "config.json": 0,
        model_dir / "model_index.json": 0,
    }
    original_open = Path.open

    def tracking_open(self: Path, *args: object, **kwargs: object):
        mode = args[0] if args else kwargs.get("mode", "r")
        if self in metadata_paths and isinstance(mode, str) and mode.startswith("r"):
            metadata_paths[self] += 1
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)

    first_snapshot = catalog.registry_snapshot(rescan=True)
    second_snapshot = catalog.registry_snapshot(rescan=True)

    assert any(model.model_id == "plain-qwen-model" for model in first_snapshot.models)
    assert any(model.model_id == "plain-qwen-model" for model in second_snapshot.models)
    assert metadata_paths == {
        model_dir / "README.md": 0,
        model_dir / "config.json": 0,
        model_dir / "model_index.json": 0,
    }



def test_registry_snapshot_rescan_invalidates_cached_text_prefix_when_metadata_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    model_dir = root / "plain-qwen-model"
    model_dir.mkdir(parents=True)
    _write_weights(model_dir)
    (model_dir / "README.md").write_text("plain readme\n", encoding="utf-8")
    (model_dir / "config.json").write_text('{"architectures": ["Qwen3ForCausalLM"]}\n', encoding="utf-8")
    (model_dir / "model_index.json").write_text('{"scheduler": "ddim"}\n', encoding="utf-8")

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})
    assert all(model.model_id != "plain-qwen-model" for model in catalog.registry_snapshot().models)

    metadata_paths = {
        model_dir / "README.md": 0,
        model_dir / "config.json": 0,
        model_dir / "model_index.json": 0,
    }
    original_open = Path.open

    def tracking_open(self: Path, *args: object, **kwargs: object):
        mode = args[0] if args else kwargs.get("mode", "r")
        if self in metadata_paths and isinstance(mode, str) and mode.startswith("r"):
            metadata_paths[self] += 1
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)

    (model_dir / "README.md").write_text("---\nlibrary_name: mlx\n---\n", encoding="utf-8")

    snapshot = catalog.registry_snapshot(rescan=True)

    assert any(model.model_id == "plain-qwen-model" for model in snapshot.models)
    assert metadata_paths[model_dir / "README.md"] == 1
    assert metadata_paths[model_dir / "model_index.json"] == 0



def test_registry_snapshot_rescan_reuses_cached_text_prefixes_for_unchanged_hf_cache_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    hf_cache = home / ".cache" / "huggingface" / "hub"
    snapshot_dir = hf_cache / "models--google--bert-base" / "snapshots" / "abc123"
    _write_model_config(snapshot_dir, {"model_type": "bert"})
    _write_weights(snapshot_dir)
    (snapshot_dir / "README.md").write_text("---\nlibrary_name: mlx\n---\n", encoding="utf-8")
    (snapshot_dir / "model_index.json").write_text('{"tags": ["mlx"]}\n', encoding="utf-8")

    catalog = WorkerModelCatalog(environment={"HOME": str(home)})

    metadata_paths = {
        snapshot_dir / "README.md": 0,
        snapshot_dir / "config.json": 0,
        snapshot_dir / "model_index.json": 0,
    }
    original_open = Path.open

    def tracking_open(self: Path, *args: object, **kwargs: object):
        mode = args[0] if args else kwargs.get("mode", "r")
        if self in metadata_paths and isinstance(mode, str) and mode.startswith("r"):
            metadata_paths[self] += 1
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)

    first_snapshot = catalog.registry_snapshot(rescan=True)
    second_snapshot = catalog.registry_snapshot(rescan=True)

    assert any(model.model_id == "google/bert-base" for model in first_snapshot.models)
    assert any(model.model_id == "google/bert-base" for model in second_snapshot.models)
    assert metadata_paths == {
        snapshot_dir / "README.md": 0,
        snapshot_dir / "config.json": 0,
        snapshot_dir / "model_index.json": 0,
    }



def test_registry_snapshot_rescan_invalidates_cached_text_prefix_for_changed_hf_cache_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    hf_cache = home / ".cache" / "huggingface" / "hub"
    snapshot_dir = hf_cache / "models--google--bert-base" / "snapshots" / "abc123"
    _write_model_config(snapshot_dir, {"model_type": "bert"})
    _write_weights(snapshot_dir)
    (snapshot_dir / "README.md").write_text("plain readme\n", encoding="utf-8")
    (snapshot_dir / "model_index.json").write_text('{"scheduler": "ddim"}\n', encoding="utf-8")

    catalog = WorkerModelCatalog(environment={"HOME": str(home)})
    assert all(model.model_id != "google/bert-base" for model in catalog.registry_snapshot().models)

    metadata_open_counts = {
        snapshot_dir / "README.md": 0,
        snapshot_dir / "model_index.json": 0,
    }
    config_read_count = 0
    original_open = Path.open
    original_read_text = Path.read_text

    def tracking_open(self: Path, *args: object, **kwargs: object):
        mode = args[0] if args else kwargs.get("mode", "r")
        if self in metadata_open_counts and isinstance(mode, str) and mode.startswith("r"):
            metadata_open_counts[self] += 1
        return original_open(self, *args, **kwargs)

    def tracking_read_text(self: Path, *args: object, **kwargs: object) -> str:
        nonlocal config_read_count
        if self == snapshot_dir / "config.json":
            config_read_count += 1
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)
    monkeypatch.setattr(Path, "read_text", tracking_read_text)

    (snapshot_dir / "README.md").write_text("---\nlibrary_name: mlx\n---\n", encoding="utf-8")

    snapshot = catalog.registry_snapshot(rescan=True)
    discovered = {model.model_id: model for model in snapshot.models}

    assert discovered["google/bert-base"].model_path == str(snapshot_dir.resolve())
    assert discovered["google/bert-base"].ext["melix.source_kind"] == "hf_cache_snapshot"
    assert metadata_open_counts[snapshot_dir / "README.md"] == 1
    assert config_read_count == 0
    assert metadata_open_counts[snapshot_dir / "model_index.json"] == 0



def test_registry_snapshot_rescan_reuses_cached_json_payloads_for_unchanged_registry_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "Tiny" / "4bit"
    _write_registry_manifest(variant_dir, model_id="mlx-community/Tiny/4bit")
    _write_model_config(variant_dir, {"model_type": "qwen3", "architectures": ["Qwen3ForCausalLM"]})
    (variant_dir / "generation_config.json").write_text(
        json.dumps({"temperature": 0.2, "top_p": 0.9}) + "\n",
        encoding="utf-8",
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    manifest_path = variant_dir / "manifest.json"
    config_path = variant_dir / "config.json"
    generation_path = variant_dir / "generation_config.json"
    original_read_text = Path.read_text
    read_counts: dict[Path, int] = {
        manifest_path: 0,
        config_path: 0,
        generation_path: 0,
    }

    def tracking_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self in read_counts:
            read_counts[self] += 1
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", tracking_read_text)

    catalog.registry_snapshot(rescan=True)
    catalog.registry_snapshot(rescan=True)

    assert read_counts == {
        manifest_path: 0,
        config_path: 0,
        generation_path: 0,
    }


def test_registry_snapshot_rescan_invalidates_cached_manifest_payload_when_file_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "Tiny" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/Tiny/4bit",
        max_context=8192,
    )
    _write_model_config(variant_dir, {"model_type": "qwen3", "architectures": ["Qwen3ForCausalLM"]})

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    manifest_path = variant_dir / "manifest.json"
    original_read_bytes = Path.read_bytes
    manifest_reads = 0

    def tracking_read_bytes(self: Path, *args: object, **kwargs: object) -> bytes:
        nonlocal manifest_reads
        if self == manifest_path:
            manifest_reads += 1
        return original_read_bytes(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", tracking_read_bytes)

    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/Tiny/4bit",
        max_context=16384,
    )

    snapshot = catalog.registry_snapshot(rescan=True)
    discovered = {model.model_id: model for model in snapshot.models}

    assert discovered["mlx-community/Tiny/4bit"].max_context == 16384
    assert manifest_reads == 1


def test_scan_huggingface_cache_models_reads_ref_files_once_per_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "root"
    cache_repo_dir = root / "models--mlx-community--Tiny"
    refs_dir = cache_repo_dir / "refs" / "heads"
    refs_dir.mkdir(parents=True, exist_ok=True)
    snapshot_ids = ("abc123", "def456")
    for snapshot_id in snapshot_ids:
        snapshot_dir = cache_repo_dir / "snapshots" / snapshot_id
        _write_model_config(snapshot_dir, {"model_type": "qwen3", "architectures": ["Qwen3ForCausalLM"]})
        _write_weights(snapshot_dir)
        (snapshot_dir / "README.md").write_text("---\nlibrary_name: mlx\ntags:\n- mlx\n---\n", encoding="utf-8")
        (refs_dir / snapshot_id).write_text(snapshot_id + "\n", encoding="utf-8")

    from worker.model_registry import catalog as catalog_module

    original_revision_map = catalog_module._hf_cache_revision_map
    revision_map_calls: list[Path] = []

    def tracking_revision_map(cache_repo_path: Path, *, snapshot_ids: set[str] | None = None) -> dict[str, str]:
        revision_map_calls.append(cache_repo_path)
        return original_revision_map(
            cache_repo_path,
            snapshot_ids=snapshot_ids,
        )

    monkeypatch.setattr(catalog_module, "_hf_cache_revision_map", tracking_revision_map)

    catalog = WorkerModelCatalog.__new__(WorkerModelCatalog)
    catalog._text_prefix_cache = {}
    models = catalog._scan_huggingface_cache_models(root=root)

    assert [model.revision for model in models] == ["heads/abc123", "heads/def456"]
    assert revision_map_calls == [cache_repo_dir]


def test_registry_snapshot_drops_huggingface_cache_model_after_snapshot_deletion(tmp_path: Path) -> None:
    home = tmp_path / "home"
    hf_cache = home / ".cache" / "huggingface" / "hub"
    snapshot_dir = hf_cache / "models--mlx-community--Qwen3-0.6B-4bit" / "snapshots" / "abc123"
    _write_model_config(snapshot_dir, {"model_type": "qwen3"})
    _write_weights(snapshot_dir)

    catalog = WorkerModelCatalog(environment={"HOME": str(home)})

    initial = {model.model_id for model in catalog.registry_snapshot().models}
    shutil.rmtree(snapshot_dir)
    refreshed = {model.model_id for model in catalog.registry_snapshot(rescan=True).models}

    assert "mlx-community/Qwen3-0.6B-4bit" in initial
    assert "mlx-community/Qwen3-0.6B-4bit" not in refreshed


def test_registry_snapshot_discovers_plain_local_mlx_directory_and_hides_uncertain_directory(tmp_path: Path) -> None:
    root = tmp_path / "roots"
    mlx_dir = root / "local-mlx-model"
    _write_model_config(mlx_dir, {"model_type": "qwen3"})
    _write_weights(mlx_dir)
    (mlx_dir / "README.md").write_text("---\nlibrary_name: mlx\ntags:\n- mlx\n---\n", encoding="utf-8")
    uncertain_dir = root / "plain-transformers-model"
    _write_model_config(uncertain_dir, {"model_type": "qwen3"})
    _write_weights(uncertain_dir)

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}

    assert "local-mlx-model" in discovered
    assert "plain-transformers-model" not in discovered
    model = discovered["local-mlx-model"]
    assert model.model_path == str(mlx_dir.resolve())
    assert model.ext["melix.source_kind"] == "local_mlx_directory"
    assert model.ext["melix.registry_relative_path"] == "local-mlx-model"


def test_registry_snapshot_raw_local_scan_skips_manifest_owned_directories(tmp_path: Path) -> None:
    root = tmp_path / "roots"
    model_dir = root / "mlx-community" / "ManifestOwned" / "main"
    _write_registry_manifest(model_dir, model_id="mlx-community/ManifestOwned/main")
    _write_model_config(model_dir, {"model_type": "qwen3"})
    _write_weights(model_dir)
    (model_dir / "README.md").write_text("---\nlibrary_name: mlx\n---\n", encoding="utf-8")

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    discovered_ids = [model.model_id for model in catalog.registry_snapshot().models]

    assert discovered_ids == ["mlx-community/ManifestOwned/main"]


def test_registry_snapshot_user_root_overrides_default_huggingface_cache_duplicate(tmp_path: Path) -> None:
    home = tmp_path / "home"
    hf_cache = home / ".cache" / "huggingface" / "hub"
    default_snapshot = hf_cache / "models--mlx-community--Tiny" / "snapshots" / "abc123"
    user_root = tmp_path / "user-root"
    user_snapshot = user_root / "models--mlx-community--Tiny" / "snapshots" / "def456"
    _write_model_config(default_snapshot, {"model_type": "qwen3"})
    _write_weights(default_snapshot)
    _write_model_config(user_snapshot, {"model_type": "qwen3_moe"})
    _write_weights(user_snapshot)

    catalog = WorkerModelCatalog(environment={"HOME": str(home), "MELIX_MODEL_ROOTS": str(user_root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    model = discovered["mlx-community/Tiny"]

    assert [root.root_path for root in snapshot.roots] == [str(user_root.resolve()), str(hf_cache.resolve())]
    assert model.model_path == str(user_snapshot.resolve())
    assert model.ext["melix.registry_root_order"] == "1"


def test_registry_snapshot_collects_models_from_ordered_roots_and_keeps_first_duplicate(tmp_path: Path) -> None:
    root_a = tmp_path / "root-a"
    root_b = tmp_path / "root-b"
    duplicate_id = "mlx-community/Qwen2.5-7B-Instruct/4bit"

    _write_registry_manifest(
        root_a / "mlx-community" / "Qwen2.5-7B-Instruct" / "4bit",
        model_id=duplicate_id,
        max_context=16384,
        ext={"source_root": "a"},
    )
    _write_registry_manifest(
        root_b / "mlx-community" / "Qwen2.5-7B-Instruct" / "4bit",
        model_id=duplicate_id,
        max_context=4096,
        ext={"source_root": "b"},
    )
    _write_registry_manifest(
        root_b / "mlx-community" / "Qwen2.5-14B-Instruct" / "8bit",
        model_id="mlx-community/Qwen2.5-14B-Instruct/8bit",
        quant_profile_id="q8",
        max_context=32768,
        ext={"source_root": "b"},
    )

    catalog = WorkerModelCatalog(
        environment={
            "MELIX_MODEL_ROOTS": f"{root_a}{os.pathsep}{root_b}",
        }
    )

    snapshot = catalog.registry_snapshot()

    assert [root.root_id for root in snapshot.roots] == [_expected_root_id(root_a), _expected_root_id(root_b)]
    assert [root.root_order for root in snapshot.roots] == [1, 2]
    discovered = {model.model_id: model for model in snapshot.models}
    assert duplicate_id in discovered
    assert discovered[duplicate_id].max_context == 16384
    assert discovered[duplicate_id].ext["source_root"] == "a"
    assert discovered[duplicate_id].ext["melix.registry_root_id"] == _expected_root_id(root_a)
    assert discovered[duplicate_id].ext["melix.registry_root_order"] == "1"
    assert discovered[duplicate_id].ext["melix.model_path"].endswith("root-a/mlx-community/Qwen2.5-7B-Instruct/4bit")
    assert "mlx-community/Qwen2.5-14B-Instruct/8bit" in discovered
    assert catalog.get(duplicate_id) == discovered[duplicate_id]


def test_registry_snapshot_reports_invalid_roots_without_poisoning_valid_discovery(tmp_path: Path) -> None:
    root_valid = tmp_path / "root-valid"
    root_missing = tmp_path / "root-missing"

    _write_registry_manifest(
        root_valid / "mlx-community" / "Phi-4-mini" / "4bit",
        model_id="mlx-community/Phi-4-mini/4bit",
        ext={"source_root": "valid"},
    )

    catalog = WorkerModelCatalog(
        environment={
            "MELIX_MODEL_ROOTS": f"{root_missing}{os.pathsep}{root_valid}",
        }
    )

    snapshot = catalog.registry_snapshot()

    assert len(snapshot.roots) == 2
    assert snapshot.roots[0].root_id == _expected_root_id(root_missing)
    assert snapshot.roots[0].root_order == 1
    assert snapshot.roots[0].accessible is False
    assert snapshot.roots[0].error_code == "not_found"
    assert snapshot.roots[1].root_id == _expected_root_id(root_valid)
    assert snapshot.roots[1].root_order == 2
    assert snapshot.roots[1].accessible is True
    assert [model.model_id for model in snapshot.models] == ["mlx-community/Phi-4-mini/4bit"]


def test_registry_snapshot_keeps_seed_models_alongside_discovered_entries(tmp_path: Path) -> None:
    root_a = tmp_path / "root-a"
    _write_registry_manifest(
        root_a / "mlx-community" / "Llama-3.2-3B" / "q4",
        model_id="mlx-community/Llama-3.2-3B/q4",
    )

    catalog = WorkerModelCatalog(
        environment={
            "MELIX_MODEL_ROOTS": str(root_a),
        }
    )

    snapshot = catalog.registry_snapshot()
    discovered_ids = {model.model_id for model in snapshot.models}

    assert "mlx-community/Llama-3.2-3B/q4" in discovered_ids
    assert "melix-dev-text" in {model.model_id for model in catalog.all_models()}


def test_registry_snapshot_rescan_refreshes_discovery_and_deduplicates_empty_root_entries(tmp_path: Path) -> None:
    root_a = tmp_path / "root-a"
    root_b = tmp_path / "root-b"
    root_b.mkdir(parents=True, exist_ok=True)

    _write_registry_manifest(
        root_a / "mlx-community" / "Qwen2.5-7B-Instruct" / "4bit",
        model_id="mlx-community/Qwen2.5-7B-Instruct/4bit",
    )

    catalog = WorkerModelCatalog(
        environment={
            "MELIX_MODEL_ROOTS": f"{os.pathsep}{root_a}{os.pathsep}{root_a}{os.pathsep}{root_b}{os.pathsep}",
        }
    )

    initial_snapshot = catalog.registry_snapshot()
    _write_registry_manifest(
        root_b / "mlx-community" / "Qwen2.5-14B-Instruct" / "8bit",
        model_id="mlx-community/Qwen2.5-14B-Instruct/8bit",
        quant_profile_id="q8",
    )
    refreshed_snapshot = catalog.registry_snapshot(rescan=True)

    assert [root.root_path for root in initial_snapshot.roots] == [str(root_a), str(root_b)]
    assert [root.root_path for root in refreshed_snapshot.roots] == [str(root_a), str(root_b)]
    assert [root.root_id for root in initial_snapshot.roots] == [root.root_id for root in refreshed_snapshot.roots]
    assert [model.model_id for model in initial_snapshot.models] == ["mlx-community/Qwen2.5-7B-Instruct/4bit"]
    assert [model.model_id for model in refreshed_snapshot.models] == [
        "mlx-community/Qwen2.5-14B-Instruct/8bit",
        "mlx-community/Qwen2.5-7B-Instruct/4bit",
    ]
    assert catalog.get("mlx-community/Qwen2.5-14B-Instruct/8bit") is not None


def test_registry_snapshot_prefers_configured_roots_before_legacy_managed_root(tmp_path: Path) -> None:
    managed_root = tmp_path / "managed-root"
    user_root = tmp_path / "user-root"
    duplicate_id = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"

    _write_registry_manifest(
        managed_root / "huggingface" / "mlx-community" / "Qwen3.5-0.8B-OptiQ-4bit" / "main",
        model_id=duplicate_id,
        ext={"source_root": "managed"},
    )
    _write_registry_manifest(
        user_root / "huggingface" / "mlx-community" / "Qwen3.5-0.8B-OptiQ-4bit" / "main",
        model_id=duplicate_id,
        ext={"source_root": "user"},
    )

    catalog = WorkerModelCatalog(
        environment={
            "MELIX_MANAGED_MODEL_ROOT": str(managed_root),
            "MELIX_MODEL_ROOTS": str(user_root),
        }
    )

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}

    assert [root.root_path for root in snapshot.roots] == [str(user_root), str(managed_root)]
    assert discovered[duplicate_id].ext["source_root"] == "user"
    assert discovered[duplicate_id].ext["melix.registry_root_order"] == "1"


def test_registry_snapshot_preserves_external_runtime_model_path_from_manifest(tmp_path: Path) -> None:
    managed_root = tmp_path / "managed-root"
    runtime_snapshot = tmp_path / "hf-cache" / "models--mlx-community--Qwen3-0.6B-4bit" / "snapshots" / "abc123"
    descriptor_dir = managed_root / "huggingface" / "mlx-community" / "Qwen3-0.6B-4bit" / "main"
    runtime_snapshot.mkdir(parents=True, exist_ok=True)
    _write_model_config(
        runtime_snapshot,
        {
            "model_type": "qwen3",
            "architectures": ["Qwen3ForCausalLM"],
        },
    )
    _write_registry_manifest(
        descriptor_dir,
        model_id="mlx-community/Qwen3-0.6B-4bit",
        ext={
            "melix.model_path": str(runtime_snapshot / ".." / "abc123"),
            "melix.registry_descriptor_path": str(descriptor_dir),
        },
    )

    catalog = WorkerModelCatalog(
        environment={
            "MELIX_MANAGED_MODEL_ROOT": str(managed_root),
        }
    )

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    model = discovered["mlx-community/Qwen3-0.6B-4bit"]

    assert model.model_path == str(runtime_snapshot.resolve())
    assert model.ext["melix.model_path"] == str(runtime_snapshot.resolve())
    assert model.ext["melix.registry_descriptor_path"] == str(descriptor_dir)
    assert model.ext["melix.registry_relative_path"] == "huggingface/mlx-community/Qwen3-0.6B-4bit/main"
    assert "melix.model_path_missing" not in model.ext
    assert model.ext["detected_architecture"] == "qwen3"


def test_registry_snapshot_marks_missing_external_runtime_model_path(tmp_path: Path) -> None:
    managed_root = tmp_path / "managed-root"
    missing_runtime = tmp_path / "hf-cache" / "models--mlx-community--Tiny" / "snapshots" / "missing"
    descriptor_dir = managed_root / "huggingface" / "mlx-community" / "Tiny" / "main"
    _write_registry_manifest(
        descriptor_dir,
        model_id="mlx-community/Tiny",
        ext={
            "melix.model_path": str(missing_runtime),
            "melix.registry_descriptor_path": str(descriptor_dir),
        },
    )

    catalog = WorkerModelCatalog(
        environment={
            "MELIX_MANAGED_MODEL_ROOT": str(managed_root),
        }
    )

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    model = discovered["mlx-community/Tiny"]

    assert model.model_path == str(missing_runtime.resolve())
    assert model.ext["melix.model_path"] == str(missing_runtime.resolve())
    assert model.ext["melix.model_path_missing"] == "true"


def test_registry_snapshot_ignores_non_string_external_runtime_model_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    managed_root = tmp_path / "managed-root"
    descriptor_dir = managed_root / "huggingface" / "mlx-community" / "Tiny" / "main"
    monkeypatch.chdir(tmp_path)
    (tmp_path / "None").mkdir()
    _write_registry_manifest(
        descriptor_dir,
        model_id="mlx-community/Tiny",
        ext={
            "melix.model_path": None,  # type: ignore[dict-item]
            "melix.registry_descriptor_path": str(descriptor_dir),
        },
    )

    catalog = WorkerModelCatalog(
        environment={
            "MELIX_MANAGED_MODEL_ROOT": str(managed_root),
        }
    )

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    model = discovered["mlx-community/Tiny"]

    assert model.model_path == str(descriptor_dir)
    assert model.ext["melix.model_path"] == str(descriptor_dir)
    assert "melix.model_path_missing" not in model.ext


def test_registry_snapshot_explicit_root_override_reorders_precedence_without_changing_root_identity(
    tmp_path: Path,
) -> None:
    root_a = tmp_path / "root-a"
    root_b = tmp_path / "root-b"
    duplicate_id = "mlx-community/Qwen2.5-7B-Instruct/4bit"

    _write_registry_manifest(
        root_a / "mlx-community" / "Qwen2.5-7B-Instruct" / "4bit",
        model_id=duplicate_id,
        max_context=16384,
        ext={"source_root": "a"},
    )
    _write_registry_manifest(
        root_b / "mlx-community" / "Qwen2.5-7B-Instruct" / "4bit",
        model_id=duplicate_id,
        max_context=4096,
        ext={"source_root": "b"},
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root_a)})

    initial_snapshot = catalog.registry_snapshot()
    reordered_snapshot = catalog.registry_snapshot(
        rescan=True,
        registry_roots=[os.fspath(root_b), os.fspath(root_a)],
    )
    discovered = {model.model_id: model for model in reordered_snapshot.models}

    assert [root.root_id for root in reordered_snapshot.roots] == [_expected_root_id(root_b), _expected_root_id(root_a)]
    assert discovered[duplicate_id].ext["source_root"] == "b"
    assert discovered[duplicate_id].ext["melix.registry_root_id"] == _expected_root_id(root_b)
    assert discovered[duplicate_id].ext["melix.registry_root_order"] == "1"
    assert initial_snapshot.roots[0].root_id == _expected_root_id(root_a)


def test_registry_snapshot_explicit_root_override_keeps_configured_root_before_legacy_managed_root(tmp_path: Path) -> None:
    managed_root = tmp_path / "managed-root"
    user_root = tmp_path / "user-root"
    duplicate_id = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"

    _write_registry_manifest(
        managed_root / "huggingface" / "mlx-community" / "Qwen3.5-0.8B-OptiQ-4bit" / "main",
        model_id=duplicate_id,
        ext={"source_root": "managed"},
    )
    _write_registry_manifest(
        user_root / "huggingface" / "mlx-community" / "Qwen3.5-0.8B-OptiQ-4bit" / "main",
        model_id=duplicate_id,
        ext={"source_root": "user"},
    )

    catalog = WorkerModelCatalog(
        environment={
            "MELIX_MANAGED_MODEL_ROOT": str(managed_root),
            "MELIX_MODEL_ROOTS": str(user_root),
        }
    )

    snapshot = catalog.registry_snapshot(rescan=True, registry_roots=[os.fspath(user_root)])
    discovered = {model.model_id: model for model in snapshot.models}

    assert [root.root_path for root in snapshot.roots] == [str(user_root), str(managed_root)]
    assert discovered[duplicate_id].ext["source_root"] == "user"
    assert discovered[duplicate_id].ext["melix.registry_root_order"] == "1"


def test_registry_snapshot_derives_structured_identity_from_paths_and_sidecar_overrides(tmp_path: Path) -> None:
    root = tmp_path / "root"

    _write_registry_manifest(
        root / "huggingface" / "mlx-community" / "Qwen2.5-7B-Instruct" / "4bit",
        model_id="mlx-community/Qwen2.5-7B-Instruct/4bit",
        manifest_fields={
            "provider_id": "hf-mirror",
            "variant_id": "q4f16",
        },
    )
    _write_registry_manifest(
        root / "mlx-community" / "Phi-4-mini" / "q8",
        model_id="mlx-community/Phi-4-mini/q8",
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    qwen = discovered["mlx-community/Qwen2.5-7B-Instruct/4bit"]
    phi = discovered["mlx-community/Phi-4-mini/q8"]

    assert qwen.ext["melix.registry_provider_id"] == "hf-mirror"
    assert qwen.ext["melix.registry_organization_id"] == "mlx-community"
    assert qwen.ext["melix.registry_model_name"] == "Qwen2.5-7B-Instruct"
    assert qwen.ext["melix.registry_variant_id"] == "q4f16"
    assert qwen.ext["melix.registry_relative_path"] == "huggingface/mlx-community/Qwen2.5-7B-Instruct/4bit"
    assert phi.ext["melix.registry_provider_id"] == ""
    assert phi.ext["melix.registry_organization_id"] == "mlx-community"
    assert phi.ext["melix.registry_model_name"] == "Phi-4-mini"
    assert phi.ext["melix.registry_variant_id"] == "q8"
    assert phi.ext["melix.registry_relative_path"] == "mlx-community/Phi-4-mini/q8"


def test_registry_snapshot_applies_text_family_adapter_metadata_from_local_config(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "Qwen3-MoE-30B-A3B-Instruct" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/Qwen3-MoE-30B-A3B-Instruct/4bit",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "qwen3_moe",
            "rope_scaling": {"type": "yarn", "interleaved": True},
            "num_local_experts": 128,
            "moe_gate_dequant": True,
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    qwen3moe = discovered["mlx-community/Qwen3-MoE-30B-A3B-Instruct/4bit"]

    assert qwen3moe.ext["text_backend_id"] == "mlx_lm"
    assert qwen3moe.ext["text_family_id"] == "qwen3moe"
    assert qwen3moe.ext["model_architecture"] == "qwen3_moe"
    assert qwen3moe.ext["detected_architecture"] == "qwen3_moe"
    assert qwen3moe.ext["detected_family_id"] == "qwen3moe"
    assert qwen3moe.ext["detected_identity_source"] == "config.model_type"
    assert qwen3moe.ext["melix.adapter_set_hash"] == "text-family-qwen3moe"
    assert qwen3moe.ext["melix.capability.route_kind"] == "python_text_compatibility"
    assert qwen3moe.ext["melix.capability.supported_parsers"] == "text,qwen"
    assert qwen3moe.ext["tool_parser_mode"] == "qwen"
    assert qwen3moe.ext["melix.text.attention_profile"] == "gqa"
    assert qwen3moe.ext["melix.text.rope_profile"] == "yarn_interleaved"
    assert qwen3moe.ext["melix.text.moe.enabled"] == "true"
    assert qwen3moe.ext["melix.text.moe.expert_count"] == "128"
    assert qwen3moe.ext["melix.text.moe.expert_count_source"] == "config"
    assert qwen3moe.ext["melix.text.moe.gate_dequant"] == "true"
    assert qwen3moe.ext["melix.lora.family_id"] == "qwen3moe"
    assert qwen3moe.ext["melix.lora.family_kind"] == "moe"
    assert qwen3moe.ext["melix.lora.support_tier"] == "experimental"
    assert qwen3moe.ext["melix.lora.training_ready"] == "true"
    assert qwen3moe.ext["melix.lora.default_target_preset"] == "attention"


def test_registry_snapshot_records_text_config_layer_count_for_text_model(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "Qwen3.5-9B-MLX-8bit" / "main"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/Qwen3.5-9B-MLX-8bit",
        model_kind="text",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "qwen3_5",
            "text_config": {
                "model_type": "qwen3_5_text",
                "num_hidden_layers": 32,
            },
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    model = discovered["mlx-community/Qwen3.5-9B-MLX-8bit"]

    assert model.model_kind == "text"
    assert model.ext["text_layer_count"] == "32"


def test_text_layer_count_metadata_prefers_top_level_count() -> None:
    assert _text_layer_count(
        {
            "num_hidden_layers": 24,
            "text_config": {"num_hidden_layers": 32},
        }
    ) == 24


def test_text_layer_count_metadata_falls_back_to_nested_text_config() -> None:
    assert _text_layer_count(
        {
            "model_type": "qwen3_5",
            "text_config": {"num_hidden_layers": 32},
        }
    ) == 32


def test_registry_snapshot_marks_dflash_draft_metadata_from_local_config(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "z-lab" / "Qwen3.5-27B-DFlash" / "main"
    _write_registry_manifest(
        variant_dir,
        model_id="z-lab/Qwen3.5-27B-DFlash",
        model_kind="text",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "qwen3",
            "architectures": ["DFlashDraftModel"],
            "auto_map": {"AutoModel": "dflash.DFlashDraftModel"},
            "block_size": 8,
            "dflash_config": {"target_layer_ids": [5, 12, 19]},
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": os.fspath(root)})
    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}

    model = discovered["z-lab/Qwen3.5-27B-DFlash"]
    assert model.model_kind == "text"
    assert model.ext["melix.draft.runtime_kind"] == "dflash"
    assert model.ext["melix.draft.architecture"] == "DFlashDraftModel"
    assert model.ext["melix.dflash.block_size"] == "8"
    assert model.ext["melix.dflash.target_layer_ids"] == "5,12,19"


def test_registry_snapshot_marks_gemma4_mtp_assistant_as_draft_only(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "gemma-4-E2B-it-assistant-bf16" / "main"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/gemma-4-E2B-it-assistant-bf16",
        model_kind="text",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "gemma4",
            "architectures": ["Gemma4ForConditionalGeneration"],
            "text_config": {"model_type": "gemma4_text"},
            "vision_config": None,
        },
    )
    (variant_dir / "README.md").write_text(
        "---\n"
        "library_name: mlx\n"
        "tags:\n"
        "- speculative-decoding\n"
        "- mtp\n"
        "- drafter\n"
        "---\n",
        encoding="utf-8",
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": os.fspath(root)})
    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}

    model = discovered["mlx-community/gemma-4-E2B-it-assistant-bf16"]
    assert model.model_kind == "vlm"
    assert model.ext["vision_family_id"] == "gemma4-v1"
    assert model.ext["melix.vlm.execution_mode"] == "text_backed"
    assert model.ext["melix.speculative.role"] == "assistant"
    assert model.ext["melix.speculative.kind"] == "mtp"
    assert model.ext["melix.speculative.target_family"] == "gemma4-v1"
    assert model.ext["melix.serving.hidden"] == "true"


def test_gemma4_mtp_assistant_metadata_handles_unserializable_config_values(tmp_path: Path) -> None:
    model_dir = tmp_path / "assistant"
    model_dir.mkdir()
    (model_dir / "README.md").write_text(
        "---\nlibrary_name: mlx\ntags:\n- mtp\n- drafter\n---\n",
        encoding="utf-8",
    )

    metadata = _gemma4_mtp_assistant_metadata(
        model_id="mlx-community/gemma-4-E2B-it-assistant-bf16",
        model_dir=model_dir,
        config_payload={
            "model_type": "gemma4",
            "unserializable": object(),
        },
    )

    assert metadata["melix.speculative.role"] == "assistant"
    assert metadata["melix.speculative.kind"] == "mtp"


def test_registry_snapshot_keeps_qwen3moe_lora_blocked_without_confirmed_expert_metadata(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "Qwen3-MoE-Unknown-Experts" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/Qwen3-MoE-Unknown-Experts/4bit",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "qwen3_moe",
            "rope_scaling": {"type": "yarn", "interleaved": True},
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    qwen3moe = discovered["mlx-community/Qwen3-MoE-Unknown-Experts/4bit"]

    assert qwen3moe.ext["text_family_id"] == "qwen3moe"
    assert qwen3moe.ext["melix.text.moe.expert_count"] == "128"
    assert qwen3moe.ext["melix.text.moe.expert_count_source"] == "family_default"
    assert qwen3moe.ext["melix.lora.family_id"] == "qwen3moe"
    assert qwen3moe.ext["melix.lora.support_tier"] == "experimental"
    assert qwen3moe.ext["melix.lora.training_ready"] == "false"
    assert qwen3moe.ext["melix.lora.default_target_preset"] == "attention"


def test_registry_snapshot_does_not_promote_qwen3moe_from_stale_expert_metadata(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "Qwen3-MoE-Stale-Experts" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/Qwen3-MoE-Stale-Experts/4bit",
        ext={
            "text_family_id": "qwen3moe",
            "melix.text.moe.expert_count": "128",
            "melix.text.moe.expert_count_source": "config",
        },
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "qwen3_moe",
            "rope_scaling": {"type": "yarn", "interleaved": True},
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    qwen3moe = discovered["mlx-community/Qwen3-MoE-Stale-Experts/4bit"]

    assert qwen3moe.ext["text_family_id"] == "qwen3moe"
    assert qwen3moe.ext["melix.text.moe.expert_count"] == "128"
    assert qwen3moe.ext["melix.text.moe.expert_count_source"] == "metadata"
    assert qwen3moe.ext["melix.lora.support_tier"] == "experimental"
    assert qwen3moe.ext["melix.lora.training_ready"] == "false"


def test_registry_snapshot_ignores_invalid_model_config_payloads(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "Broken-Unknown" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/Broken-Unknown/4bit",
    )
    variant_dir.mkdir(parents=True, exist_ok=True)
    (variant_dir / "config.json").write_text("{broken\n", encoding="utf-8")

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    broken = discovered["mlx-community/Broken-Unknown/4bit"]

    assert broken.ext["text_family_id"] == "llama"
    assert broken.ext["detected_identity_source"] == "default"
    assert broken.ext["melix.capability.route_kind"] == "python_text_compatibility"


def test_registry_snapshot_applies_image_family_adapter_metadata_from_path_and_manifest_task_kind(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "FLUX-Kontext" / "8bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/FLUX-Kontext/8bit",
        model_kind="image",
        ext={"melix.image.task_kind": "image-text-to-image"},
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    kontext = discovered["mlx-community/FLUX-Kontext/8bit"]

    assert kontext.ext["melix.image.backend_id"] == "deterministic"
    assert kontext.ext["melix.image.family_id"] == "kontext-v1"
    assert kontext.ext["melix.image.task_kind"] == "image-text-to-image"
    assert kontext.ext["melix.image.default_workflow_role"] == "edit"
    assert kontext.ext["melix.image.supports_generation"] == "true"
    assert kontext.ext["melix.image.supports_edit"] == "true"
    assert kontext.ext["detected_family_id"] == "kontext-v1"
    assert kontext.ext["detected_task_kind"] == "image-text-to-image"
    assert kontext.ext["detected_identity_source"] == "directory_name"
    assert kontext.ext["melix.adapter_set_hash"] == "image-family-kontext-v1"
    assert kontext.ext["melix.capability.route_kind"] == "python_image"
    assert kontext.ext["melix.capability.supported_tasks"] == "image_generate,image_edit"


def test_registry_snapshot_promotes_gemma4_text_manifest_to_vlm_text_backed(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "unsloth" / "gemma-4-E4B-it-MLX-8bit" / "snapshot"
    _write_registry_manifest(
        variant_dir,
        model_id="unsloth/gemma-4-E4B-it-MLX-8bit/snapshot",
        model_kind="text",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "gemma4",
            "architectures": ["Gemma4ForConditionalGeneration"],
            "text_config": {"model_type": "gemma4_text"},
            "vision_config": None,
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    gemma4 = discovered["unsloth/gemma-4-E4B-it-MLX-8bit/snapshot"]

    assert gemma4.model_kind == "vlm"
    assert gemma4.ext["melix.vlm.backend_id"] == "mlx_vlm"
    assert gemma4.ext["melix.vlm.execution_mode"] == "text_backed"
    assert gemma4.ext["melix.capability.tensor_index.warning_code"] == "missing_tensor_index"
    assert gemma4.ext["vision_family_id"] == "gemma4-v1"
    assert gemma4.ext["vision_prompt_profile_id"] == "gemma4-chatml-v1"
    assert gemma4.ext["melix.capability.route_kind"] == "python_vlm"
    assert gemma4.ext["melix.model.components"] == "text_backbone"
    assert gemma4.ext["melix.model.component_contract"] == "component_scoped_v1"
    assert gemma4.ext["melix.component.text_backbone.model_type"] == "gemma4_text"
    assert gemma4.ext["melix.component.text_backbone.family_id"] == "gemma"
    assert gemma4.ext["melix.component.text_backbone.lora_supported"] == "true"
    assert gemma4.ext["melix.component.text_backbone.training_ready"] == "true"
    assert gemma4.ext["melix.lora.adapter_scope"] == "text_backbone"
    assert gemma4.ext["melix.lora.training_surface"] == "text_backbone"
    assert gemma4.ext["melix.lora.component_model_type"] == "gemma4_text"
    assert gemma4.ext["melix.lora.family_id"] == "gemma"
    assert gemma4.ext["melix.lora.training_ready"] == "true"


def test_registry_snapshot_keeps_multimodal_gemma4_manifest_in_multimodal_mode(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "gemma-4-31b-it-4bit" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/gemma-4-31b-it-4bit/4bit",
        model_kind="text",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "gemma4",
            "architectures": ["Gemma4ForConditionalGeneration"],
            "text_config": {"model_type": "gemma4_text"},
            "vision_config": {"model_type": "gemma4_vision"},
        },
    )
    (variant_dir / "processor_config.json").write_text("{}\n", encoding="utf-8")
    _write_weight_index(
        variant_dir,
        {
            "metadata": {"total_size": 1},
            "weight_map": {
                "model.embed_tokens.weight": "model.safetensors",
                "vision_tower.blocks.0.attn.q_proj.weight": "model.safetensors",
                "embed_vision.proj.weight": "model.safetensors",
                "multi_modal_projector.linear.weight": "model.safetensors",
            },
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    gemma4 = discovered["mlx-community/gemma-4-31b-it-4bit/4bit"]

    assert gemma4.model_kind == "vlm"
    assert gemma4.ext["melix.vlm.backend_id"] == "mlx_vlm"
    assert gemma4.ext.get("melix.vlm.execution_mode", "") == ""
    assert gemma4.ext["vision_family_id"] == "gemma4-v1"
    assert gemma4.ext["melix.model.components"] == "text_backbone,vision_encoder,multimodal_projector"
    assert gemma4.ext["melix.component.text_backbone.model_type"] == "gemma4_text"
    assert gemma4.ext["melix.component.text_backbone.family_id"] == "gemma"
    assert gemma4.ext["melix.component.text_backbone.lora_supported"] == "true"
    assert gemma4.ext["melix.component.vision_encoder.model_type"] == "gemma4_vision"
    assert gemma4.ext["melix.component.vision_encoder.lora_supported"] == "false"
    assert gemma4.ext["melix.component.vision_encoder.lora_support_contract"] == "separate_contract"
    assert gemma4.ext["melix.component.multimodal_projector.lora_supported"] == "false"
    assert gemma4.ext["melix.component.multimodal_projector.lora_support_contract"] == "separate_contract"
    assert gemma4.ext["melix.lora.adapter_scope"] == "text_backbone"
    assert gemma4.ext["melix.lora.training_surface"] == "text_backbone"
    assert gemma4.ext["melix.lora.component_model_type"] == "gemma4_text"
    assert gemma4.ext["melix.lora.family_id"] == "gemma"
    assert gemma4.ext["melix.lora.training_ready"] == "true"


def test_registry_snapshot_records_multimodal_processor_and_nested_config_receipts(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "gemma-4-receipts" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/gemma-4-receipts/4bit",
        model_kind="text",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "gemma4",
            "architectures": ["Gemma4ForConditionalGeneration"],
            "text_config": {"model_type": "gemma4_text"},
            "vision_config": {"model_type": "gemma4_vision"},
            "multi_modal_projector": {"model_type": "gemma4_projector"},
            "draft_model": {"model_type": "gemma4_draft"},
            "image_token_id": 258880,
            "boi_token_id": 258881,
            "eoi_token_id": 258882,
            "audio_token_id": 258883,
        },
    )
    _write_processor_config(
        variant_dir,
        {
            "processor_class": "Gemma4Processor",
            "image_processor": {
                "image_processor_type": "Gemma4ImageProcessor",
                "image_token": "<image>",
                "num_image_tokens": 256,
            },
            "video_processor": {"video_token": "<video>"},
        },
    )
    (variant_dir / "tokenizer_config.json").write_text(
        json.dumps({"image_token": "<image>", "audio_token": "<audio>"}) + "\n",
        encoding="utf-8",
    )
    _write_weight_index(
        variant_dir,
        {
            "metadata": {"total_size": 1},
            "weight_map": {
                "model.embed_tokens.weight": "model.safetensors",
                "vision_tower.blocks.0.attn.q_proj.weight": "model.safetensors",
                "multi_modal_projector.linear.weight": "model.safetensors",
                "draft_model.layers.0.weight": "model.safetensors",
            },
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})
    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    gemma4 = discovered["mlx-community/gemma-4-receipts/4bit"]

    assert gemma4.ext["melix.capability.processor.status"] == "present"
    assert gemma4.ext["melix.capability.processor.source"].endswith("processor_config.json")
    assert gemma4.ext["melix.capability.processor.class"] == "Gemma4Processor"
    assert gemma4.ext["melix.capability.image_processor.class"] == "Gemma4ImageProcessor"
    assert gemma4.ext["melix.capability.media_placeholders.counts"] == "image:5,audio:2,video:1"
    assert gemma4.ext["melix.capability.media_placeholders.image_token_budget"] == "256"
    assert gemma4.ext["melix.capability.nested_config.aliases"] == (
        "draft:draft_model,projector:multi_modal_projector,text:text_config,vision:vision_config"
    )
    assert gemma4.ext["melix.capability.projector.status"] == "matched"
    assert gemma4.ext["melix.capability.vision_weight_remap.status"] == "matched_projector"
    assert gemma4.ext["melix.capability.optional_heads.load_attached"] == "true"
    assert gemma4.ext["melix.capability.optional_heads.acceleration_enabled"] == "false"
    assert gemma4.ext["melix.capability.optional_heads.components"] == "draft"


def test_registry_snapshot_accepts_metadata_matched_renamed_projector_receipt(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "gemma-4-renamed-projector" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/gemma-4-renamed-projector/4bit",
        model_kind="text",
        ext={"melix.projector.family_id": "gemma4-v1"},
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "gemma4",
            "architectures": ["Gemma4ForConditionalGeneration"],
            "text_config": {"model_type": "gemma4_text"},
            "vision_config": {"model_type": "gemma4_vision"},
        },
    )
    _write_processor_config(variant_dir, {"processor_class": "Gemma4Processor"})
    _write_weight_index(
        variant_dir,
        {
            "metadata": {"total_size": 1},
            "weight_map": {
                "model.embed_tokens.weight": "model.safetensors",
                "vision_tower.blocks.0.attn.q_proj.weight": "model.safetensors",
                "connector.linear.weight": "model.safetensors",
            },
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})
    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    gemma4 = discovered["mlx-community/gemma-4-renamed-projector/4bit"]

    assert gemma4.ext["melix.capability.supported_modalities"] == "text,image"
    assert gemma4.ext["melix.capability.projector.status"] == "renamed_metadata_matched"
    assert gemma4.ext["melix.capability.projector.family_id"] == "gemma4-v1"
    assert gemma4.ext["melix.capability.vision_weight_remap.status"] == "renamed_metadata_matched"
    assert gemma4.ext["melix.capability.tensor_index.warning_code"] == ""
    assert gemma4.ext.get("melix.vlm.execution_mode", "") != "text_backed"
    assert gemma4.ext["melix.capability.optional_heads.load_attached"] == "false"
    assert gemma4.ext["melix.capability.optional_heads.acceleration_enabled"] == "false"
    assert gemma4.ext["melix.capability.optional_heads.components"] == ""


def test_registry_snapshot_rejects_cross_family_projector_receipt(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "gemma-4-cross-family-projector" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/gemma-4-cross-family-projector/4bit",
        model_kind="text",
        ext={"melix.projector.family_id": "llava-v1"},
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "gemma4",
            "architectures": ["Gemma4ForConditionalGeneration"],
            "text_config": {"model_type": "gemma4_text"},
            "vision_config": {"model_type": "gemma4_vision"},
        },
    )
    _write_processor_config(variant_dir, {"processor_class": "Gemma4Processor"})
    _write_weight_index(
        variant_dir,
        {
            "metadata": {"total_size": 1},
            "weight_map": {
                "model.embed_tokens.weight": "model.safetensors",
                "vision_tower.blocks.0.attn.q_proj.weight": "model.safetensors",
                "multi_modal_projector.linear.weight": "model.safetensors",
            },
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})
    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    gemma4 = discovered["mlx-community/gemma-4-cross-family-projector/4bit"]

    assert gemma4.ext["melix.capability.supported_modalities"] == "text"
    assert gemma4.ext["melix.vlm.execution_mode"] == "text_backed"
    assert gemma4.ext["melix.capability.projector.status"] == "cross_family_rejected"
    assert gemma4.ext["melix.capability.projector.family_id"] == "llava-v1"
    assert gemma4.ext["melix.capability.vision_weight_remap.status"] == "cross_family_rejected"
    assert gemma4.ext["melix.capability.tensor_index.warning_code"] == "projector_cross_family"
    assert gemma4.ext["melix.capability.tensor_index.warning_modalities"] == "projector"
    assert gemma4.ext["melix.capability.tensor_index.warning_source"].endswith("model.safetensors.index.json")
    assert "multimodal_projector" not in gemma4.ext["melix.model.components"].split(",")


def test_registry_snapshot_rejects_missing_projector_receipt(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "gemma-4-missing-projector" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/gemma-4-missing-projector/4bit",
        model_kind="text",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "gemma4",
            "architectures": ["Gemma4ForConditionalGeneration"],
            "text_config": {"model_type": "gemma4_text"},
            "vision_config": {"model_type": "gemma4_vision"},
        },
    )
    _write_processor_config(variant_dir, {"processor_class": "Gemma4Processor"})
    _write_weight_index(
        variant_dir,
        {
            "metadata": {"total_size": 1},
            "weight_map": {
                "model.embed_tokens.weight": "model.safetensors",
                "vision_tower.blocks.0.attn.q_proj.weight": "model.safetensors",
            },
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})
    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    gemma4 = discovered["mlx-community/gemma-4-missing-projector/4bit"]

    assert gemma4.ext["melix.capability.supported_modalities"] == "text"
    assert gemma4.ext["melix.vlm.execution_mode"] == "text_backed"
    assert gemma4.ext["melix.capability.projector.status"] == "missing"
    assert gemma4.ext["melix.capability.projector.family_id"] == ""
    assert gemma4.ext["melix.capability.vision_weight_remap.status"] == "missing"
    assert gemma4.ext["melix.capability.tensor_index.warning_code"] == "projector_missing"
    assert gemma4.ext["melix.capability.tensor_index.warning_modalities"] == "projector"
    assert gemma4.ext["melix.capability.tensor_index.warning_source"].endswith("model.safetensors.index.json")
    assert "multimodal_projector" not in gemma4.ext["melix.model.components"].split(",")


def test_registry_snapshot_rejects_generic_adapter_as_renamed_projector(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "gemma-4-generic-adapter" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/gemma-4-generic-adapter/4bit",
        model_kind="text",
        ext={"melix.projector.family_id": "gemma4-v1"},
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "gemma4",
            "architectures": ["Gemma4ForConditionalGeneration"],
            "text_config": {"model_type": "gemma4_text"},
            "vision_config": {"model_type": "gemma4_vision"},
        },
    )
    _write_processor_config(variant_dir, {"processor_class": "Gemma4Processor"})
    _write_weight_index(
        variant_dir,
        {
            "metadata": {"total_size": 1},
            "weight_map": {
                "model.embed_tokens.weight": "model.safetensors",
                "vision_tower.blocks.0.attn.q_proj.weight": "model.safetensors",
                "some_adapter.weight": "model.safetensors",
            },
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})
    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    gemma4 = discovered["mlx-community/gemma-4-generic-adapter/4bit"]

    assert gemma4.ext["melix.capability.supported_modalities"] == "text"
    assert gemma4.ext["melix.capability.projector.status"] == "missing"
    assert gemma4.ext["melix.capability.tensor_index.warning_code"] == "projector_missing"


def test_registry_snapshot_records_draft_model_type_optional_head_receipt(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "gemma-4-draft-type" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/gemma-4-draft-type/4bit",
        model_kind="text",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "gemma4",
            "architectures": ["Gemma4ForConditionalGeneration"],
            "text_config": {"model_type": "gemma4_text"},
            "vision_config": {"model_type": "gemma4_vision"},
            "multi_modal_projector": {"model_type": "gemma4_projector"},
            "draft_model_type": "gemma4_draft",
        },
    )
    _write_processor_config(variant_dir, {"processor_class": "Gemma4Processor"})
    _write_weight_index(
        variant_dir,
        {
            "metadata": {"total_size": 1},
            "weight_map": {
                "model.embed_tokens.weight": "model.safetensors",
                "vision_tower.blocks.0.attn.q_proj.weight": "model.safetensors",
                "multi_modal_projector.linear.weight": "model.safetensors",
            },
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})
    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    gemma4 = discovered["mlx-community/gemma-4-draft-type/4bit"]

    assert gemma4.ext["melix.capability.optional_heads.declared"] == "draft"
    assert gemma4.ext["melix.capability.optional_heads.draft_model_type"] == "gemma4_draft"
    assert gemma4.ext["melix.capability.optional_heads.load_attached"] == "false"
    assert gemma4.ext["melix.capability.optional_heads.acceleration_enabled"] == "false"
    assert gemma4.ext["melix.capability.optional_heads.components"] == "draft"


def test_multimodal_receipt_helpers_handle_defensive_branches(tmp_path: Path) -> None:
    model_dir = tmp_path / "defensive"
    model_dir.mkdir(parents=True)
    json_cache: dict[Path, tuple[int, int, dict[str, object]]] = {}

    _write_weight_index(model_dir, {"weight_map": ["not-a-mapping"]})
    assert catalog_module._weight_map_tensor_names(model_dir, json_cache=json_cache) == ()
    assert catalog_module._has_renamed_projector_tensor(
        model_dir,
        tensor_evidence=catalog_module._tensor_index_evidence(model_dir, json_cache=json_cache),
        json_cache=json_cache,
    ) is False

    non_file_processor = model_dir / "processor_config.json"
    non_file_processor.mkdir()
    json_cache[non_file_processor] = (1, 2, {"stale": True})
    processor_path, processor_payload = catalog_module._first_json_sidecar(
        model_dir,
        ("processor_config.json", "preprocessor_config.json"),
        json_cache=json_cache,
    )
    assert processor_path is None
    assert processor_payload == {}
    assert non_file_processor not in json_cache

    assert catalog_module._positive_int_value("not-an-int") == 0

    _write_weight_index(
        model_dir,
        {
            "weight_map": {
                "vision_tower.blocks.0.weight": "model.safetensors",
                "unclassified.weight": "model.safetensors",
            }
        },
    )
    assert catalog_module._has_renamed_projector_tensor(
        model_dir,
        tensor_evidence=catalog_module._tensor_index_evidence(model_dir, json_cache=json_cache),
        json_cache=json_cache,
    ) is False


def test_gemma4_component_lora_metadata_requires_text_backbone_and_detects_processor_components(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "gemma4"
    model_dir.mkdir()

    assert catalog_module._gemma4_component_lora_metadata(
        model_path=str(model_dir),
        model_dir=model_dir,
        config_payload={},
    ) == {}
    assert catalog_module._gemma4_component_lora_metadata(
        model_path=str(model_dir),
        model_dir=model_dir,
        config_payload={"text_config": {"model_type": "llama"}},
    ) == {}

    (model_dir / "processor_config.json").write_text("{}\n", encoding="utf-8")
    metadata = catalog_module._gemma4_component_lora_metadata(
        model_path=str(model_dir),
        model_dir=model_dir,
        config_payload={"text_config": {"model_type": "gemma4_text"}, "vision_config": None},
    )

    assert metadata["melix.model.components"] == "text_backbone,vision_encoder,multimodal_projector"
    assert metadata["melix.component.vision_encoder.lora_supported"] == "false"
    assert metadata["melix.component.multimodal_projector.lora_support_contract"] == "separate_contract"


def test_registry_snapshot_promotes_gemma4_from_architecture_hint(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "gemma-4-12b-it-4bit" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/gemma-4-12b-it-4bit/4bit",
        model_kind="text",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "unknown",
            "architectures": ["Gemma4ForConditionalGeneration"],
            "vision_config": None,
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    gemma4 = discovered["mlx-community/gemma-4-12b-it-4bit/4bit"]

    assert gemma4.model_kind == "vlm"
    assert gemma4.ext["vision_family_id"] == "gemma4-v1"
    assert gemma4.ext["melix.vlm.execution_mode"] == "text_backed"


def test_registry_snapshot_promotes_gemma4_from_text_config_with_processor_hint(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "gemma-4-12b-it-processor" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/gemma-4-12b-it-processor/4bit",
        model_kind="text",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "unknown",
            "architectures": [],
            "text_config": {"model_type": "gemma4_text"},
            "vision_config": None,
        },
    )
    (variant_dir / "processor_config.json").write_text("{}\n", encoding="utf-8")

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    gemma4 = discovered["mlx-community/gemma-4-12b-it-processor/4bit"]

    assert gemma4.model_kind == "vlm"
    assert gemma4.ext["vision_family_id"] == "gemma4-v1"
    assert gemma4.ext["melix.vlm.execution_mode"] == "text_backed"
    assert gemma4.ext["melix.capability.supported_modalities"] == "text"
    assert gemma4.ext["melix.capability.tensor_index.warning_code"] == "missing_tensor_index"


def test_registry_snapshot_uses_gemma4_weight_index_to_keep_multimodal_mode(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "gemma-4-e2b-it-4bit" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/gemma-4-e2b-it-4bit/4bit",
        model_kind="text",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "gemma4",
            "architectures": ["Gemma4ForConditionalGeneration"],
            "text_config": {"model_type": "gemma4_text"},
            "image_token_id": 258880,
        },
    )
    _write_weight_index(
        variant_dir,
        {
            "metadata": {"total_size": 1},
            "weight_map": {
                "vision_tower.blocks.0.attn.q_proj.weight": "model.safetensors",
                "embed_vision.proj.weight": "model.safetensors",
            },
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    gemma4 = discovered["mlx-community/gemma-4-e2b-it-4bit/4bit"]

    assert gemma4.model_kind == "vlm"
    assert gemma4.ext["vision_family_id"] == "gemma4-v1"
    assert gemma4.ext["melix.capability.vision_weight_remap.status"] == "gemma4_embed_vision_projection"
    assert gemma4.ext.get("melix.vlm.execution_mode", "") == ""


def test_registry_snapshot_uses_tensor_index_to_fall_back_for_config_only_vision(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "gemma-4-config-only-vision" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/gemma-4-config-only-vision/4bit",
        model_kind="text",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "gemma4",
            "architectures": ["Gemma4ForConditionalGeneration"],
            "text_config": {"model_type": "gemma4_text"},
            "vision_config": {"model_type": "gemma4_vision"},
        },
    )
    _write_weight_index(
        variant_dir,
        {
            "metadata": {"total_size": 1},
            "weight_map": {
                "model.embed_tokens.weight": "model.safetensors",
                "model.layers.0.self_attn.q_proj.weight": "model.safetensors",
            },
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    gemma4 = discovered["mlx-community/gemma-4-config-only-vision/4bit"]

    assert gemma4.model_kind == "vlm"
    assert gemma4.ext["melix.vlm.execution_mode"] == "text_backed"
    assert gemma4.ext["melix.capability.supported_modalities"] == "text"
    assert gemma4.ext["melix.capability.tensor_index.modalities"] == "text"
    assert gemma4.ext["melix.capability.tensor_index.warning_code"] == "config_declared_missing_tensor_evidence"
    assert gemma4.ext["melix.capability.tensor_index.warning_modalities"] == "vision"
    assert gemma4.ext["melix.model.components"] == "text_backbone"


def test_registry_snapshot_uses_tensor_index_to_enable_vision_and_audio_routes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "gemma-4-audio-vision" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/gemma-4-audio-vision/4bit",
        model_kind="text",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "gemma4",
            "architectures": ["Gemma4ForConditionalGeneration"],
            "text_config": {"model_type": "gemma4_text"},
            "vision_config": {"model_type": "gemma4_vision"},
            "audio_config": {"model_type": "gemma4_audio"},
            "image_token_id": 258880,
            "audio_token_id": 258881,
        },
    )
    _write_weight_index(
        variant_dir,
        {
            "metadata": {"total_size": 1},
            "weight_map": {
                "model.embed_tokens.weight": "model.safetensors",
                "vision_tower.blocks.0.attn.q_proj.weight": "model.safetensors",
                "embed_vision.proj.weight": "model.safetensors",
                "audio_tower.blocks.0.attn.q_proj.weight": "model.safetensors",
                "embed_audio.proj.weight": "model.safetensors",
                "multi_modal_projector.linear.weight": "model.safetensors",
            },
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    gemma4 = discovered["mlx-community/gemma-4-audio-vision/4bit"]

    assert gemma4.model_kind == "vlm"
    assert gemma4.ext.get("melix.vlm.execution_mode", "") == ""
    assert gemma4.ext["melix.capability.supported_modalities"] == "text,image,audio"
    assert gemma4.ext["melix.capability.tensor_index.modalities"] == "text,vision,audio,projector"
    assert gemma4.ext["melix.capability.tensor_index.warning_code"] == ""
    assert gemma4.ext["melix.model.components"] == "text_backbone,vision_encoder,multimodal_projector,audio_encoder"


def test_registry_snapshot_falls_back_when_declared_vision_lacks_tensor_evidence(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "gemma-4-audio-only-vision-config" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/gemma-4-audio-only-vision-config/4bit",
        model_kind="text",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "gemma4",
            "architectures": ["Gemma4ForConditionalGeneration"],
            "text_config": {"model_type": "gemma4_text"},
            "vision_config": {"model_type": "gemma4_vision"},
            "audio_config": {"model_type": "gemma4_audio"},
            "image_token_id": 258880,
            "audio_token_id": 258881,
        },
    )
    _write_weight_index(
        variant_dir,
        {
            "metadata": {"total_size": 1},
            "weight_map": {
                "model.embed_tokens.weight": "model.safetensors",
                "model.layers.0.self_attn.q_proj.weight": "model.safetensors",
                "audio_tower.blocks.0.attn.q_proj.weight": "model.safetensors",
                "embed_audio.proj.weight": "model.safetensors",
            },
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    gemma4 = discovered["mlx-community/gemma-4-audio-only-vision-config/4bit"]

    assert gemma4.model_kind == "vlm"
    assert gemma4.ext["melix.vlm.execution_mode"] == "text_backed"
    assert gemma4.ext["melix.capability.supported_modalities"] == "text"
    assert gemma4.ext["melix.capability.tensor_index.modalities"] == "text,audio"
    assert gemma4.ext["melix.capability.tensor_index.warning_code"] == "config_declared_missing_tensor_evidence"
    assert gemma4.ext["melix.capability.tensor_index.warning_modalities"] == "vision"
    assert gemma4.ext["melix.model.components"] == "text_backbone,audio_encoder"


def test_registry_snapshot_malformed_tensor_index_falls_back_with_warning(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "gemma-4-malformed-index" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/gemma-4-malformed-index/4bit",
        model_kind="text",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "gemma4",
            "architectures": ["Gemma4ForConditionalGeneration"],
            "text_config": {"model_type": "gemma4_text"},
            "vision_config": {"model_type": "gemma4_vision"},
        },
    )
    variant_dir.mkdir(parents=True, exist_ok=True)
    (variant_dir / "model.safetensors.index.json").write_text("{not-json}\n", encoding="utf-8")

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    gemma4 = discovered["mlx-community/gemma-4-malformed-index/4bit"]

    assert gemma4.model_kind == "vlm"
    assert gemma4.ext["melix.vlm.execution_mode"] == "text_backed"
    assert gemma4.ext["melix.capability.supported_modalities"] == "text"
    assert gemma4.ext["melix.capability.tensor_index.warning_code"] == "malformed_tensor_index"
    assert gemma4.ext["melix.capability.tensor_index.warning_source"].endswith("model.safetensors.index.json")


def _assert_tensor_index_defensive_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    non_file_dir = tmp_path / "non-file-index"
    _write_model_config(
        non_file_dir,
        {
            "model_type": "gemma4",
            "architectures": ["Gemma4ForConditionalGeneration"],
            "text_config": {"model_type": "gemma4_text"},
            "video_config": {"model_type": "gemma4_video"},
            "projector_config": {"model_type": "gemma4_projector"},
            "draft_config": {"model_type": "gemma4_draft"},
            "video_token_id": 258882,
            "draft_model_type": "gemma4_draft",
        },
    )
    (non_file_dir / "model.safetensors.index.json").mkdir(parents=True)

    non_file_evidence = catalog_module._tensor_index_evidence(non_file_dir)
    assert non_file_evidence.status == "missing_tensor_index"
    assert catalog_module._supported_vlm_modalities_from_tensor_index(non_file_evidence) == ("text",)
    assert catalog_module._tensor_index_missing_declared_modalities(
        non_file_evidence,
        {"video_config": {"model_type": "gemma4_video"}},
    ) == set()

    malformed_map_dir = tmp_path / "malformed-weight-map"
    _write_weight_index(malformed_map_dir, {"weight_map": ["not-a-mapping"]})
    assert catalog_module._tensor_index_evidence(malformed_map_dir).status == "malformed_tensor_index"

    rich_dir = tmp_path / "video-draft-index"
    _write_weight_index(
        rich_dir,
        {
            "weight_map": {
                "video_tower.blocks.0.weight": "model.safetensors",
                "projector.video.weight": "model.safetensors",
                "draft_model.layers.0.weight": "model.safetensors",
                "unclassified.weight": "model.safetensors",
            }
        },
    )
    rich_evidence = catalog_module._tensor_index_evidence(rich_dir)
    assert rich_evidence.modalities == ("video", "projector", "draft")
    assert catalog_module._supported_vlm_modalities_from_tensor_index(
        rich_evidence,
        {"video_config": {"model_type": "gemma4_video"}, "projector_config": {}, "draft_config": {}},
    ) == ("text", "video")

    config_modalities = catalog_module._config_declared_modalities(
        {
            "video_config": {"model_type": "gemma4_video"},
            "projector_config": {"model_type": "gemma4_projector"},
            "draft_config": {"model_type": "gemma4_draft"},
            "draft_model_type": "gemma4_draft",
        }
    )
    assert {"video", "projector", "draft"}.issubset(config_modalities)

    stat_error_dir = tmp_path / "stat-error"
    _write_weight_index(stat_error_dir, {"weight_map": {"model.embed_tokens.weight": "model.safetensors"}})
    original_stat = Path.stat

    def raising_stat(self: Path, *args: object, **kwargs: object) -> os.stat_result:
        if self == stat_error_dir / "model.safetensors.index.json":
            raise OSError("synthetic stat failure")
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", raising_stat)
    try:
        assert catalog_module._tensor_index_evidence(stat_error_dir).status == "missing_tensor_index"
    finally:
        monkeypatch.setattr(Path, "stat", original_stat)


def test_registry_snapshot_records_gemma4_text_backbone_layer_count(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "unsloth" / "gemma-4-E4B-it-MLX-8bit" / "main"
    _write_registry_manifest(
        variant_dir,
        model_id="unsloth/gemma-4-E4B-it-MLX-8bit",
        model_kind="text",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "gemma4",
            "architectures": ["Gemma4ForConditionalGeneration"],
            "text_config": {
                "model_type": "gemma4_text",
                "num_hidden_layers": 42,
            },
            "image_token_id": 258880,
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})
    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    gemma4 = discovered["unsloth/gemma-4-E4B-it-MLX-8bit"]

    assert gemma4.model_kind == "vlm"
    assert gemma4.ext["text_layer_count"] == "42"
    assert gemma4.ext["melix.component.text_backbone.layer_count"] == "42"
    assert gemma4.ext["melix.lora.adapter_scope"] == "text_backbone"


def test_config_positive_int_rejects_missing_invalid_and_non_positive_values() -> None:
    assert _config_positive_int(None, "num_hidden_layers") == 0
    assert _config_positive_int({"num_hidden_layers": "invalid"}, "num_hidden_layers") == 0
    assert _config_positive_int({"num_hidden_layers": -1}, "num_hidden_layers") == 0
    assert _config_positive_int({"num_hidden_layers": "42"}, "num_hidden_layers") == 42


def test_gemma4_weight_index_detection_handles_missing_or_invalid_payloads(tmp_path: Path) -> None:
    model_dir = tmp_path / "gemma4"
    model_dir.mkdir(parents=True)

    assert _gemma4_index_has_vision_weights(model_dir) is False

    (model_dir / "model.safetensors.index.json").write_text("{not-json}\n", encoding="utf-8")
    assert _gemma4_index_has_vision_weights(model_dir) is False

    (model_dir / "model.safetensors.index.json").write_text('["not-a-dict"]\n', encoding="utf-8")
    assert _gemma4_index_has_vision_weights(model_dir) is False

    (model_dir / "model.safetensors.index.json").write_text(
        json.dumps({"weight_map": ["not-a-dict"]}) + "\n",
        encoding="utf-8",
    )
    assert _gemma4_index_has_vision_weights(model_dir) is False


def test_registry_snapshot_keeps_non_gemma_text_manifest_as_text(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "example" / "plain-text-model" / "q4"
    _write_registry_manifest(
        variant_dir,
        model_id="example/plain-text-model/q4",
        model_kind="text",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "llama",
            "architectures": ["LlamaForCausalLM"],
            "text_config": {"model_type": "llama"},
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    plain = discovered["example/plain-text-model/q4"]

    assert plain.model_kind == "text"
    assert plain.ext["melix.capability.route_kind"] == "python_text_compatibility"
    assert plain.ext.get("vision_family_id", "") == ""


def test_dev_image_model_reads_family_and_task_overrides() -> None:
    qwen = WorkerModelCatalog.dev_image_model(
        {
            "MELIX_DEV_IMAGE_FAMILY_ID": "qwenimage-v1",
            "MELIX_DEV_IMAGE_MODEL_PATH": "models/qwen-image-dev",
        }
    )
    fill = WorkerModelCatalog.dev_image_model(
        {
            "MELIX_DEV_IMAGE_FAMILY_ID": "fill-v1",
            "MELIX_DEV_IMAGE_MODEL_PATH": "models/flux-fill-dev",
            "MELIX_DEV_IMAGE_TASK_KIND": "image-text-to-image",
        }
    )

    assert qwen.ext["melix.image.family_id"] == "qwenimage-v1"
    assert qwen.ext["melix.image.task_kind"] == "text-to-image"
    assert qwen.ext["melix.image.supports_generation"] == "true"
    assert qwen.ext["melix.image.supports_edit"] == "false"
    assert qwen.ext["melix.capability.supported_tasks"] == "image_generate"
    assert qwen.ext["detected_identity_source"] == "explicit_override"

    assert fill.ext["melix.image.family_id"] == "fill-v1"
    assert fill.ext["melix.image.task_kind"] == "image-text-to-image"
    assert fill.ext["melix.image.supports_generation"] == "false"
    assert fill.ext["melix.image.supports_edit"] == "true"
    assert fill.ext["melix.capability.supported_tasks"] == "image_edit"


def test_registry_snapshot_skips_manifests_outside_supported_identity_depths(tmp_path: Path) -> None:
    root = tmp_path / "root"

    _write_registry_manifest(
        root / "mlx-community" / "Qwen2.5-7B-Instruct" / "4bit",
        model_id="mlx-community/Qwen2.5-7B-Instruct/4bit",
    )
    _write_registry_manifest(
        root / "too-shallow" / "Qwen2.5-7B-Instruct",
        model_id="too-shallow/Qwen2.5-7B-Instruct",
    )
    _write_registry_manifest(
        root / "provider" / "mlx-community" / "Qwen2.5-7B-Instruct" / "4bit" / "extra",
        model_id="provider/mlx-community/Qwen2.5-7B-Instruct/4bit/extra",
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()

    assert [model.model_id for model in snapshot.models] == ["mlx-community/Qwen2.5-7B-Instruct/4bit"]


def test_registry_snapshot_skips_invalid_manifests_and_normalizes_non_mapping_ext(tmp_path: Path) -> None:
    root = tmp_path / "root"

    broken_dir = root / "broken-json"
    broken_dir.mkdir(parents=True, exist_ok=True)
    (broken_dir / "manifest.json").write_text("{not-json\n", encoding="utf-8")

    list_dir = root / "list-payload"
    list_dir.mkdir(parents=True, exist_ok=True)
    (list_dir / "manifest.json").write_text(json.dumps(["not", "a", "dict"]) + "\n", encoding="utf-8")

    missing_id_dir = root / "missing-id"
    missing_id_dir.mkdir(parents=True, exist_ok=True)
    (missing_id_dir / "manifest.json").write_text(
        json.dumps({"model_kind": "text", "ext": {"source_root": "missing-id"}}) + "\n",
        encoding="utf-8",
    )

    ext_list_dir = root / "mlx-community" / "Valid-Model" / "4bit"
    ext_list_dir.mkdir(parents=True, exist_ok=True)
    (ext_list_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.model_registry_manifest.v1",
                "model_id": "mlx-community/Valid-Model/4bit",
                "model_kind": "text",
                "quant_profile_id": "q4",
                "max_context": 8192,
                "ext": ["not", "a", "mapping"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    catalog = WorkerModelCatalog(
        environment={
            "MELIX_MODEL_ROOTS": str(root),
        }
    )

    snapshot = catalog.registry_snapshot()

    assert [model.model_id for model in snapshot.models] == ["mlx-community/Valid-Model/4bit"]
    assert dict(snapshot.models[0].ext)["melix.registry_root_id"] == _expected_root_id(root)
    assert "source_root" not in snapshot.models[0].ext


def test_registry_snapshot_imports_generation_config_defaults_and_preserves_manifest_precedence(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "Vision-OCR" / "8bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/Vision-OCR/8bit",
        model_kind="ocr",
        ext={
            "melix.generation_config.temperature": "0.25",
            "ocr_sampling_profile_id": "ocr-operator",
        },
    )
    (variant_dir / "generation_config.json").write_text(
        json.dumps(
            {
                "temperature": 0.15,
                "top_p": 0.92,
                "max_new_tokens": 384,
                "do_sample": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    model = discovered["mlx-community/Vision-OCR/8bit"]

    assert model.ext["melix.generation_config.temperature"] == "0.25"
    assert model.ext["melix.generation_config.top_p"] == "0.92"
    assert model.ext["melix.generation_config.max_tokens"] == "384"
    assert model.ext["melix.generation_config.do_sample"] == "false"
    assert model.ext["melix.generation_config.source"].endswith("generation_config.json")
    assert model.ext["ocr_sampling_profile_id"] == "ocr-operator"


def test_registry_snapshot_ignores_invalid_generation_config_sidecars(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "Broken-Config" / "q4"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/Broken-Config/q4",
        ext={"source_root": "valid"},
    )
    (variant_dir / "generation_config.json").write_text("{broken\n", encoding="utf-8")

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    model = snapshot.models[0]

    assert model.model_id == "mlx-community/Broken-Config/q4"
    assert "melix.generation_config.source" not in model.ext


def test_registry_snapshot_ignores_non_mapping_generation_config_sidecars(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "List-Config" / "q4"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/List-Config/q4",
        ext={"source_root": "valid"},
    )
    (variant_dir / "generation_config.json").write_text('["not", "a", "mapping"]\n', encoding="utf-8")

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    model = snapshot.models[0]

    assert model.model_id == "mlx-community/List-Config/q4"
    assert "melix.generation_config.source" not in model.ext


def test_registry_snapshot_imports_string_generation_config_values_and_skips_blank_entries(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "String-Config" / "q4"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/String-Config/q4",
        ext={"source_root": "valid"},
    )
    (variant_dir / "generation_config.json").write_text(
        json.dumps(
            {
                "temperature": " 0.33 ",
                "top_p": ["unsupported"],
                "max_new_tokens": " 512 ",
                "do_sample": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    model = snapshot.models[0]

    assert model.model_id == "mlx-community/String-Config/q4"
    assert model.ext["melix.generation_config.temperature"] == "0.33"
    assert "melix.generation_config.top_p" not in model.ext
    assert model.ext["melix.generation_config.max_tokens"] == "512"
    assert model.ext["melix.generation_config.do_sample"] == "true"
    assert model.ext["melix.generation_config.source"].endswith("generation_config.json")
