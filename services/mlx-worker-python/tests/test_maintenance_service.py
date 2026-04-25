from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from packages.protocol.python.worker.v1 import common_pb2, maintenance_pb2

from worker.grpc_server import WorkerMaintenanceService
from worker.model_ops.adapter_activation_pipeline import AdapterActivationPipeline
from worker.model_ops.job_registry import ModelOpsJob, ModelOpsJobRegistry
from worker.model_ops.hub_catalog import (
    HubCatalogError,
    HubModelCardRecord,
    HubModelSummaryRecord,
    HubSearchPage,
)
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
from worker.model_ops.upload_receipt_pipeline import (
    HuggingFacePublishBackend,
    PublishResult,
    SourceArtifactDescriptor,
    UploadReceiptPipeline,
    _resolve_hf_cli_command,
)
from worker.productization.benchmark_schemas import (
    build_serving_benchmark_job,
    build_serving_benchmark_results,
)
from worker.productization.benchmark_suites import BenchmarkSuiteCatalog
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.engine.maintenance_core import MaintenanceCore
from worker.engine import maintenance_core as maintenance_core_module
from worker.runtime.deterministic_backend import DeterministicTextBackend
from worker.runtime.mlx_vlm_runtime import AutoMLXVLMBackend, MLXVLMRuntime
from worker.runtime.mlx_text_runtime import MLXTextRuntime, RuntimeTokenEvent


class DeterministicLoRARunner(MLXLMRunner):
    def train_native(self, request: TrainingRequest) -> TrainingResult:
        request.adapter_output_dir.mkdir(parents=True, exist_ok=True)
        weights_path = request.adapter_output_dir / "adapters.safetensors"
        adapter_config_path = request.adapter_output_dir / "adapter_config.json"
        checkpoint_dir = request.adapter_output_dir / "checkpoint-1"
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
                tokens_seen=1024,
                examples_seen=2,
                loss_final=0.42,
                loss_best=0.33,
                learning_rate_final=1e-4,
                checkpoint_count=1,
                resume_ready=True,
                latest_checkpoint_path=str(latest_checkpoint_path),
                resume_source_path=str(request.resume_source_path or ""),
                tokens_per_second=96.0,
                peak_memory_gb=2.5,
            ),
            execution_backend="native",
        )

    def activate_native(self, request: ActivationRequest) -> ActivationResult:
        request.derived_model_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = request.derived_model_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps({"schema_version": "melix.derived_text_model.v1"}) + "\n",
            encoding="utf-8",
        )
        return ActivationResult(
            derived_model_dir=request.derived_model_dir,
            manifest_path=manifest_path,
            metrics=ActivationMetrics(job_duration_ms=321.0),
            execution_backend="native",
        )


class FastBenchmarkBackend:
    runtime_name = "fast-benchmark"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id, "model_path": model_spec.model_path}

    def estimate_resident_bytes(self, model_spec) -> int:
        return 1_024

    def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event):
        _ = loaded_model
        _ = sampling
        _ = prompt
        for chunk in ("fast ", "runtime ", "probe"):
            if cancel_event.is_set():
                return
            time.sleep(0.005)
            yield chunk


class EmptyThenTokenBenchmarkBackend:
    runtime_name = "empty-then-token"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id, "model_path": model_spec.model_path}

    def estimate_resident_bytes(self, model_spec) -> int:
        return 1_024

    def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event):
        _ = loaded_model
        _ = prompt
        _ = sampling
        if cancel_event.is_set():
            return
        yield RuntimeTokenEvent(text="")
        yield RuntimeTokenEvent(text="token", completion_tokens=1)


class RecordingBenchmarkBackend:
    runtime_name = "recording-benchmark"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id, "model_path": model_spec.model_path}

    def estimate_resident_bytes(self, model_spec) -> int:
        return 1_024

    def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event):
        _ = loaded_model
        _ = sampling
        self.prompts.append(prompt)
        if cancel_event.is_set():
            return
        yield RuntimeTokenEvent(
            text="token",
            completion_tokens=1,
            prompt_tokens=len(prompt.split()),
            prompt_tps=1.0,
            generation_tps=1.0,
            peak_memory=1_024.0,
        )


class ScriptedCodeEvalBackend:
    runtime_name = "scripted-code-eval"

    def __init__(self, responses: tuple[str, ...]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id, "model_path": model_spec.model_path}

    def estimate_resident_bytes(self, model_spec) -> int:
        _ = model_spec
        return 1_024

    def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event):
        _ = loaded_model
        _ = sampling
        self.prompts.append(prompt)
        if cancel_event.is_set():
            return
        text = self._responses.pop(0)
        yield RuntimeTokenEvent(text=text, completion_tokens=max(1, len(text.split())))


class FakeBenchmarkHFDatasetFetcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, endpoint: str, params: dict[str, str]) -> dict[str, object]:
        self.calls.append((endpoint, dict(params)))
        dataset = params.get("dataset", "")
        offset = params.get("offset", "0")
        if endpoint == "rows" and offset != "0":
            return {"rows": []}

        if dataset == "HuggingFaceH4/ultrachat_200k":
            if endpoint == "rows":
                return {
                    "rows": [
                        {
                            "row": {
                                "messages": [
                                    {"role": "user", "content": "Say hi."},
                                    {"role": "assistant", "content": "Hi."},
                                ]
                            }
                        },
                        {
                            "row": {
                                "messages": [
                                    {"role": "user", "content": "Say bye."},
                                    {"role": "assistant", "content": "Bye."},
                                ]
                            }
                        },
                    ]
                }
            return {"splits": [{"dataset": dataset, "config": "default", "split": "train_sft"}]}

        if dataset == "databricks/databricks-dolly-15k":
            if endpoint == "rows":
                return {
                    "rows": [
                        {"row": {"instruction": "List two colors.", "response": "Red and blue."}},
                        {"row": {"instruction": "List two animals.", "response": "Cat and dog."}},
                    ]
                }
            return {"splits": [{"dataset": dataset, "config": "default", "split": "train"}]}

        if dataset == "huggingface/documentation-images":
            if endpoint == "rows":
                return {
                    "rows": [
                        {"row": {"image": {"src": "https://example.com/doc-image-1.jpg"}}},
                        {"row": {"image": {"src": "https://example.com/doc-image-2.jpg"}}},
                    ]
                }
            return {"splits": [{"dataset": dataset, "config": "default", "split": "train"}]}

        raise AssertionError(f"Unexpected benchmark fetch: endpoint={endpoint} dataset={dataset}")


class FakeHubCatalog:
    def __init__(self) -> None:
        self.search_requests: list[dict[str, object]] = []
        self.card_requests: list[str] = []

    def search_models(
        self,
        *,
        query: str,
        page_size: int,
        cursor: str,
        mlx_only: bool,
    ) -> HubSearchPage:
        self.search_requests.append(
            {
                "query": query,
                "page_size": page_size,
                "cursor": cursor,
                "mlx_only": mlx_only,
            }
        )
        return HubSearchPage(
            items=[
                HubModelSummaryRecord(
                    repo_id="mlx-community/Qwen2.5-7B-Instruct-4bit",
                    author="mlx-community",
                    model_name="Qwen2.5-7B-Instruct-4bit",
                    summary="MLX text-generation build",
                    pipeline_tag="text-generation",
                    tags=["mlx", "chat"],
                    downloads=321,
                    likes=12,
                    mlx_compatible=True,
                    library_name="transformers",
                    sibling_files=["README.md", "config.json"],
                    last_modified="2025-01-26T19:49:28Z",
                ),
                HubModelSummaryRecord(
                    repo_id="openai/example-non-mlx",
                    author="openai",
                    model_name="example-non-mlx",
                    summary="Non-MLX text-generation build",
                    pipeline_tag="text-generation",
                    tags=["chat"],
                    downloads=123,
                    likes=4,
                    mlx_compatible=False,
                    library_name="transformers",
                    sibling_files=["README.md"],
                    last_modified="2025-01-25T08:00:00Z",
                ),
            ],
            next_cursor="cursor:page-2",
        )

    def get_model_card(self, *, repo_id: str) -> HubModelCardRecord:
        self.card_requests.append(repo_id)
        return HubModelCardRecord(
            repo_id=repo_id,
            author="mlx-community",
            model_name="Qwen2.5-7B-Instruct-4bit",
            summary="MLX text-generation build",
            license="apache-2.0",
            pipeline_tag="text-generation",
            tags=["mlx", "chat"],
            downloads=321,
            likes=12,
            mlx_compatible=True,
            library_name="transformers",
            sibling_files=["README.md", "config.json", "model.safetensors"],
            base_models=["Qwen/Qwen2.5-7B-Instruct"],
            last_modified="2025-01-26T19:49:28Z",
        )


class FailingHubCatalog:
    def __init__(
        self,
        *,
        search_error: Exception | None = None,
        card_error: Exception | None = None,
    ) -> None:
        self.search_error = search_error
        self.card_error = card_error

    def search_models(
        self,
        *,
        query: str,
        page_size: int,
        cursor: str,
        mlx_only: bool,
    ) -> HubSearchPage:
        raise self.search_error or AssertionError("search_error must be configured")

    def get_model_card(self, *, repo_id: str) -> HubModelCardRecord:
        raise self.card_error or AssertionError("card_error must be configured")


def _write_training_dataset_package(tmp_path: Path, *, dataset_id: str = "melix-dev") -> Path:
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": dataset_id,
                "format": "chat_messages",
                "sample_count": 2,
                "version": "1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (dataset_dir / "samples.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "messages": [
                            {"role": "user", "content": "Say hi."},
                            {"role": "assistant", "content": "Hi there."},
                        ]
                    }
                ),
                json.dumps(
                    {
                        "messages": [
                            {"role": "user", "content": "Say bye."},
                            {"role": "assistant", "content": "Bye."},
                        ]
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return dataset_dir


def _write_raw_training_jsonl(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    dataset_path = tmp_path / "raw-training.jsonl"
    dataset_path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    return dataset_path


def _write_download_source_file(tmp_path: Path, *, size: int = 4096) -> tuple[Path, bytes]:
    source_path = tmp_path / "download-source.bin"
    payload = bytes(index % 251 for index in range(size))
    source_path.write_bytes(payload)
    return source_path, payload


def _write_registry_manifest(
    variant_dir: Path,
    *,
    model_id: str,
    model_kind: str = "text",
    quant_profile_id: str = "q4",
    max_context: int = 8192,
    ext: dict[str, str] | None = None,
    manifest_fields: dict[str, object] | None = None,
) -> None:
    variant_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "schema_version": "melix.model_registry_manifest.v1",
        "model_id": model_id,
        "model_kind": model_kind,
        "quant_profile_id": quant_profile_id,
        "max_context": max_context,
        "ext": ext or {},
    }
    if manifest_fields:
        payload.update(manifest_fields)
    (variant_dir / "manifest.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")


class FakePublishBackend:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls: list[dict[str, object]] = []

    def publish(
        self,
        *,
        source_path: Path,
        target_repo: str,
        artifact_kind: str,
        token: str = "",
        private: bool = False,
        commit_message: str = "",
    ) -> PublishResult:
        if self.failure is not None:
            raise self.failure
        self.calls.append(
            {
                "source_path": source_path,
                "target_repo": target_repo,
                "artifact_kind": artifact_kind,
                "token": token,
                "private": private,
                "commit_message": commit_message,
            }
        )
        if source_path.is_dir():
            published_files = sorted(
                str(path.relative_to(source_path))
                for path in source_path.rglob("*")
                if path.is_file()
            )
        else:
            published_files = [source_path.name]
        return PublishResult(
            backend="huggingface_hub",
            target_repo=target_repo,
            target_url=f"https://huggingface.co/{target_repo}",
            remote_ref=f"{target_repo}@main",
            published_files=published_files,
        )


def build_service(
    tmp_path: Path,
    runner: MLXLMRunner | None = None,
    hub_catalog: FakeHubCatalog | None = None,
    registry: WorkerRegistry | None = None,
    benchmark_fetcher: FakeBenchmarkHFDatasetFetcher | None = None,
    publish_backend: FakePublishBackend | None = None,
) -> WorkerMaintenanceService:
    registry = registry or WorkerRegistry(
        runtime=MLXTextRuntime(backend=DeterministicTextBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    publish_backend = publish_backend or FakePublishBackend()
    service = WorkerMaintenanceService(
        registry,
        jobs_root=tmp_path / "model-ops",
        hub_catalog=hub_catalog,
        evaluation_hf_dataset_fetcher=benchmark_fetcher or FakeBenchmarkHFDatasetFetcher(),
    )
    service._core = MaintenanceCore(
        registry,
        jobs_root=tmp_path / "model-ops",
        hub_catalog=hub_catalog,
        lora_training_pipeline=LoRATrainingPipeline(runner=runner or DeterministicLoRARunner()),
        adapter_activation_pipeline=AdapterActivationPipeline(runner=runner or DeterministicLoRARunner()),
        upload_receipt_pipeline=UploadReceiptPipeline(publisher=publish_backend),
        benchmark_suite_catalog=BenchmarkSuiteCatalog(
            hf_dataset_fetcher=benchmark_fetcher or FakeBenchmarkHFDatasetFetcher()
        ),
    )
    service._fake_publish_backend = publish_backend
    return service


def imported_gemma4_text_backed_model() -> common_pb2.ModelSpec:
    return common_pb2.ModelSpec(
        model_id="unsloth/gemma-4-E4B-it-MLX-8bit",
        model_path="unsloth/gemma-4-E4B-it-MLX-8bit",
        model_kind="vlm",
        revision="main",
        tokenizer_hash="hf.unsloth.gemma-4-E4B-it-MLX-8bit",
        quant_profile_id="q8",
        parser_mode="text",
        reasoning_mode="off",
        max_context=4096,
        ext={
            "melix.vlm.backend_id": "mlx_vlm",
            "melix.vlm.execution_mode": "text_backed",
            "vision_family_id": "gemma4-v1",
            "vision_prompt_profile_id": "gemma4-chatml-v1",
            "vision_tokenization_mode": "interleaved",
            "vision_max_images_per_prompt": "8",
            "vision_supports_tool_calls": "true",
            "melix.multimodal_adapter_hash": "vision-family-gemma4-v1",
        },
    )


def test_convert_model_supports_convert_and_quantize_jobs(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    convert_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "convert"),
                generate_manifest=True,
            ),
            context=None,
        )
    )
    quantize_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "quantize"),
                weight_quant="q4",
                kv_quant="q8",
                generate_manifest=True,
                ext={"operation": "quantize"},
            ),
            context=None,
        )
    )

    assert convert_events[0].HasField("started")
    assert convert_events[-1].HasField("completed")
    convert_manifest = next(event.manifest for event in convert_events if event.HasField("manifest"))
    convert_payload = json.loads(convert_manifest.manifest_json)
    assert convert_payload["operation"] == "convert"
    assert convert_payload["schema_version"] == "melix.converted_model_bundle.v1"
    assert convert_payload["artifact_kind"] == "converted_model_bundle"
    assert convert_payload["target_format"] == "melix_model_bundle"
    assert convert_payload["compatibility"]["runtime"] == "mlx_text"
    assert convert_manifest.artifact.artifact_kind == "converted_model_bundle"
    assert convert_manifest.artifact.runtime == "mlx_text"
    assert convert_events[-1].completed.output_path.endswith("convert.artifact")
    assert convert_events[-1].completed.artifact.artifact_kind == "converted_model_bundle"

    assert quantize_events[0].HasField("started")
    assert quantize_events[-1].HasField("completed")
    quantize_manifest = next(event.manifest for event in quantize_events if event.HasField("manifest"))
    quantize_payload = json.loads(quantize_manifest.manifest_json)
    assert quantize_payload["operation"] == "quantize"
    assert quantize_payload["weight_quant"] == "q4"
    assert quantize_payload["kv_quant"] == "q8"


def test_convert_model_supports_download_and_upload_jobs(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    artifact_path = tmp_path / "artifact"
    artifact_path.write_text("melix-upload", encoding="utf-8")

    download_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix/demo-repo",
                output_dir=str(tmp_path / "download"),
                ext={"operation": "download"},
            ),
            context=None,
        )
    )
    upload_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model=str(artifact_path),
                output_dir=str(tmp_path / "upload"),
                generate_manifest=True,
                ext={"operation": "upload", "target_repo": "melix/upload-target"},
            ),
            context=None,
        )
    )

    assert download_events[-1].completed.output_path.endswith("download.artifact")
    assert upload_events[-1].completed.output_path.endswith("upload.receipt.json")
    upload_manifest = next(event.manifest for event in upload_events if event.HasField("manifest"))
    upload_payload = json.loads(upload_manifest.manifest_json)
    assert upload_payload["schema_version"] == "melix.upload_receipt.v1"
    assert upload_payload["artifact_kind"] == "upload_receipt"
    assert upload_payload["status"] == "published"
    assert upload_payload["target_repo"] == "melix/upload-target"
    assert upload_payload["source_artifact_kind"] == "model"
    assert upload_payload["upload_backend"] == "huggingface_hub"
    assert upload_payload["published_url"] == "https://huggingface.co/melix/upload-target"
    assert upload_manifest.artifact.artifact_kind == "upload_receipt"


def test_download_job_materializes_hub_repo_into_managed_root_and_registry_snapshot(tmp_path: Path) -> None:
    managed_root = tmp_path / "managed-models"
    source_dir = tmp_path / "hub-source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "config.json").write_text('{"model_type":"qwen3"}\n', encoding="utf-8")
    (source_dir / "tokenizer.json").write_text('{"version":"1.0"}\n', encoding="utf-8")
    (source_dir / "model.safetensors").write_bytes(b"weights")
    registry = WorkerRegistry(
        model_catalog=WorkerModelCatalog(
            environment={
                "MELIX_MANAGED_MODEL_ROOT": str(managed_root),
            }
        )
    )
    service = build_service(tmp_path, registry=registry)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                output_dir=str(tmp_path / "download-managed"),
                generate_manifest=True,
                ext={
                    "operation": "download",
                    "melix.source_kind": "hub_repo",
                    "melix.hf_repo_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    "melix.hf_revision": "main",
                    "melix.managed_import": "true",
                    "melix.managed_root": str(managed_root),
                    "source_path": str(source_dir),
                },
            ),
            context=None,
        )
    )

    manifest = json.loads((tmp_path / "download-managed" / "download.state.json").read_text(encoding="utf-8"))
    materialized_dir = managed_root / "huggingface" / "mlx-community" / "Qwen3.5-0.8B-OptiQ-4bit" / "main"
    registry_manifest = json.loads((materialized_dir / "manifest.json").read_text(encoding="utf-8"))

    assert events[-1].completed.output_path == str(materialized_dir)
    assert manifest["ext"]["melix.source_kind"] == "hub_repo"
    assert manifest["ext"]["melix.hf_repo_id"] == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
    assert manifest["ext"]["melix.hf_revision"] == "main"
    assert manifest["ext"]["melix.managed_import"] == "true"
    assert registry_manifest["model_id"] == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
    assert registry_manifest["provider_id"] == "huggingface"

    snapshot_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "snapshot-after-download"),
                generate_manifest=True,
                ext={"operation": "registry_snapshot"},
            ),
            context=None,
        )
    )
    snapshot_payload = json.loads(
        next(event.manifest for event in snapshot_events if event.HasField("manifest")).manifest_json
    )
    discovered_ids = [model["model_id"] for model in snapshot_payload["model_registry"]["models"]]

    assert "mlx-community/Qwen3.5-0.8B-OptiQ-4bit" in discovered_ids


def test_local_import_job_materializes_a_local_model_into_managed_root_and_registry_snapshot(tmp_path: Path) -> None:
    managed_root = tmp_path / "managed-models"
    source_dir = tmp_path / "local-source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "config.json").write_text('{"model_type":"qwen3"}\n', encoding="utf-8")
    (source_dir / "tokenizer.json").write_text('{"version":"1.0"}\n', encoding="utf-8")
    (source_dir / "model.safetensors").write_bytes(b"weights")
    registry = WorkerRegistry(
        model_catalog=WorkerModelCatalog(
            environment={
                "MELIX_MANAGED_MODEL_ROOT": str(managed_root),
            }
        )
    )
    service = build_service(tmp_path, registry=registry)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-qwen-local",
                output_dir=str(tmp_path / "import-managed"),
                generate_manifest=True,
                ext={
                    "operation": "local_import",
                    "source_path": str(source_dir),
                    "melix.managed_root": str(managed_root),
                    "melix.source_kind": "local_path",
                    "melix.model_kind": "text",
                    "melix.revision": "main",
                },
            ),
            context=None,
        )
    )

    materialized_dir = managed_root / "local" / "melix-dev-qwen-local" / "main"
    manifest = json.loads((materialized_dir / "manifest.json").read_text(encoding="utf-8"))

    assert events[-1].completed.output_path == str(materialized_dir)
    assert manifest["model_id"] == "melix-dev-qwen-local"
    assert manifest["provider_id"] == "local"
    assert manifest["ext"]["melix.source_kind"] == "local_path"
    assert manifest["ext"]["melix.source_locator"] == str(source_dir)

    snapshot_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "snapshot-after-import"),
                generate_manifest=True,
                ext={"operation": "registry_snapshot"},
            ),
            context=None,
        )
    )
    snapshot_payload = json.loads(
        next(event.manifest for event in snapshot_events if event.HasField("manifest")).manifest_json
    )
    discovered_ids = [model["model_id"] for model in snapshot_payload["model_registry"]["models"]]

    assert "melix-dev-qwen-local" in discovered_ids


def test_local_import_job_rejects_missing_source_directory(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-qwen-local",
                output_dir=str(tmp_path / "import-missing"),
                generate_manifest=True,
                ext={
                    "operation": "local_import",
                    "source_path": str(tmp_path / "missing-model"),
                    "melix.managed_root": str(tmp_path / "managed-models"),
                    "melix.source_kind": "local_path",
                    "melix.model_kind": "text",
                    "melix.revision": "main",
                },
            ),
            context=None,
        )
    )

    assert events[-1].HasField("failed")
    assert events[-1].failed.error.code == "invalid_argument"
    assert "existing source directory" in events[-1].failed.error.message


def test_download_job_resumes_from_partial_state_and_records_resume_metadata(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    source_path, source_bytes = _write_download_source_file(tmp_path, size=3072)
    output_dir = tmp_path / "download-resume"

    failed_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="mlx-community/demo-repo",
                output_dir=str(output_dir),
                generate_manifest=True,
                ext={
                    "operation": "download",
                    "source_path": str(source_path),
                    "mirror_url": "https://mirror.example/hf",
                    "max_retries": "0",
                    "test_failures_before_success": "1",
                    "test_fail_after_bytes": "1024",
                },
            ),
            context=None,
        )
    )
    failed_manifest = json.loads(
        [event.manifest.manifest_json for event in failed_events if event.HasField("manifest")][-1]
    )

    assert failed_events[-1].HasField("failed")
    assert failed_events[-1].failed.error.code == "download_retry_exhausted"
    assert failed_manifest["status"] == "failed"
    assert failed_manifest["downloaded_bytes"] == 1024
    assert failed_manifest["output_path"].endswith("download.artifact")
    assert failed_manifest["partial_path"].endswith("download.artifact.partial")
    assert failed_manifest["state_path"].endswith("download.state.json")

    resumed_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="mlx-community/demo-repo",
                output_dir=str(output_dir),
                generate_manifest=True,
                ext={
                    "operation": "download",
                    "source_path": str(source_path),
                    "mirror_url": "https://mirror.example/hf",
                },
            ),
            context=None,
        )
    )
    resumed_manifest = json.loads(
        [event.manifest.manifest_json for event in resumed_events if event.HasField("manifest")][-1]
    )

    assert resumed_events[-1].completed.output_path.endswith("download.artifact")
    assert Path(resumed_events[-1].completed.output_path).read_bytes() == source_bytes
    assert resumed_manifest["status"] == "completed"
    assert resumed_manifest["resume_used"] is True
    assert resumed_manifest["resume_from_bytes"] == 1024
    assert resumed_manifest["downloaded_bytes"] == len(source_bytes)
    assert resumed_manifest["total_bytes"] == len(source_bytes)
    assert resumed_manifest["selected_mirror"] == "https://mirror.example/hf"
    assert resumed_manifest["metrics"]["download.resume_success_rate"] == 1.0


def test_download_job_retries_before_success_and_records_retry_metrics(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    source_path, source_bytes = _write_download_source_file(tmp_path, size=2048)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="mlx-community/retry-demo",
                output_dir=str(tmp_path / "download-retry"),
                generate_manifest=True,
                ext={
                    "operation": "download",
                    "source_path": str(source_path),
                    "mirror_url": "https://mirror.example/retry",
                    "max_retries": "2",
                    "test_failures_before_success": "2",
                    "test_fail_after_bytes": "512",
                },
            ),
            context=None,
        )
    )
    manifest_payload = json.loads(
        [event.manifest.manifest_json for event in events if event.HasField("manifest")][-1]
    )

    assert events[-1].completed.output_path.endswith("download.artifact")
    assert Path(events[-1].completed.output_path).read_bytes() == source_bytes
    assert manifest_payload["status"] == "completed"
    assert manifest_payload["retry_count"] == 2
    assert manifest_payload["selected_mirror"] == "https://mirror.example/retry"
    assert manifest_payload["metrics"]["download.retry_count"] == 2
    assert manifest_payload["metrics"]["download.stall_detection_count"] == 0


def test_download_job_classifies_stall_failures_in_manifest_and_error(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    source_path, _ = _write_download_source_file(tmp_path, size=2048)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="mlx-community/stall-demo",
                output_dir=str(tmp_path / "download-stall"),
                generate_manifest=True,
                ext={
                    "operation": "download",
                    "source_path": str(source_path),
                    "stall_timeout_ms": "50",
                    "max_retries": "0",
                    "test_stall_after_bytes": "512",
                    "test_stall_elapsed_ms": "250",
                },
            ),
            context=None,
        )
    )
    manifest_payload = json.loads(
        [event.manifest.manifest_json for event in events if event.HasField("manifest")][-1]
    )

    assert events[-1].HasField("failed")
    assert events[-1].failed.error.code == "download_stalled"
    assert manifest_payload["status"] == "stalled"
    assert manifest_payload["terminal_state"] == "stalled"
    assert manifest_payload["stall_reason"] == "no_progress_timeout"
    assert manifest_payload["stall_detection_count"] == 1
    assert manifest_payload["metrics"]["download.stall_detection_count"] == 1


def test_upload_job_links_quantized_artifact_metadata(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    quantize_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "quantize"),
                weight_quant="q6",
                kv_quant="q8",
                generate_manifest=True,
                run_smoke_test=True,
                ext={"operation": "quantize", "quant_profile_id": "q6"},
            ),
            context=None,
        )
    )
    bundle_path = Path(quantize_events[-1].completed.output_path)

    upload_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "upload"),
                generate_manifest=True,
                ext={
                    "operation": "upload",
                    "artifact_kind": "model",
                    "artifact_path": str(bundle_path),
                    "target_repo": "melix/models/melix-dev-text-q6",
                },
            ),
            context=None,
        )
    )
    manifest = next(event.manifest for event in upload_events if event.HasField("manifest"))
    payload = json.loads(manifest.manifest_json)

    assert upload_events[-1].completed.output_path.endswith("upload.receipt.json")
    assert manifest.artifact.artifact_kind == "upload_receipt"
    assert manifest.artifact.runtime == "mlx_text"
    assert payload["operation"] == "upload"
    assert payload["artifact_path"] == str(bundle_path)
    assert payload["artifact_kind"] == "upload_receipt"
    assert payload["target_repo"] == "melix/models/melix-dev-text-q6"
    assert payload["source_artifact_kind"] == "quantized_model_bundle"
    assert payload["linked_quantization"]["artifact_kind"] == "quantized_model_bundle"
    assert payload["linked_quantization"]["artifact_path"] == str(bundle_path)
    assert payload["linked_quantization"]["quant_profile_id"] == "q6"
    assert payload["linked_quantization"]["calibration_sample_count"] == 32
    assert payload["linked_quantization"]["smoke_test_passed"] is True


def test_upload_job_links_converted_bundle_metadata(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    convert_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "convert"),
                generate_manifest=True,
                run_smoke_test=True,
            ),
            context=None,
        )
    )
    bundle_path = Path(convert_events[-1].completed.output_path)

    upload_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "upload-convert"),
                generate_manifest=True,
                ext={
                    "operation": "upload",
                    "artifact_kind": "model",
                    "artifact_path": str(bundle_path),
                    "target_repo": "melix/models/melix-dev-text-converted",
                },
            ),
            context=None,
        )
    )
    manifest = next(event.manifest for event in upload_events if event.HasField("manifest"))
    payload = json.loads(manifest.manifest_json)

    assert upload_events[-1].completed.output_path.endswith("upload.receipt.json")
    assert payload["source_artifact_kind"] == "converted_model_bundle"
    assert payload["target_format"] == "melix_model_bundle"
    assert payload["conversion_backend"] == "melix_structural_packager"


def test_upload_job_fails_for_invalid_artifact_manifest(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    bundle_path = tmp_path / "broken-artifact"
    bundle_path.mkdir(parents=True)
    (bundle_path / "manifest.json").write_text("{not-json", encoding="utf-8")

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "upload-broken"),
                generate_manifest=True,
                ext={
                    "operation": "upload",
                    "artifact_kind": "model",
                    "artifact_path": str(bundle_path),
                    "target_repo": "melix/models/broken",
                },
            ),
            context=None,
        )
    )

    assert events[-1].HasField("failed")
    assert events[-1].failed.error.code == "invalid_artifact"
    assert "not valid JSON" in events[-1].failed.error.message


def test_hugging_face_publish_backend_adds_private_token_and_commit_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_root = tmp_path / "publish"
    artifact_root.mkdir(parents=True)
    (artifact_root / "adapter.safetensors").write_text("weights", encoding="utf-8")
    (artifact_root / "config.json").write_text("{}", encoding="utf-8")
    seen: dict[str, object] = {}

    def fake_subprocess_run(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=0,
            stdout="\nhttps://huggingface.co/melix/demo-adapter/commit/abc123\n",
            stderr="",
        )

    monkeypatch.setattr("worker.model_ops.upload_receipt_pipeline.subprocess.run", fake_subprocess_run)

    result = HuggingFacePublishBackend().publish(
        source_path=artifact_root,
        target_repo="melix/demo-adapter",
        artifact_kind="adapter",
        token="hf-token",
        private=True,
        commit_message="Publish adapter",
    )

    assert seen["command"] == [
        "hf",
        "upload",
        "melix/demo-adapter",
        str(artifact_root.resolve()),
        ".",
        "--repo-type",
        "model",
        "--quiet",
        "--private",
        "--commit-message",
        "Publish adapter",
        "--token",
        "hf-token",
    ]
    assert result.remote_ref == "https://huggingface.co/melix/demo-adapter/commit/abc123"
    assert result.published_files == ["adapter.safetensors", "config.json"]


def test_hugging_face_publish_backend_falls_back_to_legacy_cli_when_hf_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_root = tmp_path / "publish"
    artifact_root.mkdir(parents=True)
    (artifact_root / "adapter.safetensors").write_text("weights", encoding="utf-8")
    seen: dict[str, object] = {}

    def fake_which(command: str) -> str | None:
        if command == "hf":
            return None
        if command == "huggingface-cli":
            return "/usr/local/bin/huggingface-cli"
        return None

    def fake_subprocess_run(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=0,
            stdout="\nhttps://huggingface.co/melix/demo-adapter/commit/abc123\n",
            stderr="",
        )

    monkeypatch.setattr("worker.model_ops.upload_receipt_pipeline.shutil.which", fake_which)
    monkeypatch.setattr("worker.model_ops.upload_receipt_pipeline.subprocess.run", fake_subprocess_run)

    HuggingFacePublishBackend().publish(
        source_path=artifact_root,
        target_repo="melix/demo-adapter",
        artifact_kind="adapter",
    )

    assert seen["command"][0] == "huggingface-cli"


def test_resolve_hf_cli_command_defaults_to_hf_when_no_binary_is_discovered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("worker.model_ops.upload_receipt_pipeline.shutil.which", lambda command: None)

    assert _resolve_hf_cli_command() == "hf"


def test_upload_receipt_pipeline_requires_target_repo_and_valid_adapter_bundle(tmp_path: Path) -> None:
    pipeline = UploadReceiptPipeline(publisher=FakePublishBackend())

    with pytest.raises(ModelOperationError) as missing_target_repo:
        pipeline.run(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                ext={"operation": "upload"},
            ),
            job_id="upload-1",
            output_dir=tmp_path / "upload",
        )
    assert missing_target_repo.value.code == "invalid_argument"

    missing_descriptor = SourceArtifactDescriptor(
        artifact_path=str(tmp_path / "missing-artifact"),
        artifact_kind="model",
        schema_version="",
        manifest_path="",
        source_model="melix-dev-text",
        manifest_payload=None,
    )
    with pytest.raises(ModelOperationError) as missing_artifact:
        pipeline._prepare_publish_source(
            missing_descriptor,
            receipt_dir=tmp_path / "receipt",
            target_repo="melix/demo-model",
            export_artifact_kind="model_export",
        )
    assert missing_artifact.value.code == "invalid_artifact"

    adapter_manifest = tmp_path / "train_lora.adapter.json"
    adapter_manifest.write_text(
        json.dumps(
            {
                "artifact_kind": "adapter",
                "source_model": "melix-dev-text",
                "weights_path": str(tmp_path / "missing-weights.safetensors"),
                "adapter_config_path": str(tmp_path / "missing-adapter-config.json"),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    descriptor = SourceArtifactDescriptor(
        artifact_path=str(adapter_manifest),
        artifact_kind="adapter",
        schema_version="melix.lora_adapter_package.v1",
        manifest_path=str(adapter_manifest),
        source_model="melix-dev-text",
        manifest_payload=json.loads(adapter_manifest.read_text(encoding="utf-8")),
    )

    with pytest.raises(ModelOperationError) as invalid_adapter:
        pipeline._prepare_publish_source(
            descriptor,
            receipt_dir=tmp_path / "receipt",
            target_repo="melix/demo-adapter",
            export_artifact_kind="adapter_export",
        )
    assert invalid_adapter.value.code == "invalid_artifact"

    monkeypatch_env = {"HUGGINGFACE_HUB_TOKEN": "env-token"}
    for key, value in monkeypatch_env.items():
        os.environ[key] = value
    try:
        assert UploadReceiptPipeline._resolve_hf_token({}) == "env-token"
        assert UploadReceiptPipeline._resolve_hf_token({"HF_TOKEN": "ext-token"}) == "ext-token"
    finally:
        for key in monkeypatch_env:
            os.environ.pop(key, None)


def test_quantize_job_fails_when_active_requests_hold_the_same_model(tmp_path: Path) -> None:
    registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
    registry.start_request("req-active", runtime_kind="text")
    service = WorkerMaintenanceService(registry, jobs_root=tmp_path / "model-ops")

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "quantize"),
                weight_quant="q4",
                kv_quant="q8",
                ext={"operation": "quantize"},
            ),
            context=None,
        )
    )

    assert events[-1].HasField("failed")
    assert events[-1].failed.error.code == "resource_locked"
    assert "active inference" in events[-1].failed.error.message


def test_quantize_job_conflict_lock_blocks_parallel_quantization_on_same_scope(tmp_path: Path) -> None:
    registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
    service = WorkerMaintenanceService(registry, jobs_root=tmp_path / "model-ops")
    started = threading.Event()
    first_events: list[maintenance_pb2.ConvertModelEvent] = []

    def run_first_job() -> None:
        nonlocal first_events
        first_events = list(
            service.ConvertModel(
                maintenance_pb2.ConvertModelRequest(
                    source_model="melix-dev-text",
                    output_dir=str(tmp_path / "quantize-a"),
                    weight_quant="q4",
                    kv_quant="q8",
                    generate_manifest=True,
                    ext={
                        "operation": "quantize",
                        "test_hold_ms": "150",
                    },
                ),
                context=None,
            )
        )
        started.set()

    worker = threading.Thread(target=run_first_job)
    worker.start()
    time.sleep(0.03)

    second_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "quantize-b"),
                weight_quant="q4",
                kv_quant="q8",
                ext={"operation": "quantize"},
            ),
            context=None,
        )
    )
    worker.join()

    assert first_events[-1].HasField("completed")
    assert second_events[-1].HasField("failed")
    assert second_events[-1].failed.error.code == "resource_locked"
    assert "quantization lock" in second_events[-1].failed.error.message


def test_quantize_job_conflict_lock_blocks_upload_on_same_linked_quantization_scope(
    tmp_path: Path,
) -> None:
    registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
    service = WorkerMaintenanceService(registry, jobs_root=tmp_path / "model-ops")

    completed_quantize = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "quantize-ready"),
                weight_quant="q4",
                kv_quant="q8",
                generate_manifest=True,
                run_smoke_test=True,
                ext={"operation": "quantize"},
            ),
            context=None,
        )
    )
    bundle_path = Path(completed_quantize[-1].completed.output_path)

    first_events: list[maintenance_pb2.ConvertModelEvent] = []

    def run_held_quantize() -> None:
        nonlocal first_events
        first_events = list(
            service.ConvertModel(
                maintenance_pb2.ConvertModelRequest(
                    source_model="melix-dev-text",
                    output_dir=str(tmp_path / "quantize-held"),
                    weight_quant="q4",
                    kv_quant="q8",
                    ext={"operation": "quantize", "test_hold_ms": "150"},
                ),
                context=None,
            )
        )

    worker = threading.Thread(target=run_held_quantize)
    worker.start()
    time.sleep(0.03)

    upload_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "upload"),
                generate_manifest=True,
                ext={
                    "operation": "upload",
                    "artifact_kind": "model",
                    "artifact_path": str(bundle_path),
                    "target_repo": "melix/models/melix-dev-text-q4",
                },
            ),
            context=None,
        )
    )
    worker.join()

    assert first_events[-1].HasField("completed")
    assert upload_events[-1].HasField("failed")
    assert upload_events[-1].failed.error.code == "resource_locked"
    assert "quantization lock" in upload_events[-1].failed.error.message


def test_lock_scope_falls_back_to_linked_quantization_source_model_when_scope_is_missing(
    tmp_path: Path,
) -> None:
    registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
    core = MaintenanceCore(registry, jobs_root=tmp_path / "model-ops")

    artifact_dir = tmp_path / "quantized-artifact"
    artifact_dir.mkdir()
    (artifact_dir / "manifest.json").write_text(
        json.dumps(
            {
                "artifact_kind": "quantized_model_bundle",
                "source_model": "melix-dev-text",
                "quant_profile": {"quant_profile_id": "q4"},
                "calibration": {"sample_count": 64},
                "compatibility": {"smoke_test_passed": True},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    request = maintenance_pb2.ConvertModelRequest(
        source_model="melix-dev-text",
        ext={
            "operation": "upload",
            "artifact_kind": "model",
            "artifact_path": str(artifact_dir),
        },
    )

    assert core._lock_scope("upload", request) == "model-family:melix-dev-text"


def test_linked_quantization_metadata_rejects_missing_invalid_and_non_bundle_manifests(tmp_path: Path) -> None:
    empty_request = maintenance_pb2.ConvertModelRequest()
    assert MaintenanceCore._linked_quantization_metadata(empty_request) is None

    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    manifest_path = artifact_dir / "manifest.json"

    invalid_request = maintenance_pb2.ConvertModelRequest()
    invalid_request.source_model = "melix-dev-text"
    invalid_request.ext["artifact_path"] = str(artifact_dir)
    manifest_path.write_text("{not-json", encoding="utf-8")
    assert MaintenanceCore._linked_quantization_metadata(invalid_request) is None

    non_dict_request = maintenance_pb2.ConvertModelRequest()
    non_dict_request.source_model = "melix-dev-text"
    non_dict_request.ext["artifact_path"] = str(artifact_dir)
    manifest_path.write_text("[]", encoding="utf-8")
    assert MaintenanceCore._linked_quantization_metadata(non_dict_request) is None

    wrong_kind_request = maintenance_pb2.ConvertModelRequest()
    wrong_kind_request.source_model = "melix-dev-text"
    wrong_kind_request.ext["artifact_path"] = str(artifact_dir)
    manifest_path.write_text(json.dumps({"artifact_kind": "plain_model"}) + "\n", encoding="utf-8")
    assert MaintenanceCore._linked_quantization_metadata(wrong_kind_request) is None


def test_convert_model_supports_train_lora_jobs(tmp_path: Path) -> None:
    dataset_dir = _write_training_dataset_package(tmp_path)
    service = build_service(tmp_path, runner=DeterministicLoRARunner())

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

    manifest = next(event.manifest for event in events if event.HasField("manifest"))
    payload = json.loads(manifest.manifest_json)

    assert events[0].started.job_id == "model-ops-0001"
    assert events[-1].completed.output_path == str(
        tmp_path / "model-ops" / "train_lora" / "model-ops-0001" / "train_lora.adapter.json"
    )
    assert payload["schema_version"] == "melix.lora_adapter_package.v1"
    assert payload["operation"] == "train_lora"
    assert payload["adapter_name"] == "melix-dev-adapter"
    assert payload["dataset_uri"] == str(dataset_dir)
    assert payload["dataset_source_kind"] == "local_package"
    assert payload["training_duration_ms"] == 1234.0
    assert payload["adapter_artifact_bytes"] > 0


def test_convert_model_supports_build_training_dataset_jobs(tmp_path: Path) -> None:
    dataset_path = _write_raw_training_jsonl(
        tmp_path,
        [
            {
                "instruction": "Translate to French.",
                "input": "Hello world",
                "output": "Bonjour le monde",
            },
            {
                "instruction": "Translate to French.",
                "input": "Hello world",
                "output": "Bonjour le monde",
            },
            {
                "instruction": "Repeat the token.",
                "input": "",
                "output": "token\u0000token",
            },
        ],
    )
    service = build_service(tmp_path, runner=DeterministicLoRARunner())

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "dataset-build"),
                generate_manifest=True,
                ext={
                    "operation": "build_training_dataset",
                    "dataset_uri": str(dataset_path),
                    "template": "alpaca",
                    "dataset_id": "melix-built-dataset",
                    "validation_ratio": "0.34",
                },
            ),
            context=None,
        )
    )

    manifest = next(event.manifest for event in events if event.HasField("manifest"))
    payload = json.loads(manifest.manifest_json)

    assert events[0].started.job_id == "model-ops-0001"
    assert events[-1].completed.output_path == str(tmp_path / "dataset-build")
    assert payload["schema_version"] == "melix.training_dataset_package.v1"
    assert payload["dataset_id"] == "melix-built-dataset"
    assert payload["format"] == "prompt_completion"
    assert payload["sample_count"] == 2
    assert payload["validation_sample_count"] == 1
    assert payload["quality"]["duplicate_count"] == 1
    assert payload["quality"]["dirty_count"] == 1
    assert (tmp_path / "dataset-build" / "manifest.json").is_file()
    assert (tmp_path / "dataset-build" / "samples.jsonl").is_file()
    assert (tmp_path / "dataset-build" / "valid.jsonl").is_file()


def test_build_training_dataset_job_requires_known_source_model(tmp_path: Path) -> None:
    service = build_service(tmp_path, runner=DeterministicLoRARunner())

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-missing",
                output_dir=str(tmp_path / "dataset-build"),
                generate_manifest=True,
                ext={
                    "operation": "build_training_dataset",
                },
            ),
            context=None,
        )
    )

    assert events[-1].HasField("failed")
    assert events[-1].failed.error.code == "unsupported_model_family"
    assert "Unknown source model" in events[-1].failed.error.message


def test_convert_model_supports_inspect_only_dataset_jobs(tmp_path: Path) -> None:
    dataset_path = _write_raw_training_jsonl(
        tmp_path,
        [
            {
                "conversations": [
                    {"from": "human", "value": "Say hi."},
                    {"from": "gpt", "value": "Hi there."},
                ]
            },
            {
                "conversations": [
                    {"from": "human", "value": "Say bye."},
                    {"from": "gpt", "value": "Bye."},
                ]
            },
        ],
    )
    service = build_service(tmp_path, runner=DeterministicLoRARunner())

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "dataset-inspect"),
                generate_manifest=True,
                ext={
                    "operation": "build_training_dataset",
                    "dataset_uri": str(dataset_path),
                    "inspect_only": "true",
                },
            ),
            context=None,
        )
    )

    manifest = next(event.manifest for event in events if event.HasField("manifest"))
    payload = json.loads(manifest.manifest_json)

    assert events[-1].completed.output_path == str(
        tmp_path / "dataset-inspect" / "training_dataset.inspect.json"
    )
    assert payload["schema_version"] == "melix.training_dataset_inspection.v1"
    assert payload["format"] == "chat_messages"
    assert payload["conversion_template"] == "sharegpt"
    assert (tmp_path / "dataset-inspect" / "training_dataset.inspect.json").is_file()
    assert (tmp_path / "dataset-inspect" / "samples.jsonl").exists() is False


def test_registry_snapshot_returns_training_history_and_adapter_registry(tmp_path: Path) -> None:
    dataset_dir = _write_training_dataset_package(tmp_path)
    service = build_service(tmp_path, runner=DeterministicLoRARunner())
    train_dir = tmp_path / "train"
    train_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(train_dir),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-dev-adapter",
                    "dataset_uri": str(dataset_dir),
                    "target_repo": "melix/adapters/melix-dev-adapter",
                },
            ),
            context=None,
        )
    )
    adapter_path = train_events[-1].completed.output_path

    list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "upload"),
                generate_manifest=True,
                ext={
                    "operation": "upload",
                    "artifact_kind": "adapter",
                    "artifact_path": adapter_path,
                    "adapter_name": "melix-dev-adapter",
                    "target_repo": "melix/adapters/melix-dev-adapter",
                },
            ),
            context=None,
        )
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
    snapshot_manifest = next(
        event.manifest for event in snapshot_events if event.HasField("manifest")
    )
    payload = json.loads(snapshot_manifest.manifest_json)

    assert payload["operation"] == "registry_snapshot"
    assert len(payload["jobs"]) == 2
    assert payload["jobs"][0]["operation"] == "upload"
    assert payload["jobs"][1]["operation"] == "train_lora"
    assert payload["adapters"][0]["adapter_name"] == "melix-dev-adapter"
    assert payload["adapters"][0]["published_repo"] == "melix/adapters/melix-dev-adapter"
    assert payload["adapters"][0]["status"] == "published"
    assert payload["adapters"][0]["dataset_source_kind"] == "local_package"
    assert payload["adapters"][0]["dataset_id"] == "melix-dev"
    assert payload["adapters"][0]["normalized_dataset_manifest_path"].endswith("normalized_dataset/manifest.json")


def test_upload_job_publishes_adapter_bundle_to_hugging_face(tmp_path: Path) -> None:
    dataset_dir = _write_training_dataset_package(tmp_path)
    publish_backend = FakePublishBackend()
    service = build_service(tmp_path, publish_backend=publish_backend)

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
                    "target_repo": "melix/adapters/melix-dev-adapter",
                },
            ),
            context=None,
        )
    )
    adapter_manifest_path = train_events[-1].completed.output_path

    upload_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "upload-adapter"),
                generate_manifest=True,
                ext={
                    "operation": "upload",
                    "artifact_kind": "adapter_export",
                    "artifact_path": adapter_manifest_path,
                    "adapter_name": "melix-dev-adapter",
                    "target_repo": "melix/adapters/melix-dev-adapter",
                },
            ),
            context=None,
        )
    )

    payload = json.loads(
        next(event.manifest for event in upload_events if event.HasField("manifest")).manifest_json
    )

    assert upload_events[-1].completed.output_path.endswith("upload.receipt.json")
    assert payload["status"] == "published"
    assert payload["upload_backend"] == "huggingface_hub"
    assert payload["export_artifact_kind"] == "adapter_export"
    assert payload["distribution_contract"] == "adapter_only"
    assert payload["published_repo"] == "melix/adapters/melix-dev-adapter"
    assert payload["published_url"] == "https://huggingface.co/melix/adapters/melix-dev-adapter"
    assert payload["parent_lineage"]["source_artifact_kind"] == "adapter"
    assert payload["parent_lineage"]["source_job_id"].startswith("model-ops-")
    assert sorted(payload["published_files"]) == sorted(
        [
            "adapter/adapters.safetensors",
            "adapter/adapter_config.json",
            "train_lora.adapter.json",
        ]
    )
    assert publish_backend.calls[-1]["artifact_kind"] == "adapter_export"
    staged_source = publish_backend.calls[-1]["source_path"]
    assert isinstance(staged_source, Path)
    staged_manifest = json.loads((staged_source / "train_lora.adapter.json").read_text(encoding="utf-8"))
    assert staged_manifest["weights_path"] == "adapter/adapters.safetensors"
    assert staged_manifest["adapter_config_path"] == "adapter/adapter_config.json"
    assert staged_manifest["published_repo"] == "melix/adapters/melix-dev-adapter"


def test_upload_job_publishes_fused_derived_model_as_merged_export(tmp_path: Path) -> None:
    dataset_dir = _write_training_dataset_package(tmp_path)
    publish_backend = FakePublishBackend()
    service = build_service(tmp_path, publish_backend=publish_backend)

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
                    "derived_model_alias": "melix-dev-fused",
                },
            ),
            context=None,
        )
    )
    activation_manifest_path = activate_events[-1].completed.output_path

    upload_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "upload-merged"),
                generate_manifest=True,
                ext={
                    "operation": "upload",
                    "artifact_kind": "merged_export",
                    "artifact_path": activation_manifest_path,
                    "artifact_manifest_path": activation_manifest_path,
                    "target_repo": "melix/models/melix-dev-fused",
                },
            ),
            context=None,
        )
    )

    payload = json.loads(
        next(event.manifest for event in upload_events if event.HasField("manifest")).manifest_json
    )
    published_source = publish_backend.calls[-1]["source_path"]

    assert payload["export_artifact_kind"] == "merged_export"
    assert payload["distribution_contract"] == "merged_model"
    assert payload["activation_mode"] == "fused_derived_model"
    assert payload["derived_model_id"].startswith("melix-dev-text-lora-")
    assert payload["parent_lineage"]["activation_mode"] == "fused_derived_model"
    assert payload["parent_lineage"]["derived_model_id"] == payload["derived_model_id"]
    assert publish_backend.calls[-1]["artifact_kind"] == "merged_export"
    assert isinstance(published_source, Path)
    assert published_source.name == payload["derived_model_id"]
    assert payload["published_files"]


def test_registry_snapshot_includes_discovered_model_registry_payload(tmp_path: Path) -> None:
    registry_root = tmp_path / "registry-root"
    _write_registry_manifest(
        registry_root / "mlx-community" / "Qwen2.5-7B-Instruct" / "4bit",
        model_id="mlx-community/Qwen2.5-7B-Instruct/4bit",
        max_context=16384,
        ext={"source_root": "registry-root"},
    )

    registry = WorkerRegistry(
        model_catalog=WorkerModelCatalog(
            environment={
                "MELIX_MODEL_ROOTS": str(registry_root),
            }
        )
    )
    service = WorkerMaintenanceService(registry, jobs_root=tmp_path / "model-ops")

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
    snapshot_manifest = next(
        event.manifest for event in snapshot_events if event.HasField("manifest")
    )
    payload = json.loads(snapshot_manifest.manifest_json)
    expected_root_id = f"root-{hashlib.sha1(os.fspath(registry_root.resolve()).encode('utf-8')).hexdigest()[:12]}"

    assert payload["operation"] == "registry_snapshot"
    assert payload["model_registry"]["roots"][0]["root_id"] == expected_root_id
    assert payload["model_registry"]["roots"][0]["root_order"] == 1
    assert payload["model_registry"]["roots"][0]["accessible"] is True
    discovered_ids = [model["model_id"] for model in payload["model_registry"]["models"]]
    assert discovered_ids == ["mlx-community/Qwen2.5-7B-Instruct/4bit"]
    assert payload["model_registry"]["models"][0]["ext"]["melix.registry_root_id"] == expected_root_id
    assert payload["model_registry"]["models"][0]["ext"]["melix.registry_root_order"] == "1"


def test_registry_snapshot_includes_structured_identity_fields_for_discovered_models(tmp_path: Path) -> None:
    registry_root = tmp_path / "registry-root"
    _write_registry_manifest(
        registry_root / "huggingface" / "mlx-community" / "Qwen2.5-7B-Instruct" / "4bit",
        model_id="mlx-community/Qwen2.5-7B-Instruct/4bit",
        manifest_fields={
            "provider_id": "hf-mirror",
            "variant_id": "q4f16",
        },
    )

    registry = WorkerRegistry(
        model_catalog=WorkerModelCatalog(
            environment={
                "MELIX_MODEL_ROOTS": str(registry_root),
            }
        )
    )
    service = WorkerMaintenanceService(registry, jobs_root=tmp_path / "model-ops")

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
    snapshot_manifest = next(
        event.manifest for event in snapshot_events if event.HasField("manifest")
    )
    payload = json.loads(snapshot_manifest.manifest_json)
    identity = payload["model_registry"]["models"][0]["ext"]

    assert identity["melix.registry_provider_id"] == "hf-mirror"
    assert identity["melix.registry_organization_id"] == "mlx-community"
    assert identity["melix.registry_model_name"] == "Qwen2.5-7B-Instruct"
    assert identity["melix.registry_variant_id"] == "q4f16"
    assert identity["melix.registry_relative_path"] == "huggingface/mlx-community/Qwen2.5-7B-Instruct/4bit"


def test_registry_snapshot_respects_explicit_root_override_and_rescan_flag(tmp_path: Path) -> None:
    root_a = tmp_path / "root-a"
    root_b = tmp_path / "root-b"
    duplicate_id = "mlx-community/Qwen2.5-7B-Instruct/4bit"
    _write_registry_manifest(
        root_a / "mlx-community" / "Qwen2.5-7B-Instruct" / "4bit",
        model_id=duplicate_id,
        ext={"source_root": "a"},
    )
    _write_registry_manifest(
        root_b / "mlx-community" / "Qwen2.5-7B-Instruct" / "4bit",
        model_id=duplicate_id,
        ext={"source_root": "b"},
    )

    registry = WorkerRegistry(model_catalog=WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root_a)}))
    service = WorkerMaintenanceService(registry, jobs_root=tmp_path / "model-ops")

    override_json = json.dumps([os.fspath(root_b), os.fspath(root_a)])
    snapshot_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "snapshot"),
                generate_manifest=True,
                ext={
                    "operation": "registry_snapshot",
                    "melix.registry_roots_json": override_json,
                    "melix.registry_rescan": "true",
                },
            ),
            context=None,
        )
    )
    snapshot_manifest = next(
        event.manifest for event in snapshot_events if event.HasField("manifest")
    )
    payload = json.loads(snapshot_manifest.manifest_json)
    expected_b_root_id = f"root-{hashlib.sha1(os.fspath(root_b.resolve()).encode('utf-8')).hexdigest()[:12]}"
    expected_a_root_id = f"root-{hashlib.sha1(os.fspath(root_a.resolve()).encode('utf-8')).hexdigest()[:12]}"

    assert [root["root_id"] for root in payload["model_registry"]["roots"]] == [expected_b_root_id, expected_a_root_id]
    assert payload["model_registry"]["models"][0]["ext"]["source_root"] == "b"
    assert payload["model_registry"]["models"][0]["ext"]["melix.registry_root_id"] == expected_b_root_id
    assert payload["model_registry"]["models"][0]["ext"]["melix.registry_root_order"] == "1"


def test_registry_snapshot_does_not_embed_prior_registry_snapshot_manifests(tmp_path: Path) -> None:
    registry_root = tmp_path / "registry-root"
    _write_registry_manifest(
        registry_root / "mlx-community" / "Qwen2.5-7B-Instruct" / "4bit",
        model_id="mlx-community/Qwen2.5-7B-Instruct/4bit",
        ext={"source_root": "registry-root"},
    )

    registry = WorkerRegistry(
        model_catalog=WorkerModelCatalog(
            environment={
                "MELIX_MODEL_ROOTS": str(registry_root),
            }
        )
    )
    service = WorkerMaintenanceService(registry, jobs_root=tmp_path / "model-ops")

    first_snapshot_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "snapshot-a"),
                generate_manifest=True,
                ext={"operation": "registry_snapshot"},
            ),
            context=None,
        )
    )
    first_snapshot_manifest = next(
        event.manifest for event in first_snapshot_events if event.HasField("manifest")
    )
    first_payload = json.loads(first_snapshot_manifest.manifest_json)
    assert first_payload["model_registry"]["models"][0]["model_id"] == "mlx-community/Qwen2.5-7B-Instruct/4bit"

    second_snapshot_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "snapshot-b"),
                generate_manifest=True,
                ext={"operation": "registry_snapshot"},
            ),
            context=None,
        )
    )
    second_snapshot_manifest = next(
        event.manifest for event in second_snapshot_events if event.HasField("manifest")
    )
    second_payload = json.loads(second_snapshot_manifest.manifest_json)

    assert second_payload["model_registry"]["models"][0]["model_id"] == "mlx-community/Qwen2.5-7B-Instruct/4bit"
    prior_snapshot_job = next(job for job in second_payload["jobs"] if job["operation"] == "registry_snapshot")
    assert prior_snapshot_job["manifest"] == {}


def test_job_registry_snapshot_handles_invalid_manifests_and_non_numeric_ids() -> None:
    registry = ModelOpsJobRegistry()

    completed = registry.start("train_lora", "melix-dev-text", "/tmp/train")
    registry.progress(completed.job_id, "write_manifest", 0.35)
    registry.attach_manifest(completed.job_id, "{not-json")
    registry.complete(completed.job_id, "/tmp/train/train_lora.adapter.json")

    failed = registry.start("upload", "melix-dev-text", "/tmp/upload")
    registry.progress(failed.job_id, "push", 0.8)
    registry.fail(failed.job_id, "hf_upload_failed", "upload failed")

    registry._jobs["custom-job"] = ModelOpsJob(
        job_id="custom-job",
        operation="convert",
        source_model="melix-dev-text",
        output_dir="/tmp/custom",
        manifest_json="[]",
    )

    payload = registry.snapshot()

    assert [job["job_id"] for job in payload["jobs"]] == [failed.job_id, completed.job_id, "custom-job"]

    completed_job = next(job for job in payload["jobs"] if job["job_id"] == completed.job_id)
    failed_job = next(job for job in payload["jobs"] if job["job_id"] == failed.job_id)
    custom_job = next(job for job in payload["jobs"] if job["job_id"] == "custom-job")

    assert completed_job["manifest"] == {}
    assert completed_job["stage_history"] == [{"stage": "write_manifest", "pct": 0.35}]
    assert failed_job["error_code"] == "hf_upload_failed"
    assert failed_job["error_message"] == "upload failed"
    assert custom_job["stage"] == "queued"
    assert custom_job["pct"] == 0.0
    assert custom_job["manifest"] == {}
    assert payload["adapters"][0]["status"] == "completed"


def test_job_registry_snapshot_exposes_download_rows_with_machine_readable_status(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    source_path, source_bytes = _write_download_source_file(tmp_path, size=1024)
    output_dir = tmp_path / "download-snapshot"

    list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="mlx-community/snapshot-demo",
                output_dir=str(output_dir),
                generate_manifest=True,
                ext={
                    "operation": "download",
                    "source_path": str(source_path),
                    "mirror_url": "https://mirror.example/snapshot",
                },
            ),
            context=None,
        )
    )

    snapshot = service._core._job_registry.snapshot()
    download = snapshot["downloads"][0]

    assert download["source_model"] == "mlx-community/snapshot-demo"
    assert download["status"] == "completed"
    assert download["output_dir"] == str(output_dir)
    assert download["selected_mirror"] == "https://mirror.example/snapshot"
    assert download["downloaded_bytes"] == len(source_bytes)
    assert download["total_bytes"] == len(source_bytes)
    assert download["output_path"].endswith("download.artifact")
    assert download["state_path"].endswith("download.state.json")
    assert download["resume_ready"] is False


def test_job_registry_snapshot_marks_partial_downloads_as_resume_ready(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    source_path, _ = _write_download_source_file(tmp_path, size=2048)
    output_dir = tmp_path / "download-resume-ready"

    list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="mlx-community/resume-ready-demo",
                output_dir=str(output_dir),
                generate_manifest=True,
                ext={
                    "operation": "download",
                    "source_path": str(source_path),
                    "mirror_url": "https://mirror.example/resume-ready",
                    "max_retries": "0",
                    "test_failures_before_success": "1",
                    "test_fail_after_bytes": "512",
                },
            ),
            context=None,
        )
    )

    snapshot = service._core._job_registry.snapshot()
    download = snapshot["downloads"][0]

    assert download["source_model"] == "mlx-community/resume-ready-demo"
    assert download["output_dir"] == str(output_dir)
    assert download["status"] == "failed"
    assert download["resume_ready"] is True
    assert download["partial_path"].endswith("download.artifact.partial")
    assert download["downloaded_bytes"] == 512


def test_job_registry_snapshot_supports_name_only_publish_and_unpublished_adapters() -> None:
    registry = ModelOpsJobRegistry()

    published_train = registry.start("train_lora", "melix-dev-text", "/tmp/train-a")
    registry.attach_manifest(
        published_train.job_id,
        json.dumps(
            {
                "adapter_name": "adapter-a",
                "dataset_uri": "datasets/a",
                "target_repo": "melix/adapters/adapter-a",
                "training_duration_ms": 1550.0,
                "adapter_publish_ms": 125.0,
                "checkpoint_count": 2,
                "resume_ready": True,
                "tokens_per_second": 128.5,
                "peak_memory_gb": 5.25,
            }
        ),
    )
    registry.complete(published_train.job_id, "/tmp/train-a/train_lora.adapter.json")

    unrelated_upload = registry.start("upload", "melix-dev-text", "/tmp/upload-model")
    registry.attach_manifest(
        unrelated_upload.job_id,
        json.dumps(
            {
                "target_repo": "melix/models/dev",
                "ext": {"artifact_kind": "model"},
            }
        ),
    )
    registry.complete(unrelated_upload.job_id, "/tmp/upload-model/model.receipt.json")

    published_upload = registry.start("upload", "melix-dev-text", "/tmp/upload-adapter")
    registry.attach_manifest(
        published_upload.job_id,
        json.dumps(
            {
                "published_repo": "melix/adapters/adapter-a",
                "upload_backend": "huggingface_hub",
                "export_artifact_kind": "adapter_export",
                "parent_lineage": {
                    "local_artifact_path": "/tmp/train-a/train_lora.adapter.json",
                    "source_artifact_kind": "adapter",
                    "source_job_id": published_train.job_id,
                },
                "ext": {
                    "artifact_kind": "adapter",
                    "adapter_name": "adapter-a",
                },
            }
        ),
    )
    registry.complete(published_upload.job_id, "/tmp/upload-adapter/adapter.receipt.json")

    unpublished_train = registry.start("train_lora", "melix-dev-text", "/tmp/train-b")
    registry.attach_manifest(
        unpublished_train.job_id,
        json.dumps(
            {
                "adapter_name": "adapter-b",
                "dataset_uri": "datasets/b",
                "training_duration_ms": 820.0,
                "checkpoint_count": 0,
                "resume_ready": False,
                "tokens_per_second": 0.0,
                "peak_memory_gb": 0.0,
            }
        ),
    )
    registry.complete(unpublished_train.job_id, "/tmp/train-b/train_lora.adapter.json")

    adapters = {adapter["adapter_name"]: adapter for adapter in registry.snapshot()["adapters"]}

    assert adapters["adapter-a"]["published_repo"] == "melix/adapters/adapter-a"
    assert adapters["adapter-a"]["publish_job_id"] == published_upload.job_id
    assert adapters["adapter-a"]["publish_backend"] == "huggingface_hub"
    assert adapters["adapter-a"]["publish_artifact_kind"] == "adapter_export"
    assert adapters["adapter-a"]["publish_parent_lineage"]["source_job_id"] == published_train.job_id
    assert adapters["adapter-a"]["status"] == "published"
    assert adapters["adapter-a"]["checkpoint_count"] == 2
    assert adapters["adapter-a"]["resume_ready"] is True
    assert adapters["adapter-a"]["tokens_per_second"] == 128.5
    assert adapters["adapter-a"]["peak_memory_gb"] == 5.25
    assert adapters["adapter-b"]["published_repo"] == ""
    assert adapters["adapter-b"]["publish_job_id"] == ""
    assert adapters["adapter-b"]["status"] == "completed"
    assert adapters["adapter-b"]["checkpoint_count"] == 0
    assert adapters["adapter-b"]["resume_ready"] is False


def test_job_registry_snapshot_records_merged_publish_lineage_for_derived_models() -> None:
    registry = ModelOpsJobRegistry()

    train_job = registry.start("train_lora", "melix-dev-text", "/runtime/train")
    adapter_manifest_path = "/runtime/train/train_lora.adapter.json"
    registry.attach_manifest(
        train_job.job_id,
        json.dumps({"adapter_name": "adapter-merged", "adapter_set_hash": "adapter-hash-a"}),
    )
    registry.complete(train_job.job_id, adapter_manifest_path)

    activation_job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
    activation_manifest_path = "/runtime/activate/melix-dev-fused/manifest.json"
    registry.attach_manifest(
        activation_job.job_id,
        json.dumps(
            {
                "adapter_name": "adapter-merged",
                "adapter_manifest_path": adapter_manifest_path,
                "adapter_weights_path": "/runtime/train/adapters.safetensors",
                "adapter_set_hash": "adapter-hash-a",
                "derived_model_id": "melix-dev-fused",
                "derived_model_path": "/runtime/activate/melix-dev-fused",
                "activation_duration_ms": 321.0,
                "source_adapter_job_id": train_job.job_id,
                "activation_mode": "fused_derived_model",
            }
        ),
    )
    registry.complete(activation_job.job_id, activation_manifest_path)

    publish_job = registry.start("upload", "melix-dev-text", "/runtime/upload")
    registry.attach_manifest(
        publish_job.job_id,
        json.dumps(
            {
                "published_repo": "melix/models/melix-dev-fused",
                "upload_backend": "huggingface_hub",
                "export_artifact_kind": "merged_export",
                "parent_lineage": {
                    "local_artifact_path": "/runtime/activate/melix-dev-fused",
                    "local_manifest_path": activation_manifest_path,
                    "source_job_id": activation_job.job_id,
                    "source_adapter_job_id": train_job.job_id,
                    "activation_mode": "fused_derived_model",
                    "derived_model_id": "melix-dev-fused",
                },
            }
        ),
    )
    registry.complete(publish_job.job_id, "/runtime/upload/upload.receipt.json")

    derived_model = registry.snapshot()["derived_models"][0]

    assert derived_model["published_repo"] == "melix/models/melix-dev-fused"
    assert derived_model["publish_job_id"] == publish_job.job_id
    assert derived_model["publish_backend"] == "huggingface_hub"
    assert derived_model["publish_artifact_kind"] == "merged_export"
    assert derived_model["published_state"] == "published"
    assert derived_model["publish_parent_lineage"]["source_job_id"] == activation_job.job_id
    assert derived_model["publish_parent_lineage"]["source_adapter_job_id"] == train_job.job_id


def test_job_registry_snapshot_emits_publishes_section_for_adapter_and_merged_uploads() -> None:
    registry = ModelOpsJobRegistry()

    adapter_train = registry.start("train_lora", "melix-dev-text", "/tmp/train-a")
    registry.attach_manifest(
        adapter_train.job_id,
        json.dumps({"adapter_name": "adapter-a"}),
    )
    registry.complete(adapter_train.job_id, "/tmp/train-a/train_lora.adapter.json")

    adapter_upload = registry.start("upload", "melix-dev-text", "/tmp/upload-adapter")
    registry.attach_manifest(
        adapter_upload.job_id,
        json.dumps(
            {
                "published_repo": "melix/adapters/adapter-a",
                "published_url": "https://huggingface.co/melix/adapters/adapter-a",
                "published_ref": "main",
                "published_files": ["train_lora.adapter.json", "adapter/adapters.safetensors"],
                "upload_backend": "huggingface_hub",
                "export_artifact_kind": "adapter_export",
                "source_artifact_kind": "adapter",
                "distribution_contract": "adapter_only",
                "adapter_name": "adapter-a",
                "source_model": "melix-dev-text",
                "source_model_from_artifact": "melix-dev-text",
                "parent_lineage": {
                    "local_artifact_path": "/tmp/train-a/train_lora.adapter.json",
                    "local_manifest_path": "/tmp/train-a/train_lora.adapter.json",
                    "source_artifact_kind": "adapter",
                    "source_job_id": adapter_train.job_id,
                    "source_model": "melix-dev-text",
                    "export_artifact_kind": "adapter_export",
                },
                "upload_duration_ms": 120.5,
                "ext": {"artifact_kind": "adapter", "adapter_name": "adapter-a"},
            }
        ),
    )
    registry.complete(adapter_upload.job_id, "/tmp/upload-adapter/upload.receipt.json")

    merged_upload = registry.start("upload", "melix-dev-text", "/tmp/upload-merged")
    registry.attach_manifest(
        merged_upload.job_id,
        json.dumps(
            {
                "published_repo": "melix/models/melix-dev-fused",
                "published_url": "https://huggingface.co/melix/models/melix-dev-fused",
                "upload_backend": "huggingface_hub",
                "export_artifact_kind": "merged_export",
                "source_artifact_kind": "derived_text_model",
                "distribution_contract": "merged_model",
                "parent_lineage": {
                    "local_artifact_path": "/runtime/activate/melix-dev-fused",
                    "local_manifest_path": "/runtime/activate/melix-dev-fused/manifest.json",
                    "source_artifact_kind": "derived_text_model",
                    "source_job_id": "model-ops-0099",
                    "source_adapter_job_id": adapter_train.job_id,
                    "activation_mode": "fused_derived_model",
                    "derived_model_id": "melix-dev-fused",
                    "source_model": "melix-dev-text",
                    "export_artifact_kind": "merged_export",
                },
                "upload_duration_ms": 321.0,
            }
        ),
    )
    registry.complete(merged_upload.job_id, "/tmp/upload-merged/upload.receipt.json")

    # A completed upload that never actually hit a remote (no target_repo,
    # no published_url, no recognized artifact kind) should stay out of the
    # publishes lineage — it's not a publish event in any meaningful sense.
    unrelated = registry.start("upload", "melix-dev-text", "/tmp/upload-no-target")
    registry.attach_manifest(
        unrelated.job_id,
        json.dumps({"ext": {"artifact_kind": "model"}}),
    )
    registry.complete(unrelated.job_id, "/tmp/upload-no-target/upload.receipt.json")

    publishes = {entry["job_id"]: entry for entry in registry.snapshot()["publishes"]}

    assert adapter_upload.job_id in publishes
    assert merged_upload.job_id in publishes
    assert unrelated.job_id not in publishes

    adapter_entry = publishes[adapter_upload.job_id]
    assert adapter_entry["status"] == "published"
    assert adapter_entry["target_repo"] == "melix/adapters/adapter-a"
    assert adapter_entry["export_artifact_kind"] == "adapter_export"
    assert adapter_entry["source_artifact_kind"] == "adapter"
    assert adapter_entry["distribution_contract"] == "adapter_only"
    assert adapter_entry["publish_backend"] == "huggingface_hub"
    assert adapter_entry["adapter_name"] == "adapter-a"
    assert adapter_entry["source_job_id"] == adapter_train.job_id
    assert adapter_entry["source_artifact_path"] == "/tmp/train-a/train_lora.adapter.json"
    assert adapter_entry["source_manifest_path"] == "/tmp/train-a/train_lora.adapter.json"
    assert adapter_entry["published_url"].endswith("/adapters/adapter-a")
    assert adapter_entry["published_ref"] == "main"
    assert "train_lora.adapter.json" in adapter_entry["published_files"]
    assert adapter_entry["receipt_path"] == "/tmp/upload-adapter/upload.receipt.json"
    assert adapter_entry["upload_duration_ms"] == 120.5

    merged_entry = publishes[merged_upload.job_id]
    assert merged_entry["export_artifact_kind"] == "merged_export"
    assert merged_entry["source_artifact_kind"] == "derived_text_model"
    assert merged_entry["distribution_contract"] == "merged_model"
    assert merged_entry["derived_model_id"] == "melix-dev-fused"
    assert merged_entry["activation_mode"] == "fused_derived_model"
    assert merged_entry["source_artifact_path"] == "/runtime/activate/melix-dev-fused"
    assert merged_entry["source_manifest_path"].endswith("/melix-dev-fused/manifest.json")
    assert merged_entry["parent_lineage"]["source_adapter_job_id"] == adapter_train.job_id


def test_job_registry_snapshot_publishes_tolerates_null_manifest_fields() -> None:
    registry = ModelOpsJobRegistry()

    upload_job = registry.start("upload", "melix-dev-text", "/tmp/upload-null")
    registry.attach_manifest(
        upload_job.job_id,
        json.dumps(
            {
                "published_repo": None,
                "target_repo": "melix/adapters/adapter-null",
                "published_url": None,
                "published_ref": None,
                "published_files": None,
                "upload_backend": None,
                "publish_backend": "huggingface_hub",
                "export_artifact_kind": "adapter_export",
                "source_artifact_kind": "adapter",
                "distribution_contract": None,
                "adapter_name": None,
                "source_model": None,
                "parent_lineage": None,
                "upload_duration_ms": None,
                "ext": {"artifact_kind": "adapter", "adapter_name": "adapter-null"},
            }
        ),
    )
    registry.complete(upload_job.job_id, "/tmp/upload-null/upload.receipt.json")

    publishes = registry.snapshot()["publishes"]
    assert len(publishes) == 1
    entry = publishes[0]

    # str(None) would have leaked "None" into these fields without the or-fallbacks.
    for key in (
        "published_url",
        "published_ref",
        "distribution_contract",
        "adapter_name",
        "derived_model_id",
        "activation_mode",
        "source_artifact_path",
        "source_manifest_path",
        "source_model",
    ):
        assert entry[key] != "None", f"{key} leaked str(None)"
        assert entry[key] != "null"
    assert entry["target_repo"] == "melix/adapters/adapter-null"
    assert entry["publish_backend"] == "huggingface_hub"
    assert entry["adapter_name"] == "adapter-null"
    # float(None) would have raised TypeError; verify the fallback.
    assert entry["upload_duration_ms"] == 0.0
    assert entry["parent_lineage"] == {}
    assert entry["published_files"] == []


def test_job_registry_snapshot_publishes_admits_quantized_model_bundle_source_kind() -> None:
    registry = ModelOpsJobRegistry()

    upload_job = registry.start("upload", "melix-dev-text", "/tmp/upload-quant")
    registry.attach_manifest(
        upload_job.job_id,
        json.dumps(
            {
                "target_repo": "melix/models/quant-bundle",
                "upload_backend": "huggingface_hub",
                # Worker emitted a quantized-bundle upload without
                # export_artifact_kind; the source-kind branch should still
                # admit it into publishes.
                "source_artifact_kind": "quantized_model_bundle",
            }
        ),
    )
    registry.complete(upload_job.job_id, "/tmp/upload-quant/upload.receipt.json")

    publishes = registry.snapshot()["publishes"]
    assert len(publishes) == 1
    assert publishes[0]["source_artifact_kind"] == "quantized_model_bundle"
    assert publishes[0]["export_artifact_kind"] == ""
    assert publishes[0]["target_repo"] == "melix/models/quant-bundle"


def test_job_registry_snapshot_publishes_admits_legacy_uploads_with_target_repo() -> None:
    # Pre-Module-5 worker emissions only carried `published_repo` plus an
    # upload backend without `export_artifact_kind` / `source_artifact_kind`.
    # Those should still appear in the publishes lineage view so the doc
    # claim ("old-format manifests keep working") holds.
    registry = ModelOpsJobRegistry()

    legacy_upload = registry.start("upload", "melix-dev-text", "/tmp/upload-legacy")
    registry.attach_manifest(
        legacy_upload.job_id,
        json.dumps(
            {
                "published_repo": "melix/models/legacy-bundle",
                "upload_backend": "huggingface_hub",
            }
        ),
    )
    registry.complete(legacy_upload.job_id, "/tmp/upload-legacy/upload.receipt.json")

    publishes = registry.snapshot()["publishes"]
    assert len(publishes) == 1
    assert publishes[0]["job_id"] == legacy_upload.job_id
    assert publishes[0]["target_repo"] == "melix/models/legacy-bundle"
    assert publishes[0]["export_artifact_kind"] == ""
    assert publishes[0]["source_artifact_kind"] == ""


def test_job_registry_snapshot_publishes_drops_unrelated_uploads_without_remote_target() -> None:
    # A completed `upload` job that didn't reach a remote (no published_repo,
    # no published_url, no recognized artifact kind) is by definition not a
    # publish — keep it out of the publishes lineage view to avoid leaking
    # unrelated worker emissions.
    registry = ModelOpsJobRegistry()

    unrelated = registry.start("upload", "melix-dev-text", "/tmp/upload-unrelated")
    registry.attach_manifest(
        unrelated.job_id,
        json.dumps({"ext": {"artifact_kind": "model"}}),
    )
    registry.complete(unrelated.job_id, "/tmp/upload-unrelated/upload.receipt.json")

    snapshot = registry.snapshot()
    assert snapshot["publishes"] == []


def test_job_registry_snapshot_publishes_treats_non_list_published_files_as_empty() -> None:
    # If a hand-edited manifest stored a string in `published_files`, naive
    # `list(...)` would split it into per-character entries. Verify the
    # `isinstance(value, list)` guard reduces that to an empty list.
    registry = ModelOpsJobRegistry()

    upload_job = registry.start("upload", "melix-dev-text", "/tmp/upload-stringy")
    registry.attach_manifest(
        upload_job.job_id,
        json.dumps(
            {
                "published_repo": "melix/adapters/stringy",
                "upload_backend": "huggingface_hub",
                "export_artifact_kind": "adapter_export",
                "source_artifact_kind": "adapter",
                "published_files": "weights.safetensors",
            }
        ),
    )
    registry.complete(upload_job.job_id, "/tmp/upload-stringy/upload.receipt.json")

    publishes = registry.snapshot()["publishes"]
    assert len(publishes) == 1
    assert publishes[0]["published_files"] == []


def test_job_registry_snapshot_emits_empty_publishes_when_no_completed_uploads() -> None:
    registry = ModelOpsJobRegistry()

    train_job = registry.start("train_lora", "melix-dev-text", "/tmp/train-only")
    registry.attach_manifest(train_job.job_id, json.dumps({"adapter_name": "adapter-only"}))
    registry.complete(train_job.job_id, "/tmp/train-only/train_lora.adapter.json")

    in_flight_upload = registry.start("upload", "melix-dev-text", "/tmp/in-flight")
    registry.attach_manifest(
        in_flight_upload.job_id,
        json.dumps({"export_artifact_kind": "adapter_export"}),
    )

    snapshot = registry.snapshot()
    assert snapshot["publishes"] == []


def test_job_registry_snapshot_surfaces_dataset_provenance_and_derived_model_linkage() -> None:
    registry = ModelOpsJobRegistry()

    train_job = registry.start("train_lora", "melix-dev-text", "/runtime/train")
    adapter_manifest_path = "/runtime/train/train_lora.adapter.json"
    registry.attach_manifest(
        train_job.job_id,
        json.dumps(
            {
                "adapter_name": "adapter-hf",
                "dataset_uri": "hf://melix/demo-hf?config=default&split=train",
                "dataset_source_kind": "hf_dataset",
                "dataset_id": "melix/demo-hf:default:train@main",
                "dataset_format": "text_completion",
                "dataset_materialized_package_path": "/runtime/datasets/cache-a",
                "normalized_dataset_manifest_path": "/runtime/train/normalized_dataset/manifest.json",
                "hf_dataset_path": "melix/demo-hf",
                "hf_dataset_name": "default",
                "hf_dataset_revision": "main",
                "hf_train_split": "train",
                "adapter_set_hash": "adapter-hash-a",
                "training_duration_ms": 900.0,
            }
        ),
    )
    registry.complete(train_job.job_id, adapter_manifest_path)

    activation_job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
    registry.attach_manifest(
        activation_job.job_id,
        json.dumps(
            {
                "adapter_name": "adapter-hf",
                "adapter_manifest_path": adapter_manifest_path,
                "adapter_weights_path": "/runtime/train/adapter-bundle/adapters.safetensors",
                "adapter_set_hash": "adapter-hash-a",
                "derived_model_id": "melix-dev-text-lora-adapter",
                "derived_model_path": "/runtime/activate/melix-dev-text-lora-adapter",
                "activation_duration_ms": 321.0,
                "source_adapter_job_id": train_job.job_id,
            }
        ),
    )
    registry.complete(activation_job.job_id, "/runtime/activate/melix-dev-text-lora-adapter/manifest.json")

    snapshot = registry.snapshot()
    adapter = snapshot["adapters"][0]
    derived_model = snapshot["derived_models"][0]

    assert adapter["dataset_source_kind"] == "hf_dataset"
    assert adapter["dataset_id"] == "melix/demo-hf:default:train@main"
    assert adapter["dataset_format"] == "text_completion"
    assert adapter["dataset_materialized_package_path"] == "/runtime/datasets/cache-a"
    assert adapter["normalized_dataset_manifest_path"] == "/runtime/train/normalized_dataset/manifest.json"
    assert adapter["hf_dataset_path"] == "melix/demo-hf"
    assert adapter["hf_dataset_name"] == "default"
    assert adapter["hf_dataset_revision"] == "main"
    assert adapter["hf_train_split"] == "train"
    assert adapter["derived_model_id"] == "melix-dev-text-lora-adapter"
    assert adapter["derived_model_path"] == "/runtime/activate/melix-dev-text-lora-adapter"
    assert derived_model["model_id"] == "melix-dev-text-lora-adapter"
    assert derived_model["adapter_manifest_path"] == adapter_manifest_path
    assert derived_model["adapter_weights_path"] == "/runtime/train/adapter-bundle/adapters.safetensors"
    assert derived_model["source_adapter_job_id"] == train_job.job_id


def test_job_registry_snapshot_surfaces_grouped_lora_experiments_from_local_index(tmp_path: Path) -> None:
    service = build_service(tmp_path, runner=DeterministicLoRARunner())
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "melix-dev-dataset",
                "format": "chat_messages",
                "sample_count": 1,
                "version": "1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (dataset_dir / "samples.jsonl").write_text(
        json.dumps({"messages": [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "world"}]})
        + "\n",
        encoding="utf-8",
    )

    for adapter_name in ["grouped-adapter-a", "grouped-adapter-b"]:
        list(
            service.ConvertModel(
                maintenance_pb2.ConvertModelRequest(
                    source_model="melix-dev-text",
                    output_dir=str(tmp_path / adapter_name),
                    generate_manifest=True,
                    ext={
                        "operation": "train_lora",
                        "dataset_uri": str(dataset_dir),
                        "adapter_name": adapter_name,
                        "preset_id": "balanced_adapter",
                        "experiment_group_id": "nightly-qwen35",
                    },
                ),
                context=None,
            )
        )

    snapshot = service._core._job_registry.snapshot()
    group = snapshot["experiment_groups"][0]

    assert group["group_id"] == "nightly-qwen35"
    assert group["run_count"] == 2
    assert group["latest_preset_id"] == "balanced_adapter"
    assert group["latest_preset_title"] == "Balanced Adapter"
    assert group["best_run_id"].startswith("model-ops-")
    assert group["recommended_manifest_path"].endswith("train_lora.adapter.json")
    assert group["latest_tokens_per_second"] > 0.0
    assert group["latest_peak_memory_gb"] >= 0.0


def test_job_registry_restores_completed_lora_jobs_from_jobs_root(tmp_path: Path) -> None:
    jobs_root = tmp_path / "model-ops"
    train_dir = jobs_root / "train_lora" / "model-ops-0012"
    train_dir.mkdir(parents=True)
    adapter_manifest_path = train_dir / "train_lora.adapter.json"
    adapter_manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.lora_adapter_package.v1",
                "job_id": "model-ops-0012",
                "operation": "train_lora",
                "source_model": "melix-dev-text",
                "adapter_name": "adapter-restored",
                "dataset_uri": "hf://melix/demo-hf?config=default&split=train",
                "dataset_source_kind": "hf_dataset",
                "dataset_id": "melix/demo-hf:default:train@main",
                "dataset_format": "chat_messages",
                "adapter_set_hash": "adapter-hash-b",
                "target_repo": "melix/adapters/adapter-restored",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    derived_dir = jobs_root / "activate_adapter" / "model-ops-0016" / "melix-dev-text-lora-adapter"
    derived_dir.mkdir(parents=True)
    activation_manifest_path = derived_dir / "manifest.json"
    activation_manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.derived_text_model.v1",
                "job_id": "model-ops-0016",
                "operation": "activate_adapter",
                "source_model": "melix-dev-text",
                "adapter_manifest_path": str(adapter_manifest_path),
                "adapter_name": "adapter-restored",
                "adapter_set_hash": "adapter-hash-b",
                "source_adapter_job_id": "model-ops-0012",
                "derived_model_id": "melix-dev-text-lora-adapter",
                "derived_model_path": str(derived_dir),
                "derived_model_alias": "restored-alias",
                "activation_mode": "fused_derived_model",
                "activation_duration_ms": 456.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    registry = ModelOpsJobRegistry(jobs_root=jobs_root)
    snapshot = registry.snapshot()

    assert snapshot["adapters"][0]["adapter_name"] == "adapter-restored"
    assert snapshot["adapters"][0]["derived_model_id"] == "melix-dev-text-lora-adapter"
    assert snapshot["derived_models"][0]["model_id"] == "melix-dev-text-lora-adapter"
    assert snapshot["derived_models"][0]["derived_model_alias"] == "restored-alias"

    next_job = registry.start("registry_snapshot", "melix-dev-model-ops", str(jobs_root / "registry_snapshot"))
    assert next_job.job_id == "model-ops-0017"


def test_job_registry_snapshot_hides_removed_derived_models_and_marks_adapter_removed() -> None:
    registry = ModelOpsJobRegistry()

    train_job = registry.start("train_lora", "melix-dev-text", "/runtime/train")
    adapter_manifest_path = "/runtime/train/train_lora.adapter.json"
    registry.attach_manifest(
        train_job.job_id,
        json.dumps(
            {
                "adapter_name": "adapter-removable",
                "adapter_set_hash": "adapter-hash-remove",
                "dataset_uri": "/runtime/dataset",
            }
        ),
    )
    registry.complete(train_job.job_id, adapter_manifest_path)

    activation_job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
    registry.attach_manifest(
        activation_job.job_id,
        json.dumps(
            {
                "adapter_name": "adapter-removable",
                "adapter_manifest_path": adapter_manifest_path,
                "adapter_set_hash": "adapter-hash-remove",
                "derived_model_id": "melix-dev-text-lora-removable",
                "derived_model_path": "/runtime/activate/melix-dev-text-lora-removable",
                "activation_duration_ms": 321.0,
                "source_adapter_job_id": train_job.job_id,
                "activation_mode": "fused_derived_model",
            }
        ),
    )
    registry.complete(activation_job.job_id, "/runtime/activate/melix-dev-text-lora-removable/manifest.json")

    removal_job = registry.start("remove_derived_model", "melix-dev-text", "/runtime/remove")
    registry.attach_manifest(
        removal_job.job_id,
        json.dumps(
            {
                "derived_model_id": "melix-dev-text-lora-removable",
                "adapter_manifest_path": adapter_manifest_path,
                "activation_job_id": activation_job.job_id,
                "activation_mode": "fused_derived_model",
                "removed": True,
            }
        ),
    )
    registry.complete(removal_job.job_id, "/runtime/remove/remove_derived_model.lifecycle.json")

    snapshot = registry.snapshot()

    assert snapshot["derived_models"] == []
    assert snapshot["adapters"][0]["activation_status"] == "removed"
    assert snapshot["adapters"][0]["derived_model_id"] == ""
    assert snapshot["adapters"][0]["derived_model_path"] == ""


def test_job_registry_restores_completed_remove_derived_jobs_from_jobs_root(tmp_path: Path) -> None:
    jobs_root = tmp_path / "model-ops"
    train_dir = jobs_root / "train_lora" / "model-ops-0012"
    train_dir.mkdir(parents=True)
    adapter_manifest_path = train_dir / "train_lora.adapter.json"
    adapter_manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.lora_adapter_package.v1",
                "job_id": "model-ops-0012",
                "operation": "train_lora",
                "source_model": "melix-dev-text",
                "adapter_name": "adapter-removable",
                "adapter_set_hash": "adapter-hash-remove",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    derived_dir = jobs_root / "activate_adapter" / "model-ops-0016" / "melix-dev-text-lora-removable"
    derived_dir.mkdir(parents=True)
    (derived_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.derived_text_model.v1",
                "job_id": "model-ops-0016",
                "operation": "activate_adapter",
                "source_model": "melix-dev-text",
                "adapter_manifest_path": str(adapter_manifest_path),
                "adapter_name": "adapter-removable",
                "adapter_set_hash": "adapter-hash-remove",
                "source_adapter_job_id": "model-ops-0012",
                "derived_model_id": "melix-dev-text-lora-removable",
                "derived_model_path": str(derived_dir),
                "activation_mode": "fused_derived_model",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    removal_dir = jobs_root / "remove_derived_model" / "model-ops-0017"
    removal_dir.mkdir(parents=True)
    (removal_dir / "remove_derived_model.lifecycle.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.derived_model_removal.v1",
                "job_id": "model-ops-0017",
                "operation": "remove_derived_model",
                "derived_model_id": "melix-dev-text-lora-removable",
                "adapter_manifest_path": str(adapter_manifest_path),
                "activation_job_id": "model-ops-0016",
                "activation_mode": "fused_derived_model",
                "removed": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    registry = ModelOpsJobRegistry(jobs_root=jobs_root)
    snapshot = registry.snapshot()

    assert snapshot["derived_models"] == []
    assert snapshot["adapters"][0]["activation_status"] == "removed"
    next_job = registry.start("registry_snapshot", "melix-dev-model-ops", str(jobs_root / "registry_snapshot"))
    assert next_job.job_id == "model-ops-0018"


def test_job_registry_snapshot_rewrites_non_finite_metrics_to_null() -> None:
    registry = ModelOpsJobRegistry()

    train_job = registry.start("train_lora", "melix-dev-text", "/runtime/train")
    registry.attach_manifest(
        train_job.job_id,
        json.dumps(
            {
                "schema_version": "melix.lora_adapter_package.v1",
                "job_id": train_job.job_id,
                "operation": "train_lora",
                "source_model": "melix-dev-text",
                "adapter_name": "adapter-nan",
                "loss_final": float("nan"),
                "loss_best": float("inf"),
            }
        ),
    )
    registry.complete(train_job.job_id, "/runtime/train/train_lora.adapter.json")

    snapshot = registry.snapshot()

    assert snapshot["jobs"][0]["manifest"]["loss_final"] is None
    assert snapshot["jobs"][0]["manifest"]["loss_best"] is None
    json.dumps(snapshot, allow_nan=False)


def test_registry_snapshot_restores_lora_history_after_worker_restart(tmp_path: Path) -> None:
    dataset_dir = _write_training_dataset_package(tmp_path)
    runner = DeterministicLoRARunner()
    service = build_service(tmp_path, runner=runner)

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
                    "derived_model_alias": "Restart Alias",
                },
            ),
            context=None,
        )
    )
    activation_payload = json.loads(
        next(event.manifest for event in activate_events if event.HasField("manifest")).manifest_json
    )

    restarted_service = build_service(tmp_path, runner=DeterministicLoRARunner())
    snapshot_events = list(
        restarted_service.ConvertModel(
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

    assert snapshot_events[0].started.job_id == "model-ops-0003"
    assert snapshot_payload["adapters"][0]["adapter_name"] == "melix-dev-adapter"
    assert snapshot_payload["adapters"][0]["activation_status"] == "activated"
    assert snapshot_payload["adapters"][0]["derived_model_id"] == activation_payload["derived_model_id"]
    assert snapshot_payload["derived_models"][0]["model_id"] == activation_payload["derived_model_id"]
    assert snapshot_payload["derived_models"][0]["derived_model_alias"] == "Restart Alias"


def test_get_model_info_returns_known_dev_model_metadata(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    embed = service.GetModelInfo(
        maintenance_pb2.GetModelInfoRequest(source_model="melix-dev-embed"),
        context=None,
    )
    rerank = service.GetModelInfo(
        maintenance_pb2.GetModelInfoRequest(source_model="melix-dev-rerank"),
        context=None,
    )
    missing = service.GetModelInfo(
        maintenance_pb2.GetModelInfoRequest(source_model="missing-model"),
        context=None,
    )

    assert embed.ok is True
    assert embed.model_kind == "embedding"
    assert embed.supported_modalities == ["text"]
    assert embed.supported_tasks == ["embed"]
    assert embed.supported_parsers == ["text"]
    assert embed.backend_id == "bert-v1"
    assert embed.family_id == "bert"
    assert embed.model_path == "models/melix-dev-embed"
    assert embed.model_revision == "dev"
    assert embed.detected_identity_source == "default"
    assert rerank.ok is True
    assert rerank.model_kind == "rerank"
    assert rerank.supported_modalities == ["text"]
    assert rerank.supported_tasks == ["rerank"]
    assert rerank.supported_parsers == ["text"]
    assert rerank.backend_id == "token-overlap-v1"
    assert rerank.family_id == "jina-v3"
    assert rerank.model_revision == "dev"
    assert missing.ok is False
    assert missing.error.code == "not_found"


def test_get_model_info_uses_kind_fallbacks_for_audio_and_image_models(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    transcription = service.GetModelInfo(
        maintenance_pb2.GetModelInfoRequest(source_model="melix-dev-transcribe"),
        context=None,
    )
    speech = service.GetModelInfo(
        maintenance_pb2.GetModelInfoRequest(source_model="melix-dev-speech"),
        context=None,
    )
    image = service.GetModelInfo(
        maintenance_pb2.GetModelInfoRequest(source_model="melix-dev-image"),
        context=None,
    )

    assert transcription.ok is True
    assert transcription.supported_modalities == ["audio", "text"]
    assert transcription.supported_tasks == ["transcribe"]
    assert transcription.supported_parsers == ["text"]

    assert speech.ok is True
    assert speech.supported_modalities == ["text", "audio"]
    assert speech.supported_tasks == ["speak"]
    assert speech.supported_parsers == ["text"]

    assert image.ok is True
    assert image.supported_modalities == ["text", "image"]
    assert image.supported_tasks == ["image_generate", "image_edit"]
    assert image.supported_parsers == ["text"]
    assert image.backend_id == "deterministic"
    assert image.family_id == "deterministic-v1"
    assert image.default_workflow_role == "generate"
    assert image.detected_identity_source == "default"


def test_get_model_info_appends_tool_parser_when_capability_parser_metadata_is_absent(
    tmp_path: Path,
) -> None:
    service = build_service(tmp_path)
    vlm = service._core._registry.model_catalog.get("melix-dev-vlm")
    assert vlm is not None

    del vlm.ext["melix.capability.supported_parsers"]

    response = service.GetModelInfo(
        maintenance_pb2.GetModelInfoRequest(source_model="melix-dev-vlm"),
        context=None,
    )

    assert response.ok is True
    assert response.supported_parsers == ["text", "qwen"]
    assert response.family_id == "llava-v1"
    assert response.backend_id == "deterministic"


def test_doctor_and_bench_return_deterministic_reports(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    doctor = service.RunDoctor(
        maintenance_pb2.RunDoctorRequest(
            model_handle="melix-dev-text::1",
            include_cache_diagnostics=True,
            include_memory_report=True,
        ),
        context=None,
    )
    bench_events = list(
        service.RunBench(
            maintenance_pb2.RunBenchRequest(
                model_handle="melix-dev-text::1",
                suites=["smoke", "latency"],
            ),
            context=None,
        )
    )

    assert doctor.ok is True
    assert "# Melix Doctor" in doctor.report_markdown
    assert "## Health" in doctor.report_markdown
    assert "status: degraded" in doctor.report_markdown
    assert "model_handle: melix-dev-text::1" in doctor.report_markdown
    assert "## Cache" in doctor.report_markdown
    assert "## Memory" in doctor.report_markdown
    assert doctor.health_status == maintenance_pb2.HEALTH_STATUS_DEGRADED
    assert [finding.code for finding in doctor.findings] == ["model_not_loaded"]

    assert bench_events[0].started.job_id == "model-ops-0001"
    assert any(event.HasField("metric") and event.metric.name == "bench.smoke.ttft_ms" for event in bench_events)
    assert any(event.HasField("metric") and event.metric.name == "bench.latency.p95_ms" for event in bench_events)
    assert bench_events[-1].completed.report_path.endswith("bench-report.md")
    report = Path(bench_events[-1].completed.report_path).read_text(encoding="utf-8")
    assert "# Melix Bench" in report
    assert "bench.smoke.ttft_ms" in report


def test_run_bench_measures_runtime_behavior_from_loaded_backend(tmp_path: Path) -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=FastBenchmarkBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    service = build_service(tmp_path, registry=registry)


def test_doctor_reports_warning_for_loaded_models_without_cache_bytes(tmp_path: Path) -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=DeterministicTextBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    loaded = registry.load_model(WorkerModelCatalog.dev_text_model())
    service = WorkerMaintenanceService(registry, jobs_root=tmp_path / "model-ops")
    service._core._benchmark_suite_catalog = BenchmarkSuiteCatalog(
        hf_dataset_fetcher=FakeBenchmarkHFDatasetFetcher()
    )

    doctor = service.RunDoctor(
        maintenance_pb2.RunDoctorRequest(
            model_handle=loaded.handle,
            include_cache_diagnostics=True,
        ),
        context=None,
    )

    assert doctor.ok is True
    assert doctor.health_status == maintenance_pb2.HEALTH_STATUS_WARNING
    assert any(finding.code == "cache_unavailable" for finding in doctor.findings)
    assert "warning cache_unavailable" in doctor.report_markdown

    events = list(
        service.RunBench(
            maintenance_pb2.RunBenchRequest(
                model_handle="melix-dev-text::1",
                suites=["smoke", "latency"],
                parameters={"sample_size": "4"},
            ),
            context=None,
        )
    )

    metrics = {
        event.metric.name: event.metric.value
        for event in events
        if event.HasField("metric")
    }

    assert metrics["bench.smoke.tokens_per_second"] > 0.0
    assert 0.0 <= metrics["bench.smoke.ttft_ms"] < 20.0
    assert metrics["bench.latency.p95_ms"] >= metrics["bench.latency.p50_ms"] >= 0.0


def test_doctor_findings_cover_failed_worker_and_zero_resident_bytes(tmp_path: Path) -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=DeterministicTextBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    core = MaintenanceCore(registry, jobs_root=tmp_path / "model-ops")
    loaded = registry.load_model(WorkerModelCatalog.dev_text_model())
    request = maintenance_pb2.RunDoctorRequest(
        model_handle=loaded.handle,
        include_memory_report=True,
    )
    stats = SimpleNamespace(
        worker_state="failed",
        resident_bytes=0,
        l1_cache_bytes=128,
        l2_cache_bytes=64,
    )

    findings = core._doctor_findings(
        request=request,
        stats=stats,
        loaded_models=[loaded.handle],
        loaded_model=loaded,
    )

    assert [finding.code for finding in findings] == ["worker_failed", "resident_bytes_zero"]
    assert findings[0].severity == maintenance_pb2.HEALTH_STATUS_FAILED
    assert findings[1].severity == maintenance_pb2.HEALTH_STATUS_WARNING
    assert core._doctor_health_status(findings) == maintenance_pb2.HEALTH_STATUS_FAILED
    assert core._doctor_health_status_label(findings[0].severity) == "failed"


def test_doctor_health_status_helpers_cover_healthy_and_unknown_states() -> None:
    assert maintenance_core_module._health_status_rank(maintenance_pb2.HEALTH_STATUS_FAILED) == 4
    assert maintenance_core_module._health_status_rank(maintenance_pb2.HEALTH_STATUS_HEALTHY) == 1
    assert maintenance_core_module._health_status_rank(maintenance_pb2.HEALTH_STATUS_UNSPECIFIED) == 0
    assert MaintenanceCore._doctor_health_status_label(maintenance_pb2.HEALTH_STATUS_FAILED) == "failed"
    assert MaintenanceCore._doctor_health_status_label(maintenance_pb2.HEALTH_STATUS_UNSPECIFIED) == "unknown"


def test_resolve_benchmark_loaded_model_reuses_existing_handle(tmp_path: Path) -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=DeterministicTextBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    loaded = registry.load_model(WorkerModelCatalog.dev_text_model())
    core = MaintenanceCore(registry, jobs_root=tmp_path / "model-ops")

    lazy_handle, resolved = core._resolve_benchmark_loaded_model(loaded.handle)

    assert lazy_handle == ""
    assert resolved.handle == loaded.handle


def test_resolve_benchmark_loaded_model_raises_typed_error_for_unknown_model(tmp_path: Path) -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=DeterministicTextBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    core = MaintenanceCore(registry, jobs_root=tmp_path / "model-ops")

    try:
        core._resolve_benchmark_loaded_model("missing-model::1")
    except ModelOperationError as error:
        assert error.code == "not_found"
        assert error.details == {"model_id": "missing-model"}
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("expected missing benchmark model to raise ModelOperationError")


def test_benchmark_helper_defaults_cover_invalid_parameters_and_sparse_samples(tmp_path: Path) -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=EmptyThenTokenBenchmarkBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    catalog = BenchmarkSuiteCatalog(hf_dataset_fetcher=FakeBenchmarkHFDatasetFetcher())
    core = MaintenanceCore(
        registry,
        jobs_root=tmp_path / "model-ops",
        benchmark_suite_catalog=catalog,
    )
    loaded = registry.load_model(WorkerModelCatalog.dev_text_model())
    resolved_suite = catalog.resolve_suite(
        "smoke",
        jobs_root=tmp_path / "model-ops",
        parameters={"sample_size": "oops", "batch_factor": "oops"},
    )

    sample = core._measure_text_bench_sample(
        loaded_model=loaded,
        suite=resolved_suite,
        prompt=resolved_suite.prompt_batches[0],
        parameters={"max_output_tokens": "not-a-number"},
        context_length=16,
        repeat_index=0,
        batch_size=1,
        cache_profile="cold",
        reasoning_mode="",
        structured_output_mode="",
    )

    assert sample.completion_tokens == 1
    assert resolved_suite.sample_size == 1
    assert resolved_suite.batch_factor == 1
    assert MaintenanceCore._benchmark_max_output_tokens({"max_output_tokens": "oops"}) == 8


def test_benchmark_partial_prefix_cache_profile_uses_a_shorter_warmup_prompt(tmp_path: Path) -> None:
    catalog = BenchmarkSuiteCatalog(hf_dataset_fetcher=FakeBenchmarkHFDatasetFetcher())
    suite = catalog.resolve_suite(
        "smoke",
        jobs_root=tmp_path / "model-ops",
        parameters={"sample_size": "1", "batch_factor": "1"},
    )

    warm_backend = RecordingBenchmarkBackend()
    warm_registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=warm_backend),
        model_catalog=WorkerModelCatalog(),
    )
    warm_core = MaintenanceCore(
        warm_registry,
        jobs_root=tmp_path / "warm-model-ops",
        benchmark_suite_catalog=catalog,
    )
    warm_loaded = warm_registry.load_model(WorkerModelCatalog.dev_text_model())
    warm_core._measure_text_bench_sample(
        loaded_model=warm_loaded,
        suite=suite,
        prompt=suite.prompt_batches[0],
        parameters={"max_output_tokens": "4"},
        context_length=32,
        repeat_index=0,
        batch_size=1,
        cache_profile="warm",
        reasoning_mode="",
        structured_output_mode="",
    )

    partial_backend = RecordingBenchmarkBackend()
    partial_registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=partial_backend),
        model_catalog=WorkerModelCatalog(),
    )
    partial_core = MaintenanceCore(
        partial_registry,
        jobs_root=tmp_path / "partial-model-ops",
        benchmark_suite_catalog=catalog,
    )
    partial_loaded = partial_registry.load_model(WorkerModelCatalog.dev_text_model())
    partial_core._measure_text_bench_sample(
        loaded_model=partial_loaded,
        suite=suite,
        prompt=suite.prompt_batches[0],
        parameters={"max_output_tokens": "4"},
        context_length=32,
        repeat_index=0,
        batch_size=1,
        cache_profile="partial_prefix",
        reasoning_mode="",
        structured_output_mode="",
    )

    assert len(warm_backend.prompts) == 2
    assert len(partial_backend.prompts) == 2
    assert len(partial_backend.prompts[0]) < len(warm_backend.prompts[0])
    assert partial_backend.prompts[0] != warm_backend.prompts[0]


def test_benchmark_helper_parsers_cover_invalid_and_boundary_inputs(tmp_path: Path) -> None:
    catalog = BenchmarkSuiteCatalog(hf_dataset_fetcher=FakeBenchmarkHFDatasetFetcher())
    suite = catalog.resolve_suite(
        "smoke",
        jobs_root=tmp_path / "model-ops",
        parameters={"sample_size": "1", "batch_factor": "1"},
    )
    core = MaintenanceCore(
        WorkerRegistry(
            runtime=MLXTextRuntime(backend=RecordingBenchmarkBackend()),
            model_catalog=WorkerModelCatalog(),
        ),
        jobs_root=tmp_path / "helper-model-ops",
        benchmark_suite_catalog=catalog,
    )

    with pytest.raises(ModelOperationError):
        MaintenanceCore._benchmark_cache_profile({"cache_profile": "invalid"})
    assert MaintenanceCore._benchmark_repeats({"repeats": "oops"}) == 1
    assert MaintenanceCore._benchmark_generation_length({"generation_length": "oops"}) == 8
    assert core._benchmark_context_lengths(
        suite=suite,
        parameters={"context_lengths": "8, bad, 4"},
    ) == (4, 8)
    assert core._benchmark_context_lengths(
        suite=suite,
        parameters={"context_lengths": "8, , 4"},
    ) == (4, 8)
    assert core._benchmark_context_lengths(
        suite=suite,
        parameters={"context_length": "oops"},
    ) == (32,)
    assert core._benchmark_batch_sizes({"batch_sizes": "1, bad, 2"}) == (1, 2)
    assert core._benchmark_batch_sizes({"batch_sizes": "1, , 2"}) == (1, 2)
    assert core._benchmark_batch_sizes({"batch_size": "oops"}) == (1,)
    assert core._shape_benchmark_prompt("", context_length=3) == "benchmark benchmark benchmark"
    assert core._shape_benchmark_prompt("one two three", context_length=2) == "one two"
    with pytest.raises(ModelOperationError):
        core._measure_text_bench_sample(
            loaded_model=core._registry.load_model(WorkerModelCatalog.dev_text_model()),
            suite=suite,
            prompt=suite.prompt_batches[0],
            parameters={"max_output_tokens": "4"},
            context_length=16,
            repeat_index=0,
            batch_size=1,
            cache_profile="invalid",
            reasoning_mode="",
            structured_output_mode="",
        )


def test_text_backed_vlm_models_force_text_benchmark_task_kind(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    loaded = SimpleNamespace(
        spec=common_pb2.ModelSpec(model_id="unsloth/gemma-4-E4B-it-MLX-8bit", model_kind="vlm"),
        runtime_model={"metadata": {"melix.vlm.execution_mode": "text_backed"}},
    )

    task_kind = service._core._resolved_benchmark_task_kind(
        request=maintenance_pb2.RunBenchRequest(task_kind="image-text-to-text"),
        parameters={},
        loaded_model=loaded,
    )

    assert task_kind == "text-generation"
    assert MaintenanceCore._percentile([], 95.0) == 0.0
    assert MaintenanceCore._percentile([1.234], 95.0) == 1.23


def test_resolved_benchmark_task_kind_covers_explicit_mode_and_model_kind_branches(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    explicit = service._core._resolved_benchmark_task_kind(
        request=maintenance_pb2.RunBenchRequest(task_kind="image-text-to-text"),
        parameters={},
        loaded_model=SimpleNamespace(spec=common_pb2.ModelSpec(model_kind="text"), runtime_model={}),
    )
    via_parameter = service._core._resolved_benchmark_task_kind(
        request=maintenance_pb2.RunBenchRequest(),
        parameters={"benchmark_mode": "vlm"},
        loaded_model=SimpleNamespace(spec=common_pb2.ModelSpec(model_kind="text"), runtime_model={}),
    )
    ocr = service._core._resolved_benchmark_task_kind(
        request=maintenance_pb2.RunBenchRequest(),
        parameters={},
        loaded_model=SimpleNamespace(spec=common_pb2.ModelSpec(model_kind="ocr"), runtime_model={}),
    )
    image_default = service._core._resolved_benchmark_task_kind(
        request=maintenance_pb2.RunBenchRequest(),
        parameters={},
        loaded_model=SimpleNamespace(spec=common_pb2.ModelSpec(model_kind="image"), runtime_model={}),
    )
    image_edit = service._core._resolved_benchmark_task_kind(
        request=maintenance_pb2.RunBenchRequest(),
        parameters={},
        loaded_model=SimpleNamespace(
            spec=common_pb2.ModelSpec(model_kind="image", ext={"melix.image.task_kind": "image-text-to-image"}),
            runtime_model={},
        ),
    )

    assert explicit == "image-text-to-text"
    assert via_parameter == "image-text-to-text"
    assert ocr == "image-to-text"
    assert image_default == "text-to-image"
    assert image_edit == "image-text-to-image"

def _write_final_result_dataset(
    *,
    dataset_root: Path,
    dataset_id: str,
    suite_id: str,
    samples: tuple[dict[str, object], ...],
    task_kind: str = "text-generation",
    input_modalities: tuple[str, ...] | None = None,
) -> None:
    dataset_root.mkdir(parents=True, exist_ok=True)
    resolved_input_modalities = input_modalities or (
        ("text",) if task_kind == "text-generation" else ("text", "image")
    )
    (dataset_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.evaluation_dataset_package.v2",
                "dataset_id": dataset_id,
                "suite_id": suite_id,
                "version": "2026-04-14",
                "sample_count": len(samples),
                "split": "validation",
                "task_kind": task_kind,
                "input_modalities": list(resolved_input_modalities),
                "profile_type": "final_result",
                "result_kind": "text",
                "extraction_mode": "heuristic_final",
                "scoring_mode": "normalized_exact_match",
                "threshold": 1.0,
                "output_schema": {},
                "ignored_paths": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (dataset_root / "samples.jsonl").write_text(
        "\n".join(
            json.dumps(
                {
                    "id": sample.get("id", str(index)),
                    "system": sample.get("system", ""),
                    "input": {
                        **(
                            dict(sample["input"])
                            if isinstance(sample.get("input"), dict)
                            else {}
                        ),
                        **(
                            {"text": str(sample["input"]["text"])}
                            if isinstance(sample.get("input"), dict)
                            and isinstance(sample["input"].get("text"), str)
                            else (
                                {"text": str(sample.get("prompt", sample.get("question", "")))}
                                if str(sample.get("prompt", sample.get("question", ""))).strip()
                                else {}
                            )
                        ),
                        **(
                            {"image_uri": str(sample["image_uri"])}
                            if isinstance(sample.get("image_uri"), str) and sample["image_uri"].strip()
                            else {}
                        ),
                    },
                    "target": sample.get("target", sample.get("expected", sample.get("answer", ""))),
                }
            )
            for index, sample in enumerate(samples, start=1)
        )
        + "\n",
        encoding="utf-8",
    )


def test_run_evaluation_returns_typed_job_and_result(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    dataset_root = tmp_path / "datasets" / "qa_smoke.dev.v1"
    _write_final_result_dataset(
        dataset_root=dataset_root,
        dataset_id="qa_smoke.dev.v1",
        suite_id="mmlu",
        samples=(
            {"prompt": "2+2?", "expected": "4"},
            {"prompt": "3+3?", "expected": "6"},
        ),
    )

    response = service.RunEvaluation(
        maintenance_pb2.RunEvaluationRequest(
            model_handle="melix-dev-text::1",
            suite_id="mmlu",
            dataset_id="qa_smoke.dev.v1",
            dataset_root=str(dataset_root),
            sample_size=2,
            parameters={"judge": "deterministic"},
        ),
        context=None,
    )

    assert response.ok is True
    metrics = {metric.name: metric.value for metric in response.results[0].metrics}
    assert response.job.schema_version == "melix.evaluation_job.v2"
    assert response.job.model_id == "melix-dev-text"
    assert response.job.dataset_id == "qa_smoke.dev.v1"
    assert response.job.parameters["judge"] == "deterministic"
    assert len(response.results) == 1
    assert response.results[0].schema_version == "melix.evaluation_result.v2"
    assert response.results[0].dataset_id == "qa_smoke.dev.v1"
    assert metrics["eval.mmlu.typed_score_mean"] == 1.0


def test_search_hub_models_passes_cursor_and_filters_to_mlx_results(tmp_path: Path) -> None:
    hub_catalog = FakeHubCatalog()
    service = build_service(tmp_path, hub_catalog=hub_catalog)

    response = service.SearchHubModels(
        maintenance_pb2.SearchHubModelsRequest(
            query="qwen",
            page_size=5,
            cursor="cursor:page-1",
            mlx_only=True,
        ),
        context=None,
    )

    assert hub_catalog.search_requests == [
        {
            "query": "qwen",
            "page_size": 5,
            "cursor": "cursor:page-1",
            "mlx_only": True,
        }
    ]
    assert response.ok is True
    assert response.next_cursor == "cursor:page-2"
    assert [model.repo_id for model in response.models] == ["mlx-community/Qwen2.5-7B-Instruct-4bit"]
    assert response.models[0].author == "mlx-community"
    assert response.models[0].pipeline_tag == "text-generation"
    assert response.models[0].tags == ["mlx", "chat"]
    assert response.models[0].downloads == 321
    assert response.models[0].likes == 12
    assert response.models[0].mlx_compatible is True


def test_get_hub_model_card_returns_normalized_payload(tmp_path: Path) -> None:
    hub_catalog = FakeHubCatalog()
    service = build_service(tmp_path, hub_catalog=hub_catalog)

    response = service.GetHubModelCard(
        maintenance_pb2.GetHubModelCardRequest(
            repo_id="mlx-community/Qwen2.5-7B-Instruct-4bit",
        ),
        context=None,
    )

    assert hub_catalog.card_requests == ["mlx-community/Qwen2.5-7B-Instruct-4bit"]
    assert response.ok is True
    assert response.card.repo_id == "mlx-community/Qwen2.5-7B-Instruct-4bit"
    assert response.card.author == "mlx-community"
    assert response.card.model_name == "Qwen2.5-7B-Instruct-4bit"
    assert response.card.summary == "MLX text-generation build"
    assert response.card.license == "apache-2.0"
    assert response.card.pipeline_tag == "text-generation"
    assert response.card.tags == ["mlx", "chat"]
    assert response.card.downloads == 321
    assert response.card.likes == 12
    assert response.card.mlx_compatible is True
    assert response.card.library_name == "transformers"
    assert response.card.sibling_files == ["README.md", "config.json", "model.safetensors"]
    assert response.card.base_models == ["Qwen/Qwen2.5-7B-Instruct"]
    assert response.card.last_modified == "2025-01-26T19:49:28Z"


def test_search_hub_models_returns_hub_catalog_errors(tmp_path: Path) -> None:
    service = build_service(
        tmp_path,
        hub_catalog=FailingHubCatalog(
            search_error=HubCatalogError(
                "hub_rate_limited",
                "Hub request failed with HTTP 429.",
                retriable=True,
            )
        ),
    )

    response = service.SearchHubModels(
        maintenance_pb2.SearchHubModelsRequest(query="qwen"),
        context=None,
    )

    assert response.ok is False
    assert response.error.code == "hub_rate_limited"
    assert response.error.message == "Hub request failed with HTTP 429."
    assert response.error.retriable is True


def test_search_hub_models_returns_generic_errors(tmp_path: Path) -> None:
    service = build_service(
        tmp_path,
        hub_catalog=FailingHubCatalog(search_error=RuntimeError("boom")),
    )

    response = service.SearchHubModels(
        maintenance_pb2.SearchHubModelsRequest(query="qwen"),
        context=None,
    )

    assert response.ok is False
    assert response.error.code == "hub_request_failed"
    assert response.error.message == "boom"
    assert response.error.retriable is False


def test_get_hub_model_card_returns_hub_catalog_errors(tmp_path: Path) -> None:
    service = build_service(
        tmp_path,
        hub_catalog=FailingHubCatalog(
            card_error=HubCatalogError(
                "not_found",
                "Hub model not found for repo_id=missing/repo.",
            )
        ),
    )

    response = service.GetHubModelCard(
        maintenance_pb2.GetHubModelCardRequest(repo_id="missing/repo"),
        context=None,
    )

    assert response.ok is False
    assert response.error.code == "not_found"
    assert response.error.message == "Hub model not found for repo_id=missing/repo."
    assert response.error.retriable is False


def test_get_hub_model_card_returns_generic_errors(tmp_path: Path) -> None:
    service = build_service(
        tmp_path,
        hub_catalog=FailingHubCatalog(card_error=RuntimeError("boom")),
    )

    response = service.GetHubModelCard(
        maintenance_pb2.GetHubModelCardRequest(repo_id="mlx-community/example"),
        context=None,
    )

    assert response.ok is False
    assert response.error.code == "hub_request_failed"
    assert response.error.message == "boom"
    assert response.error.retriable is False


def test_run_evaluation_uses_default_dataset_root_when_dataset_root_is_omitted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = build_service(tmp_path)
    dataset_root = (
        tmp_path
        / "services"
        / "mlx-worker-python"
        / "fixtures"
        / "evaluation"
        / "qa_smoke.dev.v1"
    )
    _write_final_result_dataset(
        dataset_root=dataset_root,
        dataset_id="qa_smoke.dev.v1",
        suite_id="mmlu",
        samples=(
            {"prompt": "2+2?", "expected": "4"},
        ),
    )
    monkeypatch.chdir(tmp_path)

    response = service.RunEvaluation(
        maintenance_pb2.RunEvaluationRequest(
            model_handle="melix-dev-text::1",
            suite_id="mmlu",
            dataset_id="qa_smoke.dev.v1",
            sample_size=1,
            parameters={"judge": "deterministic"},
        ),
        context=None,
    )

    assert response.ok is True
    assert response.job.dataset_id == "qa_smoke.dev.v1"
    metrics = {metric.name: metric.value for metric in response.results[0].metrics}
    assert metrics["eval.mmlu.typed_score_mean"] == 1.0


def test_run_evaluation_uses_checked_in_repo_fixture_when_dataset_root_is_omitted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = build_service(tmp_path)
    repo_root = Path(__file__).resolve().parents[3]
    fixture_root = repo_root / "services" / "mlx-worker-python" / "fixtures" / "evaluation" / "mmlu.dev.v1"

    assert fixture_root.exists() is True
    monkeypatch.chdir(repo_root)

    response = service.RunEvaluation(
        maintenance_pb2.RunEvaluationRequest(
            model_handle="melix-dev-text::1",
            suite_id="mmlu",
            dataset_id="mmlu.dev.v1",
            sample_size=2,
            parameters={"judge": "deterministic"},
        ),
        context=None,
    )

    assert response.ok is True
    assert response.job.dataset_id == "mmlu.dev.v1"
    metrics = {metric.name: metric.value for metric in response.results[0].metrics}
    assert metrics["eval.mmlu.typed_score_mean"] == 1.0


@pytest.mark.parametrize(
    ("suite_id", "dataset_id", "response_text"),
    [
        (
            "humaneval",
            "humaneval.dev.v1",
            "```python\ndef identity(x):\n    return x\n```",
        ),
        (
            "mbpp",
            "mbpp.dev.v1",
            "```python\ndef square(n):\n    return n * n\n```",
        ),
    ],
)
def test_run_evaluation_uses_checked_in_code_fixture_when_dataset_root_is_omitted(
    tmp_path: Path,
    monkeypatch,
    suite_id: str,
    dataset_id: str,
    response_text: str,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    fixture_root = repo_root / "services" / "mlx-worker-python" / "fixtures" / "evaluation" / dataset_id
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=ScriptedCodeEvalBackend((response_text,))),
        model_catalog=WorkerModelCatalog(),
    )
    loaded = registry.load_model(WorkerModelCatalog.dev_text_model())
    service = build_service(tmp_path, registry=registry)

    assert fixture_root.exists() is True
    monkeypatch.chdir(repo_root)

    response = service.RunEvaluation(
        maintenance_pb2.RunEvaluationRequest(
            model_handle=loaded.handle,
            suite_id=suite_id,
            dataset_id=dataset_id,
            sample_size=1,
            code_exec_policy="sandboxed",
        ),
        context=None,
    )

    metrics = {metric.name: metric.value for metric in response.results[0].metrics}

    assert response.ok is True
    assert response.job.dataset_id == dataset_id
    assert metrics[f"eval.{suite_id}.typed_score_mean"] == 1.0
    assert metrics[f"eval.{suite_id}.code_exec_pass_count"] == 1.0
    assert metrics[f"eval.{suite_id}.code_exec_fail_count"] == 0.0


def test_run_evaluation_uses_checked_in_multimodal_fixture_when_dataset_root_is_omitted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    fixture_root = repo_root / "services" / "mlx-worker-python" / "fixtures" / "evaluation" / "mmlu.vision.dev.v1"

    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        return SimpleNamespace(config=SimpleNamespace(model_type="gemma4")), SimpleNamespace()

    def fake_apply_chat_template(processor, config, prompt: str, num_images: int = 0, **kwargs):
        _ = processor
        _ = config
        _ = kwargs
        return f"formatted::{prompt}::images={num_images}"

    captured_prompts: list[str] = []
    captured_image_paths: list[str] = []

    def fake_stream_generate(model, processor, prompt: str, image=None, **kwargs):
        _ = model
        _ = processor
        _ = kwargs
        captured_prompts.append(prompt)
        captured_image_paths.extend(list(image or []))
        yield SimpleNamespace(
            text="Answer: red",
            prompt_tokens=12,
            generation_tokens=1,
            prompt_tps=42.0,
            generation_tps=21.0,
            peak_memory=2048.0,
        )

    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=DeterministicTextBackend()),
        mlx_vlm_runtime=MLXVLMRuntime(
            backend=AutoMLXVLMBackend(
                load_fn=fake_load,
                stream_generate_fn=fake_stream_generate,
                apply_chat_template_fn=fake_apply_chat_template,
            )
        ),
        model_catalog=WorkerModelCatalog(),
    )
    service = build_service(tmp_path, registry=registry)
    loaded = registry.load_model(
        common_pb2.ModelSpec(
            model_id="google/paligemma2-3b-ft-docci-448",
            model_path="google/paligemma2-3b-ft-docci-448",
            model_kind="vlm",
            revision="main",
            tokenizer_hash="hf.google.paligemma2-3b-ft-docci-448",
            quant_profile_id="q8",
            parser_mode="text",
            reasoning_mode="off",
            max_context=4096,
            ext={
                "melix.vlm.backend_id": "mlx_vlm",
                "vision_family_id": "paligemma-v1",
                "vision_prompt_profile_id": "paligemma-caption-v1",
                "vision_tokenization_mode": "prefix",
                "vision_max_images_per_prompt": "1",
                "vision_supports_tool_calls": "false",
                "melix.multimodal_adapter_hash": "vision-family-paligemma-v1",
            },
        )
    )

    assert fixture_root.exists() is True
    monkeypatch.chdir(repo_root)

    response = service.RunEvaluation(
        maintenance_pb2.RunEvaluationRequest(
            model_handle=loaded.handle,
            suite_id="mmlu",
            dataset_id="mmlu.vision.dev.v1",
            sample_size=1,
            task_kind="image-text-to-text",
        ),
        context=None,
    )

    assert response.ok is True
    assert response.job.dataset_id == "mmlu.vision.dev.v1"
    assert response.job.task_kind == "image-text-to-text"
    assert captured_prompts
    assert "Return only the final short answer." in captured_prompts[0]
    assert "What color is the square?" in captured_prompts[0]
    assert captured_image_paths
    assert Path(captured_image_paths[0]).suffix == ".ppm"


def test_run_evaluation_rejects_text_generation_task_kind_for_multimodal_fixture(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    fixture_root = repo_root / "services" / "mlx-worker-python" / "fixtures" / "evaluation" / "mmlu.vision.dev.v1"

    service = build_service(tmp_path)
    loaded = service._core._registry.load_model(WorkerModelCatalog.dev_text_model())

    assert fixture_root.exists() is True
    monkeypatch.chdir(repo_root)

    response = service.RunEvaluation(
        maintenance_pb2.RunEvaluationRequest(
            model_handle=loaded.handle,
            suite_id="mmlu",
            dataset_id="mmlu.vision.dev.v1",
            sample_size=1,
            task_kind="text-generation",
        ),
        context=None,
    )

    assert response.ok is False
    assert response.error.code == "invalid_argument"
    assert "requires image inputs" in response.error.message


def test_run_evaluation_uses_checked_in_imagenette_fixture_when_dataset_root_is_omitted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    fixture_root = repo_root / "services" / "mlx-worker-python" / "fixtures" / "evaluation" / "imagenette.dev.v1"

    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        return SimpleNamespace(config=SimpleNamespace(model_type="gemma4")), SimpleNamespace()

    def fake_apply_chat_template(processor, config, prompt: str, num_images: int = 0, **kwargs):
        _ = processor
        _ = config
        _ = kwargs
        return f"formatted::{prompt}::images={num_images}"

    captured_prompts: list[str] = []
    captured_image_paths: list[str] = []

    def fake_stream_generate(model, processor, prompt: str, image=None, **kwargs):
        _ = model
        _ = processor
        _ = kwargs
        captured_prompts.append(prompt)
        captured_image_paths.extend(list(image or []))
        yield SimpleNamespace(
            text="Answer: tench",
            prompt_tokens=18,
            generation_tokens=2,
            prompt_tps=42.0,
            generation_tps=21.0,
            peak_memory=2048.0,
        )

    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=DeterministicTextBackend()),
        mlx_vlm_runtime=MLXVLMRuntime(
            backend=AutoMLXVLMBackend(
                load_fn=fake_load,
                stream_generate_fn=fake_stream_generate,
                apply_chat_template_fn=fake_apply_chat_template,
            )
        ),
        model_catalog=WorkerModelCatalog(),
    )
    service = build_service(tmp_path, registry=registry)
    loaded = registry.load_model(
        common_pb2.ModelSpec(
            model_id="google/paligemma2-3b-ft-docci-448",
            model_path="google/paligemma2-3b-ft-docci-448",
            model_kind="vlm",
            revision="main",
            tokenizer_hash="hf.google.paligemma2-3b-ft-docci-448",
            quant_profile_id="q8",
            parser_mode="text",
            reasoning_mode="off",
            max_context=4096,
            ext={
                "melix.vlm.backend_id": "mlx_vlm",
                "vision_family_id": "paligemma-v1",
                "vision_prompt_profile_id": "paligemma-caption-v1",
                "vision_tokenization_mode": "prefix",
                "vision_max_images_per_prompt": "1",
                "vision_supports_tool_calls": "false",
                "melix.multimodal_adapter_hash": "vision-family-paligemma-v1",
            },
        )
    )

    assert fixture_root.exists() is True
    monkeypatch.chdir(repo_root)

    response = service.RunEvaluation(
        maintenance_pb2.RunEvaluationRequest(
            model_handle=loaded.handle,
            suite_id="imagenette",
            dataset_id="imagenette.dev.v1",
            sample_size=1,
            task_kind="image-text-to-text",
        ),
        context=None,
    )

    assert response.ok is True
    assert response.job.dataset_id == "imagenette.dev.v1"
    assert response.job.task_kind == "image-text-to-text"
    metrics = {metric.name: metric.value for metric in response.results[0].metrics}
    assert metrics["eval.imagenette.typed_score_mean"] == 1.0
    assert captured_prompts
    assert "Classify the main subject in this image." in captured_prompts[0]
    assert "garbage truck" in captured_prompts[0]
    assert captured_image_paths
    assert Path(captured_image_paths[0]).suffix == ".jpg"


def test_run_evaluation_accepts_dataset_root_from_parameters_when_field_is_omitted(
    tmp_path: Path,
) -> None:
    service = build_service(tmp_path)
    dataset_root = tmp_path / "datasets" / "qa_smoke.dev.v1"
    _write_final_result_dataset(
        dataset_root=dataset_root,
        dataset_id="qa_smoke.dev.v1",
        suite_id="mmlu",
        samples=(
            {"prompt": "3+4?", "expected": "7"},
        ),
    )

    response = service.RunEvaluation(
        maintenance_pb2.RunEvaluationRequest(
            model_handle="melix-dev-text::1",
            suite_id="mmlu",
            dataset_id="ignored.dev.v1",
            sample_size=1,
            parameters={
                "dataset_root": str(dataset_root),
                "judge": "deterministic",
            },
        ),
        context=None,
    )

    assert response.ok is True
    assert response.job.dataset_id == "qa_smoke.dev.v1"
    assert response.job.parameters["dataset_root"] == str(dataset_root)
    metrics = {metric.name: metric.value for metric in response.results[0].metrics}
    assert metrics["eval.mmlu.typed_score_mean"] == 1.0


def test_run_evaluation_returns_typed_error_for_dataset_suite_mismatch(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    dataset_root = tmp_path / "datasets" / "qa_smoke.dev.v1"
    _write_final_result_dataset(
        dataset_root=dataset_root,
        dataset_id="qa_smoke.dev.v1",
        suite_id="mmlu",
        samples=(
            {"prompt": "2+2?", "expected": "4"},
        ),
    )

    response = service.RunEvaluation(
        maintenance_pb2.RunEvaluationRequest(
            model_handle="melix-dev-text::1",
            suite_id="unsupported-suite",
            dataset_id="qa_smoke.dev.v1",
            dataset_root=str(dataset_root),
            sample_size=1,
        ),
        context=None,
    )

    assert response.ok is False
    assert response.error.code == "invalid_argument"
    assert "Dataset suite mismatch" in response.error.message


def test_run_evaluation_materializes_local_csv_source_from_request(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    source_path = tmp_path / "capital.csv"
    with source_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["system_prompt", "question", "gold_answer", "sample_key"])
        writer.writeheader()
        writer.writerow(
            {
                "system_prompt": "Return only the final answer.",
                "question": "Capital of France?",
                "gold_answer": "Paris",
                "sample_key": "capital-1",
            }
        )

    request = maintenance_pb2.RunEvaluationRequest(
        model_handle="melix-dev-text::1",
        suite_id="capital",
        dataset_id="capital.dev.v1",
        sample_size=1,
        parameters={"judge": "deterministic"},
    )
    request.source.local_csv.path = str(source_path)
    request.field_mapping.system_path = "system_prompt"
    request.field_mapping.input_text_path = "question"
    request.field_mapping.target_path = "gold_answer"
    request.field_mapping.sample_id_path = "sample_key"
    request.profile.profile_type = "final_result"
    request.profile.result_kind = "text"
    request.profile.extraction_mode = "heuristic_final"
    request.profile.scoring_mode = "normalized_exact_match"
    request.profile.threshold = 1.0

    response = service.RunEvaluation(request, context=None)

    assert response.ok is True
    assert response.job.dataset_id == "capital.dev.v1"
    assert response.job.parameters["evaluation_source_kind"] == "csv"
    materialized_root = Path(response.job.parameters["evaluation_materialized_dataset_root"])
    assert (materialized_root / "manifest.json").exists() is True
    assert (materialized_root / "samples.jsonl").exists() is True


def test_run_evaluation_materializes_hf_source_from_request(tmp_path: Path) -> None:
    service = build_service(tmp_path, benchmark_fetcher=FakeBenchmarkHFDatasetFetcher())
    request = maintenance_pb2.RunEvaluationRequest(
        model_handle="melix-dev-text::1",
        suite_id="dolly",
        dataset_id="dolly.dev.v1",
        sample_size=1,
        parameters={"judge": "deterministic"},
    )
    request.source.hf_dataset.dataset_path = "databricks/databricks-dolly-15k"
    request.source.hf_dataset.dataset_revision = "main"
    request.source.hf_dataset.split = "train"
    request.field_mapping.input_text_path = "instruction"
    request.field_mapping.target_path = "response"
    request.profile.profile_type = "final_result"
    request.profile.result_kind = "text"
    request.profile.extraction_mode = "heuristic_final"
    request.profile.scoring_mode = "normalized_exact_match"
    request.profile.threshold = 1.0

    response = service.RunEvaluation(request, context=None)

    assert response.ok is True
    assert response.job.dataset_id == "dolly.dev.v1"
    assert response.job.parameters["evaluation_source_kind"] == "hf_dataset"
    materialized_root = Path(response.job.parameters["evaluation_materialized_dataset_root"])
    assert (materialized_root / "manifest.json").exists() is True
    assert (materialized_root / "samples.jsonl").exists() is True


def test_run_evaluation_materializes_local_jsonl_source_for_compare_from_request(
    tmp_path: Path,
) -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=DeterministicTextBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    base_loaded_model = registry.load_model(
        common_pb2.ModelSpec(
            model_id="melix-dev-text",
            model_path=str(tmp_path / "models" / "melix-dev-text"),
            model_kind="text",
            revision="test",
            tokenizer_hash="tok-test",
            quant_profile_id="test",
            parser_mode="text",
            reasoning_mode="off",
        )
    )
    _ = registry.load_model(
        common_pb2.ModelSpec(
            model_id="melix-dev-text-lora",
            model_path=str(tmp_path / "models" / "melix-dev-text-lora"),
            model_kind="text",
            revision="test",
            tokenizer_hash="tok-test",
            quant_profile_id="test",
            parser_mode="text",
            reasoning_mode="off",
        )
    )
    service = build_service(tmp_path, registry=registry)
    source_path = tmp_path / "capital.jsonl"
    source_path.write_text(
        json.dumps(
            {
                "system_prompt": "Return only the final answer.",
                "prompt": "Capital of France?",
                "expected": "Paris",
                "sample_id": "capital-1",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    request = maintenance_pb2.RunEvaluationRequest(
        model_handle=base_loaded_model.handle,
        suite_id="capital",
        dataset_id="capital.dev.v1",
        sample_size=1,
        parameters={
            "judge": "deterministic",
            "compare_mode": "base_vs_targets",
            "compare_target_model_ids": "melix-dev-text-lora",
        },
    )
    request.source.local_jsonl.path = str(source_path)
    request.field_mapping.system_path = "system_prompt"
    request.field_mapping.input_text_path = "prompt"
    request.field_mapping.target_path = "expected"
    request.field_mapping.sample_id_path = "sample_id"
    request.profile.profile_type = "final_result"
    request.profile.result_kind = "text"
    request.profile.extraction_mode = "heuristic_final"
    request.profile.scoring_mode = "normalized_exact_match"
    request.profile.threshold = 1.0

    response = service.RunEvaluation(request, context=None)

    assert response.ok is True
    assert response.job.parameters["compare_mode"] == "base_vs_targets"
    assert response.job.parameters["evaluation_source_kind"] == "jsonl"
    materialized_root = Path(response.job.parameters["evaluation_materialized_dataset_root"])
    assert (materialized_root / "manifest.json").exists() is True
    assert (materialized_root / "samples.jsonl").exists() is True
    assert len(response.results) == 1


def test_run_evaluation_defaults_structured_threshold_to_one_when_request_omits_it(
    tmp_path: Path,
) -> None:
    service = build_service(tmp_path)
    source_path = tmp_path / "capital.csv"
    with source_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["system_prompt", "question", "gold_answer", "sample_key"])
        writer.writeheader()
        writer.writerow(
            {
                "system_prompt": "Return only the final answer.",
                "question": "Capital of France?",
                "gold_answer": "Paris",
                "sample_key": "capital-1",
            }
        )

    request = maintenance_pb2.RunEvaluationRequest(
        model_handle="melix-dev-text::1",
        suite_id="capital",
        dataset_id="capital.dev.v1",
        sample_size=1,
        parameters={"judge": "deterministic"},
    )
    request.source.local_csv.path = str(source_path)
    request.field_mapping.system_path = "system_prompt"
    request.field_mapping.input_text_path = "question"
    request.field_mapping.target_path = "gold_answer"
    request.field_mapping.sample_id_path = "sample_key"
    request.profile.profile_type = "final_result"
    request.profile.result_kind = "text"
    request.profile.extraction_mode = "strict_full_response"
    request.profile.scoring_mode = "normalized_exact_match"

    response = service.RunEvaluation(request, context=None)

    materialized_root = Path(response.job.parameters["evaluation_materialized_dataset_root"])
    manifest = json.loads((materialized_root / "manifest.json").read_text(encoding="utf-8"))

    assert response.ok is True
    assert manifest["threshold"] == 1.0


def test_run_bench_persists_job_manifest_and_per_suite_results(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    events = list(
        service.RunBench(
            maintenance_pb2.RunBenchRequest(
                model_handle="melix-dev-text::1",
                suites=["smoke", "latency"],
                parameters={
                    "context_lengths": "16,32",
                    "batch_sizes": "1,2",
                    "repeats": "2",
                    "cache_profile": "partial_prefix",
                    "generation_length": "16",
                    "reasoning_mode": "step-by-step",
                    "structured_output_mode": "json",
                },
            ),
            context=None,
        )
    )

    report_path = Path(events[-1].completed.report_path)
    run_dir = tmp_path / "model-ops" / "bench" / "runs" / events[0].started.job_id
    bench_parameters = {
        "context_lengths": "16,32",
        "batch_sizes": "1,2",
        "repeats": "2",
        "cache_profile": "partial_prefix",
        "generation_length": "16",
        "reasoning_mode": "step-by-step",
        "structured_output_mode": "json",
    }
    job_manifest = run_dir / "bench-job.json"
    summary_manifest = run_dir / "bench-summary.json"
    context_rows_path = run_dir / "bench-context-rows.jsonl"
    batch_rows_path = run_dir / "bench-batch-rows.jsonl"
    smoke_result = run_dir / "bench-result-smoke.json"
    latency_result = run_dir / "bench-result-latency.json"

    assert job_manifest.exists() is True
    assert summary_manifest.exists() is True
    assert context_rows_path.exists() is True
    assert batch_rows_path.exists() is True
    assert smoke_result.exists() is True
    assert latency_result.exists() is True
    assert report_path.parent == run_dir

    job_payload = json.loads(job_manifest.read_text(encoding="utf-8"))
    summary_payload = json.loads(summary_manifest.read_text(encoding="utf-8"))
    context_rows = [
        json.loads(line)
        for line in context_rows_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    batch_rows = [
        json.loads(line)
        for line in batch_rows_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    smoke_payload = json.loads(smoke_result.read_text(encoding="utf-8"))
    latency_payload = json.loads(latency_result.read_text(encoding="utf-8"))
    report_markdown = report_path.read_text(encoding="utf-8")
    expected_metrics = {
        event.metric.name: event.metric.value
        for event in events
        if event.HasField("metric")
    }
    expected_units = {
        event.metric.name: event.metric.unit
        for event in events
        if event.HasField("metric")
    }

    expected_job = build_serving_benchmark_job(
        job_id=events[0].started.job_id,
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="",
        suites=("smoke", "latency"),
        context_lengths=tuple(job_payload["context_lengths"]),
        generation_length=job_payload["generation_length"],
        batch_sizes=tuple(job_payload["batch_sizes"]),
        repeats=job_payload["repeats"],
        cache_profile=job_payload["cache_profile"],
        reasoning_mode=job_payload["reasoning_mode"],
        structured_output_mode=job_payload["structured_output_mode"],
        request_p50_ms=job_payload["request_p50_ms"],
        request_p95_ms=job_payload["request_p95_ms"],
        parameters=bench_parameters,
        status="completed",
        output_dir=str(run_dir),
        created_at_unix_ms=job_payload["created_at_unix_ms"],
        updated_at_unix_ms=job_payload["updated_at_unix_ms"],
        suite_metadata=job_payload["suite_metadata"],
    )
    expected_results = {
        result.suite: result.to_dict()
        for result in build_serving_benchmark_results(
            job_id=events[0].started.job_id,
            metrics=expected_metrics,
            units=expected_units,
            report_path=str(report_path),
            report_markdown=report_markdown,
        )
    }

    assert job_payload == expected_job.to_dict()
    assert summary_payload == job_payload
    assert job_payload["created_at_unix_ms"] > 0
    assert job_payload["updated_at_unix_ms"] >= job_payload["created_at_unix_ms"]
    assert job_payload["suite_metadata"]["smoke"]["dataset_path"] == "HuggingFaceH4/ultrachat_200k"
    assert job_payload["suite_metadata"]["latency"]["dataset_path"] == "databricks/databricks-dolly-15k"
    assert smoke_payload == expected_results["smoke"]
    assert latency_payload == expected_results["latency"]
    assert len(context_rows) == 24
    assert len(batch_rows) == 24
    assert {row["cache_profile"] for row in context_rows} == {"partial_prefix"}
    assert {row["batch_size"] for row in batch_rows} == {1}
    assert all(row["speedup_vs_batch_1"] == 1.0 for row in batch_rows)
    assert job_payload["request_p95_ms"] >= job_payload["request_p50_ms"]


def test_run_bench_records_curated_hf_suite_cache_hits_across_runs(tmp_path: Path) -> None:
    fetcher = FakeBenchmarkHFDatasetFetcher()
    service = build_service(tmp_path, benchmark_fetcher=fetcher)

    first_events = list(
        service.RunBench(
            maintenance_pb2.RunBenchRequest(
                model_handle="melix-dev-text::1",
                suites=["smoke"],
            ),
            context=None,
        )
    )
    second_events = list(
        service.RunBench(
            maintenance_pb2.RunBenchRequest(
                model_handle="melix-dev-text::1",
                suites=["smoke"],
            ),
            context=None,
        )
    )

    first_job = json.loads(
        (tmp_path / "model-ops" / "bench" / "runs" / first_events[0].started.job_id / "bench-job.json").read_text(
            encoding="utf-8"
        )
    )
    second_job = json.loads(
        (tmp_path / "model-ops" / "bench" / "runs" / second_events[0].started.job_id / "bench-job.json").read_text(
            encoding="utf-8"
        )
    )

    assert first_job["suite_metadata"]["smoke"]["cache_hit"] is False
    assert second_job["suite_metadata"]["smoke"]["cache_hit"] is True


def test_run_bench_matrix_returns_summary_rows_and_persists_matrix_artifacts(tmp_path: Path) -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=RecordingBenchmarkBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    service = build_service(tmp_path, registry=registry)

    response = service.RunBenchMatrix(
        maintenance_pb2.RunBenchMatrixRequest(
            model_handle="melix-dev-text::1",
            task_kind="text-generation",
            suite_ids=["smoke"],
            context_lengths=[1024, 256],
            generation_lengths=[128],
            batch_sizes=[2],
            cache_profiles=["cold"],
            reasoning_modes=["enabled"],
            structured_output_modes=["plain_text"],
            concurrency_levels=[1],
            repeats=2,
            requests=4,
        ),
        context=None,
    )

    assert response.job.job_id.startswith("model-ops-")
    assert response.job.schema_version == "melix.benchmark_matrix_job.v1"
    assert response.job.model_id == "melix-dev-text"
    assert response.job.task_kind == "text-generation"
    assert response.job.suite_ids == ["smoke"]
    assert response.job.benchmark_mode == "matrix"
    assert response.job.status == "completed"
    assert len(response.summary_rows) == 2
    assert [row.context_length for row in response.summary_rows] == [256, 1024]
    assert all(row.requests == 4 for row in response.summary_rows)
    assert all(row.duration_seconds == 0 for row in response.summary_rows)
    assert all(row.success_rate == 1.0 for row in response.summary_rows)
    assert all(row.request_latency_mean_ms > 0 for row in response.summary_rows)
    assert all(row.throughput_requests_per_second > 0 for row in response.summary_rows)

    run_dir = tmp_path / "model-ops" / "bench" / "matrix-runs" / response.job.job_id
    assert (run_dir / "bench-matrix-job.json").exists() is True
    assert (run_dir / "bench-matrix-summary.jsonl").exists() is True
    assert (run_dir / "bench-matrix-summary.csv").exists() is True
    assert (run_dir / "bench-matrix-requests.jsonl").exists() is True
    assert (run_dir / "bench-matrix-requests.csv").exists() is True

    job_payload = json.loads((run_dir / "bench-matrix-job.json").read_text(encoding="utf-8"))
    summary_rows = [
        json.loads(line)
        for line in (run_dir / "bench-matrix-summary.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    request_rows = [
        json.loads(line)
        for line in (run_dir / "bench-matrix-requests.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert job_payload["benchmark_mode"] == "matrix"
    assert job_payload["suite_ids"] == ["smoke"]
    assert [row["context_length"] for row in summary_rows] == [256, 1024]
    assert len(request_rows) == 8
    assert {row["cell_id"] for row in request_rows} == {"cell-1", "cell-2"}
    assert all(row["status"] == "completed" for row in request_rows)


def test_run_bench_matrix_rejects_invalid_load_budget(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    with pytest.raises(ModelOperationError) as error:
        service._core.bench_matrix_response(
            maintenance_pb2.RunBenchMatrixRequest(
                model_handle="melix-dev-text::1",
                suite_ids=["smoke"],
                context_lengths=[1024],
                generation_lengths=[128],
                batch_sizes=[1],
                cache_profiles=["cold"],
                reasoning_modes=["default"],
                structured_output_modes=["plain_text"],
                concurrency_levels=[1],
            )
        )

    assert error.value.code == "invalid_argument"
    assert error.value.details == {"requests": 0, "duration_seconds": 0}


def test_run_bench_matrix_marks_failed_queue_state_for_unsupported_task_kind(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    with pytest.raises(ModelOperationError) as error:
        service._core.bench_matrix_response(
            maintenance_pb2.RunBenchMatrixRequest(
                model_handle="melix-dev-text::1",
                task_kind="image-text-to-image",
                suite_ids=["smoke"],
                context_lengths=[1024],
                generation_lengths=[128],
                batch_sizes=[1],
                cache_profiles=["cold"],
                reasoning_modes=["default"],
                structured_output_modes=["plain_text"],
                concurrency_levels=[1],
                requests=1,
            )
        )

    assert error.value.code == "unsupported_task_family"
    queue_records = list((tmp_path / "model-ops" / "bench" / "matrix-queue").glob("*.json"))
    assert len(queue_records) == 1
    queue_payload = json.loads(queue_records[0].read_text(encoding="utf-8"))
    assert queue_payload["status"] == "failed"


def test_run_bench_matrix_records_failed_request_rows_when_sampling_raises(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service._core._measure_benchmark_matrix_sample = lambda **kwargs: (_ for _ in ()).throw(  # type: ignore[method-assign]
        ModelOperationError(code="benchmark_failed", message="forced failure")
    )

    response = service._core.bench_matrix_response(
        maintenance_pb2.RunBenchMatrixRequest(
            model_handle="melix-dev-text::1",
            task_kind="text-generation",
            suite_ids=["smoke"],
            context_lengths=[1024],
            generation_lengths=[128],
            batch_sizes=[1],
            cache_profiles=["cold"],
            reasoning_modes=["default"],
            structured_output_modes=["plain_text"],
            concurrency_levels=[1],
            requests=1,
        )
    )

    assert response.job.status == "completed"
    assert len(response.summary_rows) == 1
    assert response.summary_rows[0].success_rate == 0.0
    run_dir = tmp_path / "model-ops" / "bench" / "matrix-runs" / response.job.job_id
    request_rows = [
        json.loads(line)
        for line in (run_dir / "bench-matrix-requests.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(request_rows) == 1
    assert request_rows[0]["status"] == "failed"
    assert request_rows[0]["error_code"] == "benchmark_failed"


def test_benchmark_matrix_task_kind_resolution_prefers_runtime_metadata_then_model_kind() -> None:
    text_backed_loaded = SimpleNamespace(
        runtime_model={"metadata": {"melix.vlm.execution_mode": "text_backed"}},
        spec=common_pb2.ModelSpec(model_kind="vlm"),
    )
    ocr_loaded = SimpleNamespace(runtime_model={}, spec=common_pb2.ModelSpec(model_kind="ocr"))
    vlm_loaded = SimpleNamespace(runtime_model={}, spec=common_pb2.ModelSpec(model_kind="vlm"))
    text_loaded = SimpleNamespace(runtime_model={}, spec=common_pb2.ModelSpec(model_kind="text"))

    assert MaintenanceCore._resolved_benchmark_matrix_task_kind(
        request=maintenance_pb2.RunBenchMatrixRequest(),
        loaded_model=text_backed_loaded,
    ) == "text-generation"
    assert MaintenanceCore._resolved_benchmark_matrix_task_kind(
        request=maintenance_pb2.RunBenchMatrixRequest(),
        loaded_model=ocr_loaded,
    ) == "image-to-text"
    assert MaintenanceCore._resolved_benchmark_matrix_task_kind(
        request=maintenance_pb2.RunBenchMatrixRequest(),
        loaded_model=vlm_loaded,
    ) == "image-text-to-text"
    assert MaintenanceCore._resolved_benchmark_matrix_task_kind(
        request=maintenance_pb2.RunBenchMatrixRequest(),
        loaded_model=text_loaded,
    ) == "text-generation"


def test_benchmark_matrix_request_count_and_sample_validation_cover_duration_and_error_paths(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    loaded_model = service._core._registry.load_model(WorkerModelCatalog.dev_vlm_model())
    suite = SimpleNamespace(title="Smoke", suite_id="smoke")

    assert MaintenanceCore._benchmark_matrix_request_count(
        requests=0,
        duration_seconds=3,
        repeats=2,
        concurrency_level=2,
    ) == 6

    with pytest.raises(ModelOperationError) as missing_case_error:
        service._core._measure_benchmark_matrix_sample(
            loaded_model=loaded_model,
            suite=suite,
            case=None,
            task_kind="image-text-to-text",
            context_length=512,
            generation_length=64,
            batch_size=1,
            repeat_index=0,
            cache_profile="cold",
            reasoning_mode="default",
            structured_output_mode="plain_text",
        )

    assert missing_case_error.value.code == "benchmark_failed"

    with pytest.raises(ModelOperationError) as unsupported_error:
        service._core._measure_benchmark_matrix_sample(
            loaded_model=loaded_model,
            suite=suite,
            case=SimpleNamespace(prompt="prompt"),
            task_kind="image-text-to-image",
            context_length=512,
            generation_length=64,
            batch_size=1,
            repeat_index=0,
            cache_profile="cold",
            reasoning_mode="default",
            structured_output_mode="plain_text",
        )

    assert unsupported_error.value.code == "unsupported_task_family"


def test_run_bench_matrix_supports_vlm_task_families(tmp_path: Path) -> None:
    image_path = tmp_path / "doc-image-1.txt"
    image_path.write_text("benchmark vision sample", encoding="utf-8")

    class LocalImageBenchmarkFetcher(FakeBenchmarkHFDatasetFetcher):
        def __call__(self, endpoint: str, params: dict[str, str]) -> dict[str, object]:
            dataset = params.get("dataset", "")
            if dataset == "huggingface/documentation-images":
                if endpoint == "rows":
                    return {"rows": [{"row": {"image": {"src": str(image_path)}}}]}
                return {"splits": [{"dataset": dataset, "config": "default", "split": "train"}]}
            return super().__call__(endpoint, params)

    registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
    core = MaintenanceCore(
        registry,
        jobs_root=tmp_path / "model-ops",
        benchmark_suite_catalog=BenchmarkSuiteCatalog(
            hf_dataset_fetcher=LocalImageBenchmarkFetcher()
        ),
    )
    loaded = registry.load_model(WorkerModelCatalog.dev_vlm_model())
    service = WorkerMaintenanceService(registry, jobs_root=tmp_path / "model-ops")
    service._core = core

    response = service.RunBenchMatrix(
        maintenance_pb2.RunBenchMatrixRequest(
            model_handle=loaded.handle,
            task_kind="image-text-to-text",
            source_repo="unsloth/gemma-4-E4B-it-MLX-8bit",
            suite_ids=["smoke"],
            context_lengths=[512],
            generation_lengths=[64],
            batch_sizes=[1],
            cache_profiles=["cold"],
            reasoning_modes=["default"],
            structured_output_modes=["plain_text"],
            concurrency_levels=[1],
            repeats=1,
            requests=1,
        ),
        context=None,
    )

    assert response.job.task_kind == "image-text-to-text"
    assert len(response.summary_rows) == 1
    assert response.summary_rows[0].task_kind == "image-text-to-text"
    assert response.summary_rows[0].ttft_mean_ms > 0


def test_run_bench_persists_completed_queue_state(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    events = list(
        service.RunBench(
            maintenance_pb2.RunBenchRequest(
                model_handle="melix-dev-text::1",
                suites=["smoke", "latency"],
            ),
            context=None,
        )
    )

    job_id = events[0].started.job_id
    queue_record = tmp_path / "model-ops" / "bench" / "queue" / f"{job_id}.json"
    payload = json.loads(queue_record.read_text(encoding="utf-8"))

    assert payload["job_kind"] == "benchmark"
    assert payload["status"] == "completed"
    assert payload["model_id"] == "melix-dev-text"
    assert payload["suite_ids"] == ["smoke", "latency"]
    assert payload["started_at_unix_ms"] > 0
    assert payload["completed_at_unix_ms"] > 0


def test_bench_events_support_text_generation_metrics_for_text_backed_gemma4_vlm(tmp_path: Path) -> None:
    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        return SimpleNamespace(config=SimpleNamespace(model_type="gemma4")), SimpleNamespace()

    def fake_apply_chat_template(processor, config, prompt: str, num_images: int = 0, **kwargs):
        _ = processor
        _ = config
        _ = kwargs
        return f"formatted::{prompt}::images={num_images}"

    def fake_stream_generate(model, processor, prompt: str, image=None, **kwargs):
        _ = model
        _ = processor
        _ = kwargs
        _ = image
        assert "[context_length=" in prompt
        assert ";batch_size=1]" in prompt
        yield SimpleNamespace(
            text="gemma",
            prompt_tokens=16,
            generation_tokens=1,
            prompt_tps=42.0,
            generation_tps=21.0,
            peak_memory=2048.0,
        )

    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=DeterministicTextBackend()),
        mlx_vlm_runtime=MLXVLMRuntime(
            backend=AutoMLXVLMBackend(
                load_fn=fake_load,
                stream_generate_fn=fake_stream_generate,
                apply_chat_template_fn=fake_apply_chat_template,
            )
        ),
        model_catalog=WorkerModelCatalog(),
    )
    service = build_service(tmp_path, registry=registry)
    loaded = registry.load_model(imported_gemma4_text_backed_model())

    events = list(
        service._core.bench_events(
            maintenance_pb2.RunBenchRequest(
                model_handle=loaded.handle,
                suites=["smoke"],
                task_kind="text-generation",
                source_repo="unsloth/gemma-4-E4B-it-MLX-8bit",
            )
        )
    )

    metric_names = [
        event.metric.name
        for event in events
        if event.HasField("metric")
    ]
    assert "bench.smoke.ttft_ms" in metric_names
    assert "bench.smoke.tokens_per_second" in metric_names

    report_event = next(event for event in events if event.HasField("completed"))
    report_content = Path(report_event.completed.report_path).read_text(encoding="utf-8")
    assert "task_kind: text-generation" in report_content
    assert "source_repo: unsloth/gemma-4-E4B-it-MLX-8bit" in report_content


def test_bench_events_vlm_mode_produces_vlm_metrics(tmp_path: Path) -> None:
    image_path = tmp_path / "doc-image-1.txt"
    image_path.write_text("benchmark vision sample", encoding="utf-8")

    class LocalImageBenchmarkFetcher(FakeBenchmarkHFDatasetFetcher):
        def __call__(self, endpoint: str, params: dict[str, str]) -> dict[str, object]:
            dataset = params.get("dataset", "")
            if dataset == "huggingface/documentation-images":
                if endpoint == "rows":
                    return {"rows": [{"row": {"image": {"src": str(image_path)}}}]}
                return {"splits": [{"dataset": dataset, "config": "default", "split": "train"}]}
            return super().__call__(endpoint, params)

    registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
    core = MaintenanceCore(
        registry,
        jobs_root=tmp_path / "model-ops",
        benchmark_suite_catalog=BenchmarkSuiteCatalog(
            hf_dataset_fetcher=LocalImageBenchmarkFetcher()
        ),
    )

    events = list(
        core.bench_events(
            maintenance_pb2.RunBenchRequest(
                model_handle="melix-dev-vlm::1",
                suites=["smoke"],
                parameters={"benchmark_mode": "vlm"},
            )
        )
    )

    metric_names = [
        event.metric.name
        for event in events
        if event.HasField("metric")
    ]
    assert "bench.smoke.image_ttft_ms" in metric_names
    assert "bench.smoke.vlm_tokens_per_second" in metric_names
    assert "bench.smoke.ttft_ms" not in metric_names

    report_event = next(event for event in events if event.HasField("completed"))
    report_content = Path(report_event.completed.report_path).read_text(encoding="utf-8")
    assert "task_kind: image-text-to-text" in report_content


def test_bench_events_vlm_latency_suite_produces_percentile_metrics(tmp_path: Path) -> None:
    image_path = tmp_path / "doc-image-1.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nbenchmark")

    class LocalImageBenchmarkFetcher(FakeBenchmarkHFDatasetFetcher):
        def __call__(self, endpoint: str, params: dict[str, str]) -> dict[str, object]:
            dataset = params.get("dataset", "")
            if dataset == "huggingface/documentation-images":
                if endpoint == "rows":
                    return {"rows": [{"row": {"image": {"src": str(image_path)}}}]}
                return {"splits": [{"dataset": dataset, "config": "default", "split": "validation"}]}
            return super().__call__(endpoint, params)

    core = MaintenanceCore(
        WorkerRegistry(model_catalog=WorkerModelCatalog()),
        jobs_root=tmp_path / "model-ops",
        benchmark_suite_catalog=BenchmarkSuiteCatalog(
            hf_dataset_fetcher=LocalImageBenchmarkFetcher()
        ),
    )

    events = list(
        core.bench_events(
            maintenance_pb2.RunBenchRequest(
                model_handle="melix-dev-vlm::1",
                suites=["latency"],
                parameters={"benchmark_mode": "vlm"},
            )
        )
    )

    metric_names = [event.metric.name for event in events if event.HasField("metric")]
    assert "bench.latency.image_p50_ms" in metric_names
    assert "bench.latency.image_p95_ms" in metric_names


def test_run_evaluation_supports_relative_image_paths_with_mlx_vlm_runtime(tmp_path: Path) -> None:
    asset_root = tmp_path / "datasets" / "mmlu.vision.dev.v1"
    image_path = asset_root / "sample.ppm"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_text("P3\n1 1\n255\n255 0 0\n", encoding="utf-8")
    _write_final_result_dataset(
        dataset_root=asset_root,
        dataset_id="mmlu.vision.dev.v1",
        suite_id="mmlu",
        task_kind="image-text-to-text",
        samples=(
            {
                "id": "vision-1",
                "prompt": "What color is the square?",
                "expected": "red",
                "image_uri": "sample.ppm",
            },
        ),
    )

    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        return SimpleNamespace(config=SimpleNamespace(model_type="gemma4")), SimpleNamespace()

    def fake_apply_chat_template(processor, config, prompt: str, num_images: int = 0, **kwargs):
        _ = processor
        _ = config
        _ = kwargs
        return f"formatted::{prompt}::images={num_images}"

    captured_image_paths: list[str] = []

    def fake_stream_generate(model, processor, prompt: str, image=None, **kwargs):
        _ = model
        _ = processor
        _ = kwargs
        assert prompt.startswith("formatted::")
        assert "Return only the final short answer." in prompt
        assert "What color is the square?" in prompt
        assert prompt.endswith("::images=1")
        captured_image_paths.extend(list(image or []))
        yield SimpleNamespace(
            text="Answer: red",
            prompt_tokens=12,
            generation_tokens=1,
            prompt_tps=42.0,
            generation_tps=21.0,
            peak_memory=2048.0,
        )

    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=DeterministicTextBackend()),
        mlx_vlm_runtime=MLXVLMRuntime(
            backend=AutoMLXVLMBackend(
                load_fn=fake_load,
                stream_generate_fn=fake_stream_generate,
                apply_chat_template_fn=fake_apply_chat_template,
            )
        ),
        model_catalog=WorkerModelCatalog(),
    )
    service = build_service(tmp_path, registry=registry)
    loaded = registry.load_model(
        common_pb2.ModelSpec(
            model_id="google/paligemma2-3b-ft-docci-448",
            model_path="google/paligemma2-3b-ft-docci-448",
            model_kind="vlm",
            revision="main",
            tokenizer_hash="hf.google.paligemma2-3b-ft-docci-448",
            quant_profile_id="q8",
            parser_mode="text",
            reasoning_mode="off",
            max_context=4096,
            ext={
                "melix.vlm.backend_id": "mlx_vlm",
                "vision_family_id": "paligemma-v1",
                "vision_prompt_profile_id": "paligemma-caption-v1",
                "vision_tokenization_mode": "prefix",
                "vision_max_images_per_prompt": "1",
                "vision_supports_tool_calls": "false",
                "melix.multimodal_adapter_hash": "vision-family-paligemma-v1",
            },
        )
    )

    response = service.RunEvaluation(
        maintenance_pb2.RunEvaluationRequest(
            model_handle=loaded.handle,
            suite_id="mmlu",
            dataset_id="mmlu.vision.dev.v1",
            dataset_root=str(asset_root),
            sample_size=1,
            task_kind="image-text-to-text",
        ),
        context=None,
    )

    assert response.ok is True
    assert response.job.task_kind == "image-text-to-text"
    assert response.results[0].suite_id == "mmlu"
    assert captured_image_paths
    assert Path(captured_image_paths[0]).suffix == ".ppm"


def test_bench_events_image_generation_mode_produces_image_metrics(tmp_path: Path) -> None:
    core = MaintenanceCore(
        WorkerRegistry(model_catalog=WorkerModelCatalog()),
        jobs_root=tmp_path / "model-ops",
        benchmark_suite_catalog=BenchmarkSuiteCatalog(
            hf_dataset_fetcher=FakeBenchmarkHFDatasetFetcher()
        ),
    )

    events = list(
        core.bench_events(
            maintenance_pb2.RunBenchRequest(
                model_handle="melix-dev-image::1",
                suites=["smoke", "latency"],
            )
        )
    )

    metric_names = [event.metric.name for event in events if event.HasField("metric")]
    assert "bench.smoke.image_job_latency_ms" in metric_names
    assert "bench.smoke.image_artifact_publish_ms" in metric_names
    assert "bench.smoke.image_output_bytes" in metric_names
    assert "bench.latency.image_job_p50_ms" in metric_names
    assert "bench.latency.image_job_p95_ms" in metric_names

    report_event = next(event for event in events if event.HasField("completed"))
    report_content = Path(report_event.completed.report_path).read_text(encoding="utf-8")
    assert "task_kind: text-to-image" in report_content


def test_bench_events_image_edit_mode_produces_edit_metrics(tmp_path: Path) -> None:
    source_image_path = tmp_path / "source.png"
    source_image_path.write_bytes(b"\x89PNG\r\n\x1a\nsource")

    class LocalEditImageFetcher(FakeBenchmarkHFDatasetFetcher):
        def __call__(self, endpoint: str, params: dict[str, str]) -> dict[str, object]:
            dataset = params.get("dataset", "")
            if dataset == "huggingface/documentation-images":
                if endpoint == "rows":
                    return {"rows": [{"row": {"image": {"path": str(source_image_path)}}}]}
                return {"splits": [{"dataset": dataset, "config": "default", "split": "train"}]}
            return super().__call__(endpoint, params)

    registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
    edit_model = WorkerModelCatalog.dev_image_model()
    edit_model.model_id = "melix-dev-image-edit"
    edit_model.ext["melix.image.task_kind"] = "image-text-to-image"
    registry.model_catalog._models[edit_model.model_id] = edit_model

    core = MaintenanceCore(
        registry,
        jobs_root=tmp_path / "model-ops",
        benchmark_suite_catalog=BenchmarkSuiteCatalog(
            hf_dataset_fetcher=LocalEditImageFetcher()
        ),
    )

    events = list(
        core.bench_events(
            maintenance_pb2.RunBenchRequest(
                model_handle="melix-dev-image-edit::1",
                suites=["smoke"],
            )
        )
    )

    metric_names = [event.metric.name for event in events if event.HasField("metric")]
    assert "bench.smoke.image_job_latency_ms" in metric_names
    assert "bench.smoke.image_artifact_publish_ms" in metric_names
    assert "bench.smoke.image_output_bytes" in metric_names

    report_event = next(event for event in events if event.HasField("completed"))
    report_content = Path(report_event.completed.report_path).read_text(encoding="utf-8")
    assert "task_kind: image-text-to-image" in report_content


def test_bench_events_rejects_unsupported_task_family_after_suite_resolution(tmp_path: Path) -> None:
    core = MaintenanceCore(
        WorkerRegistry(model_catalog=WorkerModelCatalog()),
        jobs_root=tmp_path / "model-ops",
        benchmark_suite_catalog=BenchmarkSuiteCatalog(
            hf_dataset_fetcher=FakeBenchmarkHFDatasetFetcher()
        ),
    )
    fake_loaded_model = SimpleNamespace(
        handle="melix-dev-text::1",
        spec=common_pb2.ModelSpec(model_id="melix-dev-text", model_kind="text"),
        runtime_model={},
    )
    fake_suite = SimpleNamespace(suite_id="smoke", metadata=lambda: {}, cases=())
    core._resolve_benchmark_loaded_model = lambda model_handle: ("", fake_loaded_model)  # type: ignore[method-assign]
    core._benchmark_suite_catalog.resolve_suite = lambda *args, **kwargs: fake_suite  # type: ignore[method-assign]

    with pytest.raises(ModelOperationError) as error:
        list(
            core.bench_events(
                maintenance_pb2.RunBenchRequest(
                    model_handle="melix-dev-text::1",
                    suites=["smoke"],
                    task_kind="unsupported-task",
                )
            )
        )

    assert error.value.code == "unsupported_task_family"


def test_bench_events_forwards_parameters_to_queue_record(tmp_path: Path) -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=DeterministicTextBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    core = MaintenanceCore(
        registry,
        jobs_root=tmp_path / "model-ops",
        benchmark_suite_catalog=BenchmarkSuiteCatalog(
            hf_dataset_fetcher=FakeBenchmarkHFDatasetFetcher()
        ),
    )

    events = list(
        core.bench_events(
            maintenance_pb2.RunBenchRequest(
                model_handle="melix-dev-text::1",
                suites=["smoke"],
                parameters={"sample_size": "32", "batch_factor": "2"},
            )
        )
    )

    job_id = events[0].started.job_id
    queue_record = tmp_path / "model-ops" / "bench" / "queue" / f"{job_id}.json"
    payload = json.loads(queue_record.read_text(encoding="utf-8"))
    assert payload["parameters"]["sample_size"] == "32"
    assert payload["parameters"]["batch_factor"] == "2"


def test_export_results_writes_bundle_and_collects_model_ops_artifacts(tmp_path: Path) -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=RecordingBenchmarkBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    service = build_service(tmp_path, registry=registry)
    dataset_root = tmp_path / "datasets" / "qa_smoke.dev.v1"
    dataset_root.mkdir(parents=True)
    (dataset_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.evaluation_dataset_package.v1",
                "dataset_id": "qa_smoke.dev.v1",
                "suite_id": "mmlu",
                "version": "2026-03-31",
                "sample_count": 1,
                "split": "validation",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (dataset_root / "samples.jsonl").write_text(
        json.dumps({"prompt": "2+2?", "expected": "4"}) + "\n",
        encoding="utf-8",
    )

    _ = list(
        service.RunBench(
            maintenance_pb2.RunBenchRequest(
                model_handle="melix-dev-text::1",
                suites=["smoke", "latency"],
            ),
            context=None,
        )
    )
    matrix = service.RunBenchMatrix(
        maintenance_pb2.RunBenchMatrixRequest(
            model_handle="melix-dev-text::1",
            task_kind="text-generation",
            suite_ids=["smoke"],
            context_lengths=[1024],
            generation_lengths=[128],
            batch_sizes=[2],
            cache_profiles=["cold"],
            reasoning_modes=["enabled"],
            structured_output_modes=["plain_text"],
            concurrency_levels=[1],
            repeats=2,
            requests=4,
        ),
        context=None,
    )
    assert matrix.job.job_id
    evaluation = service.RunEvaluation(
        maintenance_pb2.RunEvaluationRequest(
            model_handle="melix-dev-text::1",
            suite_id="mmlu",
            dataset_id="qa_smoke.dev.v1",
            dataset_root=str(dataset_root),
            sample_size=1,
        ),
        context=None,
    )
    assert evaluation.ok is True

    response = service.ExportResults(
        maintenance_pb2.ExportResultsRequest(),
        context=None,
    )

    assert response.ok is True
    assert Path(response.export_path).exists() is True
    payload = json.loads(response.export_json)
    assert len(payload["benchmark_jobs"]) == 1
    assert len(payload["benchmark_matrix_jobs"]) == 1
    assert len(payload["benchmark_matrix_summary_rows"]) == 1
    assert len(payload["benchmark_matrix_request_rows"]) == 4
    assert len(payload["evaluation_jobs"]) == 1
    assert json.loads(Path(response.export_path).read_text(encoding="utf-8")) == payload


def test_submit_results_returns_typed_submission_payload(tmp_path: Path) -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=RecordingBenchmarkBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    service = build_service(tmp_path, registry=registry)
    dataset_root = tmp_path / "datasets" / "qa_smoke.dev.v1"
    dataset_root.mkdir(parents=True)
    (dataset_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.evaluation_dataset_package.v1",
                "dataset_id": "qa_smoke.dev.v1",
                "suite_id": "mmlu",
                "version": "2026-03-31",
                "sample_count": 1,
                "split": "validation",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (dataset_root / "samples.jsonl").write_text(
        json.dumps({"prompt": "2+2?", "expected": "4"}) + "\n",
        encoding="utf-8",
    )

    _ = list(
        service.RunBench(
            maintenance_pb2.RunBenchRequest(
                model_handle="melix-dev-text::1",
                suites=["smoke"],
            ),
            context=None,
        )
    )
    matrix = service.RunBenchMatrix(
        maintenance_pb2.RunBenchMatrixRequest(
            model_handle="melix-dev-text::1",
            task_kind="text-generation",
            suite_ids=["smoke"],
            context_lengths=[1024],
            generation_lengths=[128],
            batch_sizes=[2],
            cache_profiles=["cold"],
            reasoning_modes=["enabled"],
            structured_output_modes=["plain_text"],
            concurrency_levels=[1],
            repeats=2,
            requests=4,
        ),
        context=None,
    )
    assert matrix.job.job_id
    evaluation = service.RunEvaluation(
        maintenance_pb2.RunEvaluationRequest(
            model_handle="melix-dev-text::1",
            suite_id="mmlu",
            dataset_id="qa_smoke.dev.v1",
            dataset_root=str(dataset_root),
            sample_size=1,
        ),
        context=None,
    )
    assert evaluation.ok is True

    response = service.SubmitResults(
        maintenance_pb2.SubmitResultsRequest(
            device_metadata={
                "chip": "Apple M4",
                "memory_gb": "48.0",
                "os_version": "15.0",
                "os_build": "24A335",
                "hostname_hash": "test-host",
                "melix_version": "0.1.0",
            }
        ),
        context=None,
    )

    assert response.ok is True
    payload = json.loads(response.submission_json)
    assert payload["schema_version"] == "melix.submission.v1"
    assert payload["device"]["chip"] == "Apple M4"
    assert payload["device"]["memory_gb"] == 48.0
    assert payload["device"]["melix_version"] == "0.1.0"
    assert len(payload["benchmark_jobs"]) == 1
    assert len(payload["benchmark_matrix_jobs"]) == 1
    assert len(payload["benchmark_matrix_summary_rows"]) == 1
    assert len(payload["benchmark_matrix_request_rows"]) == 4
    assert len(payload["evaluation_jobs"]) == 1


def test_doctor_reports_detected_and_overridden_model_identity(tmp_path: Path) -> None:
    environment = {
        "MELIX_DEV_RERANK_MODEL_PATH": "models/jina-v3-reranker",
        "MELIX_DEV_RERANK_FAMILY_ID": "causal-lm",
    }
    registry = WorkerRegistry(model_catalog=WorkerModelCatalog(environment=environment))
    loaded = registry.load_model(WorkerModelCatalog.dev_rerank_model(environment=environment))
    service = WorkerMaintenanceService(registry, jobs_root=tmp_path / "model-ops")

    doctor = service.RunDoctor(
        maintenance_pb2.RunDoctorRequest(model_handle=loaded.handle),
        context=None,
    )

    assert doctor.ok is True
    assert "## Model Identity" in doctor.report_markdown
    assert "model_handle: melix-dev-rerank::1" in doctor.report_markdown
    assert "model_architecture: causal-lm" in doctor.report_markdown
    assert "detected_architecture: cross-encoder" in doctor.report_markdown
    assert "detected_family_id: jina-v3" in doctor.report_markdown
    assert "identity_override: true" in doctor.report_markdown
    assert doctor.health_status == maintenance_pb2.HEALTH_STATUS_HEALTHY
    assert doctor.findings == []
