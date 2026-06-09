from __future__ import annotations

from dataclasses import dataclass
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Iterable

from worker.productization.workspace_manifest import preflight_workspace


DATASET_INGEST_RECEIPT_SCHEMA_VERSION = "melix.dataset_ingest_receipt.v1"
DATASET_INGEST_RECEIPT_FILENAME = "dataset-ingest-receipt.json"
DATASET_INGEST_SEGMENTS_FILENAME = "segments.jsonl"
WORKSPACE_PREFLIGHT_RECEIPT_FILENAME = "workspace-preflight-receipt.json"
DATASET_VERSION_SCHEMA_VERSION = "melix.dataset_version.v1"
DATASET_QUALITY_SUMMARY_SCHEMA_VERSION = "melix.dataset_quality_summary.v1"
DATASET_RETRY_RECEIPT_SCHEMA_VERSION = "melix.dataset_retry_receipt.v1"
DATASET_VERSION_LIST_SCHEMA_VERSION = "melix.dataset_version_list.v1"

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")
_TOKEN_RE = re.compile(r"\b(?:sk|pk|rk|ghp|github_pat)-[A-Za-z0-9._-]{8,}\b")
_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_TEXT_SOURCE_SUFFIXES = frozenset((".md", ".markdown"))
_CODE_SOURCE_SUFFIXES = frozenset(
    (".py", ".swift", ".js", ".ts", ".java", ".go", ".rs", ".cpp", ".c", ".h")
)
_STRUCTURED_DATA_SOURCE_SUFFIXES = frozenset((".jsonl", ".json", ".csv", ".tsv"))
_SOURCE_KIND_NAME_CACHE_MAX = 4096
_SOURCE_KIND_BY_NAME: dict[str, str | None] = {}


@dataclass(frozen=True)
class DatasetIngestRequest:
    workspace_project_id: str
    workspace_manifest_path: Path | str
    input_path: Path | str
    output_dir: Path | str
    dataset_preparation_id: str
    pii_mask: bool = True
    exact_dedup: bool = True
    fuzzy_dedup: bool = True
    segmentation: bool = True
    segmentation_strategy: str = "paragraph"


@dataclass(frozen=True)
class DatasetVersionRequest:
    workspace_manifest_path: Path | str
    ingest_receipt_path: Path | str
    output_root: Path | str
    dataset_id: str
    version_id: str = ""
    created_at: str = ""
    mode: str = "chat"
    generator_model: str = "melix.local.dataset-versioner.v1"
    output_kind: str = "training"
    output_format: str = "prompt_completion"
    validation_ratio: float = 0.0
    fail_segment_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class DatasetRetryFailedRequest:
    workspace_manifest_path: Path | str
    dataset_version_path: Path | str
    output_root: Path | str
    version_id: str = ""
    created_at: str = ""
    generator_model: str = ""


def prepare_dataset_ingest(request: DatasetIngestRequest) -> dict[str, Any]:
    started = time.perf_counter()
    input_path = Path(request.input_path).expanduser().resolve()
    output_dir = Path(request.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    segments_path = output_dir / DATASET_INGEST_SEGMENTS_FILENAME
    receipt_path = output_dir / DATASET_INGEST_RECEIPT_FILENAME
    workspace_preflight_receipt_path = output_dir / WORKSPACE_PREFLIGHT_RECEIPT_FILENAME
    workspace_preflight_receipt = preflight_workspace(
        Path(request.workspace_manifest_path).expanduser(),
        receipt_output_path=workspace_preflight_receipt_path,
    )
    _write_json(workspace_preflight_receipt_path, workspace_preflight_receipt)

    if workspace_preflight_receipt.get("status") != "ready":
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        operator_failures = _workspace_preflight_failures(workspace_preflight_receipt)
        receipt = {
            "schema_version": DATASET_INGEST_RECEIPT_SCHEMA_VERSION,
            "status": "blocked",
            "workspace_project_id": request.workspace_project_id,
            "workspace_manifest_path": str(Path(request.workspace_manifest_path)),
            "workspace_preflight_receipt_path": str(workspace_preflight_receipt_path),
            "workspace_preflight_receipt": workspace_preflight_receipt,
            "dataset_preparation_id": request.dataset_preparation_id,
            "source_inventory": [],
            "cleaning_controls": _cleaning_controls(request),
            "segmentation_policy": _segmentation_policy(request),
            "segment_artifacts": {
                "segments_path": str(segments_path),
                "receipt_path": str(receipt_path),
            },
            "quality_control_summary": {
                "source_file_count": 0,
                "source_record_count": 0,
                "segment_count": 0,
                "pii_mask_count": 0,
                "exact_dedup_count": 0,
                "fuzzy_dedup_count": 0,
                "fuzzy_dedup_ratio": 0.0,
            },
            "operator_failures": operator_failures,
            "metrics": {
                "ingest_latency_ms": elapsed_ms,
                "ingest_throughput_bytes_per_second": 0.0,
                "source_file_count": 0,
                "source_record_count": 0,
                "segment_count": 0,
                "pii_mask_count": 0,
                "exact_dedup_count": 0,
                "fuzzy_dedup_count": 0,
                "fuzzy_dedup_ratio": 0.0,
                "segmentation_latency_ms": 0.0,
                "workspace_preflight_status": workspace_preflight_receipt.get("status", "unknown"),
            },
        }
        _write_json(receipt_path, receipt)
        return receipt

    operator_failures: list[dict[str, Any]] = []
    records = list(_iter_source_records(input_path, operator_failures))
    source_inventory = _source_inventory(records)
    total_bytes = sum(record["byte_size"] for record in records)

    pii_mask_count = 0
    exact_dedup_count = 0
    fuzzy_dedup_count = 0
    cleaned_records: list[dict[str, Any]] = []
    exact_seen: set[str] = set()
    fuzzy_seen: set[str] = set()

    for record in records:
        text = record["text"]
        record_pii_mask_count = 0
        if request.pii_mask:
            text, record_pii_mask_count = _mask_pii(text)
        normalized = _normalize_text(text)
        if request.exact_dedup:
            exact_key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            if exact_key in exact_seen:
                exact_dedup_count += 1
                continue
            exact_seen.add(exact_key)
        if request.fuzzy_dedup:
            fuzzy_key = _fuzzy_key(normalized)
            if fuzzy_key and fuzzy_key in fuzzy_seen:
                fuzzy_dedup_count += 1
                continue
            if fuzzy_key:
                fuzzy_seen.add(fuzzy_key)
        cleaned = dict(record)
        cleaned["text"] = text
        cleaned_records.append(cleaned)
        pii_mask_count += record_pii_mask_count

    segmentation_started = time.perf_counter()
    segments = list(_segment_records(cleaned_records, request))
    segmentation_latency_ms = (time.perf_counter() - segmentation_started) * 1000.0
    _write_jsonl(segments_path, segments)

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    fuzzy_ratio = fuzzy_dedup_count / len(records) if records else 0.0
    summary = {
        "source_file_count": len(source_inventory),
        "source_record_count": len(records),
        "segment_count": len(segments),
        "pii_mask_count": pii_mask_count,
        "exact_dedup_count": exact_dedup_count,
        "fuzzy_dedup_count": fuzzy_dedup_count,
        "fuzzy_dedup_ratio": fuzzy_ratio,
    }
    metrics = {
        "ingest_latency_ms": elapsed_ms,
        "ingest_throughput_bytes_per_second": total_bytes / max(elapsed_ms / 1000.0, 0.001),
        "source_file_count": len(source_inventory),
        "source_record_count": len(records),
        "segment_count": len(segments),
        "pii_mask_count": pii_mask_count,
        "exact_dedup_count": exact_dedup_count,
        "fuzzy_dedup_count": fuzzy_dedup_count,
        "fuzzy_dedup_ratio": fuzzy_ratio,
        "segmentation_latency_ms": segmentation_latency_ms,
        "workspace_preflight_status": workspace_preflight_receipt.get("status", "unknown"),
    }
    receipt = {
        "schema_version": DATASET_INGEST_RECEIPT_SCHEMA_VERSION,
        "status": "blocked" if operator_failures else "ready",
        "workspace_project_id": request.workspace_project_id,
        "workspace_manifest_path": str(Path(request.workspace_manifest_path)),
        "workspace_preflight_receipt_path": str(workspace_preflight_receipt_path),
        "workspace_preflight_receipt": workspace_preflight_receipt,
        "dataset_preparation_id": request.dataset_preparation_id,
        "source_inventory": source_inventory,
        "cleaning_controls": _cleaning_controls(request),
        "segmentation_policy": _segmentation_policy(request),
        "segment_artifacts": {
            "segments_path": str(segments_path),
            "receipt_path": str(receipt_path),
        },
        "quality_control_summary": summary,
        "operator_failures": operator_failures,
        "metrics": metrics,
    }
    _write_json(receipt_path, receipt)
    return receipt


def prepare_dataset_version(request: DatasetVersionRequest) -> dict[str, Any]:
    started = time.perf_counter()
    ingest_receipt_path = Path(request.ingest_receipt_path).expanduser()
    ingest_receipt = _read_json(ingest_receipt_path)
    _raise_if_ingest_receipt_blocked(ingest_receipt)
    segment_artifacts = ingest_receipt.get("segment_artifacts", {})
    if not isinstance(segment_artifacts, dict) or not segment_artifacts.get("segments_path"):
        raise ValueError("DATASET_VERSION_SOURCE_RECEIPT_MISSING: ingest receipt has no segments_path")
    segments_path = Path(str(segment_artifacts["segments_path"])).expanduser()
    segments = _read_jsonl(segments_path)
    version_id = request.version_id or _default_version_id(request.dataset_id)
    version_dir = _dataset_version_dir(request.output_root, request.dataset_id, version_id)
    if version_dir.exists():
        raise ValueError(f"DATASET_VERSION_OUTPUT_EXISTS: {version_dir}")
    version_dir.mkdir(parents=True, exist_ok=False)

    successful_segments, failed_segments = _partition_failed_segments(
        segments,
        request.fail_segment_ids,
    )
    sample_rows = [
        _sample_row(segment, request.output_format, request.generator_model)
        for segment in successful_segments
    ]
    train_rows, validation_rows = _split_dataset_version_validation(
        sample_rows,
        request.validation_ratio,
    )
    failed_rows = [_failed_segment_row(segment) for segment in failed_segments]

    samples_path = version_dir / "samples.jsonl"
    valid_path = version_dir / "valid.jsonl"
    failed_segments_path = version_dir / "failed-segments.jsonl"
    manifest_path = version_dir / "manifest.json"
    quality_summary_path = version_dir / "quality-summary.json"
    dataset_version_path = version_dir / "dataset-version.json"
    copied_receipt_path = version_dir / DATASET_INGEST_RECEIPT_FILENAME
    _write_jsonl(samples_path, train_rows)
    _write_jsonl(valid_path, validation_rows)
    _write_jsonl(failed_segments_path, failed_rows)
    _write_json(manifest_path, _training_package_manifest(
        request=request,
        version_id=version_id,
        samples_path=samples_path,
        valid_path=valid_path,
        quality_summary_path=quality_summary_path,
        train_rows=train_rows,
        validation_rows=validation_rows,
    ))
    _write_json(copied_receipt_path, ingest_receipt)

    quality_started = time.perf_counter()
    quality_summary = _quality_summary(
        request=request,
        ingest_receipt=ingest_receipt,
        version_id=version_id,
        train_rows=train_rows,
        validation_rows=validation_rows,
        failed_count=len(failed_rows),
        latency_ms=(time.perf_counter() - quality_started) * 1000.0,
    )
    _write_json(quality_summary_path, quality_summary)

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    version = _dataset_version_payload(
        request=request,
        ingest_receipt=ingest_receipt,
        version_id=version_id,
        created_at=request.created_at or _utc_now(),
        version_dir=version_dir,
        dataset_version_path=dataset_version_path,
        manifest_path=manifest_path,
        samples_path=samples_path,
        valid_path=valid_path,
        failed_segments_path=failed_segments_path,
        quality_summary_path=quality_summary_path,
        train_rows=train_rows,
        validation_rows=validation_rows,
        failed_rows=failed_rows,
        successful_segments=successful_segments,
        metrics={
            "dataset_version_write_latency_ms": elapsed_ms,
            "quality_scoring_latency_ms": quality_summary["metrics"]["quality_scoring_latency_ms"],
            "generated_sample_count": len(sample_rows),
            "failed_sample_count": len(failed_rows),
        },
    )
    _write_json(dataset_version_path, version)
    return version


def _raise_if_ingest_receipt_blocked(ingest_receipt: dict[str, Any]) -> None:
    if str(ingest_receipt.get("status") or "") != "blocked":
        return
    failures = ingest_receipt.get("operator_failures")
    failure_codes = [
        code
        for failure in failures
        if isinstance(failure, dict) and (code := str(failure.get("code") or "").strip())
    ] if isinstance(failures, list) else []
    code_suffix = ",".join(failure_codes) if failure_codes else "unknown"
    raise ValueError(f"DATASET_VERSION_SOURCE_RECEIPT_BLOCKED: {code_suffix}")


def _partition_failed_segments(
    segments: list[dict[str, Any]],
    fail_segment_ids: tuple[str, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not fail_segment_ids:
        return segments, []
    failed_id_set = set(fail_segment_ids)
    successful_segments = [
        segment for segment in segments if segment.get("segment_id") not in failed_id_set
    ]
    failed_segments = [
        segment for segment in segments if segment.get("segment_id") in failed_id_set
    ]
    return successful_segments, failed_segments


def retry_failed_dataset_version(request: DatasetRetryFailedRequest) -> dict[str, Any]:
    started = time.perf_counter()
    base_version_path = Path(request.dataset_version_path).expanduser()
    base_version = _read_json(base_version_path)
    base_failed_path = Path(str(base_version.get("failed_segments_path", ""))).expanduser()
    if not base_failed_path.exists():
        raise ValueError(f"DATASET_VERSION_FAILED_SEGMENTS_MISSING: {base_failed_path}")
    failed_rows = _read_jsonl(base_failed_path)
    version_id = request.version_id or _default_version_id(str(base_version["dataset_id"]))
    version_dir = _dataset_version_dir(request.output_root, str(base_version["dataset_id"]), version_id)
    if version_dir.exists():
        raise ValueError(f"DATASET_VERSION_OUTPUT_EXISTS: {version_dir}")
    version_dir.mkdir(parents=True, exist_ok=False)

    base_train_rows = _read_jsonl(Path(str(base_version.get("samples_path", ""))).expanduser())
    base_validation_rows = _read_jsonl(Path(str(base_version.get("validation_samples_path", ""))).expanduser())
    retry_segments = [row["segment"] for row in failed_rows if isinstance(row.get("segment"), dict)]
    retry_rows = [
        _sample_row(
            segment,
            str(base_version.get("output_format", "prompt_completion")),
            request.generator_model or str(base_version.get("generator_model", "")),
        )
        for segment in retry_segments
    ]
    all_train_rows = [*base_train_rows, *base_validation_rows, *retry_rows]
    new_failed_rows: list[dict[str, Any]] = []

    samples_path = version_dir / "samples.jsonl"
    valid_path = version_dir / "valid.jsonl"
    failed_segments_path = version_dir / "failed-segments.jsonl"
    manifest_path = version_dir / "manifest.json"
    quality_summary_path = version_dir / "quality-summary.json"
    dataset_version_path = version_dir / "dataset-version.json"
    retry_receipt_path = version_dir / "dataset-retry-receipt.json"
    _write_jsonl(samples_path, all_train_rows)
    _write_jsonl(valid_path, [])
    _write_jsonl(failed_segments_path, new_failed_rows)

    ingest_receipt = _read_json(Path(str(base_version.get("source_receipt_path", ""))).expanduser())
    copied_receipt_path = version_dir / DATASET_INGEST_RECEIPT_FILENAME
    _write_json(copied_receipt_path, ingest_receipt)
    version_request = DatasetVersionRequest(
        workspace_manifest_path=request.workspace_manifest_path,
        ingest_receipt_path=Path(str(base_version.get("source_receipt_path", ""))).expanduser(),
        output_root=request.output_root,
        dataset_id=str(base_version["dataset_id"]),
        version_id=version_id,
        created_at=request.created_at,
        mode=str(base_version.get("mode", "chat")),
        generator_model=request.generator_model or str(base_version.get("generator_model", "")),
        output_kind=str(base_version.get("output_kind", "training")),
        output_format=str(base_version.get("output_format", "prompt_completion")),
        validation_ratio=0.0,
    )
    _write_json(manifest_path, _training_package_manifest(
        request=version_request,
        version_id=version_id,
        samples_path=samples_path,
        valid_path=valid_path,
        quality_summary_path=quality_summary_path,
        train_rows=all_train_rows,
        validation_rows=[],
    ))
    quality_started = time.perf_counter()
    quality_summary = _quality_summary(
        request=version_request,
        ingest_receipt=ingest_receipt,
        version_id=version_id,
        train_rows=all_train_rows,
        validation_rows=[],
        failed_count=0,
        latency_ms=(time.perf_counter() - quality_started) * 1000.0,
    )
    _write_json(quality_summary_path, quality_summary)
    retry_receipt = {
        "schema_version": DATASET_RETRY_RECEIPT_SCHEMA_VERSION,
        "base_version_id": base_version["version_id"],
        "retry_version_id": version_id,
        "input_failed_segment_count": len(failed_rows),
        "retry_success_count": len(retry_rows),
        "retry_failed_count": len(new_failed_rows),
        "reused_successful_sample_count": len(base_train_rows) + len(base_validation_rows),
        "rewritten_successful_sample_count": 0,
        "failed_retry_success_rate": len(retry_rows) / len(failed_rows) if failed_rows else 1.0,
        "dataset_version_path": str(dataset_version_path),
        "metrics": {
            "failed_retry_latency_ms": (time.perf_counter() - started) * 1000.0,
            "failed_retry_success_rate": len(retry_rows) / len(failed_rows) if failed_rows else 1.0,
        },
    }
    _write_json(retry_receipt_path, retry_receipt)
    version = _dataset_version_payload(
        request=version_request,
        ingest_receipt=ingest_receipt,
        version_id=version_id,
        created_at=request.created_at or _utc_now(),
        version_dir=version_dir,
        dataset_version_path=dataset_version_path,
        manifest_path=manifest_path,
        samples_path=samples_path,
        valid_path=valid_path,
        failed_segments_path=failed_segments_path,
        quality_summary_path=quality_summary_path,
        train_rows=all_train_rows,
        validation_rows=[],
        failed_rows=[],
        successful_segments=retry_segments,
        metrics={
            "dataset_version_write_latency_ms": retry_receipt["metrics"]["failed_retry_latency_ms"],
            "quality_scoring_latency_ms": quality_summary["metrics"]["quality_scoring_latency_ms"],
            "generated_sample_count": len(retry_rows),
            "failed_sample_count": 0,
            "failed_retry_success_rate": retry_receipt["failed_retry_success_rate"],
        },
    )
    version["successful_segment_ids"] = [
        *list(base_version.get("successful_segment_ids", [])),
        *[str(segment.get("segment_id", "")) for segment in retry_segments],
    ]
    _write_json(dataset_version_path, version)
    return retry_receipt


def list_dataset_versions(
    *,
    workspace_manifest_path: Path | str,
    output_root: Path | str,
    dataset_id: str,
) -> dict[str, Any]:
    perf_counter = time.perf_counter
    started = perf_counter()
    versions_root = Path(output_root).expanduser() / dataset_id / "versions"
    manifest_path_string = os.fspath(workspace_manifest_path)
    versions: list[dict[str, Any]] = []
    versions_append = versions.append
    read_json_file = _read_json_file
    for manifest_path in _iter_dataset_version_manifest_paths(versions_root):
        version = read_json_file(manifest_path)
        versions_append(
            {
                "dataset_id": version.get("dataset_id", ""),
                "version_id": version.get("version_id", ""),
                "created_at": version.get("created_at", ""),
                "status": version.get("status", ""),
                "train_count": version.get("train_count", 0),
                "validation_count": version.get("validation_count", 0),
                "failed_count": version.get("failed_count", 0),
                "quality_summary_path": version.get("quality_summary_path", ""),
                "dataset_version_path": manifest_path,
            }
        )
    as_str = str
    versions.sort(key=lambda item: (as_str(item["created_at"]), as_str(item["version_id"])))
    return {
        "schema_version": DATASET_VERSION_LIST_SCHEMA_VERSION,
        "workspace_manifest_path": manifest_path_string,
        "dataset_id": dataset_id,
        "versions": versions,
        "metrics": {
            "dataset_version_listing_latency_ms": (perf_counter() - started) * 1000.0,
            "dataset_version_count": len(versions),
        },
    }


def _iter_dataset_version_manifest_paths(versions_root: Path) -> Iterable[str]:
    is_file = os.path.isfile
    try:
        with os.scandir(versions_root) as entries:
            for entry in entries:
                if not entry.is_dir(follow_symlinks=False):
                    continue
                manifest_path = f"{entry.path}/dataset-version.json"
                if is_file(manifest_path):
                    yield manifest_path
    except OSError:
        return


def _iter_source_records(
    input_path: Path,
    operator_failures: list[dict[str, Any]],
) -> Iterable[dict[str, Any]]:
    paths = [input_path] if input_path.is_file() else _iter_source_file_paths(input_path)
    for path in paths:
        source_kind = _source_kind(path)
        if source_kind is None:
            operator_failures.append(
                {
                    "id": _failure_id("unsupported-source", path.name),
                    "code": "DATASET_INGEST_UNSUPPORTED_SOURCE",
                    "path": path.name,
                    "detail": "The source file extension is not supported for dataset ingest.",
                    "recovery_hint": "Convert the source to text, markdown, code, JSONL, JSON, CSV, TSV, PDF text, or DOCX text fixtures.",
                }
            )
            continue
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            operator_failures.append(
                {
                    "id": _failure_id("empty-source", path.name),
                    "code": "DATASET_INGEST_EMPTY_SOURCE",
                    "path": path.name,
                    "detail": "The source file contains no ingestable text.",
                    "recovery_hint": "Remove the empty file or add extracted text before preparing the dataset.",
                }
            )
            continue
        if source_kind == "structured_data":
            yield from _structured_records(path, text)
        else:
            yield _record(
                path=path,
                source_kind=source_kind,
                text=_normalize_line_endings(text),
                metadata=_metadata_for_path(path, source_kind),
            )


def _iter_source_file_paths(input_path: Path) -> list[Path]:
    file_paths: list[str] = []
    file_paths_append = file_paths.append
    stack = [os.fspath(input_path)]
    stack_append = stack.append
    stack_pop = stack.pop
    scandir = os.scandir
    path_cls = Path
    while stack:
        directory = stack_pop()
        try:
            with scandir(directory) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack_append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            file_paths_append(entry.path)
                    except OSError:
                        continue
        except OSError:
            continue
    file_paths.sort()
    return [path_cls(file_path) for file_path in file_paths]


def _classify_source_kind_name(name: str) -> str | None:
    if name[-4:] == ".txt":
        if len(name) >= 8 and name[-8] == "." and name[-7:-4].lower() == "pdf":
            return "pdf"
        if len(name) >= 9 and name[-9] == "." and name[-8:-4].lower() == "docx":
            return "docx"
        return "text"
    if name[-5:] == ".text":
        return "text"

    dot_index = name.rfind(".")
    if dot_index < 0:
        return None

    dotted_suffix = name[dot_index:].lower()
    if dotted_suffix == ".txt":
        lower_stem = name[:dot_index].lower()
        if lower_stem.endswith(".pdf"):
            return "pdf"
        if lower_stem.endswith(".docx"):
            return "docx"
        return "text"
    if dotted_suffix == ".text":
        return "text"

    if dotted_suffix in _TEXT_SOURCE_SUFFIXES:
        return "markdown"
    if dotted_suffix in _CODE_SOURCE_SUFFIXES:
        return "code"
    if dotted_suffix in _STRUCTURED_DATA_SOURCE_SUFFIXES:
        return "structured_data"
    return None


def _source_kind_for_name(name: str) -> str | None:
    try:
        cached = _SOURCE_KIND_BY_NAME[name]
        return cached
    except KeyError:
        pass
    source_kind = _classify_source_kind_name(name)
    if len(_SOURCE_KIND_BY_NAME) >= _SOURCE_KIND_NAME_CACHE_MAX:
        _SOURCE_KIND_BY_NAME.clear()
    _SOURCE_KIND_BY_NAME[name] = source_kind
    return source_kind


def _source_kind(path: Path) -> str | None:
    return _source_kind_for_name(path.name)


def _workspace_preflight_failures(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for check in receipt.get("checks", []):
        if not isinstance(check, dict) or check.get("status") != "blocked":
            continue
        code = str(check.get("code") or "WORKSPACE_PREFLIGHT_BLOCKED")
        failures.append(
            {
                "id": f"workspace-preflight-{_safe_component(code.lower())}",
                "code": code,
                "path": str(receipt.get("manifest_path") or ""),
                "detail": str(check.get("detail") or "Workspace preflight blocked dataset ingest."),
                "recovery_hint": str(check.get("recovery_hint") or "Resolve workspace preflight blockers before dataset ingest."),
                "items": check.get("items", []),
            }
        )
    if failures:
        return failures
    return [
        {
            "id": "workspace-preflight-blocked",
            "code": "WORKSPACE_PREFLIGHT_BLOCKED",
            "path": str(receipt.get("manifest_path") or ""),
            "detail": "Workspace preflight blocked dataset ingest.",
            "recovery_hint": "Resolve workspace preflight blockers before dataset ingest.",
            "items": [],
        }
    ]


def _cleaning_controls(request: DatasetIngestRequest) -> dict[str, Any]:
    return {
        "pii_mask": {
            "enabled": request.pii_mask,
            "policy_id": "melix.pii_mask.local.v1",
        },
        "exact_dedup": {
            "enabled": request.exact_dedup,
            "policy_id": "melix.exact_dedup.sha256.v1",
        },
        "fuzzy_dedup": {
            "enabled": request.fuzzy_dedup,
            "policy_id": "melix.fuzzy_dedup.tokens.v1",
        },
    }


def _segmentation_policy(request: DatasetIngestRequest) -> dict[str, Any]:
    return {
        "enabled": request.segmentation,
        "strategy": request.segmentation_strategy,
        "policy_id": f"melix.segmentation.{request.segmentation_strategy}.v1",
    }


def _structured_records(path: Path, text: str) -> Iterable[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        for index, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            yield _record(
                path=path,
                source_kind="structured_data",
                text=_structured_text(payload),
                metadata={"row_index": index},
            )
        return
    if suffix == ".json":
        payload = json.loads(text)
        rows = payload if isinstance(payload, list) else [payload]
        for index, row in enumerate(rows, start=1):
            yield _record(
                path=path,
                source_kind="structured_data",
                text=_structured_text(row),
                metadata={"row_index": index},
            )
        return
    dialect = "excel-tab" if suffix == ".tsv" else "excel"
    reader = csv.DictReader(text.splitlines(), dialect=dialect)
    for index, row in enumerate(reader, start=1):
        yield _record(
            path=path,
            source_kind="structured_data",
            text=_structured_text(row),
            metadata={"row_index": index},
        )


def _structured_text(payload: Any) -> str:
    if isinstance(payload, dict):
        if "text" in payload:
            return str(payload["text"])
        return " ".join(f"{key}: {value}" for key, value in sorted(payload.items()))
    return str(payload)


def _record(path: Path, source_kind: str, text: str, metadata: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_line_endings(text)
    metadata = dict(metadata)
    return {
        "source_id": hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16],
        "source_uri": path.name,
        "source_kind": source_kind,
        "content_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        "byte_size": len(normalized.encode("utf-8")),
        "record_count": 1,
        "text": normalized,
        "metadata": metadata,
    }


def _failure_id(reason: str, name: str) -> str:
    normalized_name = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower() or "source"
    return f"dataset-ingest-{reason}-{normalized_name}"


def _metadata_for_path(path: Path, source_kind: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if source_kind == "code":
        metadata["language"] = _language_for_suffix(path.suffix.lower())
    return metadata


def _language_for_suffix(suffix: str) -> str:
    return {
        ".py": "python",
        ".swift": "swift",
        ".js": "javascript",
        ".ts": "typescript",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".cpp": "cpp",
        ".c": "c",
        ".h": "c",
    }.get(suffix, suffix.lstrip(".") or "text")


def _source_inventory(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_uri: dict[str, dict[str, Any]] = {}
    for record in records:
        item = by_uri.setdefault(
            record["source_uri"],
            {
                "source_id": record["source_id"],
                "source_uri": record["source_uri"],
                "source_kind": record["source_kind"],
                "content_sha256": record["content_sha256"],
                "byte_size": 0,
                "record_count": 0,
                "metadata": {},
            },
        )
        item["byte_size"] += record["byte_size"]
        item["record_count"] += 1
        item["metadata"].update(record.get("metadata", {}))
    return [by_uri[key] for key in sorted(by_uri)]


def _mask_pii(text: str) -> tuple[str, int]:
    count = 0

    def replace_email(_: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return "[EMAIL]"

    def replace_phone(_: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return "[PHONE]"

    def replace_token(_: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return "[TOKEN]"

    text = _EMAIL_RE.sub(replace_email, text)
    text = _PHONE_RE.sub(replace_phone, text)
    text = _TOKEN_RE.sub(replace_token, text)
    return text, count


def _normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _normalize_text(text: str) -> str:
    return "\n".join(line.strip() for line in _normalize_line_endings(text).splitlines()).strip()


def _fuzzy_key(text: str) -> str:
    return " ".join(_WORD_RE.findall(text.lower()))


def _segment_records(records: list[dict[str, Any]], request: DatasetIngestRequest) -> Iterable[dict[str, Any]]:
    for record in records:
        chunks = [_normalize_text(record["text"])]
        if request.segmentation and request.segmentation_strategy == "paragraph":
            chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", record["text"]) if chunk.strip()]
        for index, chunk in enumerate(chunks, start=1):
            yield {
                "segment_id": f"{record['source_id']}-{index}",
                "source_id": record["source_id"],
                "source_uri": record["source_uri"],
                "source_kind": record["source_kind"],
                "text": chunk,
                "metadata": {
                    **record.get("metadata", {}),
                    "segmentation_strategy": request.segmentation_strategy if request.segmentation else "none",
                    "segment_index": index,
                },
            }


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_bytes())


def _read_json_file(path: str) -> dict[str, Any]:
    with open(path, "rb") as handle:
        return json.loads(handle.read())


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _dataset_version_dir(output_root: Path | str, dataset_id: str, version_id: str) -> Path:
    return Path(output_root).expanduser() / _safe_component(dataset_id) / "versions" / _safe_component(version_id)


def _safe_component(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    if not normalized:
        raise ValueError("DATASET_VERSION_MANIFEST_INVALID: path component is empty")
    return normalized


def _default_version_id(dataset_id: str) -> str:
    return f"{_safe_component(dataset_id)}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sample_row(segment: dict[str, Any], output_format: str, generator_model: str) -> dict[str, Any]:
    text = _normalize_text(str(segment.get("text", "")))
    segment_id = str(segment.get("segment_id", ""))
    row = {
        "sample_id": f"sample-{segment_id}",
        "source_segment_id": segment_id,
        "source_id": str(segment.get("source_id", "")),
        "source_uri": str(segment.get("source_uri", "")),
        "generator_model": generator_model,
        "metadata": {
            "source_kind": str(segment.get("source_kind", "")),
            "generation_policy_id": "melix.dataset_version.local.v1",
        },
    }
    if output_format == "chat_messages":
        row["messages"] = [
            {"role": "user", "content": f"Create a training answer from segment {segment_id}."},
            {"role": "assistant", "content": text},
        ]
    else:
        row["prompt"] = f"Create a training answer from segment {segment_id}."
        row["completion"] = text
    return row


def _failed_segment_row(segment: dict[str, Any]) -> dict[str, Any]:
    segment_id = str(segment.get("segment_id", ""))
    return {
        "id": f"dataset-version-generation-failed-{_safe_component(segment_id)}",
        "code": "DATASET_VERSION_GENERATION_FAILED",
        "segment_id": segment_id,
        "detail": "The segment was selected for deterministic failed-generation retry coverage.",
        "recovery_hint": "Run melix dataset prepare retry-failed to regenerate only failed segments.",
        "segment": segment,
    }


def _split_dataset_version_validation(
    rows: list[dict[str, Any]],
    validation_ratio: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if validation_ratio <= 0 or len(rows) < 2:
        return list(rows), []
    validation_count = int(round(len(rows) * validation_ratio))
    validation_count = min(max(validation_count, 1), len(rows) - 1)
    validation_segment_ids = {
        row["source_segment_id"]
        for row in sorted(rows, key=lambda item: hashlib.sha256(str(item["source_segment_id"]).encode("utf-8")).hexdigest())[:validation_count]
    }
    train_rows: list[dict[str, Any]] = []
    validation_rows: list[dict[str, Any]] = []
    for row in rows:
        if row["source_segment_id"] in validation_segment_ids:
            validation_rows.append(row)
        else:
            train_rows.append(row)
    return train_rows, validation_rows


def _training_package_manifest(
    *,
    request: DatasetVersionRequest,
    version_id: str,
    samples_path: Path,
    valid_path: Path,
    quality_summary_path: Path,
    train_rows: list[dict[str, Any]],
    validation_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "melix.training_dataset_package.v1",
        "dataset_id": request.dataset_id,
        "format": request.output_format,
        "sample_count": len(train_rows),
        "validation_sample_count": len(validation_rows),
        "version": version_id,
        "build_ready": True,
        "preview_only": False,
        "validation_strategy": "deterministic_hash_ratio" if validation_rows else "none",
        "validation_ratio": request.validation_ratio,
        "response_only_supported": request.output_format in {"chat_messages", "prompt_completion"},
        "samples_path": str(samples_path),
        "validation_samples_path": str(valid_path),
        "quality_summary_path": str(quality_summary_path),
    }


def _quality_summary(
    *,
    request: DatasetVersionRequest,
    ingest_receipt: dict[str, Any],
    version_id: str,
    train_rows: list[dict[str, Any]],
    validation_rows: list[dict[str, Any]],
    failed_count: int,
    latency_ms: float,
) -> dict[str, Any]:
    train_count = len(train_rows)
    validation_count = len(validation_rows)
    success_count = train_count + validation_count
    total_count = success_count + failed_count
    success_rate = success_count / total_count if total_count else 0.0
    score = round(success_rate, 6)
    output_length_count, output_length_total, p95_output_length = _sample_output_length_stats(
        train_rows,
        validation_rows,
    )
    quality_controls = ingest_receipt.get("quality_control_summary", {})
    source_record_count = float(quality_controls.get("source_record_count", 0) or 0)
    exact_dedup_count = float(quality_controls.get("exact_dedup_count", 0) or 0)
    fuzzy_dedup_count = float(quality_controls.get("fuzzy_dedup_count", 0) or 0)
    blocking_reasons = ["failed_generation"] if failed_count else []
    return {
        "schema_version": DATASET_QUALITY_SUMMARY_SCHEMA_VERSION,
        "dataset_id": request.dataset_id,
        "version_id": version_id,
        "score": score,
        "grade": _quality_grade(score),
        "success_rate": success_rate,
        "failed_count": failed_count,
        "train_count": train_count,
        "validation_count": validation_count,
        "pii_mask_count": int(quality_controls.get("pii_mask_count", 0) or 0),
        "dedup_ratio": (exact_dedup_count + fuzzy_dedup_count) / source_record_count if source_record_count else 0,
        "mean_output_length": output_length_total / output_length_count if output_length_count else 0,
        "p95_output_length": p95_output_length,
        "policy_id": "melix.dataset_quality.local.v1",
        "review_notes": [],
        "blocking_reasons": blocking_reasons,
        "metrics": {
            "quality_scoring_latency_ms": latency_ms,
            "generated_sample_count": success_count,
            "failed_sample_count": failed_count,
        },
    }


def _quality_grade(score: float) -> str:
    if score >= 0.95:
        return "A"
    if score >= 0.85:
        return "B"
    if score >= 0.60:
        return "C"
    if score > 0:
        return "D"
    return "F"


def _sample_output_lengths(
    train_rows: list[dict[str, Any]],
    validation_rows: list[dict[str, Any]],
) -> list[int]:
    lengths: list[int] = []
    _append_sample_output_lengths(lengths, train_rows, validation_rows)
    return lengths


def _sample_output_length_stats(
    train_rows: list[dict[str, Any]],
    validation_rows: list[dict[str, Any]],
) -> tuple[int, int, int]:
    lengths: list[int] = []
    _append_sample_output_lengths(lengths, train_rows, validation_rows)
    length_count = len(lengths)
    if not length_count:
        return 0, 0, 0
    output_length_total = sum(lengths)
    lengths.sort()
    index = min(length_count - 1, int(round((length_count - 1) * 0.95)))
    return length_count, output_length_total, lengths[index]


def _append_sample_output_lengths(
    lengths: list[int],
    train_rows: list[dict[str, Any]],
    validation_rows: list[dict[str, Any]],
) -> None:
    append = lengths.append
    str_ = str
    for row in train_rows:
        if "completion" in row:
            append(len(str_(row["completion"])))
            continue
        messages = row.get("messages", [])
        if not isinstance(messages, list):
            append(0)
            continue
        total = 0
        for item in messages:
            try:
                content = item.get("content", "")
            except AttributeError:
                continue
            total += len(str_(content))
        append(total)
    for row in validation_rows:
        if "completion" in row:
            append(len(str_(row["completion"])))
            continue
        messages = row.get("messages", [])
        if not isinstance(messages, list):
            append(0)
            continue
        total = 0
        for item in messages:
            try:
                content = item.get("content", "")
            except AttributeError:
                continue
            total += len(str_(content))
        append(total)


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95)))
    return ordered[index]


def _dataset_version_payload(
    *,
    request: DatasetVersionRequest,
    ingest_receipt: dict[str, Any],
    version_id: str,
    created_at: str,
    version_dir: Path,
    dataset_version_path: Path,
    manifest_path: Path,
    samples_path: Path,
    valid_path: Path,
    failed_segments_path: Path,
    quality_summary_path: Path,
    train_rows: list[dict[str, Any]],
    validation_rows: list[dict[str, Any]],
    failed_rows: list[dict[str, Any]],
    successful_segments: list[dict[str, Any]],
    metrics: dict[str, float | int],
) -> dict[str, Any]:
    quality_controls = ingest_receipt.get("quality_control_summary", {})
    return {
        "schema_version": DATASET_VERSION_SCHEMA_VERSION,
        "status": "ready",
        "dataset_id": request.dataset_id,
        "version_id": version_id,
        "created_at": created_at,
        "workspace_project_id": str(ingest_receipt.get("workspace_project_id", "")),
        "workspace_manifest_path": str(Path(request.workspace_manifest_path)),
        "source_receipt_path": str(Path(request.ingest_receipt_path)),
        "source_file_count": int(quality_controls.get("source_file_count", 0) or 0),
        "source_inventory": list(ingest_receipt.get("source_inventory", [])),
        "source_record_count": int(quality_controls.get("source_record_count", 0) or 0),
        "segment_count": int(quality_controls.get("segment_count", len(successful_segments) + len(failed_rows)) or 0),
        "mode": request.mode,
        "generator_model": request.generator_model,
        "output_kind": request.output_kind,
        "output_format": request.output_format,
        "train_count": len(train_rows),
        "validation_count": len(validation_rows),
        "failed_count": len(failed_rows),
        "successful_segment_ids": [str(segment.get("segment_id", "")) for segment in successful_segments],
        "failed_segment_ids": [str(row.get("segment_id", "")) for row in failed_rows],
        "version_root_path": str(version_dir),
        "dataset_version_path": str(dataset_version_path),
        "quality_summary_path": str(quality_summary_path),
        "package_manifest_path": str(manifest_path),
        "samples_path": str(samples_path),
        "validation_samples_path": str(valid_path),
        "failed_segments_path": str(failed_segments_path),
        "metrics": metrics,
    }
