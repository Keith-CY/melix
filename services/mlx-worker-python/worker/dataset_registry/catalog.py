from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import heapq
import json
import os
from pathlib import Path
import shutil
import time
from typing import Any, Iterable, Iterator, Mapping

from worker.model_ops.errors import ModelOperationError

_HF_TOKEN_KEYS = {
    "melix.hf_token",
    "hf_token",
    "HUGGINGFACE_HUB_TOKEN",
    "HF_TOKEN",
}
_SUPPORTED_DATASET_SUFFIXES = {
    ".jsonl": "jsonl",
    ".json": "json",
    ".csv": "csv",
    ".parquet": "parquet",
    ".arrow": "arrow",
}
_README_NAMES = {"README.md", "README.txt", "dataset_infos.json"}
_SPLIT_ALIASES = {
    "train": "train",
    "training": "train",
    "validation": "validation",
    "valid": "validation",
    "val": "validation",
    "dev": "validation",
    "test": "test",
}
_JSON_DECODER = json.JSONDecoder()
_JSON_ROW_ARRAY_KEYS = frozenset({"rows", "data"})
_DEFAULT_CONFIG_PARTS = frozenset({"data", "default"})
_DEFAULT_CONFIG_FIRST_PARTS = frozenset(
    {"data", "train", "test", "validation", "valid", "dev"}
)
_JSON_LIMITED_PREVIEW_CHUNK_CHARS = 16 * 1024


def _is_supported_dataset_file_name(
    name: str,
    supported_suffixes: Mapping[str, str] = _SUPPORTED_DATASET_SUFFIXES,
) -> bool:
    dot_index = name.rfind(".")
    if dot_index <= 0 or dot_index == len(name) - 1:
        return False
    suffix = name[dot_index:]
    if suffix in supported_suffixes:
        return True
    if suffix.islower():
        return False
    return suffix.lower() in supported_suffixes


@dataclass(frozen=True, slots=True)
class DatasetFile:
    relative_path: str
    size_bytes: int
    file_format: str

    def to_dict(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "file_format": self.file_format,
        }


@dataclass(frozen=True, slots=True)
class DatasetSnapshot:
    dataset_id: str
    repo_id: str
    revision: str
    snapshot_id: str
    snapshot_path: Path
    cache_repo_path: Path
    source_kind: str
    files: tuple[DatasetFile, ...]
    total_bytes: int
    splits: tuple[str, ...]
    configs: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "repo_id": self.repo_id,
            "revision": self.revision,
            "snapshot_id": self.snapshot_id,
            "snapshot_path": str(self.snapshot_path),
            "cache_repo_path": str(self.cache_repo_path),
            "source_kind": self.source_kind,
            "files": [file.to_dict() for file in self.files],
            "total_bytes": self.total_bytes,
            "splits": list(self.splits),
            "configs": list(self.configs),
            "restore_command": (
                f"melix dataset hub download --repo-id {repo_id_shell_arg(self.repo_id)} "
                f"--revision {repo_id_shell_arg(self.revision)}"
            ),
        }


@dataclass(frozen=True)
class DatasetRegistryRoot:
    root_id: str
    root_path: str
    root_order: int
    accessible: bool
    error_code: str = ""
    error_message: str = ""
    discovered_dataset_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "root_id": self.root_id,
            "root_path": self.root_path,
            "root_order": self.root_order,
            "accessible": self.accessible,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "discovered_dataset_ids": list(self.discovered_dataset_ids),
        }


@dataclass(frozen=True)
class DatasetDownloadResult:
    snapshot: DatasetSnapshot
    manifest: dict[str, Any]


@dataclass(frozen=True)
class DatasetRemoveResult:
    removed_snapshot: DatasetSnapshot
    manifest: dict[str, Any]


class DatasetCatalog:
    def __init__(self, environment: Mapping[str, str] | None = None) -> None:
        self._environment = dict(environment or os.environ)

    def registry_snapshot_payload(
        self,
        *,
        repo_id: str = "",
        revision: str = "",
        roots: Iterable[Path | str] | None = None,
    ) -> dict[str, Any]:
        root_records: list[DatasetRegistryRoot] = []
        datasets: list[DatasetSnapshot] = []
        normalized_repo_id = _normalized(repo_id)
        normalized_revision = _normalized(revision)

        for index, root in enumerate(self._resolved_roots(roots), start=1):
            root_path = Path(root).expanduser().resolve()
            root_id = _root_id(root_path)
            if not root_path.is_dir():
                root_records.append(
                    DatasetRegistryRoot(
                        root_id=root_id,
                        root_path=str(root_path),
                        root_order=index,
                        accessible=False,
                        error_code="not_found",
                        error_message="Dataset registry root does not exist.",
                    )
                )
                continue

            discovered_for_root: list[str] = []
            try:
                root_snapshots = tuple(self._scan_root(root_path))
            except OSError as exc:
                root_records.append(
                    DatasetRegistryRoot(
                        root_id=root_id,
                        root_path=str(root_path),
                        root_order=index,
                        accessible=False,
                        error_code="scan_failed",
                        error_message=str(exc),
                    )
                )
                continue

            for snapshot in root_snapshots:
                if normalized_repo_id and snapshot.repo_id != normalized_repo_id:
                    continue
                if normalized_revision and snapshot.revision != normalized_revision and snapshot.snapshot_id != normalized_revision:
                    continue
                datasets.append(snapshot)
                discovered_for_root.append(snapshot.dataset_id)

            root_records.append(
                DatasetRegistryRoot(
                    root_id=root_id,
                    root_path=str(root_path),
                    root_order=index,
                    accessible=True,
                    discovered_dataset_ids=tuple(sorted(discovered_for_root)),
                )
            )

        return {
            "schema_version": "melix.dataset_registry_snapshot.v1",
            "scanned_at_unix_ms": int(time.time() * 1000),
            "roots": [root.to_dict() for root in root_records],
            "datasets": [snapshot.to_dict() for snapshot in sorted(datasets, key=lambda item: item.dataset_id)],
        }

    def resolve_snapshot(
        self,
        *,
        repo_id: str,
        revision: str = "",
        snapshot_id: str = "",
        roots: Iterable[Path | str] | None = None,
    ) -> DatasetSnapshot | None:
        normalized_repo_id = _normalized(repo_id)
        normalized_revision = _normalized(revision) or "main"
        normalized_snapshot_id = _normalized(snapshot_id)
        if not normalized_repo_id:
            return None
        for root in self._resolved_roots(roots):
            root_path = Path(root).expanduser().resolve()
            if not root_path.is_dir():
                continue
            for snapshot in self._scan_root(root_path):
                if snapshot.repo_id != normalized_repo_id:
                    continue
                if normalized_snapshot_id:
                    if snapshot.snapshot_id == normalized_snapshot_id:
                        return snapshot
                    continue
                if snapshot.revision == normalized_revision or snapshot.snapshot_id == normalized_revision:
                    return snapshot
        return None

    def snapshot_for_path(self, snapshot_path: Path) -> DatasetSnapshot | None:
        resolved_snapshot_path = Path(snapshot_path).expanduser().resolve()
        for root in self._resolved_roots(None):
            root_path = Path(root).expanduser().resolve()
            try:
                relative_parts = resolved_snapshot_path.relative_to(root_path).parts
            except ValueError:
                continue
            if len(relative_parts) < 3 or relative_parts[1] != "snapshots":
                continue
            repo_id = _hf_dataset_repo_id(root_path / relative_parts[0])
            if repo_id is None:
                continue
            cache_repo_dir = root_path / relative_parts[0]
            revision = _hf_cache_revision(cache_repo_dir, relative_parts[2])
            return _build_dataset_snapshot(
                cache_repo_dir=cache_repo_dir,
                repo_id=repo_id,
                snapshot_dir=resolved_snapshot_path,
                revision=revision,
            )
        return None

    def download_hf_dataset(
        self,
        *,
        repo_id: str,
        revision: str = "main",
        hf_token: str = "",
        job_id: str = "",
        output_dir: Path | None = None,
    ) -> DatasetDownloadResult:
        normalized_repo_id = _normalized(repo_id)
        if not normalized_repo_id:
            raise ModelOperationError(
                code="invalid_argument",
                message="dataset download requires a Hugging Face repo id.",
            )
        normalized_revision = _normalized(revision) or "main"
        try:
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise ModelOperationError(
                code="unavailable",
                message="huggingface_hub is required for dataset downloads.",
            ) from exc

        kwargs: dict[str, object] = {
            "repo_id": normalized_repo_id,
            "repo_type": "dataset",
            "revision": normalized_revision,
            "cache_dir": os.fspath(default_huggingface_cache_root(self._environment)),
        }
        token = _normalized(hf_token)
        if token:
            kwargs["token"] = token

        try:
            downloaded = snapshot_download(**kwargs)
        except Exception as exc:
            if _is_huggingface_auth_failure(exc):
                raise ModelOperationError(
                    code="hf_auth_failed",
                    message="Hugging Face authentication failed. Check your token and try again.",
                ) from exc
            if _is_huggingface_hub_failure(exc):
                raise ModelOperationError(
                    code="unavailable",
                    message=f"dataset download failed for {normalized_repo_id}: {exc}",
                ) from exc
            raise

        snapshot = self.snapshot_for_path(Path(downloaded))
        if snapshot is None:
            snapshot_path = Path(downloaded).resolve()
            cache_repo_dir = snapshot_path.parents[1] if len(snapshot_path.parents) >= 2 else snapshot_path.parent
            snapshot = _build_dataset_snapshot(
                cache_repo_dir=cache_repo_dir,
                repo_id=normalized_repo_id,
                snapshot_dir=snapshot_path,
                revision=normalized_revision,
            )
        manifest = _dataset_operation_manifest(
            operation="dataset_download",
            job_id=job_id,
            output_dir=output_dir,
            dataset=snapshot,
            status="completed",
            extra={
                "downloaded_bytes": snapshot.total_bytes,
                "total_bytes": snapshot.total_bytes,
                "ext": {
                    "melix.source_kind": "hf_dataset",
                    "melix.hf_dataset_repo_id": normalized_repo_id,
                    "melix.hf_revision": normalized_revision,
                    "melix.dataset_path": str(snapshot.snapshot_path),
                },
            },
        )
        return DatasetDownloadResult(snapshot=snapshot, manifest=manifest)

    def remove_hf_dataset_snapshot(
        self,
        *,
        repo_id: str,
        revision: str = "",
        snapshot_id: str = "",
        job_id: str = "",
        output_dir: Path | None = None,
    ) -> DatasetRemoveResult:
        normalized_repo_id = _normalized(repo_id)
        if not normalized_repo_id:
            raise ModelOperationError(
                code="invalid_argument",
                message="dataset remove requires --repo-id.",
            )
        snapshot = self.resolve_snapshot(
            repo_id=normalized_repo_id,
            revision=_normalized(revision) or "main",
            snapshot_id=snapshot_id,
        )
        if snapshot is None:
            raise ModelOperationError(
                code="not_found",
                message="No matching managed dataset snapshot was found.",
                details={
                    "repo_id": normalized_repo_id,
                    "revision": _normalized(revision) or "main",
                    "snapshot_id": _normalized(snapshot_id),
                },
            )

        shutil.rmtree(snapshot.snapshot_path)
        manifest = _dataset_operation_manifest(
            operation="dataset_remove",
            job_id=job_id,
            output_dir=output_dir,
            dataset=snapshot,
            status="completed",
            extra={
                "removed_snapshot_path": str(snapshot.snapshot_path),
                "removed_snapshot_id": snapshot.snapshot_id,
            },
        )
        return DatasetRemoveResult(removed_snapshot=snapshot, manifest=manifest)

    def _resolved_roots(self, roots: Iterable[Path | str] | None) -> tuple[Path, ...]:
        if roots is not None:
            raw_roots = [Path(root) for root in roots]
        else:
            raw_roots = [default_huggingface_cache_root(self._environment)]
        resolved: list[Path] = []
        seen: set[str] = set()
        for root in raw_roots:
            canonical = str(Path(root).expanduser().resolve())
            if canonical in seen:
                continue
            seen.add(canonical)
            resolved.append(Path(canonical))
        return tuple(resolved)

    @staticmethod
    def _scan_root(root: Path) -> Iterator[DatasetSnapshot]:
        for cache_repo_dir in _sorted_child_directories(root, name_prefix="datasets--"):
            repo_id = _hf_dataset_repo_id(cache_repo_dir)
            if repo_id is None:
                continue
            snapshots_dir = cache_repo_dir / "snapshots"
            if not snapshots_dir.is_dir():
                continue
            snapshot_dirs = _sorted_child_directories(snapshots_dir)
            revision_map = _hf_cache_revision_map(
                cache_repo_dir,
                snapshot_ids={snapshot_dir.name for snapshot_dir in snapshot_dirs},
            )
            for snapshot_dir in snapshot_dirs:
                revision = _hf_cache_revision(cache_repo_dir, snapshot_dir.name, revision_map=revision_map)
                yield _build_dataset_snapshot(
                    cache_repo_dir=cache_repo_dir,
                    repo_id=repo_id,
                    snapshot_dir=snapshot_dir.resolve(),
                    revision=revision,
                )


def default_huggingface_cache_root(environment: Mapping[str, str] | None = None) -> Path:
    env = environment or os.environ
    home = _normalized(env.get("HOME"))
    root = (Path(home).expanduser() if home else Path.home()) / ".cache" / "huggingface" / "hub"
    return root.resolve()


def resolve_cached_hf_dataset_snapshot(
    *,
    repo_id: str,
    revision: str = "main",
    environment: Mapping[str, str] | None = None,
) -> DatasetSnapshot | None:
    return DatasetCatalog(environment=environment).resolve_snapshot(repo_id=repo_id, revision=revision or "main")


def read_hf_dataset_snapshot_rows(
    snapshot_path: Path,
    *,
    split: str = "",
    limit: int | None = None,
) -> list[dict[str, Any]]:
    if limit is not None and limit <= 0:
        return []
    resolved_snapshot_path = Path(snapshot_path).expanduser().resolve()
    normalized_split = _normalized(split)
    rows: list[dict[str, Any]] = []
    if limit is not None and not normalized_split:
        if limit == 1:
            first_path = _first_supported_dataset_file(resolved_snapshot_path)
            if first_path is None:
                return []
            return _read_rows_from_file(first_path, limit=1)
        selected_files = _iter_limited_preview_dataset_files(resolved_snapshot_path, limit=limit)
    else:
        selected_files = _iter_selected_dataset_files(resolved_snapshot_path, split=normalized_split)
    remaining = limit
    for path in selected_files:
        if remaining is not None and remaining <= 0:
            return rows
        file_rows = _read_rows_from_file(path, limit=remaining)
        rows.extend(file_rows)
        if remaining is not None:
            remaining -= len(file_rows)
            if remaining <= 0:
                return rows
    return rows


def _iter_selected_dataset_files(snapshot_path: Path, *, split: str) -> Iterator[Path]:
    if split:
        yield from _iter_matching_dataset_files(snapshot_path, split=split)
        return
    for path in _iter_supported_dataset_files(snapshot_path):
        if path.name not in _README_NAMES:
            yield path


def _iter_first_preview_dataset_file(snapshot_path: Path) -> Iterator[Path]:
    yield from _iter_limited_preview_dataset_files(snapshot_path, limit=1)


def _iter_limited_preview_dataset_files(directory: Path, *, limit: int) -> Iterator[Path]:
    if limit == 1:
        first_path = _first_supported_dataset_file(directory)
        if first_path is not None:
            yield first_path
        return
    emitted = 0
    previous_name = ""
    make_path = Path
    first_records = _first_supported_scan_entry_records
    iter_limited = _iter_limited_preview_dataset_files
    while emitted < limit:
        next_entries = first_records(
            directory,
            after=previous_name,
            limit=limit - emitted,
        )
        if not next_entries:
            return
        for name, path, is_directory, is_file in next_entries:
            previous_name = name
            entry_path = make_path(path)
            if is_directory:
                for nested_path in iter_limited(entry_path, limit=limit - emitted):
                    yield nested_path
                    emitted += 1
                    if emitted >= limit:
                        return
                continue
            if is_file:
                yield entry_path
                emitted += 1
                if emitted >= limit:
                    return


def _first_supported_scan_entries(
    directory: Path,
    *,
    after: str,
    limit: int,
) -> list[tuple[str, Path, bool, bool]]:
    return [
        (name, Path(path), is_dir, is_file)
        for name, path, is_dir, is_file in _first_supported_scan_entry_records(
            directory,
            after=after,
            limit=limit,
        )
    ]


def _first_supported_scan_entry_records(
    directory: Path,
    *,
    after: str,
    limit: int,
) -> list[tuple[str, str, bool, bool]]:
    if limit <= 0:
        return []
    try:
        with os.scandir(os.fspath(directory)) as entries:
            return heapq.nsmallest(
                limit,
                _supported_scan_entry_records(entries, after=after),
                key=lambda item: item[0],
            )
    except OSError:
        return []


def _supported_scan_entry_records(
    entries: Iterable[os.DirEntry[str]],
    *,
    after: str,
) -> Iterator[tuple[str, str, bool, bool]]:
    for entry in entries:
        name = entry.name
        if name <= after:
            continue
        is_readme = name in _README_NAMES
        is_supported = False if is_readme else _is_supported_dataset_file_name(name)
        if is_supported:
            try:
                if entry.is_file(follow_symlinks=False):
                    yield name, entry.path, False, True
                    continue
            except OSError:
                pass
        try:
            is_dir = entry.is_dir(follow_symlinks=False)
            if is_dir:
                yield name, entry.path, True, False
                continue
        except OSError:
            continue
        if is_readme or not is_supported:
            continue


def _first_supported_dataset_file(directory: Path) -> Path | None:
    previous_name = ""
    while True:
        next_entry = _next_supported_scan_entry(directory, after=previous_name)
        if next_entry is None:
            return None
        name, path, is_directory, is_file = next_entry
        previous_name = name
        if is_directory:
            nested = _first_supported_dataset_file(path)
            if nested is not None:
                return nested
            continue
        if is_file:
            return path


def _next_supported_scan_entry(directory: Path, *, after: str) -> tuple[str, Path, bool, bool] | None:
    best_name = ""
    best_path_raw = ""
    best_is_dir = False
    best_is_file = False
    readme_names = _README_NAMES
    is_supported_dataset_file_name = _is_supported_dataset_file_name
    make_path = Path
    try:
        with os.scandir(os.fspath(directory)) as entries:
            for entry in entries:
                name = entry.name
                if name <= after or (best_name and name >= best_name):
                    continue
                is_readme = name in readme_names
                is_supported = False if is_readme else is_supported_dataset_file_name(name)
                if is_supported:
                    try:
                        if entry.is_file(follow_symlinks=False):
                            best_name = name
                            best_path_raw = entry.path
                            best_is_dir = False
                            best_is_file = True
                            continue
                    except OSError:
                        pass
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                if not is_dir:
                    continue
                best_name = name
                best_path_raw = entry.path
                best_is_dir = True
                best_is_file = False
    except OSError:
        return None
    if not best_path_raw:
        return None
    return best_name, make_path(best_path_raw), best_is_dir, best_is_file


def _selected_dataset_files(snapshot_path: Path, *, split: str) -> tuple[Path, ...]:
    normalized_split = _normalized(split)
    if normalized_split:
        return tuple(_iter_matching_dataset_files(snapshot_path, split=normalized_split))
    return tuple(
        path
        for path in _iter_supported_dataset_files(snapshot_path)
        if path.name not in _README_NAMES
    )


def _iter_matching_dataset_files(snapshot_path: Path, *, split: str) -> Iterator[Path]:
    normalized_split = _normalized(split)
    if not normalized_split:
        return
    for path in _iter_supported_dataset_files(snapshot_path):
        if path.name in _README_NAMES:
            continue
        if _path_matches_split(path.relative_to(snapshot_path), normalized_split):
            yield path


def _read_rows_from_file(path: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    if limit is not None and limit <= 0:
        return []
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        loads = json.loads
        if limit == 1:
            with path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    if raw_line.isspace():
                        continue
                    payload = loads(raw_line)
                    if isinstance(payload, dict):
                        return [payload]
            return []
        rows: list[dict[str, Any]] = []
        append_row = rows.append
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                if raw_line.isspace():
                    continue
                payload = loads(raw_line)
                if isinstance(payload, dict):
                    append_row(payload)
                    if limit is not None and len(rows) >= limit:
                        break
        return rows
    if suffix == ".json":
        if limit is not None:
            limited_rows = _limited_rows_from_json_file(path, limit=limit)
            if limited_rows is not None:
                return limited_rows
        json_text = path.read_text(encoding="utf-8")
        payload = json.loads(json_text)
        return _rows_from_json_payload(payload, limit=limit)
    if suffix == ".csv":
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                rows.append(dict(row))
                if limit is not None and len(rows) >= limit:
                    break
        return rows
    if suffix == ".parquet":
        try:
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise ModelOperationError(
                code="unavailable",
                message="pyarrow is required to read local parquet dataset snapshots.",
            ) from exc
        if limit is not None and hasattr(pq, "ParquetFile"):
            rows: list[dict[str, Any]] = []
            parquet_file = pq.ParquetFile(path)
            for batch in parquet_file.iter_batches(batch_size=max(limit, 1)):
                _extend_dict_rows_from_pylist(rows, batch.to_pylist(), limit=limit)
                if len(rows) >= limit:
                    break
            return rows
        return _dict_rows_from_pyarrow_table(pq.read_table(path), limit=limit)
    if suffix == ".arrow":
        try:
            import pyarrow.ipc as ipc
        except ImportError as exc:
            raise ModelOperationError(
                code="unavailable",
                message="pyarrow is required to read local Arrow dataset snapshots.",
            ) from exc
        with ipc.open_file(path) as reader:
            if limit is not None and hasattr(reader, "get_batch"):
                rows: list[dict[str, Any]] = []
                for batch_index in range(getattr(reader, "num_record_batches", 0)):
                    _extend_dict_rows_from_pylist(
                        rows,
                        reader.get_batch(batch_index).to_pylist(),
                        limit=limit,
                    )
                    if len(rows) >= limit:
                        break
                return rows
            table = reader.read_all()
            return _dict_rows_from_pyarrow_table(table, limit=limit)
    return []


def _extend_dict_rows_from_pylist(
    rows: list[dict[str, Any]],
    values: Iterable[Any],
    *,
    limit: int | None,
) -> None:
    for row in values:
        if isinstance(row, dict):
            rows.append(row)
            if limit is not None and len(rows) >= limit:
                return


def _dict_rows_from_pyarrow_table(table: Any, *, limit: int | None) -> list[dict[str, Any]]:
    if limit is not None:
        table = table.slice(0, limit)
    rows: list[dict[str, Any]] = []
    _extend_dict_rows_from_pylist(rows, table.to_pylist(), limit=limit)
    return rows


def _limit_rows(rows: list[dict[str, Any]], limit: int | None) -> list[dict[str, Any]]:
    if limit is None:
        return rows
    return rows[:limit]


def _limited_rows_from_json_file(path: Path, *, limit: int) -> list[dict[str, Any]] | None:
    if limit <= 0:
        return []
    json_text = ""
    with path.open("r", encoding="utf-8") as handle:
        while True:
            chunk = handle.read(_JSON_LIMITED_PREVIEW_CHUNK_CHARS)
            if not chunk:
                break
            json_text = chunk if not json_text else json_text + chunk
            limited_rows = _limited_rows_from_json_text(json_text, limit=limit)
            if limited_rows is not None and len(limited_rows) >= limit:
                return limited_rows
    if not json_text:
        return None
    return _limited_rows_from_json_text(json_text, limit=limit)


def _limited_rows_from_json_text(json_text: str, *, limit: int) -> list[dict[str, Any]] | None:
    if limit <= 0:
        return []
    cursor = _json_text_first_array_start(json_text)
    if cursor is None:
        return None
    rows: list[dict[str, Any]] = []
    decoder = _JSON_DECODER
    text_length = len(json_text)
    cursor += 1
    while cursor < text_length:
        while cursor < text_length and json_text[cursor].isspace():
            cursor += 1
        if cursor >= text_length or json_text[cursor] == "]":
            return rows
        try:
            value, cursor = decoder.raw_decode(json_text, cursor)
        except json.JSONDecodeError:
            return None
        if isinstance(value, dict):
            if limit == 1:
                return [value]
            rows.append(value)
            if len(rows) >= limit:
                return rows
        while cursor < text_length and json_text[cursor].isspace():
            cursor += 1
        if cursor < text_length and json_text[cursor] == ",":
            cursor += 1
            continue
        if cursor < text_length and json_text[cursor] == "]":
            return rows
        return None
    return None


def _direct_first_row_array_start(json_text: str, object_start: int, text_length: int) -> int | None:
    cursor = object_start + 1
    while cursor < text_length and json_text[cursor].isspace():
        cursor += 1
    if json_text.startswith('"rows"', cursor):
        cursor += 6
    elif json_text.startswith('"data"', cursor):
        cursor += 6
    else:
        return None
    while cursor < text_length and json_text[cursor].isspace():
        cursor += 1
    if cursor >= text_length or json_text[cursor] != ":":
        return None
    cursor += 1
    while cursor < text_length and json_text[cursor].isspace():
        cursor += 1
    if cursor < text_length and json_text[cursor] == "[":
        return cursor
    return None


def _json_text_first_array_start(json_text: str) -> int | None:
    cursor = 0
    text_length = len(json_text)
    while cursor < text_length and json_text[cursor].isspace():
        cursor += 1
    if cursor >= text_length:
        return None
    if json_text[cursor] == "[":
        return cursor
    if json_text[cursor] != "{":
        return None
    direct_array_start = _direct_first_row_array_start(json_text, cursor, text_length)
    if direct_array_start is not None:
        return direct_array_start

    decoder = _JSON_DECODER
    cursor += 1
    while cursor < text_length:
        while cursor < text_length and json_text[cursor].isspace():
            cursor += 1
        if cursor >= text_length or json_text[cursor] == "}":
            return None
        try:
            key, cursor = decoder.raw_decode(json_text, cursor)
        except json.JSONDecodeError:
            return None
        if not isinstance(key, str):
            return None
        while cursor < text_length and json_text[cursor].isspace():
            cursor += 1
        if cursor >= text_length or json_text[cursor] != ":":
            return None
        cursor += 1
        while cursor < text_length and json_text[cursor].isspace():
            cursor += 1
        if key in _JSON_ROW_ARRAY_KEYS and cursor < text_length and json_text[cursor] == "[":
            return cursor
        try:
            _, cursor = decoder.raw_decode(json_text, cursor)
        except json.JSONDecodeError:
            return None
        while cursor < text_length and json_text[cursor].isspace():
            cursor += 1
        if cursor < text_length and json_text[cursor] == ",":
            cursor += 1
            continue
        if cursor < text_length and json_text[cursor] == "}":
            return None
        return None
    return None


def _append_limited_dict_rows(
    rows: list[dict[str, Any]],
    candidates: list[Any],
    *,
    limit: int | None,
) -> list[dict[str, Any]]:
    for row in candidates:
        if isinstance(row, dict):
            rows.append(row)
            if limit is not None and len(rows) >= limit:
                break
    return rows


def _rows_from_json_payload(payload: Any, *, limit: int | None = None) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return _append_limited_dict_rows([], payload, limit=limit)
    if isinstance(payload, dict):
        rows = payload.get("rows")
        if isinstance(rows, list):
            return _append_limited_dict_rows([], rows, limit=limit)
        data = payload.get("data")
        if isinstance(data, list):
            return _append_limited_dict_rows([], data, limit=limit)
        for value in payload.values():
            if isinstance(value, list) and all(isinstance(row, dict) for row in value):
                return _limit_rows(value, limit)
        return [payload]
    return []


def _dataset_operation_manifest(
    *,
    operation: str,
    job_id: str,
    output_dir: Path | None,
    dataset: DatasetSnapshot,
    status: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "melix.dataset_operation.v1",
        "operation": operation,
        "job_id": job_id,
        "status": status,
        "dataset_id": dataset.dataset_id,
        "repo_id": dataset.repo_id,
        "revision": dataset.revision,
        "snapshot_id": dataset.snapshot_id,
        "snapshot_path": str(dataset.snapshot_path),
        "source_kind": dataset.source_kind,
        "output_dir": str(output_dir) if output_dir is not None else "",
        "dataset": dataset.to_dict(),
    }
    if extra:
        payload.update(extra)
    return payload


def _build_dataset_snapshot(
    *,
    cache_repo_dir: Path,
    repo_id: str,
    snapshot_dir: Path,
    revision: str,
) -> DatasetSnapshot:
    dataset_files: list[DatasetFile] = []
    total_bytes = 0
    split_names: set[str] = set()
    config_names: set[str] = set()
    for dataset_file in _dataset_files(snapshot_dir):
        dataset_files.append(dataset_file)
        total_bytes += dataset_file.size_bytes
        split, config = _inferred_split_and_config(dataset_file.relative_path)
        if split:
            split_names.add(split)
        if config:
            config_names.add(config)
    files = tuple(dataset_files)
    splits = tuple(sorted(split_names))
    configs = tuple(sorted(config_names))
    revision_label = revision or snapshot_dir.name
    return DatasetSnapshot(
        dataset_id=f"{repo_id}@{revision_label}",
        repo_id=repo_id,
        revision=revision_label,
        snapshot_id=snapshot_dir.name,
        snapshot_path=snapshot_dir,
        cache_repo_path=cache_repo_dir.resolve(),
        source_kind="hf_cache_snapshot",
        files=files,
        total_bytes=total_bytes,
        splits=splits,
        configs=configs,
    )


def _dataset_files(snapshot_dir: Path) -> Iterator[DatasetFile]:
    for relative_path, file_format, size_bytes in _iter_supported_dataset_file_stat_records(snapshot_dir):
        yield DatasetFile(
            relative_path=relative_path,
            size_bytes=size_bytes,
            file_format=file_format,
        )


def _iter_supported_dataset_file_stat_records(
    snapshot_dir: Path, relative_prefix: str = ""
) -> Iterator[tuple[str, str, int]]:
    try:
        with os.scandir(os.fspath(snapshot_dir)) as entries:
            child_entries = sorted(entries, key=lambda entry: entry.name)
    except OSError:
        return
    for entry in child_entries:
        name = entry.name
        relative_path = f"{relative_prefix}{name}"
        try:
            if entry.is_dir():
                yield from _iter_supported_dataset_file_stat_records(
                    Path(entry.path), f"{relative_path}/"
                )
                continue
            file_format = _dataset_file_format_name(name)
            if not file_format or not entry.is_file():
                continue
            stat_result = entry.stat()
        except OSError:
            continue
        yield relative_path, file_format, stat_result.st_size


def _iter_supported_dataset_files(snapshot_dir: Path) -> Iterator[Path]:
    for path, _relative_path in _iter_supported_dataset_file_entries(snapshot_dir):
        yield path


def _iter_supported_dataset_file_entries(
    snapshot_dir: Path, relative_prefix: str = ""
) -> Iterator[tuple[Path, str]]:
    for path, relative_path, _file_format in _iter_supported_dataset_file_records(
        snapshot_dir,
        relative_prefix=relative_prefix,
    ):
        yield path, relative_path


def _iter_supported_dataset_file_records(
    snapshot_dir: Path, relative_prefix: str = ""
) -> Iterator[tuple[Path, str, str]]:
    try:
        with os.scandir(os.fspath(snapshot_dir)) as entries:
            child_entries = sorted(entries, key=lambda entry: entry.name)
    except OSError:
        return
    for entry in child_entries:
        name = entry.name
        relative_path = f"{relative_prefix}{name}"
        try:
            if entry.is_dir():
                yield from _iter_supported_dataset_file_records(
                    Path(entry.path), f"{relative_path}/"
                )
                continue
            if not entry.is_file():
                continue
        except OSError:
            continue
        file_format = _dataset_file_format_name(name)
        if file_format:
            yield Path(entry.path), relative_path, file_format


def _dataset_file_format(path: Path) -> str:
    return _dataset_file_format_name(path.name)


def _dataset_file_format_name(name: str) -> str:
    if name in _README_NAMES:
        return "metadata"
    dot_index = name.rfind(".")
    if dot_index <= 0 or dot_index == len(name) - 1:
        return ""
    suffix = name[dot_index:]
    file_format = _SUPPORTED_DATASET_SUFFIXES.get(suffix)
    if file_format is not None:
        return file_format
    if suffix.islower():
        return ""
    return _SUPPORTED_DATASET_SUFFIXES.get(suffix.lower(), "")


def _inferred_split(relative_path: str) -> str:
    return _inferred_split_and_config(relative_path)[0]


def _inferred_config(relative_path: str) -> str:
    return _inferred_split_and_config(relative_path)[1]


def _inferred_split_and_config(relative_path: str) -> tuple[str, str]:
    slash_index = relative_path.find("/")
    if slash_index > 0 and "\\" not in relative_path:
        next_slash_index = relative_path.find("/", slash_index + 1)
        if next_slash_index < 0 and slash_index < len(relative_path) - 1:
            first = relative_path[:slash_index]
            filename = relative_path[slash_index + 1 :]
            stem = filename.rsplit(".", 1)[0]
            split = _split_alias_from_candidate(stem)
            if not split and first not in _DEFAULT_CONFIG_PARTS:
                split = _split_alias_from_candidate(first)
            if first in _DEFAULT_CONFIG_FIRST_PARTS:
                return split, "default"
            return split, first
    parts = [part for part in relative_path.replace("\\", "/").split("/") if part]
    if not parts:
        return "", "default"
    filename = parts[-1]
    stem = filename.rsplit(".", 1)[0]
    split = _split_alias_from_candidate(stem)
    if not split:
        for candidate in parts[:-1]:
            if candidate in _DEFAULT_CONFIG_PARTS:
                continue
            split = _split_alias_from_candidate(candidate)
            if split:
                break
    if len(parts) < 2:
        return split, "default"
    first = parts[0]
    if first in _DEFAULT_CONFIG_FIRST_PARTS:
        return split, "default"
    return split, first


def _split_alias_from_candidate(candidate: str) -> str:
    delimiter_index = _first_split_alias_delimiter(candidate)
    prefix = candidate[:delimiter_index] if delimiter_index >= 0 else candidate
    split = _SPLIT_ALIASES.get(prefix)
    if split is not None:
        return split
    lowered = prefix.lower()
    if lowered == prefix:
        return ""
    return _SPLIT_ALIASES.get(lowered, "")


def _first_split_alias_delimiter(candidate: str) -> int:
    dash_index = candidate.find("-")
    underscore_index = candidate.find("_")
    if dash_index < 0:
        return underscore_index
    if underscore_index < 0:
        return dash_index
    return dash_index if dash_index < underscore_index else underscore_index


def _path_matches_split(relative_path: Path, split: str) -> bool:
    normalized_split, split_dash_prefix, split_underscore_prefix = _split_match_tokens(split)
    part_matches_split = _path_part_matches_split
    if part_matches_split(
        relative_path.name,
        normalized_split,
        split_dash_prefix,
        split_underscore_prefix,
    ):
        return True
    parts = relative_path.parts
    for part in parts[:-1]:
        if part_matches_split(
            part,
            normalized_split,
            split_dash_prefix,
            split_underscore_prefix,
        ):
            return True
    return False


@lru_cache(maxsize=16)
def _split_match_tokens(split: str) -> tuple[str, str, str]:
    normalized_split = split.lower()
    return normalized_split, f"{normalized_split}-", f"{normalized_split}_"


def _ascii_char_matches_lowercase(character: str, lowercase_character: str) -> bool:
    character_code = ord(character)
    if 65 <= character_code <= 90:
        character_code += 32
    return character_code == ord(lowercase_character)


def _path_part_matches_split(
    part: str,
    normalized_split: str,
    split_dash_prefix: str,
    split_underscore_prefix: str,
) -> bool:
    if not part or not normalized_split:
        return False
    first_char = part[0]
    split_first_char = normalized_split[0]
    if first_char != split_first_char and not _ascii_char_matches_lowercase(first_char, split_first_char):
        return False
    if (
        part == normalized_split
        or part.startswith(split_dash_prefix)
        or part.startswith(split_underscore_prefix)
    ):
        return True
    dot_index = part.rfind(".")
    if dot_index > 0 and dot_index < len(part) - 1:
        stem = part[:dot_index]
        if (
            stem == normalized_split
            or stem.startswith(split_dash_prefix)
            or stem.startswith(split_underscore_prefix)
        ):
            return True
    if first_char == split_first_char:
        return False
    lowered = part.lower()
    if (
        lowered == normalized_split
        or lowered.startswith(split_dash_prefix)
        or lowered.startswith(split_underscore_prefix)
    ):
        return True
    dot_index = lowered.rfind(".")
    if dot_index <= 0 or dot_index == len(lowered) - 1:
        return False
    stem = lowered[:dot_index]
    return (
        stem == normalized_split
        or stem.startswith(split_dash_prefix)
        or stem.startswith(split_underscore_prefix)
    )


def _string_stem(name: str) -> str:
    if not name:
        return name
    if name.endswith(".") and not name.endswith("..") and not name.startswith("."):
        return name[:-1]
    dot_index = name.rfind(".")
    if dot_index <= 0:
        return name
    return name[:dot_index]


def _hf_dataset_repo_id(cache_repo_dir: Path) -> str | None:
    name = cache_repo_dir.name
    if not name.startswith("datasets--"):
        return None
    payload = name.removeprefix("datasets--")
    if not payload:
        return None
    parts = payload.split("--", maxsplit=1)
    if len(parts) == 1:
        return parts[0] or None
    if not parts[0] or not parts[1]:
        return None
    return f"{parts[0]}/{parts[1]}"


def _hf_cache_revision_map(
    cache_repo_dir: Path,
    *,
    snapshot_ids: set[str] | None = None,
) -> dict[str, str]:
    refs_dir = cache_repo_dir / "refs"
    revisions: dict[str, str] = {}
    remaining_snapshot_ids = set(snapshot_ids) if snapshot_ids is not None else None
    if remaining_snapshot_ids is not None and not remaining_snapshot_ids:
        return revisions
    if not refs_dir.is_dir():
        return revisions

    try:
        for ref_path, relative_name in _iter_relative_file_paths_sorted(refs_dir):
            try:
                snapshot_id = ref_path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if not snapshot_id:
                continue
            if remaining_snapshot_ids is not None and snapshot_id not in remaining_snapshot_ids:
                continue
            revisions.setdefault(snapshot_id, relative_name)
            if remaining_snapshot_ids is not None:
                remaining_snapshot_ids.discard(snapshot_id)
                if not remaining_snapshot_ids:
                    return revisions
    except OSError:
        return revisions
    return revisions


def _hf_cache_revision(
    cache_repo_dir: Path,
    snapshot_id: str,
    *,
    revision_map: Mapping[str, str] | None = None,
) -> str:
    revisions = revision_map if revision_map is not None else _hf_cache_revision_map(cache_repo_dir)
    return revisions.get(snapshot_id, snapshot_id)


def _iter_relative_file_paths_sorted(root: Path, *, prefix: str = "") -> Iterable[tuple[Path, str]]:
    try:
        with os.scandir(os.fspath(root)) as entries:
            child_entries = sorted(entries, key=lambda entry: entry.name)
    except OSError as exc:
        raise OSError(str(exc)) from exc
    for entry in child_entries:
        try:
            if entry.is_dir():
                child_prefix = f"{prefix}{entry.name}/"
                yield from _iter_relative_file_paths_sorted(root / entry.name, prefix=child_prefix)
                continue
            if entry.is_file():
                yield root / entry.name, f"{prefix}{entry.name}"
        except OSError as exc:
            raise OSError(str(exc)) from exc


def _sorted_child_directories(root: Path, *, name_prefix: str | None = None) -> tuple[Path, ...]:
    child_names: list[str] = []
    try:
        with os.scandir(os.fspath(root)) as entries:
            for entry in entries:
                if name_prefix is not None and not entry.name.startswith(name_prefix):
                    continue
                try:
                    if entry.is_dir():
                        child_names.append(entry.name)
                except OSError:
                    continue
    except OSError:
        return ()
    return tuple(root / name for name in sorted(child_names))


def _root_id(root: Path) -> str:
    digest = hashlib.sha1(os.fspath(root).encode("utf-8")).hexdigest()[:12]
    return f"dataset-root-{digest}"


def _normalized(value: str | None) -> str:
    return (value or "").strip()


def _is_huggingface_hub_failure(exc: Exception) -> bool:
    module = type(exc).__module__
    return module.startswith("huggingface_hub") or module.startswith("requests")


def _is_huggingface_auth_failure(exc: Exception) -> bool:
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if status_code in {401, 403}:
        return True
    message = str(exc).lower()
    return "401" in message or "403" in message or "unauthorized" in message or "forbidden" in message


def public_ext(ext: Mapping[str, str] | Any) -> dict[str, str]:
    return {
        str(key): str(value)
        for key, value in dict(ext).items()
        if str(key) not in _HF_TOKEN_KEYS and "token" not in str(key).lower()
    }


def repo_id_shell_arg(value: str) -> str:
    if value.replace("/", "").replace("-", "").replace("_", "").replace(".", "").isalnum():
        return value
    return json.dumps(value)
