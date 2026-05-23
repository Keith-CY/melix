from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from worker.productization.packaged_vlm_cache import (
    build_packaged_vlm_cache_receipt,
    packaged_vlm_artifact_specs,
)
import worker.productization.packaged_vlm_cache as packaged_vlm_cache


REPO_ROOT = Path(__file__).resolve().parents[3]
SMOKE_PATH = REPO_ROOT / "scripts" / "packaged_vlm_artifact_cache_smoke.py"


def test_packaged_vlm_artifact_specs_use_flat_cache_filenames(tmp_path: Path) -> None:
    model = tmp_path / "model-source.gguf"
    projector = tmp_path / "projector-source.gguf"

    model_spec, projector_spec = packaged_vlm_artifact_specs(
        model_source_path=model,
        projector_source_path=projector,
    )

    assert model_spec.artifact_id == "model"
    assert model_spec.output_filename == "model.gguf"
    assert model_spec.source_path == model
    assert projector_spec.artifact_id == "companion_projector"
    assert projector_spec.output_filename == "mmproj.gguf"
    assert projector_spec.source_path == projector


def test_packaged_vlm_cache_helpers_are_exported_lazily() -> None:
    import worker.productization as productization

    assert productization.packaged_vlm_artifact_specs is packaged_vlm_artifact_specs
    assert productization.build_packaged_vlm_cache_receipt is build_packaged_vlm_cache_receipt


def test_build_packaged_vlm_cache_receipt_records_local_route_and_restore(tmp_path: Path) -> None:
    cache_dir = tmp_path / "flat-cache"
    cache_dir.mkdir()
    model_artifact = cache_dir / "model.gguf"
    projector_artifact = cache_dir / "mmproj.gguf"
    model_artifact.write_bytes(b"model")
    projector_artifact.write_bytes(b"projector")

    receipt = build_packaged_vlm_cache_receipt(
        cache_dir=cache_dir,
        cancelled_manifest={"downloaded_bytes": 1024},
        model_manifest={
            "output_path": str(model_artifact),
            "resume_used": True,
        },
        projector_manifest={
            "output_path": str(projector_artifact),
            "resume_used": False,
        },
    )

    assert receipt["model_artifact_path"] == str(model_artifact)
    assert receipt["companion_projector_path"] == str(projector_artifact)
    assert receipt["cache_layout"] == "flat_gguf_with_companion_projector"
    assert receipt["cache_restore_status"] == "restored_from_partial"
    assert receipt["local_route_verified"] == 1.0
    assert receipt["metrics"]["packaged_vlm.cache_restore_success"] == 1.0
    assert Path(str(receipt["receipt_path"])).is_file()


def test_build_packaged_vlm_cache_receipt_rejects_non_cache_route(tmp_path: Path) -> None:
    cache_dir = tmp_path / "flat-cache"
    outside_dir = tmp_path / "outside"
    cache_dir.mkdir()
    outside_dir.mkdir()
    model_artifact = outside_dir / "model.gguf"
    projector_artifact = cache_dir / "mmproj.gguf"
    model_artifact.write_bytes(b"model")
    projector_artifact.write_bytes(b"projector")

    receipt = build_packaged_vlm_cache_receipt(
        cache_dir=cache_dir,
        model_manifest={"output_path": str(model_artifact), "resume_used": False},
        projector_manifest={"output_path": str(projector_artifact), "resume_used": False},
    )

    assert receipt["cache_restore_status"] == "cold_cache"
    assert receipt["local_route_verified"] == 0.0
    assert receipt["metrics"]["packaged_vlm.local_route_verified"] == 0.0


def test_build_packaged_vlm_cache_receipt_handles_malformed_cancel_manifest(tmp_path: Path) -> None:
    cache_dir = tmp_path / "flat-cache"
    cache_dir.mkdir()
    model_artifact = cache_dir / "model.gguf"
    projector_artifact = cache_dir / "mmproj.gguf"
    model_artifact.write_bytes(b"model")
    projector_artifact.write_bytes(b"projector")

    receipt = build_packaged_vlm_cache_receipt(
        cache_dir=cache_dir,
        cancelled_manifest={"downloaded_bytes": object()},
        model_manifest={"output_path": str(model_artifact), "resume_used": False},
        projector_manifest={"output_path": str(projector_artifact), "resume_used": False},
    )

    assert receipt["partial_cache_bytes_saved"] == 0
    assert receipt["metrics"]["packaged_vlm.partial_cache_bytes_saved"] == 0.0


def test_build_packaged_vlm_cache_receipt_records_packaged_media_audit(tmp_path: Path) -> None:
    cache_dir = tmp_path / "flat-cache"
    cache_dir.mkdir()
    model_artifact = cache_dir / "model.gguf"
    projector_artifact = cache_dir / "mmproj.gguf"
    model_artifact.write_bytes(b"model")
    projector_artifact.write_bytes(b"projector")

    receipt = build_packaged_vlm_cache_receipt(
        cache_dir=cache_dir,
        model_manifest={"output_path": str(model_artifact), "resume_used": True},
        projector_manifest={"output_path": str(projector_artifact), "resume_used": False},
        processor_modality_counts={"text": 1, "image": 1},
        media_token_expansion=576,
    )

    assert receipt["processor_modality_counts"] == {
        "text": 1,
        "image": 1,
        "audio": 0,
        "video": 0,
    }
    assert receipt["media_token_expansion"] == 576
    assert receipt["packaged_media_route"] == "bundled_mlx_vlm"
    assert receipt["unsupported_reason"] == "none"
    assert receipt["metrics"]["packaged_vlm.media_token_expansion"] == 576.0
    assert receipt["metrics"]["packaged_vlm.packaged_media_route_supported"] == 1.0


def test_build_packaged_vlm_cache_receipt_fails_closed_without_media_expansion(tmp_path: Path) -> None:
    cache_dir = tmp_path / "flat-cache"
    cache_dir.mkdir()
    model_artifact = cache_dir / "model.gguf"
    projector_artifact = cache_dir / "mmproj.gguf"
    model_artifact.write_bytes(b"model")
    projector_artifact.write_bytes(b"projector")

    receipt = build_packaged_vlm_cache_receipt(
        cache_dir=cache_dir,
        model_manifest={"output_path": str(model_artifact), "resume_used": False},
        projector_manifest={"output_path": str(projector_artifact), "resume_used": False},
        processor_modality_counts={"text": 1, "image": 1},
        media_token_expansion=0,
    )

    assert receipt["packaged_media_route"] == "unsupported"
    assert receipt["unsupported_reason"] == "missing_media_token_expansion"
    assert receipt["metrics"]["packaged_vlm.packaged_media_route_supported"] == 0.0


def test_build_packaged_vlm_cache_receipt_normalizes_malformed_audit_counts(tmp_path: Path) -> None:
    cache_dir = tmp_path / "flat-cache"
    cache_dir.mkdir()
    model_artifact = cache_dir / "model.gguf"
    projector_artifact = cache_dir / "mmproj.gguf"
    model_artifact.write_bytes(b"model")
    projector_artifact.write_bytes(b"projector")

    receipt = build_packaged_vlm_cache_receipt(
        cache_dir=cache_dir,
        model_manifest={"output_path": str(model_artifact), "resume_used": False},
        projector_manifest={"output_path": str(projector_artifact), "resume_used": False},
        processor_modality_counts={"text": 1, "image": object()},
        media_token_expansion=object(),
    )

    assert receipt["processor_modality_counts"] == {
        "text": 1,
        "image": 0,
        "audio": 0,
        "video": 0,
    }
    assert receipt["media_token_expansion"] == 0
    assert receipt["packaged_media_route"] == "not_audited"
    assert receipt["unsupported_reason"] == "no_media_prompt"


def test_packaged_vlm_processor_modality_counts_tolerates_missing_optional_processor_hints() -> None:
    modality_counter = getattr(packaged_vlm_cache, "packaged_vlm_processor_modality_counts", None)
    assert callable(modality_counter)

    processor = SimpleNamespace(image_processor=object())

    counts = modality_counter(
        processor=processor,
        prompt_modality_counts={"text": 1, "image": 1},
    )

    assert counts == {
        "text": 1,
        "image": 1,
        "audio": 0,
        "video": 0,
    }


def test_packaged_vlm_processor_modality_counts_fail_closed_for_missing_processors() -> None:
    counts = packaged_vlm_cache.packaged_vlm_processor_modality_counts(
        processor=SimpleNamespace(),
        prompt_modality_counts={"text": 1, "image": 1, "audio": 1, "video": 1},
    )

    assert counts == {
        "text": 1,
        "image": 0,
        "audio": 0,
        "video": 0,
    }


def test_packaged_vlm_artifact_cache_smoke_reports_resume_and_route_receipt(
    monkeypatch,
    capsys,
) -> None:
    spec = importlib.util.spec_from_file_location("packaged_vlm_artifact_cache_smoke", SMOKE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(spec.name, None)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.sys, "argv", ["packaged_vlm_artifact_cache_smoke.py", "--json"])

    assert module.main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert all(payload["checks"].values())
    assert payload["receipt"]["cache_restore_status"] == "restored_from_partial"
    assert payload["receipt"]["local_route_verified"] == 1.0
    assert payload["receipt"]["processor_modality_counts"] == {
        "text": 1,
        "image": 1,
        "audio": 0,
        "video": 0,
    }
    assert payload["receipt"]["media_token_expansion"] > 0
    assert payload["receipt"]["packaged_media_route"] == "bundled_mlx_vlm"
    assert payload["receipt"]["unsupported_reason"] == "none"
    assert payload["receipt"]["metrics"]["packaged_vlm.partial_cache_bytes_saved"] == 1024.0
    assert payload["receipt"]["metrics"]["packaged_vlm.media_token_expansion"] > 0.0
