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
    normalized_fallback_reason = str(fallback_reason or "")
    return {
        "position_ids_present": position_ids is not None,
        "position_ids_count": position_ids_count,
        "rope_deltas_present": rope_deltas is not None,
        "rope_deltas_count": rope_deltas_count,
        "media_position_count": media_position_count,
        "cache_offset": max(0, int(cache_offset or 0)),
        "seq_len": max(0, int(seq_len or 0)),
        "rebuild_count": 1 if media_position_count else 0,
        "mismatch_fallback_count": (
            1 if media_position_count and normalized_fallback_reason not in {"", "no_media"} else 0
        ),
        "fallback_reason": normalized_fallback_reason,
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
