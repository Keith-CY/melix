from __future__ import annotations

from worker.productization.evaluation_schemas import (
    build_dataset_package_manifest,
    build_evaluation_job_record,
    build_evaluation_result_record,
)


def test_build_dataset_package_manifest_preserves_dataset_identity() -> None:
    manifest = build_dataset_package_manifest(
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        version="2026-03-31",
        sample_count=2,
        split="validation",
    )
    payload = manifest.to_dict()

    assert payload["schema_version"] == "melix.evaluation_dataset_package.v1"
    assert payload["dataset_id"] == "mmlu-dev"
    assert payload["suite_id"] == "mmlu"
    assert payload["version"] == "2026-03-31"
    assert payload["sample_count"] == 2
    assert payload["split"] == "validation"


def test_build_evaluation_job_record_preserves_core_fields() -> None:
    job = build_evaluation_job_record(
        job_id="eval-1",
        model_id="melix-dev-text",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_size=8,
        scoring_mode="exact-match",
        parameters={"split": "validation"},
        status="completed",
    )
    payload = job.to_dict()

    assert payload["schema_version"] == "melix.evaluation_job.v1"
    assert payload["job_id"] == "eval-1"
    assert payload["model_id"] == "melix-dev-text"
    assert payload["suite_id"] == "mmlu"
    assert payload["dataset_id"] == "mmlu-dev"
    assert payload["sample_size"] == 8
    assert payload["scoring_mode"] == "exact-match"
    assert payload["parameters"] == {"split": "validation"}
    assert payload["status"] == "completed"


def test_build_evaluation_result_record_orders_metrics_stably() -> None:
    result = build_evaluation_result_record(
        job_id="eval-1",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_size=8,
        metrics={"eval.mmlu.loss": 0.25, "eval.mmlu.accuracy": 0.75},
        report_path="/tmp/mmlu.json",
    )

    assert [row["name"] for row in result.to_dict()["metrics"]] == [
        "eval.mmlu.accuracy",
        "eval.mmlu.loss",
    ]
