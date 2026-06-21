from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import time
from unittest.mock import Mock

import pytest

from packages.protocol.python.worker.v1 import maintenance_pb2
from worker.model_ops.download_pipeline import DownloadPipeline
from worker.model_ops.errors import ModelOperationError


def test_selected_mirror_uses_first_configured_mirror() -> None:
    assert (
        DownloadPipeline._selected_mirror({"mirror_urls": " , https://first.example, https://second.example"})
        == "https://first.example"
    )


def test_selected_mirror_uses_default_when_configured_mirrors_are_blank() -> None:
    assert (
        DownloadPipeline._selected_mirror({"mirror_urls": " , , "})
        == "https://huggingface.co"
    )


def test_load_model_config_payload_returns_empty_for_non_object_json(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("[]", encoding="utf-8")

    assert DownloadPipeline._load_model_config_payload(model_dir) == {}


def test_huggingface_hub_failure_detects_hub_exception_module() -> None:
    HubError = type("HubError", (Exception,), {"__module__": "huggingface_hub.errors"})

    assert DownloadPipeline._is_huggingface_hub_failure(HubError("boom")) is True


def test_directory_size_uses_scandir_stack_without_os_walk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "managed-snapshot"
    nested_dir = model_dir / "nested"
    nested_dir.mkdir(parents=True)
    (model_dir / "config.json").write_bytes(b"{}")
    (nested_dir / "weights.safetensors").write_bytes(b"weights")

    def fail_os_walk(path: str):
        raise AssertionError("expected explicit os.scandir stack, not os.walk")

    monkeypatch.setattr(os, "walk", fail_os_walk)

    assert DownloadPipeline._directory_size(model_dir) == len(b"{}") + len(b"weights")


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink support unavailable")
def test_directory_size_does_not_follow_symlinked_entries(tmp_path: Path) -> None:
    model_dir = tmp_path / "managed-snapshot"
    nested_dir = model_dir / "nested"
    nested_dir.mkdir(parents=True)
    (nested_dir / "weights.safetensors").write_bytes(b"weights")
    outside_file = tmp_path / "outside.safetensors"
    outside_file.write_bytes(b"outside")
    os.symlink(outside_file, model_dir / "linked-file.safetensors")
    os.symlink(nested_dir, model_dir / "linked-dir")

    assert DownloadPipeline._directory_size(model_dir) == len(b"weights")


def test_run_reuses_public_ext_across_many_snapshots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pipeline = DownloadPipeline()
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"abcdef")
    request = maintenance_pb2.ConvertModelRequest(
        source_model="mlx-community/demo",
        ext={
            "source_path": str(source_path),
            "chunk_bytes": "1",
            "mirror_url": "https://mirror.example/download",
            "hf_token": "secret-token",
        },
    )
    call_count = 0
    original_public_ext = DownloadPipeline._public_ext

    def tracked_public_ext(ext: dict[str, str] | object) -> dict[str, str]:
        nonlocal call_count
        call_count += 1
        return original_public_ext(ext)

    monkeypatch.setattr(DownloadPipeline, "_public_ext", staticmethod(tracked_public_ext))

    result = pipeline.run(request, job_id="job-1", output_dir=tmp_path / "output")

    assert result.output_path.read_bytes() == b"abcdef"
    assert call_count == 1
    payload = json.loads(result.snapshots[-1].manifest_json)
    assert payload["ext"] == {
        "chunk_bytes": "1",
        "mirror_url": "https://mirror.example/download",
        "source_path": str(source_path),
    }
    assert payload["status"] == "completed"
    assert payload["terminal_state"] == "completed"


def test_run_derives_partial_lifecycle_without_per_snapshot_file_stat(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pipeline = DownloadPipeline()
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"abcdef")
    request = maintenance_pb2.ConvertModelRequest(
        source_model="mlx-community/demo",
        ext={
            "source_path": str(source_path),
            "chunk_bytes": "1",
        },
    )
    partial_state = Mock(side_effect=AssertionError("snapshot hot path should not stat partial file"))
    monkeypatch.setattr(
        DownloadPipeline,
        "_partial_file_state",
        staticmethod(partial_state),
    )

    result = pipeline.run(request, job_id="job-hot-path", output_dir=tmp_path / "output")

    assert result.output_path.read_bytes() == b"abcdef"
    assert partial_state.call_count == 0
    running_payload = json.loads(result.snapshots[1].manifest_json)
    assert "partial_bytes" not in running_payload
    assert "resume_eligible" not in running_payload
    assert "partial_lifecycle" not in running_payload
    completed_payload = json.loads(result.snapshots[-1].manifest_json)
    assert "partial_bytes" not in completed_payload
    assert "partial_lifecycle" not in completed_payload


def test_run_plain_download_does_not_build_operation_receipts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pipeline = DownloadPipeline()
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"abcdef")
    request = maintenance_pb2.ConvertModelRequest(
        source_model="mlx-community/demo",
        ext={
            "source_path": str(source_path),
            "chunk_bytes": "1",
        },
    )

    artifact_integrity_receipt = Mock(
        side_effect=AssertionError("plain downloads should not build operation receipt payloads")
    )
    monkeypatch.setattr(
        DownloadPipeline,
        "_artifact_integrity_receipt",
        staticmethod(artifact_integrity_receipt),
    )

    result = pipeline.run(request, job_id="job-plain", output_dir=tmp_path / "output")

    artifact_integrity_receipt.assert_not_called()
    assert result.output_path.read_bytes() == b"abcdef"
    payload = json.loads(result.snapshots[-1].manifest_json)
    assert "artifact_integrity" not in payload
    assert "operation_id" not in payload


def test_run_retry_exhausted_path_does_not_reparse_manifest_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pipeline = DownloadPipeline()
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"abcdef")
    request = maintenance_pb2.ConvertModelRequest(
        source_model="mlx-community/demo",
        ext={
            "source_path": str(source_path),
            "chunk_bytes": "1",
            "max_retries": "0",
            "test_failures_before_success": "1",
            "test_fail_after_bytes": "1",
        },
    )

    def fail_json_loads(*args: object, **kwargs: object) -> object:  # pragma: no cover - sentinel
        raise AssertionError("retry exhaustion should not reparse terminal manifest JSON")

    monkeypatch.setattr("worker.model_ops.download_pipeline.json.loads", fail_json_loads)

    with pytest.raises(ModelOperationError) as exc_info:
        pipeline.run(request, job_id="job-2", output_dir=tmp_path / "output")

    assert exc_info.value.code == "download_retry_exhausted"
    payload = json.JSONDecoder().decode(exc_info.value.details["state_json"])
    assert payload["status"] == "failed"
    assert payload["terminal_state"] == "failed"
    assert payload["downloaded_bytes"] == 1


def test_run_preserves_cancelled_partial_with_stable_output_filename(tmp_path: Path) -> None:
    pipeline = DownloadPipeline()
    source_path = tmp_path / "source.gguf"
    source_path.write_bytes(b"abcdefgh")
    output_dir = tmp_path / "flat-cache"
    request = maintenance_pb2.ConvertModelRequest(
        source_model="mlx-community/vlm",
        ext={
            "source_path": str(source_path),
            "output_filename": "../model.gguf",
            "chunk_bytes": "2",
            "test_cancel_after_bytes": "4",
        },
    )

    with pytest.raises(ModelOperationError) as exc_info:
        pipeline.run(request, job_id="job-cancel", output_dir=output_dir)

    assert exc_info.value.code == "download_cancelled"
    payload = json.loads(exc_info.value.details["state_json"])
    assert payload["status"] == "cancelled"
    assert payload["terminal_state"] == "cancelled"
    assert payload["downloaded_bytes"] == 4
    assert payload["output_path"] == str(output_dir / "model.gguf")
    assert payload["partial_path"] == str(output_dir / "model.gguf.partial")
    assert (output_dir / "model.gguf.partial").read_bytes() == b"abcd"


def test_run_resumes_named_artifact_from_preserved_partial(tmp_path: Path) -> None:
    pipeline = DownloadPipeline()
    source_path = tmp_path / "source.gguf"
    source_path.write_bytes(b"abcdefgh")
    output_dir = tmp_path / "flat-cache"
    output_dir.mkdir()
    (output_dir / "model.gguf.partial").write_bytes(b"abcd")
    request = maintenance_pb2.ConvertModelRequest(
        source_model="mlx-community/vlm",
        ext={
            "source_path": str(source_path),
            "output_filename": "model.gguf",
            "chunk_bytes": "2",
            "melix.target_scope": "hub:mlx-community/vlm@main",
            "melix.operation_kind": "managed_model_install",
        },
    )

    result = pipeline.run(request, job_id="job-resume", output_dir=output_dir)

    assert result.output_path == output_dir / "model.gguf"
    assert result.output_path.read_bytes() == b"abcdefgh"
    payload = json.loads(result.snapshots[-1].manifest_json)
    assert payload["resume_used"] is True
    assert payload["resume_from_bytes"] == 4
    assert payload["partial_bytes"] == 0
    assert payload["resume_eligible"] is False
    assert payload["stale_partial_removed"] is False
    assert payload["partial_lifecycle"] == "completed_activated"
    assert payload["activated"] is True


def test_run_removes_stale_partial_before_resume(tmp_path: Path) -> None:
    pipeline = DownloadPipeline()
    source_path = tmp_path / "source.gguf"
    source_path.write_bytes(b"abcdefgh")
    output_dir = tmp_path / "flat-cache"
    output_dir.mkdir()
    partial_path = output_dir / "model.gguf.partial"
    partial_path.write_bytes(b"stale")
    old_timestamp = time.time() - 30
    os.utime(partial_path, (old_timestamp, old_timestamp))
    request = maintenance_pb2.ConvertModelRequest(
        source_model="mlx-community/vlm",
        ext={
            "source_path": str(source_path),
            "output_filename": "model.gguf",
            "chunk_bytes": "4",
            "melix.target_scope": "hub:mlx-community/vlm@main",
            "melix.operation_kind": "managed_model_install",
            "melix.stale_partial_after_ms": "1",
        },
    )

    result = pipeline.run(request, job_id="job-stale-partial", output_dir=output_dir)

    assert result.output_path.read_bytes() == b"abcdefgh"
    prepare_payload = json.loads(result.snapshots[0].manifest_json)
    completed_payload = json.loads(result.snapshots[-1].manifest_json)
    assert prepare_payload["partial_bytes"] == len(b"stale")
    assert prepare_payload["partial_age_ms"] >= 1
    assert prepare_payload["resume_eligible"] is False
    assert prepare_payload["stale_partial_removed"] is True
    assert prepare_payload["partial_lifecycle"] == "stale_removed"
    assert prepare_payload["activated"] is False
    assert completed_payload["resume_used"] is False
    assert completed_payload["resume_from_bytes"] == 0
    assert completed_payload["partial_bytes"] == 0
    assert completed_payload["stale_partial_removed"] is True
    assert completed_payload["partial_lifecycle"] == "completed_activated"
    assert completed_payload["activated"] is True
    assert not partial_path.exists()


def test_run_reports_new_partial_progress_after_stale_partial_removal(tmp_path: Path) -> None:
    pipeline = DownloadPipeline()
    source_path = tmp_path / "source.gguf"
    source_path.write_bytes(b"abcdefgh")
    output_dir = tmp_path / "flat-cache"
    output_dir.mkdir()
    partial_path = output_dir / "model.gguf.partial"
    partial_path.write_bytes(b"old")
    old_timestamp = time.time() - 30
    os.utime(partial_path, (old_timestamp, old_timestamp))
    request = maintenance_pb2.ConvertModelRequest(
        source_model="mlx-community/vlm",
        ext={
            "source_path": str(source_path),
            "output_filename": "model.gguf",
            "chunk_bytes": "2",
            "melix.target_scope": "hub:mlx-community/vlm@main",
            "melix.operation_kind": "managed_model_install",
            "melix.stale_partial_after_ms": "1",
        },
    )

    result = pipeline.run(request, job_id="job-stale-then-progress", output_dir=output_dir)

    progress_payload = json.loads(result.snapshots[1].manifest_json)
    assert progress_payload["downloaded_bytes"] == 2
    assert progress_payload["partial_bytes"] == 2
    assert progress_payload["resume_eligible"] is True
    assert progress_payload["stale_partial_removed"] is True
    assert progress_payload["partial_lifecycle"] == "resume_candidate"


def test_sweep_stale_partial_keeps_recent_complete_partial(tmp_path: Path) -> None:
    partial_path = tmp_path / "download.artifact.partial"
    partial_path.write_bytes(b"abcdefgh")

    removed, partial_bytes, partial_age_ms = DownloadPipeline._sweep_stale_partial(
        partial_path=partial_path,
        total_bytes=8,
        ext={"melix.stale_partial_after_ms": "60000"},
    )

    assert removed is False
    assert partial_bytes == 0
    assert partial_age_ms == 0
    assert partial_path.read_bytes() == b"abcdefgh"


def test_sweep_stale_partial_removes_oversized_partial(tmp_path: Path) -> None:
    partial_path = tmp_path / "download.artifact.partial"
    partial_path.write_bytes(b"abcdefghi")

    removed, partial_bytes, partial_age_ms = DownloadPipeline._sweep_stale_partial(
        partial_path=partial_path,
        total_bytes=8,
        ext={"melix.stale_partial_after_ms": "60000"},
    )

    assert removed is True
    assert partial_bytes == 9
    assert partial_age_ms >= 0
    assert not partial_path.exists()


def test_sweep_stale_partial_keeps_recent_partial(tmp_path: Path) -> None:
    partial_path = tmp_path / "download.artifact.partial"
    partial_path.write_bytes(b"abcd")

    removed, partial_bytes, partial_age_ms = DownloadPipeline._sweep_stale_partial(
        partial_path=partial_path,
        total_bytes=8,
        ext={"melix.stale_partial_after_ms": "60000"},
    )

    assert removed is False
    assert partial_bytes == 0
    assert partial_age_ms == 0
    assert partial_path.read_bytes() == b"abcd"


def test_managed_download_manifest_records_operation_receipt_fields(tmp_path: Path) -> None:
    pipeline = DownloadPipeline()
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"abcdef")
    request = maintenance_pb2.ConvertModelRequest(
        source_model="mlx-community/demo",
        ext={
            "source_path": str(source_path),
            "chunk_bytes": "2",
            "melix.target_scope": "hub:mlx-community/demo@main",
            "melix.operation_kind": "managed_model_install",
            "test_request_deadline_ms": "250",
            "test_slow_in_progress_ms": "500",
        },
    )

    result = pipeline.run(request, job_id="job-receipt", output_dir=tmp_path / "output")

    in_progress_payload = json.loads(result.snapshots[1].manifest_json)
    completed_payload = json.loads(result.snapshots[-1].manifest_json)
    assert in_progress_payload["status"] == "in_progress"
    assert in_progress_payload["terminal_state"] == "in_progress"
    assert in_progress_payload["timeout_ms"] == 250
    assert in_progress_payload["retry_after_ms"] == 250
    assert in_progress_payload["last_error"] == ""
    assert completed_payload["status"] == "completed"
    assert completed_payload["operation_kind"] == "managed_model_install"
    assert completed_payload["target_scope"] == "hub:mlx-community/demo@main"
    assert completed_payload["operation_id"].startswith("managed_model_install:")
    assert completed_payload["attempts"] == 1
    assert completed_payload["artifact_integrity"] == {
        "verification_mode": "receipt_fixture",
        "policy_present": True,
        "digest": "",
        "checked_at": "not_recorded",
        "failure_reason": "",
        "status": "passed",
    }


def test_strict_managed_download_requires_digest_before_materializing_artifact(tmp_path: Path) -> None:
    pipeline = DownloadPipeline()
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"abcdef")
    output_dir = tmp_path / "output"
    request = maintenance_pb2.ConvertModelRequest(
        source_model="mlx-community/demo",
        ext={
            "source_path": str(source_path),
            "melix.target_scope": "hub:mlx-community/demo@main",
            "melix.operation_kind": "managed_model_install",
            "melix.strict_install_mode": "true",
        },
    )

    with pytest.raises(ModelOperationError) as exc_info:
        pipeline.run(request, job_id="job-strict", output_dir=output_dir)

    assert exc_info.value.code == "artifact_integrity_required"
    state_payload = json.loads(exc_info.value.details["state_json"])
    assert state_payload["status"] == "failed"
    assert state_payload["terminal_state"] == "failed"
    assert state_payload["last_error"] == "missing_artifact_digest"
    assert state_payload["operation_id"].startswith("managed_model_install:")
    assert state_payload["target_scope"] == "hub:mlx-community/demo@main"
    assert state_payload["artifact_integrity"] == {
        "verification_mode": "receipt_fixture",
        "policy_present": False,
        "digest": "",
        "checked_at": "not_recorded",
        "failure_reason": "missing_artifact_digest",
        "status": "failed",
    }
    assert not (output_dir / "download.artifact").exists()
    assert not (output_dir / "download.artifact.partial").exists()


def test_strict_managed_download_with_digest_materializes_artifact(tmp_path: Path) -> None:
    pipeline = DownloadPipeline()
    source_path = tmp_path / "source.bin"
    source_bytes = b"abcdef"
    source_path.write_bytes(source_bytes)
    digest = hashlib.sha256(source_bytes).hexdigest()
    request = maintenance_pb2.ConvertModelRequest(
        source_model="mlx-community/demo",
        ext={
            "source_path": str(source_path),
            "melix.target_scope": "hub:mlx-community/demo@main",
            "melix.operation_kind": "managed_model_install",
            "melix.strict_install_mode": "true",
            "melix.artifact_digest": f"sha256:{digest}",
        },
    )

    result = pipeline.run(request, job_id="job-strict-digest", output_dir=tmp_path / "output")

    assert result.output_path.read_bytes() == source_bytes
    payload = json.loads(result.snapshots[-1].manifest_json)
    assert payload["status"] == "completed"
    assert payload["artifact_integrity"] == {
        "verification_mode": "sha256",
        "policy_present": True,
        "digest": f"sha256:{digest}",
        "actual_digest": f"sha256:{digest}",
        "checked_at": payload["artifact_integrity"]["checked_at"],
        "failure_reason": "",
        "status": "passed",
    }
    assert payload["artifact_integrity"]["checked_at"] != "not_recorded"
    assert payload["activated"] is True


def test_strict_managed_download_rejects_digest_mismatch_before_activation(tmp_path: Path) -> None:
    pipeline = DownloadPipeline()
    source_bytes = b"abcdef"
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(source_bytes)
    declared_digest = "sha256:" + ("0" * 64)
    actual_digest = f"sha256:{hashlib.sha256(source_bytes).hexdigest()}"
    output_dir = tmp_path / "output"
    request = maintenance_pb2.ConvertModelRequest(
        source_model="mlx-community/demo",
        ext={
            "source_path": str(source_path),
            "melix.target_scope": "hub:mlx-community/demo@main",
            "melix.operation_kind": "managed_model_install",
            "melix.strict_install_mode": "true",
            "melix.artifact_digest": declared_digest,
        },
    )

    with pytest.raises(ModelOperationError) as exc_info:
        pipeline.run(request, job_id="job-strict-digest-mismatch", output_dir=output_dir)

    assert exc_info.value.code == "artifact_integrity_mismatch"
    state_payload = json.loads(exc_info.value.details["state_json"])
    assert state_payload["status"] == "failed"
    assert state_payload["terminal_state"] == "failed"
    assert state_payload["last_error"] == "digest_mismatch"
    assert state_payload["artifact_integrity"] == {
        "verification_mode": "sha256",
        "policy_present": True,
        "digest": declared_digest,
        "actual_digest": actual_digest,
        "checked_at": state_payload["artifact_integrity"]["checked_at"],
        "failure_reason": "digest_mismatch",
        "status": "failed",
    }
    assert state_payload["artifact_integrity"]["checked_at"] != "not_recorded"
    assert state_payload["partial_lifecycle"] == "failed_kept_for_resume"
    assert state_payload["activated"] is False
    assert not (output_dir / "download.artifact").exists()
    assert (output_dir / "download.artifact.partial").read_bytes() == source_bytes


def test_strict_integrity_rejects_missing_actual_digest_before_activation(tmp_path: Path) -> None:
    partial_path = tmp_path / "download.artifact.partial"
    partial_path.write_bytes(b"abcdef")
    state_path = tmp_path / "state.json"
    manifest_payload = {
        "state_path": str(state_path),
        "artifact_integrity": {
            "verification_mode": "sha256",
            "policy_present": True,
            "digest": "sha256:" + ("a" * 64),
            "actual_digest": "",
            "checked_at": "2026-06-21T00:00:00Z",
            "failure_reason": "",
            "status": "passed",
        },
        "activated": False,
    }

    with pytest.raises(ModelOperationError) as exc_info:
        DownloadPipeline._raise_if_strict_integrity_mismatch(
            manifest_payload=manifest_payload,
            partial_path=partial_path,
            ext={"melix.strict_install_mode": "true"},
        )

    assert exc_info.value.code == "artifact_integrity_mismatch"
    state_payload = json.loads(exc_info.value.details["state_json"])
    assert state_payload["status"] == "failed"
    assert state_payload["terminal_state"] == "failed"
    assert state_payload["last_error"] == "digest_mismatch"
    assert state_payload["artifact_integrity"]["failure_reason"] == "digest_mismatch"
    assert state_payload["artifact_integrity"]["status"] == "failed"
    assert state_payload["activated"] is False
    assert state_payload["partial_lifecycle"] == "failed_kept_for_resume"


def test_artifact_integrity_receipt_normalizes_bare_sha256_digest() -> None:
    digest = "a" * 64

    receipt = DownloadPipeline._artifact_integrity_receipt(
        ext={"sha256": digest},
        status="pending",
    )

    assert receipt["verification_mode"] == "sha256"
    assert receipt["digest"] == f"sha256:{digest}"
    assert receipt["actual_digest"] == ""


def test_strict_managed_download_rejects_unsupported_digest_policy_before_activation(tmp_path: Path) -> None:
    pipeline = DownloadPipeline()
    source_bytes = b"abcdef"
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(source_bytes)
    output_dir = tmp_path / "output"
    request = maintenance_pb2.ConvertModelRequest(
        source_model="mlx-community/demo",
        ext={
            "source_path": str(source_path),
            "melix.target_scope": "hub:mlx-community/demo@main",
            "melix.operation_kind": "managed_model_install",
            "melix.strict_install_mode": "true",
            "melix.artifact_digest": "md5:not-supported",
        },
    )

    with pytest.raises(ModelOperationError) as exc_info:
        pipeline.run(request, job_id="job-strict-unsupported-digest", output_dir=output_dir)

    assert exc_info.value.code == "artifact_integrity_unsupported"
    state_payload = json.loads(exc_info.value.details["state_json"])
    assert state_payload["status"] == "failed"
    assert state_payload["terminal_state"] == "failed"
    assert state_payload["last_error"] == "unsupported_artifact_digest"
    assert state_payload["artifact_integrity"]["verification_mode"] == "sha256"
    assert state_payload["artifact_integrity"]["digest"] == "md5:not-supported"
    assert state_payload["artifact_integrity"]["actual_digest"] == f"sha256:{hashlib.sha256(source_bytes).hexdigest()}"
    assert state_payload["artifact_integrity"]["failure_reason"] == "unsupported_artifact_digest"
    assert state_payload["artifact_integrity"]["status"] == "failed"
    assert state_payload["activated"] is False
    assert not (output_dir / "download.artifact").exists()
    assert (output_dir / "download.artifact.partial").read_bytes() == source_bytes


def test_strict_managed_hub_import_requires_digest_before_snapshot_resolution(tmp_path: Path) -> None:
    pipeline = DownloadPipeline()
    source_dir = tmp_path / "managed-snapshot"
    source_dir.mkdir()
    (source_dir / "config.json").write_text("{}", encoding="utf-8")
    output_dir = tmp_path / "output"
    request = maintenance_pb2.ConvertModelRequest(
        source_model="mlx-community/demo",
        ext={
            "source_path": str(source_dir),
            "melix.managed_import": "true",
            "melix.source_kind": "hub_repo",
            "melix.hf_repo_id": "mlx-community/demo",
            "melix.hf_revision": "main",
            "melix.install_mode": "strict",
        },
    )

    with pytest.raises(ModelOperationError) as exc_info:
        pipeline.run(request, job_id="job-strict-hub", output_dir=output_dir)

    assert exc_info.value.code == "artifact_integrity_required"
    state_payload = json.loads((output_dir / "download.state.json").read_text(encoding="utf-8"))
    assert json.loads(exc_info.value.details["state_json"]) == state_payload
    assert state_payload["status"] == "failed"
    assert state_payload["stage"] == "strict_preflight"
    assert state_payload["target_scope"] == "hub:mlx-community/demo@main"
    assert state_payload["artifact_integrity"]["policy_present"] is False
    assert state_payload["artifact_integrity"]["failure_reason"] == "missing_artifact_digest"
    assert state_payload["output_path"] == ""
    assert state_payload["partial_path"] == ""


def test_operation_identity_respects_explicit_id_and_local_source_fallback(tmp_path: Path) -> None:
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"local")
    request = maintenance_pb2.ConvertModelRequest(
        source_model="",
        ext={
            "source_path": str(source_path),
            "melix.operation_id": "op-explicit",
            "melix.operation_kind": "artifact_import",
        },
    )

    assert DownloadPipeline.operation_identity(request) == (
        "op-explicit",
        f"local:{source_path}",
        "artifact_import",
    )


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink support unavailable")
def test_operation_identity_canonicalizes_local_source_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"local")
    link_path = tmp_path / "source-link.bin"
    os.symlink(source_path, link_path)
    monkeypatch.chdir(tmp_path)

    relative_request = maintenance_pb2.ConvertModelRequest(
        source_model="",
        ext={
            "source_path": "./source.bin",
            "melix.operation_kind": "artifact_import",
        },
    )
    symlink_request = maintenance_pb2.ConvertModelRequest(
        source_model="",
        ext={
            "source_path": str(link_path),
            "melix.operation_kind": "artifact_import",
        },
    )

    assert DownloadPipeline.operation_identity(relative_request) == DownloadPipeline.operation_identity(
        symlink_request
    )
    assert DownloadPipeline.operation_identity(relative_request)[1] == f"local:{source_path.resolve()}"


def test_receipt_eligibility_includes_all_operation_receipt_triggers() -> None:
    for ext in (
        {"melix.managed_import": "true"},
        {"melix.operation_id": "op-explicit"},
        {"melix.operation_kind": "artifact_import"},
        {"melix.target_scope": "scope-a"},
        {"melix.strict_install_mode": "true"},
        {"melix.install_mode": "strict"},
        {"melix.artifact_digest": "sha256:abc"},
        {"artifact_digest": "sha256:abc"},
        {"sha256": "abc"},
        {"test_request_deadline_ms": "250"},
    ):
        assert DownloadPipeline.uses_operation_receipt(ext) is True

    assert DownloadPipeline.uses_operation_receipt({}) is False


def test_terminal_receipts_record_stalled_and_cancelled_integrity_failures(tmp_path: Path) -> None:
    state_path = tmp_path / "download.state.json"
    base_payload = {
        "state_path": str(state_path),
        "ext": {"melix.artifact_digest": "sha256:abc"},
        "stall_reason": "no_progress_timeout",
        "partial_path": str(tmp_path / "download.artifact.partial"),
        "downloaded_bytes": 128,
        "total_bytes": 1024,
    }

    stalled = json.loads(
        DownloadPipeline._terminal_manifest_json(dict(base_payload), status="stalled")
    )
    cancelled = json.loads(
        DownloadPipeline._terminal_manifest_json(dict(base_payload), status="cancelled")
    )

    assert stalled["last_error"] == "no_progress_timeout"
    assert stalled["artifact_integrity"]["status"] == "failed"
    assert stalled["artifact_integrity"]["digest"] == "sha256:abc"
    assert stalled["partial_bytes"] == 128
    assert stalled["resume_eligible"] is True
    assert stalled["stale_partial_removed"] is False
    assert stalled["partial_lifecycle"] == "stalled_kept_for_resume"
    assert stalled["activated"] is False
    assert cancelled["last_error"] == "download_cancelled"
    assert cancelled["artifact_integrity"]["failure_reason"] == "download_cancelled"
    assert cancelled["partial_bytes"] == 128
    assert cancelled["resume_eligible"] is True
    assert cancelled["partial_lifecycle"] == "cancelled_kept_for_resume"
    assert cancelled["activated"] is False
