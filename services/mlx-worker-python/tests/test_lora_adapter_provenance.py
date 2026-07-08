from __future__ import annotations

import json
from pathlib import Path

import pytest

from worker.productization.lora_adapter_provenance import (
    ADAPTER_OPERATOR_NOTES_SCHEMA_VERSION,
    ADAPTER_PROVENANCE_SCHEMA_VERSION,
    build_adapter_provenance_manifest,
    build_loss_series,
    compute_export_eligibility,
    default_adapter_operator_notes_path,
    default_adapter_provenance_manifest_path,
    load_adapter_provenance_payload,
    load_operator_notes_payload,
    write_adapter_operator_notes,
    write_adapter_provenance_artifacts,
)


def _manifest_payload(tmp_path: Path) -> dict[str, object]:
    return {
        "job_id": "model-ops-0001",
        "operation": "train_lora",
        "artifact_kind": "adapter",
        "adapter_name": "nightly-adapter",
        "experiment_group_id": "nightly-qwen",
        "experiment_group_title": "Nightly Qwen",
        "source_model": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
        "source_model_kind": "text",
        "source_model_revision": "main",
        "source_model_path": str(tmp_path / "base-model"),
        "dataset_uri": str(tmp_path / "dataset"),
        "dataset_id": "dataset-v1",
        "dataset_format": "chat_messages",
        "dataset_version": "2026-06-24",
        "trainer_dataset_sample_count": 12,
        "trainer_dataset_validation_sample_count": 3,
        "preset_id": "balanced",
        "preset_title": "Balanced",
        "training_mode": "lora",
        "adapter_algorithm": "lora",
        "rank": 8,
        "alpha": 16.0,
        "dropout": 0.05,
        "learning_rate_final": 0.0001,
        "batch_size": 2,
        "gradient_accumulation": 4,
        "effective_batch_size": 8,
        "max_steps": 100,
        "iters": 100,
        "target_modules": ["q_proj", "v_proj"],
        "training_backend": "native",
        "status": "completed",
        "training_duration_ms": 1234.0,
        "tokens_seen": 1024,
        "examples_seen": 12,
        "tokens_per_second": 96.0,
        "peak_memory_gb": 2.5,
        "loss_final": 0.42,
        "loss_best": 0.33,
        "heldout_test_loss": 0.29,
        "heldout_test_perplexity": 1.34,
        "heldout_test_sample_count": 5,
        "completion_loss": 0.41,
        "round_trip_passed": True,
        "grad_norm": 0.7,
        "weights_path": str(tmp_path / "adapter" / "adapters.safetensors"),
        "adapter_config_path": str(tmp_path / "adapter" / "adapter_config.json"),
        "adapter_set_hash": "abc123",
        "validation_errors": [],
        "merge_export_canary_result": "pass",
        "callback_api_drift_result": "pass",
        "base_config_present": True,
        "aux_modules_restored": True,
        "training_log_events": {
            "schema_version": "melix.training_log_events.v1",
            "best_validation_loss": 0.37,
            "final_validation_loss": 0.37,
        },
        "training_log_event_preview": [
            {
                "event_type": "loss",
                "step": 1,
                "total_steps": 2,
                "loss": 0.55,
                "learning_rate": 0.0001,
                "tokens_seen": 512,
                "examples_seen": 6,
                "source": "fixture",
                "line_number": 1,
            },
            {
                "event_type": "validation_loss",
                "step": 2,
                "total_steps": 2,
                "validation_loss": 0.37,
                "source": "fixture",
                "line_number": 2,
            },
            {"event_type": "stalled_progress", "step": 2},
        ],
    }


def test_build_adapter_provenance_manifest_records_training_facts_and_loss_series(tmp_path: Path) -> None:
    adapter_manifest_path = tmp_path / "train_lora.adapter.json"
    provenance_path = default_adapter_provenance_manifest_path(adapter_manifest_path)
    notes_path = default_adapter_operator_notes_path(adapter_manifest_path)

    provenance = build_adapter_provenance_manifest(
        adapter_manifest=_manifest_payload(tmp_path),
        adapter_manifest_path=adapter_manifest_path,
        provenance_manifest_path=provenance_path,
        operator_notes_path=notes_path,
        operator_notes_payload={"note_count": 0, "updated_at_unix_ms": 123},
        created_at_unix_ms=123,
    )

    assert provenance["schema_version"] == ADAPTER_PROVENANCE_SCHEMA_VERSION
    assert provenance["adapter"]["job_id"] == "model-ops-0001"
    assert provenance["adapter"]["experiment_group_id"] == "nightly-qwen"
    assert provenance["base_model"]["model_id"] == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
    assert provenance["dataset"]["version"] == "2026-06-24"
    assert provenance["dataset"]["train_sample_count"] == 12
    assert provenance["dataset"]["validation_sample_count"] == 3
    assert provenance["hyperparameters"]["effective_batch_size"] == 8
    assert provenance["training"]["loss_series_row_count"] == 2
    assert [row["event_type"] for row in provenance["training"]["loss_series"]] == [
        "loss",
        "validation_loss",
    ]
    assert provenance["final_metrics"]["loss_best"] == pytest.approx(0.33)
    assert provenance["final_metrics"]["validation_loss_best"] == pytest.approx(0.37)
    assert provenance["final_metrics"]["heldout_test_loss"] == pytest.approx(0.29)
    assert provenance["final_metrics"]["heldout_test_perplexity"] == pytest.approx(1.34)
    assert provenance["final_metrics"]["heldout_test_sample_count"] == 5
    assert provenance["operator_notes"]["schema_version"] == ADAPTER_OPERATOR_NOTES_SCHEMA_VERSION
    assert provenance["operator_notes"]["path"] == str(notes_path)
    assert provenance["export_eligibility"]["eligible"] is True


def test_build_loss_series_ignores_non_loss_events() -> None:
    series = build_loss_series(
        {
            "training_log_event_preview": [
                {"event_type": "progress", "step": 1},
                {"event_type": "loss", "step": 2, "loss": "0.4"},
                {"event_type": "validation_loss", "step": 3, "validation_loss": "0.3"},
            ]
        }
    )

    assert series == [
        {"event_type": "loss", "step": 2, "loss": 0.4},
        {"event_type": "validation_loss", "step": 3, "validation_loss": 0.3},
    ]


def test_export_eligibility_reports_blocking_reasons(tmp_path: Path) -> None:
    manifest = _manifest_payload(tmp_path)
    manifest.update(
        {
            "adapter_set_hash": "",
            "runtime_unsupported_reason": "unsupported_quantized_base",
            "merge_export_canary_result": "fail:missing_adapter_weights,eos_token_mismatch",
        }
    )

    eligibility = compute_export_eligibility(manifest)

    assert eligibility["eligible"] is False
    assert eligibility["state"] == "blocked"
    assert eligibility["blocking_reasons"] == [
        "missing_adapter_set_hash",
        "runtime_unsupported:unsupported_quantized_base",
        "merge_export_canary:missing_adapter_weights",
        "merge_export_canary:eos_token_mismatch",
    ]


def test_export_eligibility_reports_all_manifest_blockers(tmp_path: Path) -> None:
    manifest = _manifest_payload(tmp_path)
    manifest.update(
        {
            "status": "failed",
            "weights_path": "",
            "adapter_config_path": "",
            "adapter_set_hash": "",
            "validation_errors": ["adapter audit failed"],
            "adapter_unsupported_reason": "unsupported_target_modules",
            "callback_api_drift_result": "fail:callback_arity_mismatch",
        }
    )

    eligibility = compute_export_eligibility(manifest)

    assert eligibility["eligible"] is False
    assert eligibility["blocking_reasons"] == [
        "training_not_completed",
        "missing_adapter_weights_path",
        "missing_adapter_config_path",
        "missing_adapter_set_hash",
        "validation_errors_present",
        "adapter_unsupported:unsupported_target_modules",
        "callback_api_drift:callback_arity_mismatch",
    ]


def test_write_artifacts_uses_event_fallback_and_preserves_existing_notes(tmp_path: Path) -> None:
    adapter_manifest_path = tmp_path / "train_lora.adapter.json"
    notes_path = default_adapter_operator_notes_path(adapter_manifest_path)
    provenance_path = default_adapter_provenance_manifest_path(adapter_manifest_path)
    write_adapter_operator_notes(
        notes_path=notes_path,
        notes=["ship after review", {"id": "blank", "text": ""}],
        adapter_job_id="model-ops-0001",
        adapter_name="nightly-adapter",
        provenance_manifest_path=provenance_path,
        now_unix_ms=100,
    )
    manifest = _manifest_payload(tmp_path)
    manifest.pop("training_log_events")
    manifest.pop("training_log_event_preview")
    manifest["training.log_events"] = {"best_validation_loss": 0.29}
    manifest["training.log_event_preview"] = [
        "not-a-row",
        {"event_type": "loss", "step": "not-int", "loss": "not-float"},
        {
            "event_type": "validation_loss",
            "step": "2",
            "total_steps": "oops",
            "validation_loss": "0.29",
            "learning_rate": "not-float",
        },
    ]

    result = write_adapter_provenance_artifacts(
        adapter_manifest=manifest,
        adapter_manifest_path=adapter_manifest_path,
        now_unix_ms=123,
    )
    provenance = result["provenance"]
    notes = load_operator_notes_payload(notes_path)

    assert provenance["training"]["event_summary"] == {"best_validation_loss": 0.29}
    assert provenance["training"]["loss_series"] == [
        {"event_type": "validation_loss", "step": 2, "validation_loss": 0.29}
    ]
    assert provenance["operator_notes"]["note_count"] == 1
    assert notes["notes"][0]["text"] == "ship after review"
    assert result["metrics"]["adapter_provenance_manifest_bytes"] > 0


def test_loaders_reject_invalid_schema_and_non_mapping_json(tmp_path: Path) -> None:
    provenance_path = tmp_path / "provenance.json"
    notes_path = tmp_path / "notes.json"

    provenance_path.write_text(json.dumps(["not", "a", "mapping"]) + "\n", encoding="utf-8")
    notes_path.write_text(json.dumps({"schema_version": "wrong", "notes": []}) + "\n", encoding="utf-8")

    assert load_adapter_provenance_payload(provenance_path) == {}
    assert load_operator_notes_payload(notes_path) == {}


def test_operator_notes_update_does_not_mutate_provenance_file(tmp_path: Path) -> None:
    adapter_manifest_path = tmp_path / "train_lora.adapter.json"
    provenance_path = default_adapter_provenance_manifest_path(adapter_manifest_path)
    notes_path = default_adapter_operator_notes_path(adapter_manifest_path)
    provenance_payload = build_adapter_provenance_manifest(
        adapter_manifest=_manifest_payload(tmp_path),
        adapter_manifest_path=adapter_manifest_path,
        provenance_manifest_path=provenance_path,
        operator_notes_path=notes_path,
        operator_notes_payload={"note_count": 0, "updated_at_unix_ms": 123},
        created_at_unix_ms=123,
    )
    provenance_path.write_text(json.dumps(provenance_payload, indent=2) + "\n", encoding="utf-8")
    before = provenance_path.read_text(encoding="utf-8")
    before_stat = provenance_path.stat()

    notes_payload = write_adapter_operator_notes(
        notes_path=notes_path,
        notes=[{"id": "note-1", "text": "Ready for export", "author": "operator"}],
        adapter_job_id="model-ops-0001",
        adapter_name="nightly-adapter",
        provenance_manifest_path=provenance_path,
        now_unix_ms=456,
    )

    assert notes_payload["note_count"] == 1
    assert notes_payload["notes"][0]["text"] == "Ready for export"
    assert provenance_path.read_text(encoding="utf-8") == before
    assert provenance_path.stat().st_mtime_ns == before_stat.st_mtime_ns
