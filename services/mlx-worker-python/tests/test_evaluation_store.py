from __future__ import annotations

import json
from pathlib import Path

from worker.productization.evaluation_schemas import (
    build_evaluation_job_record,
    build_evaluation_result_record,
    build_evaluation_sample_record,
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
    )

    persisted = store.persist_result(
        jobs_root=jobs_root,
        job=job,
        result=result,
        samples=(sample,),
    )

    assert persisted["job"] == run_root / "evaluation-job.json"
    assert persisted["result"] == run_root / "evaluation-result.json"
    assert persisted["samples_jsonl"] == run_root / "evaluation-samples.jsonl"
    assert persisted["samples_csv"] == run_root / "evaluation-samples.csv"
    assert json.loads(persisted["job"].read_text(encoding="utf-8")) == job.to_dict()
    assert json.loads(persisted["result"].read_text(encoding="utf-8")) == result.to_dict()
    assert json.loads(persisted["samples_jsonl"].read_text(encoding="utf-8").strip()) == sample.to_dict()
    assert persisted["samples_csv"].read_text(encoding="utf-8").startswith(
        "id,correct,expected,predicted,question,raw_response,time_s,parse_status\n"
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
    )

    csv_payload = EvaluationStore._samples_csv((sample,))

    assert '"line 1,\nline 2"' in csv_payload
    assert '"say ""hello"""' in csv_payload
    assert '"value,with,comma"' in csv_payload
    assert '"quoted ""response"""' in csv_payload
