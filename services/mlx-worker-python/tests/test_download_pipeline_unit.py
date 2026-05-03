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
