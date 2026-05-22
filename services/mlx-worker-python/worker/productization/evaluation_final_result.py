from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from collections.abc import Collection, Iterable, Iterator
from functools import lru_cache
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from worker.dataset_registry.catalog import (
    DatasetSnapshot,
    read_hf_dataset_snapshot_rows,
    resolve_cached_hf_dataset_snapshot,
)
from worker.model_ops.errors import ModelOperationError

_DEFAULT_IGNORED_PATHS = {
    "evidence",
    "confidence",
    "closeness_logits",
    "closeness_probs",
}
_JSON_FENCE_PATTERN = re.compile(r"```json\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_GENERIC_FENCE_PATTERN = re.compile(r"```(?:[a-zA-Z0-9_-]+)?\s*(.*?)```", re.DOTALL)
_TEXT_ANSWER_PATTERN = re.compile(
    r"(?im)^\s*(?:final\s+answer|answer)\s*[:\-]?\s*(.+?)\s*$"
)
_HF_DATASETS_SERVER_URL = "https://datasets-server.huggingface.co"
HFEvaluationDatasetFetcher = Callable[[str, dict[str, str]], dict[str, Any]]


@dataclass(frozen=True)
class EvaluationProfileDefinition:
    profile_type: str
    result_kind: str
    extraction_mode: str
    scoring_mode: str
    threshold: float
    output_schema: dict[str, Any] | None = None
    ignored_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvaluationFieldMapping:
    system_path: str = ""
    input_text_path: str = ""
    target_path: str = ""
    sample_id_path: str = ""


@dataclass(frozen=True)
class EvaluationMaterializationRequest:
    source_kind: str
    source_path: Path
    profile: EvaluationProfileDefinition
    field_mapping: EvaluationFieldMapping
    dataset_id: str = ""
    suite_id: str = ""


@dataclass(frozen=True)
class MaterializedEvaluationDataset:
    package_path: Path
    cache_key: str
    cache_hit: bool


@dataclass(frozen=True)
class HFEvaluationDatasetSource:
    dataset_path: str
    dataset_name: str = ""
    dataset_revision: str = "main"
    split: str = "train"


@dataclass(frozen=True)
class ExtractionOutcome:
    extracted_result: str
    extraction_status: str
    failure_reason: str = ""


@dataclass(frozen=True)
class ScoringOutcome:
    typed_score: float
    validation_status: str
    failure_reason: str = ""


def extract_final_result(
    *,
    raw_response: str,
    result_kind: str,
    extraction_mode: str,
) -> ExtractionOutcome:
    normalized = raw_response.strip()
    if not normalized:
        return ExtractionOutcome("", "empty_response", "empty_response")

    if extraction_mode == "strict_full_response":
        return ExtractionOutcome(normalized, "extracted")

    if extraction_mode != "heuristic_final":
        return ExtractionOutcome("", "unsupported_extraction_mode", "unsupported_extraction_mode")

    if result_kind == "json":
        return _extract_json_heuristic(normalized)
    if result_kind == "text":
        return _extract_text_heuristic(normalized)
    return ExtractionOutcome("", "unsupported_result_kind", "unsupported_result_kind")


def score_final_result(
    *,
    extracted_result: str,
    target: str,
    profile: EvaluationProfileDefinition,
) -> ScoringOutcome:
    if profile.result_kind == "json":
        return _score_json_result(
            extracted_result=extracted_result,
            target=target,
            profile=profile,
        )
    if profile.result_kind == "text":
        return _score_text_result(
            extracted_result=extracted_result,
            target=target,
            profile=profile,
        )
    return ScoringOutcome(typed_score=0.0, validation_status="unsupported_result_kind", failure_reason="unsupported_result_kind")


def materialize_local_evaluation_dataset(
    *,
    request: EvaluationMaterializationRequest,
    cache_root: Path,
) -> MaterializedEvaluationDataset:
    resolved_source_path = request.source_path.expanduser().resolve()
    _validate_local_source_kind(request.source_kind)
    source_metadata = _local_source_metadata(
        source_kind=request.source_kind,
        source_path=resolved_source_path,
    )
    dataset_id = request.dataset_id or f"{resolved_source_path.stem}.dev.v1"
    suite_id = request.suite_id or resolved_source_path.stem
    cache_hit = _materialized_cache_hit(
        cache_root=cache_root,
        source_metadata=source_metadata,
        profile=request.profile,
        field_mapping=request.field_mapping,
        dataset_id=dataset_id,
        suite_id=suite_id,
    )
    if cache_hit is not None:
        return cache_hit

    rows = _read_local_rows(request.source_kind, resolved_source_path)
    return _materialize_evaluation_rows(
        rows=rows,
        profile=request.profile,
        field_mapping=request.field_mapping,
        dataset_id=dataset_id,
        suite_id=suite_id,
        cache_root=cache_root,
        source_metadata=source_metadata,
    )


def materialize_hf_evaluation_dataset(
    *,
    source: HFEvaluationDatasetSource,
    profile: EvaluationProfileDefinition,
    field_mapping: EvaluationFieldMapping,
    dataset_id: str,
    suite_id: str,
    cache_root: Path,
    fetch_json: HFEvaluationDatasetFetcher | None = None,
) -> MaterializedEvaluationDataset:
    local_snapshot = resolve_cached_hf_dataset_snapshot(
        repo_id=source.dataset_path,
        revision=source.dataset_revision or "main",
    )
    if local_snapshot is not None:
        rows = read_hf_dataset_snapshot_rows(
            local_snapshot.snapshot_path,
            split=source.split or "train",
        )
        if rows:
            resolved_name = source.dataset_name or (local_snapshot.configs[0] if local_snapshot.configs else "default")
            source_slug = _hf_source_slug(source.dataset_path)
            resolved_source = HFEvaluationDatasetSource(
                dataset_path=source.dataset_path,
                dataset_name=resolved_name,
                dataset_revision=source.dataset_revision or local_snapshot.revision,
                split=source.split or "train",
            )
            return _materialize_evaluation_rows(
                rows=rows,
                profile=profile,
                field_mapping=field_mapping,
                dataset_id=dataset_id or f"{source_slug}.dev.v1",
                suite_id=suite_id or source_slug,
                cache_root=cache_root,
                source_metadata=_hf_cache_source_metadata(
                    source=resolved_source,
                    snapshot=local_snapshot,
                    rows=rows,
                ),
            )

    fetcher = fetch_json or _fetch_hf_dataset_server_json
    resolved_name = source.dataset_name or _resolve_hf_dataset_name(source, fetcher)
    rows = _fetch_hf_dataset_rows(
        HFEvaluationDatasetSource(
            dataset_path=source.dataset_path,
            dataset_name=resolved_name,
            dataset_revision=source.dataset_revision or "main",
            split=source.split or "train",
        ),
        fetcher,
    )
    source_slug = _hf_source_slug(source.dataset_path)
    return _materialize_evaluation_rows(
        rows=rows,
        profile=profile,
        field_mapping=field_mapping,
        dataset_id=dataset_id or f"{source_slug}.dev.v1",
        suite_id=suite_id or source_slug,
        cache_root=cache_root,
        source_metadata=_hf_source_metadata(
            source=HFEvaluationDatasetSource(
                dataset_path=source.dataset_path,
                dataset_name=resolved_name,
                dataset_revision=source.dataset_revision or "main",
                split=source.split or "train",
            ),
            rows=rows,
        ),
    )


def _extract_json_heuristic(raw_response: str) -> ExtractionOutcome:
    candidate = _last_stripped_pattern_match(_JSON_FENCE_PATTERN, raw_response)
    if candidate and _parses_json(candidate):
        return ExtractionOutcome(candidate, "extracted")

    valid_generic_count = 0
    valid_generic_candidate = ""
    for match in _GENERIC_FENCE_PATTERN.finditer(raw_response):
        candidate = match.group(1).strip()
        if not candidate or not _parses_json(candidate):
            continue
        valid_generic_count += 1
        if valid_generic_count > 1:
            return ExtractionOutcome("", "ambiguous_extraction", "multiple_generic_json_candidates")
        valid_generic_candidate = candidate
    if valid_generic_candidate:
        return ExtractionOutcome(valid_generic_candidate, "extracted")

    suffix = _last_balanced_json_suffix(raw_response)
    if suffix:
        return ExtractionOutcome(suffix, "extracted")
    return ExtractionOutcome("", "extraction_failed", "no_json_candidate")


def _extract_text_heuristic(raw_response: str) -> ExtractionOutcome:
    answer_prefix_count = 0
    answer_prefix_candidate = ""
    for match in _TEXT_ANSWER_PATTERN.finditer(raw_response):
        candidate = match.group(1).strip()
        if not candidate:
            continue
        answer_prefix_count += 1
        if answer_prefix_count > 1:
            return ExtractionOutcome("", "ambiguous_extraction", "multiple_answer_prefix_candidates")
        answer_prefix_candidate = candidate
    if answer_prefix_candidate:
        return ExtractionOutcome(answer_prefix_candidate, "extracted")

    if "```" in raw_response:
        candidate = _last_stripped_pattern_match(_GENERIC_FENCE_PATTERN, raw_response)
        if candidate:
            return ExtractionOutcome(candidate, "extracted")

    fallback_line = _last_nonblank_text_line(raw_response)
    if fallback_line:
        return ExtractionOutcome(fallback_line, "extracted")

    return ExtractionOutcome("", "extraction_failed", "no_text_candidate")


def _last_nonblank_text_line(raw_response: str) -> str:
    end = len(raw_response)
    while end > 0 and raw_response[end - 1].isspace():
        end -= 1
    if end == 0:
        return ""
    line_start = raw_response.rfind("\n", 0, end) + 1
    return raw_response[line_start:end].strip()


def _score_json_result(
    *,
    extracted_result: str,
    target: str,
    profile: EvaluationProfileDefinition,
) -> ScoringOutcome:
    parsed_target = _loads_json_payload(target)
    try:
        parsed_result = _loads_json_payload(extracted_result)
    except json.JSONDecodeError:
        return ScoringOutcome(typed_score=0.0, validation_status="parse_failed", failure_reason="invalid_json")

    validation_error = _validate_json_schema(profile.output_schema or {}, parsed_result)
    if validation_error:
        return ScoringOutcome(typed_score=0.0, validation_status="schema_failed", failure_reason=validation_error)

    score = _json_typed_score(
        expected=parsed_target,
        actual=parsed_result,
        ignored_paths=_ignored_paths_for_profile(profile.ignored_paths),
    )
    return ScoringOutcome(typed_score=round(score, 4), validation_status="validated")


@lru_cache(maxsize=128)
def _loads_json_payload(payload: str) -> Any:
    return json.loads(payload)


@lru_cache(maxsize=128)
def _ignored_paths_for_profile(profile_ignored_paths: tuple[str, ...]) -> frozenset[str]:
    return _DEFAULT_IGNORED_PATHS | frozenset(profile_ignored_paths)


def _score_text_result(
    *,
    extracted_result: str,
    target: str,
    profile: EvaluationProfileDefinition,
) -> ScoringOutcome:
    normalized_actual = _normalize_text(extracted_result)
    normalized_target = _normalize_text(target)
    if profile.scoring_mode == "normalized_exact_match":
        score = 1.0 if normalized_actual == normalized_target else 0.0
    elif profile.scoring_mode == "label_match":
        score = 1.0 if normalized_actual.casefold() == normalized_target.casefold() else 0.0
    elif profile.scoring_mode == "regex_match":
        score = 1.0 if re.fullmatch(target, extracted_result.strip()) else 0.0
    else:
        return ScoringOutcome(typed_score=0.0, validation_status="unsupported_scoring_mode", failure_reason="unsupported_scoring_mode")
    return ScoringOutcome(typed_score=score, validation_status="validated")


def _validate_json_schema(schema: dict[str, Any], payload: Any) -> str:
    return _validate_json_schema_at(schema, payload, path="$")


def _validate_json_schema_at(schema: dict[str, Any], payload: Any, *, path: str) -> str:
    expected_types = _schema_types(schema.get("type"))
    if expected_types and not any(_matches_json_type(payload, expected_type) for expected_type in expected_types):
        return "root_type_mismatch" if path == "$" else f"type_mismatch:{path}"

    if isinstance(payload, dict) and (
        "object" in expected_types or "properties" in schema or "required" in schema
    ):
        required = schema.get("required", [])
        if isinstance(required, list):
            for key in required:
                key_text = str(key)
                if key_text not in payload:
                    return f"missing_required:{_json_schema_child_path(path, key_text)}"
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, value in properties.items():
                if key not in payload or not isinstance(value, dict):
                    continue
                validation_error = _validate_json_schema_at(
                    value,
                    payload[key],
                    path=_json_schema_child_path(path, str(key)),
                )
                if validation_error:
                    return validation_error
        pattern_properties = schema.get("patternProperties", {})
        if isinstance(pattern_properties, dict):
            for key, value in payload.items():
                key_text = str(key)
                for pattern_schema in _json_schema_pattern_schemas(pattern_properties, key_text):
                    if not isinstance(pattern_schema, dict):
                        continue
                    validation_error = _validate_json_schema_at(
                        pattern_schema,
                        value,
                        path=_json_schema_child_path(path, key_text),
                    )
                    if validation_error:
                        return validation_error
        if schema.get("additionalProperties") is False and isinstance(properties, dict):
            allowed = {str(key) for key in properties.keys()}
            for key in payload.keys():
                key_text = str(key)
                if key_text not in allowed and not _matches_json_schema_pattern(pattern_properties, key_text):
                    return f"unexpected_property:{_json_schema_child_path(path, key_text)}"
        return ""

    if isinstance(payload, list) and ("array" in expected_types or "items" in schema):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(payload):
                validation_error = _validate_json_schema_at(
                    item_schema,
                    item,
                    path=f"{path}[{index}]",
                )
                if validation_error:
                    return validation_error
        return ""

    return ""


def _schema_types(raw_type: Any) -> tuple[str, ...]:
    if isinstance(raw_type, str):
        return (raw_type,)
    if isinstance(raw_type, list):
        return tuple(str(value) for value in raw_type if isinstance(value, str) and value)
    return ()


def _json_schema_child_path(path: str, key: str) -> str:
    if path == "$":
        return f"$.{key}"
    return f"{path}.{key}"


def _json_schema_pattern_schemas(pattern_properties: dict[Any, Any], key: str) -> list[Any]:
    matched: list[Any] = []
    for pattern, pattern_schema in pattern_properties.items():
        if not isinstance(pattern, str):
            continue
        try:
            if re.search(pattern, key):
                matched.append(pattern_schema)
        except re.error:
            continue
    return matched


def _matches_json_schema_pattern(pattern_properties: Any, key: str) -> bool:
    return isinstance(pattern_properties, dict) and bool(_json_schema_pattern_schemas(pattern_properties, key))


def _json_typed_score(*, expected: Any, actual: Any, ignored_paths: Collection[str], path: str = "") -> float:
    if isinstance(expected, dict):
        total = 0.0
        count = 0
        actual_dict = actual if isinstance(actual, dict) else None
        for key, expected_value in expected.items():
            child_path = _joined_path(path, key)
            if child_path in ignored_paths:
                continue
            total += _json_typed_score(
                expected=expected_value,
                actual=actual_dict.get(key) if actual_dict is not None else None,
                ignored_paths=ignored_paths,
                path=child_path,
            )
            count += 1
        if count == 0:
            return 1.0
        return total / count
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            return 0.0
        if not expected:
            return 1.0
        total = 0.0
        for index, item in enumerate(expected):
            total += _json_typed_score(
                expected=item,
                actual=actual[index],
                ignored_paths=ignored_paths,
                path=f"{path}[{index}]",
            )
        return total / len(expected)
    return 1.0 if expected == actual else 0.0


def _joined_path(prefix: str, key: str) -> str:
    if not prefix:
        return key
    return f"{prefix}.{key}"


def _local_source_metadata(*, source_kind: str, source_path: Path) -> dict[str, Any]:
    resolved = Path(source_path).expanduser().resolve()
    return {
        "source_kind": source_kind,
        "source_path": str(resolved),
        "source_sha256": _sha256_for_path(resolved),
        "source_size_bytes": resolved.stat().st_size,
    }


def _hf_source_metadata(*, source: HFEvaluationDatasetSource, rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows_payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {
        "source_kind": "hf_dataset",
        "hf_dataset_path": source.dataset_path,
        "hf_dataset_name": source.dataset_name,
        "hf_dataset_revision": source.dataset_revision,
        "hf_split": source.split,
        "dataset_uri": _hf_dataset_uri(
            dataset_path=source.dataset_path,
            dataset_name=source.dataset_name,
            dataset_revision=source.dataset_revision,
            split=source.split,
        ),
        "hf_rows_sha256": hashlib.sha256(rows_payload.encode("utf-8")).hexdigest(),
    }


def _hf_cache_source_metadata(
    *,
    source: HFEvaluationDatasetSource,
    snapshot: DatasetSnapshot,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    metadata = _hf_source_metadata(source=source, rows=rows)
    metadata.update(
        {
            "source_kind": "hf_cache_snapshot",
            "hf_snapshot_id": snapshot.snapshot_id,
            "hf_snapshot_path": str(snapshot.snapshot_path),
            "hf_cache_repo_path": str(snapshot.cache_repo_path),
        }
    )
    return metadata


def _sha256_for_path(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_local_source_kind(source_kind: str) -> None:
    if source_kind not in {"jsonl", "csv"}:
        raise ModelOperationError(
            code="invalid_evaluation_source",
            message=f"Unsupported local evaluation source kind: {source_kind}",
        )


def _read_local_rows(source_kind: str, source_path: Path) -> list[dict[str, Any]]:
    _validate_local_source_kind(source_kind)
    resolved = Path(source_path).expanduser().resolve()
    if source_kind == "jsonl":
        rows: list[dict[str, Any]] = []
        with resolved.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                if raw_line.strip():
                    payload = json.loads(raw_line)
                    if not isinstance(payload, dict):
                        raise ModelOperationError(
                            code="invalid_evaluation_source",
                            message="JSONL evaluation rows must be JSON objects.",
                        )
                    rows.append(payload)
        return rows
    with resolved.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _required_string_field(row: dict[str, Any], path: str, field_name: str) -> str:
    value = _required_value(row, path, field_name)
    if not isinstance(value, str) or not value.strip():
        raise ModelOperationError(
            code="invalid_evaluation_source",
            message=f"{field_name} must resolve to non-empty text.",
            details={"path": path},
        )
    return value.strip()


def _required_value(row: dict[str, Any], path: str, field_name: str) -> Any:
    if not path:
        raise ModelOperationError(
            code="invalid_evaluation_source",
            message=f"{field_name} mapping is required.",
        )
    cursor: Any = row
    for segment in path.split("."):
        if not isinstance(cursor, dict) or segment not in cursor:
            raise ModelOperationError(
                code="invalid_evaluation_source",
                message=f"{field_name} mapping could not be resolved.",
                details={"path": path},
            )
        cursor = cursor[segment]
    return cursor


def _string_field(row: dict[str, Any], path: str) -> str:
    if not path:
        return ""
    value = _required_value(row, path, path)
    return str(value).strip()


def _materialization_cache_key(
    *,
    source_metadata: dict[str, Any],
    profile: EvaluationProfileDefinition,
    field_mapping: EvaluationFieldMapping,
    dataset_id: str,
    suite_id: str,
) -> str:
    payload = json.dumps(
        {
            "source": source_metadata,
            "profile": {
                "profile_type": profile.profile_type,
                "result_kind": profile.result_kind,
                "extraction_mode": profile.extraction_mode,
                "scoring_mode": profile.scoring_mode,
                "threshold": profile.threshold,
                "output_schema": profile.output_schema or {},
                "ignored_paths": list(profile.ignored_paths),
            },
            "field_mapping": {
                "system_path": field_mapping.system_path,
                "input_text_path": field_mapping.input_text_path,
                "target_path": field_mapping.target_path,
                "sample_id_path": field_mapping.sample_id_path,
            },
            "dataset_id": dataset_id,
            "suite_id": suite_id,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _materialized_cache_hit(
    *,
    cache_root: Path,
    source_metadata: dict[str, Any],
    profile: EvaluationProfileDefinition,
    field_mapping: EvaluationFieldMapping,
    dataset_id: str,
    suite_id: str,
) -> MaterializedEvaluationDataset | None:
    _validate_field_mapping(field_mapping)
    cache_key = _materialization_cache_key(
        source_metadata=source_metadata,
        profile=profile,
        field_mapping=field_mapping,
        dataset_id=dataset_id,
        suite_id=suite_id,
    )
    package_path = cache_root / cache_key
    if (package_path / "manifest.json").is_file() and (package_path / "samples.jsonl").is_file():
        return MaterializedEvaluationDataset(package_path=package_path, cache_key=cache_key, cache_hit=True)
    return None


def _materialize_evaluation_rows(
    *,
    rows: list[dict[str, Any]],
    profile: EvaluationProfileDefinition,
    field_mapping: EvaluationFieldMapping,
    dataset_id: str,
    suite_id: str,
    cache_root: Path,
    source_metadata: dict[str, Any],
) -> MaterializedEvaluationDataset:
    _validate_field_mapping(field_mapping)
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_key = _materialization_cache_key(
        source_metadata=source_metadata,
        profile=profile,
        field_mapping=field_mapping,
        dataset_id=dataset_id,
        suite_id=suite_id,
    )
    package_path = cache_root / cache_key
    manifest_path = package_path / "manifest.json"
    samples_path = package_path / "samples.jsonl"
    if manifest_path.is_file() and samples_path.is_file():
        return MaterializedEvaluationDataset(package_path=package_path, cache_key=cache_key, cache_hit=True)

    if not rows:
        raise ModelOperationError(
            code="invalid_evaluation_source",
            message="Evaluation source does not contain any rows.",
            details={key: str(value) for key, value in source_metadata.items()},
        )

    manifest_payload = {
        "schema_version": "melix.evaluation_dataset_package.v2",
        "dataset_id": dataset_id,
        "suite_id": suite_id,
        "version": "2026-04-14",
        "sample_count": len(rows),
        "split": "validation",
        "task_kind": "text-generation",
        "input_modalities": ["text"],
        "profile_type": profile.profile_type,
        "result_kind": profile.result_kind,
        "extraction_mode": profile.extraction_mode,
        "scoring_mode": profile.scoring_mode,
        "threshold": profile.threshold,
        "output_schema": profile.output_schema or {},
        "ignored_paths": list(profile.ignored_paths),
        "field_mapping": {
            "system_path": field_mapping.system_path,
            "input_text_path": field_mapping.input_text_path,
            "target_path": field_mapping.target_path,
            "sample_id_path": field_mapping.sample_id_path,
        },
        **source_metadata,
    }
    _write_materialized_package(
        cache_root=cache_root,
        package_path=package_path,
        manifest_payload=manifest_payload,
        serialized_samples=_iter_serialized_samples(rows, field_mapping),
    )
    return MaterializedEvaluationDataset(package_path=package_path, cache_key=cache_key, cache_hit=False)


def _write_materialized_package(
    *,
    cache_root: Path,
    package_path: Path,
    manifest_payload: dict[str, Any],
    serialized_samples: Iterable[dict[str, Any]],
) -> None:
    staging_path = Path(tempfile.mkdtemp(prefix=f".{package_path.name}.tmp-", dir=cache_root))
    try:
        _write_jsonl_rows(staging_path / "samples.jsonl", serialized_samples)
        (staging_path / "manifest.json").write_text(json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8")
        if package_path.exists():
            manifest_path = package_path / "manifest.json"
            samples_path = package_path / "samples.jsonl"
            if manifest_path.is_file() and samples_path.is_file():
                return
            shutil.rmtree(package_path)
        staging_path.replace(package_path)
    finally:
        shutil.rmtree(staging_path, ignore_errors=True)


def _iter_serialized_samples(
    rows: list[dict[str, Any]],
    field_mapping: EvaluationFieldMapping,
) -> Iterator[dict[str, Any]]:
    for index, row in enumerate(rows, start=1):
        yield {
            "id": _string_field(row, field_mapping.sample_id_path) or f"sample-{index}",
            "system": _string_field(row, field_mapping.system_path),
            "input": {
                "text": _required_string_field(row, field_mapping.input_text_path, "input_text_path"),
            },
            "target": _required_value(row, field_mapping.target_path, "target_path"),
        }


def _write_jsonl_rows(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    json_dumps = json.dumps
    with path.open("w", encoding="utf-8") as handle:
        handle_write = handle.write
        wrote_row = False
        for row in rows:
            wrote_row = True
            handle_write(json_dumps(row))
            handle_write("\n")
        if not wrote_row:
            handle_write("\n")


def _validate_field_mapping(field_mapping: EvaluationFieldMapping) -> None:
    if not field_mapping.input_text_path or not field_mapping.target_path:
        raise ModelOperationError(
            code="invalid_evaluation_source",
            message="final_result materialization requires explicit input_text_path and target_path mapping.",
        )


def _fetch_hf_dataset_server_json(endpoint: str, params: dict[str, str]) -> dict[str, Any]:
    query = urlencode({key: value for key, value in params.items() if value})
    request = Request(f"{_HF_DATASETS_SERVER_URL}/{endpoint}?{query}")
    token = os.environ.get("HF_TOKEN", "").strip() or os.environ.get("HUGGING_FACE_HUB_TOKEN", "").strip()
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/json")
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise ModelOperationError(
            code="hf_dataset_fetch_failed",
            message=f"Hugging Face dataset request failed with HTTP {exc.code}.",
        ) from exc
    except URLError as exc:
        raise ModelOperationError(
            code="hf_dataset_fetch_failed",
            message=f"Hugging Face dataset request failed: {exc.reason}",
        ) from exc
    except json.JSONDecodeError as exc:
        raise ModelOperationError(
            code="hf_dataset_fetch_failed",
            message="Hugging Face dataset response was not valid JSON.",
        ) from exc
    if not isinstance(payload, dict):
        raise ModelOperationError(
            code="hf_dataset_fetch_failed",
            message="Hugging Face dataset response must be a JSON object.",
        )
    return payload


def _resolve_hf_dataset_name(
    source: HFEvaluationDatasetSource,
    fetcher: HFEvaluationDatasetFetcher,
) -> str:
    payload = fetcher(
        "splits",
        {
            "dataset": source.dataset_path,
            "revision": source.dataset_revision or "main",
        },
    )
    splits = payload.get("splits")
    if not isinstance(splits, list) or not splits:
        raise ModelOperationError(
            code="hf_dataset_fetch_failed",
            message="Hugging Face dataset splits metadata is unavailable.",
            details={"hf_dataset_path": source.dataset_path},
        )

    for item in splits:
        if not isinstance(item, dict):
            continue
        if str(item.get("split", "")).strip() == (source.split or "train"):
            config = str(item.get("config", "")).strip()
            if config:
                return config

    first = splits[0]
    if isinstance(first, dict):
        config = str(first.get("config", "")).strip()
        if config:
            return config

    raise ModelOperationError(
        code="hf_dataset_fetch_failed",
        message="Unable to resolve a Hugging Face dataset configuration for evaluation.",
        details={"hf_dataset_path": source.dataset_path},
    )


def _fetch_hf_dataset_rows(
    source: HFEvaluationDatasetSource,
    fetcher: HFEvaluationDatasetFetcher,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    page_size = 100
    while True:
        payload = fetcher(
            "rows",
            {
                "dataset": source.dataset_path,
                "config": source.dataset_name,
                "split": source.split or "train",
                "offset": str(offset),
                "length": str(page_size),
                "revision": source.dataset_revision or "main",
            },
        )
        raw_rows = payload.get("rows")
        if not isinstance(raw_rows, list):
            raise ModelOperationError(
                code="hf_dataset_fetch_failed",
                message="Hugging Face dataset rows payload is malformed.",
                details={"hf_dataset_path": source.dataset_path},
            )
        if not raw_rows:
            break
        for item in raw_rows:
            if not isinstance(item, dict):
                continue
            row = item.get("row")
            if isinstance(row, dict):
                rows.append(row)
        if len(raw_rows) < page_size:
            break
        offset += len(raw_rows)
    return rows


def _hf_dataset_uri(
    *,
    dataset_path: str,
    dataset_name: str,
    dataset_revision: str,
    split: str,
) -> str:
    return f"hf://{dataset_path}?config={dataset_name}&split={split}&revision={dataset_revision}"


def _hf_source_slug(dataset_path: str) -> str:
    return dataset_path.rsplit("/", 1)[-1].replace(".", "-")


def _parses_json(payload: str) -> bool:
    try:
        json.loads(payload)
    except json.JSONDecodeError:
        return False
    return True


def _last_stripped_pattern_match(pattern: re.Pattern[str], raw_response: str) -> str:
    candidate = ""
    for match in pattern.finditer(raw_response):
        stripped = match.group(1).strip()
        if stripped:
            candidate = stripped
    return candidate


def _last_balanced_json_suffix(raw_response: str) -> str:
    for index in range(len(raw_response) - 1, -1, -1):
        if raw_response[index] not in "[{":
            continue
        candidate = raw_response[index:].strip()
        if _parses_json(candidate):
            return candidate
    return ""


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def _matches_json_type(value: Any, expected_type: str) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "null":
        return value is None
    return True
