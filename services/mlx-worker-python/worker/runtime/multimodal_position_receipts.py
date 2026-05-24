from __future__ import annotations

from functools import reduce
from operator import mul
from typing import Any


def build_position_metadata_receipt(
    *,
    prepared_request: Any | None = None,
    seq_len: int = 0,
    cache_offset: int = 0,
    position_ids: Any | None = None,
    rope_deltas: Any | None = None,
    fallback_reason: str = "",
) -> dict[str, object]:
    position_ids_count = _value_count(position_ids)
    rope_deltas_count = _value_count(rope_deltas)
    media_position_count = _media_position_count(prepared_request)
    normalized_cache_offset = max(0, int(cache_offset or 0))
    normalized_seq_len = max(0, int(seq_len or 0))
    normalized_fallback_reason = str(fallback_reason or "")
    guard = _vision_metadata_guard(
        media_position_count=media_position_count,
        position_ids=position_ids,
        rope_deltas=rope_deltas,
        seq_len=normalized_seq_len,
    )
    reuse_allowed = guard in {"no_media", "aligned"}
    stale_metadata_fallback_count = 0 if reuse_allowed else 1
    companion_rederive_skip_reason = (
        "multimodal_companion_rederive_skipped_has_media" if media_position_count else ""
    )
    return {
        "position_ids_present": position_ids is not None,
        "position_ids_count": position_ids_count,
        "rope_deltas_present": rope_deltas is not None,
        "rope_deltas_count": rope_deltas_count,
        "media_position_count": media_position_count,
        "cache_offset": normalized_cache_offset,
        "seq_len": normalized_seq_len,
        "rebuild_count": 1 if media_position_count else 0,
        "mismatch_fallback_count": (
            1
            if media_position_count
            and (
                normalized_fallback_reason not in {"", "no_media"}
                or stale_metadata_fallback_count
            )
            else 0
        ),
        "fallback_reason": normalized_fallback_reason,
        "vision_metadata_guard": guard,
        "vision_metadata_reuse_allowed": reuse_allowed,
        "stale_metadata_fallback_count": stale_metadata_fallback_count,
        "companion_rederive_skip_reason": companion_rederive_skip_reason,
    }


def _media_position_count(prepared_request: Any | None) -> int:
    if prepared_request is None:
        return 0
    images = getattr(prepared_request, "images", ()) or ()
    image_count = len(images)
    video_frame_count = int(getattr(prepared_request, "effective_video_frame_count", 0) or 0)
    videos = getattr(prepared_request, "videos", ()) or ()
    if videos and video_frame_count <= 0:
        video_frame_count = len(videos)
    return max(0, image_count + video_frame_count)


def _value_count(value: Any | None) -> int:
    if value is None:
        return 0
    shape = getattr(value, "shape", None)
    if isinstance(shape, (tuple, list)) and shape:
        return int(reduce(mul, (max(0, int(part)) for part in shape), 1))
    if isinstance(value, dict):
        return len(value)
    if isinstance(value, (list, tuple)):
        return len(value)
    return 1


def _vision_metadata_guard(
    *,
    media_position_count: int,
    position_ids: Any | None,
    rope_deltas: Any | None,
    seq_len: int,
) -> str:
    if media_position_count <= 0:
        return "no_media"
    if position_ids is None:
        return "missing_position_metadata"
    if rope_deltas is None:
        return "missing_rope_metadata"
    if not _position_metadata_covers_sequence(position_ids, seq_len):
        return "stale_position_metadata"
    return "aligned"


def _position_metadata_covers_sequence(position_ids: Any, seq_len: int) -> bool:
    if seq_len <= 0:
        return _value_count(position_ids) > 0

    shape_extent = _last_shape_extent(position_ids)
    if shape_extent is not None:
        return shape_extent >= seq_len

    if isinstance(position_ids, (list, tuple)):
        return len(position_ids) >= seq_len
    return _value_count(position_ids) >= seq_len


def _last_shape_extent(value: Any) -> int | None:
    shape = getattr(value, "shape", None)
    if not isinstance(shape, (tuple, list)) or not shape:
        return None
    return max(0, int(shape[-1]))
