from __future__ import annotations

from pathlib import Path

from scripts.real_model_support import (
    REAL_SMALL_TEXT_MODEL_ID,
    REAL_SMALL_TEXT_MODEL_PATH_ENV,
    resolve_real_small_text_model_path,
    resolve_real_small_text_model_source,
)


def test_real_small_model_source_prefers_valid_env_local_path(tmp_path: Path) -> None:
    model_dir = tmp_path / "qwen-real-small"
    model_dir.mkdir()

    source = resolve_real_small_text_model_source(
        environment={REAL_SMALL_TEXT_MODEL_PATH_ENV: str(model_dir)}
    )

    assert source.model_id == REAL_SMALL_TEXT_MODEL_ID
    assert source.live is False
    assert source.local_model_path == str(model_dir.resolve())
    assert source.model_path_for_runtime == str(model_dir.resolve())
    assert source.source_resolution_mode == "env_local_path"
    assert source.warnings == ()


def test_real_small_model_source_can_use_managed_model_root(tmp_path: Path) -> None:
    managed_model_dir = (
        tmp_path
        / "managed"
        / "huggingface"
        / "mlx-community"
        / "Qwen3.5-0.8B-OptiQ-4bit"
        / "main"
    )
    managed_model_dir.mkdir(parents=True)

    source = resolve_real_small_text_model_source(
        environment={"MELIX_MANAGED_MODEL_ROOT": str(tmp_path / "managed")},
    )

    assert source.live is False
    assert source.local_model_path == str(managed_model_dir.resolve())
    assert source.source_resolution_mode == "managed_model_path"


def test_real_small_model_source_can_use_huggingface_cache_when_allowed(tmp_path: Path) -> None:
    hf_home = tmp_path / "hf"
    snapshot = (
        hf_home
        / "hub"
        / "models--mlx-community--Qwen3.5-0.8B-OptiQ-4bit"
        / "snapshots"
        / "abc123"
    )
    snapshot.mkdir(parents=True)
    refs = snapshot.parents[1] / "refs"
    refs.mkdir()
    (refs / "main").write_text("abc123\n", encoding="utf-8")

    source = resolve_real_small_text_model_source(
        environment={"HF_HOME": str(hf_home)},
        allow_hf_cache=True,
    )

    assert source.live is False
    assert source.local_model_path == str(snapshot.resolve())
    assert source.source_resolution_mode == "hf_cache_snapshot"


def test_real_small_model_source_defaults_to_hub_without_local_sources(tmp_path: Path) -> None:
    hf_home = tmp_path / "hf"
    snapshot = (
        hf_home
        / "hub"
        / "models--mlx-community--Qwen3.5-0.8B-OptiQ-4bit"
        / "snapshots"
        / "abc123"
    )
    snapshot.mkdir(parents=True)
    refs = snapshot.parents[1] / "refs"
    refs.mkdir()
    (refs / "main").write_text("abc123\n", encoding="utf-8")

    source = resolve_real_small_text_model_source(environment={"HF_HOME": str(hf_home)})

    assert source.live is True
    assert source.local_model_path == ""
    assert source.model_path_for_runtime == REAL_SMALL_TEXT_MODEL_ID
    assert source.source_resolution_mode == "hub_fallback"


def test_resolve_real_small_model_path_uses_the_shared_source_resolution(tmp_path: Path) -> None:
    model_dir = tmp_path / "qwen-real-small"
    model_dir.mkdir()

    resolved = resolve_real_small_text_model_path(
        environment={REAL_SMALL_TEXT_MODEL_PATH_ENV: str(model_dir)}
    )

    assert resolved == model_dir.resolve()
