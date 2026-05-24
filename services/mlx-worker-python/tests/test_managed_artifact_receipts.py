from __future__ import annotations

import json
from pathlib import Path
import threading
from typing import Any

from packages.protocol.python.worker.v1 import maintenance_pb2

from test_maintenance_service import _write_download_source_file, build_service
from worker.model_ops.download_pipeline import DownloadPipelineResult


def test_duplicate_managed_download_reuses_scoped_operation_receipt(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    source_path, source_bytes = _write_download_source_file(tmp_path, size=1024)
    output_dir = tmp_path / "managed-duplicate"
    request = maintenance_pb2.ConvertModelRequest(
        source_model="mlx-community/duplicate-demo",
        output_dir=str(output_dir),
        generate_manifest=True,
        ext={
            "operation": "download",
            "source_path": str(source_path),
            "melix.managed_import": "true",
            "melix.target_scope": "hub:mlx-community/duplicate-demo@main",
            "melix.operation_kind": "managed_model_install",
        },
    )

    first_events = list(service.ConvertModel(request, context=None))
    second_events = list(service.ConvertModel(request, context=None))

    first_manifest = json.loads(
        [event.manifest.manifest_json for event in first_events if event.HasField("manifest")][-1]
    )
    second_manifest = json.loads(
        [event.manifest.manifest_json for event in second_events if event.HasField("manifest")][-1]
    )
    snapshot = service._core._job_registry.snapshot()

    assert first_events[-1].completed.output_path.endswith("download.artifact")
    assert Path(first_events[-1].completed.output_path).read_bytes() == source_bytes
    assert second_events[-1].completed.output_path == first_events[-1].completed.output_path
    assert second_manifest["operation_id"] == first_manifest["operation_id"]
    assert second_manifest["target_scope"] == "hub:mlx-community/duplicate-demo@main"
    assert second_manifest["attempts"] == 1
    assert len(snapshot["jobs"]) == 1
    assert len(snapshot["downloads"]) == 1


def test_managed_download_target_scope_isolates_operation_receipts(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    source_path, _ = _write_download_source_file(tmp_path, size=512)

    for scope in ("slot-a", "slot-b"):
        list(
            service.ConvertModel(
                maintenance_pb2.ConvertModelRequest(
                    source_model="mlx-community/scope-demo",
                    output_dir=str(tmp_path / f"managed-{scope}"),
                    generate_manifest=True,
                    ext={
                        "operation": "download",
                        "source_path": str(source_path),
                        "melix.managed_import": "true",
                        "melix.target_scope": scope,
                        "melix.operation_kind": "managed_model_install",
                    },
                ),
                context=None,
            )
        )

    snapshot = service._core._job_registry.snapshot()

    assert {download["target_scope"] for download in snapshot["downloads"]} == {"slot-a", "slot-b"}
    assert len({download["operation_id"] for download in snapshot["downloads"]}) == 2


def test_live_managed_download_duplicate_reuses_in_progress_operation_receipt(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    source_path, _ = _write_download_source_file(tmp_path, size=1024)
    output_dir = tmp_path / "managed-live-duplicate"
    request = maintenance_pb2.ConvertModelRequest(
        source_model="mlx-community/live-duplicate",
        output_dir=str(output_dir),
        generate_manifest=True,
        ext={
            "operation": "download",
            "source_path": str(source_path),
            "melix.managed_import": "true",
            "melix.target_scope": "hub:mlx-community/live-duplicate@main",
            "melix.operation_kind": "managed_model_install",
        },
    )
    original_run = service._core._download_pipeline.run
    first_entered_pipeline = threading.Event()
    release_first_pipeline = threading.Event()

    def blocked_run(*args: Any, **kwargs: Any) -> DownloadPipelineResult:
        first_entered_pipeline.set()
        assert release_first_pipeline.wait(timeout=5.0)
        return original_run(*args, **kwargs)

    service._core._download_pipeline.run = blocked_run  # type: ignore[method-assign]
    first_events: list[maintenance_pb2.ConvertModelEvent] = []
    first_error: list[BaseException] = []

    def run_first_request() -> None:
        try:
            first_events.extend(service.ConvertModel(request, context=None))
        except BaseException as exc:  # pragma: no cover - assertion surfaced below
            first_error.append(exc)

    first_thread = threading.Thread(target=run_first_request)
    first_thread.start()
    assert first_entered_pipeline.wait(timeout=5.0)

    second_events = list(service.ConvertModel(request, context=None))

    release_first_pipeline.set()
    first_thread.join(timeout=5.0)
    service._core._download_pipeline.run = original_run  # type: ignore[method-assign]

    assert first_error == []
    assert first_events[0].started.job_id == second_events[0].started.job_id
    assert not any(event.HasField("failed") for event in second_events)
    assert any(event.HasField("progress") for event in second_events)
    snapshot = service._core._job_registry.snapshot()
    assert len(snapshot["jobs"]) == 1
    assert len(snapshot["downloads"]) == 1
