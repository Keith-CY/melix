from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.protocol.python.worker.v1 import common_pb2
from worker.model_ops.deterministic_lora_runner import DeterministicLoRARunner
from worker.model_ops.lora_training_pipeline import LoRATrainingPipeline
from worker.model_ops.training_log_events import (
    parse_training_log_events,
    safe_training_log_manifest_fields,
)


def test_training_log_parser_emits_progress_loss_validation_alerts_and_summary() -> None:
    lines = [
        "step 1/4 loss=2.40 lr=1e-4 trained_tokens=128 examples_seen=1 eta=00:03",
        "step 2/4 loss=1.90 lr=9e-5 trained_tokens=256 examples_seen=2 eta=2s",
        "step 2 validation_loss=1.75",
        "warning: rising loss detected step=3 loss=2.80",
        "error: Metal watchdog timeout at step=3",
        "error: out of memory while allocating tensor at /Users/example/private/model.safetensors",
        "warning: stalled progress heartbeat timeout",
        "training complete step 4/4 loss=1.50 lr=8e-5 duration=12.5s",
        "unstructured trainer chatter",
    ]

    result = parse_training_log_events(lines, source="train.log")

    assert [event.event_type for event in result.events] == [
        "loss",
        "loss",
        "validation_loss",
        "rising_loss",
        "metal_watchdog",
        "oom",
        "stalled_progress",
        "final_summary",
    ]
    assert result.summary.schema_version == "melix.training_log_events.v1"
    assert result.summary.status == "alerts"
    assert result.summary.input_line_count == 9
    assert result.summary.parsed_row_count == 8
    assert result.summary.alert_row_count == 4
    assert result.summary.unparsed_line_count == 1
    assert result.summary.parser_error_count == 0
    assert result.summary.final_step == 4
    assert result.summary.final_total_steps == 4
    assert result.summary.final_loss == pytest.approx(1.5)
    assert result.summary.best_loss == pytest.approx(1.5)
    assert result.summary.final_validation_loss == pytest.approx(1.75)
    assert result.summary.best_validation_loss == pytest.approx(1.75)
    assert result.summary.final_learning_rate == pytest.approx(8e-5)
    assert result.summary.tokens_seen == 256
    assert result.summary.examples_seen == 2
    assert result.summary.terminal_event_type == "final_summary"
    assert result.events[0].eta_seconds == pytest.approx(3.0)
    assert result.events[-1].duration_ms == pytest.approx(12_500.0)
    assert result.events[5].raw_line_redacted.endswith("<path:redacted>")
    assert "/Users/example" not in result.events[5].raw_line_redacted


def test_training_log_manifest_fields_bound_preview() -> None:
    result = parse_training_log_events(
        [
            "step 1/3 loss=3.0",
            "step 2/3 loss=2.0",
            "step 3/3 loss=1.0",
        ],
        source="stdout",
    )

    fields = result.manifest_fields(preview_limit=2)

    assert fields["training_log_events"]["parsed_row_count"] == 3
    assert fields["training_log_event_preview_limit"] == 2
    assert [row["step"] for row in fields["training_log_event_preview"]] == [1, 2]


def test_training_log_parser_covers_progress_warnings_and_duration_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    from worker.model_ops import training_log_events as module

    original_parse_line = module._parse_line
    calls = {"count": 0}

    def flaky_parse_line(line: str, *, line_number: int, source: str):
        if "force parser error" in line:
            calls["count"] += 1
            raise ValueError("forced parser error")
        return original_parse_line(line, line_number=line_number, source=source)

    monkeypatch.setattr(module, "_parse_line", flaky_parse_line)

    result = parse_training_log_events(
        [
            "",
            "step=4 eta=2 min",
            "warning: rising loss detected step=5 loss=nan",
            "training complete step 6/9 loss=0.8 duration=01:02:03",
            "step 7 eta=12:3a loss=0.7",
            "step 7 eta=5 parsecs",
            "step 8 eta=not-a-duration",
            "force parser error",
        ],
        source="edge.log",
    )

    assert calls["count"] == 1
    assert result.summary.status == "warnings"
    assert result.summary.parser_error_count == 1
    assert result.summary.alert_row_count == 1
    assert result.summary.final_step == 8
    assert result.events[0].event_type == "progress"
    assert result.events[0].eta_seconds == pytest.approx(120.0)
    assert result.events[1].loss is None
    assert result.events[2].duration_ms == pytest.approx(3_723_000.0)
    assert result.events[3].eta_seconds is None
    assert result.events[3].loss == pytest.approx(0.7)
    assert result.events[4].eta_seconds is None
    assert result.events[5].eta_seconds is None


def test_training_log_redaction_bounds_extremely_long_lines() -> None:
    line = "error: out of memory token=secret " + ("/private/path/" + ("x" * 2000))

    result = parse_training_log_events([line], source="stdout")

    assert result.summary.parser_error_count == 0
    assert result.summary.alert_row_count == 1
    assert result.events[0].event_type == "oom"
    assert result.events[0].raw_line_redacted.startswith("error: out of memory token=<redacted>")
    assert len(result.events[0].raw_line_redacted) <= 512
    assert "secret" not in result.events[0].raw_line_redacted
    assert "/private/path" not in result.events[0].raw_line_redacted


def test_safe_training_log_manifest_fields_bounds_parser_failures() -> None:
    class BrokenLines:
        def __iter__(self):
            raise RuntimeError("broken stream")

    fields = safe_training_log_manifest_fields(BrokenLines())

    assert fields["training_log_events"]["status"] == "parser_error"
    assert fields["training_log_events"]["parser_error_count"] == 1
    assert fields["training_log_event_preview"] == []


def test_deterministic_lora_manifest_records_training_log_events(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    (dataset_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "melix-dev-dataset",
                "format": "chat_messages",
                "sample_count": 1,
                "version": "1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (dataset_dir / "samples.jsonl").write_text(
        '{"messages":[{"role":"user","content":"hi"},{"role":"assistant","content":"ok"}]}\n',
        encoding="utf-8",
    )

    result = LoRATrainingPipeline(runner=DeterministicLoRARunner()).run(
        job_id="train-log-events",
        request_ext={
            "operation": "train_lora",
            "adapter_name": "receipt-adapter",
            "dataset_uri": str(dataset_dir),
            "max_steps": "0",
        },
        source_model=common_pb2.ModelSpec(
            model_id="melix-dev-text",
            model_path=str(tmp_path / "base-model"),
            model_kind="text",
            revision="main",
            max_context=4096,
        ),
        output_dir=tmp_path / "output",
        jobs_root=tmp_path / "jobs",
    )

    manifest = result.manifest
    assert manifest["training_log_events"]["schema_version"] == "melix.training_log_events.v1"
    assert manifest["training_log_events"]["parsed_row_count"] == 3
    assert manifest["training_log_events"]["final_step"] == 2
    assert manifest["training_log_events"]["final_loss"] == pytest.approx(0.42)
    assert manifest["training_log_events"]["best_validation_loss"] == pytest.approx(0.37)
    assert manifest["training.log_events"] == manifest["training_log_events"]
    assert manifest["training_log_event_preview_limit"] == 10
    assert [row["event_type"] for row in manifest["training_log_event_preview"]] == [
        "loss",
        "validation_loss",
        "final_summary",
    ]


def test_deterministic_lora_manifest_writes_adapter_provenance_and_notes(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    (dataset_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "melix-dev-dataset",
                "format": "chat_messages",
                "sample_count": 1,
                "version": "dataset-v1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (dataset_dir / "samples.jsonl").write_text(
        '{"messages":[{"role":"user","content":"hi"},{"role":"assistant","content":"ok"}]}\n',
        encoding="utf-8",
    )

    result = LoRATrainingPipeline(runner=DeterministicLoRARunner()).run(
        job_id="adapter-provenance",
        request_ext={
            "operation": "train_lora",
            "adapter_name": "receipt-adapter",
            "dataset_uri": str(dataset_dir),
            "max_steps": "0",
        },
        source_model=common_pb2.ModelSpec(
            model_id="melix-dev-text",
            model_path=str(tmp_path / "base-model"),
            model_kind="text",
            revision="main",
            max_context=4096,
        ),
        output_dir=tmp_path / "output",
        jobs_root=tmp_path / "jobs",
    )

    manifest = result.manifest
    provenance_path = Path(manifest["adapter_provenance_manifest_path"])
    notes_path = Path(manifest["adapter_operator_notes_path"])
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    notes = json.loads(notes_path.read_text(encoding="utf-8"))

    assert manifest["adapter_provenance_schema_version"] == "melix.lora_adapter_provenance.v1"
    assert provenance["schema_version"] == "melix.lora_adapter_provenance.v1"
    assert provenance["adapter"]["job_id"] == "adapter-provenance"
    assert provenance["base_model"]["model_id"] == "melix-dev-text"
    assert provenance["dataset"]["version"] == "dataset-v1"
    assert provenance["dataset"]["train_sample_count"] == 1
    assert provenance["training"]["loss_series_row_count"] == 3
    assert provenance["final_metrics"]["loss_best"] == pytest.approx(0.33)
    assert provenance["export_eligibility"]["eligible"] is False
    assert "merge_export_canary:missing_base_config" in provenance["export_eligibility"]["blocking_reasons"]
    assert notes["schema_version"] == "melix.lora_adapter_operator_notes.v1"
    assert notes["notes"] == []
    assert notes["note_count"] == 0
    assert manifest["adapter_operator_note_count"] == 0
    assert manifest["adapter_provenance_loss_series_row_count"] == 3
    assert manifest["adapter_provenance_manifest_bytes"] > 0
    assert manifest["adapter_provenance_manifest_write_duration_ms"] >= 0.0
    assert manifest["adapter_operator_notes_write_duration_ms"] >= 0.0
