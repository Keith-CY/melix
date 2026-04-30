from __future__ import annotations

import os
from pathlib import Path

import pytest

from worker.model_ops.download_pipeline import DownloadPipeline


def test_selected_mirror_uses_first_configured_mirror() -> None:
    assert (
        DownloadPipeline._selected_mirror({"mirror_urls": " , https://first.example, https://second.example"})
        == "https://first.example"
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
