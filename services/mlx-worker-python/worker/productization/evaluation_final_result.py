from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

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
    rows = _read_local_rows(request.source_kind, resolved_source_path)
    return _materialize_evaluation_rows(
        rows=rows,
        profile=request.profile,
        field_mapping=request.field_mapping,
        dataset_id=request.dataset_id or f"{resolved_source_path.stem}.dev.v1",
        suite_id=request.suite_id or resolved_source_path.stem,
        cache_root=cache_root,
        source_metadata=_local_source_metadata(
            source_kind=request.source_kind,
            source_path=resolved_source_path,
        ),
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
    json_blocks = [candidate.strip() for candidate in _JSON_FENCE_PATTERN.findall(raw_response) if candidate.strip()]
    if json_blocks:
        candidate = json_blocks[-1]
        if _parses_json(candidate):
            return ExtractionOutcome(candidate, "extracted")

    generic_blocks = [candidate.strip() for candidate in _GENERIC_FENCE_PATTERN.findall(raw_response) if candidate.strip()]
    valid_generic = [candidate for candidate in generic_blocks if _parses_json(candidate)]
    if valid_generic:
        candidate = valid_generic[-1]
        if len(valid_generic) > 1:
            return ExtractionOutcome("", "ambiguous_extraction", "multiple_generic_json_candidates")
        return ExtractionOutcome(candidate, "extracted")

    suffix = _last_balanced_json_suffix(raw_response)
    if suffix:
        return ExtractionOutcome(suffix, "extracted")
    return ExtractionOutcome("", "extraction_failed", "no_json_candidate")


def _extract_text_heuristic(raw_response: str) -> ExtractionOutcome:
    answer_prefix_matches = [match.group(1).strip() for match in _TEXT_ANSWER_PATTERN.finditer(raw_response) if match.group(1).strip()]
    if answer_prefix_matches:
        if len(answer_prefix_matches) > 1:
            return ExtractionOutcome("", "ambiguous_extraction", "multiple_answer_prefix_candidates")
        return ExtractionOutcome(answer_prefix_matches[0], "extracted")

    fenced_blocks = [candidate.strip() for candidate in _GENERIC_FENCE_PATTERN.findall(raw_response) if candidate.strip()]
    if fenced_blocks:
        return ExtractionOutcome(fenced_blocks[-1], "extracted")

    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", raw_response) if paragraph.strip()]
    if paragraphs:
        lines = [line.strip() for line in paragraphs[-1].splitlines() if line.strip()]
        if lines:
            return ExtractionOutcome(lines[-1], "extracted")
        return ExtractionOutcome(paragraphs[-1], "extracted")

    return ExtractionOutcome("", "extraction_failed", "no_text_candidate")


def _score_json_result(
    *,
    extracted_result: str,
    target: str,
    profile: EvaluationProfileDefinition,
) -> ScoringOutcome:
    parsed_target = json.loads(target)
    try:
        parsed_result = json.loads(extracted_result)
    except json.JSONDecodeError:
        return ScoringOutcome(typed_score=0.0, validation_status="parse_failed", failure_reason="invalid_json")

    validation_error = _validate_json_schema(profile.output_schema or {}, parsed_result)
    if validation_error:
        return ScoringOutcome(typed_score=0.0, validation_status="schema_failed", failure_reason=validation_error)

    score = _json_typed_score(
        expected=parsed_target,
        actual=parsed_result,
        ignored_paths=_DEFAULT_IGNORED_PATHS | set(profile.ignored_paths),
    )
    return ScoringOutcome(typed_score=round(score, 4), validation_status="validated")


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
    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(payload, dict):
            return "root_type_mismatch"
        for key in schema.get("required", []):
            if key not in payload:
                return f"missing_required:{key}"
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, value in properties.items():
                if key in payload:
                    field_type = value.get("type") if isinstance(value, dict) else None
                    if field_type and not _matches_json_type(payload[key], field_type):
                        return f"type_mismatch:{key}"
        return ""
    if expected_type == "array":
        if not isinstance(payload, list):
            return "root_type_mismatch"
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            item_type = item_schema.get("type")
            if item_type:
                for item in payload:
                    if not _matches_json_type(item, item_type):
                        return "item_type_mismatch"
        return ""
    return ""


def _json_typed_score(*, expected: Any, actual: Any, ignored_paths: set[str], path: str = "") -> float:
    if isinstance(expected, dict):
        expected_keys = [key for key in expected if _joined_path(path, key) not in ignored_paths]
        if not expected_keys:
            return 1.0
        scores = [
            _json_typed_score(
                expected=expected[key],
                actual=actual.get(key) if isinstance(actual, dict) else None,
                ignored_paths=ignored_paths,
                path=_joined_path(path, key),
            )
            for key in expected_keys
        ]
        return sum(scores) / len(scores)
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            return 0.0
        if not expected:
            return 1.0
        scores = [
            _json_typed_score(expected=item, actual=actual[index], ignored_paths=ignored_paths, path=f"{path}[{index}]")
            for index, item in enumerate(expected)
        ]
        return sum(scores) / len(scores)
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


def _sha256_for_path(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _read_local_rows(source_kind: str, source_path: Path) -> list[dict[str, Any]]:
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
    if source_kind == "csv":
        with resolved.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    raise ModelOperationError(
        code="invalid_evaluation_source",
        message=f"Unsupported local evaluation source kind: {source_kind}",
    )


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

    serialized_samples: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        serialized_samples.append(
            {
                "id": _string_field(row, field_mapping.sample_id_path) or f"sample-{index}",
                "system": _string_field(row, field_mapping.system_path),
                "input": {
                    "text": _required_string_field(row, field_mapping.input_text_path, "input_text_path"),
                },
                "target": _required_value(row, field_mapping.target_path, "target_path"),
            }
        )

    package_path.mkdir(parents=True, exist_ok=True)
    manifest_payload = {
        "schema_version": "melix.evaluation_dataset_package.v2",
        "dataset_id": dataset_id,
        "suite_id": suite_id,
        "version": "2026-04-14",
        "sample_count": len(serialized_samples),
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
    manifest_path.write_text(json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8")
    samples_path.write_text(
        "\n".join(json.dumps(sample) for sample in serialized_samples) + "\n",
        encoding="utf-8",
    )
    return MaterializedEvaluationDataset(package_path=package_path, cache_key=cache_key, cache_hit=False)


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


def _last_balanced_json_suffix(raw_response: str) -> str:
    for index, character in enumerate(raw_response):
        if character not in "[{":
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
