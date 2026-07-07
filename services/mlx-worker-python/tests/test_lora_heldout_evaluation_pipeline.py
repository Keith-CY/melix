from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from test_lora_training_receipts import _text_model, _write_dataset_package

from worker.model_ops.deterministic_lora_runner import DeterministicLoRARunner
from worker.model_ops.lora_training_pipeline import LoRATrainingPipeline


def test_lora_training_pipeline_records_completed_heldout_evaluation_receipt(
    tmp_path: Path,
) -> None:
    sample_lines = [
        json.dumps(
            {
                "messages": [
                    {"role": "user", "content": f"question {index}"},
                    {"role": "assistant", "content": f"answer {index}"},
                ]
            }
        )
        for index in range(8)
    ]
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset-with-test-split",
        manifest_payload={
            "schema_version": "melix.training_dataset_package.v1",
            "dataset_id": "melix-heldout-demo",
            "format": "chat_messages",
            "sample_count": len(sample_lines),
            "version": "1",
        },
        sample_lines=sample_lines,
    )

    result = LoRATrainingPipeline(runner=DeterministicLoRARunner()).run(
        job_id="train-heldout-eval",
        request_ext={
            "operation": "train_lora",
            "adapter_name": "heldout-adapter",
            "dataset_uri": str(dataset_dir),
            "max_steps": "0",
            "test_ratio": "0.25",
        },
        source_model=_text_model(family_id="qwen"),
        output_dir=tmp_path / "output",
        jobs_root=tmp_path / "jobs",
    )

    manifest = result.manifest
    normalized_test_path = tmp_path / "output" / "normalized_dataset" / "test.jsonl"
    receipt_path = Path(manifest["heldout_evaluation_receipt_path"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    provenance = json.loads(
        Path(manifest["adapter_provenance_manifest_path"]).read_text(encoding="utf-8")
    )
    run_record = json.loads(
        (tmp_path / "output" / "lora-experiment-run.json").read_text(
            encoding="utf-8"
        )
    )
    train_prompts = {
        json.loads(line)["messages"][0]["content"]
        for line in (tmp_path / "output" / "normalized_dataset" / "train.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    }
    test_prompts = {
        json.loads(line)["messages"][0]["content"]
        for line in normalized_test_path.read_text(encoding="utf-8").splitlines()
    }

    assert normalized_test_path.is_file()
    assert len(test_prompts) == 2
    assert train_prompts.isdisjoint(test_prompts)
    assert manifest["trainer_dataset_sample_count"] == 6
    assert manifest["trainer_dataset_test_sample_count"] == 2
    assert manifest["heldout_evaluation_status"] == "completed"
    assert manifest["heldout_evaluation_reason"] == ""
    assert manifest["heldout_test_ratio"] == 0.25
    assert manifest["heldout_test_sample_count"] == 2
    assert manifest["heldout_test_loss"] == pytest.approx(0.29)
    assert manifest["heldout_test_perplexity"] == pytest.approx(math.exp(0.29))
    assert manifest["heldout_test_path"] == str(normalized_test_path)
    assert manifest["dataset_files_resolved"]["normalized_test_path"] == str(
        normalized_test_path
    )
    assert receipt == {
        "schema_version": "melix.lora_heldout_evaluation_receipt.v1",
        "status": "completed",
        "reason": "",
        "test_ratio": 0.25,
        "test_path": str(normalized_test_path),
        "sample_count": 2,
        "loss": pytest.approx(0.29),
        "perplexity": pytest.approx(math.exp(0.29)),
        "backend": "native",
    }
    assert provenance["final_metrics"]["heldout_test_loss"] == pytest.approx(0.29)
    assert provenance["final_metrics"]["heldout_test_perplexity"] == pytest.approx(
        math.exp(0.29)
    )
    assert provenance["final_metrics"]["heldout_test_sample_count"] == 2
    assert run_record["heldout_test_loss"] == pytest.approx(0.29)
    assert run_record["heldout_test_perplexity"] == pytest.approx(math.exp(0.29))
    assert run_record["heldout_test_sample_count"] == 2


def test_lora_training_pipeline_records_skipped_heldout_evaluation_without_test_ratio(
    tmp_path: Path,
) -> None:
    dataset_dir = _write_dataset_package(tmp_path / "dataset-without-test-split")

    result = LoRATrainingPipeline(runner=DeterministicLoRARunner()).run(
        job_id="train-heldout-eval-skipped",
        request_ext={
            "operation": "train_lora",
            "adapter_name": "heldout-skipped-adapter",
            "dataset_uri": str(dataset_dir),
            "max_steps": "0",
        },
        source_model=_text_model(family_id="qwen"),
        output_dir=tmp_path / "output",
        jobs_root=tmp_path / "jobs",
    )

    manifest = result.manifest
    receipt_path = Path(manifest["heldout_evaluation_receipt_path"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert (tmp_path / "output" / "normalized_dataset" / "test.jsonl").exists() is False
    assert manifest["trainer_dataset_test_sample_count"] == 0
    assert manifest["heldout_evaluation_status"] == "skipped"
    assert manifest["heldout_evaluation_reason"] == "test_split_not_requested"
    assert manifest["heldout_test_ratio"] == 0.0
    assert manifest["heldout_test_sample_count"] == 0
    assert manifest["heldout_test_loss"] is None
    assert manifest["heldout_test_perplexity"] is None
    assert manifest["heldout_test_path"] == ""
    assert "normalized_test_path" not in manifest["dataset_files_resolved"]
    assert receipt == {
        "schema_version": "melix.lora_heldout_evaluation_receipt.v1",
        "status": "skipped",
        "reason": "test_split_not_requested",
        "test_ratio": 0.0,
        "test_path": "",
        "sample_count": 0,
        "loss": None,
        "perplexity": None,
        "backend": "",
    }
