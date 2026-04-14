from __future__ import annotations

import json
from pathlib import Path

from worker.productization.evaluation_schemas import (
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
        score_name="accuracy",
        score_value=1.0,
        correct_count=2,
        incorrect_count=0,
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
        question="2+2?",
        expected="4",
        predicted="4",
        raw_response="4",
        correct=True,
        time_s=0.01,
        parse_status="parsed",
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
    assert json.loads(persisted["summary_json"].read_text(encoding="utf-8"))["correct_count"] == 2
    assert json.loads(persisted["samples_jsonl"].read_text(encoding="utf-8").strip()) == sample.to_dict()
    assert persisted["summary_csv"].read_text(encoding="utf-8").startswith(
        "job_id,task_kind,source_repo,model_id,suite_id,dataset_id,score_name,score_value,sample_size,correct_count,incorrect_count,duration_seconds,created_at_unix_ms\n"
    )
    assert persisted["samples_csv"].read_text(encoding="utf-8").startswith(
        "id,task_kind,correct,expected,predicted,question,raw_response,time_s,parse_status,input_modalities,media_references,code_language,code_entry_point,code_compile_status,code_runtime_status,code_timeout_status,code_test_status,code_tests_passed,code_tests_total,code_failure_detail\n"
    )

    export_bundle = collect_evaluation_artifacts(jobs_root)
    assert len(export_bundle["evaluation_summary_rows"]) == 1
    assert build_evaluation_summary_csv(export_bundle).startswith(
        "job_id,task_kind,source_repo,model_id,suite_id,dataset_id,score_name,score_value,sample_size,correct_count,incorrect_count,duration_seconds,created_at_unix_ms\r\n"
    )
    assert build_evaluation_samples_csv(export_bundle).startswith(
        "job_id,suite_id,id,correct,expected,predicted,question,raw_response,time_s,parse_status,code_language,code_entry_point,code_compile_status,code_runtime_status,code_timeout_status,code_test_status,code_tests_passed,code_tests_total,code_failure_detail\r\n"
    )


def test_samples_csv_quotes_fields_with_commas_newlines_and_quotes() -> None:
    sample = build_evaluation_sample_record(
        job_id="eval-local",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_id="sample-1",
        question="line 1,\nline 2",
        expected='say "hello"',
        predicted="value,with,comma",
        raw_response='quoted "response"',
        correct=True,
        time_s=0.01,
        parse_status="parsed",
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
        score_name="pass_at_1",
        score_value=1.0,
        correct_count=1,
        incorrect_count=0,
        duration_seconds=0.25,
        metrics={
            "eval.humaneval.pass_at_1": 1.0,
            "eval.humaneval.code_exec_pass_count": 1.0,
        },
        report_path=str(run_root / "evaluation-result.json"),
        units={
            "eval.humaneval.pass_at_1": "ratio",
            "eval.humaneval.code_exec_pass_count": "count",
        },
    )
    sample = build_evaluation_sample_record(
        job_id="eval-code",
        suite_id="humaneval",
        dataset_id="humaneval.dev.v1",
        sample_id="sample-1",
        question="Write identity(x) that returns x.",
        expected="identity",
        predicted="def identity(x):\n    return x",
        raw_response="```python\ndef identity(x):\n    return x\n```",
        correct=True,
        time_s=0.02,
        parse_status="parsed_code_block",
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
    assert persisted["samples_csv"].read_text(encoding="utf-8").startswith(
        "id,task_kind,correct,expected,predicted,question,raw_response,time_s,parse_status,input_modalities,media_references,code_language,code_entry_point,code_compile_status,code_runtime_status,code_timeout_status,code_test_status,code_tests_passed,code_tests_total,code_failure_detail\n"
    )

    export_bundle = collect_evaluation_artifacts(jobs_root)
    assert build_evaluation_samples_csv(export_bundle).startswith(
        "job_id,suite_id,id,correct,expected,predicted,question,raw_response,time_s,parse_status,code_language,code_entry_point,code_compile_status,code_runtime_status,code_timeout_status,code_test_status,code_tests_passed,code_tests_total,code_failure_detail\r\n"
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
        question="2+2?",
        expected="4",
        base_predicted="4",
        target_predicted="4",
        base_raw_response="Answer: 4",
        target_raw_response="Answer: 4",
        base_correct=True,
        target_correct=True,
        outcome="tie",
        regression=False,
        base_time_s=0.01,
        target_time_s=0.02,
        base_parse_status="parsed_answer_prefix",
        target_parse_status="parsed_answer_prefix",
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
    assert json.loads(persisted["samples_jsonl"].read_text(encoding="utf-8").strip()) == compare_sample.to_dict()
    assert persisted["summary_csv"].read_text(encoding="utf-8").startswith(
        "job_id,base_model_id,target_model_id,suite_id,dataset_id,sample_size,win_count,loss_count,tie_count,regression_count,base_accuracy,target_accuracy,delta_accuracy,duration_seconds,created_at_unix_ms\n"
    )
    assert persisted["report_markdown"].read_text(encoding="utf-8").startswith("# Melix Evaluation Compare\n")


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
        question="Write identity(x) that returns x.",
        expected="identity",
        base_predicted="def identity(x):\n    return None",
        target_predicted="def identity(x):\n    return x",
        base_raw_response="```python\ndef identity(x):\n    return None\n```",
        target_raw_response="```python\ndef identity(x):\n    return x\n```",
        base_correct=False,
        target_correct=True,
        outcome="win",
        regression=False,
        base_time_s=0.01,
        target_time_s=0.02,
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
