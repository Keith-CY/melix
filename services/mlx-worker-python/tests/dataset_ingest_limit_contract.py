from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import worker.productization.dataset_preparation as dataset_preparation_module
from worker.productization.dataset_preparation import (
    DatasetIngestRequest,
    DatasetVersionRequest,
    prepare_dataset_ingest,
    prepare_dataset_version,
)


WORKSPACE_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures/workspace/m-courtyard-smoke.dev.v1/workspace-manifest.json"
)


def exercise_dataset_ingest_limit_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_rejects_over_upload_cap_before_reading_sources(tmp_path / "over-upload", monkeypatch)
    _assert_rejects_over_source_cap_before_expensive_processing(tmp_path / "over-source")
    _assert_rejects_over_limit_settings_before_reading_sources(tmp_path / "invalid-relation", monkeypatch)
    _assert_rejects_negative_limit_settings_before_source_scan(tmp_path / "negative")
    _assert_accepted_upload_uses_bounded_source_reader(tmp_path / "accepted", monkeypatch)
    _assert_records_zero_observed_bytes_when_source_stat_fails(tmp_path / "stat-fails", monkeypatch)
    _assert_blocks_unreadable_source_and_reports_cleanup(tmp_path / "unreadable")
    _assert_cleanup_reports_failed_partial_removal(tmp_path / "cleanup-fails", monkeypatch)
    _assert_bounded_source_reader_rejects_over_cap(tmp_path / "reader-cap")
    _assert_removes_partial_segments_artifact_on_write_failure(tmp_path / "write-fails", monkeypatch)
    _assert_dataset_version_persists_ingest_limit_and_cleanup_evidence(tmp_path / "version")


def _assert_rejects_over_upload_cap_before_reading_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_root = tmp_path / "raw-inputs"
    output_root = tmp_path / "prepared"
    input_root.mkdir(parents=True)
    oversized_source = input_root / "big.txt"
    oversized_source.write_text("abcdef", encoding="utf-8")
    manifest_path = _write_ready_workspace_manifest(tmp_path)
    original_read_text = Path.read_text
    source_read_attempts: list[str] = []

    def fail_source_read(path: Path, *args: object, **kwargs: object) -> str:
        if path == oversized_source:  # pragma: no cover - failure path only
            source_read_attempts.append(str(path))
            raise AssertionError("over-limit ingest should reject before reading source text")
        return original_read_text(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_text", fail_source_read)
        receipt = prepare_dataset_ingest(
            DatasetIngestRequest(
                workspace_project_id="m-courtyard-demo",
                workspace_manifest_path=manifest_path,
                input_path=input_root,
                output_dir=output_root,
                dataset_preparation_id="prep-over-upload-cap",
                upload_cap_bytes=5,
            )
        )

    assert receipt["status"] == "blocked"
    assert receipt["upload_cap_bytes"] == 5
    assert receipt["observed_payload_bytes"] == 6
    assert receipt["source_cap_bytes"] == 0
    assert receipt["rejection_reason"] == "upload_cap_exceeded"
    assert receipt["partial_artifact_cleanup"] == {
        "status": "missing",
        "target_path": str(output_root / "segments.jsonl"),
        "removed": False,
        "error": "",
    }
    assert receipt["operator_failures"][0]["code"] == "DATASET_INGEST_UPLOAD_CAP_EXCEEDED"
    assert not (output_root / "segments.jsonl").exists()
    assert source_read_attempts == []


def _assert_rejects_over_source_cap_before_expensive_processing(tmp_path: Path) -> None:
    input_root = tmp_path / "raw-inputs"
    output_root = tmp_path / "prepared"
    input_root.mkdir(parents=True)
    (input_root / "small.txt").write_text("ok", encoding="utf-8")
    (input_root / "large.txt").write_text("abcdef", encoding="utf-8")

    receipt = prepare_dataset_ingest(
        DatasetIngestRequest(
            workspace_project_id="m-courtyard-demo",
            workspace_manifest_path=_write_ready_workspace_manifest(tmp_path),
            input_path=input_root,
            output_dir=output_root,
            dataset_preparation_id="prep-over-source-cap",
            upload_cap_bytes=100,
            source_cap_bytes=5,
        )
    )

    assert receipt["status"] == "blocked"
    assert receipt["upload_cap_bytes"] == 100
    assert receipt["observed_payload_bytes"] == 8
    assert receipt["source_cap_bytes"] == 5
    assert receipt["rejection_reason"] == "source_cap_exceeded"
    assert receipt["operator_failures"][0]["code"] == "DATASET_INGEST_SOURCE_CAP_EXCEEDED"
    assert receipt["operator_failures"][0]["path"] == "large.txt"
    assert not (output_root / "segments.jsonl").exists()


def _assert_rejects_over_limit_settings_before_reading_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_root = tmp_path / "raw-inputs"
    output_root = tmp_path / "prepared"
    input_root.mkdir(parents=True)
    source_path = input_root / "notes.txt"
    source_path.write_text("ok", encoding="utf-8")
    manifest_path = _write_ready_workspace_manifest(tmp_path)
    original_read_text = Path.read_text
    source_read_attempts: list[str] = []

    def fail_source_read(path: Path, *args: object, **kwargs: object) -> str:
        if path == source_path:  # pragma: no cover - failure path only
            source_read_attempts.append(str(path))
            raise AssertionError("invalid ingest limit settings should reject before reading source text")
        return original_read_text(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_text", fail_source_read)
        receipt = prepare_dataset_ingest(
            DatasetIngestRequest(
                workspace_project_id="m-courtyard-demo",
                workspace_manifest_path=manifest_path,
                input_path=input_root,
                output_dir=output_root,
                dataset_preparation_id="prep-invalid-limit-policy",
                upload_cap_bytes=5,
                source_cap_bytes=6,
            )
        )

    assert receipt["status"] == "blocked"
    assert receipt["upload_cap_bytes"] == 5
    assert receipt["source_cap_bytes"] == 6
    assert receipt["observed_payload_bytes"] == 0
    assert receipt["rejection_reason"] == "limit_policy_invalid"
    assert receipt["partial_artifact_cleanup"]["status"] == "missing"
    assert receipt["operator_failures"][0]["code"] == "DATASET_INGEST_LIMIT_POLICY_INVALID"
    assert not (output_root / "segments.jsonl").exists()
    assert source_read_attempts == []


def _assert_rejects_negative_limit_settings_before_source_scan(tmp_path: Path) -> None:
    input_root = tmp_path / "raw-inputs"
    output_root = tmp_path / "prepared"
    input_root.mkdir(parents=True)
    (input_root / "notes.txt").write_text("ok", encoding="utf-8")

    receipt = prepare_dataset_ingest(
        DatasetIngestRequest(
            workspace_project_id="m-courtyard-demo",
            workspace_manifest_path=_write_ready_workspace_manifest(tmp_path),
            input_path=input_root,
            output_dir=output_root,
            dataset_preparation_id="prep-negative-limit-policy",
            upload_cap_bytes=-1,
        )
    )

    assert receipt["status"] == "blocked"
    assert receipt["rejection_reason"] == "limit_policy_invalid"
    assert receipt["operator_failures"][0]["code"] == "DATASET_INGEST_LIMIT_POLICY_INVALID"
    assert receipt["observed_payload_bytes"] == 0
    assert not (output_root / "segments.jsonl").exists()


def _assert_accepted_upload_uses_bounded_source_reader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_root = tmp_path / "raw-inputs"
    output_root = tmp_path / "prepared"
    input_root.mkdir(parents=True)
    source_path = input_root / "notes.txt"
    source_path.write_text("This upload is under the configured caps.\n", encoding="utf-8")
    manifest_path = _write_ready_workspace_manifest(tmp_path)
    original_read_text = Path.read_text

    def fail_source_read(path: Path, *args: object, **kwargs: object) -> str:
        if path == source_path:  # pragma: no cover - failure path only
            raise AssertionError("accepted ingest should use the bounded source reader")
        return original_read_text(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_text", fail_source_read)
        receipt = prepare_dataset_ingest(
            DatasetIngestRequest(
                workspace_project_id="m-courtyard-demo",
                workspace_manifest_path=manifest_path,
                input_path=input_root,
                output_dir=output_root,
                dataset_preparation_id="prep-under-cap",
                upload_cap_bytes=100,
                source_cap_bytes=100,
            )
        )

    assert receipt["status"] == "ready"
    assert receipt["upload_cap_bytes"] == 100
    assert receipt["observed_payload_bytes"] == source_path.stat().st_size
    assert receipt["source_cap_bytes"] == 100
    assert receipt["rejection_reason"] == ""
    assert receipt["partial_artifact_cleanup"]["status"] == "not_needed"
    assert receipt["metrics"]["observed_payload_bytes"] == source_path.stat().st_size
    assert (output_root / "segments.jsonl").is_file()


def _assert_records_zero_observed_bytes_when_source_stat_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_root = tmp_path / "raw-inputs"
    output_root = tmp_path / "prepared"
    input_root.mkdir(parents=True)
    source_path = input_root / "notes.txt"
    source_path.write_text("Stat failures should not block readable sources.\n", encoding="utf-8")
    original_stat = Path.stat

    def fake_stat(path: Path, *args: object, **kwargs: object) -> os.stat_result:
        if path == source_path:
            raise OSError("stat denied")
        return original_stat(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "stat", fake_stat)
        receipt = prepare_dataset_ingest(
            DatasetIngestRequest(
                workspace_project_id="m-courtyard-demo",
                workspace_manifest_path=_write_ready_workspace_manifest(tmp_path),
                input_path=input_root,
                output_dir=output_root,
                dataset_preparation_id="prep-stat-failure",
                upload_cap_bytes=100,
            )
        )

    assert receipt["status"] == "ready"
    assert receipt["observed_payload_bytes"] == 0
    assert receipt["metrics"]["observed_payload_bytes"] == 0


def _assert_blocks_unreadable_source_and_reports_cleanup(tmp_path: Path) -> None:
    input_root = tmp_path / "raw-inputs"
    output_root = tmp_path / "prepared"
    input_root.mkdir(parents=True)
    (input_root / "bad.txt").write_bytes(b"\xff")

    receipt = prepare_dataset_ingest(
        DatasetIngestRequest(
            workspace_project_id="m-courtyard-demo",
            workspace_manifest_path=_write_ready_workspace_manifest(tmp_path),
            input_path=input_root,
            output_dir=output_root,
            dataset_preparation_id="prep-unreadable-source",
            upload_cap_bytes=100,
        )
    )

    assert receipt["status"] == "blocked"
    assert receipt["rejection_reason"] == "source_processing_failed"
    assert receipt["operator_failures"][0]["code"] == "DATASET_INGEST_PARSE_FAILED"
    assert receipt["partial_artifact_cleanup"]["status"] == "missing"
    assert not (output_root / "segments.jsonl").exists()


def _assert_cleanup_reports_failed_partial_removal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_path.mkdir(parents=True)
    partial_path = tmp_path / "segments.jsonl"
    partial_path.write_text('{"partial": true}\n', encoding="utf-8")
    original_unlink = Path.unlink

    def fail_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path == partial_path:
            raise OSError("locked")
        original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_unlink)
        cleanup = dataset_preparation_module._cleanup_partial_artifact(partial_path)

    assert cleanup == {
        "status": "failed",
        "target_path": str(partial_path),
        "removed": False,
        "error": "locked",
    }
    assert partial_path.exists()


def _assert_bounded_source_reader_rejects_over_cap(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True)
    source_path = tmp_path / "notes.txt"
    source_path.write_text("too large", encoding="utf-8")

    with pytest.raises(OSError, match="source exceeded configured read cap"):
        dataset_preparation_module._read_source_text(source_path, cap_bytes=1)


def _assert_removes_partial_segments_artifact_on_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_root = tmp_path / "raw-inputs"
    output_root = tmp_path / "prepared"
    input_root.mkdir(parents=True)
    (input_root / "notes.txt").write_text("Partial artifacts should be cleaned.\n", encoding="utf-8")

    def fail_after_partial_write(path: Path, rows: object) -> None:
        path.write_text('{"partial": true}\n', encoding="utf-8")
        raise OSError("disk full")

    with monkeypatch.context() as patch:
        patch.setattr(dataset_preparation_module, "_write_jsonl", fail_after_partial_write)
        receipt = prepare_dataset_ingest(
            DatasetIngestRequest(
                workspace_project_id="m-courtyard-demo",
                workspace_manifest_path=_write_ready_workspace_manifest(tmp_path),
                input_path=input_root,
                output_dir=output_root,
                dataset_preparation_id="prep-partial-cleanup",
                upload_cap_bytes=100,
            )
        )

    assert receipt["status"] == "blocked"
    assert receipt["rejection_reason"] == "segment_artifact_write_failed"
    assert receipt["partial_artifact_cleanup"] == {
        "status": "removed",
        "target_path": str(output_root / "segments.jsonl"),
        "removed": True,
        "error": "",
    }
    assert receipt["operator_failures"][0]["code"] == "DATASET_INGEST_PARSE_FAILED"
    assert not (output_root / "segments.jsonl").exists()


def _assert_dataset_version_persists_ingest_limit_and_cleanup_evidence(tmp_path: Path) -> None:
    input_root = tmp_path / "raw-inputs"
    output_root = tmp_path / "prepared"
    input_root.mkdir(parents=True)
    (input_root / "notes.txt").write_text("Alpha support answer.\n\nBeta support answer.\n", encoding="utf-8")
    ingest_receipt = prepare_dataset_ingest(
        DatasetIngestRequest(
            workspace_project_id="m-courtyard-demo",
            workspace_manifest_path=_write_ready_workspace_manifest(tmp_path),
            input_path=input_root,
            output_dir=output_root,
            dataset_preparation_id="prep-version-limit",
            segmentation=True,
            segmentation_strategy="paragraph",
            upload_cap_bytes=1024,
        )
    )
    dataset_root = tmp_path / "datasets"
    receipt_path = Path(ingest_receipt["segment_artifacts"]["receipt_path"])
    manifest_path = Path(str(ingest_receipt["workspace_manifest_path"]))

    version = prepare_dataset_version(
        DatasetVersionRequest(
            workspace_manifest_path=manifest_path,
            ingest_receipt_path=receipt_path,
            output_root=dataset_root,
            dataset_id="support-chat",
            version_id="support-chat-v1",
        )
    )
    version_path = dataset_root / "support-chat" / "versions" / "support-chat-v1" / "dataset-version.json"
    persisted = json.loads(version_path.read_text(encoding="utf-8"))

    assert version["upload_cap_bytes"] == 1024
    assert version["partial_artifact_cleanup"] == ingest_receipt["partial_artifact_cleanup"]
    assert persisted["upload_cap_bytes"] == 1024
    assert persisted["partial_artifact_cleanup"] == ingest_receipt["partial_artifact_cleanup"]


def _write_ready_workspace_manifest(
    tmp_path: Path,
    *,
    skip_roots: set[str] | None = None,
) -> Path:
    workspace_root = tmp_path / "workspace"
    manifest = json.loads(WORKSPACE_FIXTURE.read_text(encoding="utf-8"))
    workspace_root.mkdir(parents=True, exist_ok=True)
    manifest_path = workspace_root / "workspace-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    skip_roots = skip_roots or set()
    root_paths = {
        root["root_id"]: root["path"]
        for root in manifest["artifact_roots"]
        if root.get("path") and root["root_id"] not in skip_roots
    }
    for root_path in root_paths.values():
        (workspace_root / root_path).mkdir(parents=True, exist_ok=True)
    for artifact in manifest["artifacts"]:
        root_path = root_paths.get(artifact["root_id"])
        if root_path is None:
            continue
        artifact_path = workspace_root / root_path / artifact["relative_path"]
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(artifact["artifact_id"], encoding="utf-8")
    return manifest_path
