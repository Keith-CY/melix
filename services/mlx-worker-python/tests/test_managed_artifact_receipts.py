from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import threading
import time
from typing import Any

from packages.protocol.python.worker.v1 import maintenance_pb2

from test_maintenance_service import _write_download_source_file, build_service
from worker.model_ops.download_pipeline import DownloadPipelineResult


def _expected_directory_snapshot_digest(root: Path) -> str:
    digest = hashlib.sha256()
    file_paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    )
    for path in file_paths:
        relative_path = path.relative_to(root).as_posix()
        file_bytes = path.read_bytes()
        digest.update(b"file\0")
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(file_bytes)).encode("ascii"))
        digest.update(b"\0")
        digest.update(file_bytes)
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


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


def test_strict_managed_download_failure_emits_integrity_receipt(tmp_path: Path) -> None:
    source_path, _ = _write_download_source_file(tmp_path, size=1024)
    output_dir = tmp_path / "strict-download"
    service = build_service(tmp_path)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="mlx-community/strict-demo",
                output_dir=str(output_dir),
                generate_manifest=True,
                ext={
                    "operation": "download",
                    "source_path": str(source_path),
                    "melix.target_scope": "hub:mlx-community/strict-demo@main",
                    "melix.operation_kind": "managed_model_install",
                    "melix.strict_install_mode": "true",
                },
            ),
            context=None,
        )
    )

    assert events[0].started.job_id
    assert events[-1].failed.error.code == "artifact_integrity_required"
    manifest_payload = json.loads(
        next(event.manifest for event in events if event.HasField("manifest")).manifest_json
    )
    assert manifest_payload["status"] == "failed"
    assert manifest_payload["terminal_state"] == "failed"
    assert manifest_payload["last_error"] == "missing_artifact_digest"
    assert manifest_payload["artifact_integrity"]["policy_present"] is False
    assert manifest_payload["artifact_integrity"]["failure_reason"] == "missing_artifact_digest"
    assert json.loads((output_dir / "download.state.json").read_text(encoding="utf-8")) == manifest_payload
    assert service._core._job_registry.snapshot()["downloads"][0]["artifact_integrity_status"] == "failed"


def test_strict_managed_hub_download_failure_emits_snapshot_digest_receipt(tmp_path: Path) -> None:
    source_dir = tmp_path / "hub-source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "config.json").write_text('{"model_type":"qwen3"}\n', encoding="utf-8")
    (source_dir / "model.safetensors").write_bytes(b"weights")
    actual_digest = _expected_directory_snapshot_digest(source_dir)
    output_dir = tmp_path / "download-managed-digest-failed"
    service = build_service(tmp_path)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                output_dir=str(output_dir),
                generate_manifest=True,
                ext={
                    "operation": "download",
                    "melix.source_kind": "hub_repo",
                    "melix.hf_repo_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    "melix.hf_revision": "main",
                    "melix.managed_import": "true",
                    "melix.strict_install_mode": "true",
                    "melix.artifact_digest": "sha256:" + ("0" * 64),
                    "source_path": str(source_dir),
                },
            ),
            context=None,
        )
    )

    assert events[-1].HasField("failed")
    assert events[-1].failed.error.code == "artifact_integrity_mismatch"
    failed_manifest = json.loads(events[-1].failed.error.details["state_json"])
    persisted_manifest = json.loads((output_dir / "download.state.json").read_text(encoding="utf-8"))
    assert failed_manifest == persisted_manifest
    assert failed_manifest["status"] == "failed"
    assert failed_manifest["terminal_state"] == "failed"
    assert failed_manifest["last_error"] == "digest_mismatch"
    assert failed_manifest["managed_model_path"] == str(source_dir.resolve())
    assert failed_manifest["artifact_integrity"]["digest"] == "sha256:" + ("0" * 64)
    assert failed_manifest["artifact_integrity"]["actual_digest"] == actual_digest
    assert failed_manifest["artifact_integrity"]["failure_reason"] == "digest_mismatch"
    assert failed_manifest["artifact_integrity"]["status"] == "failed"
    assert failed_manifest["activated"] is False
    assert service._core._job_registry.snapshot()["downloads"][0]["artifact_integrity_status"] == "failed"


def test_managed_download_registry_exposes_stale_partial_lifecycle(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    source_path, source_bytes = _write_download_source_file(tmp_path, size=1024)
    output_dir = tmp_path / "managed-stale-partial"
    output_dir.mkdir()
    partial_path = output_dir / "download.artifact.partial"
    partial_path.write_bytes(b"old-partial")
    old_timestamp = time.time() - 60
    os.utime(partial_path, (old_timestamp, old_timestamp))

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="mlx-community/stale-partial-demo",
                output_dir=str(output_dir),
                generate_manifest=True,
                ext={
                    "operation": "download",
                    "source_path": str(source_path),
                    "melix.managed_import": "true",
                    "melix.target_scope": "hub:mlx-community/stale-partial-demo@main",
                    "melix.operation_kind": "managed_model_install",
                    "melix.stale_partial_after_ms": "1",
                },
            ),
            context=None,
        )
    )

    manifest_payload = json.loads(
        [event.manifest.manifest_json for event in events if event.HasField("manifest")][-1]
    )
    download = service._core._job_registry.snapshot()["downloads"][0]
    assert Path(events[-1].completed.output_path).read_bytes() == source_bytes
    assert manifest_payload["stale_partial_removed"] is True
    assert manifest_payload["partial_lifecycle"] == "completed_activated"
    assert download["stale_partial_removed"] is True
    assert download["partial_lifecycle"] == "completed_activated"
    assert download["partial_bytes"] == 0
    assert download["resume_eligible"] is False
    assert download["activated"] is True
    assert not partial_path.exists()
