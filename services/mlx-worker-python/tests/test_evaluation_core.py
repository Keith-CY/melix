from __future__ import annotations

import json
from pathlib import Path

from packages.protocol.python.worker.v1 import maintenance_pb2
from worker.engine.evaluation_core import EvaluationCore
from worker.grpc_server import WorkerMaintenanceService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry


def test_run_local_suite_executes_packaged_dataset_and_persists_result(tmp_path: Path) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        samples=(
            {"prompt": "2+2?", "expected": "4"},
            {"prompt": "3+3?", "expected": "6"},
        ),
    )
    jobs_root = tmp_path / "runs" / "mmlu"
    runner = EvaluationCore(jobs_root=jobs_root)

    run = runner.run_local_suite(
        model_id="melix-dev-text",
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=2,
        few_shot=4,
        seed=7,
        scoring_mode="multiple_choice_accuracy",
        code_exec_policy="sandboxed",
    )

    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert run.job.dataset_id == "mmlu-dev"
    assert run.job.sample_size == 2
    assert run.job.task_kind == "text-generation"
    assert run.job.few_shot == 4
    assert run.job.seed == 7
    assert run.job.scoring_mode == "multiple_choice_accuracy"
    assert run.job.code_exec_policy == "sandboxed"
    assert metrics["eval.mmlu.accuracy"] == 1.0
    assert metrics["eval.mmlu.correct_count"] == 2.0
    assert metrics["eval.mmlu.incorrect_count"] == 0.0
    assert metrics["eval.mmlu.duration_seconds"] >= 0.0
    assert run.result.score_name == "accuracy"
    assert run.result.score_value == 1.0
    assert run.result.correct_count == 2
    assert run.result.incorrect_count == 0
    assert run.result.duration_seconds >= 0.0
    assert run.job.job_id == "eval-0001"
    assert run.persisted_paths["job"] == jobs_root / "runs" / "eval-0001" / "evaluation-job.json"
    assert run.persisted_paths["result"] == jobs_root / "runs" / "eval-0001" / "evaluation-result.json"
    assert run.persisted_paths["summary_json"] == jobs_root / "runs" / "eval-0001" / "evaluation-summary.json"
    assert run.persisted_paths["summary_csv"] == jobs_root / "runs" / "eval-0001" / "evaluation-summary.csv"
    assert run.persisted_paths["samples_jsonl"] == jobs_root / "runs" / "eval-0001" / "evaluation-samples.jsonl"
    assert json.loads(run.persisted_paths["job"].read_text(encoding="utf-8")) == run.job.to_dict()
    assert json.loads(run.persisted_paths["result"].read_text(encoding="utf-8")) == run.result.to_dict()
    assert json.loads(run.persisted_paths["summary_json"].read_text(encoding="utf-8"))["score_name"] == "accuracy"
    assert "job_id,task_kind,source_repo,model_id,suite_id,dataset_id,score_name,score_value,sample_size,correct_count,incorrect_count,duration_seconds,created_at_unix_ms" in run.persisted_paths["summary_csv"].read_text(encoding="utf-8")
    persisted_samples = [
        json.loads(line)
        for line in run.persisted_paths["samples_jsonl"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert persisted_samples == [sample.to_dict() for sample in run.samples]
    assert len(run.samples) == 2
    assert run.samples[0].sample_id == "1"
    assert run.samples[0].correct is True

    queue_payload = json.loads((jobs_root / "queue" / f"{run.job.job_id}.json").read_text(encoding="utf-8"))
    assert queue_payload["job_kind"] == "evaluation"
    assert queue_payload["status"] == "completed"
    assert queue_payload["parameters"]["sample_size"] == "2"
    assert queue_payload["started_at_unix_ms"] > 0
    assert queue_payload["completed_at_unix_ms"] > 0


def test_run_local_suite_respects_sample_size_for_deterministic_accuracy(tmp_path: Path) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        samples=(
            {"prompt": "2+2?", "expected": "4"},
            {"prompt": "capital of france?", "expected": "Paris"},
            {"prompt": "3+3?", "expected": "6"},
        ),
    )
    runner = EvaluationCore()

    run = runner.run_local_suite(
        model_id="melix-dev-text",
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=2,
    )

    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert run.job.sample_size == 2
    assert metrics["eval.mmlu.accuracy"] == 0.5
    assert metrics["eval.mmlu.correct_count"] == 1.0
    assert run.persisted_paths == {}
    assert len(run.samples) == 2


def test_run_local_suite_supports_additional_score_modes_and_job_metadata(tmp_path: Path) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mbpp-dev",
        suite_id="mbpp",
        samples=(
            {"id": "sample-1", "question": "2+2?", "answer": "4"},
        ),
    )
    jobs_root = tmp_path / "runs" / "mbpp"
    runner = EvaluationCore(jobs_root=jobs_root)

    run = runner.run_local_suite(
        model_id="melix-dev-text",
        suite_id="mbpp",
        dataset_root=dataset_root,
        sample_size=1,
        parameters={
            "task_kind": "text-generation",
            "source_repo": "openai_humaneval",
        },
    )

    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert run.job.job_id == "eval-0001"
    assert run.job.source_repo == "openai_humaneval"
    assert run.job.output_dir == str(jobs_root / "runs" / "eval-0001")
    assert run.job.scoring_mode == "pass_at_1"
    assert run.job.few_shot == 0
    assert run.job.seed == 0
    assert run.job.code_exec_policy == ""
    assert metrics["eval.mbpp.pass_at_1"] == 1.0


def test_run_local_suite_falls_back_to_zero_for_invalid_numeric_controls(tmp_path: Path) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        samples=(
            {"prompt": "2+2?", "expected": "4"},
        ),
    )
    runner = EvaluationCore()

    run = runner.run_local_suite(
        model_id="melix-dev-text",
        suite_id="mmlu",
        dataset_root=dataset_root,
        sample_size=1,
        parameters={
            "few_shot": "invalid",
            "seed": "also-invalid",
            "code_exec_policy": "sandboxed",
        },
    )

    assert run.job.few_shot == 0
    assert run.job.seed == 0
    assert run.job.code_exec_policy == "sandboxed"
    assert run.job.parameters["few_shot"] == "0"
    assert run.job.parameters["seed"] == "0"


def test_worker_maintenance_service_stages_evaluation_core_with_configured_jobs_root(
    tmp_path: Path,
) -> None:
    evaluation_jobs_root = tmp_path / "model-ops" / "evaluation-runs"
    service = WorkerMaintenanceService(
        WorkerRegistry(model_catalog=WorkerModelCatalog()),
        jobs_root=tmp_path / "model-ops",
        evaluation_jobs_root=evaluation_jobs_root,
    )

    assert service._evaluation_jobs_root == evaluation_jobs_root.resolve()
    assert isinstance(service._evaluation_core, EvaluationCore)
    assert service._evaluation_core._jobs_root == evaluation_jobs_root.resolve()


def test_worker_maintenance_service_run_evaluation_maps_request_task_metadata(
    tmp_path: Path,
) -> None:
    dataset_root = _write_dataset_package(
        tmp_path=tmp_path,
        dataset_id="mmlu-dev",
        suite_id="mmlu",
        samples=(
            {"prompt": "2+2?", "expected": "4"},
        ),
    )
    service = WorkerMaintenanceService(
        WorkerRegistry(model_catalog=WorkerModelCatalog()),
        jobs_root=tmp_path / "model-ops",
    )

    response = service.RunEvaluation(
        maintenance_pb2.RunEvaluationRequest(
            model_handle="melix-dev-text::explicit",
            suite_id="mmlu",
            dataset_id="mmlu-dev",
            dataset_root=str(dataset_root),
            sample_size=1,
            task_kind="text-generation",
            source_repo="unsloth/gemma-4-E4B-it-MLX-8bit",
            parameters={"judge": "deterministic"},
        ),
        context=None,
    )

    assert response.ok is True
    assert response.job.model_id == "melix-dev-text"
    assert response.job.task_kind == "text-generation"
    assert response.job.source_repo == "unsloth/gemma-4-E4B-it-MLX-8bit"
    assert response.job.parameters["judge"] == "deterministic"
    assert response.job.parameters["task_kind"] == "text-generation"
    assert response.job.parameters["source_repo"] == "unsloth/gemma-4-E4B-it-MLX-8bit"
    assert response.job.output_dir.endswith("/runs/eval-0001")
    assert response.job.created_at_unix_ms > 0
    assert response.job.updated_at_unix_ms > 0
    assert response.results[0].job_id == response.job.job_id
    assert response.results[0].dataset_id == "mmlu-dev"


def _write_dataset_package(
    *,
    tmp_path: Path,
    dataset_id: str,
    suite_id: str,
    samples: tuple[dict[str, str], ...],
) -> Path:
    dataset_root = tmp_path / "datasets" / dataset_id
    dataset_root.mkdir(parents=True)
    (dataset_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.evaluation_dataset_package.v1",
                "dataset_id": dataset_id,
                "suite_id": suite_id,
                "version": "2026-03-31",
                "sample_count": len(samples),
                "split": "validation",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (dataset_root / "samples.jsonl").write_text(
        "\n".join(json.dumps(sample) for sample in samples) + "\n",
        encoding="utf-8",
    )
    return dataset_root
