from __future__ import annotations

import builtins
import csv
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest

from packages.protocol.python.worker.v1 import common_pb2, maintenance_pb2

from worker.grpc_server import WorkerMaintenanceService, _default_melix_home
from worker.model_ops.conversion_pipeline import ModelConversionPipeline
from worker.model_ops.adapter_activation_pipeline import AdapterActivationPipeline
from worker.model_ops.job_registry import (
    ModelOpsJob,
    ModelOpsJobRegistry,
    _runtime_mode_from_activation,
)
from worker.model_ops.hub_catalog import (
    HubCatalogError,
    HubModelCardRecord,
    HubModelSummaryRecord,
    HubSearchPage,
)
from worker.model_ops.download_pipeline import DownloadPipeline
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
    LocalFilesystemPublishBackend,
    PublishResult,
    SourceArtifactDescriptor,
    UploadReceiptPipeline,
    _last_nonblank_line,
    _resolve_hf_cli_command,
)
from worker.productization.benchmark_schemas import (
    build_serving_benchmark_job,
    build_serving_benchmark_results,
)
from worker.productization.benchmark_store import BenchmarkStore
from worker.productization.benchmark_suites import BenchmarkSuiteCatalog
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.engine.maintenance_core import (
    BenchSample,
    BenchmarkLoadedModelResolution,
    ImageBenchSample,
    MaintenanceCore,
)
from worker.engine import maintenance_core as maintenance_core_module
from worker.runtime.deterministic_backend import DeterministicTextBackend
from worker.runtime.mlx_vlm_runtime import AutoMLXVLMBackend, MLXVLMRuntime
from worker.runtime.mlx_text_runtime import MLXTextRuntime, RuntimeTokenEvent
from telemetry_fixtures import fixture_telemetry_collector


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
            speculative_acceptance_rate=0.75,
            speculative_rejected_tokens=1,
            speculative_draft_model_configured=True,
            dflash_enabled=True,
            dflash_rollback_count=1,
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
                    local_fit_status="good",
                    local_fit_reasons=[
                        "MLX-compatible Hub metadata found.",
                        "Estimated resident bytes are within the memory comfort budget.",
                    ],
                    estimated_artifact_bytes=4_200_000_000,
                    estimated_resident_bytes=5_670_000_000,
                    parameter_count=7_000_000_000,
                    quantization_summary="4-bit",
                    gated=False,
                    recommended_action="download",
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
                    local_fit_status="blocked",
                    local_fit_reasons=["No MLX compatibility signal"],
                    estimated_artifact_bytes=2_000_000_000,
                    estimated_resident_bytes=2_700_000_000,
                    parameter_count=0,
                    quantization_summary="",
                    gated=False,
                    recommended_action="unavailable",
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
            local_fit_status="heavy",
            local_fit_reasons=[
                "MLX-compatible Hub metadata found.",
                "Estimated resident bytes exceed the memory comfort budget.",
            ],
            estimated_artifact_bytes=52_000_000_000,
            estimated_resident_bytes=70_200_000_000,
            parameter_count=72_000_000_000,
            quantization_summary="4-bit",
            gated=False,
            recommended_action="review_risk",
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


class FakeDatasetCatalog:
    def __init__(self, *, failure: ModelOperationError | None = None) -> None:
        self.failure = failure
        self.calls: list[tuple[str, dict[str, object]]] = []

    def _raise_if_configured(self) -> None:
        if self.failure is not None:
            raise self.failure

    def registry_snapshot_payload(self, *, repo_id: str = "", revision: str = "") -> dict[str, object]:
        self._raise_if_configured()
        self.calls.append(("registry_snapshot_payload", {"repo_id": repo_id, "revision": revision}))
        return {
            "schema_version": "melix.dataset_registry_snapshot.v1",
            "roots": [],
            "datasets": [
                {
                    "dataset_id": f"{repo_id or 'org/repo'}@{revision or 'main'}",
                    "repo_id": repo_id or "org/repo",
                    "revision": revision or "main",
                    "snapshot_id": "abc123",
                    "snapshot_path": "/tmp/hf-cache/datasets--org--repo/snapshots/abc123",
                    "total_bytes": 123,
                }
            ],
        }

    def download_hf_dataset(
        self,
        *,
        repo_id: str,
        revision: str = "main",
        hf_token: str = "",
        job_id: str = "",
        output_dir: Path | None = None,
    ) -> SimpleNamespace:
        self._raise_if_configured()
        self.calls.append(
            (
                "download_hf_dataset",
                {
                    "repo_id": repo_id,
                    "revision": revision,
                    "hf_token": hf_token,
                    "job_id": job_id,
                    "output_dir": output_dir,
                },
            )
        )
        snapshot_path = Path(output_dir or "/tmp") / "snapshots" / "abc123"
        snapshot = SimpleNamespace(snapshot_path=snapshot_path)
        return SimpleNamespace(
            snapshot=snapshot,
            manifest={
                "schema_version": "melix.dataset_operation.v1",
                "operation": "dataset_download",
                "repo_id": repo_id,
                "revision": revision,
                "snapshot_id": "abc123",
                "snapshot_path": str(snapshot_path),
                "job_id": job_id,
            },
        )

    def remove_hf_dataset_snapshot(
        self,
        *,
        repo_id: str,
        revision: str = "",
        snapshot_id: str = "",
        job_id: str = "",
        output_dir: Path | None = None,
    ) -> SimpleNamespace:
        self._raise_if_configured()
        self.calls.append(
            (
                "remove_hf_dataset_snapshot",
                {
                    "repo_id": repo_id,
                    "revision": revision,
                    "snapshot_id": snapshot_id,
                    "job_id": job_id,
                    "output_dir": output_dir,
                },
            )
        )
        return SimpleNamespace(
            removed_snapshot=SimpleNamespace(snapshot_id=snapshot_id),
            manifest={
                "schema_version": "melix.dataset_operation.v1",
                "operation": "dataset_remove",
                "repo_id": repo_id,
                "revision": revision or "main",
                "snapshot_id": snapshot_id,
                "removed_snapshot_id": snapshot_id,
                "job_id": job_id,
            },
        )


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
        published_files: list[str] | None = None,
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
                "published_files": published_files,
            }
        )
        if published_files is not None:
            result_published_files = published_files
        elif source_path.is_dir():
            result_published_files = sorted(
                str(path.relative_to(source_path))
                for path in source_path.rglob("*")
                if path.is_file()
            )
        else:
            result_published_files = [source_path.name]
        return PublishResult(
            backend="huggingface_hub",
            target_repo=target_repo,
            target_url=f"https://huggingface.co/{target_repo}",
            remote_ref=f"{target_repo}@main",
            published_files=result_published_files,
        )


def build_service(
    tmp_path: Path,
    runner: MLXLMRunner | None = None,
    hub_catalog: FakeHubCatalog | None = None,
    registry: WorkerRegistry | None = None,
    benchmark_fetcher: FakeBenchmarkHFDatasetFetcher | None = None,
    publish_backend: FakePublishBackend | None = None,
    dataset_catalog: FakeDatasetCatalog | None = None,
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
        dataset_catalog=dataset_catalog,
    )
    service._core._benchmark_store = BenchmarkStore(telemetry_collector=fixture_telemetry_collector())
    service._fake_publish_backend = publish_backend
    return service


def test_default_melix_home_accepts_environment_mapping(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    melix_home = tmp_path / "custom-home"
    ignored_home = tmp_path / "ignored-home"
    monkeypatch.setenv("MELIX_HOME", str(ignored_home))

    assert _default_melix_home({"MELIX_HOME": f"  {melix_home}  "}) == melix_home.resolve()
    assert _default_melix_home({}) == (Path.home() / ".melix").resolve()


def test_maintenance_service_defaults_evaluation_jobs_root_next_to_model_ops_root(tmp_path: Path) -> None:
    service = WorkerMaintenanceService(
        WorkerRegistry(model_catalog=WorkerModelCatalog(environment={})),
        jobs_root=tmp_path / "jobs" / "model-ops",
        environment={},
    )

    assert service._evaluation_jobs_root == (tmp_path / "jobs" / "evaluation").resolve()


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


def test_convert_model_dispatches_synthetic_dataset_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = build_service(tmp_path)
    captured: dict[str, object] = {}

    def fake_generate_synthetic_dataset_package(request, *, jobs_root, output_dir, progress=None):
        captured["request"] = request
        captured["jobs_root"] = jobs_root
        captured["output_dir"] = output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "samples.jsonl"
        output_path.write_text('{"prompt":"hello","completion":"world"}\n', encoding="utf-8")
        manifest_path = output_dir / "manifest.json"
        manifest_payload = {
            "schema_version": "melix.training_dataset_package.v1",
            "operation": "generate_synthetic_dataset",
            "dataset_id": request.dataset_id,
            "dataset_name": request.dataset_name,
            "output_kind": request.output_kind,
            "row_count": request.num_records,
        }
        manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")
        if progress is not None:
            progress("generate_rows", 0.35)
            progress("complete", 1.0)
        return SimpleNamespace(
            manifest_payload=manifest_payload,
            manifest_path=manifest_path,
            output_path=output_path,
        )

    monkeypatch.setattr(
        maintenance_core_module,
        "generate_synthetic_dataset_package",
        fake_generate_synthetic_dataset_package,
    )

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-datasets",
                output_dir=str(tmp_path / "synthetic"),
                generate_manifest=True,
                ext={
                    "operation": "generate_synthetic_dataset",
                    "synthetic_mode": "create",
                    "synthetic_dataset_id": "synthetic.chat.v1",
                    "synthetic_dataset_name": "Synthetic Chat",
                    "synthetic_num_records": "4",
                    "synthetic_output_kind": "training",
                    "synthetic_output_format": "prompt_completion",
                    "provider_endpoint": "http://127.0.0.1:12436/v1",
                    "provider_name": "melix",
                    "provider_type": "openai",
                    "api_key": "sk-secret",
                    "headers_json": '["X-Test=1"]',
                    "model_alias": "generator",
                    "model": "melix-dev-text",
                    "temperature": "0.2",
                    "top_p": "0.9",
                    "max_tokens": "128",
                    "timeout_seconds": "30",
                    "max_parallel_requests": "2",
                    "extra_body_json": '{"seed":7}',
                    "columns_json": '["prompt:llm_text:{\\"prompt\\":\\"write\\"}"]',
                    "validation_ratio": "0.1",
                    "preview_count": "2",
                    "random_seed": "7",
                    "resume": "never",
                    "disable_datadesigner_telemetry": "true",
                },
            ),
            context=None,
        )
    )

    request = captured["request"]
    assert request.dataset_id == "synthetic.chat.v1"
    assert request.dataset_name == "Synthetic Chat"
    assert request.mode == "create"
    assert request.num_records == 4
    assert request.output_kind == "training"
    assert request.output_format == "prompt_completion"
    assert request.model_provider.endpoint == "http://127.0.0.1:12436/v1"
    assert request.model_provider.api_key == "sk-secret"
    assert request.model_provider.extra_headers == {"X-Test": "1"}
    assert request.models[0].alias == "generator"
    assert request.models[0].model == "melix-dev-text"
    assert request.models[0].temperature == 0.2
    assert request.models[0].top_p == 0.9
    assert request.models[0].max_tokens == 128
    assert request.models[0].timeout_seconds == 30.0
    assert request.models[0].max_parallel_requests == 2
    assert request.models[0].extra_body == {"seed": 7}
    assert request.columns[0].name == "prompt"
    assert request.columns[0].column_type == "llm_text"
    assert request.columns[0].params == {"prompt": "write"}
    assert request.validation_ratio == 0.1
    assert request.preview_count == 2
    assert request.random_seed == 7
    assert request.disable_data_designer_telemetry is True
    assert events[0].HasField("started")
    assert any(event.HasField("progress") and event.progress.stage == "generate_rows" for event in events)
    manifest = next(event.manifest for event in events if event.HasField("manifest"))
    manifest_payload = json.loads(manifest.manifest_json)
    assert manifest_payload["operation"] == "generate_synthetic_dataset"
    assert manifest_payload["job_id"].startswith("model-ops-")
    assert events[-1].HasField("completed")
    assert events[-1].completed.output_path.endswith("samples.jsonl")


def _synthetic_dataset_base_ext(**overrides: str) -> dict[str, str]:
    ext = {
        "synthetic_dataset_id": "synthetic.chat.v1",
        "synthetic_dataset_name": "Synthetic Chat",
        "synthetic_num_records": "4",
        "synthetic_output_kind": "training",
        "synthetic_output_format": "prompt_completion",
        "provider_endpoint": "http://127.0.0.1:12436/v1",
        "model": "melix-dev-text",
        "columns_json": json.dumps(["prompt:llm_text:Write a prompt"]),
    }
    ext.update(overrides)
    return ext


def test_synthetic_dataset_request_uses_defaults_and_column_shortcuts(tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("Write a useful training prompt.", encoding="utf-8")
    seed_file = tmp_path / "seed.jsonl"
    seed_file.write_text('{"topic":"swift"}\n', encoding="utf-8")

    request = maintenance_core_module._synthetic_dataset_request_from_ext(
        _synthetic_dataset_base_ext(
            columns_json=json.dumps(
                [
                    f"prompt:llm_text:@{prompt_file}",
                    "answer:expression:row.topic.upper()",
                    "label:sampler:positive,negative",
                    "tag:constant:static",
                    "empty:metadata:",
                ]
            ),
            seed_source_kind="jsonl",
            seed_source_path=str(seed_file),
            disable_datadesigner_telemetry="false",
        ),
        job_id="job-defaults",
    )

    assert request.mode == "create"
    assert request.model_provider.name == "melix"
    assert request.model_provider.provider_type == "openai"
    assert request.models[0].alias == "generator"
    assert request.models[0].temperature is None
    assert request.models[0].max_tokens is None
    assert request.validation_ratio == 0.0
    assert request.preview_count == 3
    assert request.random_seed is None
    assert request.disable_data_designer_telemetry is False
    assert request.seed_source is not None
    assert request.seed_source.source_path == seed_file
    assert request.columns[0].params == {"prompt": "Write a useful training prompt."}
    assert request.columns[1].params == {"expression": "row.topic.upper()"}
    assert request.columns[2].params == {"values": "positive,negative"}
    assert request.columns[3].params == {"value": "static"}
    assert request.columns[4].params == {}


def test_synthetic_dataset_request_parses_source_construction_metadata() -> None:
    request = maintenance_core_module._synthetic_dataset_request_from_ext(
        _synthetic_dataset_base_ext(
            source_construction_json=json.dumps(
                {
                    "construction_method": "source_anchored_multihop",
                    "source_bundle_id": "bundle-1",
                    "source_bundle_revision": "rev-a",
                    "source_count": 3,
                    "transformation_kinds": ["paraphrase", "entity_alias"],
                    "excluded_leakage_field_kinds": ["answer"],
                    "split_policy": "source_id_holdout",
                }
            )
        ),
        job_id="job-source-construction",
    )

    assert request.source_construction is not None
    assert request.source_construction.construction_method == "source_anchored_multihop"
    assert request.source_construction.source_bundle_id == "bundle-1"
    assert request.source_construction.source_count == 3
    assert request.source_construction.transformation_kinds == ("paraphrase", "entity_alias")
    assert request.source_construction.excluded_leakage_field_kinds == ("answer",)


def test_synthetic_dataset_request_accepts_empty_source_construction_lists() -> None:
    request = maintenance_core_module._synthetic_dataset_request_from_ext(
        _synthetic_dataset_base_ext(
            source_construction_json=json.dumps(
                {
                    "construction_method": "source_anchored_multihop",
                    "source_bundle_id": "bundle-1",
                    "source_count": "",
                    "transformation_kinds": "",
                    "excluded_leakage_field_kinds": None,
                }
            )
        ),
        job_id="job-source-construction-empty",
    )

    assert request.source_construction is not None
    assert request.source_construction.source_count == 0
    assert request.source_construction.transformation_kinds == ()
    assert request.source_construction.excluded_leakage_field_kinds == ()


def test_synthetic_dataset_column_shortcuts_only_read_explicit_at_files(tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("file-backed prompt", encoding="utf-8")

    request = maintenance_core_module._synthetic_dataset_request_from_ext(
        _synthetic_dataset_base_ext(
            columns_json=json.dumps(
                [
                    f"literal:llm_text:{prompt_file}",
                    f"expanded:llm_text:@{prompt_file}",
                    "missing:llm_text:@/does/not/exist.txt",
                    "empty:llm_text:@",
                ]
            )
        ),
        job_id="job-explicit-files",
    )

    assert request.columns[0].params == {"prompt": str(prompt_file)}
    assert request.columns[1].params == {"prompt": "file-backed prompt"}
    assert request.columns[2].params == {"prompt": "@/does/not/exist.txt"}
    assert request.columns[3].params == {"prompt": "@"}


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"synthetic_dataset_id": ""}, "synthetic_dataset_id is required"),
        ({"synthetic_num_records": ""}, "synthetic_num_records must be greater than zero"),
        ({"synthetic_num_records": "many"}, "synthetic_num_records must be an integer"),
        ({"preview_count": "0"}, "preview_count must be greater than zero"),
        ({"random_seed": "abc"}, "random_seed must be an integer"),
        ({"temperature": "hot"}, "temperature must be numeric"),
        ({"disable_datadesigner_telemetry": "maybe"}, "disable_datadesigner_telemetry must be a boolean"),
        ({"extra_body_json": "{"}, "extra_body_json must be valid JSON"),
        ({"extra_body_json": "[]"}, "extra_body_json must be a JSON object"),
        (
            {"source_construction_json": '{"source_count":"many"}'},
            "source_construction_json.source_count must be an integer",
        ),
        (
            {"source_construction_json": '{"transformation_kinds":"paraphrase"}'},
            "source_construction_json.transformation_kinds must be a JSON array",
        ),
        ({"headers_json": "{"}, "headers_json must be valid JSON"),
        ({"headers_json": "{}"}, "headers_json must be a JSON array"),
        ({"headers_json": json.dumps(["bad"])}, "Synthetic provider headers must use KEY=VALUE syntax"),
        ({"columns_json": json.dumps(["bad"])}, "Synthetic columns must use NAME:TYPE:JSON_OR_PATH syntax"),
        ({"columns_json": "[]"}, "At least one synthetic column is required"),
        ({"columns_json": json.dumps(["prompt:llm_text:{"])}, "Synthetic column JSON parameters must be valid JSON"),
        ({"columns_json": json.dumps(["prompt:llm_text:[]"])}, "Synthetic column JSON parameters must be an object"),
        ({"seed_source_kind": "jsonl"}, "seed_source_kind and seed_source_path must be provided together"),
    ],
)
def test_synthetic_dataset_request_rejects_malformed_ext(
    overrides: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(ModelOperationError, match=message):
        maintenance_core_module._synthetic_dataset_request_from_ext(
            _synthetic_dataset_base_ext(**overrides),
            job_id="job-invalid",
        )


def test_convert_model_writes_manifest_once_after_in_memory_byte_convergence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = build_service(tmp_path)
    write_calls = 0
    encode_manifest_bytes: list[int] = []
    original_write_manifest = ModelConversionPipeline._write_manifest
    original_encode_manifest = ModelConversionPipeline._encode_manifest

    def counting_write_manifest(path: Path, payload: dict[str, object], encoded: bytes | None = None) -> int:
        nonlocal write_calls
        write_calls += 1
        return original_write_manifest(path, payload, encoded)

    def tracking_encode_manifest(payload: dict[str, object]) -> bytes:
        encode_manifest_bytes.append(int(payload["manifest_bytes"]))
        return original_encode_manifest(payload)

    monkeypatch.setattr(ModelConversionPipeline, "_write_manifest", staticmethod(counting_write_manifest))
    monkeypatch.setattr(ModelConversionPipeline, "_encode_manifest", staticmethod(tracking_encode_manifest))

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
    convert_manifest = next(event.manifest for event in convert_events if event.HasField("manifest"))
    convert_payload = json.loads(convert_manifest.manifest_json)
    manifest_path = Path(convert_events[-1].completed.output_path) / "manifest.json"
    final_manifest_bytes = convert_payload["manifest_bytes"]

    assert write_calls == 1
    assert encode_manifest_bytes.count(final_manifest_bytes) == 1
    assert convert_payload["manifest_bytes"] == manifest_path.stat().st_size
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == convert_payload

    rewrite_path = manifest_path.with_name("manifest.rewrite.json")
    assert original_write_manifest(rewrite_path, convert_payload) == final_manifest_bytes
    assert rewrite_path.read_bytes() == manifest_path.read_bytes()


def test_convert_pipeline_counts_artifact_bytes_without_rescanning_bundle_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = build_service(tmp_path)
    original_scandir = os.scandir
    bundle_scandir_calls = 0

    def tracked_scandir(path: str | os.PathLike[str]) -> os.ScandirIterator[os.DirEntry[str]]:
        nonlocal bundle_scandir_calls
        if Path(path).name == "convert.artifact":
            bundle_scandir_calls += 1
            raise AssertionError("convert pipeline should not rescan the bundle directory for artifact_bytes")
        return original_scandir(path)

    with pytest.raises(AssertionError, match="should not rescan"):
        tracked_scandir(bundle_path := tmp_path / "convert.artifact")
    assert bundle_scandir_calls == 1
    bundle_scandir_calls = 0

    monkeypatch.setattr(os, "scandir", tracked_scandir)

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
    convert_manifest = next(event.manifest for event in convert_events if event.HasField("manifest"))
    convert_payload = json.loads(convert_manifest.manifest_json)
    bundle_path = Path(convert_events[-1].completed.output_path)
    expected_artifact_bytes = sum(
        (bundle_path / file_name).stat().st_size
        for file_name in ("config.json", "tokenizer.json", "weights.safetensors")
    )

    assert bundle_scandir_calls == 0
    assert convert_payload["artifact_bytes"] == expected_artifact_bytes


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


def test_convert_model_dispatches_dataset_operations_through_injected_catalog(tmp_path: Path) -> None:
    dataset_catalog = FakeDatasetCatalog()
    service = build_service(tmp_path, dataset_catalog=dataset_catalog)

    snapshot_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-datasets",
                output_dir=str(tmp_path / "dataset-snapshot"),
                generate_manifest=True,
                ext={
                    "operation": "dataset_snapshot",
                    "melix.hf_dataset_repo_id": "org/repo",
                    "melix.hf_revision": "main",
                },
            ),
            context=None,
        )
    )
    download_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="org/repo",
                output_dir=str(tmp_path / "dataset-download"),
                generate_manifest=True,
                ext={
                    "operation": "dataset_download",
                    "melix.hf_dataset_repo_id": "org/repo",
                    "melix.hf_revision": "feature",
                    "melix.hf_token": "hf_secret",
                },
            ),
            context=None,
        )
    )
    remove_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="org/repo",
                output_dir=str(tmp_path / "dataset-remove"),
                generate_manifest=True,
                ext={
                    "operation": "dataset_remove",
                    "melix.hf_dataset_repo_id": "org/repo",
                    "melix.hf_revision": "feature",
                    "melix.hf_snapshot_id": "abc123",
                },
            ),
            context=None,
        )
    )

    snapshot_payload = json.loads(
        next(event.manifest for event in snapshot_events if event.HasField("manifest")).manifest_json
    )
    download_payload = json.loads(
        next(event.manifest for event in download_events if event.HasField("manifest")).manifest_json
    )
    remove_payload = json.loads(
        next(event.manifest for event in remove_events if event.HasField("manifest")).manifest_json
    )

    assert snapshot_events[0].HasField("started")
    assert snapshot_events[-1].HasField("completed")
    assert snapshot_payload["dataset_registry"]["datasets"][0]["repo_id"] == "org/repo"
    assert download_events[-1].completed.output_path.endswith("snapshots/abc123")
    assert download_payload["operation"] == "dataset_download"
    assert remove_events[-1].completed.output_path.endswith("dataset_remove.json")
    assert remove_payload["operation"] == "dataset_remove"
    assert [name for name, _payload in dataset_catalog.calls] == [
        "registry_snapshot_payload",
        "download_hf_dataset",
        "remove_hf_dataset_snapshot",
    ]
    assert dataset_catalog.calls[1][1]["hf_token"] == "hf_secret"


def test_convert_model_dataset_operation_surfaces_catalog_errors(tmp_path: Path) -> None:
    dataset_catalog = FakeDatasetCatalog(
        failure=ModelOperationError(
            code="not_found",
            message="No matching managed dataset snapshot was found.",
        )
    )
    service = build_service(tmp_path, dataset_catalog=dataset_catalog)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="org/missing",
                ext={
                    "operation": "dataset_remove",
                    "melix.hf_dataset_repo_id": "org/missing",
                    "melix.hf_snapshot_id": "missing",
                },
            ),
            context=None,
        )
    )

    assert events[0].HasField("started")
    assert events[-1].HasField("failed")
    assert events[-1].failed.error.code == "not_found"
    assert events[-1].failed.error.message == "No matching managed dataset snapshot was found."


def test_upload_job_writes_receipt_once_after_in_memory_byte_convergence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = build_service(tmp_path)
    artifact_path = tmp_path / "artifact"
    artifact_path.write_text("melix-upload", encoding="utf-8")
    write_calls = 0
    original_write_manifest = UploadReceiptPipeline._write_manifest

    def counting_write_manifest(path: Path, payload: dict[str, object]) -> int:
        nonlocal write_calls
        write_calls += 1
        return original_write_manifest(path, payload)

    monkeypatch.setattr(UploadReceiptPipeline, "_write_manifest", staticmethod(counting_write_manifest))

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
    upload_manifest = next(event.manifest for event in upload_events if event.HasField("manifest"))
    upload_payload = json.loads(upload_manifest.manifest_json)
    receipt_path = Path(upload_events[-1].completed.output_path)

    assert write_calls == 1
    assert upload_payload["manifest_bytes"] == receipt_path.stat().st_size
    assert upload_payload["artifact_bytes"] == receipt_path.stat().st_size
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == upload_payload


def test_download_job_reports_managed_hub_snapshot_without_creating_descriptor(tmp_path: Path) -> None:
    source_dir = tmp_path / "hub-source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "config.json").write_text('{"model_type":"qwen3"}\n', encoding="utf-8")
    (source_dir / "tokenizer.json").write_text('{"version":"1.0"}\n', encoding="utf-8")
    (source_dir / "model.safetensors").write_bytes(b"weights")
    service = build_service(tmp_path, registry=WorkerRegistry(model_catalog=WorkerModelCatalog(environment={})))

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
                    "source_path": str(source_dir),
                },
            ),
            context=None,
        )
    )

    manifest = json.loads((tmp_path / "download-managed" / "download.state.json").read_text(encoding="utf-8"))
    expected_runtime_bytes = sum(path.stat().st_size for path in source_dir.rglob("*") if path.is_file())

    assert events[-1].completed.output_path == str(source_dir.resolve())
    assert manifest["managed_model_path"] == str(source_dir.resolve())
    assert manifest["output_path"] == str(source_dir.resolve())
    assert manifest["downloaded_bytes"] == expected_runtime_bytes
    assert manifest["total_bytes"] == expected_runtime_bytes
    assert manifest["ext"]["melix.source_kind"] == "hub_repo"
    assert manifest["ext"]["melix.hf_repo_id"] == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
    assert manifest["ext"]["melix.hf_revision"] == "main"
    assert manifest["ext"]["melix.managed_import"] == "true"
    assert manifest["ext"]["melix.model_path"] == str(source_dir.resolve())
    assert "melix.registry_descriptor_path" not in manifest["ext"]
    assert not (tmp_path / "managed-models").exists()


def test_managed_hub_repo_download_uses_default_huggingface_cache_and_cached_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hf_snapshot = tmp_path / "hf-cache" / "models--mlx-community--Tiny" / "snapshots" / "abc123"
    hf_snapshot.mkdir(parents=True, exist_ok=True)
    (hf_snapshot / "config.json").write_text('{"model_type":"qwen3"}\n', encoding="utf-8")
    (hf_snapshot / "model.safetensors").write_bytes(b"weights")
    home = tmp_path / "home"
    calls: list[dict[str, object]] = []

    def fake_snapshot_download(**kwargs: object) -> str:
        calls.append(dict(kwargs))
        return str(hf_snapshot)

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("HUGGINGFACE_HUB_CACHE", str(tmp_path / "ignored-hub-cache"))
    monkeypatch.setenv("HF_HOME", str(tmp_path / "ignored-hf-home"))
    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=fake_snapshot_download),
    )
    service = build_service(tmp_path, registry=WorkerRegistry(model_catalog=WorkerModelCatalog(environment={})))

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="mlx-community/Tiny",
                output_dir=str(tmp_path / "download-managed-cache"),
                generate_manifest=True,
                ext={
                    "operation": "download",
                    "melix.source_kind": "hub_repo",
                    "melix.hf_repo_id": "mlx-community/Tiny",
                    "melix.hf_revision": "main",
                    "melix.managed_import": "true",
                    "melix.hf_token": "hf_secret_token",
                },
            ),
            context=None,
        )
    )

    state_payload = json.loads((tmp_path / "download-managed-cache" / "download.state.json").read_text(encoding="utf-8"))

    assert calls[0]["repo_id"] == "mlx-community/Tiny"
    assert calls[0]["revision"] == "main"
    assert calls[0]["cache_dir"] == str(home / ".cache" / "huggingface" / "hub")
    assert calls[0]["token"] == "hf_secret_token"
    assert "local_dir" not in calls[0]
    assert "local_dir_use_symlinks" not in calls[0]
    assert events[-1].completed.output_path == str(hf_snapshot.resolve())
    assert state_payload["managed_model_path"] == str(hf_snapshot.resolve())
    assert state_payload["output_path"] == str(hf_snapshot.resolve())
    assert state_payload["ext"]["melix.model_path"] == str(hf_snapshot.resolve())
    assert "melix.registry_descriptor_path" not in state_payload["ext"]
    assert "hf_secret_token" not in json.dumps(state_payload, sort_keys=True)


def test_managed_hub_source_download_omits_blank_revision_and_normalizes_hub_and_auth_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hf_snapshot = tmp_path / "hf-cache" / "models--mlx-community--Tiny" / "snapshots" / "abc123"
    hf_snapshot.mkdir(parents=True, exist_ok=True)
    calls: list[dict[str, object]] = []

    def fake_snapshot_download(**kwargs: object) -> str:
        calls.append(dict(kwargs))
        return str(hf_snapshot)

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=fake_snapshot_download),
    )

    resolved = DownloadPipeline()._resolve_managed_hub_source_path(
        output_dir=tmp_path / "download",
        ext={},
        repo_id="mlx-community/Tiny",
        revision="",
    )

    assert resolved == hf_snapshot.resolve()
    assert calls[0]["revision"] is None
    assert calls[0]["cache_dir"] == str(Path.home() / ".cache" / "huggingface" / "hub")
    assert "token" not in calls[0]

    class FakeHubHTTPError(RuntimeError):
        pass

    FakeHubHTTPError.__module__ = "huggingface_hub.errors"

    def failing_snapshot_download(**kwargs: object) -> str:
        raise FakeHubHTTPError("network unavailable")

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=failing_snapshot_download),
    )

    with pytest.raises(ModelOperationError) as exc_info:
        DownloadPipeline()._resolve_managed_hub_source_path(
            output_dir=tmp_path / "download-failed",
            ext={},
            repo_id="mlx-community/Tiny",
            revision="main",
        )

    assert exc_info.value.code == "unavailable"
    assert "managed hub import failed" in exc_info.value.message

    class FakeHubAuthHTTPError(RuntimeError):
        response = SimpleNamespace(status_code=401)

    FakeHubAuthHTTPError.__module__ = "huggingface_hub.errors"

    def auth_failing_snapshot_download(**kwargs: object) -> str:
        raise FakeHubAuthHTTPError("401 unauthorized")

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=auth_failing_snapshot_download),
    )

    with pytest.raises(ModelOperationError) as auth_exc_info:
        DownloadPipeline()._resolve_managed_hub_source_path(
            output_dir=tmp_path / "download-auth-failed",
            ext={"melix.hf_token": "hf_secret_token"},
            repo_id="mlx-community/Tiny",
            revision="main",
        )

    assert auth_exc_info.value.code == "hf_auth_failed"
    assert auth_exc_info.value.message == "Hugging Face authentication failed. Check your token and try again."


def test_download_job_marks_managed_dflash_draft_metadata(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source_dir = (
        home
        / ".cache"
        / "huggingface"
        / "hub"
        / "models--z-lab--Qwen3.5-27B-DFlash"
        / "snapshots"
        / "abc123"
    )
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "config.json").write_text(
        json.dumps(
            {
                "model_type": "qwen3",
                "architectures": ["DFlashDraftModel"],
                "auto_map": {"AutoModel": "dflash.DFlashDraftModel"},
                "block_size": 8,
                "dflash_config": {"target_layer_ids": [5, 12, 19]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (source_dir / "README.md").write_text("library_name: mlx\n", encoding="utf-8")
    (source_dir / "dflash.py").write_text("class DFlashDraftModel: pass\n", encoding="utf-8")
    (source_dir / "model.safetensors").write_bytes(b"weights")
    registry = WorkerRegistry(
        model_catalog=WorkerModelCatalog(
            environment={
                "HOME": str(home),
            }
        )
    )
    service = build_service(tmp_path, registry=registry)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="z-lab/Qwen3.5-27B-DFlash",
                output_dir=str(tmp_path / "download-dflash"),
                generate_manifest=True,
                ext={
                    "operation": "download",
                    "melix.source_kind": "hub_repo",
                    "melix.hf_repo_id": "z-lab/Qwen3.5-27B-DFlash",
                    "melix.hf_revision": "main",
                    "melix.managed_import": "true",
                    "source_path": str(source_dir),
                },
            ),
            context=None,
        )
    )

    download_manifest = json.loads((tmp_path / "download-dflash" / "download.state.json").read_text(encoding="utf-8"))

    assert events[-1].completed.output_path == str(source_dir.resolve())
    assert download_manifest["managed_model_path"] == str(source_dir.resolve())
    assert download_manifest["ext"]["melix.model_path"] == str(source_dir.resolve())
    assert download_manifest["ext"]["melix.draft.runtime_kind"] == "dflash"
    assert download_manifest["ext"]["melix.draft.architecture"] == "DFlashDraftModel"
    assert download_manifest["ext"]["melix.dflash.block_size"] == "8"
    assert download_manifest["ext"]["melix.dflash.target_layer_ids"] == "5,12,19"

    snapshot_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "snapshot-after-dflash-download"),
                generate_manifest=True,
                ext={"operation": "registry_snapshot"},
            ),
            context=None,
        )
    )
    snapshot_payload = json.loads(
        next(event.manifest for event in snapshot_events if event.HasField("manifest")).manifest_json
    )
    discovered = {model["model_id"]: model for model in snapshot_payload["model_registry"]["models"]}

    assert discovered["z-lab/Qwen3.5-27B-DFlash"]["ext"]["melix.draft.runtime_kind"] == "dflash"


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


def test_hugging_face_publish_backend_extracts_large_stdout_tail_without_splitlines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_root = tmp_path / "publish"
    artifact_root.mkdir(parents=True)
    (artifact_root / "adapter.safetensors").write_text("weights", encoding="utf-8")
    stdout = "".join(f"progress {index}\n" for index in range(10_000))
    stdout += "   https://huggingface.co/melix/demo-adapter/commit/tail-ref   \n\n"

    def fake_subprocess_run(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("worker.model_ops.upload_receipt_pipeline.subprocess.run", fake_subprocess_run)

    result = HuggingFacePublishBackend().publish(
        source_path=artifact_root,
        target_repo="melix/demo-adapter",
        artifact_kind="adapter",
        published_files=["adapter.safetensors"],
    )

    assert result.remote_ref == "https://huggingface.co/melix/demo-adapter/commit/tail-ref"


def test_upload_receipt_pipeline_last_nonblank_line_preserves_edge_cases() -> None:
    assert _last_nonblank_line("") == ""
    assert _last_nonblank_line("\n \t \n") == ""
    assert _last_nonblank_line("first\r\n second \r\n\r\n") == "second"
    assert _last_nonblank_line("prefix\n  final-without-newline  ") == "final-without-newline"


def test_hugging_face_publish_backend_uses_precomputed_published_files_without_rescanning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_root = tmp_path / "publish"
    artifact_root.mkdir(parents=True)
    (artifact_root / "adapter.safetensors").write_text("weights", encoding="utf-8")
    seen: dict[str, object] = {}

    def fake_subprocess_run(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=0,
            stdout="\nhttps://huggingface.co/melix/demo-adapter/commit/abc123\n",
            stderr="",
        )

    def fail_rglob(self: Path, pattern: str):
        raise AssertionError("publish() should not rescan when published_files is supplied")

    monkeypatch.setattr("worker.model_ops.upload_receipt_pipeline.subprocess.run", fake_subprocess_run)
    monkeypatch.setattr(Path, "rglob", fail_rglob)

    result = HuggingFacePublishBackend().publish(
        source_path=artifact_root,
        target_repo="melix/demo-adapter",
        artifact_kind="adapter",
        published_files=["adapter.safetensors"],
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
    ]
    assert result.remote_ref == "https://huggingface.co/melix/demo-adapter/commit/abc123"
    assert result.published_files == ["adapter.safetensors"]


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


def test_hugging_face_publish_backend_maps_auth_and_generic_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_path = tmp_path / "artifact.gguf"
    artifact_path.write_text("weights", encoding="utf-8")

    responses = iter(
        [
            SimpleNamespace(returncode=1, stdout="", stderr="Not logged in to Hugging Face"),
            SimpleNamespace(returncode=1, stdout="generic failure", stderr=""),
        ]
    )

    monkeypatch.setattr(
        "worker.model_ops.upload_receipt_pipeline.subprocess.run",
        lambda *args, **kwargs: next(responses),
    )

    with pytest.raises(ModelOperationError) as auth_error:
        HuggingFacePublishBackend().publish(
            source_path=artifact_path,
            target_repo="melix/demo",
            artifact_kind="model_export",
        )
    assert auth_error.value.code == "publish_auth_required"
    assert "Not logged in" in auth_error.value.message

    with pytest.raises(ModelOperationError) as generic_error:
        HuggingFacePublishBackend().publish(
            source_path=artifact_path,
            target_repo="melix/demo",
            artifact_kind="model_export",
        )
    assert generic_error.value.code == "publish_failed"
    assert generic_error.value.message == "generic failure"


@pytest.mark.parametrize(
    ("descriptor", "requested_kind", "expected_code", "expected_kind"),
    [
        (
            SourceArtifactDescriptor(
                artifact_path="/tmp/model.gguf",
                artifact_kind="model",
                schema_version="",
                manifest_path="",
                source_model="melix-dev-text",
                manifest_payload=None,
            ),
            "adapter_export",
            "invalid_argument",
            None,
        ),
        (
            SourceArtifactDescriptor(
                artifact_path="/tmp/model.gguf",
                artifact_kind="model",
                schema_version="",
                manifest_path="",
                source_model="melix-dev-text",
                manifest_payload=None,
            ),
            "merged_export",
            "invalid_argument",
            None,
        ),
        (
            SourceArtifactDescriptor(
                artifact_path="/tmp/model.gguf",
                artifact_kind="model",
                schema_version="melix.derived_text_model.v1",
                manifest_path="/tmp/model.json",
                source_model="melix-dev-text",
                manifest_payload={"activation_mode": "fused_derived_model"},
            ),
            "",
            None,
            "merged_export",
        ),
    ],
)
def test_upload_receipt_pipeline_resolve_export_artifact_kind_edges(
    descriptor: SourceArtifactDescriptor,
    requested_kind: str,
    expected_code: str | None,
    expected_kind: str | None,
) -> None:
    if expected_code is not None:
        with pytest.raises(ModelOperationError) as error:
            UploadReceiptPipeline._resolve_export_artifact_kind(
                descriptor=descriptor,
                requested_kind=requested_kind,
            )
        assert error.value.code == expected_code
        return

    assert (
        UploadReceiptPipeline._resolve_export_artifact_kind(
            descriptor=descriptor,
            requested_kind=requested_kind,
        )
        == expected_kind
    )


def test_upload_receipt_pipeline_resolve_merged_publish_source_edges(tmp_path: Path) -> None:
    converted_root = tmp_path / "converted"
    converted_root.mkdir()
    bundle_file = converted_root / "model.gguf"
    bundle_file.write_text("weights", encoding="utf-8")
    (converted_root / "manifest.json").write_text("{}\n", encoding="utf-8")

    converted_descriptor = SourceArtifactDescriptor(
        artifact_path=str(bundle_file),
        artifact_kind="converted_model_bundle",
        schema_version="",
        manifest_path=str(converted_root / "manifest.json"),
        source_model="melix-dev-text",
        manifest_payload={"artifact_kind": "converted_model_bundle"},
    )
    assert UploadReceiptPipeline._resolve_merged_publish_source(converted_descriptor, bundle_file) == converted_root

    invalid_activation_descriptor = SourceArtifactDescriptor(
        artifact_path=str(bundle_file),
        artifact_kind="derived_text_model",
        schema_version="melix.derived_text_model.v1",
        manifest_path=str(converted_root / "manifest.json"),
        source_model="melix-dev-text",
        manifest_payload={"activation_mode": "adapter_runtime", "derived_model_path": str(tmp_path / "missing")},
    )
    with pytest.raises(ModelOperationError) as invalid_activation:
        UploadReceiptPipeline._resolve_merged_publish_source(invalid_activation_descriptor, bundle_file)
    assert invalid_activation.value.code == "invalid_argument"

    invalid_source_descriptor = SourceArtifactDescriptor(
        artifact_path=str(bundle_file),
        artifact_kind="model",
        schema_version="",
        manifest_path="",
        source_model="melix-dev-text",
        manifest_payload=None,
    )
    with pytest.raises(ModelOperationError) as invalid_source:
        UploadReceiptPipeline._resolve_merged_publish_source(invalid_source_descriptor, bundle_file)
    assert invalid_source.value.code == "invalid_artifact"


def test_upload_receipt_pipeline_resolve_source_artifact_and_linked_quantization_edges(tmp_path: Path) -> None:
    pipeline = UploadReceiptPipeline(publisher=FakePublishBackend())

    missing_request = maintenance_pb2.ConvertModelRequest(
        source_model="melix-dev-text",
        ext={"artifact_path": str(tmp_path / "missing.gguf")},
    )
    with pytest.raises(ModelOperationError) as missing_artifact:
        pipeline._resolve_source_artifact(missing_request)
    assert missing_artifact.value.code == "invalid_artifact"

    manifest_root = tmp_path / "manifest-root"
    manifest_root.mkdir()
    (manifest_root / "manifest.json").write_text("[]\n", encoding="utf-8")
    non_dict_request = maintenance_pb2.ConvertModelRequest(
        source_model="melix-dev-text",
        ext={"artifact_path": str(manifest_root), "artifact_kind": "model_export"},
    )
    descriptor = pipeline._resolve_source_artifact(non_dict_request)
    assert descriptor.manifest_payload is None
    assert descriptor.artifact_kind == "model_export"

    linked_quantization = UploadReceiptPipeline._linked_quantization(
        {
            "artifact_kind": "quantized_model_bundle",
            "artifact_path": "bundle",
            "manifest_path": "bundle/manifest.json",
            "source_model": "melix-dev-text",
            "calibration": "bad",
            "compatibility": "bad",
            "quant_profile": "bad",
        }
    )
    assert linked_quantization == {
        "artifact_kind": "quantized_model_bundle",
        "artifact_path": "bundle",
        "manifest_path": "bundle/manifest.json",
        "source_model": "melix-dev-text",
        "quant_profile_id": "",
        "calibration_sample_count": 0,
        "smoke_test_passed": False,
    }


def test_upload_receipt_pipeline_collect_published_file_list_filters_and_sorts(tmp_path: Path) -> None:
    source_root = tmp_path / "model"
    source_root.mkdir()
    (source_root / "aa.bin").write_text("weights", encoding="utf-8")
    nested_root = source_root / "sub"
    nested_root.mkdir()
    (nested_root / "zz.bin").write_text("meta", encoding="utf-8")
    nested_root.joinpath("aa.bin").write_text("meta2", encoding="utf-8")
    (source_root / "README.md").write_text("meta", encoding="utf-8")

    files = UploadReceiptPipeline._collect_published_file_list(source_root)
    assert files == [
        "README.md",
        "aa.bin",
        "sub/aa.bin",
        "sub/zz.bin",
    ]


def test_upload_receipt_pipeline_collect_published_file_list_uses_scandir_stack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "model"
    source_root.mkdir()
    (source_root / "weights.bin").write_text("weights", encoding="utf-8")
    nested_root = source_root / "nested"
    nested_root.mkdir()
    (nested_root / "config.json").write_text("{}", encoding="utf-8")

    def fail_os_walk(*args, **kwargs):
        raise AssertionError("published file collection should avoid os.walk")  # pragma: no cover

    monkeypatch.setattr("worker.model_ops.upload_receipt_pipeline.os.walk", fail_os_walk)

    assert UploadReceiptPipeline._collect_published_file_list(source_root) == [
        "nested/config.json",
        "weights.bin",
    ]


def test_upload_receipt_pipeline_collect_published_file_list_preserves_symlink_rules(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "model"
    source_root.mkdir()
    (source_root / "weights.bin").write_text("weights", encoding="utf-8")
    target_file = source_root / "target.txt"
    target_file.write_text("target", encoding="utf-8")
    (source_root / "file-link.txt").symlink_to(target_file)
    nested_root = source_root / "nested"
    nested_root.mkdir()
    (nested_root / "config.json").write_text("{}", encoding="utf-8")
    (source_root / "dir-link").symlink_to(nested_root, target_is_directory=True)
    (source_root / "broken-link").symlink_to(source_root / "missing.bin")

    assert UploadReceiptPipeline._collect_published_file_list(source_root) == [
        "broken-link",
        "file-link.txt",
        "nested/config.json",
        "target.txt",
        "weights.bin",
    ]


def test_upload_receipt_pipeline_collect_published_file_list_limits_follow_dir_checks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "model"
    source_root.mkdir()
    followed_dir_checks: list[str] = []

    class FakeDirEntry:
        def __init__(
            self,
            name: str,
            *,
            is_dir: bool = False,
            is_file: bool = False,
            is_symlink: bool = False,
            follows_to_dir: bool = False,
        ) -> None:
            self.name = name
            self.path = os.fspath(source_root / name)
            self._is_dir = is_dir
            self._is_file = is_file
            self._is_symlink = is_symlink
            self._follows_to_dir = follows_to_dir

        def is_dir(self, *, follow_symlinks: bool = True) -> bool:
            if follow_symlinks:
                followed_dir_checks.append(self.name)
                return self._follows_to_dir
            return self._is_dir

        def is_file(self, *, follow_symlinks: bool = True) -> bool:
            return self._is_file if not follow_symlinks else self._is_file

        def is_symlink(self) -> bool:
            return self._is_symlink

    class FakeScandir:
        def __init__(self, path: str) -> None:
            self._path = path

        def __enter__(self):
            if self._path == os.fspath(source_root):
                return iter(
                    [
                        FakeDirEntry("regular.bin", is_file=True),
                        FakeDirEntry("special-device"),
                        FakeDirEntry("file-link", is_symlink=True),
                        FakeDirEntry("dir-link", is_symlink=True, follows_to_dir=True),
                    ]
                )
            return iter(())  # pragma: no cover - only used for unexpected nested scans

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr("worker.model_ops.upload_receipt_pipeline.os.scandir", FakeScandir)

    assert UploadReceiptPipeline._collect_published_file_list(source_root) == [
        "file-link",
        "regular.bin",
        "special-device",
    ]
    assert followed_dir_checks == ["file-link", "dir-link"]


def test_prepare_publish_source_uses_collected_file_list_for_directory(tmp_path: Path) -> None:
    pipeline = UploadReceiptPipeline(publisher=FakePublishBackend())
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "a.bin").write_text("artifact", encoding="utf-8")
    nested_root = source_root / "nested"
    nested_root.mkdir()
    (nested_root / "b.bin").write_text("artifact", encoding="utf-8")

    descriptor = SourceArtifactDescriptor(
        artifact_path=str(source_root),
        artifact_kind="model",
        schema_version="",
        manifest_path="",
        source_model="melix-dev-text",
        manifest_payload=None,
    )
    prepared = pipeline._prepare_publish_source(
        descriptor,
        receipt_dir=tmp_path / "receipt",
        target_repo="melix/dev",
        export_artifact_kind="model_export",
    )
    assert prepared.source_path == source_root
    assert prepared.published_files == ["a.bin", "nested/b.bin"]


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


@pytest.mark.parametrize(
    "filename",
    ["processor_config.json", "preprocessor_config.json", "image_processor.json"],
)
def test_collect_processor_config_files_detects_all_supported_names_at_root(filename: str) -> None:
    files = [filename, "config.json", "model.safetensors", "tokenizer.json"]
    result = UploadReceiptPipeline._collect_processor_config_files(files)
    assert result == [filename]


def test_collect_processor_config_files_ignores_nested_processor_configs() -> None:
    files = [
        "config.json",
        "model.safetensors",
        "adapters/processor_config.json",
        "sub/preprocessor_config.json",
    ]
    assert UploadReceiptPipeline._collect_processor_config_files(files) == []


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
        for event in service.ConvertModel(
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
        ):
            first_events.append(event)
            if event.HasField("started"):
                started.set()

    worker = threading.Thread(target=run_first_job)
    worker.start()
    assert started.wait(timeout=1.0)

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


def test_quantize_job_reports_unstructured_pipeline_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
    service = WorkerMaintenanceService(registry, jobs_root=tmp_path / "model-ops")

    def raise_unstructured_failure(*args: object, **kwargs: object) -> None:
        raise RuntimeError("calibration reader exploded")

    monkeypatch.setattr(
        service._core._quantization_pipeline,
        "run",
        raise_unstructured_failure,
    )

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
    assert events[-1].failed.error.code == "quantization_failure"
    assert events[-1].failed.error.message == "calibration reader exploded"


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

    started = threading.Event()
    first_events: list[maintenance_pb2.ConvertModelEvent] = []

    def run_held_quantize() -> None:
        nonlocal first_events
        for event in service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "quantize-held"),
                weight_quant="q4",
                kv_quant="q8",
                ext={"operation": "quantize", "test_hold_ms": "150"},
            ),
            context=None,
        ):
            first_events.append(event)
            if event.HasField("started"):
                started.set()

    worker = threading.Thread(target=run_held_quantize)
    worker.start()
    assert started.wait(timeout=1.0)

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
    assert publish_backend.calls[-1]["published_files"] == [
        "adapter/adapter_config.json",
        "adapter/adapters.safetensors",
        "train_lora.adapter.json",
    ]
    staged_source = publish_backend.calls[-1]["source_path"]
    assert isinstance(staged_source, Path)
    staged_manifest = json.loads((staged_source / "train_lora.adapter.json").read_text(encoding="utf-8"))
    assert staged_manifest["weights_path"] == "adapter/adapters.safetensors"
    assert staged_manifest["adapter_config_path"] == "adapter/adapter_config.json"
    assert staged_manifest["published_repo"] == "melix/adapters/melix-dev-adapter"


def test_upload_receipt_pipeline_local_filesystem_backend_writes_publish_bundle(tmp_path: Path) -> None:
    adapter_dir = tmp_path / "adapter-source"
    adapter_dir.mkdir()
    weights_path = adapter_dir / "adapters.safetensors"
    config_path = adapter_dir / "adapter_config.json"
    manifest_path = adapter_dir / "train_lora.adapter.json"
    weights_path.write_bytes(b"adapter")
    config_path.write_text('{"fine_tune_type":"lora"}\n', encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.lora_adapter_package.v1",
                "artifact_kind": "adapter",
                "adapter_name": "local-adapter",
                "job_id": "train-1",
                "source_model": "melix-dev-text",
                "weights_path": str(weights_path),
                "adapter_config_path": str(config_path),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = UploadReceiptPipeline().run(
        maintenance_pb2.ConvertModelRequest(
            source_model="melix-dev-text",
            generate_manifest=True,
            ext={
                "operation": "upload",
                "artifact_kind": "adapter_export",
                "artifact_path": str(manifest_path),
                "target_repo": "melix/adapters/local-adapter",
                "publish_backend": "local_filesystem",
                "local_publish_root": str(tmp_path / "local-publish"),
            },
        ),
        job_id="upload-local-1",
        output_dir=tmp_path / "upload-local",
    )

    publish_root = tmp_path / "local-publish" / "melix" / "adapters" / "local-adapter"
    payload = result.manifest_payload
    assert payload["status"] == "published"
    assert payload["upload_backend"] == "local_filesystem"
    assert payload["published_url"] == publish_root.as_uri()
    assert payload["published_ref"] == str(publish_root)
    assert payload["distribution_contract"] == "adapter_only"
    assert (publish_root / "adapter" / "adapters.safetensors").is_file()
    assert (publish_root / "adapter" / "adapter_config.json").is_file()
    assert (publish_root / "train_lora.adapter.json").is_file()


def test_local_filesystem_publish_backend_handles_file_source_and_backend_edges(tmp_path: Path) -> None:
    source_path = tmp_path / "artifact.json"
    source_path.write_text('{"ok":true}\n', encoding="utf-8")
    target_file = tmp_path / "publish" / "artifact"
    target_file.parent.mkdir()
    target_file.write_text("stale", encoding="utf-8")

    result = LocalFilesystemPublishBackend(root=tmp_path / "publish").publish(
        source_path=source_path,
        target_repo="/",
        artifact_kind="model_export",
    )

    assert result.backend == "local_filesystem"
    assert result.target_repo == "/"
    assert result.published_files == ["artifact.json"]
    assert (tmp_path / "publish" / "artifact" / "artifact.json").read_text(encoding="utf-8") == '{"ok":true}\n'
    assert isinstance(UploadReceiptPipeline._resolve_publisher_from_ext({}), HuggingFacePublishBackend)
    with pytest.raises(ModelOperationError, match="local_publish_root"):
        UploadReceiptPipeline._resolve_publisher_from_ext({"publish_backend": "local_filesystem"})
    with pytest.raises(ModelOperationError, match="publish_backend must be one of"):
        UploadReceiptPipeline._resolve_publisher_from_ext({"publish_backend": "unknown"})


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


def test_upload_job_publishes_merged_multimodal_model_with_processor_lineage(tmp_path: Path) -> None:
    class MultimodalLoRARunner(DeterministicLoRARunner):
        def activate_native(self, request: ActivationRequest) -> ActivationResult:
            result = super().activate_native(request)
            (request.derived_model_dir / "processor_config.json").write_text(
                json.dumps({"processor_type": "melix-test-vlm"}) + "\n",
                encoding="utf-8",
            )
            return result

    dataset_dir = _write_training_dataset_package(tmp_path)
    publish_backend = FakePublishBackend()
    service = build_service(tmp_path, runner=MultimodalLoRARunner(), publish_backend=publish_backend)

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
                    "derived_model_alias": "melix-dev-vlm",
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
                output_dir=str(tmp_path / "upload-multimodal"),
                generate_manifest=True,
                ext={
                    "operation": "upload",
                    "artifact_kind": "merged_export",
                    "artifact_path": activation_manifest_path,
                    "artifact_manifest_path": activation_manifest_path,
                    "target_repo": "melix/models/melix-dev-vlm",
                },
            ),
            context=None,
        )
    )

    payload = json.loads(
        next(event.manifest for event in upload_events if event.HasField("manifest")).manifest_json
    )

    assert upload_events[-1].completed.output_path.endswith("upload.receipt.json")
    assert payload["export_artifact_kind"] == "merged_export"
    assert payload["distribution_contract"] == "merged_multimodal"
    assert payload["processor_config_files"] == ["processor_config.json"]
    assert "processor_config.json" in payload["published_files"]
    assert publish_backend.calls[-1]["artifact_kind"] == "merged_export"


def test_upload_job_publishes_converted_bundle_as_merged_multimodal_when_processor_config_present(
    tmp_path: Path,
) -> None:
    service = build_service(tmp_path, publish_backend=FakePublishBackend())

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
    # convert emits the bundle directory as output_path, not the manifest file.
    bundle_dir = Path(convert_events[-1].completed.output_path)
    (bundle_dir / "processor_config.json").write_text(
        '{"processor_type": "melix-test-vlm"}\n', encoding="utf-8"
    )

    publish_backend = FakePublishBackend()
    service = build_service(tmp_path, publish_backend=publish_backend)
    upload_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "upload-converted-multimodal"),
                generate_manifest=True,
                ext={
                    "operation": "upload",
                    "artifact_path": str(bundle_dir),
                    "target_repo": "melix/models/melix-dev-vlm-converted",
                },
            ),
            context=None,
        )
    )

    payload = json.loads(
        next(event.manifest for event in upload_events if event.HasField("manifest")).manifest_json
    )

    assert upload_events[-1].completed.output_path.endswith("upload.receipt.json")
    assert payload["export_artifact_kind"] == "merged_export"
    assert payload["distribution_contract"] == "merged_multimodal"
    assert payload["processor_config_files"] == ["processor_config.json"]
    assert "processor_config.json" in payload["published_files"]


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


def test_registry_snapshot_keeps_gemma4_vlm_cooperative_text_step_opt_in(tmp_path: Path) -> None:
    default_model_dir = (
        tmp_path / "registry-root" / "huggingface" / "lmstudio-community" / "gemma-4-26B-A4B-it-MLX-4bit"
    )
    _write_registry_manifest(
        default_model_dir,
        model_id="lmstudio-community/gemma-4-26B-A4B-it-MLX-4bit",
        model_kind="vlm",
    )
    (default_model_dir / "config.json").write_text(json.dumps({"model_type": "gemma4"}) + "\n", encoding="utf-8")
    opt_in_model_dir = (
        tmp_path / "registry-root" / "huggingface" / "melix-local" / "gemma-4-26B-A4B-it-MLX-4bit-cooperative"
    )
    _write_registry_manifest(
        opt_in_model_dir,
        model_id="melix-local/gemma-4-26B-A4B-it-MLX-4bit-cooperative",
        model_kind="vlm",
        ext={"melix.vlm.text_only_step_cooperative": "true"},
    )
    (opt_in_model_dir / "config.json").write_text(json.dumps({"model_type": "gemma4"}) + "\n", encoding="utf-8")

    registry = WorkerRegistry(
        model_catalog=WorkerModelCatalog(
            environment={
                "MELIX_MODEL_ROOTS": str(tmp_path / "registry-root"),
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
    models_by_id = {model["model_id"]: model for model in payload["model_registry"]["models"]}
    default_ext = models_by_id["lmstudio-community/gemma-4-26B-A4B-it-MLX-4bit"]["ext"]
    opt_in_ext = models_by_id["melix-local/gemma-4-26B-A4B-it-MLX-4bit-cooperative"]["ext"]

    assert default_ext["vision_family_id"] == "gemma4-v1"
    assert default_ext["melix.vlm.backend_id"] == "mlx_vlm"
    assert default_ext["melix.vlm.text_only_step_cooperative"] == "false"
    assert opt_in_ext["vision_family_id"] == "gemma4-v1"
    assert opt_in_ext["melix.vlm.text_only_step_cooperative"] == "true"


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


def test_job_registry_snapshot_reuses_cached_manifest_after_attach(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = ModelOpsJobRegistry()
    completed = registry.start("train_lora", "melix-dev-text", "/tmp/train")
    manifest = json.dumps({"adapter_name": "adapter-a", "adapter_set_hash": "hash-a"})
    registry.attach_manifest(completed.job_id, manifest)
    registry.complete(completed.job_id, "/tmp/train/train_lora.adapter.json")

    def fail_manifest_decode(manifest_json: str) -> dict[str, object]:
        raise AssertionError(f"snapshot should not reparse cached manifest: {manifest_json}")

    monkeypatch.setattr(ModelOpsJobRegistry, "_decode_manifest_json", staticmethod(fail_manifest_decode))

    payload = registry.snapshot()

    assert payload["jobs"][0]["manifest"] == {"adapter_name": "adapter-a", "adapter_set_hash": "hash-a"}
    assert payload["adapters"][0]["adapter_name"] == "adapter-a"


def test_job_registry_snapshot_reuses_cached_manifest_after_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs_root = tmp_path / "jobs"
    manifest_path = jobs_root / "train_lora" / "model-ops-0007" / "train_lora.adapter.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "job_id": "model-ops-0007",
                "operation": "train_lora",
                "source_model": "melix-dev-text",
                "adapter_name": "adapter-restored",
                "adapter_set_hash": "hash-restored",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    registry = ModelOpsJobRegistry(jobs_root=jobs_root)

    def fail_manifest_decode(manifest_json: str) -> dict[str, object]:
        raise AssertionError(f"snapshot should not reparse restored manifest: {manifest_json}")

    monkeypatch.setattr(ModelOpsJobRegistry, "_decode_manifest_json", staticmethod(fail_manifest_decode))

    payload = registry.snapshot()

    assert payload["jobs"][0]["manifest"] == {
        "job_id": "model-ops-0007",
        "operation": "train_lora",
        "source_model": "melix-dev-text",
        "adapter_name": "adapter-restored",
        "adapter_set_hash": "hash-restored",
    }
    assert payload["adapters"][0]["adapter_name"] == "adapter-restored"


def test_job_registry_helper_paths_cover_restore_and_runtime_edges(tmp_path: Path) -> None:
    missing_manifest = tmp_path / "missing.json"
    list_manifest = tmp_path / "list.json"
    list_manifest.write_text("[]\n", encoding="utf-8")

    assert ModelOpsJobRegistry._decode_manifest_json("[]") == {}
    assert ModelOpsJobRegistry._read_manifest_dict(missing_manifest) == {}
    assert ModelOpsJobRegistry._read_manifest_dict(list_manifest) == {}
    assert ModelOpsJobRegistry._resolved_job_id(
        Path("/tmp/train_lora/model-ops-0042/train_lora.adapter.json"), {}
    ) == "model-ops-0042"
    assert ModelOpsJobRegistry._resolved_job_id(Path("/tmp/train_lora/no-job-id/manifest.json"), {}) == ""
    assert ModelOpsJobRegistry().resolve_derived_model_target() is None
    assert ModelOpsJobRegistry._job_sort_key(
        ModelOpsJob(
            job_id="custom-job",
            operation="train_lora",
            source_model="melix-dev-text",
            output_dir="/tmp/custom",
        )
    ) == 0
    assert common_pb2.RuntimeMode.Name(_runtime_mode_from_activation(" adapter_backed_runtime ")) == "RUNTIME_MODE_ADAPTER_BACKED"


def test_derived_model_registration_preserves_component_scoped_adapter_metadata(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    source_model = common_pb2.ModelSpec(
        model_id="melix-gemma4-vlm",
        model_path=str(tmp_path / "gemma4-vlm"),
        model_kind="vlm",
        revision="main",
        max_context=8192,
    )
    source_model.ext["melix.lora.adapter_scope"] = "text_backbone"
    source_model.ext["melix.lora.training_surface"] = "text_backbone"
    source_model.ext["melix.lora.family_id"] = "gemma"
    source_model.ext["melix.lora.component_model_type"] = "gemma4_text"
    source_model.ext["melix.lora.base_model_path"] = source_model.model_path
    service._core._registry.model_catalog.register_model(source_model)

    model_spec = service._core._derived_model_spec_from_manifest(
        {
            "derived_model_id": "melix-gemma4-vlm-lora-abcd",
            "derived_model_path": source_model.model_path,
            "source_model": source_model.model_id,
            "source_model_revision": "main",
            "source_model_kind": "vlm",
            "source_model_ext": dict(source_model.ext),
            "activation_mode": "adapter_backed_runtime",
            "adapter_manifest_path": str(tmp_path / "train_lora.adapter.json"),
            "adapter_weights_path": str(tmp_path / "adapters.safetensors"),
            "adapter_set_hash": "abcd1234",
            "adapter_scope": "text_backbone",
            "training_surface": "text_backbone",
            "component_model_type": "gemma4_text",
            "component_family": "gemma",
            "component_model_path": source_model.model_path,
            "adapter_runtime.base_reuse_key": "base-key-123",
            "adapter_runtime.adapter_isolation_key": "adapter-key-456",
            "adapter_runtime.switch_mode": "base_reuse_adapter_swap",
            "adapter_runtime.sharing_policy": "shared_base_isolated_adapter",
            "adapter_runtime.compatibility_status": "compatible",
        }
    )

    assert model_spec is not None
    assert model_spec.model_kind == "vlm"
    assert model_spec.runtime_mode == common_pb2.RUNTIME_MODE_ADAPTER_BACKED
    assert model_spec.ext["melix.adapter_scope"] == "text_backbone"
    assert model_spec.ext["melix.training_surface"] == "text_backbone"
    assert model_spec.ext["melix.component_model_type"] == "gemma4_text"
    assert model_spec.ext["melix.component_family"] == "gemma"
    assert model_spec.ext["melix.component_model_path"] == source_model.model_path
    assert model_spec.ext["melix.lora.adapter_scope"] == "text_backbone"
    assert model_spec.ext["melix.lora.training_surface"] == "text_backbone"
    assert model_spec.ext["melix.lora.component_model_type"] == "gemma4_text"
    assert model_spec.ext["melix.lora.family_id"] == "gemma"
    assert model_spec.ext["melix.lora.base_model_path"] == source_model.model_path
    assert model_spec.ext["melix.adapter_runtime.base_reuse_key"] == "base-key-123"
    assert model_spec.ext["melix.adapter_runtime.adapter_isolation_key"] == "adapter-key-456"
    assert model_spec.ext["melix.adapter_runtime.switch_mode"] == "base_reuse_adapter_swap"
    assert model_spec.ext["melix.adapter_runtime.sharing_policy"] == "shared_base_isolated_adapter"
    assert model_spec.ext["melix.adapter_runtime.compatibility_status"] == "compatible"


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


def test_job_registry_snapshot_records_multimodal_publish_lineage_for_derived_models() -> None:
    registry = ModelOpsJobRegistry()

    train_job = registry.start("train_lora", "melix-dev-text", "/runtime/train")
    adapter_manifest_path = "/runtime/train/train_lora.adapter.json"
    registry.attach_manifest(
        train_job.job_id,
        json.dumps({"adapter_name": "adapter-vlm", "adapter_set_hash": "vlm-hash-b"}),
    )
    registry.complete(train_job.job_id, adapter_manifest_path)

    activation_job = registry.start("activate_adapter", "melix-dev-text", "/runtime/activate")
    activation_manifest_path = "/runtime/activate/melix-dev-vlm/manifest.json"
    registry.attach_manifest(
        activation_job.job_id,
        json.dumps(
            {
                "adapter_name": "adapter-vlm",
                "adapter_manifest_path": adapter_manifest_path,
                "adapter_set_hash": "vlm-hash-b",
                "derived_model_id": "melix-dev-vlm",
                "derived_model_path": "/runtime/activate/melix-dev-vlm",
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
                "published_repo": "melix/models/melix-dev-vlm",
                "upload_backend": "huggingface_hub",
                "export_artifact_kind": "merged_export",
                "distribution_contract": "merged_multimodal",
                "processor_config_files": ["processor_config.json"],
                "parent_lineage": {
                    "local_artifact_path": "/runtime/activate/melix-dev-vlm",
                    "local_manifest_path": activation_manifest_path,
                    "source_job_id": activation_job.job_id,
                    "source_adapter_job_id": train_job.job_id,
                    "activation_mode": "fused_derived_model",
                    "derived_model_id": "melix-dev-vlm",
                },
            }
        ),
    )
    registry.complete(publish_job.job_id, "/runtime/upload/upload.receipt.json")

    snapshot = registry.snapshot()

    publish = next(p for p in snapshot["publishes"] if p["job_id"] == publish_job.job_id)
    assert publish["distribution_contract"] == "merged_multimodal"
    assert publish["processor_config_files"] == ["processor_config.json"]

    derived_model = snapshot["derived_models"][0]
    assert derived_model["published_repo"] == "melix/models/melix-dev-vlm"
    assert derived_model["distribution_contract"] == "merged_multimodal"
    assert derived_model["processor_config_files"] == ["processor_config.json"]
    assert derived_model["published_state"] == "published"


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
    assert bench_events[-1].completed.evidence_path.endswith("run-evidence.json")
    report = Path(bench_events[-1].completed.report_path).read_text(encoding="utf-8")
    assert "# Melix Bench" in report
    assert "bench.smoke.ttft_ms" in report


def test_run_bench_measures_runtime_behavior_from_loaded_backend(tmp_path: Path) -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=FastBenchmarkBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    loaded = registry.load_model(WorkerModelCatalog.dev_text_model())
    service = build_service(tmp_path, registry=registry)
    service._core._benchmark_suite_catalog = BenchmarkSuiteCatalog(
        hf_dataset_fetcher=FakeBenchmarkHFDatasetFetcher()
    )

    events = list(
        service.RunBench(
            maintenance_pb2.RunBenchRequest(
                model_handle=loaded.handle,
                suites=["smoke"],
                parameters={"require_live_model": "true"},
            ),
            context=None,
        )
    )

    report_path = Path(events[-1].completed.report_path)
    evidence_path = Path(events[-1].completed.evidence_path)
    run_dir = report_path.parent
    summary = json.loads((run_dir / "bench-summary.json").read_text(encoding="utf-8"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    report = report_path.read_text(encoding="utf-8")

    assert evidence_path == run_dir / "run-evidence.json"
    assert evidence["run_id"] == events[0].started.job_id
    phases = [probe["phase"] for probe in evidence["probe_timeline"]]
    assert phases[0] == "worker_dispatch"
    assert "runtime_prepare" in phases
    assert "prefill" in phases
    assert "decode" in phases
    assert phases[-1] == "artifact_write"
    assert evidence["telemetry_summary"]["collector_status"] == "collected"
    assert evidence["telemetry_summary"]["time_series_path"] == "telemetry-samples.jsonl"
    assert evidence["model_memory_summary"]["runtime_model_handle"] == loaded.handle
    assert evidence["model_memory_summary"]["loaded_model_estimated_resident_bytes"] == loaded.estimated_resident_bytes
    assert evidence["model_memory_summary"]["runtime_stats_model_resident_bytes"] == loaded.estimated_resident_bytes
    assert evidence["model_memory_summary"]["load_triggered_by_run"] is False
    assert summary["parameters"]["runtime_live_model"] == "true"
    assert summary["parameters"]["runtime_name"] == "fast-benchmark"
    assert summary["parameters"]["runtime_model_handle"] == loaded.handle
    assert "runtime_name: fast-benchmark" in report
    assert "## Model Memory" in report
    assert f"runtime_model_handle: {loaded.handle}" in report
    assert "runtime_stats_model_resident_bytes: 1024" in report


def test_bench_events_defaults_to_evidence_probe_policy(tmp_path: Path) -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=FastBenchmarkBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    loaded = registry.load_model(WorkerModelCatalog.dev_text_model())
    core = MaintenanceCore(
        registry,
        jobs_root=tmp_path / "model-ops",
        benchmark_suite_catalog=BenchmarkSuiteCatalog(
            hf_dataset_fetcher=FakeBenchmarkHFDatasetFetcher()
        ),
    )

    list(
        core.bench_events(
            maintenance_pb2.RunBenchRequest(
                model_handle=loaded.handle,
                suites=["smoke"],
                parameters={"require_live_model": "true"},
            )
        )
    )

    assert type(core._benchmark_store._telemetry_collector).__name__ == "AppleSiliconTelemetryCollector"


def test_run_bench_persists_report_without_reading_report_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=FastBenchmarkBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    loaded = registry.load_model(WorkerModelCatalog.dev_text_model())
    service = build_service(tmp_path, registry=registry)
    service._core._benchmark_suite_catalog = BenchmarkSuiteCatalog(
        hf_dataset_fetcher=FakeBenchmarkHFDatasetFetcher()
    )

    original_read_text = Path.read_text

    def guarded_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "bench-report.md" and self.parent.name == "model-ops-0001":
            raise AssertionError("RunBench should reuse in-memory report markdown instead of rereading bench-report.md")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    events = list(
        service.RunBench(
            maintenance_pb2.RunBenchRequest(
                model_handle=loaded.handle,
                suites=["smoke"],
                parameters={"require_live_model": "true"},
            ),
            context=None,
        )
    )

    report_path = Path(events[-1].completed.report_path)
    evidence_path = Path(events[-1].completed.evidence_path)
    report = original_read_text(report_path, encoding="utf-8")

    assert report_path.name == "bench-report.md"
    assert evidence_path.name == "run-evidence.json"
    assert "# Melix Bench" in report
    assert "runtime_name: fast-benchmark" in report


def test_text_bench_cache_warmups_reuse_base_request_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=FastBenchmarkBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    loaded = registry.load_model(WorkerModelCatalog.dev_text_model())
    service = build_service(tmp_path, registry=registry)
    core = service._core
    suite = SimpleNamespace(suite_id="smoke")
    request_id_calls: list[dict[str, object]] = []
    warmup_request_ids: list[str] = []
    measured_request_ids: list[str] = []
    original_start_request = registry.start_request

    def tracked_request_id(**kwargs: object) -> str:
        request_id_calls.append(dict(kwargs))
        return f"bench-request-{len(request_id_calls)}"

    def capture_warmup_request(*, request_id: str, **kwargs: object) -> None:
        _ = kwargs
        warmup_request_ids.append(request_id)

    def capture_measured_request(*, request_id: str, runtime_kind: str):
        measured_request_ids.append(request_id)
        return original_start_request(request_id=request_id, runtime_kind=runtime_kind)

    monkeypatch.setattr(MaintenanceCore, "_benchmark_request_id", staticmethod(tracked_request_id))
    monkeypatch.setattr(core, "_benchmark_warmup_text_request", capture_warmup_request)
    monkeypatch.setattr(registry, "start_request", capture_measured_request)

    for cache_profile, expected_warmup_suffix in (
        ("warm", "::warmup"),
        ("partial_prefix", "::partial_prefix"),
    ):
        sample = core._measure_text_bench_sample(
            loaded_model=loaded,
            suite=suite,
            prompt="alpha beta gamma delta",
            parameters={},
            context_length=16,
            repeat_index=len(request_id_calls),
            batch_size=1,
            cache_profile=cache_profile,
            reasoning_mode="default",
            structured_output_mode="plain_text",
        )

        assert sample.cache_hit is True
        assert warmup_request_ids[-1] == f"bench-request-{len(request_id_calls)}{expected_warmup_suffix}"
        assert request_id_calls[-1]["cache_profile"] == cache_profile

    assert len(request_id_calls) == 2
    assert warmup_request_ids == ["bench-request-1::warmup", "bench-request-2::partial_prefix"]
    assert measured_request_ids == ["bench-request-1", "bench-request-2"]


def test_percentiles_reuse_one_sorted_vector_and_preserve_interpolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_sorted = builtins.sorted
    sorted_calls: list[list[float]] = []

    def tracked_sorted(values: list[float], *args: object, **kwargs: object) -> list[float]:
        ordered = original_sorted(values, *args, **kwargs)
        sorted_calls.append(list(ordered))
        return ordered

    monkeypatch.setattr(builtins, "sorted", tracked_sorted)

    values = [5.0, 1.0, 7.0, 9.0]

    assert MaintenanceCore._percentiles(values) == ()
    assert MaintenanceCore._percentiles([], 50.0, 95.0) == (0.0, 0.0)
    assert MaintenanceCore._percentiles(values, 50.0, 95.0) == (6.0, 8.7)
    assert MaintenanceCore._percentiles(values, -25.0, 125.0) == (1.0, 9.0)
    assert MaintenanceCore._percentile(values, 95.0) == 8.7
    assert sorted_calls == [
        [1.0, 5.0, 7.0, 9.0],
        [1.0, 5.0, 7.0, 9.0],
        [1.0, 5.0, 7.0, 9.0],
    ]


def test_run_bench_latency_and_summary_reuse_single_sorted_request_latency_vector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=FastBenchmarkBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    loaded = registry.load_model(WorkerModelCatalog.dev_text_model())
    service = build_service(tmp_path, registry=registry)
    service._core._benchmark_suite_catalog = BenchmarkSuiteCatalog(
        hf_dataset_fetcher=FakeBenchmarkHFDatasetFetcher()
    )

    monkeypatch.setattr(
        MaintenanceCore,
        "_percentile",
        staticmethod(lambda values, percentile: (_ for _ in ()).throw(AssertionError("legacy percentile helper should not run"))),
    )

    events = list(
        service.RunBench(
            maintenance_pb2.RunBenchRequest(
                model_handle=loaded.handle,
                suites=["latency"],
                parameters={"require_live_model": "true"},
            ),
            context=None,
        )
    )

    metrics = {
        event.metric.name: event.metric.value
        for event in events
        if event.HasField("metric")
    }

    assert metrics["bench.latency.p95_ms"] >= metrics["bench.latency.p50_ms"] >= 0.0


def test_run_bench_matrix_reuses_single_sorted_latency_vectors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=RecordingBenchmarkBackend()),
        model_catalog=WorkerModelCatalog(environment={}),
    )
    service = build_service(tmp_path, registry=registry)

    monkeypatch.setattr(
        MaintenanceCore,
        "_percentile",
        staticmethod(
            lambda values, percentile: 9.2
            if percentile == 95.0
            else (_ for _ in ()).throw(AssertionError("matrix percentile reuse should only leave the queue-wait p95 path"))
        ),
    )

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

    assert len(response.summary_rows) == 2


def test_measure_vlm_latency_metrics_reuse_single_sorted_total_latency_vector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core = MaintenanceCore.__new__(MaintenanceCore)
    samples = [
        BenchSample(ttft_ms=12.0, total_latency_ms=40.0, completion_tokens=8),
        BenchSample(ttft_ms=14.0, total_latency_ms=80.0, completion_tokens=8),
        BenchSample(ttft_ms=18.0, total_latency_ms=120.0, completion_tokens=8),
        BenchSample(ttft_ms=20.0, total_latency_ms=160.0, completion_tokens=8),
    ]
    monkeypatch.setattr(
        core,
        "_measure_vlm_bench_sample",
        lambda **_kwargs: samples.pop(0),
    )
    monkeypatch.setattr(
        MaintenanceCore,
        "_percentile",
        staticmethod(lambda values, percentile: (_ for _ in ()).throw(AssertionError("legacy percentile helper should not run"))),
    )

    metrics = core._measure_vlm_bench_metrics(
        loaded_model=SimpleNamespace(runtime_model={}),
        suite=SimpleNamespace(suite_id="latency", cases=(object(), object(), object(), object())),
        parameters={},
    )

    metric_values = {metric.name: metric.value for metric in metrics}
    assert metric_values["bench.latency.image_p50_ms"] == 100.0
    assert metric_values["bench.latency.image_p95_ms"] == 154.0


def test_image_latency_metrics_reuse_single_sorted_job_latency_vector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core = MaintenanceCore.__new__(MaintenanceCore)
    monkeypatch.setattr(
        MaintenanceCore,
        "_percentile",
        staticmethod(lambda values, percentile: (_ for _ in ()).throw(AssertionError("legacy percentile helper should not run"))),
    )

    metrics = core._image_metrics_for_suite(
        suite=SimpleNamespace(suite_id="latency"),
        samples=[
            ImageBenchSample(latency_ms=12.0, artifact_publish_ms=2.0, output_bytes=256),
            ImageBenchSample(latency_ms=20.0, artifact_publish_ms=3.0, output_bytes=512),
            ImageBenchSample(latency_ms=28.0, artifact_publish_ms=4.0, output_bytes=768),
            ImageBenchSample(latency_ms=40.0, artifact_publish_ms=5.0, output_bytes=1024),
        ],
    )

    metric_values = {metric.name: metric.value for metric in metrics}
    assert metric_values["bench.latency.image_job_p50_ms"] == 24.0
    assert metric_values["bench.latency.image_job_p95_ms"] == 38.2


def test_run_bench_require_live_model_rejects_deterministic_runtime(tmp_path: Path) -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=DeterministicTextBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    loaded = registry.load_model(WorkerModelCatalog.dev_text_model())
    service = build_service(tmp_path, registry=registry)

    with pytest.raises(ModelOperationError, match="requires a loaded live model runtime"):
        list(
            service.RunBench(
                maintenance_pb2.RunBenchRequest(
                    model_handle=loaded.handle,
                    suites=["smoke"],
                    parameters={"require_live_model": "true"},
                ),
                context=None,
            )
        )


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


def test_write_jsonl_rows_streams_each_row_without_joining_full_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "bench-rows.jsonl"
    writes: list[str] = []

    class RecordingFile:
        def __enter__(self) -> RecordingFile:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def write(self, chunk: str) -> int:
            writes.append(chunk)
            return len(chunk)

    def fake_open(self: Path, mode: str = "r", *args: object, **kwargs: object) -> RecordingFile:
        assert self == output_path
        assert mode == "w"
        assert kwargs.get("encoding") == "utf-8"
        return RecordingFile()

    monkeypatch.setattr(Path, "open", fake_open)

    maintenance_core_module._write_jsonl_rows(
        output_path,
        [
            {"suite": "smoke", "ttft_ms": 10.0},
            {"suite": "latency", "ttft_ms": 20.0},
        ],
    )

    assert writes == [
        json.dumps({"suite": "smoke", "ttft_ms": 10.0}) + "\n",
        json.dumps({"suite": "latency", "ttft_ms": 20.0}) + "\n",
    ]


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


def test_current_process_rss_bytes_uses_resource_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("missing proc")))
    monkeypatch.setattr(
        maintenance_core_module.subprocess,
        "check_output",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("ps unavailable")),
    )
    monkeypatch.setattr(maintenance_core_module.sys, "platform", "darwin")
    monkeypatch.setattr(
        maintenance_core_module.resource,
        "getrusage",
        lambda _kind: SimpleNamespace(ru_maxrss=1234),
    )

    assert MaintenanceCore._current_process_rss_bytes() == 1234


def test_current_process_rss_bytes_returns_zero_when_fallback_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("missing proc")))
    monkeypatch.setattr(
        maintenance_core_module.subprocess,
        "check_output",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("ps unavailable")),
    )
    monkeypatch.setattr(
        maintenance_core_module.resource,
        "getrusage",
        lambda _kind: (_ for _ in ()).throw(RuntimeError("resource unavailable")),
    )

    assert MaintenanceCore._current_process_rss_bytes() == 0


def test_run_bench_records_lazy_model_load_memory_summary(tmp_path: Path) -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=FastBenchmarkBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    service = build_service(tmp_path, registry=registry)

    events = list(
        service.RunBench(
            maintenance_pb2.RunBenchRequest(
                model_handle="melix-dev-text",
                suites=["smoke"],
            ),
            context=None,
        )
    )

    evidence_path = Path(events[-1].completed.evidence_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    memory = evidence["model_memory_summary"]

    assert memory["runtime_model_handle"].startswith("melix-dev-text::")
    assert memory["runtime_model_id"] == "melix-dev-text"
    assert memory["loaded_model_estimated_resident_bytes"] > 0
    assert memory["runtime_stats_model_resident_bytes"] >= memory["loaded_model_estimated_resident_bytes"]
    assert memory["load_triggered_by_run"] is True
    assert memory["load_rss_after_bytes"] >= 0
    assert memory["load_rss_delta_bytes"] >= 0


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
    assert sample.prompt_tokens == 16
    assert resolved_suite.sample_size == 1
    assert resolved_suite.batch_factor == 1
    assert MaintenanceCore._benchmark_max_output_tokens({"max_output_tokens": "oops"}) == 8
    assert MaintenanceCore._vlm_fast_path_bench_metrics(suite_id="smoke", samples=[]) == []


def test_vlm_fast_path_bench_metrics_surfaces_mixed_decode_modes() -> None:
    metrics = MaintenanceCore._vlm_fast_path_bench_metrics(
        suite_id="smoke",
        samples=[
            maintenance_core_module.BenchSample(
                ttft_ms=10.0,
                total_latency_ms=20.0,
                completion_tokens=2,
                multimodal_decode_mode="single_stream",
            ),
            maintenance_core_module.BenchSample(
                ttft_ms=8.0,
                total_latency_ms=16.0,
                completion_tokens=2,
                multimodal_decode_mode="image_cache_reuse",
            ),
        ],
    )

    metrics_by_name = {metric.name: metric for metric in metrics}
    assert metrics_by_name["bench.smoke.multimodal_decode_mode"].value == 5.0


def test_vlm_fast_path_bench_metrics_encode_text_only_batch_generator() -> None:
    metrics = MaintenanceCore._vlm_fast_path_bench_metrics(
        suite_id="smoke",
        samples=[
            maintenance_core_module.BenchSample(
                ttft_ms=10.0,
                total_latency_ms=20.0,
                completion_tokens=2,
                multimodal_decode_mode="text_only_batch_generator",
                multimodal_decode_sync_mode="executor_batch_generator",
            ),
        ],
    )

    metrics_by_name = {metric.name: metric for metric in metrics}
    assert metrics_by_name["bench.smoke.multimodal_decode_mode"].value == 7.0
    assert metrics_by_name["bench.smoke.multimodal_decode_sync_mode"].value == 4.0


def test_vlm_fast_path_bench_metrics_warns_for_unmapped_decode_mode(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="worker.engine.maintenance_core")

    metrics = MaintenanceCore._vlm_fast_path_bench_metrics(
        suite_id="smoke",
        samples=[
            maintenance_core_module.BenchSample(
                ttft_ms=10.0,
                total_latency_ms=20.0,
                completion_tokens=2,
                multimodal_decode_mode="future_mode",
            ),
        ],
    )

    metrics_by_name = {metric.name: metric for metric in metrics}
    assert metrics_by_name["bench.smoke.multimodal_decode_mode"].value == -1.0
    assert "unmapped categorical metric value" in caplog.text
    assert "future_mode" in caplog.text


def test_vlm_fast_path_bench_metrics_ignore_missing_probe_sentinels_in_cache_sums() -> None:
    metrics = MaintenanceCore._vlm_fast_path_bench_metrics(
        suite_id="smoke",
        samples=[
            maintenance_core_module.BenchSample(
                ttft_ms=10.0,
                total_latency_ms=20.0,
                completion_tokens=2,
                image_feature_cache_hits=-1,
                image_feature_cache_misses=-1,
            ),
            maintenance_core_module.BenchSample(
                ttft_ms=8.0,
                total_latency_ms=16.0,
                completion_tokens=2,
                image_feature_cache_hits=2,
                image_feature_cache_misses=3,
            ),
        ],
    )

    metrics_by_name = {metric.name: metric for metric in metrics}
    assert metrics_by_name["bench.smoke.image_feature_cache_hits"].value == 2.0
    assert metrics_by_name["bench.smoke.image_feature_cache_misses"].value == 3.0


def test_vlm_bench_sample_marks_missing_fast_path_probe(caplog) -> None:
    class RuntimeWithoutProbe:
        def render_prompt(self, *_args, **_kwargs):
            return "rendered"

        def generate_tokens(self, *_args, **_kwargs):
            yield SimpleNamespace(text="ok", completion_tokens=1)

    class Registry:
        def __init__(self) -> None:
            self.runtime = RuntimeWithoutProbe()

        def runtime_for_loaded_model(self, _loaded_model):
            return self.runtime

        def start_request(self, **_kwargs):
            return SimpleNamespace(cancel_event=threading.Event())

        def finish_request(self, _request_id):
            return None

    caplog.set_level(logging.DEBUG, logger="worker.engine.maintenance_core")
    core = MaintenanceCore.__new__(MaintenanceCore)
    core._registry = Registry()

    sample = core._measure_vlm_bench_sample(
        loaded_model=SimpleNamespace(
            handle="melix-dev-vlm::1",
            runtime_kind="vlm",
            runtime_model={},
        ),
        suite=SimpleNamespace(suite_id="smoke"),
        case=SimpleNamespace(prompt="what is this?", image_uris=("image.png",)),
        parameters={},
    )

    assert sample.image_feature_cache_hits == -1
    assert sample.image_feature_cache_misses == -1
    assert sample.multimodal_decode_mode == "not_reported"
    assert "without a fast-path probe" in caplog.text


def test_vlm_bench_sample_preserves_empty_success_fallback_reasons() -> None:
    class RuntimeWithSuccessProbe:
        def render_prompt(self, *_args, **_kwargs):
            return "rendered"

        def generate_tokens(self, *_args, **_kwargs):
            yield SimpleNamespace(text="ok", completion_tokens=1)

        def last_probe_snapshot(self):
            return SimpleNamespace(
                image_feature_cache_hits=1,
                image_feature_cache_misses=0,
                multimodal_decode_mode="image_cache_reuse",
                multimodal_fallback_reason="",
                multimodal_decode_sync_mode="executor_stream",
                multi_image_scatter_mode="none",
                quantized_load_mode="native_quantized",
                quantized_load_fallback_reason="",
            )

    class Registry:
        def __init__(self) -> None:
            self.runtime = RuntimeWithSuccessProbe()

        def runtime_for_loaded_model(self, _loaded_model):
            return self.runtime

        def start_request(self, **_kwargs):
            return SimpleNamespace(cancel_event=threading.Event())

        def finish_request(self, _request_id):
            return None

    core = MaintenanceCore.__new__(MaintenanceCore)
    core._registry = Registry()

    sample = core._measure_vlm_bench_sample(
        loaded_model=SimpleNamespace(
            handle="melix-dev-vlm::1",
            runtime_kind="vlm",
            runtime_model={},
        ),
        suite=SimpleNamespace(suite_id="smoke"),
        case=SimpleNamespace(prompt="what is this?", image_uris=("image.png",)),
        parameters={},
    )

    assert sample.multimodal_fallback_reason == ""
    assert sample.quantized_load_fallback_reason == ""


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


def test_benchmark_helper_parsers_cover_invalid_and_boundary_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        parameters={"context_lengths": "8, 4, 8, 4"},
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
    assert core._benchmark_batch_sizes({"batch_sizes": "2, 1, 2, 1"}) == (1, 2)
    assert core._benchmark_batch_sizes({"batch_sizes": "1, , 2"}) == (1, 2)
    assert core._benchmark_batch_sizes({"batch_size": "oops"}) == (1,)

    class CountedInt:
        def __init__(self, value: int) -> None:
            self.value = value
            self.calls = 0

        def __int__(self) -> int:
            self.calls += 1
            return self.value

    counted_ints = [CountedInt(8), CountedInt(0), CountedInt(4), CountedInt(8)]
    assert MaintenanceCore._positive_sorted_values(counted_ints, default=(32,)) == (4, 8)
    assert [value.calls for value in counted_ints] == [1, 1, 1, 1]

    class CountedString:
        def __init__(self, value: str) -> None:
            self.value = value
            self.calls = 0

        def __str__(self) -> str:
            self.calls += 1
            return self.value

    counted_strings = [CountedString(" warm "), CountedString(""), CountedString("cold")]
    assert MaintenanceCore._normalized_string_values(
        counted_strings,
        default=("default",),
    ) == ("cold", "warm")
    assert [value.calls for value in counted_strings] == [1, 1, 1]

    MaintenanceCore._shape_benchmark_prompt.cache_clear()
    MaintenanceCore._benchmark_prompt_token_count.cache_clear()
    assert core._shape_benchmark_prompt("", context_length=3) == "benchmark benchmark benchmark"
    assert core._shape_benchmark_prompt("one two three", context_length=2) == "one two"
    assert core._shape_benchmark_prompt("one two three", context_length=8) == (
        "one two three one two three one two"
    )
    shaped_repeated_prompt = core._shape_benchmark_prompt("one two", context_length=6)
    assert shaped_repeated_prompt == "one two one two one two"
    assert shaped_repeated_prompt.tokens == ("one", "two", "one", "two", "one", "two")
    assert shaped_repeated_prompt.token_count == 6
    split_tokens = shaped_repeated_prompt.split()
    assert isinstance(split_tokens, list)
    assert split_tokens == ["one", "two", "one", "two", "one", "two"]
    assert split_tokens[0] == "one"
    assert split_tokens[:2] == ["one", "two"]
    with pytest.raises(TypeError, match="immutable"):
        split_tokens.append("three")
    with pytest.raises(TypeError, match="immutable"):
        split_tokens[0] = "three"
    assert shaped_repeated_prompt.split(" ", 1) == ["one", "two one two one two"]
    assert core._benchmark_prompt_token_count(shaped_repeated_prompt) == 6

    class SplitCountingPrompt(str):
        def __new__(cls, value: str) -> "SplitCountingPrompt":
            instance = str.__new__(cls, value)
            instance.split_calls = 0
            return instance

        def split(self, *args: object, **kwargs: object) -> list[str]:
            self.split_calls += 1
            return super().split(*args, **kwargs)

    normalized_prompt = SplitCountingPrompt("one two three")
    assert core._benchmark_prompt_token_count(normalized_prompt) == 3
    assert normalized_prompt.split_calls == 0
    fallback_prompt = SplitCountingPrompt("one\ttwo  three")
    assert core._benchmark_whitespace_token_count(fallback_prompt) == 3
    assert fallback_prompt.split_calls == 1
    assert core._benchmark_prompt_token_count(fallback_prompt) == 3
    assert core._benchmark_prompt_token_count(fallback_prompt) == 3
    assert fallback_prompt.split_calls == 2
    assert normalized_prompt.split_calls == 0
    unicode_space_prompt = SplitCountingPrompt("one\u2003two three")
    assert core._benchmark_whitespace_token_count(unicode_space_prompt) == 3
    assert unicode_space_prompt.split_calls == 1
    default_prompt_suite = SimpleNamespace(prompt_batches=(normalized_prompt,), title="unused")

    class EmptyTrackingParameters(dict[str, str]):
        def __init__(self) -> None:
            super().__init__()
            self.get_calls = 0

        def get(
            self,
            key: str,
            default: Any = None,
        ) -> Any:  # pragma: no cover - proves fast path skips lookup
            self.get_calls += 1
            return super().get(key, default)

    empty_tracking_parameters = EmptyTrackingParameters()
    assert MaintenanceCore._benchmark_context_lengths(
        suite=default_prompt_suite,  # type: ignore[arg-type]
        parameters=empty_tracking_parameters,
    ) == (3,)
    assert empty_tracking_parameters.get_calls == 0
    assert normalized_prompt.split_calls == 0
    assert MaintenanceCore._benchmark_context_lengths(suite=default_prompt_suite, parameters={}) == (
        3,
    )
    assert normalized_prompt.split_calls == 0

    counted_context_calls = 0
    original_counter = MaintenanceCore._benchmark_prompt_token_count

    def counted_prompt_token_count(prompt: str) -> int:
        nonlocal counted_context_calls
        counted_context_calls += 1
        return original_counter(prompt)

    monkeypatch.setattr(
        MaintenanceCore,
        "_benchmark_prompt_token_count",
        staticmethod(counted_prompt_token_count),
    )
    assert MaintenanceCore._benchmark_context_lengths(suite=default_prompt_suite, parameters={}) == (
        3,
    )
    assert counted_context_calls == 1
    default_shaped_suite = SimpleNamespace(prompt_batches=(shaped_repeated_prompt,), title="unused")
    assert MaintenanceCore._benchmark_context_lengths(suite=default_shaped_suite, parameters={}) == (
        6,
    )
    assert core._benchmark_prompt_token_count("") == 1
    assert core._benchmark_prompt_token_count("one two") == 2
    assert core._shape_benchmark_prompt("one two", context_length=6) == "one two one two one two"
    assert MaintenanceCore._shape_benchmark_prompt.cache_info().hits == 1
    shaped_long_prompt = core._shape_benchmark_prompt("alpha beta", context_length=128)
    assert shaped_long_prompt.token_count == 128
    assert shaped_long_prompt._tokens is None
    assert shaped_long_prompt.tokens[:4] == ("alpha", "beta", "alpha", "beta")
    assert shaped_long_prompt.token_count == 128
    MaintenanceCore._shape_benchmark_prompt.cache_clear()

    shape_calls: list[tuple[str, int]] = []
    original_shape_prompt = MaintenanceCore._shape_benchmark_prompt

    def tracked_shape_prompt(prompt: str, *, context_length: int) -> str:
        shape_calls.append((prompt, context_length))
        return original_shape_prompt(prompt, context_length=context_length)

    monkeypatch.setattr(MaintenanceCore, "_shape_benchmark_prompt", staticmethod(tracked_shape_prompt))
    loaded = core._registry.load_model(WorkerModelCatalog.dev_text_model())
    _, context_rows, _, _ = core._measure_text_bench_metrics(
        loaded_model=loaded,
        suite=suite,
        parameters={"context_lengths": "8", "repeats": "3", "max_output_tokens": "1"},
        job_id="shape-reuse",
        source_repo="local",
        task_kind="text-generation",
    )
    assert len(context_rows) == 3
    assert shape_calls == [(suite.cases[0].prompt, 8)]

    agentic_case = SimpleNamespace(
        tool_calls=[
            {"id": "visit-1", "name": "visit", "arguments": {"url": "fixture://bench"}}
        ],
        tool_fixture_context={
            "pages": {"fixture://bench": {"text": "Benchmark page."}},
        },
    )
    agentic_tool_run = core._agentic_tool_run_for_benchmark_case(agentic_case)
    assert agentic_tool_run.metrics["agentic_tool.call_count"] == 1.0
    agentic_kwargs = core._agentic_tool_kwargs(agentic_tool_run)
    assert agentic_kwargs["agentic_tool_calls"][0]["name"] == "visit"
    assert agentic_kwargs["agentic_tool_observations"][0]["payload"]["text"] == "Benchmark page."
    assert core._agentic_tool_run_for_benchmark_case(SimpleNamespace(tool_calls=[])) is None

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
    assert response.models[0].local_fit_status == "good"
    assert response.models[0].local_fit_reasons == [
        "MLX-compatible Hub metadata found.",
        "Estimated resident bytes are within the memory comfort budget.",
    ]
    assert response.models[0].estimated_artifact_bytes == 4_200_000_000
    assert response.models[0].estimated_resident_bytes == 5_670_000_000
    assert response.models[0].parameter_count == 7_000_000_000
    assert response.models[0].quantization_summary == "4-bit"
    assert response.models[0].gated is False
    assert response.models[0].recommended_action == "download"


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
    assert response.card.local_fit_status == "heavy"
    assert response.card.local_fit_reasons == [
        "MLX-compatible Hub metadata found.",
        "Estimated resident bytes exceed the memory comfort budget.",
    ]
    assert response.card.estimated_artifact_bytes == 52_000_000_000
    assert response.card.estimated_resident_bytes == 70_200_000_000
    assert response.card.parameter_count == 72_000_000_000
    assert response.card.quantization_summary == "4-bit"
    assert response.card.gated is False
    assert response.card.recommended_action == "review_risk"


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
    evidence_path = Path(events[-1].completed.evidence_path)
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
    expected_job_parameters = {
        **bench_parameters,
        "runtime_live_model": "false",
        "runtime_model_handle": "melix-dev-text::1",
        "runtime_kind": "text",
        "runtime_name": "deterministic-text",
        "runtime_model_id": "melix-dev-text",
        "runtime_model_path": "models/melix-dev-text",
        "runtime_source_kind": "",
        "runtime_source_repo": "",
    }
    job_manifest = run_dir / "bench-job.json"
    summary_manifest = run_dir / "bench-summary.json"
    context_rows_path = run_dir / "bench-context-rows.jsonl"
    batch_rows_path = run_dir / "bench-batch-rows.jsonl"
    smoke_result = run_dir / "bench-result-smoke.json"
    latency_result = run_dir / "bench-result-latency.json"
    run_evidence = run_dir / "run-evidence.json"

    assert job_manifest.exists() is True
    assert summary_manifest.exists() is True
    assert context_rows_path.exists() is True
    assert batch_rows_path.exists() is True
    assert smoke_result.exists() is True
    assert latency_result.exists() is True
    assert run_evidence.exists() is True
    assert report_path.parent == run_dir
    assert evidence_path == run_evidence

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
            parameters=expected_job_parameters,
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
        model_catalog=WorkerModelCatalog(environment={}),
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
    assert job_payload["parameters"]["runtime_kind"] == "text"
    assert job_payload["parameters"]["runtime_model_id"] == "melix-dev-text"
    assert [row["context_length"] for row in summary_rows] == [256, 1024]
    assert len(request_rows) == 8
    assert {row["cell_id"] for row in request_rows} == {"cell-1", "cell-2"}
    assert all(row["status"] == "completed" for row in request_rows)
    assert all(row["speculative_acceptance_rate"] == 0.75 for row in request_rows)
    assert all(row["speculative_rejected_tokens"] == 1 for row in request_rows)
    assert all(row["speculative_draft_model_configured"] is True for row in request_rows)
    assert all(row["dflash_enabled"] is True for row in request_rows)
    assert all(row["dflash_rollback_count"] == 1 for row in request_rows)


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
    assert request_rows[0]["error_stage"] == "runtime"


def test_run_bench_matrix_records_failure_stage_from_sampling_error(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    sample_error = ModelOperationError(
        code="benchmark_failed",
        message="forced prompt render failure",
        details={"error_stage": "prompt_render"},
    )
    service._core._measure_benchmark_matrix_sample = lambda **kwargs: (_ for _ in ()).throw(  # type: ignore[method-assign]
        sample_error
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

    run_dir = tmp_path / "model-ops" / "bench" / "matrix-runs" / response.job.job_id
    request_rows = [
        json.loads(line)
        for line in (run_dir / "bench-matrix-requests.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(request_rows) == 1
    assert request_rows[0]["status"] == "failed"
    assert request_rows[0]["error_code"] == "benchmark_failed"
    assert request_rows[0]["error_stage"] == "prompt_render"


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


def test_run_bench_matrix_preserves_vlm_request_probe_fields(tmp_path: Path) -> None:
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

    def fake_measure_vlm_bench_sample(**kwargs) -> BenchSample:
        _ = kwargs
        return BenchSample(
            ttft_ms=12.3,
            total_latency_ms=45.6,
            completion_tokens=2,
            prompt_tokens=11,
            request_latency_ms=45.6,
            prefill_tokens_per_second=88.8,
            decode_tokens_per_second=99.9,
            peak_memory_bytes=1234.0,
            prompt_render_ms=7.5,
            prefill_ms=12.3,
            decode_ms=33.3,
            first_token_index=1,
            runtime_kind="vlm",
        )

    core._measure_vlm_bench_sample = fake_measure_vlm_bench_sample  # type: ignore[method-assign]

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

    run_dir = tmp_path / "model-ops" / "bench" / "matrix-runs" / response.job.job_id
    request_rows = [
        json.loads(line)
        for line in (run_dir / "bench-matrix-requests.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(request_rows) == 1
    assert request_rows[0]["prompt_render_ms"] == 7.5
    assert request_rows[0]["prefill_ms"] == 12.3
    assert request_rows[0]["decode_ms"] == 33.3
    assert request_rows[0]["first_token_index"] == 1
    assert request_rows[0]["runtime_kind"] == "vlm"


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
    assert "bench.smoke.image_feature_cache_hits" in metric_names
    assert "bench.smoke.image_feature_cache_misses" in metric_names
    assert "bench.smoke.multimodal_decode_mode" in metric_names
    assert "bench.smoke.multimodal_fallback_reason" in metric_names
    assert "bench.smoke.multimodal_decode_sync_mode" in metric_names
    assert "bench.smoke.multi_image_scatter_mode" in metric_names
    assert "bench.smoke.quantized_load_mode" in metric_names
    assert "bench.smoke.quantized_load_fallback_reason" in metric_names
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
    core._resolve_benchmark_loaded_model = lambda model_handle: BenchmarkLoadedModelResolution(  # type: ignore[method-assign]
        lazy_model_handle="",
        loaded_model=fake_loaded_model,
        load_rss_before_bytes=0,
        load_rss_after_bytes=0,
    )
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
        model_catalog=WorkerModelCatalog(environment={}),
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
        model_catalog=WorkerModelCatalog(environment={}),
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
