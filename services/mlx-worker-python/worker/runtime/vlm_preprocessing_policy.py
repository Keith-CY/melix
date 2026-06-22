from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

_SUPPORTED_IMAGE_PREPROCESSING_HINTS = frozenset(
    {
        "input_data_format",
        "layout",
        "max_pixels",
        "min_pixels",
        "resized_height",
        "resized_width",
    }
)
_IMAGE_PREPROCESSING_INT_HINTS = frozenset(
    {
        "max_pixels",
        "min_pixels",
        "resized_height",
        "resized_width",
    }
)
_IMAGE_PREPROCESSING_LAYOUT_VALUES = frozenset({"channels_first", "channels_last"})
EMPTY_PREPROCESSING_POLICY: dict[str, object] = {}
EMPTY_PREPROCESSING_POLICY_RECEIPT: dict[str, object] = {}


def empty_preprocessing_policy() -> dict[str, object]:
    return EMPTY_PREPROCESSING_POLICY


def empty_preprocessing_policy_receipt() -> dict[str, object]:
    return EMPTY_PREPROCESSING_POLICY_RECEIPT


def normalize_image_preprocessing_policy(
    hints: Any,
    *,
    error_factory: type[Exception] = ValueError,
) -> dict[str, object]:
    if not hints:
        return EMPTY_PREPROCESSING_POLICY
    normalized: dict[str, object] = {}
    for raw_key in sorted(hints):
        key = str(raw_key).strip()
        if key not in _SUPPORTED_IMAGE_PREPROCESSING_HINTS:
            raise error_factory(f"unsupported_preprocessing_field: {key}")
        raw_value = str(hints[raw_key]).strip()
        if not raw_value:
            continue
        if key in _IMAGE_PREPROCESSING_INT_HINTS:
            normalized[key] = _positive_preprocessing_int(key, raw_value, error_factory)
            continue
        normalized[key] = _normalized_layout_value(key, raw_value, error_factory)
    return normalized or EMPTY_PREPROCESSING_POLICY


def normalize_media_preprocessing_policy(
    media: Any,
    *,
    error_factory: type[Exception] = ValueError,
) -> dict[str, object]:
    hints = getattr(media, "preprocessing_hints", None)
    if not hints:
        return EMPTY_PREPROCESSING_POLICY
    return normalize_image_preprocessing_policy(hints, error_factory=error_factory)


def _positive_preprocessing_int(
    key: str,
    raw_value: str,
    error_factory: type[Exception],
) -> int:
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise error_factory(f"invalid_preprocessing_value: {key}") from exc
    if value <= 0:
        raise error_factory(f"invalid_preprocessing_value: {key}")
    return value


def _normalized_layout_value(
    key: str,
    raw_value: str,
    error_factory: type[Exception],
) -> str:
    value = raw_value.strip().lower().replace("-", "_")
    if value not in _IMAGE_PREPROCESSING_LAYOUT_VALUES:
        raise error_factory(f"invalid_preprocessing_value: {key}")
    return value


def preprocessing_policy_signature_value(policy: dict[str, object]) -> str:
    if not policy:
        return ""
    return json.dumps(
        {str(key): policy[key] for key in sorted(policy)},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def update_image_hash_with_policy(digest: Any, image: Any) -> None:
    policy = getattr(image, "preprocessing_policy", EMPTY_PREPROCESSING_POLICY)
    if not policy:
        return
    policy_signature = preprocessing_policy_signature_value(policy)
    digest.update(b"\0preprocessing_policy\0")
    digest.update(policy_signature.encode("utf-8"))


def update_multimodal_image_hashes(
    digest: Any,
    images: Iterable[Any],
    *,
    has_preprocessing_policy: bool,
) -> None:
    for image in images:
        digest.update(image.sha256_hex.encode("ascii"))
        if has_preprocessing_policy:
            update_image_hash_with_policy(digest, image)


def request_preprocessing_policy_signature_for_known_policy_state(
    images: Iterable[Any],
    *,
    has_preprocessing_policy: bool,
) -> str:
    if not has_preprocessing_policy:
        return ""
    return request_preprocessing_policy_signature(images)


def request_preprocessing_policy_signature(images: Iterable[Any]) -> str:
    image_sequence = images if isinstance(images, (list, tuple)) else tuple(images)
    has_policy = False
    for image in image_sequence:
        if getattr(image, "preprocessing_policy", EMPTY_PREPROCESSING_POLICY):
            has_policy = True
            break
    if not has_policy:
        return ""

    chunks: list[str] = []
    for index, image in enumerate(image_sequence):
        policy_signature = preprocessing_policy_signature_value(
            getattr(image, "preprocessing_policy", EMPTY_PREPROCESSING_POLICY)
        )
        chunks.append(f"({str(index)!r}, {policy_signature!r})")
    if len(chunks) == 1:
        return f"({chunks[0]},)"
    return "(" + ", ".join(chunks) + ")"


def preprocessing_policy_receipt_value(images: Iterable[Any]) -> dict[str, object]:
    policies: list[dict[str, object]] = []
    accepted_fields: set[str] = set()
    image_count = 0
    for index, image in enumerate(images):
        image_count += 1
        image_policy = getattr(image, "preprocessing_policy", EMPTY_PREPROCESSING_POLICY)
        if not image_policy:
            continue
        policy = {str(key): image_policy[key] for key in sorted(image_policy)}
        accepted_fields.update(policy)
        policies.append(
            {
                "image_index": index,
                "policy": policy,
            }
        )
    if not policies:
        return EMPTY_PREPROCESSING_POLICY_RECEIPT
    return {
        "image_count": image_count,
        "policy_count": len(policies),
        "accepted_fields": sorted(accepted_fields),
        "unsupported_fields": [],
        "policies": policies,
    }


def prepared_request_preprocessing_policy_receipt(prepared_request: Any) -> dict[str, object]:
    if not getattr(prepared_request, "preprocessing_policy_signature", ""):
        return EMPTY_PREPROCESSING_POLICY_RECEIPT
    return preprocessing_policy_receipt_value(getattr(prepared_request, "images", ()))


def image_preprocessing_resize_shape(images: Iterable[Any]) -> tuple[int, int] | None:
    resize_shape: tuple[int, int] | None = None
    for image in images:
        policy = getattr(image, "preprocessing_policy", EMPTY_PREPROCESSING_POLICY)
        height = policy.get("resized_height")
        width = policy.get("resized_width")
        if height is None and width is None:
            continue
        if not isinstance(height, int) or not isinstance(width, int):
            return None
        candidate = (height, width)
        if resize_shape is None:
            resize_shape = candidate
            continue
        if resize_shape != candidate:
            return None
    return resize_shape


def apply_resize_shape_to_stream_kwargs(
    stream_kwargs: dict[str, object],
    prepared_request: Any,
) -> None:
    if not getattr(prepared_request, "preprocessing_policy_signature", ""):
        return
    resize_shape = image_preprocessing_resize_shape(getattr(prepared_request, "images", ()))
    if resize_shape is not None:
        stream_kwargs["resize_shape"] = resize_shape
