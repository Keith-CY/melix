from __future__ import annotations

from pathlib import Path

import pytest

from scripts.phase5_model_ops_metrics import artifact_size


def test_artifact_size_sums_directory_contents(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "quantize.artifact"
    artifact_dir.mkdir()
    (artifact_dir / "config.json").write_text("{}", encoding="utf-8")
    nested = artifact_dir / "nested"
    nested.mkdir()
    (nested / "weights.safetensors").write_bytes(b"12345")

    assert artifact_size(artifact_dir) == 7


def test_artifact_size_returns_single_file_size(tmp_path: Path) -> None:
    artifact_file = tmp_path / "download.artifact"
    artifact_file.write_bytes(b"artifact-bytes")

    assert artifact_size(artifact_file) == len(b"artifact-bytes")


def test_artifact_size_uses_scandir_stack_without_rglob(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_dir = tmp_path / "download.artifact"
    nested = artifact_dir / "nested"
    nested.mkdir(parents=True)
    (artifact_dir / "config.json").write_text("{}", encoding="utf-8")
    (nested / "weights.safetensors").write_bytes(b"12345")

    def fail_rglob(self: Path, pattern: str):
        raise AssertionError("artifact_size() should not allocate a Path.rglob() tree")

    monkeypatch.setattr(Path, "rglob", fail_rglob)

    assert artifact_size(artifact_dir) == 7
