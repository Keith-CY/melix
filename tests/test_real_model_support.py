from __future__ import annotations

import json
from pathlib import Path

from scripts.real_model_support import (
    PHASE2_DEFAULT_DRAFT_TEXT_MODEL_ID,
    REAL_SMALL_TEXT_MODEL_ID,
    REAL_SMALL_TEXT_MODEL_PATH_ENV,
    _descriptor_runtime_model_path,
    build_runtime_model_preflight,
    resolve_real_small_text_model_path,
    resolve_real_small_text_model_source,
)


def test_phase2_default_draft_model_is_small_mlx_qwen() -> None:
    assert PHASE2_DEFAULT_DRAFT_TEXT_MODEL_ID == "mlx-community/Qwen3-0.6B-4bit"


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
    hf_snapshot = tmp_path / "hf-cache" / "models--mlx-community--Qwen3.5-0.8B-OptiQ-4bit" / "snapshots" / "abc123"
    hf_snapshot.mkdir(parents=True)
    (hf_snapshot / "model.safetensors").write_bytes(b"weights")
    (managed_model_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.model_registry_manifest.v1",
                "model_id": REAL_SMALL_TEXT_MODEL_ID,
                "ext": {
                    "melix.model_path": str(hf_snapshot),
                    "melix.registry_descriptor_path": str(managed_model_dir),
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    source = resolve_real_small_text_model_source(
        environment={"MELIX_MANAGED_MODEL_ROOT": str(tmp_path / "managed")},
    )

    assert source.live is False
    assert source.local_model_path == str(hf_snapshot.resolve())
    assert source.source_resolution_mode == "managed_model_path"


def test_real_small_model_source_preserves_old_copied_managed_layout_fallback(tmp_path: Path) -> None:
    managed_model_dir = (
        tmp_path
        / "managed"
        / "huggingface"
        / "mlx-community"
        / "Qwen3.5-0.8B-OptiQ-4bit"
        / "main"
    )
    managed_model_dir.mkdir(parents=True)
    (managed_model_dir / "model.safetensors").write_bytes(b"weights")

    source = resolve_real_small_text_model_source(
        environment={"MELIX_MANAGED_MODEL_ROOT": str(tmp_path / "managed")},
    )

    assert source.live is False
    assert source.local_model_path == str(managed_model_dir.resolve())
    assert source.source_resolution_mode == "managed_model_path"


def test_descriptor_runtime_model_path_ignores_invalid_descriptor_manifests(
    tmp_path: Path,
    monkeypatch,
) -> None:
    missing_runtime = tmp_path / "missing-runtime"
    monkeypatch.chdir(tmp_path)
    (tmp_path / "None").mkdir()
    manifest_payloads = [
        "{",
        "[]",
        json.dumps({"ext": "invalid"}),
        json.dumps({"ext": {}}),
        json.dumps({"ext": {"melix.model_path": None}}),
        json.dumps({"ext": {"melix.model_path": str(missing_runtime)}}),
    ]

    for index, payload in enumerate(manifest_payloads):
        descriptor_dir = tmp_path / f"descriptor-{index}"
        descriptor_dir.mkdir()
        (descriptor_dir / "manifest.json").write_text(payload + "\n", encoding="utf-8")

        assert _descriptor_runtime_model_path(descriptor_dir) is None


def test_descriptor_runtime_model_path_logs_manifest_runtime_file(
    tmp_path: Path,
    caplog,
) -> None:
    descriptor_dir = tmp_path / "descriptor"
    runtime_file = tmp_path / "hf-cache" / "snapshot" / "config.json"
    descriptor_dir.mkdir()
    runtime_file.parent.mkdir(parents=True)
    runtime_file.write_text("{}", encoding="utf-8")
    (descriptor_dir / "manifest.json").write_text(
        json.dumps({"ext": {"melix.model_path": str(runtime_file)}}) + "\n",
        encoding="utf-8",
    )

    caplog.set_level("DEBUG", logger="scripts.real_model_support")

    assert _descriptor_runtime_model_path(descriptor_dir) is None
    assert "is not a directory" in caplog.text


def test_real_small_model_source_can_use_huggingface_cache_when_allowed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    snapshot = (
        home
        / ".cache"
        / "huggingface"
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
        environment={"HOME": str(home)},
        allow_hf_cache=True,
    )

    assert source.live is False
    assert source.local_model_path == str(snapshot.resolve())
    assert source.source_resolution_mode == "hf_cache_snapshot"


def test_real_small_model_source_defaults_to_hub_without_local_sources(tmp_path: Path) -> None:
    home = tmp_path / "home"
    snapshot = (
        home
        / ".cache"
        / "huggingface"
        / "hub"
        / "models--mlx-community--Qwen3.5-0.8B-OptiQ-4bit"
        / "snapshots"
        / "abc123"
    )
    snapshot.mkdir(parents=True)
    refs = snapshot.parents[1] / "refs"
    refs.mkdir()
    (refs / "main").write_text("abc123\n", encoding="utf-8")

    source = resolve_real_small_text_model_source(environment={"HOME": str(home)})

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


def test_resolve_real_small_model_path_returns_none_without_local_source(tmp_path: Path) -> None:
    assert (
        resolve_real_small_text_model_path(
            environment={"HOME": str(tmp_path / "home")},
            allow_managed_root=False,
            allow_hf_cache=False,
        )
        is None
    )


def test_real_small_model_source_ignores_missing_managed_candidate(tmp_path: Path) -> None:
    source = resolve_real_small_text_model_source(
        environment={"MELIX_MANAGED_MODEL_ROOT": str(tmp_path / "managed")},
        allow_hf_cache=False,
    )

    assert source.live is True
    assert source.local_model_path == ""
    assert source.source_resolution_mode == "hub_fallback"


def test_real_small_model_source_can_fallback_to_last_hf_cache_snapshot(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cache_root = home / ".cache" / "huggingface" / "hub"
    snapshots_root = cache_root / "models--mlx-community--Qwen3.5-0.8B-OptiQ-4bit" / "snapshots"
    old_snapshot = snapshots_root / "aaa"
    latest_snapshot = snapshots_root / "zzz"
    old_snapshot.mkdir(parents=True)
    latest_snapshot.mkdir()

    source = resolve_real_small_text_model_source(
        environment={"HOME": str(home)},
        allow_managed_root=False,
        allow_hf_cache=True,
    )

    assert source.live is False
    assert source.local_model_path == str(latest_snapshot.resolve())
    assert source.source_resolution_mode == "hf_cache_snapshot"
    assert "refs/main was unavailable" in source.warnings[0]


def test_runtime_model_preflight_marks_real_local_weights(tmp_path: Path) -> None:
    model_dir = tmp_path / "qwen-real-small"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "model.safetensors").write_text("weights\n", encoding="utf-8")

    preflight = build_runtime_model_preflight(
        model_id=REAL_SMALL_TEXT_MODEL_ID,
        live=False,
        local_model_path=str(model_dir),
        source_resolution_mode="explicit_local_path",
    )

    assert preflight.runtime_model_class == "real_local_model"
    assert preflight.real_local_model is True
    assert preflight.deterministic_dev_model is False
    assert preflight.hub_required is False
    assert preflight.to_dict()["local_model_path"] == str(model_dir.resolve())


def test_runtime_model_preflight_marks_deterministic_development_models() -> None:
    preflight = build_runtime_model_preflight(
        model_id="melix-dev-text",
        live=False,
        local_model_path="",
        source_resolution_mode="",
    )

    assert preflight.runtime_model_class == "deterministic_dev_model"
    assert preflight.real_local_model is False
    assert preflight.deterministic_dev_model is True
    assert preflight.hub_required is False
    assert "deterministic development model" in preflight.warnings[0]


def test_runtime_model_preflight_marks_hub_required_models() -> None:
    preflight = build_runtime_model_preflight(
        model_id=REAL_SMALL_TEXT_MODEL_ID,
        live=True,
        local_model_path="",
        source_resolution_mode="hub_fallback",
    )

    assert preflight.runtime_model_class == "hub_required"
    assert preflight.real_local_model is False
    assert preflight.deterministic_dev_model is False
    assert preflight.hub_required is True


def test_runtime_model_preflight_warns_when_local_path_has_no_real_weights(tmp_path: Path) -> None:
    model_dir = tmp_path / "empty-local-model"
    model_dir.mkdir()

    preflight = build_runtime_model_preflight(
        model_id=REAL_SMALL_TEXT_MODEL_ID,
        live=False,
        local_model_path=str(model_dir),
        source_resolution_mode="explicit_local_path",
    )

    assert preflight.runtime_model_class == "missing_real_local_model"
    assert preflight.real_local_model is False
    assert preflight.deterministic_dev_model is False
    assert preflight.hub_required is False
    assert "recognized model weight files" in preflight.warnings[0]


def test_runtime_model_preflight_warns_when_non_live_model_has_no_local_path() -> None:
    preflight = build_runtime_model_preflight(
        model_id=REAL_SMALL_TEXT_MODEL_ID,
        live=False,
        local_model_path="",
        source_resolution_mode="",
    )

    assert preflight.runtime_model_class == "missing_real_local_model"
    assert "No local model path" in preflight.warnings[0]


def test_runtime_model_preflight_warns_when_local_path_is_missing(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing-model"

    preflight = build_runtime_model_preflight(
        model_id=REAL_SMALL_TEXT_MODEL_ID,
        live=False,
        local_model_path=str(missing_path),
        source_resolution_mode="explicit_local_path",
    )

    assert preflight.runtime_model_class == "missing_real_local_model"
    assert f"Local model path does not exist: {missing_path.resolve()}" in preflight.warnings


def test_runtime_model_preflight_accepts_index_weight_files(tmp_path: Path) -> None:
    model_dir = tmp_path / "indexed-model"
    model_dir.mkdir()
    (model_dir / "nested").mkdir()
    (model_dir / "model.safetensors.index.json").write_text("{}", encoding="utf-8")

    preflight = build_runtime_model_preflight(
        model_id=REAL_SMALL_TEXT_MODEL_ID,
        live=False,
        local_model_path=str(model_dir),
        source_resolution_mode="explicit_local_path",
    )

    assert preflight.runtime_model_class == "real_local_model"
