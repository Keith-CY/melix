from __future__ import annotations

from functools import reduce
from operator import mul
from typing import Any, cast


NO_MEDIA_HYBRID_STATE_PATCH_RECEIPT: dict[str, object] = {
    "schema_version": "melix.hybrid_state_patch_receipt.v1",
    "family_id": "",
    "patch_mode": "not_applicable",
    "batch_row_count": 0,
    "mixed_length_batch": False,
    "cache_advance_count": 0,
    "family_fast_path_override_count": 0,
    "contiguous_state_guard": "aligned",
    "text_only_rope_guard": "aligned",
    "row_drift_count": 0,
    "fallback_reason": "no_media",
    "rows": [],
}


def build_mixed_batch_geometry_receipt(*, rows: list[dict[str, Any]]) -> dict[str, object]:
    row_receipts: list[dict[str, object]] = []
    total_media_count = 0
    total_visual_embed_count = 0
    seq_lens: set[int] = set()

    for expected_row_index, row in enumerate(rows):
        row_receipt = _mixed_batch_row_geometry_receipt(
            row=row,
            expected_row_index=expected_row_index,
        )
        row_receipts.append(row_receipt)
        total_media_count += int(row_receipt["media_count"])
        total_visual_embed_count += int(row_receipt["visual_embed_count"])
        seq_lens.add(int(row_receipt["seq_len"]))

    row_drift_count = sum(
        1 for row_receipt in row_receipts if row_receipt["row_geometry_guard"] == "row_drift"
    )
    return {
        "batch_row_count": len(row_receipts),
        "mixed_length_batch": len(seq_lens) > 1,
        "row_geometry_guard": "row_drift" if row_drift_count else "aligned",
        "row_drift_count": row_drift_count,
        "total_media_count": total_media_count,
        "total_visual_embed_count": total_visual_embed_count,
        "rows": row_receipts,
    }


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


def empty_quantized_kv_mask_receipt() -> dict[str, object]:
    return {
        "schema_version": "melix.quantized_kv_mask_receipt.v1",
        "batch_row_count": 0,
        "unequal_cache_offsets": False,
        "per_row_offsets": [],
        "cache_mask_guard": "aligned",
        "row_drift_count": 0,
        "cache_mask_shapes": [],
        "offset_receipts": [],
        "logit_parity": {
            "status": "not_provided",
            "sample_count": 0,
            "max_abs_delta": 0.0,
            "tolerance": 0.0,
        },
    }


def empty_hybrid_state_patch_receipt() -> dict[str, object]:
    return build_hybrid_state_patch_receipt(
        family_id="",
        patch_mode="not_reported",
        rows=[],
    )


def build_quantized_kv_mask_receipt(
    *,
    rows: list[dict[str, Any]],
    quantized_logits: Any | None = None,
    unquantized_logits: Any | None = None,
    tolerance: float = 0.0,
) -> dict[str, object]:
    row_receipts: list[dict[str, object]] = []
    per_row_offsets: list[int] = []
    cache_mask_shapes: list[list[int]] = []

    for expected_row_index, row in enumerate(rows):
        row_receipt = _quantized_kv_mask_row_receipt(
            row=row,
            expected_row_index=expected_row_index,
        )
        row_receipts.append(row_receipt)
        per_row_offsets.append(int(row_receipt["cache_offset"]))
        cache_mask_shapes.append(cast(list[int], row_receipt["cache_mask_shape"]))

    row_drift_count = sum(
        1 for row_receipt in row_receipts if row_receipt["cache_mask_guard"] == "row_drift"
    )
    return {
        "schema_version": "melix.quantized_kv_mask_receipt.v1",
        "batch_row_count": len(row_receipts),
        "unequal_cache_offsets": len(set(per_row_offsets)) > 1,
        "per_row_offsets": per_row_offsets,
        "cache_mask_guard": "row_drift" if row_drift_count else "aligned",
        "row_drift_count": row_drift_count,
        "cache_mask_shapes": cache_mask_shapes,
        "offset_receipts": row_receipts,
        "logit_parity": _logit_parity_receipt(
            quantized_logits=quantized_logits,
            unquantized_logits=unquantized_logits,
            tolerance=tolerance,
        ),
    }


def build_hybrid_state_patch_receipt(
    *,
    family_id: str,
    patch_mode: str,
    rows: list[dict[str, Any]],
    fallback_reason: str = "",
    family_fast_path_override_count: int = 0,
) -> dict[str, object]:
    row_receipts: list[dict[str, object]] = []
    seq_lens: set[int] = set()
    cache_advance_count = 0

    for expected_row_index, row in enumerate(rows):
        row_receipt = _hybrid_state_patch_row_receipt(
            row=row,
            expected_row_index=expected_row_index,
        )
        row_receipts.append(row_receipt)
        seq_lens.add(int(row_receipt["seq_len"]))
        cache_advance_count += int(row_receipt["cache_advance"])

    row_drift_count = sum(
        1 for row_receipt in row_receipts if row_receipt["row_state_guard"] == "row_drift"
    )
    text_only_rope_drift = any(
        "text_only_rope_mode_mismatch" in row_receipt["row_drift_reasons"]
        for row_receipt in row_receipts
    )
    return {
        "schema_version": "melix.hybrid_state_patch_receipt.v1",
        "family_id": str(family_id or ""),
        "patch_mode": str(patch_mode or "not_reported"),
        "batch_row_count": len(row_receipts),
        "mixed_length_batch": len(seq_lens) > 1,
        "cache_advance_count": cache_advance_count,
        "family_fast_path_override_count": _non_negative_int(family_fast_path_override_count),
        "contiguous_state_guard": "row_drift" if row_drift_count else "aligned",
        "text_only_rope_guard": "row_drift" if text_only_rope_drift else "aligned",
        "row_drift_count": row_drift_count,
        "fallback_reason": str(fallback_reason or ""),
        "rows": row_receipts,
    }


def _mixed_batch_row_geometry_receipt(
    *,
    row: dict[str, Any],
    expected_row_index: int,
) -> dict[str, object]:
    row_index = _non_negative_int(row.get("row_index", expected_row_index))
    seq_len = _non_negative_int(row.get("seq_len", 0))
    cache_offset = _non_negative_int(row.get("cache_offset", 0))
    media_count = _non_negative_int(row.get("media_count", 0))
    left_padding = _non_negative_int(row.get("left_padding", 0))
    expected_left_padding = _non_negative_int(row.get("expected_left_padding", left_padding))
    visual_embed_count = _non_negative_int(row.get("visual_embed_count", 0))
    expected_visual_embed_count = _non_negative_int(
        row.get("expected_visual_embed_count", visual_embed_count)
    )
    raw_prompt_kwargs = row.get("prompt_kwargs")
    prompt_kwargs = _normalized_prompt_kwargs(raw_prompt_kwargs)
    prompt_kwargs_complete = isinstance(raw_prompt_kwargs, dict) and {
        "input_ids_len",
        "attention_mask_len",
    }.issubset(raw_prompt_kwargs)
    mrope_delta_override_count = _value_count(row.get("mrope_delta_override"))
    mrope_delta_override_identity = _normalized_identity(
        row.get("mrope_delta_override_identity", [])
    )
    expected_mrope_delta_override_identity = _normalized_identity(
        row.get("expected_mrope_delta_override_identity", mrope_delta_override_identity)
    )
    visual_embed_identity = _normalized_identity(row.get("visual_embed_identity", []))
    expected_visual_embed_identity = _normalized_identity(
        row.get("expected_visual_embed_identity", visual_embed_identity)
    )

    drift_reasons: list[str] = []
    if row_index != expected_row_index:
        drift_reasons.append("row_index_mismatch")
    if not prompt_kwargs_complete:
        drift_reasons.append("prompt_kwargs_missing")
    if prompt_kwargs.get("input_ids_len", seq_len) != seq_len:
        drift_reasons.append("prompt_input_ids_len_mismatch")
    if left_padding != expected_left_padding:
        drift_reasons.append("left_padding_mismatch")
    if (
        prompt_kwargs.get("attention_mask_len", seq_len + left_padding)
        != seq_len + expected_left_padding
    ):
        drift_reasons.append("prompt_attention_mask_len_mismatch")
    if mrope_delta_override_count != media_count:
        drift_reasons.append("mrope_delta_override_count_mismatch")
    if mrope_delta_override_identity != expected_mrope_delta_override_identity:
        drift_reasons.append("mrope_delta_override_identity_drift")
    if media_count and visual_embed_count <= 0:
        drift_reasons.append("visual_embed_count_missing")
    if (
        visual_embed_count != expected_visual_embed_count
        or visual_embed_identity != expected_visual_embed_identity
    ):
        drift_reasons.append("visual_embed_scatter_drift")

    return {
        "row_index": row_index,
        "prompt_kwargs": prompt_kwargs,
        "seq_len": seq_len,
        "cache_offset": cache_offset,
        "media_count": media_count,
        "left_padding": left_padding,
        "expected_left_padding": expected_left_padding,
        "mrope_delta_override_count": mrope_delta_override_count,
        "mrope_delta_override_identity": mrope_delta_override_identity,
        "visual_embed_count": visual_embed_count,
        "visual_embed_identity": visual_embed_identity,
        "row_geometry_guard": "row_drift" if drift_reasons else "aligned",
        "row_drift_reasons": drift_reasons,
    }


def _hybrid_state_patch_row_receipt(
    *,
    row: dict[str, Any],
    expected_row_index: int,
) -> dict[str, object]:
    row_index = _non_negative_int(row.get("row_index", expected_row_index))
    seq_len = _non_negative_int(row.get("seq_len", 0))
    cache_offset = _non_negative_int(row.get("cache_offset", 0))
    cache_advance = _non_negative_int(row.get("cache_advance", seq_len))
    expected_cache_advance = _non_negative_int(
        row.get("expected_cache_advance", cache_advance)
    )
    media_count = _non_negative_int(row.get("media_count", 0))
    contiguous_state_start = _non_negative_int(
        row.get("contiguous_state_start", cache_offset)
    )
    contiguous_state_end = _non_negative_int(
        row.get("contiguous_state_end", contiguous_state_start + cache_advance)
    )
    expected_contiguous_state_start = _non_negative_int(
        row.get("expected_contiguous_state_start", cache_offset)
    )
    expected_contiguous_state_end = _non_negative_int(
        row.get(
            "expected_contiguous_state_end",
            expected_contiguous_state_start + expected_cache_advance,
        )
    )
    default_rope_mode = "multimodal" if media_count else "text_only"
    text_only_rope_mode = str(row.get("text_only_rope_mode", default_rope_mode) or "")
    expected_text_only_rope_mode = str(
        row.get("expected_text_only_rope_mode", default_rope_mode) or ""
    )

    drift_reasons: list[str] = []
    if row_index != expected_row_index:
        drift_reasons.append("row_index_mismatch")
    if seq_len <= 0:
        drift_reasons.append("seq_len_missing")
    if cache_advance != expected_cache_advance:
        drift_reasons.append("cache_advance_mismatch")
    if contiguous_state_start != expected_contiguous_state_start:
        drift_reasons.append("contiguous_state_start_mismatch")
    if contiguous_state_end != expected_contiguous_state_end:
        drift_reasons.append("contiguous_state_end_mismatch")
    if text_only_rope_mode != expected_text_only_rope_mode:
        drift_reasons.append("text_only_rope_mode_mismatch")

    return {
        "row_index": row_index,
        "seq_len": seq_len,
        "cache_offset": cache_offset,
        "cache_advance": cache_advance,
        "expected_cache_advance": expected_cache_advance,
        "media_count": media_count,
        "contiguous_state_start": contiguous_state_start,
        "contiguous_state_end": contiguous_state_end,
        "expected_contiguous_state_start": expected_contiguous_state_start,
        "expected_contiguous_state_end": expected_contiguous_state_end,
        "text_only_rope_mode": text_only_rope_mode,
        "row_state_guard": "row_drift" if drift_reasons else "aligned",
        "row_drift_reasons": drift_reasons,
    }


def _quantized_kv_mask_row_receipt(
    *,
    row: dict[str, Any],
    expected_row_index: int,
) -> dict[str, object]:
    row_index = _non_negative_int(row.get("row_index", expected_row_index))
    seq_len = _non_negative_int(row.get("seq_len", 0))
    cache_offset = _non_negative_int(row.get("cache_offset", 0))
    expected_cache_offset = _non_negative_int(row.get("expected_cache_offset", cache_offset))
    kv_seq_len = _non_negative_int(row.get("kv_seq_len", cache_offset + seq_len))
    cache_mask_shape = _normalized_shape(row.get("cache_mask_shape", row.get("mask_shape")))
    expected_cache_mask_shape = _normalized_shape(row.get("expected_cache_mask_shape"))
    if not expected_cache_mask_shape:
        expected_cache_mask_shape = [1, 1, seq_len, kv_seq_len]

    drift_reasons: list[str] = []
    if row_index != expected_row_index:
        drift_reasons.append("row_index_mismatch")
    if cache_offset != expected_cache_offset:
        drift_reasons.append("cache_offset_mismatch")
    if seq_len <= 0:
        drift_reasons.append("seq_len_missing")
    if kv_seq_len <= 0:
        drift_reasons.append("kv_seq_len_missing")
    if not cache_mask_shape:
        drift_reasons.append("cache_mask_shape_missing")
    elif cache_mask_shape != expected_cache_mask_shape:
        drift_reasons.append("cache_mask_shape_mismatch")

    return {
        "row_index": row_index,
        "cache_offset": cache_offset,
        "seq_len": seq_len,
        "kv_seq_len": kv_seq_len,
        "expected_cache_mask_shape": expected_cache_mask_shape,
        "cache_mask_shape": cache_mask_shape,
        "cache_mask_guard": "row_drift" if drift_reasons else "aligned",
        "cache_mask_drift_reasons": drift_reasons,
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


def _normalized_prompt_kwargs(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, int] = {}
    for key in sorted(value):
        normalized[str(key)] = _non_negative_int(value[key])
    return normalized


def _normalized_identity(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)]


def _normalized_shape(value: Any) -> list[int]:
    if value is None:
        return []
    shape = getattr(value, "shape", None)
    if isinstance(shape, (list, tuple)):
        return _flatten_shape_parts(shape)
    if isinstance(value, (list, tuple)):
        return _flatten_shape_parts(value)
    return [_non_negative_int(value)]


def _flatten_shape_parts(value: list[Any] | tuple[Any, ...]) -> list[int]:
    parts: list[int] = []
    for part in value:
        if isinstance(part, (list, tuple)):
            parts.extend(_flatten_shape_parts(part))
        else:
            parts.append(_non_negative_int(part))
    return parts


def _non_negative_int(value: Any) -> int:
    return max(0, int(value or 0))


def _logit_parity_receipt(
    *,
    quantized_logits: Any | None,
    unquantized_logits: Any | None,
    tolerance: float,
) -> dict[str, object]:
    normalized_tolerance = max(0.0, float(tolerance or 0.0))
    if quantized_logits is None or unquantized_logits is None:
        return {
            "status": "not_provided",
            "sample_count": 0,
            "max_abs_delta": 0.0,
            "tolerance": normalized_tolerance,
        }

    quantized_shape = _numeric_shape(quantized_logits)
    unquantized_shape = _numeric_shape(unquantized_logits)
    quantized_values = _flatten_numeric_values(quantized_logits)
    unquantized_values = _flatten_numeric_values(unquantized_logits)
    sample_count = min(len(quantized_values), len(unquantized_values))
    if quantized_shape != unquantized_shape:
        status = "shape_mismatch"
    elif len(quantized_values) != len(unquantized_values):
        status = "shape_mismatch"
    elif sample_count == 0:
        status = "empty"
    else:
        status = "within_tolerance"

    max_abs_delta = 0.0
    if sample_count:
        max_abs_delta = max(
            abs(quantized_values[index] - unquantized_values[index])
            for index in range(sample_count)
        )
        if status == "within_tolerance" and max_abs_delta > normalized_tolerance:
            status = "outside_tolerance"

    return {
        "status": status,
        "sample_count": sample_count,
        "max_abs_delta": round(max_abs_delta, 10),
        "tolerance": normalized_tolerance,
    }


def _numeric_shape(value: Any) -> tuple[int, ...]:
    shape = getattr(value, "shape", None)
    if isinstance(shape, (list, tuple)):
        return tuple(_non_negative_int(part) for part in shape)

    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        value = tolist()
    if isinstance(value, (list, tuple)):
        if not value:
            return (0,)
        child_shapes = [_numeric_shape(item) for item in value]
        first_shape = child_shapes[0]
        if any(child_shape != first_shape for child_shape in child_shapes):
            return (len(value), -1)
        return (len(value), *first_shape)
    return ()


def _flatten_numeric_values(value: Any) -> list[float]:
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        value = tolist()
    if isinstance(value, (list, tuple)):
        flattened: list[float] = []
        for item in value:
            flattened.extend(_flatten_numeric_values(item))
        return flattened
    return [float(value)]


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
