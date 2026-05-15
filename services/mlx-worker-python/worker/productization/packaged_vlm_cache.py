from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class PackagedVLMArtifactSpec:
    artifact_id: str
    output_filename: str
    source_path: Path


def packaged_vlm_artifact_specs(
    *,
    model_source_path: Path,
    projector_source_path: Path,
) -> tuple[PackagedVLMArtifactSpec, PackagedVLMArtifactSpec]:
    return (
        PackagedVLMArtifactSpec(
            artifact_id="model",
            output_filename="model.gguf",
            source_path=model_source_path,
        ),
        PackagedVLMArtifactSpec(
            artifact_id="companion_projector",
            output_filename="mmproj.gguf",
            source_path=projector_source_path,
        ),
    )


def build_packaged_vlm_cache_receipt(
    *,
    cache_dir: Path,
    model_manifest: Mapping[str, Any],
    projector_manifest: Mapping[str, Any],
    cancelled_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    model_artifact_path = Path(str(model_manifest.get("output_path", "")))
    companion_projector_path = Path(str(projector_manifest.get("output_path", "")))
    model_partial_bytes_saved = _partial_bytes(cancelled_manifest)
    model_resumed = bool(model_manifest.get("resume_used"))
    projector_resumed = bool(projector_manifest.get("resume_used"))
    local_route_verified = float(
        model_artifact_path.is_file()
        and companion_projector_path.is_file()
        and _is_relative_to(model_artifact_path, cache_dir)
        and _is_relative_to(companion_projector_path, cache_dir)
    )
    cache_restore_status = (
        "restored_from_partial"
        if model_resumed and model_partial_bytes_saved > 0
        else "cold_cache"
    )
    receipt = {
        "schema_version": "melix.packaged_vlm_cache_receipt.v1",
        "model_artifact_path": str(model_artifact_path),
        "companion_projector_path": str(companion_projector_path),
        "cache_layout": "flat_gguf_with_companion_projector",
        "cache_restore_status": cache_restore_status,
        "local_route_verified": local_route_verified,
        "partial_cache_bytes_saved": model_partial_bytes_saved,
        "model_resume_used": float(model_resumed),
        "companion_projector_resume_used": float(projector_resumed),
        "metrics": {
            "packaged_vlm.cache_restore_success": float(cache_restore_status == "restored_from_partial"),
            "packaged_vlm.partial_cache_bytes_saved": float(model_partial_bytes_saved),
            "packaged_vlm.local_route_verified": local_route_verified,
        },
    }
    receipt_path = cache_dir / "packaged-vlm-route-receipt.json"
    receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    receipt["receipt_path"] = str(receipt_path)
    return receipt


def _partial_bytes(manifest: Mapping[str, Any] | None) -> int:
    if not manifest:
        return 0
    try:
        return max(0, int(manifest.get("downloaded_bytes", 0) or 0))
    except (TypeError, ValueError):
        return 0


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True
