from __future__ import annotations

import hashlib
from collections import OrderedDict
from dataclasses import dataclass
import logging
from threading import Lock
from typing import Any

from worker.runtime.multimodal_preprocessing import PreparedImageInput, PreparedVisionRequest

logger = logging.getLogger(__name__)

MULTIMODAL_DECODE_BASELINE = "baseline"
MULTIMODAL_DECODE_SINGLE_STREAM = "single_stream"
MULTIMODAL_DECODE_IMAGE_CACHE_REUSE = "image_cache_reuse"
MULTIMODAL_DECODE_NATIVE_QUANTIZED = "native_quantized"
MULTIMODAL_DECODE_FALLBACK = "fallback"

MULTIMODAL_LOAD_NATIVE_QUANTIZED = "native_quantized"
MULTIMODAL_LOAD_FALLBACK = "fallback"

_SUPPORTED_FAST_PATH_FAMILIES = frozenset({"gemma4-v1", "llava-v1", "paligemma-v1"})
_NATIVE_QUANTIZED_PROFILES = frozenset({"q4", "q6", "q8", "int4", "int8", "mlx-q4", "mlx-q8"})


@dataclass(frozen=True)
class ImageFeatureCacheKey:
    family_id: str
    adapter_hash: str
    preprocessing_fingerprint: str
    quant_profile_id: str
    sha256_hex: str


@dataclass(frozen=True)
class MultimodalFastPathDecision:
    image_feature_cache_hits: int
    image_feature_cache_misses: int
    multimodal_decode_mode: str
    multimodal_fallback_reason: str
    multimodal_decode_sync_mode: str
    multi_image_scatter_mode: str
    quantized_load_mode: str
    quantized_load_fallback_reason: str


class MultimodalFastPathController:
    """Tracks Melix-owned VLM fast-path admission without changing request APIs."""

    def __init__(self, *, max_image_feature_cache_entries: int = 1024) -> None:
        self._max_image_feature_cache_entries = max(max_image_feature_cache_entries, 1)
        self._image_feature_cache: OrderedDict[ImageFeatureCacheKey, None] = OrderedDict()
        self._image_feature_cache_lock = Lock()

    def plan(
        self,
        loaded_model: Any,
        prepared_request: PreparedVisionRequest,
    ) -> MultimodalFastPathDecision:
        metadata = _loaded_metadata(loaded_model)
        family_id = _loaded_value(loaded_model, metadata, "vision_family_id")
        resolved_execution_mode = (
            str(metadata.get("melix.vlm.execution_mode", "") or "").strip()
            or str(metadata.get("execution_mode", "") or "").strip()
        )
        execution_mode = (
            resolved_execution_mode
            or "multimodal"
        )
        quant_profile_id = _loaded_value(loaded_model, metadata, "quant_profile_id") or "none"
        quantized_load_mode, quantized_fallback = self._quantized_load_admission(
            family_id=family_id,
            execution_mode=execution_mode,
            quant_profile_id=quant_profile_id,
        )

        if not prepared_request.images and not prepared_request.videos:
            return MultimodalFastPathDecision(
                image_feature_cache_hits=0,
                image_feature_cache_misses=0,
                multimodal_decode_mode=MULTIMODAL_DECODE_BASELINE,
                multimodal_fallback_reason="no_media",
                multimodal_decode_sync_mode=MULTIMODAL_DECODE_BASELINE,
                multi_image_scatter_mode="none",
                quantized_load_mode=quantized_load_mode,
                quantized_load_fallback_reason=quantized_fallback,
            )

        if execution_mode == "text_backed":
            return self._fallback_decision(
                reason="text_backed_no_vision_weights",
                quantized_load_mode=quantized_load_mode,
                quantized_load_fallback_reason=quantized_fallback or "text_backed_no_vision_weights",
            )

        if not family_id or not resolved_execution_mode:
            logger.warning(
                "VLM fast-path metadata is incomplete; family_id_present=%s execution_mode_present=%s",
                bool(family_id),
                bool(resolved_execution_mode),
            )

        if family_id not in _SUPPORTED_FAST_PATH_FAMILIES:
            return self._fallback_decision(
                reason="unsupported_family",
                quantized_load_mode=MULTIMODAL_LOAD_FALLBACK,
                quantized_load_fallback_reason="unsupported_family",
            )

        if prepared_request.videos and not prepared_request.images:
            return self._fallback_decision(
                reason="video_fast_path_unimplemented",
                quantized_load_mode=quantized_load_mode,
                quantized_load_fallback_reason=quantized_fallback,
            )

        hits = 0
        misses = 0
        with self._image_feature_cache_lock:
            for image in prepared_request.images:
                if not image.sha256_hex:
                    misses += 1
                    continue
                key = self._cache_key(
                    image=image,
                    family_id=family_id,
                    adapter_hash=_adapter_hash(metadata),
                    quant_profile_id=quant_profile_id,
                    metadata=metadata,
                )
                if key in self._image_feature_cache:
                    hits += 1
                    self._image_feature_cache.move_to_end(key)
                    continue
                misses += 1
                self._image_feature_cache[key] = None
                # If one request exceeds the bounded cache size, earlier images in that
                # request can be evicted before the next request observes them.
                while len(self._image_feature_cache) > self._max_image_feature_cache_entries:
                    self._image_feature_cache.popitem(last=False)

        if hits > 0:
            decode_mode = MULTIMODAL_DECODE_IMAGE_CACHE_REUSE
        elif quantized_load_mode == MULTIMODAL_LOAD_NATIVE_QUANTIZED:
            decode_mode = MULTIMODAL_DECODE_NATIVE_QUANTIZED
        else:
            decode_mode = MULTIMODAL_DECODE_SINGLE_STREAM
        return MultimodalFastPathDecision(
            image_feature_cache_hits=hits,
            image_feature_cache_misses=misses,
            multimodal_decode_mode=decode_mode,
            multimodal_fallback_reason="",
            multimodal_decode_sync_mode="executor_stream",
            multi_image_scatter_mode="per_sample" if len(prepared_request.images) > 1 else "none",
            quantized_load_mode=quantized_load_mode,
            quantized_load_fallback_reason=quantized_fallback,
        )

    @staticmethod
    def _cache_key(
        *,
        image: PreparedImageInput,
        family_id: str,
        adapter_hash: str,
        quant_profile_id: str,
        metadata: dict[str, str],
    ) -> ImageFeatureCacheKey:
        digest = hashlib.sha256()
        for value in (
            image.mime_type,
            image.format,
            metadata.get("vision_prompt_profile_id", ""),
            metadata.get("vision_tokenization_mode", ""),
            metadata.get("vision_max_images_per_prompt", ""),
        ):
            digest.update(str(value or "").encode("utf-8"))
            digest.update(b"\0")
        return ImageFeatureCacheKey(
            family_id=family_id,
            adapter_hash=adapter_hash,
            preprocessing_fingerprint=digest.hexdigest(),
            quant_profile_id=quant_profile_id,
            sha256_hex=image.sha256_hex,
        )

    @staticmethod
    def _fallback_decision(
        *,
        reason: str,
        quantized_load_mode: str,
        quantized_load_fallback_reason: str,
    ) -> MultimodalFastPathDecision:
        return MultimodalFastPathDecision(
            image_feature_cache_hits=0,
            image_feature_cache_misses=0,
            multimodal_decode_mode=MULTIMODAL_DECODE_FALLBACK,
            multimodal_fallback_reason=reason,
            multimodal_decode_sync_mode=MULTIMODAL_DECODE_BASELINE,
            multi_image_scatter_mode="none",
            quantized_load_mode=quantized_load_mode,
            quantized_load_fallback_reason=quantized_load_fallback_reason,
        )

    @staticmethod
    def _quantized_load_admission(
        *,
        family_id: str,
        execution_mode: str,
        quant_profile_id: str,
    ) -> tuple[str, str]:
        if not quant_profile_id or quant_profile_id.lower() in {"none", "fp16", "float16"}:
            return MULTIMODAL_LOAD_FALLBACK, "not_quantized"
        normalized = quant_profile_id.lower()
        is_quantized = normalized in _NATIVE_QUANTIZED_PROFILES
        if not is_quantized:
            return MULTIMODAL_LOAD_FALLBACK, "unsupported_quant_profile"
        if execution_mode == "text_backed":
            return MULTIMODAL_LOAD_FALLBACK, "text_backed_no_vision_weights"
        if family_id not in _SUPPORTED_FAST_PATH_FAMILIES:
            return MULTIMODAL_LOAD_FALLBACK, "unsupported_family"
        return MULTIMODAL_LOAD_NATIVE_QUANTIZED, ""


def _loaded_metadata(loaded_model: Any) -> dict[str, str]:
    if not isinstance(loaded_model, dict):
        return {}
    combined: dict[str, str] = {}
    for key in (
        "melix.vlm.execution_mode",
        "vision_family_id",
        "vision_prompt_profile_id",
        "vision_tokenization_mode",
        "vision_max_images_per_prompt",
        "melix.multimodal_adapter_hash",
        "multimodal_adapter_hash",
    ):
        value = loaded_model.get(key)
        if isinstance(value, str) and value.strip():
            combined[key] = value.strip()
    metadata = loaded_model.get("metadata", {})
    if isinstance(metadata, dict):
        # The nested runtime metadata is authoritative; top-level values are import-time copies.
        for key, value in metadata.items():
            normalized = str(value).strip()
            if normalized:
                combined[str(key)] = normalized
    return combined


def _loaded_value(loaded_model: Any, metadata: dict[str, str], key: str) -> str:
    if metadata_value := str(metadata.get(key, "") or "").strip():
        return metadata_value
    if isinstance(loaded_model, dict):
        value = loaded_model.get(key, "")
        if value:
            return str(value).strip()
    return ""


def _adapter_hash(metadata: dict[str, str]) -> str:
    return (
        metadata.get("melix.multimodal_adapter_hash", "").strip()
        or metadata.get("multimodal_adapter_hash", "").strip()
        or "adapter-unset"
    )
