from __future__ import annotations

from dataclasses import dataclass
import csv
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Iterable


DATASET_INGEST_RECEIPT_SCHEMA_VERSION = "melix.dataset_ingest_receipt.v1"
DATASET_INGEST_RECEIPT_FILENAME = "dataset-ingest-receipt.json"
DATASET_INGEST_SEGMENTS_FILENAME = "segments.jsonl"

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")
_TOKEN_RE = re.compile(r"\b(?:sk|pk|rk|ghp|github_pat)-[A-Za-z0-9._-]{8,}\b")
_WORD_RE = re.compile(r"[A-Za-z0-9]+")


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


def prepare_dataset_ingest(request: DatasetIngestRequest) -> dict[str, Any]:
    started = time.perf_counter()
    segmentation_started = time.perf_counter()
    input_path = Path(request.input_path).expanduser().resolve()
    output_dir = Path(request.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    segments_path = output_dir / DATASET_INGEST_SEGMENTS_FILENAME
    receipt_path = output_dir / DATASET_INGEST_RECEIPT_FILENAME

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
    }
    receipt = {
        "schema_version": DATASET_INGEST_RECEIPT_SCHEMA_VERSION,
        "status": "blocked" if operator_failures else "ready",
        "workspace_project_id": request.workspace_project_id,
        "workspace_manifest_path": str(Path(request.workspace_manifest_path)),
        "dataset_preparation_id": request.dataset_preparation_id,
        "source_inventory": source_inventory,
        "cleaning_controls": {
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
        },
        "segmentation_policy": {
            "enabled": request.segmentation,
            "strategy": request.segmentation_strategy,
            "policy_id": f"melix.segmentation.{request.segmentation_strategy}.v1",
        },
        "segment_artifacts": {
            "segments_path": str(segments_path),
            "receipt_path": str(receipt_path),
        },
        "quality_control_summary": summary,
        "operator_failures": operator_failures,
        "metrics": metrics,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def _iter_source_records(
    input_path: Path,
    operator_failures: list[dict[str, Any]],
) -> Iterable[dict[str, Any]]:
    paths = [input_path] if input_path.is_file() else sorted(path for path in input_path.rglob("*") if path.is_file())
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


def _source_kind(path: Path) -> str | None:
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if suffixes[-2:] == [".pdf", ".txt"]:
        return "pdf"
    if suffixes[-2:] == [".docx", ".txt"]:
        return "docx"
    suffix = suffixes[-1] if suffixes else ""
    if suffix in {".txt", ".text"}:
        return "text"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in {".py", ".swift", ".js", ".ts", ".java", ".go", ".rs", ".cpp", ".c", ".h"}:
        return "code"
    if suffix in {".jsonl", ".json", ".csv", ".tsv"}:
        return "structured_data"
    return None


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
