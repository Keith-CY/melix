from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import math
from pathlib import Path
import time
from typing import Any


ADAPTER_PROVENANCE_SCHEMA_VERSION = "melix.lora_adapter_provenance.v1"
ADAPTER_OPERATOR_NOTES_SCHEMA_VERSION = "melix.lora_adapter_operator_notes.v1"
ADAPTER_EXPORT_ELIGIBILITY_SCHEMA_VERSION = "melix.lora_adapter_export_eligibility.v1"
ADAPTER_PROVENANCE_MANIFEST_NAME = "train_lora.adapter.provenance.json"
ADAPTER_OPERATOR_NOTES_NAME = "train_lora.adapter.notes.json"


def default_adapter_provenance_manifest_path(adapter_manifest_path: str | Path) -> Path:
    return Path(adapter_manifest_path).parent / ADAPTER_PROVENANCE_MANIFEST_NAME


def default_adapter_operator_notes_path(adapter_manifest_path: str | Path) -> Path:
    return Path(adapter_manifest_path).parent / ADAPTER_OPERATOR_NOTES_NAME


def write_adapter_provenance_artifacts(
    *,
    adapter_manifest: Mapping[str, Any],
    adapter_manifest_path: Path,
    now_unix_ms: int | None = None,
) -> dict[str, Any]:
    created_at_unix_ms = _int_value(
        adapter_manifest.get("created_at_unix_ms"),
        default=now_unix_ms or int(time.time() * 1000),
    )
    provenance_path = default_adapter_provenance_manifest_path(adapter_manifest_path)
    notes_path = default_adapter_operator_notes_path(adapter_manifest_path)

    note_started_at = time.perf_counter()
    notes_payload = ensure_adapter_operator_notes_file(
        notes_path=notes_path,
        adapter_manifest=adapter_manifest,
        provenance_manifest_path=provenance_path,
        now_unix_ms=created_at_unix_ms,
    )
    note_write_duration_ms = (time.perf_counter() - note_started_at) * 1000.0

    provenance = build_adapter_provenance_manifest(
        adapter_manifest=adapter_manifest,
        adapter_manifest_path=adapter_manifest_path,
        provenance_manifest_path=provenance_path,
        operator_notes_path=notes_path,
        operator_notes_payload=notes_payload,
        created_at_unix_ms=created_at_unix_ms,
    )

    provenance_started_at = time.perf_counter()
    provenance_path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(_json_safe(provenance), indent=2, allow_nan=False) + "\n"
    provenance_path.write_text(encoded, encoding="utf-8")
    provenance_write_duration_ms = (time.perf_counter() - provenance_started_at) * 1000.0

    return {
        "provenance": provenance,
        "provenance_path": provenance_path,
        "notes_path": notes_path,
        "metrics": {
            "adapter_provenance_manifest_write_duration_ms": provenance_write_duration_ms,
            "adapter_operator_notes_write_duration_ms": note_write_duration_ms,
            "adapter_provenance_loss_series_row_count": len(
                provenance["training"]["loss_series"]
            ),
            "adapter_provenance_manifest_bytes": len(encoded.encode("utf-8")),
        },
    }


def build_adapter_provenance_manifest(
    *,
    adapter_manifest: Mapping[str, Any],
    adapter_manifest_path: Path,
    provenance_manifest_path: Path,
    operator_notes_path: Path,
    operator_notes_payload: Mapping[str, Any] | None = None,
    created_at_unix_ms: int | None = None,
) -> dict[str, Any]:
    created_at = _int_value(
        adapter_manifest.get("created_at_unix_ms"),
        default=created_at_unix_ms or int(time.time() * 1000),
    )
    updated_at = _int_value(adapter_manifest.get("updated_at_unix_ms"), default=created_at)
    loss_series = build_loss_series(adapter_manifest)
    training_events = _mapping_value(adapter_manifest.get("training_log_events"))
    if not training_events:
        training_events = _mapping_value(adapter_manifest.get("training.log_events"))
    notes_payload = operator_notes_payload or {}
    note_count = _int_value(notes_payload.get("note_count"), default=0)

    return {
        "schema_version": ADAPTER_PROVENANCE_SCHEMA_VERSION,
        "adapter": {
            "job_id": _str_value(adapter_manifest.get("job_id")),
            "adapter_name": _str_value(adapter_manifest.get("adapter_name")),
            "experiment_group_id": _str_value(adapter_manifest.get("experiment_group_id")),
            "experiment_group_title": _str_value(adapter_manifest.get("experiment_group_title")),
            "artifact_kind": _str_value(adapter_manifest.get("artifact_kind")),
            "adapter_set_hash": _str_value(adapter_manifest.get("adapter_set_hash")),
            "adapter_manifest_path": str(adapter_manifest_path),
            "provenance_manifest_path": str(provenance_manifest_path),
            "output_dir": str(adapter_manifest_path.parent),
            "weights_path": _str_value(adapter_manifest.get("weights_path")),
            "adapter_config_path": _str_value(adapter_manifest.get("adapter_config_path")),
            "target_repo": _str_value(adapter_manifest.get("target_repo")),
            "checkpoint_count": _int_value(adapter_manifest.get("checkpoint_count")),
            "latest_checkpoint_path": _str_value(adapter_manifest.get("latest_checkpoint_path")),
            "checkpoint_step": _int_value(adapter_manifest.get("checkpoint_step")),
            "checkpoint_sort_key": _str_value(adapter_manifest.get("checkpoint_sort_key")),
            "selected_checkpoint_path": _str_value(
                adapter_manifest.get("selected_checkpoint_path")
            ),
            "selected_checkpoint_loss_source": _str_value(
                adapter_manifest.get("selected_checkpoint_loss_source")
            ),
            "resume_source_path": _str_value(adapter_manifest.get("resume_source_path")),
            "resume_source_job_id": _str_value(adapter_manifest.get("resume_source_job_id")),
            "resume_source_manifest_path": _str_value(adapter_manifest.get("resume_source_manifest_path")),
            "resume_ready": bool(adapter_manifest.get("resume_ready", False)),
        },
        "base_model": {
            "model_id": _str_value(adapter_manifest.get("source_model")),
            "model_kind": _str_value(adapter_manifest.get("source_model_kind")),
            "revision": _str_value(adapter_manifest.get("source_model_revision")),
            "model_path": _str_value(adapter_manifest.get("source_model_path")),
            "adapter_scope": _str_value(adapter_manifest.get("adapter_scope")),
            "training_surface": _str_value(adapter_manifest.get("training_surface")),
            "component_model_type": _str_value(adapter_manifest.get("component_model_type")),
            "component_family": _str_value(adapter_manifest.get("component_family")),
            "component_model_path": _str_value(adapter_manifest.get("component_model_path")),
            "quantization_mode": _str_value(adapter_manifest.get("quantization_mode")),
            "base_quantization_method": _str_value(adapter_manifest.get("base_quantization_method")),
            "quantized_base_detected": bool(adapter_manifest.get("quantized_base_detected", False)),
            "quantized_base_kind": _str_value(adapter_manifest.get("quantized_base_kind")),
            "quantization_profile_id": _str_value(adapter_manifest.get("quantization_profile_id")),
        },
        "dataset": {
            "uri": _str_value(adapter_manifest.get("dataset_uri")),
            "source_kind": _str_value(adapter_manifest.get("dataset_source_kind")),
            "dataset_id": _str_value(adapter_manifest.get("dataset_id")),
            "format": _str_value(adapter_manifest.get("dataset_format")),
            "trainer_format": _str_value(adapter_manifest.get("trainer_dataset_format")),
            "version": _str_value(adapter_manifest.get("dataset_version")),
            "sample_count": _int_value(adapter_manifest.get("dataset_sample_count")),
            "train_sample_count": _int_value(adapter_manifest.get("trainer_dataset_sample_count")),
            "validation_sample_count": _int_value(
                adapter_manifest.get("trainer_dataset_validation_sample_count"),
                adapter_manifest.get("validation_sample_count"),
            ),
            "source_manifest_path": _str_value(adapter_manifest.get("dataset_source_manifest_path")),
            "normalized_manifest_path": _str_value(adapter_manifest.get("normalized_dataset_manifest_path")),
        },
        "hyperparameters": {
            "preset_id": _str_value(adapter_manifest.get("preset_id")),
            "preset_title": _str_value(adapter_manifest.get("preset_title")),
            "training_mode": _str_value(adapter_manifest.get("training_mode")),
            "training_objective": _str_value(adapter_manifest.get("training_objective")),
            "adapter_algorithm": _str_value(adapter_manifest.get("adapter_algorithm")),
            "adapter_family": _str_value(adapter_manifest.get("adapter_family")),
            "rank": _int_value(adapter_manifest.get("rank")),
            "alpha": _float_value(adapter_manifest.get("alpha")),
            "dropout": _float_value(adapter_manifest.get("dropout")),
            "learning_rate": _float_value(
                adapter_manifest.get("learning_rate"),
                adapter_manifest.get("training.learning_rate_final"),
                adapter_manifest.get("learning_rate_final"),
            ),
            "learning_rate_final": _float_value(
                adapter_manifest.get("learning_rate_final"),
                adapter_manifest.get("training.learning_rate_final"),
            ),
            "batch_size": _int_value(adapter_manifest.get("batch_size")),
            "gradient_accumulation": _int_value(adapter_manifest.get("gradient_accumulation")),
            "effective_batch_size": _int_value(adapter_manifest.get("effective_batch_size")),
            "max_steps": _int_value(adapter_manifest.get("max_steps")),
            "iters": _int_value(adapter_manifest.get("iters")),
            "optimizer_steps": _int_value(adapter_manifest.get("optimizer_steps")),
            "max_seq_length": _int_value(adapter_manifest.get("max_seq_length")),
            "response_only": bool(adapter_manifest.get("response_only", False)),
            "gradient_checkpointing": bool(adapter_manifest.get("gradient_checkpointing", False)),
            "mask_prompt": bool(adapter_manifest.get("mask_prompt", False)),
            "target_modules": _list_value(adapter_manifest.get("target_modules")),
            "validation_strategy": _str_value(adapter_manifest.get("validation_strategy")),
        },
        "training": {
            "backend": _str_value(adapter_manifest.get("training_backend")),
            "status": _str_value(adapter_manifest.get("status", "completed")),
            "duration_ms": _float_value(
                adapter_manifest.get("training_duration_ms"),
                adapter_manifest.get("training.job_duration_ms"),
            ),
            "tokens_seen": _int_value(
                adapter_manifest.get("tokens_seen"),
                adapter_manifest.get("training.tokens_seen"),
            ),
            "examples_seen": _int_value(
                adapter_manifest.get("examples_seen"),
                adapter_manifest.get("training.examples_seen"),
            ),
            "tokens_per_second": _float_value(
                adapter_manifest.get("tokens_per_second"),
                adapter_manifest.get("training.tokens_per_second"),
            ),
            "peak_memory_gb": _float_value(
                adapter_manifest.get("peak_memory_gb"),
                adapter_manifest.get("training.peak_memory_gb"),
            ),
            "event_summary": dict(training_events),
            "event_preview_limit": _int_value(
                adapter_manifest.get("training_log_event_preview_limit"),
                adapter_manifest.get("training.log_event_preview_limit"),
            ),
            "loss_series": loss_series,
            "loss_series_row_count": len(loss_series),
        },
        "final_metrics": {
            "loss_final": _float_value(
                adapter_manifest.get("loss_final"),
                adapter_manifest.get("training.loss_final"),
            ),
            "loss_best": _float_value(
                adapter_manifest.get("loss_best"),
                adapter_manifest.get("training.loss_best"),
            ),
            "validation_loss_final": _float_value(training_events.get("final_validation_loss")),
            "validation_loss_best": _float_value(training_events.get("best_validation_loss")),
            "learning_rate_final": _float_value(
                adapter_manifest.get("learning_rate_final"),
                adapter_manifest.get("training.learning_rate_final"),
            ),
            "completion_loss": _float_value(adapter_manifest.get("completion_loss")),
            "round_trip_passed": bool(adapter_manifest.get("round_trip_passed", False)),
            "grad_norm": _float_value(adapter_manifest.get("grad_norm")),
        },
        "canary_receipts": {
            "merge_export_canary_result": _str_value(adapter_manifest.get("merge_export_canary_result")),
            "callback_api_drift_result": _str_value(adapter_manifest.get("callback_api_drift_result")),
            "source_eos_token": _str_value(adapter_manifest.get("source_eos_token")),
            "saved_eos_token": _str_value(adapter_manifest.get("saved_eos_token")),
            "base_config_present": bool(adapter_manifest.get("base_config_present", False)),
            "tokenizer_config_path": _str_value(adapter_manifest.get("tokenizer_config_path")),
            "processor_resume_mode": _str_value(adapter_manifest.get("processor_resume_mode")),
            "aux_modules_restored": bool(adapter_manifest.get("aux_modules_restored", False)),
        },
        "operator_notes": {
            "schema_version": ADAPTER_OPERATOR_NOTES_SCHEMA_VERSION,
            "path": str(operator_notes_path),
            "mutable": True,
            "note_count": note_count,
            "updated_at_unix_ms": _int_value(notes_payload.get("updated_at_unix_ms"), default=created_at),
        },
        "export_eligibility": compute_export_eligibility(adapter_manifest),
        "created_at_unix_ms": created_at,
        "updated_at_unix_ms": updated_at,
    }


def build_loss_series(adapter_manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = _sequence_value(adapter_manifest.get("training_log_event_preview"))
    if not rows:
        rows = _sequence_value(adapter_manifest.get("training.log_event_preview"))
    loss_series: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        loss = _float_value(row.get("loss"))
        validation_loss = _float_value(row.get("validation_loss"))
        if loss is None and validation_loss is None:
            continue
        projected: dict[str, Any] = {
            "event_type": _str_value(row.get("event_type")),
            "step": _optional_int_value(row.get("step")),
            "total_steps": _optional_int_value(row.get("total_steps")),
            "loss": loss,
            "validation_loss": validation_loss,
            "learning_rate": _float_value(row.get("learning_rate")),
            "tokens_seen": _optional_int_value(row.get("tokens_seen")),
            "examples_seen": _optional_int_value(row.get("examples_seen")),
            "duration_ms": _float_value(row.get("duration_ms")),
            "source": _str_value(row.get("source")),
            "line_number": _optional_int_value(row.get("line_number")),
        }
        loss_series.append(
            {
                key: value
                for key, value in projected.items()
                if value not in ("", None)
            }
        )
    return loss_series


def compute_export_eligibility(adapter_manifest: Mapping[str, Any]) -> dict[str, Any]:
    blocking_reasons: list[str] = []
    status = _str_value(adapter_manifest.get("status", "completed"))
    if status and status != "completed":
        blocking_reasons.append("training_not_completed")
    if not _str_value(adapter_manifest.get("weights_path")):
        blocking_reasons.append("missing_adapter_weights_path")
    if not _str_value(adapter_manifest.get("adapter_config_path")):
        blocking_reasons.append("missing_adapter_config_path")
    if not _str_value(adapter_manifest.get("adapter_set_hash")):
        blocking_reasons.append("missing_adapter_set_hash")
    if _non_empty_sequence(adapter_manifest.get("validation_errors")):
        blocking_reasons.append("validation_errors_present")

    runtime_reason = _str_value(adapter_manifest.get("runtime_unsupported_reason"))
    if runtime_reason:
        blocking_reasons.append(f"runtime_unsupported:{runtime_reason}")
    adapter_reason = _str_value(
        adapter_manifest.get("adapter_unsupported_reason"),
        adapter_manifest.get("unsupported_reason"),
    )
    if adapter_reason:
        blocking_reasons.append(f"adapter_unsupported:{adapter_reason}")

    merge_canary = _str_value(adapter_manifest.get("merge_export_canary_result"))
    if merge_canary.startswith("fail:"):
        for reason in merge_canary.removeprefix("fail:").split(","):
            normalized = reason.strip()
            if normalized:
                blocking_reasons.append(f"merge_export_canary:{normalized}")
    callback_drift = _str_value(adapter_manifest.get("callback_api_drift_result"))
    if callback_drift.startswith("fail:"):
        blocking_reasons.append(f"callback_api_drift:{callback_drift.removeprefix('fail:')}")

    unique_reasons = list(dict.fromkeys(blocking_reasons))
    eligible = not unique_reasons
    return {
        "schema_version": ADAPTER_EXPORT_ELIGIBILITY_SCHEMA_VERSION,
        "eligible": eligible,
        "state": "eligible" if eligible else "blocked",
        "blocking_reasons": unique_reasons,
        "computed_from_fields": [
            "status",
            "weights_path",
            "adapter_config_path",
            "adapter_set_hash",
            "validation_errors",
            "runtime_unsupported_reason",
            "adapter_unsupported_reason",
            "merge_export_canary_result",
            "callback_api_drift_result",
        ],
    }


def ensure_adapter_operator_notes_file(
    *,
    notes_path: Path,
    adapter_manifest: Mapping[str, Any],
    provenance_manifest_path: Path,
    now_unix_ms: int | None = None,
) -> dict[str, Any]:
    existing = load_operator_notes_payload(notes_path)
    if existing:
        return existing
    return write_adapter_operator_notes(
        notes_path=notes_path,
        notes=[],
        adapter_job_id=_str_value(adapter_manifest.get("job_id")),
        adapter_name=_str_value(adapter_manifest.get("adapter_name")),
        provenance_manifest_path=provenance_manifest_path,
        now_unix_ms=now_unix_ms,
    )


def write_adapter_operator_notes(
    *,
    notes_path: Path,
    notes: Sequence[Mapping[str, Any] | str],
    adapter_job_id: str = "",
    adapter_name: str = "",
    provenance_manifest_path: str | Path = "",
    now_unix_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = now_unix_ms or int(time.time() * 1000)
    existing = load_operator_notes_payload(notes_path)
    created_at = _int_value(existing.get("created_at_unix_ms"), default=now_ms) if existing else now_ms
    payload = {
        "schema_version": ADAPTER_OPERATOR_NOTES_SCHEMA_VERSION,
        "adapter_job_id": adapter_job_id or _str_value(existing.get("adapter_job_id") if existing else ""),
        "adapter_name": adapter_name or _str_value(existing.get("adapter_name") if existing else ""),
        "provenance_manifest_path": str(provenance_manifest_path)
        if provenance_manifest_path
        else _str_value(existing.get("provenance_manifest_path") if existing else ""),
        "notes": _normalize_notes(notes, now_unix_ms=now_ms),
        "note_count": 0,
        "created_at_unix_ms": created_at,
        "updated_at_unix_ms": now_ms,
    }
    payload["note_count"] = len(payload["notes"])
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    notes_path.write_text(json.dumps(_json_safe(payload), indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return payload


def load_operator_notes_payload(notes_path: str | Path) -> dict[str, Any]:
    payload = _load_json_mapping(Path(notes_path))
    if payload.get("schema_version") != ADAPTER_OPERATOR_NOTES_SCHEMA_VERSION:
        return {}
    notes = payload.get("notes")
    payload["note_count"] = len(notes) if isinstance(notes, list) else 0
    return payload


def load_adapter_provenance_payload(provenance_path: str | Path) -> dict[str, Any]:
    payload = _load_json_mapping(Path(provenance_path))
    if payload.get("schema_version") != ADAPTER_PROVENANCE_SCHEMA_VERSION:
        return {}
    return payload


def _normalize_notes(
    notes: Sequence[Mapping[str, Any] | str],
    *,
    now_unix_ms: int,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, note in enumerate(notes, start=1):
        if isinstance(note, Mapping):
            text = _str_value(note.get("text"))
            note_id = _str_value(note.get("id")) or f"note-{index}"
            author = _str_value(note.get("author"))
            created_at = _int_value(note.get("created_at_unix_ms"), default=now_unix_ms)
            updated_at = _int_value(note.get("updated_at_unix_ms"), default=created_at)
        else:
            text = _str_value(note)
            note_id = f"note-{index}"
            author = ""
            created_at = now_unix_ms
            updated_at = now_unix_ms
        if not text:
            continue
        row = {
            "id": note_id,
            "text": text,
            "author": author,
            "created_at_unix_ms": created_at,
            "updated_at_unix_ms": updated_at,
        }
        normalized.append({key: value for key, value in row.items() if value != ""})
    return normalized


def _load_json_mapping(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _mapping_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence_value(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


def _list_value(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _non_empty_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) and len(value) > 0


def _str_value(*raw_values: Any) -> str:
    for raw_value in raw_values:
        if raw_value is None:
            continue
        parsed = str(raw_value).strip()
        if parsed:
            return parsed
    return ""


def _int_value(*raw_values: Any, default: int = 0) -> int:
    for raw_value in raw_values:
        if raw_value is None or raw_value == "":
            continue
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            continue
    return default


def _optional_int_value(*raw_values: Any) -> int | None:
    for raw_value in raw_values:
        if raw_value is None or raw_value == "":
            continue
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            continue
    return None


def _float_value(*raw_values: Any) -> float | None:
    for raw_value in raw_values:
        if raw_value is None or raw_value == "":
            continue
        try:
            parsed = float(raw_value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(parsed):
            return parsed
    return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and math.isfinite(value) is False:
        return None
    return value
