from __future__ import annotations

import json
from pathlib import Path

from worker.productization.evaluation_schemas import (
    build_evaluation_job_record,
    build_evaluation_result_record,
)
from worker.productization.evaluation_store import EvaluationStore


def test_persist_result_writes_expected_artifact_names_and_payloads(tmp_path: Path) -> None:
    store = EvaluationStore()
    jobs_root = tmp_path / "evaluation"
    job = build_evaluation_job_record(
        job_id="eval-local",
        model_id="melix-dev-text",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_size=2,
        scoring_mode="deterministic_accuracy",
        parameters={"dataset_root": str(tmp_path / "datasets" / "mmlu-dev")},
        status="completed",
    )
    result = build_evaluation_result_record(
        job_id="eval-local",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_size=2,
        metrics={"eval.mmlu.accuracy": 1.0},
        report_path=str(jobs_root / "evaluation-result.json"),
    )

    persisted = store.persist_result(
        jobs_root=jobs_root,
        job=job,
        result=result,
    )

    assert persisted["job"] == jobs_root / "evaluation-job.json"
    assert persisted["result"] == jobs_root / "evaluation-result.json"
    assert json.loads(persisted["job"].read_text(encoding="utf-8")) == job.to_dict()
    assert json.loads(persisted["result"].read_text(encoding="utf-8")) == result.to_dict()
