from __future__ import annotations

import json
from pathlib import Path

from packages.protocol.python.worker.v1 import maintenance_pb2

from worker.grpc_server import WorkerMaintenanceService
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
