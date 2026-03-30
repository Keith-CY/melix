from __future__ import annotations

import json
from pathlib import Path

from packages.protocol.python.worker.v1 import maintenance_pb2

from worker.grpc_server import WorkerMaintenanceService
from worker.model_ops.job_registry import ModelOpsJob, ModelOpsJobRegistry
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry


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
    assert rerank.ok is True
    assert rerank.model_kind == "rerank"
    assert missing.ok is False
    assert missing.error.code == "not_found"


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
