#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from packages.protocol.python.worker.v1 import maintenance_pb2
from worker.grpc_server import WorkerMaintenanceService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.productization.packaged_vlm_cache import (
    build_packaged_vlm_cache_receipt,
    packaged_vlm_artifact_specs,
)
from worker.registry import WorkerRegistry


def _write_bytes(path: Path, *, size: int, seed: int) -> bytes:
    payload = bytes((index + seed) % 251 for index in range(size))
    path.write_bytes(payload)
    return payload


def _events_manifest(events) -> dict[str, object]:
    manifests = [event.manifest.manifest_json for event in events if event.HasField("manifest")]
    if not manifests:
        return {}
    return json.loads(manifests[-1])


def _run_download(service: WorkerMaintenanceService, *, source_model: str, output_dir: Path, ext: dict[str, str]):
    request = maintenance_pb2.ConvertModelRequest(
        source_model=source_model,
        output_dir=str(output_dir),
        generate_manifest=True,
        ext={"operation": "download", **ext},
    )
    return list(service.ConvertModel(request, context=None))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="melix-packaged-vlm-cache-") as temp_dir:
        root = Path(temp_dir)
        cache_dir = root / "flat-cache"
        sources_dir = root / "sources"
        cache_dir.mkdir()
        sources_dir.mkdir()
        model_source = sources_dir / "source-model.gguf"
        projector_source = sources_dir / "source-mmproj.gguf"
        model_payload = _write_bytes(model_source, size=3072, seed=7)
        projector_payload = _write_bytes(projector_source, size=1024, seed=31)

        registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
        service = WorkerMaintenanceService(registry, jobs_root=root / "model-ops")
        model_spec, projector_spec = packaged_vlm_artifact_specs(
            model_source_path=model_source,
            projector_source_path=projector_source,
        )

        cancelled_events = _run_download(
            service,
            source_model="mlx-community/packaged-vlm-model",
            output_dir=cache_dir,
            ext={
                "source_path": str(model_spec.source_path),
                "output_filename": model_spec.output_filename,
                "chunk_bytes": "512",
                "test_cancel_after_bytes": "1024",
            },
        )
        cancelled_manifest = _events_manifest(cancelled_events)
        cancelled_partial_path = Path(str(cancelled_manifest.get("partial_path", "")))
        cancelled_partial_existed_before_resume = cancelled_partial_path.is_file()
        cancelled_partial_bytes_before_resume = (
            cancelled_partial_path.stat().st_size if cancelled_partial_existed_before_resume else 0
        )

        model_events = _run_download(
            service,
            source_model="mlx-community/packaged-vlm-model",
            output_dir=cache_dir,
            ext={
                "source_path": str(model_spec.source_path),
                "output_filename": model_spec.output_filename,
                "chunk_bytes": "512",
            },
        )
        projector_events = _run_download(
            service,
            source_model="mlx-community/packaged-vlm-projector",
            output_dir=cache_dir,
            ext={
                "source_path": str(projector_spec.source_path),
                "output_filename": projector_spec.output_filename,
                "chunk_bytes": "256",
            },
        )
        model_manifest = _events_manifest(model_events)
        projector_manifest = _events_manifest(projector_events)
        receipt = build_packaged_vlm_cache_receipt(
            cache_dir=cache_dir,
            model_manifest=model_manifest,
            projector_manifest=projector_manifest,
            cancelled_manifest=cancelled_manifest,
        )

        checks = {
            "cancel_saved_partial": cancelled_events[-1].HasField("failed")
            and cancelled_manifest.get("terminal_state") == "cancelled"
            and cancelled_partial_existed_before_resume
            and cancelled_partial_bytes_before_resume == 1024
            and cancelled_manifest.get("downloaded_bytes") == 1024,
            "model_resumed": model_events[-1].HasField("completed")
            and model_manifest.get("resume_used") is True
            and model_manifest.get("resume_from_bytes") == 1024
            and Path(str(model_manifest["output_path"])).read_bytes() == model_payload,
            "projector_detected": projector_events[-1].HasField("completed")
            and Path(str(projector_manifest["output_path"])).read_bytes() == projector_payload,
            "local_route_verified": receipt["local_route_verified"] == 1.0,
            "receipt_fields": all(
                receipt.get(key)
                for key in (
                    "model_artifact_path",
                    "companion_projector_path",
                    "cache_layout",
                    "cache_restore_status",
                    "receipt_path",
                )
            ),
        }
        result = {
            "checks": checks,
            "receipt": receipt,
            "cancelled": {
                "status": cancelled_manifest.get("status"),
                "terminal_state": cancelled_manifest.get("terminal_state"),
                "downloaded_bytes": cancelled_manifest.get("downloaded_bytes"),
                "partial_bytes_before_resume": cancelled_partial_bytes_before_resume,
            },
            "model": {
                "resume_used": model_manifest.get("resume_used"),
                "resume_from_bytes": model_manifest.get("resume_from_bytes"),
                "output_path": model_manifest.get("output_path"),
            },
            "projector": {
                "output_path": projector_manifest.get("output_path"),
            },
        }

    print(json.dumps(result, indent=2, sort_keys=True) if args.json else json.dumps(result, indent=2, sort_keys=True))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
