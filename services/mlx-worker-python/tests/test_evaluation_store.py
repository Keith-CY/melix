from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from worker.productization.evaluation_schemas import (
    EvaluationCompareTargetLineage,
    build_evaluation_compare_job_record,
    build_evaluation_compare_sample_record,
    build_evaluation_compare_summary_record,
    build_evaluation_job_record,
    build_evaluation_result_record,
    build_evaluation_sample_record,
)
from worker.productization.benchmark_export import (
    build_evaluation_samples_csv,
    build_evaluation_summary_csv,
    collect_evaluation_artifacts,
)
from worker.productization.evaluation_store import EvaluationStore


def test_persist_result_writes_expected_artifact_names_and_payloads(tmp_path: Path) -> None:
    store = EvaluationStore()
    jobs_root = tmp_path / "evaluation"
    run_root = jobs_root / "runs" / "eval-local"
    job = build_evaluation_job_record(
        job_id="eval-local",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="HuggingFaceH4/ultrachat_200k",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_size=2,
        scoring_mode="deterministic_accuracy",
        few_shot=4,
        seed=7,
        code_exec_policy="sandboxed",
        parameters={"dataset_root": str(tmp_path / "datasets" / "mmlu-dev")},
        status="completed",
        output_dir=str(run_root),
        created_at_unix_ms=101,
        updated_at_unix_ms=202,
    )
    result = build_evaluation_result_record(
        job_id="eval-local",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_size=2,
        primary_score_name="normalized_exact_match",
        primary_score_value=1.0,
        extraction_success_count=2,
        validation_success_count=2,
        scored_sample_count=2,
        failure_count=0,
        duration_seconds=0.25,
        metrics={"eval.mmlu.accuracy": 1.0},
        report_path=str(run_root / "evaluation-result.json"),
        units={"eval.mmlu.accuracy": "ratio"},
    )
    sample = build_evaluation_sample_record(
        job_id="eval-local",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_id="sample-1",
        system="Return only the final answer.",
        input_text="2+2?",
        target="4",
        raw_response="4",
        extracted_result="4",
        typed_score=1.0,
        time_s=0.01,
        extraction_status="extracted",
        validation_status="validated",
        failure_reason="",
        task_kind="image-text-to-text",
        input_modalities=("text", "image"),
        media_references=("/tmp/cat.png",),
    )

    persisted = store.persist_result(
        jobs_root=jobs_root,
        job=job,
        result=result,
        samples=(sample,),
    )

    assert persisted["job"] == run_root / "evaluation-job.json"
    assert persisted["result"] == run_root / "evaluation-result.json"
    assert persisted["summary_json"] == run_root / "evaluation-summary.json"
    assert persisted["summary_csv"] == run_root / "evaluation-summary.csv"
    assert persisted["samples_jsonl"] == run_root / "evaluation-samples.jsonl"
    assert persisted["samples_csv"] == run_root / "evaluation-samples.csv"
    assert json.loads(persisted["job"].read_text(encoding="utf-8")) == job.to_dict()
    assert json.loads(persisted["result"].read_text(encoding="utf-8")) == result.to_dict()
    assert json.loads(persisted["summary_json"].read_text(encoding="utf-8"))["scored_sample_count"] == 2
    assert json.loads(persisted["samples_jsonl"].read_text(encoding="utf-8").strip()) == sample.to_dict()
    assert persisted["summary_csv"].read_text(encoding="utf-8").startswith(
        "job_id,task_kind,source_repo,model_id,suite_id,dataset_id,primary_score_name,primary_score_value,sample_size,extraction_success_count,validation_success_count,scored_sample_count,failure_count,duration_seconds,created_at_unix_ms\n"
    )
    samples_header = persisted["samples_csv"].read_text(encoding="utf-8").splitlines()[0]
    assert samples_header.startswith(
        "id,task_kind,target,extracted_result,input_text,raw_response,typed_score,time_s,extraction_status,validation_status,failure_reason,input_modalities,media_references,code_language,code_entry_point,code_compile_status,code_runtime_status,code_timeout_status,code_test_status,code_tests_passed,code_tests_total,code_failure_detail,category_label,subject_label"
    )
    assert (
        "sample_render_ms,inference_ms,extraction_ms,validation_ms,scoring_ms,raw_response_chars,extracted_result_chars,failure_stage"
        in samples_header
    )

    export_bundle = collect_evaluation_artifacts(jobs_root)
    assert len(export_bundle["evaluation_summary_rows"]) == 1
    assert build_evaluation_summary_csv(export_bundle).startswith(
        "job_id,model_id,task_kind,source_repo,suite_id,dataset_id,primary_score_name,primary_score_value,sample_size,extraction_success_count,validation_success_count,scored_sample_count,failure_count,effect_threshold,verdict,bootstrap_lower_bound,bootstrap_upper_bound,analytical_lower_bound,analytical_upper_bound,duration_seconds,created_at_unix_ms\r\n"
    )
    export_samples_header = build_evaluation_samples_csv(export_bundle).splitlines()[0]
    assert export_samples_header.startswith(
        "job_id,suite_id,id,task_kind,target,extracted_result,input_text,raw_response,typed_score,time_s,extraction_status,validation_status,failure_reason,input_modalities,media_references,code_language,code_entry_point,code_compile_status,code_runtime_status,code_timeout_status,code_test_status,code_tests_passed,code_tests_total,code_failure_detail,category_label,subject_label"
    )
    assert (
        "sample_render_ms,inference_ms,extraction_ms,validation_ms,scoring_ms,raw_response_chars,extracted_result_chars,failure_stage"
        in export_samples_header
    )


def test_samples_csv_quotes_fields_with_commas_newlines_and_quotes() -> None:
    sample = build_evaluation_sample_record(
        job_id="eval-local",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_id="sample-1",
        system="Return only the final answer.",
        input_text="line 1,\nline 2",
        target='say "hello"',
        raw_response='quoted "response"',
        extracted_result="value,with,comma",
        typed_score=1.0,
        time_s=0.01,
        extraction_status="extracted",
        validation_status="validated",
        failure_reason="",
        task_kind="image-text-to-text",
        input_modalities=("text", "image"),
        media_references=("/tmp/a,1.png", '/tmp/b"2".png'),
    )

    csv_payload = EvaluationStore._samples_csv((sample,))

    assert '"line 1,\nline 2"' in csv_payload
    assert '"say ""hello"""' in csv_payload
    assert '"value,with,comma"' in csv_payload
    assert '"quoted ""response"""' in csv_payload
    assert '"text,image"' in csv_payload
    assert '"/tmp/a,1.png,/tmp/b""2"".png"' in csv_payload


def test_samples_csv_preserves_explicit_zero_char_probes() -> None:
    sample = build_evaluation_sample_record(
        job_id="eval-local",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_id="sample-1",
        system="",
        input_text="Question?",
        target="Answer",
        raw_response="nonempty",
        extracted_result="result",
        typed_score=0.0,
        time_s=0.01,
        extraction_status="extracted",
        validation_status="validated",
        failure_reason="",
        task_kind="text-generation",
        raw_response_chars=0,
        extracted_result_chars=0,
    )

    csv_payload = EvaluationStore._samples_csv((sample,))
    row = next(csv.DictReader(io.StringIO(csv_payload)))

    assert row["raw_response_chars"] == "0"
    assert row["extracted_result_chars"] == "0"


def test_persist_result_exports_code_execution_evidence_fields(tmp_path: Path) -> None:
    store = EvaluationStore()
    jobs_root = tmp_path / "evaluation"
    run_root = jobs_root / "runs" / "eval-code"
    job = build_evaluation_job_record(
        job_id="eval-code",
        model_id="melix-dev-code",
        task_kind="text-generation",
        source_repo="openai_humaneval",
        suite_id="humaneval",
        dataset_id="humaneval.dev.v1",
        sample_size=1,
        scoring_mode="pass_at_1",
        code_exec_policy="sandboxed",
        parameters={"dataset_root": str(tmp_path / "datasets" / "humaneval.dev.v1")},
        status="completed",
        output_dir=str(run_root),
        created_at_unix_ms=101,
        updated_at_unix_ms=202,
    )
    result = build_evaluation_result_record(
        job_id="eval-code",
        suite_id="humaneval",
        dataset_id="humaneval.dev.v1",
        sample_size=1,
        primary_score_name="typed_score_mean",
        primary_score_value=1.0,
        extraction_success_count=1,
        validation_success_count=1,
        scored_sample_count=1,
        failure_count=0,
        duration_seconds=0.25,
        metrics={
            "eval.humaneval.typed_score_mean": 1.0,
            "eval.humaneval.code_exec_pass_count": 1.0,
        },
        report_path=str(run_root / "evaluation-result.json"),
        units={
            "eval.humaneval.typed_score_mean": "ratio",
            "eval.humaneval.code_exec_pass_count": "count",
        },
    )
    sample = build_evaluation_sample_record(
        job_id="eval-code",
        suite_id="humaneval",
        dataset_id="humaneval.dev.v1",
        sample_id="sample-1",
        system="Return only executable Python code.",
        input_text="Write identity(x) that returns x.",
        target="identity",
        raw_response="```python\ndef identity(x):\n    return x\n```",
        extracted_result="def identity(x):\n    return x",
        typed_score=1.0,
        time_s=0.02,
        extraction_status="extracted",
        validation_status="validated",
        failure_reason="",
        task_kind="text-generation",
        code_language="python",
        code_entry_point="identity",
        code_compile_status="compiled",
        code_runtime_status="ok",
        code_timeout_status="ok",
        code_test_status="passed",
        code_tests_passed=2,
        code_tests_total=2,
        code_failure_detail="",
    )

    persisted = store.persist_result(
        jobs_root=jobs_root,
        job=job,
        result=result,
        samples=(sample,),
    )

    sample_payload = json.loads(persisted["samples_jsonl"].read_text(encoding="utf-8").strip())
    assert sample_payload["code_language"] == "python"
    assert sample_payload["code_entry_point"] == "identity"
    assert sample_payload["code_compile_status"] == "compiled"
    assert sample_payload["code_runtime_status"] == "ok"
    assert sample_payload["code_timeout_status"] == "ok"
    assert sample_payload["code_test_status"] == "passed"
    assert sample_payload["code_tests_passed"] == 2
    assert sample_payload["code_tests_total"] == 2
    samples_header = persisted["samples_csv"].read_text(encoding="utf-8").splitlines()[0]
    assert samples_header.startswith(
        "id,task_kind,target,extracted_result,input_text,raw_response,typed_score,time_s,extraction_status,validation_status,failure_reason,input_modalities,media_references,code_language,code_entry_point,code_compile_status,code_runtime_status,code_timeout_status,code_test_status,code_tests_passed,code_tests_total,code_failure_detail,category_label,subject_label"
    )
    assert (
        "sample_render_ms,inference_ms,extraction_ms,validation_ms,scoring_ms,raw_response_chars,extracted_result_chars,failure_stage"
        in samples_header
    )

    export_bundle = collect_evaluation_artifacts(jobs_root)
    export_samples_header = build_evaluation_samples_csv(export_bundle).splitlines()[0]
    assert export_samples_header.startswith(
        "job_id,suite_id,id,task_kind,target,extracted_result,input_text,raw_response,typed_score,time_s,extraction_status,validation_status,failure_reason,input_modalities,media_references,code_language,code_entry_point,code_compile_status,code_runtime_status,code_timeout_status,code_test_status,code_tests_passed,code_tests_total,code_failure_detail,category_label,subject_label"
    )
    assert (
        "sample_render_ms,inference_ms,extraction_ms,validation_ms,scoring_ms,raw_response_chars,extracted_result_chars,failure_stage"
        in export_samples_header
    )


def test_persist_compare_result_writes_expected_compare_artifact_names_and_payloads(
    tmp_path: Path,
) -> None:
    store = EvaluationStore()
    jobs_root = tmp_path / "evaluation"
    run_root = jobs_root / "runs" / "eval-compare-1"
    compare_job = build_evaluation_compare_job_record(
        job_id="eval-compare-1",
        base_model_id="melix-dev-text",
        target_model_ids=("melix-dev-text-lora-a",),
        task_kind="text-generation",
        source_repo="HuggingFaceH4/ultrachat_200k",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_size=2,
        scoring_mode="multiple_choice_accuracy",
        parameters={"compare_mode": "base_vs_targets"},
        status="completed",
        output_dir=str(run_root),
        created_at_unix_ms=101,
        updated_at_unix_ms=202,
    )
    compare_summary = build_evaluation_compare_summary_record(
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
        report_path=str(run_root / "evaluation-compare-report.md"),
    )
    compare_sample = build_evaluation_compare_sample_record(
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

    persisted = store.persist_compare_result(
        jobs_root=jobs_root,
        job=compare_job,
        summaries=(compare_summary,),
        samples=(compare_sample,),
    )

    assert persisted["job"] == run_root / "evaluation-compare-job.json"
    assert persisted["summary_json"] == run_root / "evaluation-compare-summary.json"
    assert persisted["summary_csv"] == run_root / "evaluation-compare-summary.csv"
    assert persisted["samples_jsonl"] == run_root / "evaluation-compare-samples.jsonl"
    assert persisted["report_markdown"] == run_root / "evaluation-compare-report.md"
    assert json.loads(persisted["job"].read_text(encoding="utf-8")) == compare_job.to_dict()
    summary_payload = json.loads(persisted["summary_json"].read_text(encoding="utf-8"))
    assert summary_payload["job_id"] == "eval-compare-1"
    assert summary_payload["target_summaries"][0]["target_model_id"] == "melix-dev-text-lora-a"
    assert summary_payload["target_summaries"][0]["verdict"] == "improvement"
    assert summary_payload["target_summaries"][0]["category_breakdown"]["math"]["sample_size"] == 2
    assert summary_payload["target_summaries"][0]["statistical_evidence"]["bootstrap"]["iterations"] == 400
    assert (
        summary_payload["target_summaries"][0]["release_gate_summary"]["both_intervals_same_side"]
        is True
    )
    assert json.loads(persisted["samples_jsonl"].read_text(encoding="utf-8").strip()) == compare_sample.to_dict()
    assert persisted["summary_csv"].read_text(encoding="utf-8").startswith(
        "job_id,base_model_id,target_model_id,suite_id,dataset_id,sample_size,win_count,loss_count,tie_count,regression_count,base_accuracy,target_accuracy,delta_accuracy,effect_threshold,verdict,bootstrap_lower_bound,bootstrap_upper_bound,analytical_lower_bound,analytical_upper_bound,duration_seconds,created_at_unix_ms,target_adapter_manifest_path,target_adapter_set_hash\n"
    )
    assert persisted["report_markdown"].read_text(encoding="utf-8").startswith("# Melix Evaluation Compare\n")
    report_markdown = persisted["report_markdown"].read_text(encoding="utf-8")
    assert "Verdict" in report_markdown
    assert "Bootstrap CI" in report_markdown
    assert "Analytical CI" in report_markdown
    assert "Category Breakdown" in report_markdown


def test_persist_compare_result_preserves_code_execution_evidence(tmp_path: Path) -> None:
    store = EvaluationStore()
    jobs_root = tmp_path / "evaluation"
    run_root = jobs_root / "runs" / "eval-compare-code"
    compare_job = build_evaluation_compare_job_record(
        job_id="eval-compare-code",
        base_model_id="melix-dev-code-base",
        target_model_ids=("melix-dev-code-target",),
        task_kind="text-generation",
        source_repo="openai_humaneval",
        suite_id="humaneval",
        dataset_id="humaneval.dev.v1",
        sample_size=1,
        scoring_mode="pass_at_1",
        parameters={"compare_mode": "base_vs_targets", "code_exec_policy": "sandboxed"},
        status="completed",
        output_dir=str(run_root),
        created_at_unix_ms=101,
        updated_at_unix_ms=202,
    )
    compare_summary = build_evaluation_compare_summary_record(
        job_id="eval-compare-code",
        base_model_id="melix-dev-code-base",
        target_model_id="melix-dev-code-target",
        suite_id="humaneval",
        dataset_id="humaneval.dev.v1",
        sample_size=1,
        scoring_mode="pass_at_1",
        win_count=1,
        loss_count=0,
        tie_count=0,
        regression_count=0,
        base_accuracy=0.0,
        target_accuracy=1.0,
        delta_accuracy=1.0,
        effect_threshold=0.1,
        verdict="improvement",
        category_breakdown={
            "code": {
                "sample_size": 1,
                "base_accuracy": 0.0,
                "target_accuracy": 1.0,
                "delta_accuracy": 1.0,
            }
        },
        statistical_evidence={
            "sample_size": 1,
            "delta_accuracy": 1.0,
            "bootstrap": {
                "method": "paired_bootstrap_percentile",
                "confidence_level": 0.95,
                "lower_bound": 1.0,
                "upper_bound": 1.0,
                "crosses_zero": False,
                "iterations": 400,
                "seed": 9,
            },
            "analytical": {
                "method": "paired_difference_normal_approximation",
                "confidence_level": 0.95,
                "lower_bound": 1.0,
                "upper_bound": 1.0,
                "crosses_zero": False,
            },
        },
        release_gate_summary={
            "verdict": "improvement",
            "reason": "delta_exceeds_threshold_with_supported_intervals",
            "effect_threshold": 0.1,
            "delta_accuracy": 1.0,
            "threshold_passed": True,
            "both_intervals_same_side": True,
        },
        duration_seconds=0.25,
        metrics={"eval.compare.delta_accuracy": 1.0},
        report_path=str(run_root / "evaluation-compare-report.md"),
    )
    compare_sample = build_evaluation_compare_sample_record(
        job_id="eval-compare-code",
        suite_id="humaneval",
        dataset_id="humaneval.dev.v1",
        sample_id="sample-1",
        target_model_id="melix-dev-code-target",
        input_text="Write identity(x) that returns x.",
        target="identity",
        base_extracted_result="def identity(x):\n    return None",
        target_extracted_result="def identity(x):\n    return x",
        base_raw_response="```python\ndef identity(x):\n    return None\n```",
        target_raw_response="```python\ndef identity(x):\n    return x\n```",
        base_typed_score=0.0,
        target_typed_score=1.0,
        outcome="win",
        regression_kind="",
        base_time_s=0.01,
        target_time_s=0.02,
        base_extraction_status="extracted",
        target_extraction_status="extracted",
        base_validation_status="validated",
        target_validation_status="validated",
        base_failure_reason="AssertionError",
        target_failure_reason="",
        base_parse_status="parsed_code_block",
        target_parse_status="parsed_code_block",
        code_language="python",
        code_entry_point="identity",
        base_code_compile_status="compiled",
        target_code_compile_status="compiled",
        base_code_runtime_status="ok",
        target_code_runtime_status="ok",
        base_code_timeout_status="ok",
        target_code_timeout_status="ok",
        base_code_test_status="failed",
        target_code_test_status="passed",
        base_code_tests_passed=0,
        target_code_tests_passed=2,
        base_code_tests_total=2,
        target_code_tests_total=2,
        base_code_failure_detail="AssertionError",
        target_code_failure_detail="",
    )

    persisted = store.persist_compare_result(
        jobs_root=jobs_root,
        job=compare_job,
        summaries=(compare_summary,),
        samples=(compare_sample,),
    )

    sample_payload = json.loads(persisted["samples_jsonl"].read_text(encoding="utf-8").strip())
    assert sample_payload["code_language"] == "python"
    assert sample_payload["code_entry_point"] == "identity"
    assert sample_payload["base_code_test_status"] == "failed"
    assert sample_payload["target_code_test_status"] == "passed"
    assert sample_payload["base_code_failure_detail"] == "AssertionError"


def test_compare_job_persists_adapter_target_lineage(tmp_path: Path) -> None:
    # Module 2 — a compare job mixing a registered target with an adapter
    # target persists per-target lineage so downstream consumers know
    # which adapter produced which target column.
    store = EvaluationStore()
    jobs_root = tmp_path / "evaluation"
    run_root = jobs_root / "runs" / "eval-compare-adapter"
    compare_job = build_evaluation_compare_job_record(
        job_id="eval-compare-adapter",
        base_model_id="melix-dev-text",
        target_model_ids=(
            "melix-dev-text-lora-registered",
            "melix-dev-text-lora-abcd1234-compare-0042",
        ),
        task_kind="text-generation",
        source_repo="mmlu",
        suite_id="mmlu",
        dataset_id="mmlu.dev.v1",
        sample_size=2,
        scoring_mode="multiple_choice_accuracy",
        parameters={
            "compare_mode": "base_vs_targets",
            "compare_target_model_ids": "melix-dev-text-lora-registered",
            "compare_target_adapter_manifest_paths": "/tmp/melix-adapters/demo.adapter.json",
        },
        status="completed",
        output_dir=str(run_root),
        created_at_unix_ms=1000,
        updated_at_unix_ms=2000,
        target_lineage=(
            EvaluationCompareTargetLineage(
                target_model_id="melix-dev-text-lora-registered",
                materialization_kind="registered",
            ),
            EvaluationCompareTargetLineage(
                target_model_id="melix-dev-text-lora-abcd1234-compare-0042",
                materialization_kind="ephemeral_adapter",
                adapter_manifest_path="/tmp/melix-adapters/demo.adapter.json",
                adapter_weights_path="/tmp/melix-adapters/weights/adapters.safetensors",
                adapter_set_hash="abcd1234efg5678",
                derived_from_model_id="melix-dev-text",
            ),
        ),
    )

    persisted = store.persist_compare_result(
        jobs_root=jobs_root,
        job=compare_job,
        summaries=(),
        samples=(),
    )

    # Job JSON round-trips the lineage entries.
    job_payload = json.loads(persisted["job"].read_text(encoding="utf-8"))
    assert "target_lineage" in job_payload
    assert len(job_payload["target_lineage"]) == 2
    registered, ephemeral = job_payload["target_lineage"]
    assert registered["materialization_kind"] == "registered"
    assert registered["adapter_manifest_path"] == ""
    assert ephemeral["materialization_kind"] == "ephemeral_adapter"
    assert ephemeral["adapter_manifest_path"] == "/tmp/melix-adapters/demo.adapter.json"
    assert ephemeral["adapter_set_hash"] == "abcd1234efg5678"
    assert ephemeral["derived_from_model_id"] == "melix-dev-text"


def test_compare_summary_csv_carries_adapter_columns_per_target(tmp_path: Path) -> None:
    # Module 2 — the compare summary CSV gains two trailing columns
    # (target_adapter_manifest_path, target_adapter_set_hash) that are
    # empty for registered targets and populated for adapter targets.
    store = EvaluationStore()
    jobs_root = tmp_path / "evaluation"
    run_root = jobs_root / "runs" / "eval-compare-csv"
    adapter_target_id = "melix-dev-text-lora-beefface-compare-0003"
    compare_job = build_evaluation_compare_job_record(
        job_id="eval-compare-csv",
        base_model_id="melix-dev-text",
        target_model_ids=("melix-dev-text-lora-registered", adapter_target_id),
        task_kind="text-generation",
        source_repo="mmlu",
        suite_id="mmlu",
        dataset_id="mmlu.dev.v1",
        sample_size=1,
        scoring_mode="multiple_choice_accuracy",
        parameters={},
        status="completed",
        output_dir=str(run_root),
        created_at_unix_ms=1000,
        updated_at_unix_ms=1000,
        target_lineage=(
            EvaluationCompareTargetLineage(
                target_model_id="melix-dev-text-lora-registered",
                materialization_kind="registered",
            ),
            EvaluationCompareTargetLineage(
                target_model_id=adapter_target_id,
                materialization_kind="ephemeral_adapter",
                adapter_manifest_path="/tmp/melix-adapters/bee.adapter.json",
                adapter_set_hash="beefface12345678",
            ),
        ),
    )
    registered_summary = build_evaluation_compare_summary_record(
        job_id="eval-compare-csv",
        base_model_id="melix-dev-text",
        target_model_id="melix-dev-text-lora-registered",
        suite_id="mmlu",
        dataset_id="mmlu.dev.v1",
        sample_size=1,
        scoring_mode="multiple_choice_accuracy",
        win_count=0,
        loss_count=0,
        tie_count=1,
        regression_count=0,
        base_accuracy=1.0,
        target_accuracy=1.0,
        delta_accuracy=0.0,
        effect_threshold=0.1,
        verdict="tie",
        category_breakdown={},
        statistical_evidence={"bootstrap": {}, "analytical": {}},
        release_gate_summary={"verdict": "tie"},
        duration_seconds=0.1,
        metrics={},
        units={},
        report_path=str(run_root / "evaluation-compare-report.md"),
    )
    adapter_summary = build_evaluation_compare_summary_record(
        job_id="eval-compare-csv",
        base_model_id="melix-dev-text",
        target_model_id=adapter_target_id,
        suite_id="mmlu",
        dataset_id="mmlu.dev.v1",
        sample_size=1,
        scoring_mode="multiple_choice_accuracy",
        win_count=0,
        loss_count=0,
        tie_count=1,
        regression_count=0,
        base_accuracy=1.0,
        target_accuracy=1.0,
        delta_accuracy=0.0,
        effect_threshold=0.1,
        verdict="tie",
        category_breakdown={},
        statistical_evidence={"bootstrap": {}, "analytical": {}},
        release_gate_summary={"verdict": "tie"},
        duration_seconds=0.1,
        metrics={},
        units={},
        report_path=str(run_root / "evaluation-compare-report.md"),
    )

    persisted = store.persist_compare_result(
        jobs_root=jobs_root,
        job=compare_job,
        summaries=(registered_summary, adapter_summary),
        samples=(),
    )

    csv_body = persisted["summary_csv"].read_text(encoding="utf-8")
    lines = csv_body.strip().split("\n")
    header, registered_row, adapter_row = lines[0], lines[1], lines[2]
    assert header.endswith("target_adapter_manifest_path,target_adapter_set_hash")
    assert registered_row.endswith(",,")  # both adapter columns empty
    assert adapter_row.endswith(",/tmp/melix-adapters/bee.adapter.json,beefface12345678")
