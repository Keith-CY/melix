from __future__ import annotations

import json
from pathlib import Path
import threading
import time

from packages.protocol.python.worker.v1 import maintenance_pb2

from worker.grpc_server import WorkerMaintenanceService
from worker.model_ops.adapter_activation_pipeline import AdapterActivationPipeline
from worker.model_ops.job_registry import ModelOpsJob, ModelOpsJobRegistry
from worker.model_ops.hub_catalog import (
    HubCatalogError,
    HubModelCardRecord,
    HubModelSummaryRecord,
    HubSearchPage,
)
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
from worker.productization.benchmark_schemas import (
    build_serving_benchmark_job,
    build_serving_benchmark_results,
)
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.engine.maintenance_core import MaintenanceCore


class DeterministicLoRARunner(MLXLMRunner):
    def train_native(self, request: TrainingRequest) -> TrainingResult:
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
                tokens_seen=1024,
                examples_seen=2,
                loss_final=0.42,
                loss_best=0.33,
                learning_rate_final=1e-4,
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


def build_service(
    tmp_path: Path,
    runner: MLXLMRunner | None = None,
    hub_catalog: FakeHubCatalog | None = None,
) -> WorkerMaintenanceService:
    registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
    service = WorkerMaintenanceService(
        registry,
        jobs_root=tmp_path / "model-ops",
        hub_catalog=hub_catalog,
    )
    if runner is not None:
        service._core = MaintenanceCore(
            registry,
            jobs_root=tmp_path / "model-ops",
            hub_catalog=hub_catalog,
            lora_training_pipeline=LoRATrainingPipeline(runner=runner),
            adapter_activation_pipeline=AdapterActivationPipeline(runner=runner),
        )
    return service


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
    assert json.loads(convert_manifest.manifest_json)["operation"] == "convert"

    assert quantize_events[0].HasField("started")
    assert quantize_events[-1].HasField("completed")
    quantize_manifest = next(event.manifest for event in quantize_events if event.HasField("manifest"))
    quantize_payload = json.loads(quantize_manifest.manifest_json)
    assert quantize_payload["operation"] == "quantize"
    assert quantize_payload["weight_quant"] == "q4"
    assert quantize_payload["kv_quant"] == "q8"


def test_convert_model_supports_download_and_upload_jobs(tmp_path: Path) -> None:
    service = build_service(tmp_path)

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
                source_model=str(tmp_path / "artifact"),
                output_dir=str(tmp_path / "upload"),
                ext={"operation": "upload", "target_repo": "melix/upload-target"},
            ),
            context=None,
        )
    )

    assert download_events[-1].completed.output_path.endswith("download.artifact")
    assert upload_events[-1].completed.output_path.endswith("upload.receipt.json")


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
    assert payload["operation"] == "upload"
    assert payload["artifact_path"] == str(bundle_path)
    assert payload["artifact_kind"] == "model"
    assert payload["target_repo"] == "melix/models/melix-dev-text-q6"
    assert payload["linked_quantization"]["artifact_kind"] == "quantized_model_bundle"
    assert payload["linked_quantization"]["artifact_path"] == str(bundle_path)
    assert payload["linked_quantization"]["quant_profile_id"] == "q6"
    assert payload["linked_quantization"]["calibration_sample_count"] == 32
    assert payload["linked_quantization"]["smoke_test_passed"] is True


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

    assert payload["operation"] == "registry_snapshot"
    assert payload["model_registry"]["roots"][0]["root_id"] == "root-1"
    assert payload["model_registry"]["roots"][0]["accessible"] is True
    discovered_ids = [model["model_id"] for model in payload["model_registry"]["models"]]
    assert discovered_ids == ["mlx-community/Qwen2.5-7B-Instruct/4bit"]
    assert payload["model_registry"]["models"][0]["ext"]["melix.registry_root_id"] == "root-1"


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
    assert download["selected_mirror"] == "https://mirror.example/snapshot"
    assert download["downloaded_bytes"] == len(source_bytes)
    assert download["total_bytes"] == len(source_bytes)
    assert download["output_path"].endswith("download.artifact")
    assert download["state_path"].endswith("download.state.json")


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
                "target_repo": "melix/adapters/adapter-a",
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
            }
        ),
    )
    registry.complete(unpublished_train.job_id, "/tmp/train-b/train_lora.adapter.json")

    adapters = {adapter["adapter_name"]: adapter for adapter in registry.snapshot()["adapters"]}

    assert adapters["adapter-a"]["published_repo"] == "melix/adapters/adapter-a"
    assert adapters["adapter-a"]["publish_job_id"] == published_upload.job_id
    assert adapters["adapter-a"]["status"] == "published"
    assert adapters["adapter-b"]["published_repo"] == ""
    assert adapters["adapter-b"]["publish_job_id"] == ""
    assert adapters["adapter-b"]["status"] == "completed"


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
    assert derived_model["source_adapter_job_id"] == train_job.job_id


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
    assert rerank.ok is True
    assert rerank.model_kind == "rerank"
    assert rerank.supported_modalities == ["text"]
    assert rerank.supported_tasks == ["rerank"]
    assert rerank.supported_parsers == ["text"]
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
    assert "model_handle: melix-dev-text::1" in doctor.report_markdown
    assert "## Cache" in doctor.report_markdown
    assert "## Memory" in doctor.report_markdown

    assert bench_events[0].started.job_id == "model-ops-0001"
    assert any(event.HasField("metric") and event.metric.name == "bench.smoke.ttft_ms" for event in bench_events)
    assert any(event.HasField("metric") and event.metric.name == "bench.latency.p95_ms" for event in bench_events)
    assert bench_events[-1].completed.report_path.endswith("bench-report.md")
    report = Path(bench_events[-1].completed.report_path).read_text(encoding="utf-8")
    assert "# Melix Bench" in report
    assert "bench.smoke.ttft_ms" in report


def test_run_evaluation_returns_typed_job_and_result(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    dataset_root = tmp_path / "datasets" / "qa_smoke.dev.v1"
    dataset_root.mkdir(parents=True)
    (dataset_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.evaluation_dataset_package.v1",
                "dataset_id": "qa_smoke.dev.v1",
                "suite_id": "mmlu",
                "version": "2026-03-31",
                "sample_count": 2,
                "split": "validation",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (dataset_root / "samples.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"prompt": "2+2?", "expected": "4"}),
                json.dumps({"prompt": "3+3?", "expected": "6"}),
            ]
        )
        + "\n",
        encoding="utf-8",
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
    assert response.job.schema_version == "melix.evaluation_job.v1"
    assert response.job.model_id == "melix-dev-text"
    assert response.job.dataset_id == "qa_smoke.dev.v1"
    assert response.job.parameters["judge"] == "deterministic"
    assert len(response.results) == 1
    assert response.results[0].schema_version == "melix.evaluation_result.v1"
    assert response.results[0].dataset_id == "qa_smoke.dev.v1"
    assert response.results[0].metrics[0].name == "eval.mmlu.accuracy"
    assert response.results[0].metrics[0].value == 1.0


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
    assert response.results[0].metrics[0].value == 1.0


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
    assert response.results[0].metrics[0].name == "eval.mmlu.accuracy"
    assert response.results[0].metrics[0].value == 1.0


def test_run_evaluation_returns_typed_error_for_invalid_suite(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    response = service.RunEvaluation(
        maintenance_pb2.RunEvaluationRequest(
            model_handle="melix-dev-text::1",
            suite_id="unsupported-suite",
            dataset_id="qa_smoke.dev.v1",
            dataset_root=str(tmp_path / "missing"),
            sample_size=1,
        ),
        context=None,
    )

    assert response.ok is False
    assert response.error.code == "evaluation_failed"
    assert "Unsupported evaluation suite" in response.error.message


def test_run_bench_persists_job_manifest_and_per_suite_results(tmp_path: Path) -> None:
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

    report_path = Path(events[-1].completed.report_path)
    job_manifest = report_path.with_name("bench-job.json")
    smoke_result = report_path.with_name("bench-result-smoke.json")
    latency_result = report_path.with_name("bench-result-latency.json")

    assert job_manifest.exists() is True
    assert smoke_result.exists() is True
    assert latency_result.exists() is True

    job_payload = json.loads(job_manifest.read_text(encoding="utf-8"))
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
        suites=("smoke", "latency"),
        parameters={},
        status="completed",
        output_dir=str(report_path.parent),
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
    assert smoke_payload == expected_results["smoke"]
    assert latency_payload == expected_results["latency"]


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


def test_bench_events_vlm_mode_produces_vlm_metrics(tmp_path: Path) -> None:
    registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
    core = MaintenanceCore(registry, jobs_root=tmp_path / "model-ops")

    events = list(
        core.bench_events(
            maintenance_pb2.RunBenchRequest(
                model_handle="melix-dev-text::1",
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
    assert "benchmark_mode: vlm" in report_content


def test_bench_events_forwards_parameters_to_queue_record(tmp_path: Path) -> None:
    registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
    core = MaintenanceCore(registry, jobs_root=tmp_path / "model-ops")

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
    service = build_service(tmp_path)
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
    assert len(payload["evaluation_jobs"]) == 1
    assert json.loads(Path(response.export_path).read_text(encoding="utf-8")) == payload


def test_submit_results_returns_typed_submission_payload(tmp_path: Path) -> None:
    service = build_service(tmp_path)
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
