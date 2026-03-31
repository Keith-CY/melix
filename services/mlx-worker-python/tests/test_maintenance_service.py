from __future__ import annotations

import json
from pathlib import Path
import threading
import time

from packages.protocol.python.worker.v1 import maintenance_pb2

from worker.grpc_server import WorkerMaintenanceService
from worker.model_ops.job_registry import ModelOpsJob, ModelOpsJobRegistry
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.engine.maintenance_core import MaintenanceCore


def build_service(tmp_path: Path) -> WorkerMaintenanceService:
    registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
    return WorkerMaintenanceService(registry, jobs_root=tmp_path / "model-ops")


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
    service = build_service(tmp_path)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-dev-adapter",
                    "dataset_uri": "datasets/melix-dev",
                },
            ),
            context=None,
        )
    )

    manifest = next(event.manifest for event in events if event.HasField("manifest"))
    payload = json.loads(manifest.manifest_json)

    assert events[0].started.job_id == "model-ops-0001"
    assert events[-1].completed.output_path.endswith("train_lora.adapter.json")
    assert payload["operation"] == "train_lora"
    assert payload["adapter_name"] == "melix-dev-adapter"
    assert payload["dataset_uri"] == "datasets/melix-dev"
    assert payload["training_duration_ms"] == 1420.0
    assert payload["adapter_publish_ms"] == 118.0


def test_registry_snapshot_returns_training_history_and_adapter_registry(tmp_path: Path) -> None:
    service = build_service(tmp_path)
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
                    "dataset_uri": "datasets/melix-dev",
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
