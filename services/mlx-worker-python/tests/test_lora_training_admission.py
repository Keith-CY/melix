from __future__ import annotations

import json
from pathlib import Path

from packages.protocol.python.worker.v1 import common_pb2, maintenance_pb2

from worker.engine.maintenance_core import MaintenanceCore
from worker.grpc_server import WorkerMaintenanceService
from worker.model_ops.adapter_activation_pipeline import AdapterActivationPipeline
from worker.model_ops.errors import ModelOperationError
from worker.model_ops.lora_training_pipeline import LoRATrainingPipeline
from worker.model_ops.mlx_lm_runner import (
    ActivationMetrics,
    ActivationRequest,
    ActivationResult,
    MLXLMRunner,
    TrainingMetrics,
    TrainingRequest,
    TrainingResult,
)
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime.deterministic_backend import DeterministicTextBackend
from worker.runtime.mlx_text_runtime import MLXTextRuntime


def _write_dataset_package(root: Path, samples: list[dict[str, object]]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "melix-dev-dataset",
                "format": "chat_messages",
                "sample_count": len(samples),
                "version": "1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "samples.jsonl").write_text(
        "".join(json.dumps(sample) + "\n" for sample in samples),
        encoding="utf-8",
    )
    return root


class AdmissionFailureRunner(MLXLMRunner):
    def __init__(self) -> None:
        super().__init__()
        self.native_train_calls = 0

    def train_native(self, request: TrainingRequest) -> TrainingResult:
        self.native_train_calls += 1
        raise ModelOperationError(
            code="training_tokens_truncated",
            message="training tokens would be truncated",
            details={
                "field": "max_length",
                "reason": "media_tokens_truncated",
                "sample_index": "0",
                "affected_sample_count": "1",
                "requested_sequence_length": "8",
                "effective_sequence_length": "8",
                "media_token_count": "12",
                "suggested_minimum_sequence_length": "13",
            },
        )

    def activate(self, request: ActivationRequest) -> ActivationResult:
        return ActivationResult(
            derived_model_id=request.derived_model_id,
            model_path=request.weights_path.parent,
            metrics=ActivationMetrics(
                job_duration_ms=1.0,
                adapter_bytes=1,
                adapter_config_bytes=1,
            ),
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
    model = common_pb2.ModelSpec(
        model_id="melix-dev-text",
        model_path=str(tmp_path / "base-model"),
        model_kind="text",
        revision="main",
        quant_profile_id="q4",
        max_context=4096,
    )
    model.ext["melix.lora.family_id"] = "qwen"
    model.ext["melix.lora.family_kind"] = "dense"
    model.ext["melix.lora.support_tier"] = "stable"
    model.ext["melix.lora.training_ready"] = "true"
    model.ext["melix.lora.default_target_preset"] = "attention"
    registry.model_catalog.register_model(model)
    return service


def test_train_lora_admission_failure_preserves_typed_error_details(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset",
        [
            {
                "messages": [
                    {"role": "user", "content": "Describe this image."},
                    {"role": "assistant", "content": "It is a chart."},
                ],
                "media_refs": [{"id": "image-a", "uri": "images/a.png"}],
                "media_token_count": 12,
            }
        ],
    )
    runner = AdmissionFailureRunner()
    service = _build_service(tmp_path, runner)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train"),
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-dev-adapter",
                    "dataset_uri": str(dataset_dir),
                    "max_seq_length": "8",
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "training_tokens_truncated"
    assert events[-1].failed.error.details["field"] == "max_length"
    assert events[-1].failed.error.details["reason"] == "media_tokens_truncated"
    assert events[-1].failed.error.details["requested_sequence_length"] == "8"
    assert events[-1].failed.error.details["effective_sequence_length"] == "8"
    assert events[-1].failed.error.details["media_token_count"] == "12"
    assert events[-1].failed.error.details["suggested_minimum_sequence_length"] == "13"
    assert runner.native_train_calls == 1
