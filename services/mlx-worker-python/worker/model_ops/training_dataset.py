from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worker.model_ops.errors import ModelOperationError

_SUPPORTED_FORMATS = {"chat_messages", "prompt_completion", "text_completion"}
_SUPPORTED_ROLES = {"system", "user", "assistant", "tool"}


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
    response_only_supported: bool


@dataclass(frozen=True)
class NormalizedDatasetSnapshot:
    dataset_dir: Path
    manifest_path: Path
    samples_path: Path
    train_path: Path
    sample_count: int
    format: str


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
        response_only_supported=format_name in {"chat_messages", "prompt_completion"},
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

    manifest_payload = {
        "schema_version": "melix.training_dataset_snapshot.v1",
        "dataset_id": dataset.dataset_id,
        "format": dataset.format,
        "sample_count": dataset.sample_count,
        "version": dataset.version,
        "source_manifest_path": str(dataset.manifest_path),
        "source_samples_path": str(dataset.samples_path),
        "response_only_supported": dataset.response_only_supported,
    }
    manifest_path.write_text(json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8")

    serialized_samples = [json.dumps(sample) for sample in dataset.normalized_samples]
    samples_path.write_text("\n".join(serialized_samples) + "\n", encoding="utf-8")
    train_path.write_text("\n".join(serialized_samples) + "\n", encoding="utf-8")

    return NormalizedDatasetSnapshot(
        dataset_dir=dataset_dir,
        manifest_path=manifest_path,
        samples_path=samples_path,
        train_path=train_path,
        sample_count=dataset.sample_count,
        format=dataset.format,
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


def _truncate_text(value: str, max_characters_per_sample: int) -> str:
    if max_characters_per_sample > 0:
        return value[:max_characters_per_sample]
    return value
