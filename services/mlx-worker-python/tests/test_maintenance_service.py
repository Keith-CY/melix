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
