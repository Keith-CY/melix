from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import pytest
import sys
import types
from urllib.error import HTTPError, URLError

from packages.protocol.python.worker.v1 import common_pb2, maintenance_pb2

from worker.grpc_server import WorkerMaintenanceService
from worker.engine.maintenance_core import MaintenanceCore
from worker.model_ops.adapter_activation_pipeline import AdapterActivationPipeline
from worker.model_ops.lora_training_pipeline import (
    LoRATrainingPipeline,
    _latest_checkpoint_from_directory,
    _load_manifest_payload,
    _resolve_resume_context,
    _resolve_resume_path_from_manifest,
    _validated_resume_path,
)
from worker.model_ops.errors import ModelOperationError
from worker.model_ops.mlx_lm_runner import (
    ActivationMetrics,
    ActivationRequest,
    ActivationResult,
    MLXLMRunner,
    NativeExecutionUnavailable,
    TrainingMetrics,
    TrainingRequest,
    TrainingResult,
    _checkpoint_order_key,
)
from worker.model_ops import lora_training_pipeline as lora_training_pipeline_module
from worker.model_ops import training_config as training_config_module
from worker.model_ops import training_dataset as training_dataset_module
from worker.model_ops.training_dataset import (
    HFDatasetReference,
    MaterializedTrainingDatasetPackage,
    TrainingDatasetPackage,
    materialize_hf_training_dataset_package,
    resolve_training_dataset_package,
)
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime.deterministic_backend import DeterministicTextBackend
from worker.runtime.mlx_text_runtime import MLXTextRuntime


def test_checkpoint_order_key_uses_last_numeric_token() -> None:
    older = Path("/tmp/model-ops-999/adapter/checkpoint-2/adapters.safetensors")
    newer = Path("/tmp/model-ops-001/adapter/checkpoint-10/adapters.safetensors")

    assert max((older, newer), key=_checkpoint_order_key) == newer
    assert _checkpoint_order_key(Path("/tmp/melix/no-number/adapters.safetensors")) == (
        -1,
        "/tmp/melix/no-number/adapters.safetensors",
    )


def test_alignment_percentile_uses_interpolation_and_upper_bound() -> None:
    assert lora_training_pipeline_module._percentile_value(
        [0.4, 0.7],
        0.5,
    ) == pytest.approx(0.55)
    assert lora_training_pipeline_module._percentile_value(
        [0.4, 0.7],
        1.0,
    ) == pytest.approx(0.7)


def test_reward_summary_reuses_candidate_group_minmax(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sorted_calls: list[int] = []
    original_sorted = sorted

    def counting_sorted(values: list[float]) -> list[float]:
        sorted_calls.append(len(values))
        return original_sorted(values)

    monkeypatch.setattr(
        lora_training_pipeline_module,
        "sorted",
        counting_sorted,
        raising=False,
    )

    samples = [
        {
            "reward_score": 0.05,
            "candidates": [
                {"score": 0.4},
                {"score": 0.1},
                {"score": 0.9},
            ],
        },
        {
            "reward_score": 0.2,
            "candidates": [
                {"score": 1.1},
                {"score": -0.2},
                {"score": 0.3},
            ],
        },
    ]

    summary = lora_training_pipeline_module._reward_summary(samples)

    assert summary["candidate_group_count"] == 2
    assert summary["candidate_group_reward_margin_mean"] == pytest.approx(1.05)
    assert summary["candidate_group_reward_margin_p50"] == pytest.approx(1.05)
    assert sorted_calls == [8, 2]


def test_latest_checkpoint_from_directory_prefers_last_numeric_token(tmp_path: Path) -> None:
    older = (
        tmp_path / "model-ops-999" / "adapter" / "checkpoint-2" / "adapters.safetensors"
    )
    newer = (
        tmp_path / "model-ops-001" / "adapter" / "checkpoint-10" / "adapters.safetensors"
    )
    for checkpoint in (older, newer):
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_bytes(b"weights")

    assert _latest_checkpoint_from_directory(tmp_path) == newer.resolve()


def test_latest_checkpoint_from_directory_uses_scandir_stack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    nested = tmp_path / "model-ops-001" / "adapter" / "checkpoint-3"
    nested.mkdir(parents=True)
    checkpoint = nested / "adapters.safetensors"
    checkpoint.write_bytes(b"weights")

    def fail_os_walk(path: Path):
        raise AssertionError("expected explicit os.scandir stack, not os.walk")

    monkeypatch.setattr(lora_training_pipeline_module.os, "walk", fail_os_walk)

    assert _latest_checkpoint_from_directory(tmp_path) == checkpoint.resolve()


def test_latest_checkpoint_from_directory_skips_non_weight_entries(tmp_path: Path) -> None:
    (tmp_path / "checkpoint-99").mkdir()
    (tmp_path / "checkpoint-99" / "adapter.txt").write_text("not weights", encoding="utf-8")

    with pytest.raises(ModelOperationError, match="does not contain adapter weights"):
        _latest_checkpoint_from_directory(tmp_path)


def test_resume_helpers_reject_invalid_sources(tmp_path: Path) -> None:
    missing_resume_path = tmp_path / "missing.safetensors"
    with pytest.raises(ModelOperationError, match="Resume source does not exist"):
        _resolve_resume_context({"resume_source_path": str(missing_resume_path)})

    broken_manifest = tmp_path / "broken.json"
    broken_manifest.write_text("not-json", encoding="utf-8")
    with pytest.raises(ModelOperationError, match="Resume manifest is unreadable"):
        _load_manifest_payload(broken_manifest)

    with pytest.raises(ModelOperationError, match="does not expose a checkpoint"):
        _resolve_resume_path_from_manifest(tmp_path / "manifest.json", {})

    with pytest.raises(ModelOperationError, match="does not exist"):
        _validated_resume_path(missing_resume_path, source_label="test")


def test_validated_resume_path_selects_latest_checkpoint_from_directory(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint-7" / "adapters.safetensors"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"weights")

    assert _validated_resume_path(tmp_path, source_label="test") == checkpoint.resolve()


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
        self.last_train_request: TrainingRequest | None = None
        self.last_activation_request: ActivationRequest | None = None

    def supports_alignment_training(self, config) -> bool:
        del config
        return True

    def train_native(self, request: TrainingRequest) -> TrainingResult:
        self.native_train_calls += 1
        self.last_train_request = request
        request.adapter_output_dir.mkdir(parents=True, exist_ok=True)
        weights_path = request.adapter_output_dir / "adapters.safetensors"
        adapter_config_path = request.adapter_output_dir / "adapter_config.json"
        checkpoint_dir = request.adapter_output_dir / "checkpoint-2"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        latest_checkpoint_path = checkpoint_dir / "adapters.safetensors"
        weights_path.write_bytes(b"melix-test-adapter")
        latest_checkpoint_path.write_bytes(b"melix-test-checkpoint")
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
        preference_metrics = {}
        if request.config.training_objective == "preference":
            preference_metrics = {
                "preference_loss_final": 0.2,
                "chosen_logprob_mean": -1.5,
                "rejected_logprob_mean": -2.0,
                "chosen_rejected_margin": 0.5,
                "win_rate_proxy": 1.0,
            }
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
                checkpoint_count=2,
                resume_ready=True,
                latest_checkpoint_path=str(latest_checkpoint_path),
                resume_source_path=str(request.resume_source_path or ""),
                tokens_per_second=128.5,
                peak_memory_gb=5.25,
                **preference_metrics,
            ),
            execution_backend="native",
        )

    def train_subprocess(self, request: TrainingRequest, reason: Exception) -> TrainingResult:
        self.subprocess_train_calls += 1
        return self.train_native(request)

    def activate_native(self, request: ActivationRequest) -> ActivationResult:
        self.native_activation_calls += 1
        self.last_activation_request = request
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
        self.last_activation_request = request
        return self.activate_native(request)


class NativeUnavailableRunner(SuccessfulRunner):
    def train_native(self, request: TrainingRequest) -> TrainingResult:
        self.native_train_calls += 1
        self.last_train_request = request
        raise NativeExecutionUnavailable("mlx native path unavailable")

    def train_subprocess(self, request: TrainingRequest, reason: Exception) -> TrainingResult:
        self.subprocess_train_calls += 1
        self.last_train_request = request
        request.adapter_output_dir.mkdir(parents=True, exist_ok=True)
        weights_path = request.adapter_output_dir / "adapters.safetensors"
        adapter_config_path = request.adapter_output_dir / "adapter_config.json"
        checkpoint_dir = request.adapter_output_dir / "checkpoint-2"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        latest_checkpoint_path = checkpoint_dir / "adapters.safetensors"
        weights_path.write_bytes(b"melix-test-adapter")
        latest_checkpoint_path.write_bytes(b"melix-test-checkpoint")
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
                checkpoint_count=2,
                resume_ready=True,
                latest_checkpoint_path=str(latest_checkpoint_path),
                resume_source_path=str(request.resume_source_path or ""),
                tokens_per_second=128.5,
                peak_memory_gb=5.25,
            ),
            execution_backend="subprocess",
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


def _configure_lora_family(
    source_model: common_pb2.ModelSpec,
    *,
    model_path: str,
    family_id: str,
    family_kind: str,
    support_tier: str,
    training_ready: bool = True,
    default_target_preset: str,
) -> None:
    source_model.model_path = model_path
    source_model.ext["melix.lora.family_id"] = family_id
    source_model.ext["melix.lora.family_kind"] = family_kind
    source_model.ext["melix.lora.support_tier"] = support_tier
    source_model.ext["melix.lora.training_ready"] = "true" if training_ready else "false"
    source_model.ext["melix.lora.default_target_preset"] = default_target_preset


class FakeHFDatasetFetcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, endpoint: str, params: dict[str, str]) -> dict[str, object]:
        self.calls.append((endpoint, dict(params)))
        if endpoint == "splits":
            return {
                "splits": [
                    {
                        "dataset": "melix/demo-hf",
                        "config": "default",
                        "split": "train",
                    },
                    {
                        "dataset": "melix/demo-hf",
                        "config": "default",
                        "split": "validation",
                    }
                ]
            }
        if endpoint == "rows":
            if params.get("split") == "validation":
                return {
                    "rows": [
                        {"row": {"text": "validation sample"}},
                    ]
                }
            return {
                "rows": [
                    {"row": {"text": "hello from hf"}},
                    {"row": {"text": "goodbye from hf"}},
                ]
            }
        raise AssertionError(f"Unexpected endpoint: {endpoint}")


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
                    "gradient_accumulation": "2",
                    "preset_id": "balanced_adapter",
                    "experiment_group_id": "nightly-qwen35",
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
    assert payload["gradient_accumulation"] == 2
    # Observability: plumbing (we do not assert MLX-LM honors the flag).
    assert payload["effective_batch_size"] == payload["batch_size"] * 2
    assert payload["optimizer_steps"] == payload["iters"] // 2
    assert payload["training_duration_ms"] == 1234.0
    assert payload["loss_final"] == 0.42
    assert payload["preset_id"] == "balanced_adapter"
    assert payload["preset_title"] == "Balanced Adapter"
    assert payload["experiment_group_id"] == "nightly-qwen35"
    assert payload["checkpoint_count"] == 2
    assert payload["latest_checkpoint_path"].endswith("checkpoint-2/adapters.safetensors")
    assert payload["resume_source_path"] == ""
    assert payload["resume_ready"] is True
    assert payload["tokens_per_second"] == 128.5
    assert payload["peak_memory_gb"] == 5.25
    assert payload["experiment.checkpoint_count"] == 2
    assert payload["experiment.latest_checkpoint_path"].endswith("checkpoint-2/adapters.safetensors")
    assert payload["experiment.resume_source_path"] == ""
    assert payload["experiment.resume_ready"] is True
    assert payload["training.tokens_per_second"] == 128.5
    assert payload["training.peak_memory_gb"] == 5.25
    assert payload["adapter_artifact_bytes"] > 0
    assert payload["adapter_set_hash"]
    assert payload["weights_path"].endswith("adapters.safetensors")
    assert payload["adapter_config_path"].endswith("adapter_config.json")
    assert payload["normalized_dataset_manifest_path"].endswith("normalized_dataset/manifest.json")
    assert Path(payload["weights_path"]).is_file()
    assert Path(payload["adapter_config_path"]).is_file()
    assert Path(payload["normalized_dataset_manifest_path"]).is_file()
    index_path = tmp_path / "model-ops" / "train_lora" / "lora-experiments.index.json"
    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    assert index_payload["groups"][0]["group_id"] == "nightly-qwen35"
    assert index_payload["groups"][0]["latest_preset_id"] == "balanced_adapter"
    assert index_payload["groups"][0]["recommended_manifest_path"].endswith("train_lora.adapter.json")
    assert index_payload["runs"][0]["preset_title"] == "Balanced Adapter"
    assert index_payload["runs"][0]["group_id"] == "nightly-qwen35"
    assert payload["target_modules"] == [
        "model.layers.0.self_attn.q_proj",
        "model.layers.1.self_attn.q_proj",
        "model.layers.0.mlp.gate_proj",
        "model.layers.1.mlp.gate_proj",
    ]


def test_train_lora_persists_response_only_boundary_metrics_when_present(tmp_path: Path) -> None:
    class ResponseOnlyMetricsRunner(SuccessfulRunner):
        def train_native(self, request: TrainingRequest) -> TrainingResult:
            base = super().train_native(request)
            return replace(
                base,
                metrics=replace(
                    base.metrics,
                    response_only_boundary_sample_count=2,
                    response_only_boundary_min=4,
                    response_only_boundary_max=9,
                    response_only_boundary_mean=6.5,
                ),
            )

    dataset_dir = _write_dataset_package(
        tmp_path / "dataset-response-only-boundary",
        samples=[
            {
                "messages": [
                    {"role": "user", "content": "Question?"},
                    {"role": "assistant", "content": "Answer."},
                ]
            }
        ],
    )
    service = _build_service(tmp_path, ResponseOnlyMetricsRunner())

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train-response-only-boundary"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-boundary-adapter",
                    "dataset_uri": str(dataset_dir),
                    "response_only": "true",
                },
            ),
            context=None,
        )
    )

    payload = json.loads(next(event.manifest for event in events if event.HasField("manifest")).manifest_json)

    assert payload["response_only"] is True
    assert payload["response_only_boundary_sample_count"] == 2
    assert payload["response_only_boundary_min"] == 4
    assert payload["response_only_boundary_max"] == 9
    assert payload["response_only_boundary_mean"] == 6.5



def test_train_lora_records_resume_manifest_metadata_and_reuses_checkpoint_path(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset-resume",
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

    first_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train-initial"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-resume-source",
                    "dataset_uri": str(dataset_dir),
                    "experiment_group_id": "nightly-qwen35",
                },
            ),
            context=None,
        )
    )
    first_payload = json.loads(
        next(event.manifest for event in first_events if event.HasField("manifest")).manifest_json
    )

    resume_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train-resumed"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-resumed-adapter",
                    "dataset_uri": str(dataset_dir),
                    "experiment_group_id": "nightly-qwen35",
                    "resume_manifest_path": first_payload["artifact_path"],
                },
            ),
            context=None,
        )
    )
    resume_payload = json.loads(
        next(event.manifest for event in resume_events if event.HasField("manifest")).manifest_json
    )

    assert runner.last_train_request is not None
    assert runner.last_train_request.resume_source_path is not None
    assert str(runner.last_train_request.resume_source_path) == first_payload["latest_checkpoint_path"]
    assert resume_payload["resume_source_path"] == first_payload["latest_checkpoint_path"]
    assert resume_payload["resume_source_manifest_path"] == first_payload["artifact_path"]
    assert resume_payload["resume_source_job_id"] == first_payload["job_id"]
    assert resume_payload["experiment.resume_source_path"] == first_payload["latest_checkpoint_path"]

def test_resolve_training_dataset_rejects_invalid_source_kind_and_missing_hf_path(tmp_path: Path) -> None:
    with pytest.raises(Exception) as invalid_source:
        resolve_training_dataset_package(
            {"dataset_source_kind": "remote_zip"},
            jobs_root=tmp_path / "jobs",
        )
    assert invalid_source.value.code == "invalid_dataset_source"

    with pytest.raises(Exception) as missing_path:
        resolve_training_dataset_package(
            {"dataset_source_kind": "hf_dataset"},
            jobs_root=tmp_path / "jobs",
        )
    assert missing_path.value.code == "invalid_dataset_source"


def test_train_lora_materializes_hf_dataset_and_reuses_cached_package(tmp_path: Path) -> None:
    fetcher = FakeHFDatasetFetcher()
    registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
    service = WorkerMaintenanceService(registry, jobs_root=tmp_path / "model-ops")
    service._core = MaintenanceCore(
        registry,
        jobs_root=tmp_path / "model-ops",
        lora_training_pipeline=LoRATrainingPipeline(
            runner=SuccessfulRunner(),
            hf_dataset_fetcher=fetcher,
        ),
        adapter_activation_pipeline=AdapterActivationPipeline(runner=SuccessfulRunner()),
    )

    request = maintenance_pb2.ConvertModelRequest(
        source_model="melix-dev-text",
        output_dir=str(tmp_path / "ignored-train-output"),
        generate_manifest=True,
        ext={
            "operation": "train_lora",
            "adapter_name": "melix-hf-adapter",
            "dataset_source_kind": "hf_dataset",
            "hf_dataset_path": "melix/demo-hf",
            "hf_train_split": "train",
            "text_feature": "text",
        },
    )

    first_events = list(service.ConvertModel(request, context=None))
    second_events = list(service.ConvertModel(request, context=None))

    first_payload = json.loads(
        next(event.manifest for event in first_events if event.HasField("manifest")).manifest_json
    )
    second_payload = json.loads(
        next(event.manifest for event in second_events if event.HasField("manifest")).manifest_json
    )

    assert first_payload["dataset_source_kind"] == "hf_dataset"
    assert first_payload["hf_dataset_path"] == "melix/demo-hf"
    assert first_payload["hf_dataset_name"] == "default"
    assert first_payload["hf_train_split"] == "train"
    assert first_payload["dataset_uri"] == "hf://melix/demo-hf?config=default&split=train&revision=main"
    assert first_payload["dataset_cache_hit"] is False
    assert first_payload["dataset_materialized_package_path"].startswith(str(tmp_path / "model-ops" / "datasets"))
    assert Path(first_payload["dataset_materialized_package_path"]).is_dir()
    assert second_payload["dataset_cache_hit"] is True
    assert [endpoint for endpoint, _ in fetcher.calls] == ["splits", "rows"]


def test_train_lora_supports_qlora_with_hf_valid_split_and_persists_desired_alias(
    tmp_path: Path,
) -> None:
    fetcher = FakeHFDatasetFetcher()
    runner = SuccessfulRunner()
    service = _build_service(tmp_path, runner)
    source_model = service._core._registry.model_catalog.get("melix-dev-text")
    assert source_model is not None
    source_model.model_path = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
    source_model.quant_profile_id = "q4"

    service._core = MaintenanceCore(
        service._core._registry,
        jobs_root=tmp_path / "model-ops",
        lora_training_pipeline=LoRATrainingPipeline(
            runner=runner,
            hf_dataset_fetcher=fetcher,
        ),
        adapter_activation_pipeline=AdapterActivationPipeline(runner=runner),
    )

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "ignored-train-output"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "training_mode": "qlora",
                    "adapter_name": "melix-qwen35-acceptance-adapter",
                    "dataset_source_kind": "hf_dataset",
                    "hf_dataset_path": "melix/demo-hf",
                    "hf_train_split": "train",
                    "hf_valid_split": "validation",
                    "text_feature": "text",
                    "derived_model_alias": "melix-qwen35-acceptance",
                },
            ),
            context=None,
        )
    )

    payload = json.loads(next(event.manifest for event in events if event.HasField("manifest")).manifest_json)
    normalized_dataset_path = Path(payload["normalized_dataset_manifest_path"])
    normalized_dataset_payload = json.loads(normalized_dataset_path.read_text(encoding="utf-8"))

    assert payload["training_mode"] == "qlora"
    assert payload["quantization_mode"] == "quantized_base"
    assert payload["hf_valid_split"] == "validation"
    assert payload["validation_strategy"] == "hf_split"
    assert payload["validation_sample_count"] == 1
    assert payload["desired_derived_model_alias"] == "melix-qwen35-acceptance"
    assert normalized_dataset_payload["validation_sample_count"] == 1
    assert normalized_dataset_payload["validation_strategy"] == "hf_split"
    assert normalized_dataset_payload["hf_valid_split"] == "validation"
    assert runner.last_train_request is not None
    assert runner.last_train_request.config.training_mode == "qlora"
    assert runner.last_train_request.config.validation_strategy == "hf_split"
    assert runner.last_train_request.config.validation_sample_count == 1
    assert (normalized_dataset_path.parent / "valid.jsonl").is_file()
    assert [params["split"] for endpoint, params in fetcher.calls if endpoint == "rows"] == [
        "train",
        "validation",
    ]


def test_train_lora_supports_dora_mode_contract_and_manifest(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset-dora",
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

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train-dora"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "training_mode": "dora",
                    "adapter_name": "melix-dora-adapter",
                    "dataset_uri": str(dataset_dir),
                },
            ),
            context=None,
        )
    )

    payload = json.loads(next(event.manifest for event in events if event.HasField("manifest")).manifest_json)

    assert payload["training_mode"] == "dora"
    assert payload["training_objective"] == "supervised_finetuning"
    assert payload["adapter_algorithm"] == "dora"
    assert payload["preference_loss"] == ""
    assert payload["dataset_contract"] == "sft"
    assert payload["dora_enabled"] is True
    assert runner.last_train_request is not None
    assert runner.last_train_request.config.training_mode == "dora"
    assert runner.last_train_request.config.adapter_algorithm == "dora"
    assert runner.last_train_request.config.training_objective == "supervised_finetuning"


@pytest.mark.parametrize("training_mode", ["dpo", "orpo", "cpo"])
def test_train_lora_supports_preference_mode_contracts(
    tmp_path: Path,
    training_mode: str,
) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / f"dataset-{training_mode}",
        format="preference_pair",
        samples=[
            {
                "prompt": "Choose a response.",
                "chosen": "The concise response.",
                "rejected": "The unrelated response.",
            },
            {
                "prompt": "Choose a safer answer.",
                "chosen": "Follow the guide.",
                "rejected": "Make a guess.",
            },
        ],
    )
    runner = SuccessfulRunner()
    service = _build_service(tmp_path, runner)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / f"train-{training_mode}"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "training_mode": training_mode,
                    "adapter_name": f"melix-{training_mode}-adapter",
                    "dataset_uri": str(dataset_dir),
                },
            ),
            context=None,
        )
    )

    payload = json.loads(next(event.manifest for event in events if event.HasField("manifest")).manifest_json)
    normalized_dataset_path = Path(payload["normalized_dataset_manifest_path"])
    normalized_dataset_payload = json.loads(normalized_dataset_path.read_text(encoding="utf-8"))

    assert payload["training_mode"] == training_mode
    assert payload["dataset_format"] == "preference_pair"
    assert payload["training_objective"] == "preference"
    assert payload["adapter_algorithm"] == "lora"
    assert payload["preference_loss"] == training_mode
    assert payload["dataset_contract"] == "preference_pair"
    assert payload["alignment_run_manifest_path"].endswith("train_lora.alignment.json")
    assert payload["dora_enabled"] is False
    alignment_payload = json.loads(Path(payload["alignment_run_manifest_path"]).read_text(encoding="utf-8"))
    assert alignment_payload["schema_version"] == "melix.alignment_run.v1"
    assert alignment_payload["alignment_algorithm"] == training_mode
    assert alignment_payload["dataset_contract"] == "preference_pair"
    assert alignment_payload["adapter_manifest_path"] == payload["artifact_path"]
    assert "preference_loss" not in alignment_payload["metrics"]
    assert alignment_payload["metrics"]["preference_loss_config"] == training_mode
    assert alignment_payload["metrics"]["preference_loss_final"] == pytest.approx(0.2)
    assert alignment_payload["metrics"]["chosen_logprob_mean"] == pytest.approx(-1.5)
    assert alignment_payload["metrics"]["rejected_logprob_mean"] == pytest.approx(-2.0)
    assert alignment_payload["metrics"]["chosen_rejected_margin"] == pytest.approx(0.5)
    assert alignment_payload["metrics"]["win_rate_proxy"] == pytest.approx(1.0)
    assert normalized_dataset_payload["format"] == "preference_pair"
    assert runner.last_train_request is not None
    assert runner.last_train_request.dataset_format == "preference_pair"
    assert runner.last_train_request.config.preference_loss == training_mode
    assert runner.last_train_request.config.training_objective == "preference"
    assert runner.last_train_request.config.alignment is not None
    assert runner.last_train_request.config.alignment.alignment_algorithm == training_mode


@pytest.mark.parametrize(
    ("training_mode", "dataset_format", "samples", "extra_ext", "expected_contract"),
    [
        (
            "grpo",
            "prompt_candidate",
            [
                {
                    "prompt": "Draft two summaries.",
                    "candidates": [
                        {"text": "Short summary.", "score": 0.7},
                        {"text": "Verbose summary.", "score": 0.4},
                    ],
                }
            ],
            {"grpo_candidate_count": "2", "reference_model_path": "/tmp/reference-model"},
            "prompt_candidate",
        ),
        (
            "rlhf",
            "reward_scored",
            [
                {
                    "prompt": "Rate this answer.",
                    "response": "Helpful answer.",
                    "reward_score": 0.9,
                }
            ],
            {"reward_model_manifest_path": "/tmp/reward-model/manifest.json"},
            "reward_scored",
        ),
    ],
)
def test_train_lora_supports_rl_alignment_mode_contracts(
    tmp_path: Path,
    training_mode: str,
    dataset_format: str,
    samples: list[dict],
    extra_ext: dict[str, str],
    expected_contract: str,
) -> None:
    extra_ext = dict(extra_ext)
    if training_mode == "rlhf":
        reward_manifest_path = tmp_path / "reward-model" / "manifest.json"
        reward_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        reward_manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": "melix.reward_model_adapter.v1",
                    "reward_model_id": "reward-model",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        extra_ext["reward_model_manifest_path"] = str(reward_manifest_path)

    dataset_dir = _write_dataset_package(
        tmp_path / f"dataset-{training_mode}",
        format=dataset_format,
        samples=samples,
    )
    runner = SuccessfulRunner()
    service = _build_service(tmp_path, runner)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / f"train-{training_mode}"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "training_mode": training_mode,
                    "adapter_name": f"melix-{training_mode}-adapter",
                    "dataset_uri": str(dataset_dir),
                    **extra_ext,
                },
            ),
            context=None,
        )
    )

    payload = json.loads(next(event.manifest for event in events if event.HasField("manifest")).manifest_json)
    alignment_payload = json.loads(Path(payload["alignment_run_manifest_path"]).read_text(encoding="utf-8"))

    assert payload["training_mode"] == training_mode
    assert payload["training_objective"] == "alignment_rl"
    assert payload["dataset_contract"] == expected_contract
    assert payload["alignment_run_manifest_path"].endswith("train_lora.alignment.json")
    assert alignment_payload["schema_version"] == "melix.alignment_run.v1"
    assert alignment_payload["alignment_algorithm"] == training_mode
    assert alignment_payload["dataset_contract"] == expected_contract
    assert alignment_payload["candidate_trace_path"].endswith("train_lora.candidates.jsonl")
    metrics = alignment_payload["metrics"]
    if training_mode == "grpo":
        assert alignment_payload["grpo_candidate_count"] == 2
        assert alignment_payload["reference_model_path"] == "/tmp/reference-model"
        assert metrics["reward_p50"] == pytest.approx(0.55)
        assert metrics["candidate_group_count"] == 1
        assert metrics["candidate_group_reward_margin_mean"] == pytest.approx(0.3)
        assert metrics["candidate_group_reward_variance_mean"] == pytest.approx(0.0225)
    else:
        assert alignment_payload["reward_model_manifest_path"] == extra_ext["reward_model_manifest_path"]
        assert metrics["reward_mean"] == pytest.approx(0.9)
    assert runner.last_train_request is not None
    assert runner.last_train_request.config.alignment is not None
    assert runner.last_train_request.config.alignment.alignment_algorithm == training_mode


def test_train_lora_supports_continual_pretraining_contract(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset-cpt",
        format="text_completion",
        samples=[
            {"text": "Long-form domain text for local continual pretraining."},
            {"text": "A second document keeps the contract sample based."},
        ],
    )
    runner = SuccessfulRunner()
    service = _build_service(tmp_path, runner)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train-cpt"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "training_mode": "cpt",
                    "adapter_name": "melix-cpt-adapter",
                    "dataset_uri": str(dataset_dir),
                },
            ),
            context=None,
        )
    )

    payload = json.loads(next(event.manifest for event in events if event.HasField("manifest")).manifest_json)

    assert payload["training_mode"] == "cpt"
    assert payload["dataset_format"] == "text_completion"
    assert payload["training_objective"] == "continual_pretraining"
    assert payload["adapter_algorithm"] == "lora"
    assert payload["preference_loss"] == ""
    assert payload["dataset_contract"] == "text_completion"
    assert payload["response_only"] is False
    assert runner.last_train_request is not None
    assert runner.last_train_request.config.mask_prompt is False
    assert runner.last_train_request.config.training_objective == "continual_pretraining"


def test_train_lora_rejects_qlora_for_non_quantized_base_model(tmp_path: Path) -> None:
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
    source_model = service._core._registry.model_catalog.get("melix-dev-text")
    assert source_model is not None
    source_model.model_path = "models/plain-llama"
    source_model.quant_profile_id = ""

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train"),
                ext={
                    "operation": "train_lora",
                    "training_mode": "qlora",
                    "adapter_name": "melix-dev-adapter",
                    "dataset_uri": str(dataset_dir),
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "unsupported_training_mode"


@pytest.mark.parametrize("training_mode", ["dpo", "orpo", "cpo"])
def test_train_lora_rejects_preference_modes_without_preference_pair_dataset(
    tmp_path: Path,
    training_mode: str,
) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / f"dataset-invalid-{training_mode}",
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
                output_dir=str(tmp_path / f"train-invalid-{training_mode}"),
                ext={
                    "operation": "train_lora",
                    "training_mode": training_mode,
                    "adapter_name": f"melix-invalid-{training_mode}",
                    "dataset_uri": str(dataset_dir),
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "invalid_dataset_package"
    assert events[-1].failed.error.details["training_mode"] == training_mode
    assert events[-1].failed.error.details["required_format"] == "preference_pair"
    assert events[-1].failed.error.details["actual_format"] == "chat_messages"


def test_train_lora_rejects_grpo_without_prompt_candidate_dataset(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset-invalid-grpo",
        format="preference_pair",
        samples=[
            {
                "prompt": "Choose.",
                "chosen": "A.",
                "rejected": "B.",
            }
        ],
    )
    service = _build_service(tmp_path, SuccessfulRunner())

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train-invalid-grpo"),
                ext={
                    "operation": "train_lora",
                    "training_mode": "grpo",
                    "adapter_name": "melix-invalid-grpo",
                    "dataset_uri": str(dataset_dir),
                    "grpo_candidate_count": "2",
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "invalid_dataset_package"
    assert events[-1].failed.error.details["training_mode"] == "grpo"
    assert events[-1].failed.error.details["required_format"] == "prompt_candidate"
    assert events[-1].failed.error.details["actual_format"] == "preference_pair"


def test_train_lora_rejects_grpo_without_candidate_count(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset-invalid-grpo-count",
        format="prompt_candidate",
        samples=[
            {
                "prompt": "Draft two options.",
                "candidates": [{"text": "A."}, {"text": "B."}],
            }
        ],
    )
    service = _build_service(tmp_path, SuccessfulRunner())

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train-invalid-grpo-count"),
                ext={
                    "operation": "train_lora",
                    "training_mode": "grpo",
                    "adapter_name": "melix-invalid-grpo-count",
                    "dataset_uri": str(dataset_dir),
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "invalid_alignment_config"
    assert events[-1].failed.error.details["training_mode"] == "grpo"
    assert events[-1].failed.error.details["missing_field"] == "grpo_candidate_count"


def test_train_lora_rejects_grpo_with_non_integer_candidate_count(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset-invalid-grpo-count-type",
        format="prompt_candidate",
        samples=[
            {
                "prompt": "Draft two options.",
                "candidates": [{"text": "A."}, {"text": "B."}],
            }
        ],
    )
    service = _build_service(tmp_path, SuccessfulRunner())

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train-invalid-grpo-count-type"),
                ext={
                    "operation": "train_lora",
                    "training_mode": "grpo",
                    "adapter_name": "melix-invalid-grpo-count-type",
                    "dataset_uri": str(dataset_dir),
                    "grpo_candidate_count": "four",
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "invalid_argument"
    assert events[-1].failed.error.message == "grpo_candidate_count must be an integer."
    assert events[-1].failed.error.details["field"] == "grpo_candidate_count"
    assert events[-1].failed.error.details["raw_value"] == "four"


def test_train_lora_rejects_grpo_candidate_count_above_dataset_group_size(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset-invalid-grpo-group-size",
        format="prompt_candidate",
        samples=[
            {
                "prompt": "Draft two options.",
                "candidates": [{"text": "A."}, {"text": "B."}],
            }
        ],
    )
    service = _build_service(tmp_path, SuccessfulRunner())

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train-invalid-grpo-group-size"),
                ext={
                    "operation": "train_lora",
                    "training_mode": "grpo",
                    "adapter_name": "melix-invalid-grpo-group-size",
                    "dataset_uri": str(dataset_dir),
                    "grpo_candidate_count": "3",
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "invalid_alignment_dataset"
    assert events[-1].failed.error.details["sample_index"] == "0"
    assert events[-1].failed.error.details["candidate_count"] == "2"
    assert events[-1].failed.error.details["grpo_candidate_count"] == "3"


def test_train_lora_rejects_rlhf_without_reward_scored_dataset(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset-invalid-rlhf-format",
        format="preference_pair",
        samples=[
            {
                "prompt": "Choose.",
                "chosen": "A.",
                "rejected": "B.",
            }
        ],
    )
    service = _build_service(tmp_path, SuccessfulRunner())

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train-invalid-rlhf-format"),
                ext={
                    "operation": "train_lora",
                    "training_mode": "rlhf",
                    "adapter_name": "melix-invalid-rlhf-format",
                    "dataset_uri": str(dataset_dir),
                    "reward_model_manifest_path": "/tmp/reward/manifest.json",
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "invalid_dataset_package"
    assert events[-1].failed.error.details["training_mode"] == "rlhf"
    assert events[-1].failed.error.details["required_format"] == "reward_scored"
    assert events[-1].failed.error.details["actual_format"] == "preference_pair"


def test_train_lora_rejects_rlhf_without_reward_model_manifest(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset-invalid-rlhf",
        format="reward_scored",
        samples=[
            {
                "prompt": "Rate this.",
                "response": "Helpful.",
                "reward_score": 0.75,
            }
        ],
    )
    service = _build_service(tmp_path, SuccessfulRunner())

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train-invalid-rlhf"),
                ext={
                    "operation": "train_lora",
                    "training_mode": "rlhf",
                    "adapter_name": "melix-invalid-rlhf",
                    "dataset_uri": str(dataset_dir),
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "invalid_alignment_config"
    assert events[-1].failed.error.details["training_mode"] == "rlhf"
    assert events[-1].failed.error.details["missing_field"] == "reward_model_manifest_path"


def test_train_lora_rejects_rlhf_with_missing_reward_model_manifest_file(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset-invalid-rlhf-reward-manifest",
        format="reward_scored",
        samples=[
            {
                "prompt": "Rate this.",
                "response": "Helpful.",
                "reward_score": 0.75,
            }
        ],
    )
    reward_manifest_path = tmp_path / "missing-reward-model" / "manifest.json"
    service = _build_service(tmp_path, SuccessfulRunner())

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train-invalid-rlhf-reward-manifest"),
                ext={
                    "operation": "train_lora",
                    "training_mode": "rlhf",
                    "adapter_name": "melix-invalid-rlhf-reward-manifest",
                    "dataset_uri": str(dataset_dir),
                    "reward_model_manifest_path": str(reward_manifest_path),
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "invalid_alignment_config"
    assert events[-1].failed.error.details["reward_model_manifest_path"] == str(
        reward_manifest_path
    )


def test_train_lora_rejects_rlhf_with_malformed_reward_model_manifest(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset-invalid-rlhf-reward-manifest-json",
        format="reward_scored",
        samples=[
            {
                "prompt": "Rate this.",
                "response": "Helpful.",
                "reward_score": 0.75,
            }
        ],
    )
    reward_manifest_path = tmp_path / "reward-model" / "manifest.json"
    reward_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    reward_manifest_path.write_text("{not-json", encoding="utf-8")
    service = _build_service(tmp_path, SuccessfulRunner())

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train-invalid-rlhf-reward-manifest-json"),
                ext={
                    "operation": "train_lora",
                    "training_mode": "rlhf",
                    "adapter_name": "melix-invalid-rlhf-reward-manifest-json",
                    "dataset_uri": str(dataset_dir),
                    "reward_model_manifest_path": str(reward_manifest_path),
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "invalid_alignment_config"
    assert (
        events[-1].failed.error.message
        == "reward_model_manifest_path must point to a readable JSON manifest."
    )


def test_train_lora_rejects_rlhf_reward_model_manifest_without_schema_version(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset-invalid-rlhf-reward-manifest-schema",
        format="reward_scored",
        samples=[
            {
                "prompt": "Rate this.",
                "response": "Helpful.",
                "reward_score": 0.75,
            }
        ],
    )
    reward_manifest_path = tmp_path / "reward-model-schema" / "manifest.json"
    reward_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    reward_manifest_path.write_text(
        json.dumps({"reward_model_id": "reward-model"}) + "\n",
        encoding="utf-8",
    )
    service = _build_service(tmp_path, SuccessfulRunner())

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train-invalid-rlhf-reward-manifest-schema"),
                ext={
                    "operation": "train_lora",
                    "training_mode": "rlhf",
                    "adapter_name": "melix-invalid-rlhf-reward-manifest-schema",
                    "dataset_uri": str(dataset_dir),
                    "reward_model_manifest_path": str(reward_manifest_path),
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "invalid_alignment_config"
    assert events[-1].failed.error.message == "reward model manifest must include schema_version."


def test_train_lora_rejects_cpt_without_text_completion_dataset(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset-invalid-cpt",
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
                output_dir=str(tmp_path / "train-invalid-cpt"),
                ext={
                    "operation": "train_lora",
                    "training_mode": "cpt",
                    "adapter_name": "melix-invalid-cpt",
                    "dataset_uri": str(dataset_dir),
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "invalid_dataset_package"
    assert events[-1].failed.error.details["training_mode"] == "cpt"
    assert events[-1].failed.error.details["required_format"] == "text_completion"
    assert events[-1].failed.error.details["actual_format"] == "chat_messages"


def test_train_lora_rejects_sft_mode_with_preference_pair_dataset(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset-invalid-sft",
        format="preference_pair",
        samples=[
            {
                "prompt": "Choose.",
                "chosen": "A.",
                "rejected": "B.",
            }
        ],
    )
    service = _build_service(tmp_path, SuccessfulRunner())

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train-invalid-sft"),
                ext={
                    "operation": "train_lora",
                    "training_mode": "lora",
                    "adapter_name": "melix-invalid-sft",
                    "dataset_uri": str(dataset_dir),
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "invalid_dataset_package"
    assert events[-1].failed.error.details["training_mode"] == "lora"
    assert events[-1].failed.error.details["required_format"] == (
        "chat_messages,prompt_completion,text_completion"
    )
    assert events[-1].failed.error.details["actual_format"] == "preference_pair"


def test_train_lora_rejects_sft_mode_with_prompt_candidate_dataset(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset-invalid-sft-prompt-candidate",
        format="prompt_candidate",
        samples=[
            {
                "prompt": "Choose.",
                "candidates": ["A.", "B."],
            }
        ],
    )
    service = _build_service(tmp_path, SuccessfulRunner())

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train-invalid-sft-prompt-candidate"),
                ext={
                    "operation": "train_lora",
                    "training_mode": "lora",
                    "adapter_name": "melix-invalid-sft-prompt-candidate",
                    "dataset_uri": str(dataset_dir),
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "invalid_dataset_package"
    assert events[-1].failed.error.details["training_mode"] == "lora"
    assert events[-1].failed.error.details["required_format"] == (
        "chat_messages,prompt_completion,text_completion"
    )
    assert events[-1].failed.error.details["actual_format"] == "prompt_candidate"


def test_train_lora_accepts_sft_mode_with_text_completion_dataset(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset-sft-text-completion",
        format="text_completion",
        samples=[
            {"text": "Domain note one."},
            {"text": "Domain note two."},
        ],
    )
    runner = SuccessfulRunner()
    service = _build_service(tmp_path, runner)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train-sft-text-completion"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "training_mode": "lora",
                    "adapter_name": "melix-sft-text-completion",
                    "dataset_uri": str(dataset_dir),
                },
            ),
            context=None,
        )
    )

    payload = json.loads(next(event.manifest for event in events if event.HasField("manifest")).manifest_json)
    assert events[-1].HasField("completed")
    assert payload["training_mode"] == "lora"
    assert payload["dataset_format"] == "text_completion"
    assert payload["dataset_contract"] == "sft"
    assert runner.last_train_request is not None
    assert runner.last_train_request.config.dataset_contract == "sft"


def test_train_lora_resolves_qwen_attention_preset_and_catalog_support_metadata(tmp_path: Path) -> None:
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
    source_model = service._core._registry.model_catalog.get("melix-dev-text")
    assert source_model is not None
    _configure_lora_family(
        source_model,
        model_path="mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
        family_id="qwen",
        family_kind="dense",
        support_tier="stable",
        default_target_preset="attention_mlp",
    )

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-qwen-attention-adapter",
                    "dataset_uri": str(dataset_dir),
                    "target_modules": "@attention",
                    "num_layers": "2",
                },
            ),
            context=None,
        )
    )

    payload = json.loads(next(event.manifest for event in events if event.HasField("manifest")).manifest_json)

    assert source_model.ext["melix.lora.family_id"] == "qwen"
    assert source_model.ext["melix.lora.family_kind"] == "dense"
    assert source_model.ext["melix.lora.support_tier"] == "stable"
    assert source_model.ext["melix.lora.default_target_preset"] == "attention_mlp"
    assert runner.last_train_request is not None
    assert runner.last_train_request.config.target_modules == ["q_proj", "k_proj", "v_proj", "o_proj"]
    assert runner.last_train_request.config.backend_target_modules == [
        "self_attn.q_proj",
        "self_attn.k_proj",
        "self_attn.v_proj",
        "self_attn.o_proj",
    ]
    assert payload["target_modules"] == [
        "model.layers.0.self_attn.q_proj",
        "model.layers.1.self_attn.q_proj",
        "model.layers.0.self_attn.k_proj",
        "model.layers.1.self_attn.k_proj",
        "model.layers.0.self_attn.v_proj",
        "model.layers.1.self_attn.v_proj",
        "model.layers.0.self_attn.o_proj",
        "model.layers.1.self_attn.o_proj",
    ]


def test_train_lora_resolves_gemma_gated_mlp_preset(tmp_path: Path) -> None:
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
    source_model = service._core._registry.model_catalog.get("melix-dev-text")
    assert source_model is not None

    _configure_lora_family(
        source_model,
        model_path="google/gemma-3-4b-it",
        family_id="gemma",
        family_kind="dense",
        support_tier="stable",
        default_target_preset="attention_mlp",
    )
    gemma_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "gemma-train"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-gemma-mlp-adapter",
                    "dataset_uri": str(dataset_dir),
                    "target_modules": "gated_mlp",
                },
            ),
            context=None,
        )
    )
    gemma_payload = json.loads(next(event.manifest for event in gemma_events if event.HasField("manifest")).manifest_json)
    assert runner.last_train_request is not None
    assert runner.last_train_request.config.family_id == "gemma"
    assert runner.last_train_request.config.target_modules == ["gate_proj", "up_proj", "down_proj"]
    assert gemma_payload["target_modules"] == [
        "model.layers.0.mlp.gate_proj",
        "model.layers.1.mlp.gate_proj",
        "model.layers.0.mlp.up_proj",
        "model.layers.1.mlp.up_proj",
        "model.layers.0.mlp.down_proj",
        "model.layers.1.mlp.down_proj",
    ]


def test_train_lora_resolves_kimi_qkv_preset(tmp_path: Path) -> None:
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
    source_model = service._core._registry.model_catalog.get("melix-dev-text")
    assert source_model is not None

    _configure_lora_family(
        source_model,
        model_path="moonshotai/Kimi-K2-Instruct-0905",
        family_id="kimi",
        family_kind="dense",
        support_tier="stable",
        default_target_preset="attention_mlp",
    )
    kimi_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "kimi-train"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-kimi-qkv-adapter",
                    "dataset_uri": str(dataset_dir),
                    "target_modules": "qkv",
                },
            ),
            context=None,
        )
    )
    kimi_payload = json.loads(next(event.manifest for event in kimi_events if event.HasField("manifest")).manifest_json)
    assert runner.last_train_request is not None
    assert runner.last_train_request.config.family_id == "kimi"
    assert runner.last_train_request.config.target_modules == ["q_proj", "k_proj", "v_proj"]
    assert kimi_payload["target_modules"] == [
        "model.layers.0.self_attn.q_proj",
        "model.layers.1.self_attn.q_proj",
        "model.layers.0.self_attn.k_proj",
        "model.layers.1.self_attn.k_proj",
        "model.layers.0.self_attn.v_proj",
        "model.layers.1.self_attn.v_proj",
    ]


def test_train_lora_separates_moe_hooks_from_dense_defaults(tmp_path: Path) -> None:
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
    source_model = service._core._registry.model_catalog.get("melix-dev-text")
    assert source_model is not None

    _configure_lora_family(
        source_model,
        model_path="mlx-community/Mixtral-8x7B-Instruct-4bit",
        family_id="mixtral",
        family_kind="moe",
        support_tier="experimental",
        default_target_preset="attention",
    )
    mixtral_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "mixtral-train"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-mixtral-attention-adapter",
                    "dataset_uri": str(dataset_dir),
                },
            ),
            context=None,
        )
    )
    mixtral_payload = json.loads(next(event.manifest for event in mixtral_events if event.HasField("manifest")).manifest_json)
    assert runner.last_train_request is not None
    assert runner.last_train_request.config.family_id == "mixtral"
    assert runner.last_train_request.config.target_modules == ["q_proj", "k_proj", "v_proj", "o_proj"]
    assert all("block_sparse_moe" not in item for item in mixtral_payload["target_modules"])

    _configure_lora_family(
        source_model,
        model_path="mlx-community/Qwen3-MoE-30B-A3B-Instruct/4bit",
        family_id="qwen3moe",
        family_kind="moe",
        support_tier="experimental",
        training_ready=False,
        default_target_preset="attention",
    )
    unsupported_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "qwen3moe-train"),
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-qwen3moe-adapter",
                    "dataset_uri": str(dataset_dir),
                },
            ),
            context=None,
        )
    )

    assert unsupported_events[-1].failed.error.code == "unsupported_model_family"
    assert unsupported_events[-1].failed.error.details["family_id"] == "qwen3moe"
    assert unsupported_events[-1].failed.error.details["family_kind"] == "moe"
    assert unsupported_events[-1].failed.error.details["support_tier"] == "experimental"
    assert unsupported_events[-1].failed.error.details["training_ready"] == "false"


def test_train_lora_resolves_qwen3moe_expert_preset_and_adapter_backed_activation(
    tmp_path: Path,
) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset",
        samples=[
            {
                "messages": [
                    {"role": "user", "content": "Route expert adapters."},
                    {"role": "assistant", "content": "Use deterministic experts."},
                ]
            }
        ],
    )
    runner = SuccessfulRunner()
    service = _build_service(tmp_path, runner)
    source_model = service._core._registry.model_catalog.get("melix-dev-text")
    assert source_model is not None
    source_model.quant_profile_id = "q4"
    source_model.ext["text_family_id"] = "qwen3moe"
    source_model.ext["text_layer_count"] = "1"
    source_model.ext["melix.text.moe.expert_count"] = "2"
    source_model.ext["melix.text.moe.expert_count_source"] = "config"
    _configure_lora_family(
        source_model,
        model_path="mlx-community/Qwen3-MoE-30B-A3B-Instruct/4bit",
        family_id="qwen3moe",
        family_kind="moe",
        support_tier="experimental",
        default_target_preset="attention",
    )

    train_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "qwen3moe-train"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "training_mode": "qlora",
                    "adapter_name": "melix-qwen3moe-experts-adapter",
                    "dataset_uri": str(dataset_dir),
                    "target_modules": "experts",
                    "num_layers": "1",
                    "derived_model_alias": "melix-qwen3moe-experts",
                },
            ),
            context=None,
        )
    )
    train_payload = json.loads(next(event.manifest for event in train_events if event.HasField("manifest")).manifest_json)

    assert runner.last_train_request is not None
    assert runner.last_train_request.config.family_id == "qwen3moe"
    assert runner.last_train_request.config.training_mode == "qlora"
    assert runner.last_train_request.config.quantization_mode == "quantized_base"
    assert runner.last_train_request.config.target_modules == ["gate_proj", "up_proj", "down_proj"]
    assert runner.last_train_request.config.backend_target_modules == [
        "mlp.experts.0.gate_proj",
        "mlp.experts.1.gate_proj",
        "mlp.experts.0.up_proj",
        "mlp.experts.1.up_proj",
        "mlp.experts.0.down_proj",
        "mlp.experts.1.down_proj",
    ]
    assert train_payload["target_modules"] == [
        "model.layers.0.mlp.experts.0.gate_proj",
        "model.layers.0.mlp.experts.1.gate_proj",
        "model.layers.0.mlp.experts.0.up_proj",
        "model.layers.0.mlp.experts.1.up_proj",
        "model.layers.0.mlp.experts.0.down_proj",
        "model.layers.0.mlp.experts.1.down_proj",
    ]
    assert train_payload["source_model"] == "melix-dev-text"
    assert train_payload["quantization_mode"] == "quantized_base"

    activate_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "qwen3moe-activate"),
                generate_manifest=True,
                ext={
                    "operation": "activate_adapter",
                    "artifact_path": train_events[-1].completed.output_path,
                    "activation_mode": "adapter_backed_runtime",
                },
            ),
            context=None,
        )
    )
    activation_payload = json.loads(
        next(event.manifest for event in activate_events if event.HasField("manifest")).manifest_json
    )

    assert activation_payload["activation_mode"] == "adapter_backed_runtime"
    assert activation_payload["source_model_quant_profile_id"] == "q4"
    assert activation_payload["source_model_ext"]["melix.lora.family_id"] == "qwen3moe"
    assert activation_payload["source_model_ext"]["melix.text.moe.expert_count"] == "2"
    assert activation_payload["derived_model_alias"] == "melix-qwen3moe-experts"
    registered_model = service._core._registry.model_catalog.get(activation_payload["derived_model_id"])
    assert registered_model is not None
    assert registered_model.quant_profile_id == "q4"
    assert registered_model.ext["melix.lora.family_id"] == "qwen3moe"
    assert registered_model.ext["melix.text.moe.expert_count"] == "2"
    assert registered_model.ext["melix.text.moe.expert_count_source"] == "config"


@pytest.mark.parametrize("unsafe_target", ["embed_tokens", "lm_head"])
def test_train_lora_rejects_quantized_qwen3moe_unsafe_targets(
    tmp_path: Path,
    unsafe_target: str,
) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / f"dataset-{unsafe_target}",
        samples=[
            {
                "messages": [
                    {"role": "user", "content": "Unsafe target?"},
                    {"role": "assistant", "content": "Reject it."},
                ]
            }
        ],
    )
    service = _build_service(tmp_path, SuccessfulRunner())
    source_model = service._core._registry.model_catalog.get("melix-dev-text")
    assert source_model is not None
    source_model.quant_profile_id = "q4"
    source_model.ext["text_family_id"] = "qwen3moe"
    source_model.ext["melix.text.moe.expert_count"] = "2"
    source_model.ext["melix.text.moe.expert_count_source"] = "config"
    _configure_lora_family(
        source_model,
        model_path="mlx-community/Qwen3-MoE-30B-A3B-Instruct/4bit",
        family_id="qwen3moe",
        family_kind="moe",
        support_tier="experimental",
        default_target_preset="attention",
    )

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / f"qwen3moe-{unsafe_target}"),
                ext={
                    "operation": "train_lora",
                    "training_mode": "qlora",
                    "adapter_name": "melix-qwen3moe-unsafe-adapter",
                    "dataset_uri": str(dataset_dir),
                    "target_modules": unsafe_target,
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "unsupported_lora_target_module"
    assert events[-1].failed.error.details["family_id"] == "qwen3moe"
    assert events[-1].failed.error.details["target_module"] == unsafe_target
    assert events[-1].failed.error.details["unsupported_target_class"] == "embedding_or_head"


def test_train_lora_rejects_qwen3moe_expert_preset_without_expert_count_metadata(
    tmp_path: Path,
) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset-missing-expert-count",
        samples=[
            {
                "messages": [
                    {"role": "user", "content": "Missing experts?"},
                    {"role": "assistant", "content": "Fail closed."},
                ]
            }
        ],
    )
    service = _build_service(tmp_path, SuccessfulRunner())
    source_model = service._core._registry.model_catalog.get("melix-dev-text")
    assert source_model is not None
    source_model.quant_profile_id = "q4"
    source_model.ext["text_family_id"] = "qwen3moe"
    source_model.ext["melix.text.moe.expert_count"] = "128"
    source_model.ext["melix.text.moe.expert_count_source"] = "family_default"
    _configure_lora_family(
        source_model,
        model_path="mlx-community/Qwen3-MoE-Unknown-Experts/4bit",
        family_id="qwen3moe",
        family_kind="moe",
        support_tier="experimental",
        default_target_preset="attention",
    )

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "qwen3moe-missing-expert-count"),
                ext={
                    "operation": "train_lora",
                    "training_mode": "qlora",
                    "adapter_name": "melix-qwen3moe-experts-adapter",
                    "dataset_uri": str(dataset_dir),
                    "target_modules": "experts",
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "unsupported_lora_target_module"
    assert events[-1].failed.error.details["family_id"] == "qwen3moe"
    assert events[-1].failed.error.details["target_module_class"] == "expert"
    assert events[-1].failed.error.details["metadata_key"] == "melix.text.moe.expert_count"
    assert events[-1].failed.error.details["metadata_source_key"] == "melix.text.moe.expert_count_source"
    assert events[-1].failed.error.details["metadata_source"] == "family_default"


def test_training_config_validates_direct_error_paths() -> None:
    non_text_model = common_pb2.ModelSpec(model_id="embed", model_kind="embedding")
    with pytest.raises(Exception) as non_text_error:
        training_config_module.normalize_training_config(
            source_model=non_text_model,
            ext={},
            dataset_format="text_completion",
            response_only_supported=True,
            sample_count=1,
        )
    assert non_text_error.value.code == "unsupported_model_family"

    text_model = common_pb2.ModelSpec(
        model_id="plain-text",
        model_path="models/plain-llama",
        model_kind="text",
        revision="dev",
        max_context=2048,
        ext={"text_family_id": "llama"},
    )
    with pytest.raises(Exception) as bad_mode_error:
        training_config_module.normalize_training_config(
            source_model=text_model,
            ext={"training_mode": "ppo"},
            dataset_format="text_completion",
            response_only_supported=True,
            sample_count=1,
        )
    assert bad_mode_error.value.code == "unsupported_training_mode"

    dora_config = training_config_module.normalize_training_config(
        source_model=text_model,
        ext={"training_mode": "dora"},
        dataset_format="text_completion",
        response_only_supported=False,
        sample_count=1,
    )
    assert dora_config.training_mode == "dora"
    assert dora_config.adapter_algorithm == "dora"
    assert dora_config.training_objective == "supervised_finetuning"

    with pytest.raises(Exception) as preset_error:
        training_config_module.normalize_training_config(
            source_model=text_model,
            ext={"preset_id": "unknown-preset"},
            dataset_format="text_completion",
            response_only_supported=True,
            sample_count=1,
        )
    assert preset_error.value.code == "invalid_training_preset"

    with pytest.raises(Exception) as response_error:
        training_config_module.normalize_training_config(
            source_model=text_model,
            ext={"response_only": "true"},
            dataset_format="prompt_completion",
            response_only_supported=False,
            sample_count=1,
        )
    assert response_error.value.code == "invalid_dataset_package"


def test_training_config_helper_resolution_paths_and_limits() -> None:
    assert training_config_module._resolve_family_id(
        common_pb2.ModelSpec(model_id="explicit", model_kind="text", ext={"melix.lora.family_id": "qwen"})
    ) == "qwen"
    assert training_config_module._resolve_family_id(
        common_pb2.ModelSpec(model_id="detected", model_kind="text", ext={"detected_family_id": "gemma"})
    ) == "gemma"
    assert training_config_module._resolve_family_id(
        common_pb2.ModelSpec(model_id="heuristic", model_kind="text", model_path="models/deepseek-v3")
    ) == "deepseek-mla"
    assert training_config_module._resolve_family_id(
        common_pb2.ModelSpec(model_id="heuristic", model_kind="text", model_path="models/mistral-small-4")
    ) == "mistral4"
    assert training_config_module._resolve_family_id(
        common_pb2.ModelSpec(model_id="heuristic", model_kind="text", model_path="models/nemotron-h")
    ) == "nemotron-h"

    hooks = training_config_module._resolve_family_hooks(
        common_pb2.ModelSpec(
            model_id="mixtral",
            model_kind="text",
            ext={"melix.lora.family_kind": "moe", "melix.lora.support_tier": "experimental"},
        ),
        family_id="mixtral",
    )
    assert hooks["family_kind"] == "moe"
    assert hooks["support_tier"] == "experimental"
    assert hooks["default_target_preset"] == "attention"

    mistral4_hooks = training_config_module._resolve_family_hooks(
        common_pb2.ModelSpec(model_id="mistral4", model_kind="text"),
        family_id="mistral4",
    )
    assert mistral4_hooks["family_kind"] == "dense"
    assert mistral4_hooks["support_tier"] == "experimental"
    assert mistral4_hooks["training_ready"] == "false"

    qwen3moe_hooks = training_config_module._resolve_family_hooks(
        common_pb2.ModelSpec(model_id="qwen3moe", model_kind="text"),
        family_id="qwen3moe",
    )
    assert qwen3moe_hooks["training_ready"] == "false"

    # Mixed preset aliases and literal module names should collapse to one deduplicated target set.
    qwen_targets = training_config_module._resolve_target_modules(
        "@attention,q_proj,attention",
        profile=training_config_module._FAMILY_PROFILES["qwen"],
    )
    assert qwen_targets == ["q_proj", "k_proj", "v_proj", "o_proj"]
    assert training_config_module._resolve_target_modules(
        "",
        profile=training_config_module._FAMILY_PROFILES["mixtral"],
    ) == ["q_proj", "k_proj", "v_proj", "o_proj"]
    assert training_config_module._resolve_target_modules(
        "attention_experts",
        profile=training_config_module._FAMILY_PROFILES["qwen3moe"],
    ) == ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    assert training_config_module._backend_target_modules(["standalone.module"]) == ["standalone.module"]

    bounded = training_config_module.normalize_training_config(
        source_model=common_pb2.ModelSpec(
            model_id="bounded",
            model_path="models/qwen",
            model_kind="text",
            revision="dev",
            max_context=4096,
            quant_profile_id="q4",
            ext={
                "text_family_id": "qwen",
                "text_layer_count": "4",
                "melix.lora.family_id": "qwen",
                "melix.lora.family_kind": "dense",
                "melix.lora.support_tier": "stable",
                "melix.lora.training_ready": "true",
                "melix.lora.default_target_preset": "attention_mlp",
            },
        ),
        ext={
            "training_mode": "qlora",
            "batch_size": "4",
            "epochs": "3",
            "max_steps": "2",
            "preset_id": "balanced_adapter",
        },
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
        validation_sample_count=1,
    )
    assert bounded.iters == 2
    assert bounded.steps_per_eval == 2

    with pytest.raises(Exception) as int_error:
        training_config_module._int_value("0", default=1, minimum=1, field_name="rank")
    assert int_error.value.code == "invalid_argument"

    with pytest.raises(Exception) as int_parse_error:
        training_config_module._int_value("two", default=1, minimum=1, field_name="rank")
    assert int_parse_error.value.code == "invalid_argument"
    assert int_parse_error.value.details["field"] == "rank"

    with pytest.raises(Exception) as float_error:
        training_config_module._float_value("-0.5", default=0.0, minimum=0.0, field_name="dropout")
    assert float_error.value.code == "invalid_argument"

    with pytest.raises(Exception) as float_parse_error:
        training_config_module._float_value("wide", default=0.0, minimum=0.0, field_name="dropout")
    assert float_parse_error.value.code == "invalid_argument"
    assert float_parse_error.value.details["field"] == "dropout"


def test_quantized_lora_target_safety_uses_exact_leaf_names() -> None:
    training_config_module._reject_unsafe_quantized_lora_targets(
        ["classifier.head.weight", "router.score", "model.layers.0.output.gate_proj"],
        family_id="qwen",
        training_mode="lora",
        quantization_mode="quantized_base",
    )

    with pytest.raises(Exception) as unsafe_error:
        training_config_module._reject_unsafe_quantized_lora_targets(
            ["model.embed_tokens"],
            family_id="qwen",
            training_mode="lora",
            quantization_mode="quantized_base",
        )

    assert unsafe_error.value.code == "unsupported_lora_target_module"
    assert unsafe_error.value.details["target_module"] == "model.embed_tokens"


def test_quantized_base_detection_uses_token_boundaries() -> None:
    assert training_config_module._is_quantized_base_model(
        common_pb2.ModelSpec(model_id="qwen", model_path="models/q4_k_m", model_kind="text")
    )
    assert training_config_module._is_quantized_base_model(
        common_pb2.ModelSpec(model_id="qwen", model_path="models/4bit", model_kind="text")
    )
    assert not training_config_module._is_quantized_base_model(
        common_pb2.ModelSpec(model_id="qwen", model_path="models/aq4ua", model_kind="text")
    )
    assert not training_config_module._is_quantized_base_model(
        common_pb2.ModelSpec(model_id="qwen", model_path="models/optiqon", model_kind="text")
    )


def test_resolve_training_dataset_rejects_hf_valid_split_for_local_package(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset",
        samples=[
            {
                "text": "hello",
            }
        ],
        format="text_completion",
    )

    with pytest.raises(Exception) as exc:
        resolve_training_dataset_package(
            {
                "dataset_source_kind": "local_package",
                "dataset_uri": str(dataset_dir),
                "hf_valid_split": "validation",
            },
            jobs_root=tmp_path / "jobs",
        )

    assert exc.value.code == "invalid_dataset_source"


def test_resolve_training_dataset_package_reuses_materialized_hf_package_without_reloading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_path = tmp_path / "datasets" / "cached-hf"
    package = TrainingDatasetPackage(
        package_path=package_path,
        manifest_path=package_path / "manifest.json",
        samples_path=package_path / "samples.jsonl",
        schema_version="melix.training_dataset_package.v1",
        dataset_id="melix/demo-hf:default:train@main",
        format="text_completion",
        sample_count=1,
        version="main",
        normalized_samples=[{"text": "hello world"}],
        normalized_validation_samples=[],
        validation_sample_count=0,
        response_only_supported=False,
    )
    reference = HFDatasetReference(
        dataset_path="melix/demo-hf",
        dataset_name="default",
        dataset_revision="main",
        train_split="train",
        valid_split="",
        chat_feature="",
        prompt_feature="",
        completion_feature="",
        text_feature="text",
    )

    monkeypatch.setattr(
        training_dataset_module,
        "materialize_hf_training_dataset_package",
        lambda *args, **kwargs: MaterializedTrainingDatasetPackage(
            package_path=package_path,
            cache_key="cached-hf",
            cache_hit=False,
            dataset_uri="hf://melix/demo-hf",
            reference=reference,
            package=package,
        ),
    )

    def fail_load(*args, **kwargs):
        raise AssertionError("resolve_training_dataset_package should reuse the freshly materialized package")

    monkeypatch.setattr(training_dataset_module, "load_training_dataset_package", fail_load)

    resolved = resolve_training_dataset_package(
        {"dataset_source_kind": "hf_dataset", "hf_dataset_path": "melix/demo-hf"},
        jobs_root=tmp_path / "jobs",
    )

    assert resolved.package is package
    assert resolved.cache_hit is False
    assert resolved.materialized_package_path == package_path
    assert resolved.dataset_uri == "hf://melix/demo-hf"



def test_materialize_hf_training_dataset_rejects_empty_row_payload(tmp_path: Path) -> None:
    reference = HFDatasetReference(
        dataset_path="melix/demo-hf",
        dataset_name="default",
        dataset_revision="main",
        train_split="train",
        valid_split="",
        chat_feature="",
        prompt_feature="",
        completion_feature="",
        text_feature="text",
    )

    def empty_fetcher(endpoint: str, params: dict[str, str]) -> dict[str, object]:
        if endpoint == "rows":
            return {"rows": []}
        raise AssertionError(f"Unexpected endpoint: {endpoint}")

    with pytest.raises(Exception) as exc:
        materialize_hf_training_dataset_package(
            reference,
            cache_root=tmp_path / "datasets",
            fetch_json=empty_fetcher,
        )
    assert exc.value.code == "hf_dataset_fetch_failed"


def test_hf_dataset_fetcher_reports_http_url_json_and_shape_errors(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return self._payload

    def raise_http(request, timeout: int):
        raise HTTPError(request.full_url, 429, "rate limited", hdrs=None, fp=None)

    monkeypatch.setattr(training_dataset_module, "urlopen", raise_http)
    with pytest.raises(Exception) as http_exc:
        training_dataset_module._fetch_hf_dataset_server_json("rows", {"dataset": "melix/demo-hf"})
    assert http_exc.value.code == "hf_dataset_fetch_failed"

    def raise_url(request, timeout: int):
        raise URLError("offline")

    monkeypatch.setattr(training_dataset_module, "urlopen", raise_url)
    with pytest.raises(Exception) as url_exc:
        training_dataset_module._fetch_hf_dataset_server_json("rows", {"dataset": "melix/demo-hf"})
    assert url_exc.value.code == "hf_dataset_fetch_failed"

    monkeypatch.setattr(
        training_dataset_module,
        "urlopen",
        lambda request, timeout: FakeResponse(b"{not-json"),
    )
    with pytest.raises(Exception) as json_exc:
        training_dataset_module._fetch_hf_dataset_server_json("rows", {"dataset": "melix/demo-hf"})
    assert json_exc.value.code == "hf_dataset_fetch_failed"

    monkeypatch.setattr(
        training_dataset_module,
        "urlopen",
        lambda request, timeout: FakeResponse(b"[]"),
    )
    with pytest.raises(Exception) as shape_exc:
        training_dataset_module._fetch_hf_dataset_server_json("rows", {"dataset": "melix/demo-hf"})
    assert shape_exc.value.code == "hf_dataset_fetch_failed"

    captured_headers: dict[str, str] = {}

    def success_urlopen(request, timeout: int):
        for key, value in request.header_items():
            captured_headers[key.lower()] = value
        return FakeResponse(b"{}")

    monkeypatch.setenv("HF_TOKEN", "secret-token")
    monkeypatch.setattr(training_dataset_module, "urlopen", success_urlopen)
    assert training_dataset_module._fetch_hf_dataset_server_json("rows", {"dataset": "melix/demo-hf"}) == {}
    assert captured_headers["authorization"] == "Bearer secret-token"


def test_reference_from_cached_manifest_handles_invalid_payloads(tmp_path: Path) -> None:
    reference = HFDatasetReference(
        dataset_path="melix/demo-hf",
        dataset_name="default",
        dataset_revision="main",
        train_split="train",
        valid_split="",
        chat_feature="",
        prompt_feature="",
        completion_feature="",
        text_feature="text",
    )
    manifest_path = tmp_path / "manifest.json"

    manifest_path.write_text("{not-json", encoding="utf-8")
    assert training_dataset_module._reference_from_cached_manifest(reference, manifest_path) == reference

    manifest_path.write_text("[]", encoding="utf-8")
    assert training_dataset_module._reference_from_cached_manifest(reference, manifest_path) == reference


def test_hf_dataset_helper_resolution_and_mapping_paths() -> None:
    reference = HFDatasetReference(
        dataset_path="melix/demo-hf",
        dataset_name="",
        dataset_revision="main",
        train_split="train",
        valid_split="",
        chat_feature="messages",
        prompt_feature="",
        completion_feature="",
        text_feature="",
    )

    assert (
        training_dataset_module._resolve_hf_dataset_name(
            reference,
            lambda endpoint, params: {"splits": [{"split": "validation", "config": "fallback"}]},
        )
        == "fallback"
    )

    with pytest.raises(Exception) as missing_splits:
        training_dataset_module._resolve_hf_dataset_name(
            reference,
            lambda endpoint, params: {"splits": []},
        )
    assert missing_splits.value.code == "hf_dataset_fetch_failed"

    with pytest.raises(Exception) as missing_config:
        training_dataset_module._resolve_hf_dataset_name(
            reference,
            lambda endpoint, params: {"splits": [{"split": "train"}]},
        )
    assert missing_config.value.code == "hf_dataset_fetch_failed"

    fetch_calls: list[tuple[str, dict[str, str]]] = []

    def paged_fetcher(endpoint: str, params: dict[str, str]) -> dict[str, object]:
        fetch_calls.append((endpoint, dict(params)))
        return {
            "rows": [
                {"row": {"text": "alpha"}},
                "skip-me",
                {"row": {"text": "beta"}},
            ]
        }

    rows = training_dataset_module._fetch_hf_dataset_rows(
        HFDatasetReference(
            dataset_path="melix/demo-hf",
            dataset_name="default",
            dataset_revision="main",
            train_split="train",
            valid_split="",
            chat_feature="",
            prompt_feature="",
            completion_feature="",
            text_feature="text",
        ),
        paged_fetcher,
    )
    assert rows == [{"text": "alpha"}, {"text": "beta"}]
    assert fetch_calls[0][0] == "rows"

    with pytest.raises(Exception) as malformed_rows:
        training_dataset_module._fetch_hf_dataset_rows(
            HFDatasetReference(
                dataset_path="melix/demo-hf",
                dataset_name="default",
                dataset_revision="main",
                train_split="train",
                valid_split="",
                chat_feature="",
                prompt_feature="",
                completion_feature="",
                text_feature="text",
            ),
            lambda endpoint, params: {"rows": "bad"},
        )
    assert malformed_rows.value.code == "hf_dataset_fetch_failed"

    assert training_dataset_module._infer_hf_dataset_format(
        HFDatasetReference(
            dataset_path="melix/demo-hf",
            dataset_name="default",
            dataset_revision="main",
            train_split="train",
            valid_split="",
            chat_feature="",
            prompt_feature="prompt",
            completion_feature="completion",
            text_feature="",
        ),
        [{"prompt": "p", "completion": "c"}],
    ) == "prompt_completion"
    assert training_dataset_module._infer_hf_dataset_format(
        HFDatasetReference(
            dataset_path="melix/demo-hf",
            dataset_name="default",
            dataset_revision="main",
            train_split="train",
            valid_split="",
            chat_feature="",
            prompt_feature="",
            completion_feature="",
            text_feature="text",
        ),
        [{"text": "hello"}],
    ) == "text_completion"

    with pytest.raises(Exception) as format_error:
        training_dataset_module._infer_hf_dataset_format(
            HFDatasetReference(
                dataset_path="melix/demo-hf",
                dataset_name="default",
                dataset_revision="main",
                train_split="train",
                valid_split="",
                chat_feature="",
                prompt_feature="",
                completion_feature="",
                text_feature="",
            ),
            [{"unknown": "field"}],
        )
    assert format_error.value.code == "hf_dataset_fetch_failed"

    assert training_dataset_module._map_hf_row_to_training_sample(
        {"prompt": "p", "completion": "c"},
        "prompt_completion",
        HFDatasetReference(
            dataset_path="melix/demo-hf",
            dataset_name="default",
            dataset_revision="main",
            train_split="train",
            valid_split="",
            chat_feature="",
            prompt_feature="prompt",
            completion_feature="completion",
            text_feature="",
        ),
    ) == {"prompt": "p", "completion": "c"}
    assert training_dataset_module._map_hf_row_to_training_sample(
        {"text": "hello"},
        "text_completion",
        HFDatasetReference(
            dataset_path="melix/demo-hf",
            dataset_name="default",
            dataset_revision="main",
            train_split="train",
            valid_split="",
            chat_feature="",
            prompt_feature="",
            completion_feature="",
            text_feature="text",
        ),
    ) == {"text": "hello"}

    with pytest.raises(Exception) as chat_error:
        training_dataset_module._map_hf_row_to_training_sample(
            {"messages": "bad"},
            "chat_messages",
            reference,
        )
    assert chat_error.value.code == "hf_dataset_fetch_failed"

    with pytest.raises(Exception) as prompt_error:
        training_dataset_module._map_hf_row_to_training_sample(
            {"prompt": "p"},
            "prompt_completion",
            HFDatasetReference(
                dataset_path="melix/demo-hf",
                dataset_name="default",
                dataset_revision="main",
                train_split="train",
                valid_split="",
                chat_feature="",
                prompt_feature="prompt",
                completion_feature="completion",
                text_feature="",
            ),
        )
    assert prompt_error.value.code == "hf_dataset_fetch_failed"

    with pytest.raises(Exception) as text_error:
        training_dataset_module._map_hf_row_to_training_sample(
            {"body": "p"},
            "text_completion",
            HFDatasetReference(
                dataset_path="melix/demo-hf",
                dataset_name="default",
                dataset_revision="main",
                train_split="train",
                valid_split="",
                chat_feature="",
                prompt_feature="",
                completion_feature="",
                text_feature="text",
            ),
        )
    assert text_error.value.code == "hf_dataset_fetch_failed"


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
                    "derived_model_alias": "Activated Alias",
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
    assert activation_payload["derived_model_alias"] == "Activated Alias"
    assert activation_payload["source_adapter_job_id"] == "model-ops-0001"
    assert train_events[-1].completed.output_path == str(
        tmp_path / "model-ops" / "train_lora" / "model-ops-0001" / "train_lora.adapter.json"
    )
    assert activate_events[-1].completed.output_path == str(
        tmp_path
        / "model-ops"
        / "activate_adapter"
        / "model-ops-0002"
        / activation_payload["derived_model_id"]
        / "manifest.json"
    )
    assert activation_payload["adapter_set_hash"]
    assert Path(activation_payload["derived_model_path"]).is_dir()
    assert snapshot_payload["adapters"][0]["activation_status"] == "activated"
    assert snapshot_payload["adapters"][0]["derived_model_id"] == activation_payload["derived_model_id"]
    assert snapshot_payload["derived_models"][0]["model_id"] == activation_payload["derived_model_id"]
    assert snapshot_payload["derived_models"][0]["adapter_manifest_path"] == train_events[-1].completed.output_path


def test_activate_adapter_supports_adapter_backed_runtime_and_uses_training_alias(tmp_path: Path) -> None:
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
                    "derived_model_alias": "Preferred Alias",
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
                    "activation_mode": "adapter_backed_runtime",
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

    source_model = service._core._registry.model_catalog.get("melix-dev-text")
    assert source_model is not None
    assert runner.native_activation_calls == 0
    assert activation_payload["activation_mode"] == "adapter_backed_runtime"
    assert activation_payload["derived_model_alias"] == "Preferred Alias"
    assert activation_payload["base_model_repo_id"] == "melix-dev-text"
    assert activation_payload["adapter_manifest_path"] == adapter_manifest_path
    assert activation_payload["adapter_weights_path"].endswith("adapters.safetensors")
    assert activation_payload["source_model_kind"] == "text"
    assert activation_payload["source_model_ext"]["text_family_id"] == "llama"
    assert activation_payload["derived_model_path"] == source_model.model_path
    assert activation_payload["remove_supported"] is True
    assert snapshot_payload["adapters"][0]["activation_mode"] == "adapter_backed_runtime"
    assert snapshot_payload["adapters"][0]["activation_backend"] == "internal"
    assert snapshot_payload["adapters"][0]["adapter_weights_path"] == activation_payload["adapter_weights_path"]
    # RuntimeMode enum flows through the snapshot alongside the legacy string.
    # RUNTIME_MODE_ADAPTER_BACKED = 2 per worker/v1/common.proto.
    assert snapshot_payload["adapters"][0]["runtime_mode"] == 2
    assert snapshot_payload["derived_models"][0]["activation_mode"] == "adapter_backed_runtime"
    assert snapshot_payload["derived_models"][0]["activation_backend"] == "internal"
    assert snapshot_payload["derived_models"][0]["runtime_mode"] == 2
    assert snapshot_payload["derived_models"][0]["model_id"] == activation_payload["derived_model_id"]

    registered_model = service._core._registry.model_catalog.get(activation_payload["derived_model_id"])
    assert registered_model is not None
    assert registered_model.model_path == source_model.model_path
    assert registered_model.ext["melix.activation_mode"] == "adapter_backed_runtime"
    assert registered_model.ext["melix.adapter_manifest_path"] == adapter_manifest_path
    # Typed RuntimeMode enum must propagate from activation manifest through
    # catalog registration — this is the authoritative signal the runtime
    # backend keys off to decide adapter-aware load behavior.
    assert registered_model.runtime_mode == common_pb2.RUNTIME_MODE_ADAPTER_BACKED
    loaded = service._core._registry.load_model(
        common_pb2.ModelSpec(model_id=activation_payload["derived_model_id"])
    )
    assert loaded.spec.model_id == activation_payload["derived_model_id"]
    assert loaded.spec.ext["melix.adapter_weights_path"] == activation_payload["adapter_weights_path"]
    assert loaded.spec.runtime_mode == common_pb2.RUNTIME_MODE_ADAPTER_BACKED


def test_activate_adapter_rejects_unknown_activation_mode(tmp_path: Path) -> None:
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
                ext={
                    "operation": "activate_adapter",
                    "artifact_path": adapter_manifest_path,
                    "activation_mode": "mystery_mode",
                },
            ),
            context=None,
        )
    )

    assert activate_events[-1].failed.error.code == "activation_failure"


def test_remove_derived_model_deletes_artifacts_and_prunes_registry_snapshot(tmp_path: Path) -> None:
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
                    "derived_model_alias": "Removable Alias",
                },
            ),
            context=None,
        )
    )
    activation_payload = json.loads(
        next(event.manifest for event in activate_events if event.HasField("manifest")).manifest_json
    )

    loaded_handle = service._core._registry.load_model(
        common_pb2.ModelSpec(
            model_id=activation_payload["derived_model_id"],
            model_path=activation_payload["derived_model_path"],
            model_kind="text",
            revision="derived",
            max_context=4096,
        )
    ).handle
    assert loaded_handle in service._core._registry.list_loaded_models()

    remove_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "remove"),
                generate_manifest=True,
                ext={
                    "operation": "remove_derived_model",
                    "derived_model_id": activation_payload["derived_model_id"],
                },
            ),
            context=None,
        )
    )

    removal_payload = json.loads(
        next(event.manifest for event in remove_events if event.HasField("manifest")).manifest_json
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

    assert removal_payload["derived_model_id"] == activation_payload["derived_model_id"]
    assert removal_payload["activation_mode"] == "fused_derived_model"
    assert removal_payload["unloaded"] is True
    assert not Path(activation_payload["derived_model_path"]).exists()
    assert service._core._registry.list_loaded_models() == []
    assert snapshot_payload["derived_models"] == []
    assert snapshot_payload["adapters"][0]["activation_status"] == "removed"



def test_adapter_backed_runtime_catalog_registration_restores_from_jobs_root(tmp_path: Path) -> None:
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
                    "activation_mode": "adapter_backed_runtime",
                },
            ),
            context=None,
        )
    )
    activation_payload = json.loads(
        next(event.manifest for event in activate_events if event.HasField("manifest")).manifest_json
    )

    restored_service = _build_service(tmp_path, SuccessfulRunner())
    restored_model = restored_service._core._registry.model_catalog.get(activation_payload["derived_model_id"])

    assert restored_model is not None
    assert restored_model.model_path == activation_payload["derived_model_path"]
    assert restored_model.ext["melix.activation_mode"] == "adapter_backed_runtime"
    # RuntimeMode enum survives the catalog-rebuild-from-jobs-root path too.
    assert restored_model.runtime_mode == common_pb2.RUNTIME_MODE_ADAPTER_BACKED
    loaded = restored_service._core._registry.load_model(
        common_pb2.ModelSpec(model_id=activation_payload["derived_model_id"])
    )
    assert loaded.spec.ext["melix.adapter_manifest_path"] == adapter_manifest_path
    assert loaded.spec.runtime_mode == common_pb2.RUNTIME_MODE_ADAPTER_BACKED


def test_remove_derived_model_requires_a_known_target(tmp_path: Path) -> None:
    service = _build_service(tmp_path, SuccessfulRunner())

    missing_target_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "remove"),
                ext={"operation": "remove_derived_model"},
            ),
            context=None,
        )
    )
    assert missing_target_events[-1].failed.error.code == "invalid_argument"

    unknown_target_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "remove-missing"),
                ext={
                    "operation": "remove_derived_model",
                    "derived_model_id": "missing-derived-model",
                },
            ),
            context=None,
        )
    )
    assert unknown_target_events[-1].failed.error.code == "not_found"


def test_activate_native_passes_repo_id_strings_to_save(monkeypatch, tmp_path: Path) -> None:
    recorded: dict[str, object] = {}

    def fake_load(model_path: str, *, adapter_path: str, return_config: bool):
        recorded["load_model_path"] = model_path
        recorded["load_adapter_path"] = adapter_path
        recorded["return_config"] = return_config

        class FakeModel:
            def named_modules(self):
                return []

            def update_modules(self, modules):
                recorded["updated_modules"] = modules

        return FakeModel(), object(), {"model_type": "llama"}

    def fake_save(output_dir, repo_id_or_path, model, tokenizer, config, donate_model=False):
        recorded["save_output_dir"] = output_dir
        recorded["save_base_model"] = repo_id_or_path
        recorded["save_donate_model"] = donate_model

    monkeypatch.setitem(
        sys.modules,
        "mlx.utils",
        types.SimpleNamespace(tree_unflatten=lambda items: items),
    )
    monkeypatch.setitem(
        sys.modules,
        "mlx_lm.utils",
        types.SimpleNamespace(load=fake_load, save=fake_save),
    )

    runner = MLXLMRunner()
    request = ActivationRequest(
        job_id="model-ops-activate-1",
        base_model_id="melix-dev-text",
        model_path=Path("mlx-community/Qwen3.5-0.8B-OptiQ-4bit"),
        adapter_dir=tmp_path / "adapter",
        adapter_manifest_path=tmp_path / "adapter" / "train_lora.adapter.json",
        derived_model_dir=tmp_path / "derived",
        activation_mode="fused_derived_model",
    )
    request.adapter_dir.mkdir(parents=True, exist_ok=True)
    request.adapter_manifest_path.write_text("{}", encoding="utf-8")

    result = runner.activate_native(request)

    assert recorded["load_model_path"] == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
    assert recorded["save_base_model"] == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
    assert isinstance(recorded["save_base_model"], str)
    assert result.manifest_path == request.derived_model_dir / "manifest.json"
