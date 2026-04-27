from __future__ import annotations

from worker.productization.evaluation_schemas import (
    build_dataset_package_manifest,
    build_evaluation_compare_job_record,
    build_evaluation_compare_sample_record,
    build_evaluation_compare_summary_record,
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
        profile_type="final_result",
        result_kind="text",
        extraction_mode="heuristic_final",
        scoring_mode="normalized_exact_match",
        threshold=1.0,
    )
    payload = manifest.to_dict()

    assert payload["schema_version"] == "melix.evaluation_dataset_package.v2"
    assert payload["dataset_id"] == "mmlu-dev"
    assert payload["suite_id"] == "mmlu"
    assert payload["version"] == "2026-03-31"
    assert payload["sample_count"] == 2
    assert payload["split"] == "validation"
    assert payload["task_kind"] == "text-generation"
    assert payload["input_modalities"] == []
    assert payload["profile_type"] == "final_result"
    assert payload["result_kind"] == "text"
    assert payload["extraction_mode"] == "heuristic_final"
    assert payload["scoring_mode"] == "normalized_exact_match"
    assert payload["threshold"] == 1.0
    assert payload["ignored_paths"] == []


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

    assert payload["schema_version"] == "melix.evaluation_job.v2"
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
        primary_score_name="json_field_match",
        primary_score_value=0.75,
        extraction_success_count=7,
        validation_success_count=6,
        scored_sample_count=6,
        failure_count=2,
        duration_seconds=1.25,
        metrics={"eval.mmlu.loss": 0.25, "eval.mmlu.accuracy": 0.75},
        report_path="/tmp/mmlu.json",
        units={"eval.mmlu.accuracy": "ratio", "eval.mmlu.loss": "loss"},
    )

    payload = result.to_dict()
    metrics = payload["metrics"]
    assert [row["name"] for row in metrics] == [
        "eval.mmlu.accuracy",
        "eval.mmlu.loss",
    ]
    assert metrics[0]["unit"] == "ratio"
    assert metrics[1]["unit"] == "loss"
    assert payload["primary_score_name"] == "json_field_match"
    assert payload["primary_score_value"] == 0.75
    assert payload["extraction_success_count"] == 7
    assert payload["validation_success_count"] == 6
    assert payload["scored_sample_count"] == 6
    assert payload["failure_count"] == 2


def test_build_evaluation_sample_record_preserves_sample_payload() -> None:
    sample = build_evaluation_sample_record(
        job_id="eval-1",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_id="sample-1",
        system="Return only the final answer.",
        input_text="2+2?",
        target="4",
        raw_response="4",
        extracted_result="4",
        typed_score=1.0,
        time_s=0.0123,
        extraction_status="extracted",
        validation_status="validated",
        failure_reason="",
        task_kind="text-generation",
    )

    assert sample.to_dict() == {
        "schema_version": "melix.evaluation_sample.v2",
        "job_id": "eval-1",
        "suite_id": "mmlu",
        "dataset_id": "mmlu-dev",
        "sample_id": "sample-1",
        "system": "Return only the final answer.",
        "input_text": "2+2?",
        "target": "4",
        "raw_response": "4",
        "extracted_result": "4",
        "typed_score": 1.0,
        "time_s": 0.0123,
        "extraction_status": "extracted",
        "validation_status": "validated",
        "failure_reason": "",
        "task_kind": "text-generation",
        "input_modalities": [],
        "media_references": [],
        "code_language": "",
        "code_entry_point": "",
        "code_compile_status": "",
        "code_runtime_status": "",
        "code_timeout_status": "",
        "code_test_status": "",
        "code_tests_passed": 0,
        "code_tests_total": 0,
        "code_failure_detail": "",
        "sample_render_ms": 0.0,
        "inference_ms": 0.0,
        "extraction_ms": 0.0,
        "validation_ms": 0.0,
        "scoring_ms": 0.0,
        "raw_response_chars": 1,
        "extracted_result_chars": 1,
        "failure_stage": "",
    }


def test_build_evaluation_sample_record_preserves_probe_fields() -> None:
    sample = build_evaluation_sample_record(
        job_id="eval-1",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_id="sample-1",
        system="Return only the final answer.",
        input_text="2+2?",
        target="4",
        raw_response="Answer: 4",
        extracted_result="4",
        typed_score=1.0,
        time_s=0.0123,
        extraction_status="extracted",
        validation_status="validated",
        failure_reason="",
        task_kind="text-generation",
        sample_render_ms=1.1,
        inference_ms=9.2,
        extraction_ms=0.3,
        validation_ms=0.4,
        scoring_ms=0.5,
        raw_response_chars=9,
        extracted_result_chars=1,
        failure_stage="",
    )

    payload = sample.to_dict()

    assert payload["sample_render_ms"] == 1.1
    assert payload["inference_ms"] == 9.2
    assert payload["extraction_ms"] == 0.3
    assert payload["validation_ms"] == 0.4
    assert payload["scoring_ms"] == 0.5
    assert payload["raw_response_chars"] == 9
    assert payload["extracted_result_chars"] == 1
    assert payload["failure_stage"] == ""


def test_build_evaluation_sample_record_preserves_multimodal_evidence_fields() -> None:
    sample = build_evaluation_sample_record(
        job_id="eval-1",
        suite_id="mmlu",
        dataset_id="vision-dev",
        sample_id="vision-1",
        system="Describe the image.",
        input_text="Describe the image.",
        target="Cat",
        raw_response="Answer: Cat",
        extracted_result="Cat",
        typed_score=1.0,
        time_s=0.045,
        extraction_status="extracted",
        validation_status="validated",
        failure_reason="",
        task_kind="image-text-to-text",
        input_modalities=("text", "image"),
        media_references=("/tmp/cat.png",),
        category_label="animals",
        subject_label="imagenette",
    )

    assert sample.to_dict() == {
        "schema_version": "melix.evaluation_sample.v2",
        "job_id": "eval-1",
        "suite_id": "mmlu",
        "dataset_id": "vision-dev",
        "sample_id": "vision-1",
        "system": "Describe the image.",
        "input_text": "Describe the image.",
        "target": "Cat",
        "raw_response": "Answer: Cat",
        "extracted_result": "Cat",
        "typed_score": 1.0,
        "time_s": 0.045,
        "extraction_status": "extracted",
        "validation_status": "validated",
        "failure_reason": "",
        "task_kind": "image-text-to-text",
        "input_modalities": ["text", "image"],
        "media_references": ["/tmp/cat.png"],
        "code_language": "",
        "code_entry_point": "",
        "code_compile_status": "",
        "code_runtime_status": "",
        "code_timeout_status": "",
        "code_test_status": "",
        "code_tests_passed": 0,
        "code_tests_total": 0,
        "code_failure_detail": "",
        "category_label": "animals",
        "subject_label": "imagenette",
        "sample_render_ms": 0.0,
        "inference_ms": 0.0,
        "extraction_ms": 0.0,
        "validation_ms": 0.0,
        "scoring_ms": 0.0,
        "raw_response_chars": 11,
        "extracted_result_chars": 3,
        "failure_stage": "",
    }


def test_build_evaluation_compare_records_preserve_target_metadata() -> None:
    job = build_evaluation_compare_job_record(
        job_id="eval-compare-1",
        base_model_id="melix-dev-text",
        target_model_ids=("melix-dev-text-lora-a", "melix-dev-text-lora-b"),
        task_kind="text-generation",
        source_repo="test/source",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_size=2,
        scoring_mode="multiple_choice_accuracy",
        parameters={"compare_mode": "base_vs_targets"},
        status="completed",
        output_dir="/tmp/melix/evaluation/runs/eval-compare-1",
        created_at_unix_ms=101,
        updated_at_unix_ms=202,
    )
    summary = build_evaluation_compare_summary_record(
        job_id="eval-compare-1",
        base_model_id="melix-dev-text",
        target_model_id="melix-dev-text-lora-a",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_size=2,
        scoring_mode="multiple_choice_accuracy",
        win_count=1,
        loss_count=0,
        tie_count=1,
        regression_count=0,
        base_accuracy=0.5,
        target_accuracy=1.0,
        delta_accuracy=0.5,
        effect_threshold=0.1,
        verdict="improvement",
        category_breakdown={
            "math": {
                "sample_size": 2,
                "base_accuracy": 0.5,
                "target_accuracy": 1.0,
                "delta_accuracy": 0.5,
            }
        },
        statistical_evidence={
            "sample_size": 2,
            "delta_accuracy": 0.5,
            "bootstrap": {
                "method": "paired_bootstrap_percentile",
                "confidence_level": 0.95,
                "lower_bound": 0.15,
                "upper_bound": 0.8,
                "crosses_zero": False,
                "iterations": 400,
                "seed": 9,
            },
            "analytical": {
                "method": "paired_difference_normal_approximation",
                "confidence_level": 0.95,
                "lower_bound": 0.12,
                "upper_bound": 0.88,
                "crosses_zero": False,
            },
        },
        release_gate_summary={
            "verdict": "improvement",
            "reason": "delta_exceeds_threshold_with_supported_intervals",
            "effect_threshold": 0.1,
            "delta_accuracy": 0.5,
            "threshold_passed": True,
            "both_intervals_same_side": True,
        },
        duration_seconds=0.25,
        metrics={"eval.compare.win_count": 1.0, "eval.compare.delta_accuracy": 0.5},
        report_path="/tmp/melix/evaluation/runs/eval-compare-1/evaluation-compare-report.md",
    )
    sample = build_evaluation_compare_sample_record(
        job_id="eval-compare-1",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_id="sample-1",
        target_model_id="melix-dev-text-lora-a",
        input_text="2+2?",
        target="4",
        base_extracted_result="4",
        target_extracted_result="4",
        base_raw_response="Answer: 4",
        target_raw_response="Answer: 4",
        base_typed_score=1.0,
        target_typed_score=1.0,
        outcome="score_tie",
        regression_kind="",
        base_time_s=0.01,
        target_time_s=0.02,
        base_extraction_status="extracted",
        target_extraction_status="extracted",
        base_validation_status="validated",
        target_validation_status="validated",
        base_failure_reason="",
        target_failure_reason="",
        base_parse_status="parsed_answer_prefix",
        target_parse_status="parsed_answer_prefix",
        category_label="math",
        subject_label="algebra",
    )

    assert job.to_dict()["target_model_ids"] == ["melix-dev-text-lora-a", "melix-dev-text-lora-b"]
    assert summary.to_dict()["target_model_id"] == "melix-dev-text-lora-a"
    assert summary.to_dict()["effect_threshold"] == 0.1
    assert summary.to_dict()["verdict"] == "improvement"
    assert summary.to_dict()["category_breakdown"]["math"]["delta_accuracy"] == 0.5
    assert summary.to_dict()["statistical_evidence"]["bootstrap"]["iterations"] == 400
    assert summary.to_dict()["release_gate_summary"]["threshold_passed"] is True
    assert sample.to_dict()["category_label"] == "math"
    assert sample.to_dict()["subject_label"] == "algebra"
    assert summary.to_dict()["metrics"][0]["name"] == "eval.compare.delta_accuracy"
    assert sample.to_dict()["base_extracted_result"] == "4"
    assert sample.to_dict()["target_extracted_result"] == "4"
    assert sample.to_dict()["outcome"] == "score_tie"
    assert sample.to_dict()["regression_kind"] == ""
