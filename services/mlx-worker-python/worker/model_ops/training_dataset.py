from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from dataclasses import replace
import os
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from worker.model_ops.errors import ModelOperationError

_SUPPORTED_FORMATS = {"chat_messages", "prompt_completion", "text_completion"}
_SUPPORTED_ROLES = {"system", "user", "assistant", "tool"}
_HF_DATASETS_SERVER_URL = "https://datasets-server.huggingface.co"

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


@dataclass(frozen=True)
class MaterializedTrainingDatasetPackage:
    package_path: Path
    cache_key: str
    cache_hit: bool
    dataset_uri: str
    reference: HFDatasetReference


@dataclass(frozen=True)
class ResolvedTrainingDatasetPackage:
    package: TrainingDatasetPackage
    source_kind: str
    dataset_uri: str
    materialized_package_path: Path
    cache_key: str
    cache_hit: bool
    hf_reference: HFDatasetReference | None


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
    with samples_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                sample = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ModelOperationError(
                    code="invalid_dataset_package",
                    message="Training dataset sample is not valid JSON.",
                    details={"line": str(line_number)},
                ) from exc

            normalized = _normalize_sample(
                sample,
                format_name=format_name,
                max_characters_per_sample=max_characters_per_sample,
            )
            normalized_samples.append(normalized)
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

    validation_samples_path = package_path / "valid.jsonl"
    normalized_validation_samples: list[dict[str, Any]] = []
    if validation_samples_path.is_file():
        with validation_samples_path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    sample = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ModelOperationError(
                        code="invalid_dataset_package",
                        message="Training dataset validation sample is not valid JSON.",
                        details={"line": str(line_number)},
                    ) from exc
                normalized_validation_samples.append(
                    _normalize_sample(
                        sample,
                        format_name=format_name,
                        max_characters_per_sample=max_characters_per_sample,
                    )
                )

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

    serialized_samples = [json.dumps(sample) for sample in dataset.normalized_samples]
    samples_path.write_text("\n".join(serialized_samples) + "\n", encoding="utf-8")
    train_path.write_text("\n".join(serialized_samples) + "\n", encoding="utf-8")
    if dataset.normalized_validation_samples:
        serialized_validation_samples = [
            json.dumps(sample)
            for sample in dataset.normalized_validation_samples
        ]
        valid_path.write_text(
            "\n".join(serialized_validation_samples) + "\n",
            encoding="utf-8",
        )
    else:
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
    }
    manifest_path.write_text(json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8")
    samples_path.write_text(
        "\n".join(json.dumps(sample) for sample in serialized_samples) + "\n",
        encoding="utf-8",
    )
    if serialized_validation_samples:
        (package_path / "valid.jsonl").write_text(
            "\n".join(json.dumps(sample) for sample in serialized_validation_samples) + "\n",
            encoding="utf-8",
        )
    return MaterializedTrainingDatasetPackage(
        package_path=package_path,
        cache_key=cache_key,
        cache_hit=False,
        dataset_uri=dataset_uri,
        reference=resolved_reference,
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
    if reference.prompt_feature or reference.completion_feature:
        return "prompt_completion"
    if reference.text_feature:
        return "text_completion"

    sample = rows[0]
    if isinstance(sample.get("messages"), list):
        return "chat_messages"
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
