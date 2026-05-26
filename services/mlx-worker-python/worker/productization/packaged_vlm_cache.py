from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


_MODALITY_KEYS = ("text", "image", "audio", "video")


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
    processor_modality_counts: Mapping[str, Any] | None = None,
    media_token_expansion: int | float = 0,
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
    normalized_modality_counts = _normalize_modality_counts(processor_modality_counts)
    normalized_media_token_expansion = _non_negative_int(media_token_expansion)
    has_non_text_media = any(normalized_modality_counts[key] > 0 for key in ("image", "audio", "video"))
    if not local_route_verified:
        packaged_media_route = "unsupported"
        unsupported_reason = "non_cache_route"
    elif has_non_text_media and normalized_media_token_expansion > 0:
        packaged_media_route = "bundled_mlx_vlm"
        unsupported_reason = "none"
    elif has_non_text_media:
        packaged_media_route = "unsupported"
        unsupported_reason = "missing_media_token_expansion"
    else:
        packaged_media_route = "not_audited"
        unsupported_reason = "no_media_prompt"
    packaged_media_route_supported = float(packaged_media_route == "bundled_mlx_vlm")
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
        "processor_modality_counts": normalized_modality_counts,
        "media_token_expansion": normalized_media_token_expansion,
        "packaged_media_route": packaged_media_route,
        "unsupported_reason": unsupported_reason,
        "metrics": {
            "packaged_vlm.cache_restore_success": float(cache_restore_status == "restored_from_partial"),
            "packaged_vlm.partial_cache_bytes_saved": float(model_partial_bytes_saved),
            "packaged_vlm.local_route_verified": local_route_verified,
            "packaged_vlm.media_token_expansion": float(normalized_media_token_expansion),
            "packaged_vlm.packaged_media_route_supported": packaged_media_route_supported,
            "packaged_vlm.processor_modality_count.text": float(normalized_modality_counts["text"]),
            "packaged_vlm.processor_modality_count.image": float(normalized_modality_counts["image"]),
            "packaged_vlm.processor_modality_count.audio": float(normalized_modality_counts["audio"]),
            "packaged_vlm.processor_modality_count.video": float(normalized_modality_counts["video"]),
        },
    }
    receipt_path = cache_dir / "packaged-vlm-route-receipt.json"
    receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    receipt["receipt_path"] = str(receipt_path)
    return receipt


def packaged_vlm_processor_modality_counts(
    *,
    processor: Any,
    prompt_modality_counts: Mapping[str, Any],
) -> dict[str, int]:
    counts = _normalize_modality_counts(prompt_modality_counts)
    if counts["image"] > 0 and getattr(processor, "image_processor", None) is None:
        counts["image"] = 0
    if counts["audio"] > 0 and getattr(processor, "audio_processor", None) is None:
        counts["audio"] = 0
    if counts["video"] > 0 and getattr(processor, "video_processor", None) is None:
        counts["video"] = 0
    return counts


def _normalize_modality_counts(counts: Mapping[str, Any] | None) -> dict[str, int]:
    raw_counts = counts or {}
    return {
        key: _non_negative_int(raw_counts.get(key, 0))
        for key in _MODALITY_KEYS
    }


def _non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


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
