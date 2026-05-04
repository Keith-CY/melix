from __future__ import annotations

import hashlib
import json
from itertools import chain
from contextlib import ExitStack
from dataclasses import dataclass
from dataclasses import replace
import os
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from worker.model_ops.errors import ModelOperationError

_SUPPORTED_FORMATS = {
    "chat_messages",
    "prompt_completion",
    "text_completion",
    "preference_pair",
    "prompt_candidate",
    "reward_scored",
    "calibration",
}
_SUPPORTED_ROLES = {"system", "user", "assistant", "tool"}
_HF_DATASETS_SERVER_URL = "https://datasets-server.huggingface.co"
_QUALITY_REPORT_SAMPLE_LIMIT = 10
_ALLOWED_CONTROL_CHARACTERS = frozenset({"\n", "\r", "\t"})

HFDatasetFetcher = Callable[[str, dict[str, str]], dict[str, Any]]


@dataclass(frozen=True)
class TrainingDatasetPackage:
    package_path: Path
    manifest_path: Path
    samples_path: Path
    schema_version: str
    dataset_id: str
    format: str
    sample_count: int
    version: str
    normalized_samples: list[dict[str, Any]]
    normalized_validation_samples: list[dict[str, Any]]
    validation_sample_count: int
    response_only_supported: bool


@dataclass(frozen=True)
class NormalizedDatasetSnapshot:
    dataset_dir: Path
    manifest_path: Path
    samples_path: Path
    train_path: Path
    valid_path: Path | None
    sample_count: int
    validation_sample_count: int
    format: str


@dataclass(frozen=True)
class HFDatasetReference:
    dataset_path: str
    dataset_name: str
    dataset_revision: str
    train_split: str
    chat_feature: str
    prompt_feature: str
    completion_feature: str
    text_feature: str
    valid_split: str = ""
    chosen_feature: str = ""
    rejected_feature: str = ""


@dataclass(frozen=True)
class MaterializedTrainingDatasetPackage:
    package_path: Path
    cache_key: str
    cache_hit: bool
    dataset_uri: str
    reference: HFDatasetReference
    package: TrainingDatasetPackage | None = None


@dataclass(frozen=True)
class ResolvedTrainingDatasetPackage:
    package: TrainingDatasetPackage
    source_kind: str
    dataset_uri: str
    materialized_package_path: Path
    cache_key: str
    cache_hit: bool
    hf_reference: HFDatasetReference | None


@dataclass(frozen=True)
class BuiltTrainingDatasetArtifact:
    package_path: Path
    manifest_path: Path
    output_path: Path
    manifest_payload: dict[str, Any]
    sample_count: int
    validation_sample_count: int
    format: str
    inspect_only: bool


def _write_jsonl_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    _write_duplicate_jsonl_rows((path,), rows)


def _write_duplicate_jsonl_rows(paths: tuple[Path, ...], rows: list[dict[str, Any]]) -> None:
    with ExitStack() as stack:
        handles = [stack.enter_context(path.open("w", encoding="utf-8")) for path in paths]
        wrote_any = False
        for row in rows:
            line = json.dumps(row) + "\n"
            for handle in handles:
                handle.write(line)
            wrote_any = True
        if not wrote_any:
            for handle in handles:
                handle.write("\n")


def _iter_dataset_package_jsonl_rows(
    path: Path,
    *,
    invalid_json_message: str,
    sample_limit: int = 0,
) -> Iterable[dict[str, Any]]:
    yielded = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ModelOperationError(
                    code="invalid_dataset_package",
                    message=invalid_json_message,
                    details={"line": str(line_number)},
                ) from exc
            yield payload
            yielded += 1
            if sample_limit > 0 and yielded >= sample_limit:
                break


def _build_training_dataset_package(
    *,
    dataset_uri: str,
    package_path: Path,
    manifest_path: Path,
    samples_path: Path,
    manifest: dict[str, Any],
    serialized_samples: Iterable[dict[str, Any]],
    serialized_validation_samples: Iterable[dict[str, Any]],
    sample_limit: int = 0,
    max_characters_per_sample: int = 0,
) -> TrainingDatasetPackage:
    if not isinstance(manifest, dict):
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="Training dataset manifest must be a JSON object.",
            details={"dataset_uri": dataset_uri},
        )

    missing_fields = [
        field
        for field in ("schema_version", "dataset_id", "format", "sample_count", "version")
        if field not in manifest
    ]
    if missing_fields:
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="Training dataset manifest is missing required fields.",
            details={"missing_fields": ",".join(missing_fields)},
        )

    format_name = str(manifest["format"])
    if format_name not in _SUPPORTED_FORMATS:
        raise ModelOperationError(
            code="invalid_dataset_package",
            message=f"Unsupported training dataset format: {format_name}",
            details={"format": format_name},
        )

    normalized_samples: list[dict[str, Any]] = []
    for sample in serialized_samples:
        normalized_samples.append(
            _normalize_sample(
                sample,
                format_name=format_name,
                max_characters_per_sample=max_characters_per_sample,
            )
        )
        if sample_limit > 0 and len(normalized_samples) >= sample_limit:
            break

    if not normalized_samples:
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="Training dataset package does not contain any usable samples.",
            details={"dataset_uri": dataset_uri},
        )

    declared_sample_count = int(manifest["sample_count"])
    if sample_limit <= 0 and declared_sample_count != len(normalized_samples):
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="Training dataset sample_count does not match samples.jsonl.",
            details={
                "declared_sample_count": str(declared_sample_count),
                "actual_sample_count": str(len(normalized_samples)),
            },
        )

    normalized_validation_samples = [
        _normalize_sample(
            sample,
            format_name=format_name,
            max_characters_per_sample=max_characters_per_sample,
        )
        for sample in serialized_validation_samples
    ]

    return TrainingDatasetPackage(
        package_path=package_path,
        manifest_path=manifest_path,
        samples_path=samples_path,
        schema_version=str(manifest["schema_version"]),
        dataset_id=str(manifest["dataset_id"]),
        format=format_name,
        sample_count=len(normalized_samples),
        version=str(manifest["version"]),
        normalized_samples=normalized_samples,
        normalized_validation_samples=normalized_validation_samples,
        validation_sample_count=len(normalized_validation_samples),
        response_only_supported=format_name in {"chat_messages", "prompt_completion"},
    )


def load_training_dataset_package(
    dataset_uri: str,
    *,
    sample_limit: int = 0,
    max_characters_per_sample: int = 0,
) -> TrainingDatasetPackage:
    package_path = Path(dataset_uri).expanduser().resolve()
    manifest_path = package_path / "manifest.json"
    samples_path = package_path / "samples.jsonl"

    if not manifest_path.is_file() or not samples_path.is_file():
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="Training dataset package must contain manifest.json and samples.jsonl.",
            details={"dataset_uri": dataset_uri},
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="Training dataset manifest is not valid JSON.",
            details={"dataset_uri": dataset_uri},
        ) from exc

    validation_samples_path = package_path / "valid.jsonl"
    serialized_validation_samples: Iterable[dict[str, Any]] = ()
    if validation_samples_path.is_file():
        serialized_validation_samples = _iter_dataset_package_jsonl_rows(
            validation_samples_path,
            invalid_json_message="Training dataset validation sample is not valid JSON.",
        )

    return _build_training_dataset_package(
        dataset_uri=dataset_uri,
        package_path=package_path,
        manifest_path=manifest_path,
        samples_path=samples_path,
        manifest=manifest,
        serialized_samples=_iter_dataset_package_jsonl_rows(
            samples_path,
            invalid_json_message="Training dataset sample is not valid JSON.",
            sample_limit=sample_limit,
        ),
        serialized_validation_samples=serialized_validation_samples,
        sample_limit=sample_limit,
        max_characters_per_sample=max_characters_per_sample,
    )


def resolve_training_dataset_package(
    request_ext: dict[str, str],
    *,
    jobs_root: Path,
    hf_dataset_fetcher: HFDatasetFetcher | None = None,
    sample_limit: int = 0,
    max_characters_per_sample: int = 0,
) -> ResolvedTrainingDatasetPackage:
    source_kind = request_ext.get("dataset_source_kind", "").strip() or (
        "hf_dataset" if request_ext.get("hf_dataset_path", "").strip() else "local_package"
    )
    if source_kind == "local_package":
        if request_ext.get("hf_valid_split", "").strip():
            raise ModelOperationError(
                code="invalid_dataset_source",
                message="hf_valid_split is only supported for hf_dataset sources.",
            )
        dataset_uri = request_ext.get("dataset_uri", "").strip()
        package = load_training_dataset_package(
            dataset_uri,
            sample_limit=sample_limit,
            max_characters_per_sample=max_characters_per_sample,
        )
        return ResolvedTrainingDatasetPackage(
            package=package,
            source_kind="local_package",
            dataset_uri=dataset_uri,
            materialized_package_path=package.package_path,
            cache_key="",
            cache_hit=False,
            hf_reference=None,
        )

    if source_kind != "hf_dataset":
        raise ModelOperationError(
            code="invalid_dataset_source",
            message=f"Unsupported dataset_source_kind: {source_kind}",
        )

    reference = HFDatasetReference(
        dataset_path=request_ext.get("hf_dataset_path", "").strip(),
        dataset_name=request_ext.get("hf_dataset_name", "").strip(),
        dataset_revision=request_ext.get("hf_dataset_revision", "").strip() or "main",
        train_split=request_ext.get("hf_train_split", "").strip() or "train",
        chat_feature=request_ext.get("chat_feature", "").strip(),
        prompt_feature=request_ext.get("prompt_feature", "").strip(),
        completion_feature=request_ext.get("completion_feature", "").strip(),
        text_feature=request_ext.get("text_feature", "").strip(),
        valid_split=request_ext.get("hf_valid_split", "").strip(),
        chosen_feature=request_ext.get("chosen_feature", "").strip(),
        rejected_feature=request_ext.get("rejected_feature", "").strip(),
    )
    if not reference.dataset_path:
        raise ModelOperationError(
            code="invalid_dataset_source",
            message="hf_dataset training requires hf_dataset_path.",
        )

    materialized = materialize_hf_training_dataset_package(
        reference,
        cache_root=jobs_root / "datasets",
        fetch_json=hf_dataset_fetcher,
    )
    package = materialized.package
    if package is None or materialized.cache_hit or sample_limit > 0 or max_characters_per_sample > 0:
        package = load_training_dataset_package(
            str(materialized.package_path),
            sample_limit=sample_limit,
            max_characters_per_sample=max_characters_per_sample,
        )
    return ResolvedTrainingDatasetPackage(
        package=package,
        source_kind="hf_dataset",
        dataset_uri=materialized.dataset_uri,
        materialized_package_path=materialized.package_path,
        cache_key=materialized.cache_key,
        cache_hit=materialized.cache_hit,
        hf_reference=materialized.reference,
    )


def build_training_dataset_artifact(
    request_ext: dict[str, str],
    *,
    jobs_root: Path,
    output_dir: Path,
    source_model_id: str = "",
    hf_dataset_fetcher: HFDatasetFetcher | None = None,
    progress: Callable[[str, float], None] | None = None,
) -> BuiltTrainingDatasetArtifact:
    inspect_only = _truthy(request_ext.get("inspect_only", ""))
    preview_count = _int_ext_value(
        request_ext.get("preview_count", ""),
        default=3,
        minimum=1,
        field_name="preview_count",
    )
    validation_ratio = _float_ext_value(
        request_ext.get("validation_ratio", ""),
        default=0.0,
        minimum=0.0,
        maximum=0.99,
        field_name="validation_ratio",
    )
    sample_limit = _int_ext_value(
        request_ext.get("sample_limit", ""),
        default=0,
        minimum=0,
        field_name="sample_limit",
    )

    if progress is not None:
        progress("resolve_source", 0.15)

    source = _resolve_dataset_build_source(
        request_ext,
        jobs_root=jobs_root,
        hf_dataset_fetcher=hf_dataset_fetcher,
        sample_limit=sample_limit,
    )

    source_train_samples = source["samples"]
    source_validation_samples = source["validation_samples"]
    if not source_train_samples and not source_validation_samples:
        raise ModelOperationError(
            code="invalid_dataset_source",
            message="Dataset builder did not resolve any usable training samples.",
        )

    train_samples = source_train_samples
    validation_samples = source_validation_samples

    if progress is not None:
        progress("inspect_samples", 0.45)

    validation_strategy = "source_validation" if validation_samples else "none"
    if validation_ratio > 0 and not validation_samples:
        train_samples, validation_samples = _deterministic_validation_split(
            train_samples,
            validation_ratio,
        )
        validation_strategy = "deterministic_ratio"

    quality, token_stats = _build_quality_and_token_stats(
        chain(source_train_samples, source_validation_samples),
        source["format"],
    )

    manifest_payload: dict[str, Any] = {
        "dataset_id": source["dataset_id"],
        "format": source["format"],
        "sample_count": len(train_samples),
        "validation_sample_count": len(validation_samples),
        "version": source["version"],
        "source_model": source_model_id,
        "source_kind": source["source_kind"],
        "dataset_uri": source["source_uri"],
        "source_manifest_path": source["source_manifest_path"],
        "source_samples_path": source["source_samples_path"],
        "response_only_supported": source["response_only_supported"],
        "conversion_template": source["conversion_template"],
        "validation_strategy": validation_strategy,
        "validation_ratio": validation_ratio,
        "preview_count": preview_count,
        "preview_samples": train_samples[:preview_count],
        "validation_preview_samples": validation_samples[:preview_count],
        "quality": quality,
        "token_stats": token_stats,
        "build_ready": True,
        "operation": "build_training_dataset",
        "inspect_only": inspect_only,
    }
    if source["hf_metadata"]:
        manifest_payload.update(source["hf_metadata"])

    package_path = output_dir.expanduser().resolve()
    package_path.mkdir(parents=True, exist_ok=True)

    if inspect_only:
        if progress is not None:
            progress("write_inspection_manifest", 0.9)
        manifest_payload["schema_version"] = "melix.training_dataset_inspection.v1"
        manifest_path = package_path / "training_dataset.inspect.json"
        manifest_path.write_text(json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8")
        _cleanup_dataset_package_files(package_path)
        return BuiltTrainingDatasetArtifact(
            package_path=package_path,
            manifest_path=manifest_path,
            output_path=manifest_path,
            manifest_payload=manifest_payload,
            sample_count=len(train_samples),
            validation_sample_count=len(validation_samples),
            format=source["format"],
            inspect_only=True,
        )

    if progress is not None:
        progress("write_dataset_package", 0.9)
    manifest_payload["schema_version"] = "melix.training_dataset_package.v1"
    manifest_path = package_path / "manifest.json"
    samples_path = package_path / "samples.jsonl"
    _write_jsonl_rows(samples_path, train_samples)
    valid_path = package_path / "valid.jsonl"
    if validation_samples:
        _write_jsonl_rows(valid_path, validation_samples)
    elif valid_path.exists():
        valid_path.unlink()
    manifest_path.write_text(json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8")
    return BuiltTrainingDatasetArtifact(
        package_path=package_path,
        manifest_path=manifest_path,
        output_path=package_path,
        manifest_payload=manifest_payload,
        sample_count=len(train_samples),
        validation_sample_count=len(validation_samples),
        format=source["format"],
        inspect_only=False,
    )


def write_normalized_dataset_snapshot(
    dataset: TrainingDatasetPackage,
    *,
    output_dir: Path,
) -> NormalizedDatasetSnapshot:
    dataset_dir = output_dir / "normalized_dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = dataset_dir / "manifest.json"
    samples_path = dataset_dir / "samples.jsonl"
    train_path = dataset_dir / "train.jsonl"
    valid_path = dataset_dir / "valid.jsonl"

    manifest_payload = {
        "schema_version": "melix.training_dataset_snapshot.v1",
        "dataset_id": dataset.dataset_id,
        "format": dataset.format,
        "sample_count": dataset.sample_count,
        "validation_sample_count": dataset.validation_sample_count,
        "version": dataset.version,
        "source_manifest_path": str(dataset.manifest_path),
        "source_samples_path": str(dataset.samples_path),
        "response_only_supported": dataset.response_only_supported,
    }
    manifest_path.write_text(json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8")

    _write_duplicate_jsonl_rows((samples_path, train_path), dataset.normalized_samples)
    if dataset.normalized_validation_samples:
        _write_jsonl_rows(valid_path, dataset.normalized_validation_samples)
    else:
        if valid_path.exists():
            valid_path.unlink()
        valid_path = None

    return NormalizedDatasetSnapshot(
        dataset_dir=dataset_dir,
        manifest_path=manifest_path,
        samples_path=samples_path,
        train_path=train_path,
        valid_path=valid_path,
        sample_count=dataset.sample_count,
        validation_sample_count=dataset.validation_sample_count,
        format=dataset.format,
    )


def materialize_hf_training_dataset_package(
    reference: HFDatasetReference,
    *,
    cache_root: Path,
    fetch_json: HFDatasetFetcher | None = None,
) -> MaterializedTrainingDatasetPackage:
    fetcher = fetch_json or _fetch_hf_dataset_server_json
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_key = _hf_materialization_cache_key(reference)
    package_path = cache_root / cache_key
    manifest_path = package_path / "manifest.json"
    samples_path = package_path / "samples.jsonl"
    if manifest_path.is_file() and samples_path.is_file():
        cached_reference = _reference_from_cached_manifest(reference, manifest_path)
        return MaterializedTrainingDatasetPackage(
            package_path=package_path,
            cache_key=cache_key,
            cache_hit=True,
            dataset_uri=_hf_dataset_uri(cached_reference),
            reference=cached_reference,
        )

    resolved_reference = reference
    if not resolved_reference.dataset_name:
        resolved_reference = replace(
            resolved_reference,
            dataset_name=_resolve_hf_dataset_name(resolved_reference, fetcher),
        )

    rows = _fetch_hf_dataset_rows(resolved_reference, fetcher)
    if not rows:
        raise ModelOperationError(
            code="hf_dataset_fetch_failed",
            message="Hugging Face dataset did not return any training rows.",
            details={"hf_dataset_path": resolved_reference.dataset_path},
        )

    format_name = _infer_hf_dataset_format(resolved_reference, rows)
    serialized_samples = [_map_hf_row_to_training_sample(row, format_name, resolved_reference) for row in rows]
    serialized_validation_samples: list[dict[str, Any]] = []
    if resolved_reference.valid_split:
        validation_rows = _fetch_hf_dataset_rows(
            replace(resolved_reference, train_split=resolved_reference.valid_split),
            fetcher,
        )
        if not validation_rows:
            raise ModelOperationError(
                code="hf_dataset_fetch_failed",
                message="Hugging Face validation split did not return any rows.",
                details={
                    "hf_dataset_path": resolved_reference.dataset_path,
                    "hf_valid_split": resolved_reference.valid_split,
                },
            )
        serialized_validation_samples = [
            _map_hf_row_to_training_sample(row, format_name, resolved_reference)
            for row in validation_rows
        ]
    dataset_uri = _hf_dataset_uri(resolved_reference)
    dataset_id = (
        f"{resolved_reference.dataset_path}:{resolved_reference.dataset_name}:"
        f"{resolved_reference.train_split}@{resolved_reference.dataset_revision}"
    )

    package_path.mkdir(parents=True, exist_ok=True)
    manifest_payload = {
        "schema_version": "melix.training_dataset_package.v1",
        "dataset_id": dataset_id,
        "format": format_name,
        "sample_count": len(serialized_samples),
        "version": resolved_reference.dataset_revision,
        "dataset_uri": dataset_uri,
        "source_kind": "hf_dataset",
        "hf_dataset_path": resolved_reference.dataset_path,
        "hf_dataset_name": resolved_reference.dataset_name,
        "hf_dataset_revision": resolved_reference.dataset_revision,
        "hf_train_split": resolved_reference.train_split,
        "hf_valid_split": resolved_reference.valid_split,
        "validation_sample_count": len(serialized_validation_samples),
        "chat_feature": resolved_reference.chat_feature,
        "prompt_feature": resolved_reference.prompt_feature,
        "completion_feature": resolved_reference.completion_feature,
        "text_feature": resolved_reference.text_feature,
        "chosen_feature": resolved_reference.chosen_feature,
        "rejected_feature": resolved_reference.rejected_feature,
    }
    manifest_path.write_text(json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8")
    _write_jsonl_rows(samples_path, serialized_samples)
    if serialized_validation_samples:
        _write_jsonl_rows(package_path / "valid.jsonl", serialized_validation_samples)
    return MaterializedTrainingDatasetPackage(
        package_path=package_path,
        cache_key=cache_key,
        cache_hit=False,
        dataset_uri=dataset_uri,
        reference=resolved_reference,
        package=_build_training_dataset_package(
            dataset_uri=dataset_uri,
            package_path=package_path,
            manifest_path=manifest_path,
            samples_path=samples_path,
            manifest=manifest_payload,
            serialized_samples=serialized_samples,
            serialized_validation_samples=serialized_validation_samples,
        ),
    )


def _normalize_sample(
    sample: Any,
    *,
    format_name: str,
    max_characters_per_sample: int,
) -> dict[str, Any]:
    if not isinstance(sample, dict):
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="Training dataset samples must be JSON objects.",
        )

    if format_name == "chat_messages":
        messages = sample.get("messages")
        if not isinstance(messages, list) or not messages:
            raise ModelOperationError(
                code="invalid_dataset_package",
                message="chat_messages samples must contain a non-empty messages array.",
            )
        normalized_messages: list[dict[str, str]] = []
        assistant_count = 0
        previous_role = ""
        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                raise ModelOperationError(
                    code="invalid_dataset_package",
                    message="Each chat message must be a JSON object.",
                    details={"message_index": str(index)},
                )
            role = str(message.get("role", "")).strip()
            content = str(message.get("content", "")).strip()
            if role not in _SUPPORTED_ROLES or not content:
                raise ModelOperationError(
                    code="invalid_dataset_package",
                    message="Chat messages must contain supported roles and non-empty content.",
                    details={"message_index": str(index)},
                )
            if role == "assistant":
                assistant_count += 1
            if previous_role == role and role in {"user", "assistant", "tool"}:
                raise ModelOperationError(
                    code="invalid_dataset_package",
                    message="Chat message ordering is invalid for supervised training.",
                    details={"message_index": str(index)},
                )
            previous_role = role
            normalized_messages.append(
                {"role": role, "content": _truncate_text(content, max_characters_per_sample)}
            )
        if assistant_count == 0 or normalized_messages[-1]["role"] != "assistant":
            raise ModelOperationError(
                code="invalid_dataset_package",
                message="Chat datasets must end with an assistant message for supervision.",
            )
        payload: dict[str, Any] = {"messages": normalized_messages}
        if "tools" in sample and isinstance(sample["tools"], list):
            payload["tools"] = sample["tools"]
        return payload

    if format_name == "prompt_completion":
        prompt = str(sample.get("prompt", "")).strip()
        completion = str(sample.get("completion", "")).strip()
        if not prompt or not completion:
            raise ModelOperationError(
                code="invalid_dataset_package",
                message="prompt_completion samples must include prompt and completion text.",
            )
        return {
            "prompt": _truncate_text(prompt, max_characters_per_sample),
            "completion": _truncate_text(completion, max_characters_per_sample),
        }

    if format_name == "preference_pair":
        prompt = str(sample.get("prompt", "")).strip()
        chosen = str(sample.get("chosen", "")).strip()
        rejected = str(sample.get("rejected", "")).strip()
        if not prompt or not chosen or not rejected:
            raise ModelOperationError(
                code="invalid_dataset_package",
                message="preference_pair samples must include prompt, chosen, and rejected text.",
            )
        return {
            "prompt": _truncate_text(prompt, max_characters_per_sample),
            "chosen": _truncate_text(chosen, max_characters_per_sample),
            "rejected": _truncate_text(rejected, max_characters_per_sample),
        }

    if format_name == "prompt_candidate":
        prompt = str(sample.get("prompt", "")).strip()
        candidates = sample.get("candidates")
        if not prompt or not isinstance(candidates, list) or len(candidates) < 2:
            raise ModelOperationError(
                code="invalid_dataset_package",
                message="prompt_candidate samples must include prompt text and at least two candidates.",
            )
        normalized_candidates: list[dict[str, Any]] = []
        for candidate_index, candidate in enumerate(candidates):
            candidate_text = ""
            candidate_payload: dict[str, Any] = {}
            if isinstance(candidate, str):
                candidate_text = candidate.strip()
            elif isinstance(candidate, dict):
                candidate_text = str(candidate.get("text", "")).strip()
                if "score" in candidate:
                    try:
                        candidate_payload["score"] = float(candidate["score"])
                    except (TypeError, ValueError) as exc:
                        raise ModelOperationError(
                            code="invalid_dataset_package",
                            message="prompt_candidate candidate scores must be numeric.",
                            details={"candidate_index": str(candidate_index)},
                        ) from exc
            else:
                raise ModelOperationError(
                    code="invalid_dataset_package",
                    message="prompt_candidate candidates must be strings or JSON objects.",
                    details={"candidate_index": str(candidate_index)},
                )
            if not candidate_text:
                raise ModelOperationError(
                    code="invalid_dataset_package",
                    message="prompt_candidate candidates must include non-empty text.",
                    details={"candidate_index": str(candidate_index)},
                )
            candidate_payload["text"] = _truncate_text(candidate_text, max_characters_per_sample)
            normalized_candidates.append(candidate_payload)
        return {
            "prompt": _truncate_text(prompt, max_characters_per_sample),
            "candidates": normalized_candidates,
        }

    if format_name == "reward_scored":
        prompt = str(sample.get("prompt", "")).strip()
        response = str(sample.get("response", "")).strip()
        if not prompt or not response or "reward_score" not in sample:
            raise ModelOperationError(
                code="invalid_dataset_package",
                message="reward_scored samples must include prompt, response, and reward_score.",
            )
        try:
            reward_score = float(sample["reward_score"])
        except (TypeError, ValueError) as exc:
            raise ModelOperationError(
                code="invalid_dataset_package",
                message="reward_scored reward_score must be numeric.",
            ) from exc
        return {
            "prompt": _truncate_text(prompt, max_characters_per_sample),
            "response": _truncate_text(response, max_characters_per_sample),
            "reward_score": reward_score,
        }

    if format_name == "calibration":
        text = str(sample.get("text", "")).strip()
        if not text:
            raise ModelOperationError(
                code="invalid_dataset_package",
                message="calibration samples must include text.",
            )
        return {"text": _truncate_text(text, max_characters_per_sample)}

    text = str(sample.get("text", "")).strip()
    if not text:
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="text_completion samples must include text.",
        )
    return {"text": _truncate_text(text, max_characters_per_sample)}


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


def _reference_from_cached_manifest(
    reference: HFDatasetReference,
    manifest_path: Path,
) -> HFDatasetReference:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return reference
    if not isinstance(payload, dict):
        return reference
    return replace(
        reference,
        dataset_name=str(payload.get("hf_dataset_name", reference.dataset_name)),
        dataset_revision=str(payload.get("hf_dataset_revision", reference.dataset_revision)),
        train_split=str(payload.get("hf_train_split", reference.train_split)),
        chat_feature=str(payload.get("chat_feature", reference.chat_feature)),
        prompt_feature=str(payload.get("prompt_feature", reference.prompt_feature)),
        completion_feature=str(payload.get("completion_feature", reference.completion_feature)),
        text_feature=str(payload.get("text_feature", reference.text_feature)),
        valid_split=str(payload.get("hf_valid_split", reference.valid_split)),
        chosen_feature=str(payload.get("chosen_feature", reference.chosen_feature)),
        rejected_feature=str(payload.get("rejected_feature", reference.rejected_feature)),
    )


def _resolve_hf_dataset_name(
    reference: HFDatasetReference,
    fetcher: HFDatasetFetcher,
) -> str:
    payload = fetcher(
        "splits",
        {
            "dataset": reference.dataset_path,
            "revision": reference.dataset_revision,
        },
    )
    splits = payload.get("splits")
    if not isinstance(splits, list) or not splits:
        raise ModelOperationError(
            code="hf_dataset_fetch_failed",
            message="Hugging Face dataset splits metadata is unavailable.",
            details={"hf_dataset_path": reference.dataset_path},
        )

    for item in splits:
        if not isinstance(item, dict):
            continue
        if str(item.get("split", "")) == reference.train_split:
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
        message="Unable to resolve a Hugging Face dataset configuration for training.",
        details={"hf_dataset_path": reference.dataset_path},
    )


def _fetch_hf_dataset_rows(
    reference: HFDatasetReference,
    fetcher: HFDatasetFetcher,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    page_size = 100
    while True:
        payload = fetcher(
            "rows",
            {
                "dataset": reference.dataset_path,
                "config": reference.dataset_name,
                "split": reference.train_split,
                "offset": str(offset),
                "length": str(page_size),
                "revision": reference.dataset_revision,
            },
        )
        raw_rows = payload.get("rows")
        if not isinstance(raw_rows, list):
            raise ModelOperationError(
                code="hf_dataset_fetch_failed",
                message="Hugging Face dataset rows payload is malformed.",
                details={"hf_dataset_path": reference.dataset_path},
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


def _infer_hf_dataset_format(reference: HFDatasetReference, rows: list[dict[str, Any]]) -> str:
    if reference.chat_feature:
        return "chat_messages"
    if reference.chosen_feature or reference.rejected_feature:
        return "preference_pair"
    if reference.prompt_feature or reference.completion_feature:
        return "prompt_completion"
    if reference.text_feature:
        return "text_completion"

    sample = rows[0]
    if isinstance(sample.get("messages"), list):
        return "chat_messages"
    if "prompt" in sample and "chosen" in sample and "rejected" in sample:
        return "preference_pair"
    if "prompt" in sample and "completion" in sample:
        return "prompt_completion"
    if "text" in sample:
        return "text_completion"
    raise ModelOperationError(
        code="hf_dataset_fetch_failed",
        message="Unable to infer a supported training format from the Hugging Face dataset row schema.",
        details={"hf_dataset_path": reference.dataset_path},
    )


def _map_hf_row_to_training_sample(
    row: dict[str, Any],
    format_name: str,
    reference: HFDatasetReference,
) -> dict[str, Any]:
    if format_name == "chat_messages":
        field = reference.chat_feature or "messages"
        messages = row.get(field)
        if not isinstance(messages, list):
            raise ModelOperationError(
                code="hf_dataset_fetch_failed",
                message="Hugging Face dataset chat rows must provide a messages list.",
                details={"hf_dataset_path": reference.dataset_path, "chat_feature": field},
            )
        return {"messages": messages}

    if format_name == "prompt_completion":
        prompt_field = reference.prompt_feature or "prompt"
        completion_field = reference.completion_feature or "completion"
        if prompt_field not in row or completion_field not in row:
            raise ModelOperationError(
                code="hf_dataset_fetch_failed",
                message="Hugging Face dataset prompt_completion rows are missing configured columns.",
                details={
                    "hf_dataset_path": reference.dataset_path,
                    "prompt_feature": prompt_field,
                    "completion_feature": completion_field,
                },
            )
        return {
            "prompt": row[prompt_field],
            "completion": row[completion_field],
        }

    if format_name == "preference_pair":
        prompt_field = reference.prompt_feature or "prompt"
        chosen_field = reference.chosen_feature or "chosen"
        rejected_field = reference.rejected_feature or "rejected"
        if prompt_field not in row or chosen_field not in row or rejected_field not in row:
            raise ModelOperationError(
                code="hf_dataset_fetch_failed",
                message="Hugging Face dataset preference_pair rows are missing configured columns.",
                details={
                    "hf_dataset_path": reference.dataset_path,
                    "prompt_feature": prompt_field,
                    "chosen_feature": chosen_field,
                    "rejected_feature": rejected_field,
                },
            )
        return {
            "prompt": row[prompt_field],
            "chosen": row[chosen_field],
            "rejected": row[rejected_field],
        }

    text_field = reference.text_feature or "text"
    if text_field not in row:
        raise ModelOperationError(
            code="hf_dataset_fetch_failed",
            message="Hugging Face dataset text rows are missing the configured text column.",
            details={"hf_dataset_path": reference.dataset_path, "text_feature": text_field},
        )
    return {"text": row[text_field]}


def _hf_dataset_uri(reference: HFDatasetReference) -> str:
    uri = (
        f"hf://{reference.dataset_path}"
        f"?config={reference.dataset_name}&split={reference.train_split}"
    )
    if reference.valid_split:
        uri += f"&valid_split={reference.valid_split}"
    uri += f"&revision={reference.dataset_revision}"
    return uri


def _hf_materialization_cache_key(reference: HFDatasetReference) -> str:
    digest = hashlib.sha256()
    digest.update(
        json.dumps(
            {
                "dataset_path": reference.dataset_path,
                "dataset_name": reference.dataset_name,
                "dataset_revision": reference.dataset_revision,
                "train_split": reference.train_split,
                "chat_feature": reference.chat_feature,
                "prompt_feature": reference.prompt_feature,
                "completion_feature": reference.completion_feature,
                "text_feature": reference.text_feature,
                "chosen_feature": reference.chosen_feature,
                "rejected_feature": reference.rejected_feature,
                "valid_split": reference.valid_split,
            },
            sort_keys=True,
        ).encode("utf-8")
    )
    return digest.hexdigest()[:16]


def _truncate_text(value: str, max_characters_per_sample: int) -> str:
    if max_characters_per_sample > 0:
        return value[:max_characters_per_sample]
    return value


def _resolve_dataset_build_source(
    request_ext: dict[str, str],
    *,
    jobs_root: Path,
    hf_dataset_fetcher: HFDatasetFetcher | None,
    sample_limit: int,
) -> dict[str, Any]:
    explicit_source_kind = request_ext.get("dataset_source_kind", "").strip()
    if explicit_source_kind:
        source_kind = explicit_source_kind
    elif request_ext.get("hf_dataset_path", "").strip():
        source_kind = "hf_dataset"
    else:
        source_kind = "local_path"

    if source_kind == "hf_dataset":
        resolved = resolve_training_dataset_package(
            {**request_ext, "dataset_source_kind": "hf_dataset"},
            jobs_root=jobs_root,
            hf_dataset_fetcher=hf_dataset_fetcher,
            sample_limit=sample_limit,
        )
        template = request_ext.get("template", "").strip() or "source_schema"
        return {
            "dataset_id": request_ext.get("dataset_id", "").strip() or resolved.package.dataset_id,
            "format": resolved.package.format,
            "version": resolved.package.version,
            "source_kind": "hf_dataset",
            "source_uri": resolved.dataset_uri,
            "source_manifest_path": str(resolved.package.manifest_path),
            "source_samples_path": str(resolved.package.samples_path),
            "samples": resolved.package.normalized_samples,
            "validation_samples": resolved.package.normalized_validation_samples,
            "response_only_supported": resolved.package.response_only_supported,
            "conversion_template": template,
            "hf_metadata": {
                "hf_dataset_path": resolved.hf_reference.dataset_path if resolved.hf_reference else "",
                "hf_dataset_name": resolved.hf_reference.dataset_name if resolved.hf_reference else "",
                "hf_dataset_revision": resolved.hf_reference.dataset_revision if resolved.hf_reference else "",
                "hf_train_split": resolved.hf_reference.train_split if resolved.hf_reference else "",
                "hf_valid_split": resolved.hf_reference.valid_split if resolved.hf_reference else "",
                "chosen_feature": resolved.hf_reference.chosen_feature if resolved.hf_reference else "",
                "rejected_feature": resolved.hf_reference.rejected_feature if resolved.hf_reference else "",
            },
        }

    dataset_uri = request_ext.get("dataset_uri", "").strip()
    if not dataset_uri:
        raise ModelOperationError(
            code="invalid_dataset_source",
            message="Dataset builder requires dataset_uri or hf_dataset_path.",
        )

    source_path = Path(dataset_uri).expanduser().resolve()
    if source_path.is_dir():
        package = load_training_dataset_package(
            str(source_path),
            sample_limit=sample_limit,
        )
        template = request_ext.get("template", "").strip() or "existing_package"
        return {
            "dataset_id": request_ext.get("dataset_id", "").strip() or package.dataset_id,
            "format": package.format,
            "version": package.version,
            "source_kind": "local_package",
            "source_uri": str(source_path),
            "source_manifest_path": str(package.manifest_path),
            "source_samples_path": str(package.samples_path),
            "samples": package.normalized_samples,
            "validation_samples": package.normalized_validation_samples,
            "response_only_supported": package.response_only_supported,
            "conversion_template": template,
            "hf_metadata": {},
        }

    if source_path.is_file() is False:
        raise ModelOperationError(
            code="invalid_dataset_source",
            message="Local dataset source path was not found.",
            details={"dataset_uri": dataset_uri},
        )

    normalized_samples, format_name, resolved_template = _resolve_local_training_samples(
        source_path,
        template=request_ext.get("template", "").strip() or "auto",
        sample_limit=sample_limit,
    )
    dataset_id = request_ext.get("dataset_id", "").strip() or source_path.stem
    return {
        "dataset_id": dataset_id,
        "format": format_name,
        "version": "1",
        "source_kind": "local_path",
        "source_uri": str(source_path),
        "source_manifest_path": "",
        "source_samples_path": str(source_path),
        "samples": normalized_samples,
        "validation_samples": [],
        "response_only_supported": format_name in {"chat_messages", "prompt_completion"},
        "conversion_template": resolved_template,
        "hf_metadata": {},
    }


def _iter_local_jsonl_rows(path: Path, *, sample_limit: int) -> Iterable[dict[str, Any]]:
    yielded = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ModelOperationError(
                    code="invalid_dataset_source",
                    message="Local dataset source contains invalid JSONL rows.",
                    details={"line": str(line_number)},
                ) from exc
            if not isinstance(payload, dict):
                raise ModelOperationError(
                    code="invalid_dataset_source",
                    message="Local dataset rows must be JSON objects.",
                    details={"line": str(line_number)},
                )
            yield payload
            yielded += 1
            if sample_limit > 0 and yielded >= sample_limit:
                break


def _read_local_jsonl_rows(path: Path, *, sample_limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for payload in _iter_local_jsonl_rows(path, sample_limit=sample_limit):
        rows.append(payload)
    if not rows:
        raise ModelOperationError(
            code="invalid_dataset_source",
            message="Local dataset source did not contain any usable rows.",
            details={"dataset_uri": str(path)},
        )
    return rows


def _resolve_local_conversion_template(template: str, sample_row: dict[str, Any]) -> str:
    if template and template != "auto":
        if template in {
            "chat_messages",
            "prompt_completion",
            "text_completion",
            "preference_pair",
            "prompt_candidate",
            "reward_scored",
            "calibration",
            "alpaca",
            "sharegpt",
        }:
            return template
        raise ModelOperationError(
            code="invalid_dataset_source",
            message=f"Unsupported dataset conversion template: {template}",
        )

    if isinstance(sample_row.get("messages"), list):
        return "chat_messages"
    if "prompt" in sample_row and "candidates" in sample_row:
        return "prompt_candidate"
    if "prompt" in sample_row and "response" in sample_row and "reward_score" in sample_row:
        return "reward_scored"
    if "prompt" in sample_row and "chosen" in sample_row and "rejected" in sample_row:
        return "preference_pair"
    if "prompt" in sample_row and "completion" in sample_row:
        return "prompt_completion"
    if "text" in sample_row:
        return "text_completion"
    if "instruction" in sample_row and ("output" in sample_row or "response" in sample_row):
        return "alpaca"
    if isinstance(sample_row.get("conversations"), list) or isinstance(sample_row.get("conversation"), list):
        return "sharegpt"
    raise ModelOperationError(
        code="invalid_dataset_source",
        message="Unable to infer a supported dataset conversion template from the local source row schema.",
    )


def _local_conversion_format(template: str) -> str:
    if template == "chat_messages" or template == "sharegpt":
        return "chat_messages"
    if template == "prompt_completion" or template == "alpaca":
        return "prompt_completion"
    if template == "text_completion":
        return "text_completion"
    if template == "preference_pair":
        return "preference_pair"
    if template == "prompt_candidate":
        return "prompt_candidate"
    if template == "reward_scored":
        return "reward_scored"
    if template == "calibration":
        return "calibration"
    raise ModelOperationError(
        code="invalid_dataset_source",
        message=f"Unsupported dataset conversion template: {template}",
    )


def _convert_local_row(
    row: dict[str, Any],
    template: str,
) -> dict[str, Any]:
    if template == "chat_messages":
        return {"messages": row.get("messages")}
    if template == "prompt_completion":
        return {
            "prompt": row.get("prompt"),
            "completion": row.get("completion"),
        }
    if template == "text_completion":
        return {"text": row.get("text")}
    if template == "preference_pair":
        return {
            "prompt": row.get("prompt"),
            "chosen": row.get("chosen"),
            "rejected": row.get("rejected"),
        }
    if template == "prompt_candidate":
        return {
            "prompt": row.get("prompt"),
            "candidates": row.get("candidates"),
        }
    if template == "reward_scored":
        return {
            "prompt": row.get("prompt"),
            "response": row.get("response"),
            "reward_score": row.get("reward_score"),
        }
    if template == "calibration":
        return {"text": row.get("text")}
    if template == "alpaca":
        instruction = str(row.get("instruction", "")).strip()
        input_text = str(row.get("input", "")).strip()
        completion = str(row.get("output", row.get("response", ""))).strip()
        prompt = instruction
        if input_text:
            prompt = f"{instruction}\n\nInput:\n{input_text}"
        return {"prompt": prompt, "completion": completion}
    if template == "sharegpt":
        role_map = {
            "system": "system",
            "human": "user",
            "user": "user",
            "gpt": "assistant",
            "assistant": "assistant",
            "tool": "tool",
        }
        raw_conversations = row.get("conversations", row.get("conversation"))
        if not isinstance(raw_conversations, list):
            raise ModelOperationError(
                code="invalid_dataset_source",
                message="sharegpt conversion requires a conversations array.",
            )
        messages: list[dict[str, str]] = []
        for turn_index, turn in enumerate(raw_conversations):
            if not isinstance(turn, dict):
                raise ModelOperationError(
                    code="invalid_dataset_source",
                    message="sharegpt conversations must contain JSON object turns.",
                    details={"message_index": str(turn_index)},
                )
            raw_role = str(turn.get("from", turn.get("role", ""))).strip().lower()
            role = role_map.get(raw_role, "")
            if not role:
                raise ModelOperationError(
                    code="invalid_dataset_source",
                    message="sharegpt conversion encountered an unsupported role.",
                    details={"role": raw_role or "unknown"},
                )
            messages.append({"role": role, "content": turn.get("value", turn.get("content", ""))})
        return {"messages": messages}
    raise ModelOperationError(
        code="invalid_dataset_source",
        message=f"Unsupported dataset conversion template: {template}",
    )


def _resolve_local_training_samples(
    path: Path,
    *,
    template: str,
    sample_limit: int,
) -> tuple[list[dict[str, Any]], str, str]:
    row_iterator = iter(_iter_local_jsonl_rows(path, sample_limit=sample_limit))
    first_row = next(row_iterator, None)
    if first_row is None:
        raise ModelOperationError(
            code="invalid_dataset_source",
            message="Local dataset source did not contain any usable rows.",
            details={"dataset_uri": str(path)},
        )
    resolved_template = _resolve_local_conversion_template(template, first_row)
    format_name = _local_conversion_format(resolved_template)
    normalized_samples = [
        _normalize_sample(
            _convert_local_row(row, resolved_template),
            format_name=format_name,
            max_characters_per_sample=0,
        )
        for row in chain((first_row,), row_iterator)
    ]
    return normalized_samples, format_name, resolved_template


def _convert_local_rows(
    rows: list[dict[str, Any]],
    template: str,
) -> tuple[str, list[dict[str, Any]]]:
    format_name = _local_conversion_format(template)
    return format_name, [_convert_local_row(row, template) for row in rows]


def _deterministic_validation_split(
    samples: list[dict[str, Any]],
    validation_ratio: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(samples) < 2:
        raise ModelOperationError(
            code="invalid_dataset_source",
            message="Automatic validation split requires at least two samples.",
        )

    validation_count = int(round(len(samples) * validation_ratio))
    validation_count = max(1, min(len(samples) - 1, validation_count))
    ranked = sorted(
        (
            _canonical_sample_digest(sample),
            index,
        )
        for index, sample in enumerate(samples)
    )
    validation_indices = {index for _, index in ranked[:validation_count]}
    train_samples = [sample for index, sample in enumerate(samples) if index not in validation_indices]
    validation_samples = [sample for index, sample in enumerate(samples) if index in validation_indices]
    return train_samples, validation_samples


def _build_quality_report(samples: Iterable[dict[str, Any]]) -> dict[str, Any]:
    quality, _ = _build_quality_and_token_stats(samples, "")
    return quality


def _build_quality_and_token_stats(
    samples: Iterable[dict[str, Any]],
    format_name: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    seen: set[object] = set()
    duplicate_indices: list[int] = []
    dirty_samples: list[dict[str, Any]] = []
    duplicate_count = 0
    dirty_count = 0
    prompt_tokens: list[int] = []
    completion_tokens: list[int] = []
    total_tokens: list[int] = []
    sample_count = 0
    is_prompt_completion = format_name == "prompt_completion"
    prompt_tokens_append = prompt_tokens.append
    completion_tokens_append = completion_tokens.append
    total_tokens_append = total_tokens.append
    duplicate_indices_append = duplicate_indices.append
    dirty_samples_append = dirty_samples.append
    canonical_sample_digest = _canonical_sample_digest
    prompt_completion_duplicate_key = _prompt_completion_duplicate_key
    dirty_sample_reasons = (
        _prompt_completion_dirty_sample_reasons
        if is_prompt_completion
        else _dirty_sample_reasons
    )
    sample_token_counts = _sample_token_counts
    whitespace_token_count = _whitespace_token_count
    quality_report_sample_limit = _QUALITY_REPORT_SAMPLE_LIMIT
    for index, sample in enumerate(samples):
        sample_count += 1
        if is_prompt_completion:
            sample_identity = prompt_completion_duplicate_key(sample)
        else:
            sample_identity = canonical_sample_digest(sample)
        if sample_identity in seen:
            duplicate_count += 1
            if len(duplicate_indices) < quality_report_sample_limit:
                duplicate_indices_append(index)
        else:
            seen.add(sample_identity)
        reasons = dirty_sample_reasons(sample)
        if reasons:
            dirty_count += 1
            if len(dirty_samples) < quality_report_sample_limit:
                dirty_samples_append({"index": index, "reasons": reasons})
        if is_prompt_completion:
            prompt_count = whitespace_token_count(str(sample.get("prompt", "")))
            completion_count = whitespace_token_count(str(sample.get("completion", "")))
        else:
            prompt_count, completion_count = sample_token_counts(sample, format_name)
        prompt_tokens_append(prompt_count)
        completion_tokens_append(completion_count)
        total_tokens_append(prompt_count + completion_count)

    finalized_prompt_summary = _summarize_token_values(prompt_tokens, sort_in_place=True)
    finalized_completion_summary = _summarize_token_values(completion_tokens, sort_in_place=True)
    finalized_total_summary = _summarize_token_values(total_tokens, sort_in_place=True)

    return (
        {
            "duplicate_count": duplicate_count,
            "duplicate_sample_indices": duplicate_indices,
            "dirty_count": dirty_count,
            "dirty_samples": dirty_samples,
        },
        {
            "estimator": "whitespace_v1",
            "sample_count": sample_count,
            "prompt_tokens_mean": finalized_prompt_summary["mean"],
            "prompt_tokens_p50": finalized_prompt_summary["p50"],
            "prompt_tokens_p95": finalized_prompt_summary["p95"],
            "prompt_tokens_max": finalized_prompt_summary["max"],
            "completion_tokens_mean": finalized_completion_summary["mean"],
            "completion_tokens_p50": finalized_completion_summary["p50"],
            "completion_tokens_p95": finalized_completion_summary["p95"],
            "completion_tokens_max": finalized_completion_summary["max"],
            "total_tokens_mean": finalized_total_summary["mean"],
            "total_tokens_p50": finalized_total_summary["p50"],
            "total_tokens_p95": finalized_total_summary["p95"],
            "total_tokens_max": finalized_total_summary["max"],
        },
    )


def _build_token_stats(samples: Iterable[dict[str, Any]], format_name: str) -> dict[str, Any]:
    return _collect_token_stats(samples, format_name)


def _collect_token_stats(samples: Iterable[dict[str, Any]], format_name: str) -> dict[str, Any]:
    prompt_tokens: list[int] = []
    completion_tokens: list[int] = []
    total_tokens: list[int] = []
    sample_count = 0
    prompt_token_sum: int | None = None
    completion_token_sum: int | None = None
    total_token_sum: int | None = None
    if format_name == "prompt_completion":
        (
            sample_count,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            prompt_token_sum,
            completion_token_sum,
            total_token_sum,
        ) = _collect_prompt_completion_token_counts(samples)
    else:
        prompt_tokens_append = prompt_tokens.append
        completion_tokens_append = completion_tokens.append
        total_tokens_append = total_tokens.append
        sample_token_counts = _sample_token_counts
        for sample in samples:
            sample_count += 1
            prompt_count, completion_count = sample_token_counts(sample, format_name)
            prompt_tokens_append(prompt_count)
            completion_tokens_append(completion_count)
            total_tokens_append(prompt_count + completion_count)

    prompt_summary = _summarize_token_values(prompt_tokens, total=prompt_token_sum, sort_in_place=True)
    completion_summary = _summarize_token_values(completion_tokens, total=completion_token_sum, sort_in_place=True)
    total_summary = _summarize_token_values(total_tokens, total=total_token_sum, sort_in_place=True)

    return {
        "estimator": "whitespace_v1",
        "sample_count": sample_count,
        "prompt_tokens_mean": prompt_summary["mean"],
        "prompt_tokens_p50": prompt_summary["p50"],
        "prompt_tokens_p95": prompt_summary["p95"],
        "prompt_tokens_max": prompt_summary["max"],
        "completion_tokens_mean": completion_summary["mean"],
        "completion_tokens_p50": completion_summary["p50"],
        "completion_tokens_p95": completion_summary["p95"],
        "completion_tokens_max": completion_summary["max"],
        "total_tokens_mean": total_summary["mean"],
        "total_tokens_p50": total_summary["p50"],
        "total_tokens_p95": total_summary["p95"],
        "total_tokens_max": total_summary["max"],
    }


def _collect_prompt_completion_token_counts(
    samples: Iterable[dict[str, Any]],
) -> tuple[int, list[int], list[int], list[int], int, int, int]:
    prompt_tokens: list[int] = []
    completion_tokens: list[int] = []
    total_tokens: list[int] = []
    prompt_tokens_append = prompt_tokens.append
    completion_tokens_append = completion_tokens.append
    total_tokens_append = total_tokens.append
    sample_count = 0
    prompt_token_sum = 0
    completion_token_sum = 0
    total_token_sum = 0

    for sample in samples:
        sample_count += 1
        prompt_count = len(str(sample.get("prompt", "")).split())
        completion_count = len(str(sample.get("completion", "")).split())
        total_count = prompt_count + completion_count
        prompt_token_sum += prompt_count
        completion_token_sum += completion_count
        total_token_sum += total_count
        prompt_tokens_append(prompt_count)
        completion_tokens_append(completion_count)
        total_tokens_append(total_count)

    return (
        sample_count,
        prompt_tokens,
        completion_tokens,
        total_tokens,
        prompt_token_sum,
        completion_token_sum,
        total_token_sum,
    )


def _sample_token_counts(sample: dict[str, Any], format_name: str) -> tuple[int, int]:
    if format_name == "chat_messages":
        messages = sample.get("messages", [])
        if not isinstance(messages, list) or not messages:
            return 0, 0
        prompt_token_count = sum(
            _whitespace_token_count(f"{message.get('role', '')}: {message.get('content', '')}")
            for message in messages[:-1]
            if isinstance(message, dict)
        )
        last_message = messages[-1] if isinstance(messages[-1], dict) else {}
        completion_text = str(last_message.get("content", ""))
        return prompt_token_count, _whitespace_token_count(completion_text)

    if format_name == "prompt_completion":
        return (
            _whitespace_token_count(str(sample.get("prompt", ""))),
            _whitespace_token_count(str(sample.get("completion", ""))),
        )

    if format_name == "preference_pair":
        return (
            _whitespace_token_count(str(sample.get("prompt", ""))),
            _whitespace_token_count(
                f"{sample.get('chosen', '')} {sample.get('rejected', '')}"
            ),
        )

    if format_name == "prompt_candidate":
        candidates = sample.get("candidates", [])
        candidate_text = ""
        if isinstance(candidates, list):
            candidate_text = " ".join(
                str(candidate.get("text", "") if isinstance(candidate, dict) else candidate)
                for candidate in candidates
            )
        return (
            _whitespace_token_count(str(sample.get("prompt", ""))),
            _whitespace_token_count(candidate_text),
        )

    if format_name == "reward_scored":
        return (
            _whitespace_token_count(str(sample.get("prompt", ""))),
            _whitespace_token_count(str(sample.get("response", ""))),
        )

    return 0, _whitespace_token_count(str(sample.get("text", "")))


def _dirty_sample_reasons(sample: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for text in _sample_text_segments(sample):
        if _contains_problematic_control_characters(text):
            reasons.append("control_characters")
            break

    if "prompt" in sample and "completion" in sample:
        prompt = str(sample.get("prompt", "")).strip()
        completion = str(sample.get("completion", "")).strip()
        if prompt and completion and prompt == completion:
            reasons.append("duplicate_prompt_completion")
    if "prompt" in sample and "chosen" in sample and "rejected" in sample:
        chosen = str(sample.get("chosen", "")).strip()
        rejected = str(sample.get("rejected", "")).strip()
        if chosen and rejected and chosen == rejected:
            reasons.append("duplicate_preference_pair")

    if "messages" in sample:
        messages = sample.get("messages")
        if isinstance(messages, list) and len(messages) >= 2:
            previous = messages[-2] if isinstance(messages[-2], dict) else {}
            last = messages[-1] if isinstance(messages[-1], dict) else {}
            prev_content = str(previous.get("content", "")).strip()
            last_content = str(last.get("content", "")).strip()
            if prev_content and prev_content == last_content:
                reasons.append("echo_response")

    unique_reasons: list[str] = []
    for reason in reasons:
        if reason not in unique_reasons:
            unique_reasons.append(reason)
    return unique_reasons


def _prompt_completion_dirty_sample_reasons(sample: dict[str, Any]) -> list[str]:
    prompt = str(sample.get("prompt", ""))
    completion = str(sample.get("completion", ""))
    has_control_characters = _contains_problematic_control_characters(
        prompt
    ) or _contains_problematic_control_characters(completion)
    stripped_prompt = prompt.strip()
    stripped_completion = completion.strip()
    has_duplicate_prompt_completion = bool(
        stripped_prompt and stripped_completion and stripped_prompt == stripped_completion
    )
    if has_control_characters:
        if has_duplicate_prompt_completion:
            return ["control_characters", "duplicate_prompt_completion"]
        return ["control_characters"]
    if has_duplicate_prompt_completion:
        return ["duplicate_prompt_completion"]
    return []


def _sample_text_segments(sample: dict[str, Any]) -> list[str]:
    if "messages" in sample:
        messages = sample.get("messages", [])
        if isinstance(messages, list):
            return [
                str(message.get("content", ""))
                for message in messages
                if isinstance(message, dict)
            ]
    if "prompt" in sample and ("chosen" in sample or "rejected" in sample):
        return [
            str(sample.get("prompt", "")),
            str(sample.get("chosen", "")),
            str(sample.get("rejected", "")),
        ]
    if "prompt" in sample and "candidates" in sample:
        segments = [str(sample.get("prompt", ""))]
        candidates = sample.get("candidates")
        if isinstance(candidates, list):
            segments.extend(
                str(candidate.get("text", "") if isinstance(candidate, dict) else candidate)
                for candidate in candidates
            )
        return segments
    if "prompt" in sample and "response" in sample:
        return [str(sample.get("prompt", "")), str(sample.get("response", ""))]
    if "prompt" in sample or "completion" in sample:
        return [str(sample.get("prompt", "")), str(sample.get("completion", ""))]
    return [str(sample.get("text", ""))]


def _contains_problematic_control_characters(text: str) -> bool:
    return any(ord(character) < 32 and character not in _ALLOWED_CONTROL_CHARACTERS for character in text)


def _prompt_completion_duplicate_key(sample: dict[str, Any]) -> tuple[str, str] | bytes:
    if len(sample) == 2:
        prompt = sample.get("prompt")
        completion = sample.get("completion")
        if isinstance(prompt, str) and isinstance(completion, str):
            return prompt, completion
    return _canonical_sample_digest(sample)


def _canonical_sample_key(sample: dict[str, Any]) -> str:
    return json.dumps(sample, sort_keys=True, ensure_ascii=False)


def _canonical_sample_digest(sample: dict[str, Any]) -> bytes:
    return hashlib.sha256(_canonical_sample_key(sample).encode("utf-8")).digest()


def _whitespace_token_count(text: str) -> int:
    return len(text.split())


def _mean_value(values: list[int]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 3)


def _summarize_token_values(
    values: list[int], *, total: int | None = None, sort_in_place: bool = False
) -> dict[str, float | int]:
    ordered = values if sort_in_place else list(values)
    ordered.sort()
    return {
        "mean": _mean_value_from_total(total if total is not None else sum(values), len(values)),
        "p50": _sorted_percentile_value(ordered, 0.50),
        "p95": _sorted_percentile_value(ordered, 0.95),
        "max": ordered[-1] if ordered else 0,
    }


def _mean_value_from_total(total: int, count: int) -> float:
    if count == 0:
        return 0.0
    return round(total / count, 3)


def _sorted_percentile_value(ordered_values: list[int], pct: float) -> int:
    if not ordered_values:
        return 0
    index = int((len(ordered_values) - 1) * pct)
    return ordered_values[index]


def _percentile_value(values: list[int], pct: float) -> int:
    return _sorted_percentile_value(sorted(values), pct)


def _truthy(raw_value: str) -> bool:
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _int_ext_value(
    raw_value: str,
    *,
    default: int,
    minimum: int,
    field_name: str,
) -> int:
    value = raw_value.strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ModelOperationError(
            code="invalid_dataset_source",
            message=f"{field_name} must be an integer.",
        ) from exc
    if parsed < minimum:
        raise ModelOperationError(
            code="invalid_dataset_source",
            message=f"{field_name} must be >= {minimum}.",
        )
    return parsed


def _float_ext_value(
    raw_value: str,
    *,
    default: float,
    minimum: float,
    maximum: float,
    field_name: str,
) -> float:
    value = raw_value.strip()
    if not value:
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ModelOperationError(
            code="invalid_dataset_source",
            message=f"{field_name} must be a number.",
        ) from exc
    if parsed < minimum or parsed > maximum:
        raise ModelOperationError(
            code="invalid_dataset_source",
            message=f"{field_name} must be between {minimum} and {maximum}.",
        )
    return parsed


def _cleanup_dataset_package_files(package_path: Path) -> None:
    for candidate in ("manifest.json", "samples.jsonl", "valid.jsonl"):
        target = package_path / candidate
        if target.exists():
            target.unlink()
