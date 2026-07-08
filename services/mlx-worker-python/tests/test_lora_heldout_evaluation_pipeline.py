from __future__ import annotations

import json
import math
from pathlib import Path
from typing import cast

import pytest

from test_lora_training_receipts import _text_model, _write_dataset_package

from worker.model_ops.deterministic_lora_runner import DeterministicLoRARunner
from worker.model_ops.lora_heldout_evaluation import evaluate_heldout_if_requested
from worker.model_ops.lora_training_pipeline import LoRATrainingPipeline
from worker.model_ops.mlx_lm_runner import HeldoutEvaluationRequest, HeldoutEvaluationResult
from worker.model_ops.training_config import LoRATrainingConfig
from worker.model_ops.training_dataset import NormalizedDatasetSnapshot


class FailingHeldoutEvaluationRunner(DeterministicLoRARunner):
    def evaluate_heldout_native(
        self,
        request: HeldoutEvaluationRequest,
    ) -> HeldoutEvaluationResult:
        del request
        raise RuntimeError("held-out metric backend unavailable")


class FailingBaselineHeldoutEvaluationRunner(DeterministicLoRARunner):
    def evaluate_heldout_native(
        self,
        request: HeldoutEvaluationRequest,
    ) -> HeldoutEvaluationResult:
        if request.adapter_dir is None:
            raise RuntimeError("baseline metric backend unavailable")
        return super().evaluate_heldout_native(request)


def _heldout_dataset_package(tmp_path: Path, name: str, dataset_id: str) -> Path:
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
    return _write_dataset_package(
        tmp_path / name,
        manifest_payload={
            "schema_version": "melix.training_dataset_package.v1",
            "dataset_id": dataset_id,
            "format": "chat_messages",
            "sample_count": len(sample_lines),
            "version": "1",
        },
        sample_lines=sample_lines,
    )


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


def test_lora_training_pipeline_records_failed_heldout_evaluation_without_failing_training(
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
        tmp_path / "dataset-with-failing-heldout",
        manifest_payload={
            "schema_version": "melix.training_dataset_package.v1",
            "dataset_id": "melix-heldout-fails",
            "format": "chat_messages",
            "sample_count": len(sample_lines),
            "version": "1",
        },
        sample_lines=sample_lines,
    )

    result = LoRATrainingPipeline(runner=FailingHeldoutEvaluationRunner()).run(
        job_id="train-heldout-eval-fails",
        request_ext={
            "operation": "train_lora",
            "adapter_name": "heldout-failed-adapter",
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
    receipt = json.loads(
        Path(manifest["heldout_evaluation_receipt_path"]).read_text(encoding="utf-8")
    )
    provenance = json.loads(
        Path(manifest["adapter_provenance_manifest_path"]).read_text(encoding="utf-8")
    )

    assert Path(manifest["weights_path"]).is_file()
    assert manifest["heldout_evaluation_status"] == "failed"
    assert manifest["heldout_evaluation_reason"] == "heldout_evaluation_failed"
    assert manifest["heldout_test_ratio"] == 0.25
    assert manifest["heldout_test_path"] == str(normalized_test_path)
    assert manifest["heldout_test_sample_count"] == 2
    assert manifest["heldout_test_loss"] is None
    assert manifest["heldout_test_perplexity"] is None
    assert receipt["status"] == "failed"
    assert receipt["reason"] == "heldout_evaluation_failed"
    assert receipt["test_path"] == str(normalized_test_path)
    assert receipt["sample_count"] == 2
    assert receipt["loss"] is None
    assert receipt["perplexity"] is None
    assert receipt["backend"] == ""
    assert receipt["error_code"] == "backend_training_failure"
    assert receipt["error_message"] == "held-out metric backend unavailable"
    assert provenance["final_metrics"]["heldout_test_loss"] is None
    assert provenance["final_metrics"]["heldout_test_perplexity"] is None
    assert provenance["final_metrics"]["heldout_test_sample_count"] == 2


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


def test_lora_training_pipeline_records_heldout_baseline_comparison(
    tmp_path: Path,
) -> None:
    dataset_dir = _heldout_dataset_package(
        tmp_path, "dataset-with-baseline-compare", "melix-heldout-baseline"
    )

    result = LoRATrainingPipeline(runner=DeterministicLoRARunner()).run(
        job_id="train-heldout-baseline",
        request_ext={
            "operation": "train_lora",
            "adapter_name": "heldout-baseline-adapter",
            "dataset_uri": str(dataset_dir),
            "max_steps": "0",
            "test_ratio": "0.25",
            "heldout_baseline_compare": "true",
        },
        source_model=_text_model(family_id="qwen"),
        output_dir=tmp_path / "output",
        jobs_root=tmp_path / "jobs",
    )

    manifest = result.manifest
    receipt = json.loads(
        Path(manifest["heldout_evaluation_receipt_path"]).read_text(encoding="utf-8")
    )
    run_record = json.loads(
        (tmp_path / "output" / "lora-experiment-run.json").read_text(encoding="utf-8")
    )

    assert manifest["heldout_evaluation_status"] == "completed"
    assert manifest["heldout_test_loss"] == pytest.approx(0.29)
    assert manifest["heldout_baseline_status"] == "completed"
    assert manifest["heldout_baseline_reason"] == ""
    assert manifest["heldout_baseline_backend"] == "native"
    assert manifest["heldout_baseline_loss"] == pytest.approx(0.42)
    assert manifest["heldout_baseline_perplexity"] == pytest.approx(math.exp(0.42))
    assert manifest["heldout_loss_delta"] == pytest.approx(0.42 - 0.29)
    assert manifest["heldout_perplexity_ratio"] == pytest.approx(
        math.exp(0.42) / math.exp(0.29)
    )
    assert receipt["baseline_status"] == "completed"
    assert receipt["baseline_loss"] == pytest.approx(0.42)
    assert receipt["loss_delta"] == pytest.approx(0.13)
    assert run_record["heldout_baseline_loss"] == pytest.approx(0.42)
    assert run_record["heldout_loss_delta"] == pytest.approx(0.13)


def test_lora_training_pipeline_baseline_failure_keeps_adapter_heldout_metrics(
    tmp_path: Path,
) -> None:
    dataset_dir = _heldout_dataset_package(
        tmp_path, "dataset-with-failing-baseline", "melix-heldout-baseline-fails"
    )

    result = LoRATrainingPipeline(runner=FailingBaselineHeldoutEvaluationRunner()).run(
        job_id="train-heldout-baseline-fails",
        request_ext={
            "operation": "train_lora",
            "adapter_name": "heldout-baseline-failed-adapter",
            "dataset_uri": str(dataset_dir),
            "max_steps": "0",
            "test_ratio": "0.25",
            "heldout_baseline_compare": "true",
        },
        source_model=_text_model(family_id="qwen"),
        output_dir=tmp_path / "output",
        jobs_root=tmp_path / "jobs",
    )

    manifest = result.manifest
    receipt = json.loads(
        Path(manifest["heldout_evaluation_receipt_path"]).read_text(encoding="utf-8")
    )

    # The adapter's own held-out metrics survive a failed baseline pass.
    assert manifest["heldout_evaluation_status"] == "completed"
    assert manifest["heldout_test_loss"] == pytest.approx(0.29)
    assert manifest["heldout_baseline_status"] == "failed"
    assert manifest["heldout_baseline_reason"] == "baseline_evaluation_failed"
    assert manifest["heldout_baseline_loss"] is None
    assert manifest["heldout_loss_delta"] is None
    assert receipt["baseline_status"] == "failed"
    assert receipt["baseline_error_code"] == "backend_training_failure"
    assert receipt["baseline_error_message"] == "baseline metric backend unavailable"
    assert receipt["loss_delta"] is None


def test_lora_training_pipeline_baseline_not_requested_keeps_receipt_shape(
    tmp_path: Path,
) -> None:
    dataset_dir = _heldout_dataset_package(
        tmp_path, "dataset-without-baseline-compare", "melix-heldout-no-baseline"
    )

    result = LoRATrainingPipeline(runner=DeterministicLoRARunner()).run(
        job_id="train-heldout-no-baseline",
        request_ext={
            "operation": "train_lora",
            "adapter_name": "heldout-no-baseline-adapter",
            "dataset_uri": str(dataset_dir),
            "max_steps": "0",
            "test_ratio": "0.25",
        },
        source_model=_text_model(family_id="qwen"),
        output_dir=tmp_path / "output",
        jobs_root=tmp_path / "jobs",
    )

    manifest = result.manifest
    receipt = json.loads(
        Path(manifest["heldout_evaluation_receipt_path"]).read_text(encoding="utf-8")
    )

    assert "baseline_status" not in receipt
    assert "heldout_baseline_status" not in manifest
    assert "heldout_loss_delta" not in manifest


def test_heldout_baseline_skipped_when_adapter_evaluation_fails(
    tmp_path: Path,
) -> None:
    dataset_dir = _heldout_dataset_package(
        tmp_path, "dataset-adapter-fails-baseline-requested", "melix-heldout-adapter-fails"
    )

    result = LoRATrainingPipeline(runner=FailingHeldoutEvaluationRunner()).run(
        job_id="train-heldout-adapter-fails-baseline",
        request_ext={
            "operation": "train_lora",
            "adapter_name": "heldout-adapter-fails-baseline",
            "dataset_uri": str(dataset_dir),
            "max_steps": "0",
            "test_ratio": "0.25",
            "heldout_baseline_compare": "1",
        },
        source_model=_text_model(family_id="qwen"),
        output_dir=tmp_path / "output",
        jobs_root=tmp_path / "jobs",
    )

    manifest = result.manifest
    assert manifest["heldout_evaluation_status"] == "failed"
    assert manifest["heldout_baseline_status"] == "skipped"
    assert manifest["heldout_baseline_reason"] == "adapter_evaluation_not_completed"
    assert manifest["heldout_baseline_loss"] is None
    assert manifest["heldout_loss_delta"] is None


def test_heldout_evaluation_skipped_reason_preserves_empty_after_formatting(
    tmp_path: Path,
) -> None:
    snapshot = NormalizedDatasetSnapshot(
        dataset_dir=tmp_path / "normalized_dataset",
        manifest_path=tmp_path / "normalized_dataset" / "manifest.json",
        manifest_payload={
            "test_ratio": 0.75,
            "test_split_reason": "test_split_empty_after_formatting",
            "source_trace_test_sample_count": 3,
            "test_sample_count": 0,
        },
        samples_path=tmp_path / "normalized_dataset" / "samples.jsonl",
        train_path=tmp_path / "normalized_dataset" / "train.jsonl",
        valid_path=None,
        test_path=None,
        sample_count=1,
        validation_sample_count=0,
        test_sample_count=0,
        format="agentic_tool_trace",
        trainer_format="chat_messages",
    )

    receipt = evaluate_heldout_if_requested(
        runner=DeterministicLoRARunner(),
        job_id="train-heldout-empty-after-formatting",
        source_model=_text_model(family_id="qwen"),
        training_model_path=tmp_path / "model",
        adapter_output_dir=tmp_path / "adapter",
        normalized_snapshot=snapshot,
        config=cast(LoRATrainingConfig, object()),
        trainer_dataset_format="chat_messages",
        test_ratio=0.75,
        runtime_failure_details={},
    )

    assert receipt["status"] == "skipped"
    assert receipt["reason"] == "test_split_empty_after_formatting"
    assert receipt["sample_count"] == 0
    assert receipt["loss"] is None
    assert receipt["perplexity"] is None
