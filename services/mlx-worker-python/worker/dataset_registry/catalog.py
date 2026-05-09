from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
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


@dataclass(frozen=True)
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


@dataclass(frozen=True)
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
    resolved_snapshot_path = Path(snapshot_path).expanduser().resolve()
    normalized_split = _normalized(split)
    rows: list[dict[str, Any]] = []
    if limit == 1 and not normalized_split:
        selected_files = _iter_first_preview_dataset_file(resolved_snapshot_path)
    else:
        selected_files = _iter_selected_dataset_files(resolved_snapshot_path, split=normalized_split)
    for path in selected_files:
        remaining = None if limit is None else max(limit - len(rows), 0)
        if remaining == 0:
            return rows
        rows.extend(_read_rows_from_file(path, limit=remaining))
        if limit is not None and normalized_split and len(rows) >= limit:
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
    first_path = _first_supported_dataset_file(snapshot_path)
    if first_path is not None:
        yield first_path


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
        if is_file and name not in _README_NAMES and _dataset_file_format(path):
            return path


def _next_supported_scan_entry(directory: Path, *, after: str) -> tuple[str, Path, bool, bool] | None:
    best_name = ""
    best_path: Path | None = None
    best_is_dir = False
    best_is_file = False
    try:
        with os.scandir(os.fspath(directory)) as entries:
            for entry in entries:
                name = entry.name
                if name <= after or (best_name and name >= best_name):
                    continue
                try:
                    is_dir = entry.is_dir()
                    is_file = False if is_dir else entry.is_file()
                except OSError:
                    continue
                if not is_dir and not is_file:
                    continue
                best_name = name
                best_path = Path(entry.path)
                best_is_dir = is_dir
                best_is_file = is_file
    except OSError:
        return None
    if best_path is None:
        return None
    return best_name, best_path, best_is_dir, best_is_file


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
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                if isinstance(payload, dict):
                    rows.append(payload)
                    if limit is not None and len(rows) >= limit:
                        break
        return rows
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
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
    for path in _iter_supported_dataset_files(snapshot_dir):
        try:
            stat_result = path.stat()
        except OSError:
            continue
        yield DatasetFile(
            relative_path=os.fspath(path.relative_to(snapshot_dir)),
            size_bytes=stat_result.st_size,
            file_format=_dataset_file_format(path),
        )


def _iter_supported_dataset_files(snapshot_dir: Path) -> Iterator[Path]:
    try:
        with os.scandir(os.fspath(snapshot_dir)) as entries:
            child_entries = sorted(entries, key=lambda entry: entry.name)
    except OSError:
        return
    for entry in child_entries:
        try:
            if entry.is_dir():
                yield from _iter_supported_dataset_files(Path(entry.path))
                continue
            if not entry.is_file():
                continue
        except OSError:
            continue
        child_path = Path(entry.path)
        if _dataset_file_format(child_path):
            yield child_path


def _dataset_file_format(path: Path) -> str:
    if path.name in _README_NAMES:
        return "metadata"
    return _SUPPORTED_DATASET_SUFFIXES.get(path.suffix.lower(), "")


def _inferred_split(relative_path: str) -> str:
    return _inferred_split_and_config(relative_path)[0]


def _inferred_config(relative_path: str) -> str:
    return _inferred_split_and_config(relative_path)[1]


def _inferred_split_and_config(relative_path: str) -> tuple[str, str]:
    parts = tuple(part for part in relative_path.replace("\\", "/").split("/") if part)
    if not parts:
        return "", "default"
    filename = parts[-1]
    stem = filename.rsplit(".", 1)[0]
    candidates = [stem]
    candidates.extend(part for part in parts[:-1] if part not in {"data", "default"})
    split = ""
    for candidate in candidates:
        prefix = candidate.split("-", 1)[0].split("_", 1)[0].lower()
        if prefix in _SPLIT_ALIASES:
            split = _SPLIT_ALIASES[prefix]
            break
    if len(parts) < 2:
        return split, "default"
    first = parts[0]
    if first in {"data", "train", "test", "validation", "valid", "dev"}:
        return split, "default"
    return split, first


def _path_matches_split(relative_path: Path, split: str) -> bool:
    normalized_split = split.lower()
    for part in relative_path.parts:
        lowered = part.lower()
        stem = _string_stem(part).lower()
        if (
            lowered == normalized_split
            or lowered.startswith(f"{normalized_split}-")
            or lowered.startswith(f"{normalized_split}_")
            or stem == normalized_split
            or stem.startswith(f"{normalized_split}-")
            or stem.startswith(f"{normalized_split}_")
        ):
            return True
    return False


def _string_stem(name: str) -> str:
    if not name or name.endswith("."):
        return name
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
