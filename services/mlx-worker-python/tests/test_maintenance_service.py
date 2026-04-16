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
