from __future__ import annotations

import json
from pathlib import Path

from packages.protocol.python.worker.v1 import maintenance_pb2

from worker.grpc_server import WorkerMaintenanceService
from worker.engine.maintenance_core import MaintenanceCore
from worker.model_ops.adapter_activation_pipeline import AdapterActivationPipeline
from worker.model_ops.lora_training_pipeline import LoRATrainingPipeline
from worker.model_ops.mlx_lm_runner import (
    ActivationMetrics,
    ActivationRequest,
    ActivationResult,
    MLXLMRunner,
    NativeExecutionUnavailable,
    TrainingMetrics,
    TrainingRequest,
    TrainingResult,
)
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry


def _write_dataset_package(
    root: Path,
    *,
    dataset_id: str = "melix-dev-dataset",
    format: str = "chat_messages",
    samples: list[dict],
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": dataset_id,
                "format": format,
                "sample_count": len(samples),
                "version": "1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with (root / "samples.jsonl").open("w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(sample) + "\n")
    return root


class SuccessfulRunner(MLXLMRunner):
    def __init__(self) -> None:
        super().__init__()
        self.native_train_calls = 0
        self.subprocess_train_calls = 0
        self.native_activation_calls = 0
        self.subprocess_activation_calls = 0

    def train_native(self, request: TrainingRequest) -> TrainingResult:
        self.native_train_calls += 1
        request.adapter_output_dir.mkdir(parents=True, exist_ok=True)
        weights_path = request.adapter_output_dir / "adapters.safetensors"
        adapter_config_path = request.adapter_output_dir / "adapter_config.json"
        weights_path.write_bytes(b"melix-test-adapter")
        adapter_config_path.write_text(
            json.dumps(
                {
                    "fine_tune_type": "lora",
                    "num_layers": request.config.num_layers,
                    "lora_parameters": {
                        "rank": request.config.rank,
                        "dropout": request.config.dropout,
                        "scale": request.config.alpha,
                        "keys": request.config.expanded_target_modules,
                    },
                    "mask_prompt": request.config.mask_prompt,
                    "grad_checkpoint": request.config.gradient_checkpointing,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return TrainingResult(
            weights_path=weights_path,
            adapter_config_path=adapter_config_path,
            metrics=TrainingMetrics(
                job_duration_ms=1234.0,
                tokens_seen=2048,
                examples_seen=2,
                loss_final=0.42,
                loss_best=0.33,
                learning_rate_final=1e-4,
            ),
            execution_backend="native",
        )

    def train_subprocess(self, request: TrainingRequest, reason: Exception) -> TrainingResult:
        self.subprocess_train_calls += 1
        return self.train_native(request)

    def activate_native(self, request: ActivationRequest) -> ActivationResult:
        self.native_activation_calls += 1
        request.derived_model_dir.mkdir(parents=True, exist_ok=True)
        (request.derived_model_dir / "config.json").write_text(
            json.dumps({"model_type": "llama"}) + "\n",
            encoding="utf-8",
        )
        (request.derived_model_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
        activation_manifest = request.derived_model_dir / "manifest.json"
        activation_manifest.write_text(
            json.dumps({"schema_version": "melix.derived_text_model.v1"}) + "\n",
            encoding="utf-8",
        )
        return ActivationResult(
            derived_model_dir=request.derived_model_dir,
            manifest_path=activation_manifest,
            metrics=ActivationMetrics(job_duration_ms=321.0),
            execution_backend="native",
        )

    def activate_subprocess(self, request: ActivationRequest, reason: Exception) -> ActivationResult:
        self.subprocess_activation_calls += 1
        return self.activate_native(request)


class NativeUnavailableRunner(SuccessfulRunner):
    def train_native(self, request: TrainingRequest) -> TrainingResult:
        self.native_train_calls += 1
        raise NativeExecutionUnavailable("mlx native path unavailable")

    def train_subprocess(self, request: TrainingRequest, reason: Exception) -> TrainingResult:
        self.subprocess_train_calls += 1
        request.adapter_output_dir.mkdir(parents=True, exist_ok=True)
        weights_path = request.adapter_output_dir / "adapters.safetensors"
        adapter_config_path = request.adapter_output_dir / "adapter_config.json"
        weights_path.write_bytes(b"melix-test-adapter")
        adapter_config_path.write_text(
            json.dumps(
                {
                    "fine_tune_type": "lora",
                    "num_layers": request.config.num_layers,
                    "lora_parameters": {
                        "rank": request.config.rank,
                        "dropout": request.config.dropout,
                        "scale": request.config.alpha,
                        "keys": request.config.expanded_target_modules,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return TrainingResult(
            weights_path=weights_path,
            adapter_config_path=adapter_config_path,
            metrics=TrainingMetrics(
                job_duration_ms=1234.0,
                tokens_seen=2048,
                examples_seen=2,
                loss_final=0.42,
                loss_best=0.33,
                learning_rate_final=1e-4,
            ),
            execution_backend="subprocess",
        )


def _build_service(tmp_path: Path, runner: MLXLMRunner) -> WorkerMaintenanceService:
    registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
    service = WorkerMaintenanceService(registry, jobs_root=tmp_path / "model-ops")
    service._core = MaintenanceCore(
        registry,
        jobs_root=tmp_path / "model-ops",
        lora_training_pipeline=LoRATrainingPipeline(runner=runner),
        adapter_activation_pipeline=AdapterActivationPipeline(runner=runner),
    )
    return service


def test_train_lora_produces_adapter_package_and_expanded_modules(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset",
        samples=[
            {
                "messages": [
                    {"role": "system", "content": "You are helpful."},
                    {"role": "user", "content": "Say hi."},
                    {"role": "assistant", "content": "Hi there."},
                ]
            },
            {
                "messages": [
                    {"role": "user", "content": "Say bye."},
                    {"role": "assistant", "content": "Bye."},
                ]
            },
        ],
    )
    service = _build_service(tmp_path, SuccessfulRunner())

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-dev-adapter",
                    "dataset_uri": str(dataset_dir),
                    "target_modules": "q_proj,gate_proj",
                    "num_layers": "2",
                    "rank": "16",
                    "alpha": "32",
                    "dropout": "0.1",
                    "response_only": "true",
                    "gradient_checkpointing": "true",
                    "target_repo": "melix/adapters/melix-dev-adapter",
                },
            ),
            context=None,
        )
    )

    payload = json.loads(next(event.manifest for event in events if event.HasField("manifest")).manifest_json)
    stages = [event.progress.stage for event in events if event.HasField("progress")]

    assert stages == [
        "resolve_source",
        "validate_dataset",
        "normalize_config",
        "prepare_training_data",
        "apply_lora",
        "train",
        "write_adapter",
        "write_manifest",
    ]
    assert payload["schema_version"] == "melix.lora_adapter_package.v1"
    assert payload["training_mode"] == "lora"
    assert payload["adapter_name"] == "melix-dev-adapter"
    assert payload["source_model"] == "melix-dev-text"
    assert payload["dataset_uri"] == str(dataset_dir)
    assert payload["response_only"] is True
    assert payload["gradient_checkpointing"] is True
    assert payload["training_duration_ms"] == 1234.0
    assert payload["loss_final"] == 0.42
    assert payload["adapter_artifact_bytes"] > 0
    assert payload["adapter_set_hash"]
    assert payload["weights_path"].endswith("adapters.safetensors")
    assert payload["adapter_config_path"].endswith("adapter_config.json")
    assert payload["normalized_dataset_manifest_path"].endswith("normalized_dataset/manifest.json")
    assert Path(payload["weights_path"]).is_file()
    assert Path(payload["adapter_config_path"]).is_file()
    assert Path(payload["normalized_dataset_manifest_path"]).is_file()
    assert payload["target_modules"] == [
        "model.layers.0.self_attn.q_proj",
        "model.layers.1.self_attn.q_proj",
        "model.layers.0.mlp.gate_proj",
        "model.layers.1.mlp.gate_proj",
    ]


def test_train_lora_invalid_dataset_package_fails_with_typed_error(tmp_path: Path) -> None:
    invalid_dataset_dir = tmp_path / "dataset-invalid"
    invalid_dataset_dir.mkdir(parents=True, exist_ok=True)
    service = _build_service(tmp_path, SuccessfulRunner())

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train"),
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-dev-adapter",
                    "dataset_uri": str(invalid_dataset_dir),
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "invalid_dataset_package"


def test_train_lora_rejects_unknown_target_module(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset",
        samples=[
            {
                "messages": [
                    {"role": "user", "content": "Say hi."},
                    {"role": "assistant", "content": "Hi there."},
                ]
            }
        ],
    )
    service = _build_service(tmp_path, SuccessfulRunner())

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train"),
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-dev-adapter",
                    "dataset_uri": str(dataset_dir),
                    "target_modules": "q_proj,unknown_proj",
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "unsupported_lora_target_module"


def test_train_lora_uses_fallback_runner_when_native_path_is_unavailable(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset",
        samples=[
            {
                "messages": [
                    {"role": "user", "content": "Say hi."},
                    {"role": "assistant", "content": "Hi there."},
                ]
            }
        ],
    )
    runner = NativeUnavailableRunner()
    service = _build_service(tmp_path, runner)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-dev-adapter",
                    "dataset_uri": str(dataset_dir),
                },
            ),
            context=None,
        )
    )

    payload = json.loads(next(event.manifest for event in events if event.HasField("manifest")).manifest_json)

    assert runner.native_train_calls == 1
    assert runner.subprocess_train_calls == 1
    assert payload["training_backend"] == "subprocess"


def test_activate_adapter_produces_derived_model_and_registry_activation_state(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset",
        samples=[
            {
                "messages": [
                    {"role": "user", "content": "Say hi."},
                    {"role": "assistant", "content": "Hi there."},
                ]
            }
        ],
    )
    runner = SuccessfulRunner()
    service = _build_service(tmp_path, runner)

    train_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-dev-adapter",
                    "dataset_uri": str(dataset_dir),
                },
            ),
            context=None,
        )
    )
    adapter_manifest_path = train_events[-1].completed.output_path

    activate_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "activate"),
                generate_manifest=True,
                ext={
                    "operation": "activate_adapter",
                    "artifact_path": adapter_manifest_path,
                },
            ),
            context=None,
        )
    )
    activation_payload = json.loads(
        next(event.manifest for event in activate_events if event.HasField("manifest")).manifest_json
    )

    snapshot_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "snapshot"),
                generate_manifest=True,
                ext={"operation": "registry_snapshot"},
            ),
            context=None,
        )
    )
    snapshot_payload = json.loads(
        next(event.manifest for event in snapshot_events if event.HasField("manifest")).manifest_json
    )

    assert runner.native_activation_calls == 1
    assert activation_payload["schema_version"] == "melix.derived_text_model.v1"
    assert activation_payload["activation_mode"] == "fused_derived_model"
    assert activation_payload["derived_model_id"].startswith("melix-dev-text-lora-")
    assert activation_payload["adapter_set_hash"]
    assert Path(activation_payload["derived_model_path"]).is_dir()
    assert snapshot_payload["adapters"][0]["activation_status"] == "activated"
    assert snapshot_payload["adapters"][0]["derived_model_id"] == activation_payload["derived_model_id"]
    assert snapshot_payload["derived_models"][0]["model_id"] == activation_payload["derived_model_id"]
