from __future__ import annotations

import json
import os
from pathlib import Path

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
        },
    )

    result = pipeline.run(request, job_id="job-resume", output_dir=output_dir)

    assert result.output_path == output_dir / "model.gguf"
    assert result.output_path.read_bytes() == b"abcdefgh"
    payload = json.loads(result.snapshots[-1].manifest_json)
    assert payload["resume_used"] is True
    assert payload["resume_from_bytes"] == 4


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
    assert cancelled["last_error"] == "download_cancelled"
    assert cancelled["artifact_integrity"]["failure_reason"] == "download_cancelled"
