from __future__ import annotations

from pathlib import Path

from scripts.phase5_model_ops_metrics import artifact_size


def test_artifact_size_sums_directory_contents(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "quantize.artifact"
    artifact_dir.mkdir()
    (artifact_dir / "config.json").write_text("{}", encoding="utf-8")
    nested = artifact_dir / "nested"
    nested.mkdir()
    (nested / "weights.safetensors").write_bytes(b"12345")

    assert artifact_size(artifact_dir) == 7
