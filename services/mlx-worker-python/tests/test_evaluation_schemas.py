from __future__ import annotations

from worker.productization.evaluation_schemas import (
    build_dataset_package_manifest,
    build_evaluation_job_record,
    build_evaluation_result_record,
    build_evaluation_sample_record,
)


def test_build_dataset_package_manifest_preserves_dataset_identity() -> None:
    manifest = build_dataset_package_manifest(
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        version="2026-03-31",
        sample_count=2,
        split="validation",
        task_kind="text-generation",
    )
    payload = manifest.to_dict()

    assert payload["schema_version"] == "melix.evaluation_dataset_package.v1"
    assert payload["dataset_id"] == "mmlu-dev"
    assert payload["suite_id"] == "mmlu"
    assert payload["version"] == "2026-03-31"
    assert payload["sample_count"] == 2
    assert payload["split"] == "validation"
    assert payload["task_kind"] == "text-generation"
    assert payload["input_modalities"] == []


def test_build_evaluation_job_record_preserves_core_fields() -> None:
    job = build_evaluation_job_record(
        job_id="eval-1",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="HuggingFaceH4/ultrachat_200k",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_size=8,
        scoring_mode="exact-match",
        parameters={"split": "validation"},
        status="completed",
        output_dir="/tmp/melix/evaluation/runs/eval-1",
        created_at_unix_ms=101,
        updated_at_unix_ms=202,
    )
    payload = job.to_dict()

    assert payload["schema_version"] == "melix.evaluation_job.v1"
    assert payload["job_id"] == "eval-1"
    assert payload["model_id"] == "melix-dev-text"
    assert payload["task_kind"] == "text-generation"
    assert payload["source_repo"] == "HuggingFaceH4/ultrachat_200k"
    assert payload["suite_id"] == "mmlu"
    assert payload["dataset_id"] == "mmlu-dev"
    assert payload["sample_size"] == 8
    assert payload["scoring_mode"] == "exact-match"
    assert payload["parameters"] == {"split": "validation"}
    assert payload["status"] == "completed"
    assert payload["output_dir"] == "/tmp/melix/evaluation/runs/eval-1"
    assert payload["created_at_unix_ms"] == 101
    assert payload["updated_at_unix_ms"] == 202


def test_build_evaluation_result_record_orders_metrics_stably() -> None:
    result = build_evaluation_result_record(
        job_id="eval-1",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_size=8,
        metrics={"eval.mmlu.loss": 0.25, "eval.mmlu.accuracy": 0.75},
        report_path="/tmp/mmlu.json",
        units={"eval.mmlu.accuracy": "ratio", "eval.mmlu.loss": "loss"},
    )

    metrics = result.to_dict()["metrics"]
    assert [row["name"] for row in metrics] == [
        "eval.mmlu.accuracy",
        "eval.mmlu.loss",
    ]
    assert metrics[0]["unit"] == "ratio"
    assert metrics[1]["unit"] == "loss"


def test_build_evaluation_sample_record_preserves_sample_payload() -> None:
    sample = build_evaluation_sample_record(
        job_id="eval-1",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_id="sample-1",
        question="2+2?",
        expected="4",
        predicted="4",
        raw_response="4",
        correct=True,
        time_s=0.0123,
        parse_status="parsed",
        task_kind="text-generation",
    )

    assert sample.to_dict() == {
        "schema_version": "melix.evaluation_sample.v1",
        "job_id": "eval-1",
        "suite_id": "mmlu",
        "dataset_id": "mmlu-dev",
        "sample_id": "sample-1",
        "question": "2+2?",
        "expected": "4",
        "predicted": "4",
        "raw_response": "4",
        "correct": True,
        "time_s": 0.0123,
        "parse_status": "parsed",
        "task_kind": "text-generation",
        "input_modalities": [],
        "media_references": [],
    }


def test_build_evaluation_sample_record_preserves_multimodal_evidence_fields() -> None:
    sample = build_evaluation_sample_record(
        job_id="eval-1",
        suite_id="mmlu",
        dataset_id="vision-dev",
        sample_id="vision-1",
        question="Describe the image.",
        expected="Cat",
        predicted="Cat",
        raw_response="Answer: Cat",
        correct=True,
        time_s=0.045,
        parse_status="parsed_answer_prefix",
        task_kind="image-text-to-text",
        input_modalities=("text", "image"),
        media_references=("/tmp/cat.png",),
    )

    assert sample.to_dict() == {
        "schema_version": "melix.evaluation_sample.v1",
        "job_id": "eval-1",
        "suite_id": "mmlu",
        "dataset_id": "vision-dev",
        "sample_id": "vision-1",
        "question": "Describe the image.",
        "expected": "Cat",
        "predicted": "Cat",
        "raw_response": "Answer: Cat",
        "correct": True,
        "time_s": 0.045,
        "parse_status": "parsed_answer_prefix",
        "task_kind": "image-text-to-text",
        "input_modalities": ["text", "image"],
        "media_references": ["/tmp/cat.png"],
    }
