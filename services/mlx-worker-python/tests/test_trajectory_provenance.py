from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest

from packages.protocol.python.worker.v1 import common_pb2, maintenance_pb2
from worker.engine.maintenance_core import MaintenanceCore
from worker.grpc_server import WorkerMaintenanceService
from worker.model_ops.adapter_activation_pipeline import AdapterActivationPipeline
from worker.model_ops.lora_training_pipeline import (
    LoRATrainingPipeline,
    _alignment_manifest_payload,
)
from worker.model_ops.mlx_lm_runner import (
    MLXLMRunner,
    TrainingMetrics,
    TrainingRequest,
    TrainingResult,
)
from worker.model_ops import training_config as training_config_module
from worker.model_ops import mlx_lm_runner as mlx_lm_runner_module
from worker.model_ops.training_dataset import (
    ResolvedTrainingDatasetPackage,
    TrainingDatasetPackage,
)
from worker.model_registry.catalog import WorkerModelCatalog
from worker.productization.benchmark_export import (
    build_evaluation_samples_csv,
    collect_evaluation_artifacts,
)
from worker.productization.evaluation_schemas import (
    build_evaluation_job_record,
    build_evaluation_result_record,
    build_evaluation_sample_record,
)
from worker.productization.evaluation_store import EvaluationStore
from worker.registry import WorkerRegistry
from worker.runtime.deterministic_backend import DeterministicTextBackend
from worker.runtime.mlx_text_runtime import MLXTextRuntime
from worker.trajectory_provenance import (
    load_trajectory_provenance_from_snapshot_manifest,
)
from telemetry_fixtures import fixture_telemetry_collector


def _write_agentic_dataset_package(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    sample = {
        "trace_id": "trace-001",
        "question": "Use tools before answering.",
        "turns": [
            {"role": "user", "content": "Read the page."},
            {
                "role": "assistant",
                "tool_call": {
                    "id": "visit-1",
                    "name": "visit",
                    "arguments": {"url": "fixture://doc"},
                },
            },
            {
                "role": "tool",
                "tool_call_id": "visit-1",
                "observation": {"text": "The answer is MELIX."},
            },
            {"role": "assistant", "content": "MELIX"},
        ],
        "final_answer": "MELIX",
        "reward": {"total": 1.0},
        "fatal_stage": "",
    }
    manifest = {
        "schema_version": "melix.training_dataset_package.v1",
        "dataset_id": "agentic-package",
        "format": "agentic_tool_trace",
        "sample_count": 1,
        "version": "2026-05-19",
        "trajectory_schema_version": "melix.agentic_tool_trace.v1",
        "toolset_version": "melix.agentic_tools.builtin.v1",
        "registry_schema_version": "melix.agentic_tool_registry.v1",
        "reward_policy_id": "reward-policy.v1",
        "source_dataset_id": "opensearch-vl.dev",
        "source_split": "train",
    }
    (root / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    (root / "samples.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")
    return root


def _text_model(*, model_path: str = "models/plain-llama") -> common_pb2.ModelSpec:
    model = common_pb2.ModelSpec(
        model_id="melix-dev-text",
        model_path=model_path,
        model_kind="text",
        revision="main",
        max_context=4096,
    )
    model.ext["text_layer_count"] = "2"
    return model


class SuccessfulRunner(MLXLMRunner):
    def __init__(self) -> None:
        super().__init__()
        self.last_train_request: TrainingRequest | None = None

    def train_native(self, request: TrainingRequest) -> TrainingResult:
        self.last_train_request = request
        request.adapter_output_dir.mkdir(parents=True, exist_ok=True)
        weights_path = request.adapter_output_dir / "adapters.safetensors"
        adapter_config_path = request.adapter_output_dir / "adapter_config.json"
        weights_path.write_bytes(b"melix-test-adapter")
        adapter_config_path.write_text(
            json.dumps({"fine_tune_type": "lora"}) + "\n",
            encoding="utf-8",
        )
        return TrainingResult(
            weights_path=weights_path,
            adapter_config_path=adapter_config_path,
            metrics=TrainingMetrics(
                job_duration_ms=1234.0,
                tokens_seen=2048,
                examples_seen=1,
                loss_final=0.42,
                loss_best=0.33,
                learning_rate_final=1e-4,
            ),
            execution_backend="native",
        )


def _build_service(tmp_path: Path, runner: MLXLMRunner) -> WorkerMaintenanceService:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=DeterministicTextBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    service = WorkerMaintenanceService(registry, jobs_root=tmp_path / "model-ops")
    service._core = MaintenanceCore(
        registry,
        jobs_root=tmp_path / "model-ops",
        lora_training_pipeline=LoRATrainingPipeline(runner=runner),
        adapter_activation_pipeline=AdapterActivationPipeline(runner=runner),
    )
    return service


def test_load_trajectory_provenance_from_snapshot_manifest_uses_stable_field_names(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "normalized_dataset" / "manifest.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_snapshot.v1",
                "dataset_id": "agentic-snapshot",
                "format": "agentic_tool_trace",
                "version": "2026-05-19",
                "source_package_path": str(tmp_path / "agentic-package"),
                "source_dataset_id": "opensearch-vl.dev",
                "trajectory_schema_version": "melix.agentic_tool_trace.v1",
                "trajectory_split": "train",
                "trajectory_trace_digest": "abc123",
                "trajectory_toolset_version": "melix.agentic_tools.builtin.v1",
                "trajectory_registry_schema_version": "melix.agentic_tool_registry.v1",
                "trajectory_reward_policy_id": "reward-policy.v1",
                "trajectory_quality_metrics": {"reward_coverage_count": 1},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    provenance = load_trajectory_provenance_from_snapshot_manifest(manifest_path)

    assert provenance == {
        "trajectory_dataset_id": "opensearch-vl.dev",
        "trajectory_dataset_version": "2026-05-19",
        "trajectory_schema_version": "melix.agentic_tool_trace.v1",
        "trajectory_snapshot_manifest_path": str(manifest_path),
        "trajectory_split": "train",
        "trajectory_trace_digest": "abc123",
        "trajectory_toolset_version": "melix.agentic_tools.builtin.v1",
        "trajectory_registry_schema_version": "melix.agentic_tool_registry.v1",
        "trajectory_reward_policy_id": "reward-policy.v1",
        "trajectory_package_path": str(tmp_path / "agentic-package"),
        "trajectory_quality_metrics": {"reward_coverage_count": 1},
    }


def test_train_lora_records_agentic_trajectory_provenance_in_adapter_manifest(
    tmp_path: Path,
) -> None:
    dataset_dir = _write_agentic_dataset_package(tmp_path / "dataset-agentic")
    runner = SuccessfulRunner()
    service = _build_service(tmp_path, runner)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train-agentic"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "training_mode": "lora",
                    "adapter_name": "melix-agentic-adapter",
                    "dataset_uri": str(dataset_dir),
                },
            ),
            context=None,
        )
    )

    payload = json.loads(next(event.manifest for event in events if event.HasField("manifest")).manifest_json)

    assert events[-1].HasField("completed")
    assert payload["dataset_format"] == "agentic_tool_trace"
    assert payload["trajectory_dataset_id"] == "opensearch-vl.dev"
    assert payload["trajectory_dataset_version"] == "2026-05-19"
    assert payload["trajectory_schema_version"] == "melix.agentic_tool_trace.v1"
    assert payload["trajectory_split"] == "train"
    assert payload["trajectory_reward_policy_id"] == "reward-policy.v1"
    assert payload["trajectory_toolset_version"] == "melix.agentic_tools.builtin.v1"
    assert payload["trajectory_snapshot_manifest_path"] == payload["normalized_dataset_manifest_path"]
    assert payload["trajectory_provenance_field_count"] >= 8
    assert payload["trajectory_reward_policy_present"] is True
    assert runner.last_train_request is not None
    assert runner.last_train_request.dataset_format == "agentic_tool_trace"


def test_alignment_rl_trace_runner_attaches_trajectory_provenance(tmp_path: Path) -> None:
    config = training_config_module.normalize_training_config(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        ext={"training_mode": "grpo", "grpo_candidate_count": "2"},
        dataset_format="prompt_candidate",
        response_only_supported=False,
        sample_count=1,
    )
    normalized_dataset_dir = tmp_path / "normalized"
    normalized_dataset_dir.mkdir()
    (normalized_dataset_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_snapshot.v1",
                "dataset_id": "agentic-snapshot",
                "format": "agentic_tool_trace",
                "version": "2026-05-19",
                "source_package_path": str(tmp_path / "agentic-package"),
                "source_dataset_id": "opensearch-vl.dev",
                "trajectory_schema_version": "melix.agentic_tool_trace.v1",
                "trajectory_split": "train",
                "trajectory_trace_digest": "abc123",
                "trajectory_reward_policy_id": "reward-policy.v1",
                "trajectory_toolset_version": "melix.agentic_tools.builtin.v1",
                "trajectory_quality_metrics": {"reward_coverage_count": 1},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (normalized_dataset_dir / "train.jsonl").write_text(
        json.dumps(
            {
                "prompt": "Use tools before choosing.",
                "candidates": [
                    {"text": "Tool-backed answer.", "score": 0.9},
                    {"text": "Guess.", "score": 0.1},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-grpo-provenance",
        base_model_id="melix-dev-text",
        model_path=tmp_path / "base-model",
        model_revision="main",
        adapter_output_dir=tmp_path / "adapter-output",
        normalized_dataset_dir=normalized_dataset_dir,
        config=config,
        dataset_format="prompt_candidate",
    )

    result = mlx_lm_runner_module.MLXLMRunner().train(request)
    adapter_config = json.loads(result.adapter_config_path.read_text(encoding="utf-8"))
    trace_rows = [
        json.loads(line)
        for line in Path(result.metrics.policy_update_trace_path).read_text(encoding="utf-8").splitlines()
    ]

    assert adapter_config["trajectory_dataset_id"] == "opensearch-vl.dev"
    assert adapter_config["trajectory_reward_policy_id"] == "reward-policy.v1"
    assert adapter_config["trajectory_provenance_field_count"] >= 8
    assert trace_rows[0]["trajectory_trace_digest"] == "abc123"
    assert trace_rows[0]["trajectory_snapshot_manifest_path"] == str(
        normalized_dataset_dir / "manifest.json"
    )


def test_alignment_manifest_payload_records_trajectory_provenance_metrics(
    tmp_path: Path,
) -> None:
    weights_path = tmp_path / "adapters.safetensors"
    config_path = tmp_path / "adapter_config.json"
    weights_path.write_bytes(b"weights")
    config_path.write_text("{}\n", encoding="utf-8")
    config = training_config_module.normalize_training_config(
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        ext={"training_mode": "grpo", "grpo_candidate_count": "2"},
        dataset_format="prompt_candidate",
        response_only_supported=False,
        sample_count=1,
    )
    dataset = ResolvedTrainingDatasetPackage(
        package=TrainingDatasetPackage(
            package_path=tmp_path / "dataset",
            manifest_path=tmp_path / "dataset" / "manifest.json",
            samples_path=tmp_path / "dataset" / "samples.jsonl",
            schema_version="melix.training_dataset_package.v1",
            dataset_id="agentic-package",
            format="agentic_tool_trace",
            sample_count=1,
            version="2026-05-19",
            normalized_samples=[
                {
                    "prompt": "Use tools.",
                    "candidates": [
                        {"text": "Tool-backed answer.", "score": 0.9},
                        {"text": "Guess.", "score": 0.1},
                    ],
                }
            ],
            normalized_validation_samples=[],
            validation_sample_count=0,
            response_only_supported=False,
        ),
        source_kind="local",
        dataset_uri="file:///tmp/agentic",
        materialized_package_path=tmp_path / "dataset",
        cache_key="",
        cache_hit=False,
        hf_reference=None,
    )
    training_result = TrainingResult(
        weights_path=weights_path,
        adapter_config_path=config_path,
        metrics=TrainingMetrics(
            job_duration_ms=12.0,
            tokens_seen=8,
            examples_seen=1,
            loss_final=0.2,
            loss_best=0.2,
            learning_rate_final=1e-4,
            policy_update_count=1,
            selected_candidate_count=1,
            policy_update_trace_path=str(tmp_path / "policy_updates.jsonl"),
        ),
        execution_backend="scored_trace",
    )
    provenance = {
        "trajectory_dataset_id": "opensearch-vl.dev",
        "trajectory_trace_digest": "abc123",
        "trajectory_reward_policy_id": "reward-policy.v1",
        "trajectory_quality_metrics": {"reward_coverage_count": 1},
    }

    payload = _alignment_manifest_payload(
        job_id="train-grpo-provenance",
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        config=config,
        dataset=dataset,
        training_result=training_result,
        adapter_manifest_path=tmp_path / "train_lora.adapter.json",
        candidate_trace_path=str(tmp_path / "train_lora.candidates.jsonl"),
        trajectory_provenance=provenance,
        created_at_unix_ms=123,
    )

    assert payload["trajectory_trace_digest"] == "abc123"
    assert payload["metrics"]["trajectory_provenance_field_count"] == len(provenance)
    assert payload["metrics"]["trajectory_reward_policy_present"] == 1
    assert payload["metrics"]["trajectory_reward_component_coverage"] == 1


def test_persist_result_exports_trajectory_provenance_fields(tmp_path: Path) -> None:
    store = EvaluationStore(telemetry_collector=fixture_telemetry_collector())
    jobs_root = tmp_path / "evaluation"
    run_root = jobs_root / "runs" / "eval-trajectory"
    snapshot_manifest = tmp_path / "snapshots" / "normalized_dataset" / "manifest.json"
    snapshot_manifest.parent.mkdir(parents=True)
    snapshot_manifest.write_text("{}\n", encoding="utf-8")
    provenance = {
        "trajectory_dataset_id": "opensearch-vl.dev",
        "trajectory_dataset_version": "2026-05-19",
        "trajectory_schema_version": "melix.agentic_tool_trace.v1",
        "trajectory_snapshot_manifest_path": str(snapshot_manifest),
        "trajectory_package_path": str(tmp_path / "packages" / "opensearch-vl.dev"),
        "trajectory_split": "train",
        "trajectory_trace_digest": "abc123",
        "trajectory_toolset_version": "melix.agentic_tools.builtin.v1",
        "trajectory_reward_policy_id": "reward-policy.v1",
        "trajectory_quality_metrics": {"reward_coverage_count": 1},
    }
    job = build_evaluation_job_record(
        job_id="eval-trajectory",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="local",
        suite_id="agentic",
        dataset_id="agentic-dev",
        sample_size=1,
        scoring_mode="exact",
        parameters={},
        status="completed",
        output_dir=str(run_root),
        trajectory_provenance=provenance,
    )
    result = build_evaluation_result_record(
        job_id="eval-trajectory",
        suite_id="agentic",
        dataset_id="agentic-dev",
        sample_size=1,
        primary_score_name="exact",
        primary_score_value=1.0,
        extraction_success_count=1,
        validation_success_count=1,
        scored_sample_count=1,
        failure_count=0,
        metrics={"eval.agentic.score": 1.0},
        report_path=str(run_root / "evaluation-result.json"),
    )
    sample = build_evaluation_sample_record(
        job_id="eval-trajectory",
        suite_id="agentic",
        dataset_id="agentic-dev",
        sample_id="sample-1",
        system="",
        input_text="Inspect image.",
        target="MELIX",
        raw_response="MELIX",
        extracted_result="MELIX",
        typed_score=1.0,
        time_s=0.01,
        extraction_status="extracted",
        validation_status="validated",
        failure_reason="",
        agentic_tool_calls=({"id": "call-1", "name": "visit", "arguments": {}},),
        agentic_tool_observations=({"status": "completed"},),
        agentic_tool_metrics={"agentic_tool.call_count": 1.0},
        trajectory_provenance=provenance,
    )

    persisted = store.persist_result(
        jobs_root=jobs_root,
        job=job,
        result=result,
        samples=(sample,),
    )

    sample_jsonl = json.loads(persisted["samples_jsonl"].read_text(encoding="utf-8"))
    evidence = json.loads(persisted["evidence"].read_text(encoding="utf-8"))
    export_bundle = collect_evaluation_artifacts(jobs_root)
    export_rows = list(csv.DictReader(io.StringIO(build_evaluation_samples_csv(export_bundle))))

    assert sample_jsonl["trajectory_dataset_id"] == "opensearch-vl.dev"
    assert sample_jsonl["agentic_tool_calls"][0]["name"] == "visit"
    assert evidence["domain_results"]["trajectory_provenance"]["trajectory_split"] == "train"
    assert {artifact["kind"] for artifact in evidence["artifacts"]} >= {
        "trajectory_snapshot_manifest",
        "trajectory_package",
    }
    assert export_rows[0]["trajectory_reward_policy_id"] == "reward-policy.v1"
    assert json.loads(export_rows[0]["trajectory_quality_metrics"])["reward_coverage_count"] == 1


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({}, ""),
        ([], ""),
        ((), ""),
        (None, ""),
        ({"reward_coverage_count": 1}, "{\"reward_coverage_count\": 1}"),
    ],
)
def test_benchmark_export_csv_value_handles_empty_and_nested_provenance(
    value: object,
    expected: str,
) -> None:
    from worker.productization.benchmark_export import _csv_value

    assert _csv_value(value) == expected
