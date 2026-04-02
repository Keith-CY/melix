#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from packages.protocol.python.worker.v1 import maintenance_pb2
from worker.grpc_server import WorkerMaintenanceService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry


def _write_source(path: Path, *, size: int) -> bytes:
    payload = bytes(index % 251 for index in range(size))
    path.write_bytes(payload)
    return payload


def _latest_manifest_payload(events) -> dict[str, object]:
    manifest_json = [event.manifest.manifest_json for event in events if event.HasField("manifest")][-1]
    return json.loads(manifest_json)


def _run_download(service: WorkerMaintenanceService, **kwargs):
    request = maintenance_pb2.ConvertModelRequest(**kwargs)
    return list(service.ConvertModel(request, context=None))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="melix-m8-download-smoke-") as temp_dir:
        root = Path(temp_dir)
        registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
        service = WorkerMaintenanceService(registry, jobs_root=root / "model-ops")

        retry_source = root / "retry-source.bin"
        retry_bytes = _write_source(retry_source, size=2048)
        retry_events = _run_download(
            service,
            source_model="mlx-community/retry-smoke",
            output_dir=str(root / "retry"),
            generate_manifest=True,
            ext={
                "operation": "download",
                "source_path": str(retry_source),
                "mirror_url": "https://mirror.example/retry",
                "max_retries": "2",
                "test_failures_before_success": "2",
                "test_fail_after_bytes": "512",
            },
        )
        retry_manifest = _latest_manifest_payload(retry_events)

        resume_source = root / "resume-source.bin"
        resume_bytes = _write_source(resume_source, size=3072)
        failed_resume_events = _run_download(
            service,
            source_model="mlx-community/resume-smoke",
            output_dir=str(root / "resume"),
            generate_manifest=True,
            ext={
                "operation": "download",
                "source_path": str(resume_source),
                "mirror_url": "https://mirror.example/resume",
                "max_retries": "0",
                "test_failures_before_success": "1",
                "test_fail_after_bytes": "1024",
            },
        )
        resumed_events = _run_download(
            service,
            source_model="mlx-community/resume-smoke",
            output_dir=str(root / "resume"),
            generate_manifest=True,
            ext={
                "operation": "download",
                "source_path": str(resume_source),
                "mirror_url": "https://mirror.example/resume",
            },
        )
        failed_resume_manifest = _latest_manifest_payload(failed_resume_events)
        resumed_manifest = _latest_manifest_payload(resumed_events)

        stall_source = root / "stall-source.bin"
        _write_source(stall_source, size=2048)
        stall_events = _run_download(
            service,
            source_model="mlx-community/stall-smoke",
            output_dir=str(root / "stall"),
            generate_manifest=True,
            ext={
                "operation": "download",
                "source_path": str(stall_source),
                "stall_timeout_ms": "50",
                "max_retries": "0",
                "test_stall_after_bytes": "512",
                "test_stall_elapsed_ms": "250",
            },
        )
        stall_manifest = _latest_manifest_payload(stall_events)

        checks = {
            "retry_success": retry_events[-1].HasField("completed")
            and retry_manifest["retry_count"] == 2
            and Path(retry_events[-1].completed.output_path).read_bytes() == retry_bytes,
            "resume_success": resumed_events[-1].HasField("completed")
            and failed_resume_events[-1].HasField("failed")
            and resumed_manifest["resume_used"] is True
            and resumed_manifest["resume_from_bytes"] == 1024
            and Path(resumed_events[-1].completed.output_path).read_bytes() == resume_bytes,
            "stall_classified": stall_events[-1].HasField("failed")
            and stall_events[-1].failed.error.code == "download_stalled"
            and stall_manifest["terminal_state"] == "stalled"
            and stall_manifest["stall_reason"] == "no_progress_timeout",
        }

        result = {
            "checks": checks,
            "retry": {
                "status": retry_manifest["status"],
                "retry_count": retry_manifest["retry_count"],
                "selected_mirror": retry_manifest["selected_mirror"],
            },
            "resume": {
                "failed_status": failed_resume_manifest["status"],
                "status": resumed_manifest["status"],
                "resume_from_bytes": resumed_manifest["resume_from_bytes"],
                "resume_used": resumed_manifest["resume_used"],
            },
            "stall": {
                "status": stall_manifest["status"],
                "stall_detection_count": stall_manifest["stall_detection_count"],
                "stall_reason": stall_manifest["stall_reason"],
            },
        }

    print(json.dumps(result, indent=2, sort_keys=True) if args.json else json.dumps(result, indent=2, sort_keys=True))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
