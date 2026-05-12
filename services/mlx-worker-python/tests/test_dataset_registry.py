from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

import worker.dataset_registry.catalog as catalog
from worker.model_ops.errors import ModelOperationError
from worker.dataset_registry.catalog import (
    DatasetCatalog,
    read_hf_dataset_snapshot_rows,
)


def _write_hf_dataset_snapshot(
    home: Path,
    *,
    repo_dir_name: str = "datasets--org--repo",
    snapshot_id: str = "abc123",
    revision: str = "main",
    rows: list[dict[str, object]] | None = None,
) -> Path:
    cache_repo_dir = home / ".cache" / "huggingface" / "hub" / repo_dir_name
    snapshot_dir = cache_repo_dir / "snapshots" / snapshot_id
    snapshot_dir.mkdir(parents=True)
    (cache_repo_dir / "refs").mkdir()
    (cache_repo_dir / "refs" / revision).write_text(snapshot_id, encoding="utf-8")
    data_dir = snapshot_dir / "data"
    data_dir.mkdir()
    with (data_dir / "train-00000-of-00001.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows or [{"prompt": "hello", "answer": "world"}]:
            handle.write(json.dumps(row))
            handle.write("\n")
    (snapshot_dir / "README.md").write_text("# Dataset\n", encoding="utf-8")
    return snapshot_dir


def test_dataset_catalog_discovers_default_huggingface_cache_snapshot(tmp_path: Path) -> None:
    home = tmp_path / "home"
    snapshot_dir = _write_hf_dataset_snapshot(home)

    payload = DatasetCatalog(environment={"HOME": str(home)}).registry_snapshot_payload()

    datasets = payload["datasets"]
    assert len(datasets) == 1
    dataset = datasets[0]
    assert dataset["dataset_id"] == "org/repo@main"
    assert dataset["repo_id"] == "org/repo"
    assert dataset["revision"] == "main"
    assert dataset["snapshot_id"] == "abc123"
    assert dataset["snapshot_path"] == str(snapshot_dir.resolve())
    assert dataset["source_kind"] == "hf_cache_snapshot"
    assert dataset["splits"] == ["train"]
    assert dataset["configs"] == ["default"]
    assert dataset["total_bytes"] > 0
    assert dataset["restore_command"] == "melix dataset hub download --repo-id org/repo --revision main"


def test_dataset_catalog_builds_snapshot_inference_in_one_pass(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    snapshot_dir = _write_hf_dataset_snapshot(home)
    (snapshot_dir / "custom").mkdir()
    (snapshot_dir / "custom" / "validation-00000.parquet").write_bytes(b"validation")
    (snapshot_dir / "custom" / "test.json").write_text("[]", encoding="utf-8")

    def fail_split(_relative_path: str) -> str:
        raise AssertionError("snapshot build should infer split/config together")

    monkeypatch.setattr(catalog, "_inferred_split", fail_split)
    monkeypatch.setattr(catalog, "_inferred_config", fail_split)

    payload = DatasetCatalog(environment={"HOME": str(home)}).registry_snapshot_payload()

    dataset = payload["datasets"][0]
    assert dataset["splits"] == ["test", "train", "validation"]
    assert dataset["configs"] == ["custom", "default"]
    assert {file["relative_path"] for file in dataset["files"]} == {
        "README.md",
        "custom/test.json",
        "custom/validation-00000.parquet",
        "data/train-00000-of-00001.jsonl",
    }


def test_dataset_catalog_inferred_split_and_config_preserves_legacy_helpers() -> None:
    assert catalog._inferred_split("custom/validation-00000.parquet") == "validation"
    assert catalog._inferred_config("custom/validation-00000.parquet") == "custom"
    assert catalog._inferred_split_and_config("data/train-00000-of-00001.jsonl") == ("train", "default")
    assert catalog._inferred_split_and_config("custom\\test.json") == ("test", "custom")
    assert catalog._inferred_split_and_config("README.md") == ("", "default")
    assert catalog._inferred_split_and_config("") == ("", "default")


def test_dataset_catalog_reports_unavailable_roots_and_filters_snapshots(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_hf_dataset_snapshot(home)
    cache_root = home / ".cache" / "huggingface" / "hub"
    missing_root = tmp_path / "missing-root"

    payload = DatasetCatalog(environment={"HOME": str(home)}).registry_snapshot_payload(
        repo_id="org/repo",
        revision="missing",
        roots=[missing_root, cache_root],
    )

    assert payload["datasets"] == []
    assert payload["roots"][0]["accessible"] is False
    assert payload["roots"][0]["error_code"] == "not_found"
    assert payload["roots"][1]["accessible"] is True
    assert payload["roots"][1]["discovered_dataset_ids"] == []

    repo_filtered = DatasetCatalog(environment={"HOME": str(home)}).registry_snapshot_payload(
        repo_id="other/repo",
        roots=[cache_root],
    )
    assert repo_filtered["datasets"] == []


def test_dataset_catalog_reports_scan_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "hub"
    root.mkdir()

    def fail_scan(_root: Path):
        raise OSError("boom")

    monkeypatch.setattr(DatasetCatalog, "_scan_root", staticmethod(fail_scan))

    payload = DatasetCatalog(environment={"HOME": str(tmp_path)}).registry_snapshot_payload(roots=[root])

    assert payload["roots"][0]["accessible"] is False
    assert payload["roots"][0]["error_code"] == "scan_failed"
    assert payload["roots"][0]["error_message"] == "boom"


def test_dataset_catalog_resolves_by_revision_snapshot_id_and_missing_roots(tmp_path: Path) -> None:
    home = tmp_path / "home"
    snapshot_dir = _write_hf_dataset_snapshot(home)
    cache_root = home / ".cache" / "huggingface" / "hub"
    catalog_instance = DatasetCatalog(environment={"HOME": str(home)})

    assert catalog_instance.resolve_snapshot(repo_id="") is None
    assert catalog_instance.resolve_snapshot(repo_id="org/repo", roots=[tmp_path / "missing"]) is None
    by_revision = catalog_instance.resolve_snapshot(repo_id="org/repo", revision="main")
    by_snapshot = catalog_instance.resolve_snapshot(repo_id="org/repo", snapshot_id="abc123")
    wrong_snapshot = catalog_instance.resolve_snapshot(repo_id="org/repo", snapshot_id="missing")

    assert by_revision is not None
    assert by_revision.snapshot_path == snapshot_dir.resolve()
    assert by_snapshot is not None
    assert by_snapshot.snapshot_id == "abc123"
    assert wrong_snapshot is None
    assert catalog_instance.snapshot_for_path(tmp_path / "outside") is None
    assert catalog_instance.snapshot_for_path(cache_root / "not-a-snapshot") is None
    invalid_repo_snapshot = cache_root / "datasets--" / "snapshots" / "abc123"
    invalid_repo_snapshot.mkdir(parents=True)
    assert catalog_instance.snapshot_for_path(invalid_repo_snapshot) is None


def test_dataset_catalog_reads_rows_from_selected_split(tmp_path: Path) -> None:
    home = tmp_path / "home"
    snapshot_dir = _write_hf_dataset_snapshot(
        home,
        rows=[
            {"prompt": "first", "answer": "a"},
            {"prompt": "second", "answer": "b"},
        ],
    )
    (snapshot_dir / "data" / "test.jsonl").write_text('{"prompt":"test","answer":"c"}\n', encoding="utf-8")

    rows = read_hf_dataset_snapshot_rows(snapshot_dir, split="test")

    assert rows == [{"prompt": "test", "answer": "c"}]


def test_dataset_catalog_selected_split_filters_during_iteration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot_dir = tmp_path / "snapshot"
    data_dir = snapshot_dir / "data"
    custom_dir = snapshot_dir / "custom"
    validation_a = data_dir / "validation-00000.jsonl"
    readme = snapshot_dir / "README.md"
    train = data_dir / "train-00000.jsonl"
    validation_b = custom_dir / "validation-00001.jsonl"
    supported_paths = (readme, validation_a, train, validation_b)
    iterated_paths: list[Path] = []

    def fake_supported_files(path: Path):
        assert path == snapshot_dir
        for candidate in supported_paths:
            iterated_paths.append(candidate)
            yield candidate

    monkeypatch.setattr(catalog, "_iter_supported_dataset_files", fake_supported_files)

    assert catalog._selected_dataset_files(snapshot_dir, split="validation") == (
        validation_a,
        validation_b,
    )
    assert iterated_paths == list(supported_paths)
    assert catalog._selected_dataset_files(snapshot_dir, split="missing") == ()
    assert catalog._selected_dataset_files(snapshot_dir, split="") == supported_paths[1:]
    assert list(catalog._iter_matching_dataset_files(snapshot_dir, split="")) == []


def test_dataset_catalog_row_reader_respects_limit(tmp_path: Path) -> None:
    home = tmp_path / "home"
    snapshot_dir = _write_hf_dataset_snapshot(
        home,
        rows=[
            {"prompt": "first", "answer": "a"},
            {"prompt": "second", "answer": "b"},
        ],
    )

    rows = read_hf_dataset_snapshot_rows(snapshot_dir, split="train", limit=1)

    assert rows == [{"prompt": "first", "answer": "a"}]


def test_dataset_catalog_json_row_reader_limit_uses_incremental_decode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    json_path = tmp_path / "preview.json"
    json_path.write_text(
        json.dumps(
            {
                "rows": [
                    {"prompt": "first", "answer": "a"},
                    {"prompt": "second", "answer": "b"},
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        catalog.json,
        "loads",
        lambda _payload: (_ for _ in ()).throw(
            AssertionError("limited canonical JSON previews should not fully decode")
        ),
    )

    assert catalog._read_rows_from_file(json_path, limit=1) == [
        {"prompt": "first", "answer": "a"}
    ]


def test_dataset_catalog_limited_json_text_helper_edges() -> None:
    assert catalog._limited_rows_from_json_text("[]", limit=0) == []
    assert catalog._limited_rows_from_json_text("{}", limit=1) is None
    assert catalog._limited_rows_from_json_text("  []", limit=1) == []
    assert catalog._limited_rows_from_json_text("[", limit=1) is None
    assert catalog._limited_rows_from_json_text("[invalid", limit=1) is None
    assert catalog._limited_rows_from_json_text("[1]", limit=1) == []
    assert catalog._limited_rows_from_json_text("[1 x", limit=1) is None
    assert catalog._limited_rows_from_json_text(
        '[{"prompt":"first"}, {"prompt":"second"}]', limit=2
    ) == [{"prompt": "first"}, {"prompt": "second"}]
    assert catalog._limited_rows_from_json_text(
        '{"data" : [{"prompt":"first"}]}', limit=1
    ) == [{"prompt": "first"}]
    assert catalog._json_text_first_array_start("") is None
    assert catalog._json_text_first_array_start("1") is None
    assert catalog._json_text_first_array_start('{"rows" []}') is None
    assert catalog._json_text_first_array_start('{"rows" }') is None
    assert catalog._json_text_first_array_start('{  }') is None
    assert catalog._json_text_first_array_start('{invalid') is None
    assert catalog._json_text_first_array_start('{1: 2}') is None
    assert catalog._json_text_first_array_start('{"metadata": bad}') is None
    assert catalog._json_text_first_array_start('{"metadata": 1 , "rows": []}') is not None
    assert catalog._json_text_first_array_start('{"metadata": 1 x}') is None
    assert catalog._json_text_first_array_start("{") is None
    assert catalog._json_text_first_array_start('{"items": []}') is None


class _FakeColumnarBatch:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def to_pylist(self) -> list[object]:
        return list(self._rows)


class _FakeColumnarTable(_FakeColumnarBatch):
    def slice(self, offset: int, length: int) -> "_FakeColumnarTable":
        return _FakeColumnarTable(self._rows[offset : offset + length])


def _install_fake_pyarrow_module(
    monkeypatch: pytest.MonkeyPatch,
    *,
    module_name: str,
    module: types.ModuleType,
) -> None:
    pyarrow_module = types.ModuleType("pyarrow")
    setattr(pyarrow_module, module_name.rsplit(".", 1)[-1], module)
    monkeypatch.setitem(sys.modules, "pyarrow", pyarrow_module)
    monkeypatch.setitem(sys.modules, module_name, module)


def test_dataset_catalog_parquet_limit_uses_batched_reader(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    parquet_path = tmp_path / "preview.parquet"
    parquet_path.write_bytes(b"fake")
    batch_sizes: list[int] = []
    read_table_calls = 0

    class FakeParquetFile:
        def __init__(self, path: Path) -> None:
            assert path == parquet_path

        def iter_batches(self, *, batch_size: int):
            batch_sizes.append(batch_size)
            yield _FakeColumnarBatch([
                {"prompt": "first"},
                ["not", "a", "dict"],
                {"prompt": "second"},
            ])
            yield _FakeColumnarBatch([{"prompt": "third"}])

    parquet_module = types.ModuleType("pyarrow.parquet")
    parquet_module.ParquetFile = FakeParquetFile

    def read_table(_path: Path) -> object:
        nonlocal read_table_calls
        assert _path == parquet_path
        read_table_calls += 1
        return _FakeColumnarTable([{"prompt": "full"}, {"prompt": "later"}])

    parquet_module.read_table = read_table
    _install_fake_pyarrow_module(monkeypatch, module_name="pyarrow.parquet", module=parquet_module)

    rows = catalog._read_rows_from_file(parquet_path, limit=2)

    assert rows == [{"prompt": "first"}, {"prompt": "second"}]
    assert batch_sizes == [2]
    assert read_table_calls == 0
    assert catalog._read_rows_from_file(parquet_path) == [{"prompt": "full"}, {"prompt": "later"}]
    assert read_table_calls == 1


def test_dataset_catalog_arrow_limit_uses_first_batches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    arrow_path = tmp_path / "preview.arrow"
    arrow_path.write_bytes(b"fake")
    read_all_calls = 0
    batch_indexes: list[int] = []

    class FakeReader:
        num_record_batches = 3

        def __enter__(self) -> "FakeReader":
            return self

        def __exit__(self, *_exc_info: object) -> None:
            return None

        def get_batch(self, index: int) -> _FakeColumnarBatch:
            batch_indexes.append(index)
            batches = [
                _FakeColumnarBatch([{"prompt": "first"}]),
                _FakeColumnarBatch([["not", "a", "dict"], {"prompt": "second"}]),
                _FakeColumnarBatch([{"prompt": "third"}]),
            ]
            return batches[index]

        def read_all(self) -> object:
            nonlocal read_all_calls
            read_all_calls += 1
            return _FakeColumnarTable([{"prompt": "full"}, ["not", "a", "dict"], {"prompt": "later"}])

    ipc_module = types.ModuleType("pyarrow.ipc")
    ipc_module.open_file = lambda path: FakeReader() if path == arrow_path else None
    _install_fake_pyarrow_module(monkeypatch, module_name="pyarrow.ipc", module=ipc_module)

    rows = catalog._read_rows_from_file(arrow_path, limit=2)

    assert rows == [{"prompt": "first"}, {"prompt": "second"}]
    assert batch_indexes == [0, 1]
    assert read_all_calls == 0
    assert catalog._read_rows_from_file(arrow_path) == [{"prompt": "full"}, {"prompt": "later"}]
    assert read_all_calls == 1


def test_dataset_catalog_row_reader_zero_limit_returns_empty(tmp_path: Path) -> None:
    jsonl_path = tmp_path / "preview.jsonl"
    jsonl_path.write_text('{"prompt":"first"}\n', encoding="utf-8")

    assert catalog._read_rows_from_file(jsonl_path, limit=0) == []


def test_dataset_catalog_limited_unfiltered_read_stops_before_later_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot_dir = tmp_path / "snapshot"
    data_dir = snapshot_dir / "data"
    data_dir.mkdir(parents=True)
    first_file = data_dir / "part-000.jsonl"
    later_file = data_dir / "part-001.jsonl"
    first_file.write_text('{"prompt":"first"}\n', encoding="utf-8")
    later_file.write_text('{"prompt":"later"}\n', encoding="utf-8")
    (snapshot_dir / "README.md").write_text("# metadata\n", encoding="utf-8")
    read_files: list[str] = []
    original_reader = catalog._read_rows_from_file

    def tracked_reader(path: Path, *, limit: int | None = None) -> list[dict[str, object]]:
        read_files.append(path.name)
        return original_reader(path, limit=limit)

    monkeypatch.setattr(catalog, "_read_rows_from_file", tracked_reader)

    rows = read_hf_dataset_snapshot_rows(snapshot_dir, limit=1)

    assert rows == [{"prompt": "first"}]
    assert read_files == ["part-000.jsonl"]


def test_dataset_catalog_unlimited_unfiltered_read_preserves_full_selection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot_dir = tmp_path / "snapshot"
    data_dir = snapshot_dir / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "part-000.jsonl").write_text('{"prompt":"first"}\n', encoding="utf-8")
    (data_dir / "part-001.jsonl").write_text('{"prompt":"second"}\n', encoding="utf-8")
    selected_calls: list[str] = []
    original_selector = catalog._selected_dataset_files

    def tracked_selector(snapshot_path: Path, *, split: str) -> tuple[Path, ...]:
        selected_calls.append(split)
        return original_selector(snapshot_path, split=split)

    monkeypatch.setattr(catalog, "_selected_dataset_files", tracked_selector)

    rows = read_hf_dataset_snapshot_rows(snapshot_dir)

    assert rows == [{"prompt": "first"}, {"prompt": "second"}]
    assert selected_calls == []


def test_dataset_catalog_row_reader_stops_file_scan_after_unsplit_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot_dir = tmp_path / "snapshot"
    data_dir = snapshot_dir / "data"
    data_dir.mkdir(parents=True)
    first_file = data_dir / "part-00000.jsonl"
    second_file = data_dir / "part-00001.jsonl"
    first_file.write_text('{"prompt":"first"}\n', encoding="utf-8")
    second_file.write_text('{"prompt":"second"}\n', encoding="utf-8")
    read_paths: list[Path] = []
    original_read_rows = catalog._read_rows_from_file

    def tracking_read_rows(path: Path, *, limit: int | None = None) -> list[dict[str, object]]:
        read_paths.append(path)
        return original_read_rows(path, limit=limit)

    monkeypatch.setattr(catalog, "_read_rows_from_file", tracking_read_rows)

    rows = read_hf_dataset_snapshot_rows(snapshot_dir, limit=1)

    assert rows == [{"prompt": "first"}]
    assert read_paths == [first_file]


def test_dataset_catalog_limit_one_preview_avoids_full_supported_file_iterator(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot_dir = tmp_path / "snapshot"
    data_dir = snapshot_dir / "data"
    data_dir.mkdir(parents=True)
    first_file = data_dir / "part-00000.jsonl"
    first_file.write_text('{"prompt":"first"}\n', encoding="utf-8")
    (data_dir / "part-00001.jsonl").write_text('{"prompt":"second"}\n', encoding="utf-8")

    monkeypatch.setattr(catalog, "_iter_supported_dataset_files", None)

    rows = read_hf_dataset_snapshot_rows(snapshot_dir, limit=1)

    assert rows == [{"prompt": "first"}]


def test_dataset_catalog_first_preview_file_preserves_sorted_depth_first_edges(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot_dir = tmp_path / "snapshot"
    empty_dir = snapshot_dir / "a-empty"
    data_dir = snapshot_dir / "data"
    empty_dir.mkdir(parents=True)
    data_dir.mkdir()
    (data_dir / "notes.txt").write_text("ignore", encoding="utf-8")
    first_file = data_dir / "part-00000.jsonl"
    first_file.write_text('{"prompt":"first"}\n', encoding="utf-8")

    assert catalog._first_supported_dataset_file(snapshot_dir) == first_file
    assert catalog._first_supported_dataset_file(tmp_path / "missing") is None

    original_scandir = catalog.os.scandir

    def failing_scandir(_path: object):
        raise OSError("scan failed")

    monkeypatch.setattr(catalog.os, "scandir", failing_scandir)
    assert catalog._first_supported_dataset_file(snapshot_dir) is None
    monkeypatch.setattr(catalog.os, "scandir", original_scandir)

    class BrokenEntry:
        name = "broken.jsonl"
        path = str(data_dir / "broken.jsonl")

        def is_dir(self) -> bool:
            raise OSError("broken entry")

        def is_file(self) -> bool:
            return True

    class FakeScandir:
        def __enter__(self):
            return iter([BrokenEntry()])

        def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
            return False

    monkeypatch.setattr(catalog.os, "scandir", lambda _path: FakeScandir())
    assert catalog._next_supported_scan_entry(snapshot_dir, after="") is None


def test_dataset_catalog_row_reader_keeps_split_filtering_eager_for_missing_split(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot_dir = tmp_path / "snapshot"
    data_dir = snapshot_dir / "data"
    data_dir.mkdir(parents=True)
    train_path = data_dir / "train.jsonl"
    validation_path = data_dir / "validation.jsonl"
    train_path.write_text('{"prompt":"train"}\n', encoding="utf-8")
    validation_path.write_text('{"prompt":"validation"}\n', encoding="utf-8")
    considered_paths: list[Path] = []
    original_iter_supported = catalog._iter_supported_dataset_files

    def tracking_iter_supported(path: Path):
        for candidate in original_iter_supported(path):
            considered_paths.append(candidate)
            yield candidate

    monkeypatch.setattr(catalog, "_iter_supported_dataset_files", tracking_iter_supported)

    rows = read_hf_dataset_snapshot_rows(snapshot_dir, split="test", limit=1)

    assert rows == []
    assert sorted(set(considered_paths)) == [train_path, validation_path]


def test_dataset_catalog_limited_split_read_stops_after_first_matching_row(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot_dir = tmp_path / "snapshot"
    data_dir = snapshot_dir / "data"
    data_dir.mkdir(parents=True)
    first_validation = data_dir / "validation-00000.jsonl"
    train = data_dir / "train-00000.jsonl"
    later_validation = data_dir / "validation-00001.jsonl"
    first_validation.write_text('{"prompt":"first-validation"}\n', encoding="utf-8")
    train.write_text('{"prompt":"train"}\n', encoding="utf-8")
    later_validation.write_text('{"prompt":"later-validation"}\n', encoding="utf-8")
    supported_paths = (first_validation, train, later_validation)
    considered_paths: list[Path] = []

    def fake_supported_files(path: Path):
        assert path == snapshot_dir
        for candidate in supported_paths:
            considered_paths.append(candidate)
            yield candidate

    monkeypatch.setattr(catalog, "_iter_supported_dataset_files", fake_supported_files)

    rows = read_hf_dataset_snapshot_rows(snapshot_dir, split="validation", limit=1)

    assert rows == [{"prompt": "first-validation"}]
    assert considered_paths == [first_validation]


def test_dataset_catalog_reads_json_and_csv_snapshots(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "snapshot"
    data_dir = snapshot_dir / "custom"
    data_dir.mkdir(parents=True)
    (data_dir / "validation.json").write_text(
        json.dumps({"rows": [{"prompt": "json-row"}]}),
        encoding="utf-8",
    )
    (data_dir / "train.csv").write_text("prompt,answer\ncsv-row,ok\n", encoding="utf-8")

    assert read_hf_dataset_snapshot_rows(snapshot_dir, split="validation") == [{"prompt": "json-row"}]
    assert read_hf_dataset_snapshot_rows(snapshot_dir, split="train") == [{"prompt": "csv-row", "answer": "ok"}]
    assert read_hf_dataset_snapshot_rows(snapshot_dir, split="missing", limit=1) == []
    assert read_hf_dataset_snapshot_rows(snapshot_dir, limit=1) == [{"prompt": "csv-row", "answer": "ok"}]


def test_dataset_catalog_path_split_matching_avoids_temporary_path_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingPath:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("split matching should use string stems, not Path(part).stem")

    monkeypatch.setattr(catalog, "Path", FailingPath)

    assert catalog._path_matches_split(Path("data/validation-00000.jsonl"), "validation") is True
    assert catalog._path_matches_split(Path("custom/test.arrow"), "test") is True
    assert catalog._path_matches_split(Path("train_dir/part-00000.parquet"), "train") is True
    assert catalog._path_matches_split(Path("custom/eval.jsonl"), "train") is False


def test_dataset_catalog_string_stem_matches_pathlib_for_split_names() -> None:
    names = [
        "train.jsonl",
        "validation_foo.parquet",
        "test-00000-of-00001.arrow",
        "archive.train.jsonl",
        ".hidden",
        "train.",
        "train..jsonl",
    ]

    for name in names:
        assert catalog._string_stem(name) == Path(name).stem


def test_dataset_catalog_reads_parquet_and_arrow_with_fake_pyarrow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    parquet_path = tmp_path / "train.parquet"
    arrow_path = tmp_path / "train.arrow"
    parquet_path.write_bytes(b"parquet")
    arrow_path.write_bytes(b"arrow")
    sliced_offsets: list[tuple[int, int | None]] = []

    class FakeArrowTable:
        def __init__(self, rows: list[object]) -> None:
            self._rows = rows

        def slice(self, offset: int, length: int | None = None) -> "FakeArrowTable":
            sliced_offsets.append((offset, length))
            end = None if length is None else offset + length
            return FakeArrowTable(self._rows[offset:end])

        def to_pylist(self) -> list[object]:
            return list(self._rows)

    pyarrow_module = types.ModuleType("pyarrow")
    pyarrow_module.__path__ = []
    parquet_module = types.ModuleType("pyarrow.parquet")
    parquet_module.read_table = lambda _path: FakeArrowTable([{"prompt": "parquet"}, {"prompt": "extra"}, "ignored"])

    class FakeArrowReader:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def read_all(self):
            return FakeArrowTable([{"prompt": "arrow"}, {"prompt": "extra"}, "ignored"])

    ipc_module = types.ModuleType("pyarrow.ipc")
    ipc_module.open_file = lambda _path: FakeArrowReader()

    monkeypatch.setitem(sys.modules, "pyarrow", pyarrow_module)
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", parquet_module)
    monkeypatch.setitem(sys.modules, "pyarrow.ipc", ipc_module)

    assert catalog._read_rows_from_file(parquet_path, limit=1) == [{"prompt": "parquet"}]
    assert catalog._read_rows_from_file(arrow_path, limit=1) == [{"prompt": "arrow"}]
    assert sliced_offsets == [(0, 1), (0, 1)]


def test_dataset_catalog_surfaces_missing_pyarrow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    parquet_path = tmp_path / "train.parquet"
    arrow_path = tmp_path / "train.arrow"
    parquet_path.write_bytes(b"parquet")
    arrow_path.write_bytes(b"arrow")
    original_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"pyarrow.parquet", "pyarrow.ipc"}:
            raise ImportError(name)
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)

    with pytest.raises(ModelOperationError) as parquet_error:
        catalog._read_rows_from_file(parquet_path)
    assert parquet_error.value.code == "unavailable"

    with pytest.raises(ModelOperationError) as arrow_error:
        catalog._read_rows_from_file(arrow_path)
    assert arrow_error.value.code == "unavailable"


def test_dataset_catalog_json_payload_helpers_cover_supported_shapes() -> None:
    assert catalog._rows_from_json_payload([{"a": 1}, ["ignored"]]) == [{"a": 1}]
    assert catalog._rows_from_json_payload({"data": [{"a": 2}]}) == [{"a": 2}]
    assert catalog._rows_from_json_payload({"items": [{"a": 3}]}) == [{"a": 3}]
    assert catalog._rows_from_json_payload({"single": "row"}) == [{"single": "row"}]
    assert catalog._rows_from_json_payload("ignored") == []


def test_dataset_catalog_json_payload_limit_short_circuits_canonical_lists() -> None:
    assert catalog._rows_from_json_payload({"rows": [{"a": 1}, {"a": 2}]}, limit=1) == [{"a": 1}]
    assert catalog._rows_from_json_payload({"data": [{"a": 1}, {"a": 2}]}, limit=1) == [{"a": 1}]
    assert catalog._rows_from_json_payload([{"a": 1}, {"a": 2}], limit=1) == [{"a": 1}]
    assert catalog._rows_from_json_payload({"items": [{"a": 1}, {"a": 2}]}, limit=1) == [{"a": 1}]


def test_dataset_catalog_downloads_dataset_repo_type_without_leaking_token(
    monkeypatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    snapshot_dir = _write_hf_dataset_snapshot(home, repo_dir_name="datasets--org--downloaded")
    captured_kwargs: dict[str, object] = {}

    def fake_snapshot_download(**kwargs):
        captured_kwargs.update(kwargs)
        return str(snapshot_dir)

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        types.SimpleNamespace(snapshot_download=fake_snapshot_download),
    )

    result = DatasetCatalog(environment={"HOME": str(home)}).download_hf_dataset(
        repo_id="org/downloaded",
        revision="main",
        hf_token="hf_secret",
        job_id="job-1",
        output_dir=tmp_path / "job",
    )

    assert captured_kwargs["repo_type"] == "dataset"
    assert captured_kwargs["repo_id"] == "org/downloaded"
    assert captured_kwargs["token"] == "hf_secret"
    assert result.snapshot.repo_id == "org/downloaded"
    assert "hf_secret" not in json.dumps(result.manifest)
    assert result.manifest["snapshot_path"] == str(snapshot_dir.resolve())


def test_dataset_catalog_download_validates_repo_and_hub_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    with pytest.raises(ModelOperationError) as invalid_error:
        DatasetCatalog().download_hf_dataset(repo_id="")
    assert invalid_error.value.code == "invalid_argument"

    monkeypatch.setitem(sys.modules, "huggingface_hub", None)
    with pytest.raises(ModelOperationError) as import_error:
        DatasetCatalog().download_hf_dataset(repo_id="org/repo")
    assert import_error.value.code == "unavailable"
    monkeypatch.delitem(sys.modules, "huggingface_hub", raising=False)

    class AuthFailure(Exception):
        def __init__(self) -> None:
            super().__init__("private")
            self.response = types.SimpleNamespace(status_code=401)

    class HubFailure(Exception):
        pass

    HubFailure.__module__ = "huggingface_hub.errors"

    def auth_download(**_kwargs):
        raise AuthFailure()

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        types.SimpleNamespace(snapshot_download=auth_download),
    )
    with pytest.raises(ModelOperationError) as auth_error:
        DatasetCatalog().download_hf_dataset(repo_id="org/private")
    assert auth_error.value.code == "hf_auth_failed"

    def hub_download(**_kwargs):
        raise HubFailure("offline")

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        types.SimpleNamespace(snapshot_download=hub_download),
    )
    with pytest.raises(ModelOperationError) as hub_error:
        DatasetCatalog().download_hf_dataset(repo_id="org/repo")
    assert hub_error.value.code == "unavailable"

    fallback_snapshot = tmp_path / "manual" / "snapshots" / "def456"
    fallback_snapshot.mkdir(parents=True)
    (fallback_snapshot / "train.jsonl").write_text('{"prompt":"fallback"}\n', encoding="utf-8")

    def fallback_download(**_kwargs):
        return str(fallback_snapshot)

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        types.SimpleNamespace(snapshot_download=fallback_download),
    )
    result = DatasetCatalog(environment={"HOME": str(tmp_path / "home")}).download_hf_dataset(
        repo_id="org/fallback",
        revision="rev",
    )
    assert result.snapshot.repo_id == "org/fallback"
    assert result.snapshot.snapshot_path == fallback_snapshot.resolve()

    def unexpected_download(**_kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        types.SimpleNamespace(snapshot_download=unexpected_download),
    )
    with pytest.raises(RuntimeError):
        DatasetCatalog().download_hf_dataset(repo_id="org/repo")


def test_dataset_catalog_remove_deletes_only_selected_snapshot(tmp_path: Path) -> None:
    home = tmp_path / "home"
    snapshot_dir = _write_hf_dataset_snapshot(home)

    result = DatasetCatalog(environment={"HOME": str(home)}).remove_hf_dataset_snapshot(
        repo_id="org/repo",
        revision="main",
        job_id="job-remove",
        output_dir=tmp_path / "job",
    )

    assert result.removed_snapshot.snapshot_id == "abc123"
    assert result.manifest["removed_snapshot_path"] == str(snapshot_dir.resolve())
    assert not snapshot_dir.exists()
    assert snapshot_dir.parents[1].exists()


def test_dataset_catalog_remove_validates_target(tmp_path: Path) -> None:
    with pytest.raises(ModelOperationError) as invalid_error:
        DatasetCatalog().remove_hf_dataset_snapshot(repo_id="")
    assert invalid_error.value.code == "invalid_argument"

    with pytest.raises(ModelOperationError) as missing_error:
        DatasetCatalog(environment={"HOME": str(tmp_path)}).remove_hf_dataset_snapshot(
            repo_id="org/missing",
            revision="main",
            snapshot_id="missing",
        )
    assert missing_error.value.code == "not_found"
    assert missing_error.value.details == {
        "repo_id": "org/missing",
        "revision": "main",
        "snapshot_id": "missing",
    }


def test_dataset_catalog_private_helpers_cover_cache_edge_cases(tmp_path: Path) -> None:
    assert catalog.default_huggingface_cache_root(environment={}).name == "hub"
    assert catalog._hf_dataset_repo_id(tmp_path / "models--org--repo") is None
    assert catalog._hf_dataset_repo_id(tmp_path / "datasets--") is None
    assert catalog._hf_dataset_repo_id(tmp_path / "datasets--repo") == "repo"
    assert catalog._hf_dataset_repo_id(tmp_path / "datasets--org--repo") == "org/repo"
    assert catalog._hf_dataset_repo_id(tmp_path / "datasets----repo") is None
    assert catalog._hf_dataset_repo_id(tmp_path / "datasets--org--") is None

    cache_repo = tmp_path / "datasets--org--repo"
    assert catalog._hf_cache_revision_map(cache_repo, snapshot_ids=set()) == {}
    assert catalog._hf_cache_revision(cache_repo, "abc123") == "abc123"

    refs_dir = cache_repo / "refs" / "pull"
    refs_dir.mkdir(parents=True)
    (refs_dir / "1").write_text("abc123", encoding="utf-8")
    assert catalog._hf_cache_revision_map(cache_repo, snapshot_ids={"abc123"}) == {"abc123": "pull/1"}
    assert list(catalog._iter_relative_file_paths_sorted(cache_repo / "refs")) == [
        (refs_dir / "1", "pull/1")
    ]

    (cache_repo / "refs" / "blank").write_text("", encoding="utf-8")
    (cache_repo / "refs" / "other").write_text("other", encoding="utf-8")
    assert catalog._hf_cache_revision_map(cache_repo, snapshot_ids={"missing"}) == {}

    original_read_text = Path.read_text

    def guarded_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "broken":
            raise OSError("broken")
        return original_read_text(self, *args, **kwargs)

    (cache_repo / "refs" / "broken").write_text("abc123", encoding="utf-8")
    with pytest.MonkeyPatch.context() as local_monkeypatch:
        local_monkeypatch.setattr(Path, "read_text", guarded_read_text)
        assert catalog._hf_cache_revision_map(cache_repo, snapshot_ids={"abc123"}) == {"abc123": "pull/1"}

    with pytest.MonkeyPatch.context() as local_monkeypatch:
        local_monkeypatch.setattr(
            catalog,
            "_iter_relative_file_paths_sorted",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("scan")),
        )
        assert catalog._hf_cache_revision_map(cache_repo) == {}

    assert catalog._limit_rows([{"a": 1}], None) == [{"a": 1}]
    assert catalog.public_ext({"melix.hf_token": "secret", "safe": "value"}) == {"safe": "value"}
    assert catalog.repo_id_shell_arg("org/repo") == "org/repo"
    assert catalog.repo_id_shell_arg("org/repo with space") == '"org/repo with space"'


def test_dataset_catalog_filesystem_error_helpers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    data_file = snapshot_dir / "train.jsonl"
    data_file.write_text('{"prompt":"ok"}\n', encoding="utf-8")
    original_stat = Path.stat

    def guarded_stat(self: Path, *args: object, **kwargs: object):
        if self == data_file:
            raise OSError("stat failed")
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", guarded_stat)
    assert list(catalog._dataset_files(snapshot_dir)) == []

    def raising_scandir(_path):
        raise OSError("scan failed")

    monkeypatch.setattr(catalog.os, "scandir", raising_scandir)
    assert list(catalog._iter_supported_dataset_files(snapshot_dir)) == []
    assert catalog._sorted_child_directories(snapshot_dir) == ()
