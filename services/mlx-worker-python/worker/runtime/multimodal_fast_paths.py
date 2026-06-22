from __future__ import annotations

import hashlib
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
import logging
from threading import Lock
from typing import Any, Callable

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
_HYBRID_STATE_PATCH_FAMILIES = frozenset({"gemma4-v1", "llava-v1"})
_NATIVE_QUANTIZED_PROFILES = frozenset({"q4", "q6", "q8", "int4", "int8", "mlx-q4", "mlx-q8"})
_FAST_PATH_SIGNATURE_CORE_METADATA_KEYS = frozenset(
    {
        "melix.vlm.execution_mode",
        "vision_family_id",
        "vision_prompt_profile_id",
        "vision_tokenization_mode",
        "vision_max_images_per_prompt",
        "melix.multimodal_adapter_hash",
        "multimodal_adapter_hash",
    }
)
_FAST_PATH_SIGNATURE_PROCESSOR_METADATA_KEYS = frozenset(
    {
        "vision_processor_policy",
        "vision_processor_crop_grid",
        "vision_processor_patch_size",
        "vision_processor_max_crop_count",
        "vision_prompt_format",
        "vision_projected_feature_shape",
    }
)
_FAST_PATH_SIGNATURE_METADATA_KEYS = (
    _FAST_PATH_SIGNATURE_CORE_METADATA_KEYS | _FAST_PATH_SIGNATURE_PROCESSOR_METADATA_KEYS
)
_FAST_PATH_SIGNATURE_METADATA_KEYS_SORTED = tuple(sorted(_FAST_PATH_SIGNATURE_METADATA_KEYS))
_FAST_PATH_SIGNATURE_CORE_METADATA_KEYS_SORTED = tuple(
    sorted(_FAST_PATH_SIGNATURE_CORE_METADATA_KEYS)
)
_FAST_PATH_SIGNATURE_TOP_LEVEL_KEYS = ("model_id", "revision", "tokenizer_hash", "quant_profile_id")
_FAST_PATH_SIGNATURE_TOP_LEVEL_KEYS_SORTED = tuple(sorted(_FAST_PATH_SIGNATURE_TOP_LEVEL_KEYS))


@dataclass(frozen=True, slots=True)
class ImageFeatureCacheKey:
    family_id: str
    adapter_hash: str
    preprocessing_fingerprint: str
    quant_profile_id: str
    sha256_hex: str


@dataclass(frozen=True, slots=True)
class ImageFeatureCacheEntry:
    payload: Any
    byte_length: int


@dataclass(frozen=True, slots=True)
class MultimodalFastPathDecision:
    image_feature_cache_hits: int
    image_feature_cache_misses: int
    image_feature_cache_artifact_count: int
    image_feature_cache_bytes: int
    image_feature_encoder_calls_saved: int
    image_feature_work_saved_bytes: int
    image_feature_cache_fallback_reason: str
    multimodal_decode_mode: str
    multimodal_fallback_reason: str
    multimodal_decode_sync_mode: str
    multi_image_scatter_mode: str
    quantized_load_mode: str
    quantized_load_fallback_reason: str
    hybrid_state_patch_mode: str
    hybrid_state_media_count: int
    family_fast_path_override_count: int


_NO_MEDIA_FAST_PATH_DECISION = MultimodalFastPathDecision(
    image_feature_cache_hits=0,
    image_feature_cache_misses=0,
    image_feature_cache_artifact_count=0,
    image_feature_cache_bytes=0,
    image_feature_encoder_calls_saved=0,
    image_feature_work_saved_bytes=0,
    image_feature_cache_fallback_reason="",
    multimodal_decode_mode=MULTIMODAL_DECODE_BASELINE,
    multimodal_fallback_reason="no_media",
    multimodal_decode_sync_mode=MULTIMODAL_DECODE_BASELINE,
    multi_image_scatter_mode="none",
    quantized_load_mode=MULTIMODAL_LOAD_FALLBACK,
    quantized_load_fallback_reason="not_quantized",
    hybrid_state_patch_mode="not_applicable",
    hybrid_state_media_count=0,
    family_fast_path_override_count=0,
)


class MultimodalFastPathController:
    """Tracks Melix-owned VLM fast-path admission without changing request APIs."""

    def __init__(self, *, max_image_feature_cache_entries: int = 1024) -> None:
        self._max_image_feature_cache_entries = max(max_image_feature_cache_entries, 1)
        self._image_feature_cache: OrderedDict[ImageFeatureCacheKey, ImageFeatureCacheEntry] = (
            OrderedDict()
        )
        self._image_feature_cache_lock = Lock()

    def plan(
        self,
        loaded_model: Any,
        prepared_request: PreparedVisionRequest,
    ) -> MultimodalFastPathDecision:
        if not prepared_request.images and not prepared_request.videos:
            family_id = _loaded_metadata_value(loaded_model, "vision_family_id")
            resolved_execution_mode = (
                _loaded_metadata_value(loaded_model, "melix.vlm.execution_mode")
                or _loaded_metadata_value(loaded_model, "execution_mode")
            )
            execution_mode = resolved_execution_mode or "multimodal"
            quant_profile_id = _loaded_metadata_value(loaded_model, "quant_profile_id") or "none"
            quantized_load_mode, quantized_fallback = self._quantized_load_admission(
                family_id=family_id,
                execution_mode=execution_mode,
                quant_profile_id=quant_profile_id,
            )
            if quantized_load_mode == MULTIMODAL_LOAD_FALLBACK and quantized_fallback == "not_quantized":
                return _NO_MEDIA_FAST_PATH_DECISION
            return MultimodalFastPathDecision(
                image_feature_cache_hits=0,
                image_feature_cache_misses=0,
                image_feature_cache_artifact_count=0,
                image_feature_cache_bytes=0,
                image_feature_encoder_calls_saved=0,
                image_feature_work_saved_bytes=0,
                image_feature_cache_fallback_reason="",
                multimodal_decode_mode=MULTIMODAL_DECODE_BASELINE,
                multimodal_fallback_reason="no_media",
                multimodal_decode_sync_mode=MULTIMODAL_DECODE_BASELINE,
                multi_image_scatter_mode="none",
                quantized_load_mode=quantized_load_mode,
                quantized_load_fallback_reason=quantized_fallback,
                hybrid_state_patch_mode="not_applicable",
                hybrid_state_media_count=0,
                family_fast_path_override_count=0,
            )

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
                hybrid_state_patch_mode="fallback",
                hybrid_state_media_count=0,
                family_fast_path_override_count=1,
            )

        if prepared_request.videos:
            return self._fallback_decision(
                reason="video_fast_path_unimplemented",
                quantized_load_mode=quantized_load_mode,
                quantized_load_fallback_reason=quantized_fallback,
                hybrid_state_patch_mode="fallback",
                hybrid_state_media_count=0,
                family_fast_path_override_count=1,
            )

        hits = 0
        misses = 0
        work_saved_bytes = 0
        artifact_count = 0
        artifact_bytes = 0
        adapter_hash = _adapter_hash(metadata)
        cache_key_factory = self._cache_key_factory(
            family_id=family_id,
            adapter_hash=adapter_hash,
            quant_profile_id=quant_profile_id,
            metadata=metadata,
        )
        with self._image_feature_cache_lock:
            for image in prepared_request.images:
                if not image.sha256_hex:
                    misses += 1
                    continue
                key = cache_key_factory(image)
                entry = self._image_feature_cache.get(key)
                if entry is not None:
                    hits += 1
                    work_saved_bytes += image.byte_length
                    self._image_feature_cache.move_to_end(key)
                    continue
                misses += 1
            artifact_count, artifact_bytes = self._image_feature_cache_summary_locked()

        if hits > 0:
            decode_mode = MULTIMODAL_DECODE_IMAGE_CACHE_REUSE
        elif quantized_load_mode == MULTIMODAL_LOAD_NATIVE_QUANTIZED:
            decode_mode = MULTIMODAL_DECODE_NATIVE_QUANTIZED
        else:
            decode_mode = MULTIMODAL_DECODE_SINGLE_STREAM
        hybrid_state_patch_mode = (
            "family_scoped" if family_id in _HYBRID_STATE_PATCH_FAMILIES else "not_applicable"
        )
        hybrid_state_media_count = (
            max(1, len(prepared_request.images) + len(prepared_request.videos))
            if hybrid_state_patch_mode == "family_scoped"
            else 0
        )
        return MultimodalFastPathDecision(
            image_feature_cache_hits=hits,
            image_feature_cache_misses=misses,
            image_feature_cache_artifact_count=artifact_count,
            image_feature_cache_bytes=artifact_bytes,
            image_feature_encoder_calls_saved=hits,
            image_feature_work_saved_bytes=work_saved_bytes,
            image_feature_cache_fallback_reason="",
            multimodal_decode_mode=decode_mode,
            multimodal_fallback_reason="",
            multimodal_decode_sync_mode="executor_stream",
            multi_image_scatter_mode="per_sample" if len(prepared_request.images) > 1 else "single",
            quantized_load_mode=quantized_load_mode,
            quantized_load_fallback_reason=quantized_fallback,
            hybrid_state_patch_mode=hybrid_state_patch_mode,
            hybrid_state_media_count=hybrid_state_media_count,
            family_fast_path_override_count=0,
        )

    def image_feature_payloads(
        self,
        *,
        loaded_model: Any,
        prepared_request: PreparedVisionRequest,
    ) -> tuple[Any | None, ...]:
        if not prepared_request.images:
            return ()
        metadata = _loaded_metadata(loaded_model)
        family_id = _loaded_value(loaded_model, metadata, "vision_family_id")
        if family_id not in _SUPPORTED_FAST_PATH_FAMILIES:
            return tuple(None for _ in prepared_request.images)
        cache_key_factory = self._cache_key_factory(
            family_id=family_id,
            adapter_hash=_adapter_hash(metadata),
            quant_profile_id=_loaded_value(loaded_model, metadata, "quant_profile_id") or "none",
            metadata=metadata,
        )
        payloads: list[Any | None] = []
        with self._image_feature_cache_lock:
            for image in prepared_request.images:
                if not image.sha256_hex:
                    payloads.append(None)
                    continue
                key = cache_key_factory(image)
                entry = self._image_feature_cache.get(key)
                if entry is None:
                    payloads.append(None)
                    continue
                self._image_feature_cache.move_to_end(key)
                payloads.append(entry.payload)
        return tuple(payloads)

    def put_image_feature_payloads(
        self,
        *,
        loaded_model: Any,
        prepared_request: PreparedVisionRequest,
        payloads: tuple[Any | None, ...],
    ) -> tuple[bool, ...]:
        image_count = len(prepared_request.images)
        if image_count <= 0:
            return ()
        metadata = _loaded_metadata(loaded_model)
        family_id = _loaded_value(loaded_model, metadata, "vision_family_id")
        stored = [False] * image_count
        if family_id not in _SUPPORTED_FAST_PATH_FAMILIES:
            return tuple(stored)
        cache_key_factory = self._cache_key_factory(
            family_id=family_id,
            adapter_hash=_adapter_hash(metadata),
            quant_profile_id=_loaded_value(loaded_model, metadata, "quant_profile_id") or "none",
            metadata=metadata,
        )
        with self._image_feature_cache_lock:
            for index, image in enumerate(prepared_request.images):
                if index >= len(payloads):
                    break
                payload = payloads[index]
                if payload is None or not image.sha256_hex:
                    continue
                key = cache_key_factory(image)
                self._image_feature_cache[key] = ImageFeatureCacheEntry(
                    payload=payload,
                    byte_length=_payload_byte_length(payload),
                )
                self._image_feature_cache.move_to_end(key)
                stored[index] = True
            while len(self._image_feature_cache) > self._max_image_feature_cache_entries:
                self._image_feature_cache.popitem(last=False)
        return tuple(stored)

    def image_feature_cache_summary(self) -> tuple[int, int]:
        with self._image_feature_cache_lock:
            return self._image_feature_cache_summary_locked()

    def image_feature_cache_keys(self) -> tuple[ImageFeatureCacheKey, ...]:
        with self._image_feature_cache_lock:
            return tuple(self._image_feature_cache)

    def _image_feature_cache_summary_locked(self) -> tuple[int, int]:
        return (
            len(self._image_feature_cache),
            sum(entry.byte_length for entry in self._image_feature_cache.values()),
        )

    @staticmethod
    def _cache_key_factory(
        *,
        family_id: str,
        adapter_hash: str,
        quant_profile_id: str,
        metadata: dict[str, str],
    ) -> Callable[[PreparedImageInput], ImageFeatureCacheKey]:
        vision_prompt_profile_id = metadata.get("vision_prompt_profile_id", "")
        vision_tokenization_mode = metadata.get("vision_tokenization_mode", "")
        vision_max_images_per_prompt = metadata.get("vision_max_images_per_prompt", "")
        vision_processor_policy = metadata.get("vision_processor_policy", "")
        vision_processor_crop_grid = metadata.get("vision_processor_crop_grid", "")
        vision_processor_patch_size = metadata.get("vision_processor_patch_size", "")
        vision_processor_max_crop_count = metadata.get("vision_processor_max_crop_count", "")
        vision_prompt_format = metadata.get("vision_prompt_format", "")
        vision_projected_feature_shape = metadata.get("vision_projected_feature_shape", "")
        preprocessing_fingerprints: dict[tuple[str, str], str] = {}

        def build(image: PreparedImageInput) -> ImageFeatureCacheKey:
            shape = (image.mime_type, image.format)
            preprocessing_fingerprint = preprocessing_fingerprints.get(shape)
            if preprocessing_fingerprint is None:
                preprocessing_fingerprint = _preprocessing_fingerprint(
                    image.mime_type,
                    image.format,
                    vision_prompt_profile_id,
                    vision_tokenization_mode,
                    vision_max_images_per_prompt,
                    vision_processor_policy,
                    vision_processor_crop_grid,
                    vision_processor_patch_size,
                    vision_processor_max_crop_count,
                    vision_prompt_format,
                    vision_projected_feature_shape,
                )
                preprocessing_fingerprints[shape] = preprocessing_fingerprint
            return ImageFeatureCacheKey(
                family_id=family_id,
                adapter_hash=adapter_hash,
                preprocessing_fingerprint=preprocessing_fingerprint,
                quant_profile_id=quant_profile_id,
                sha256_hex=image.sha256_hex,
            )

        return build

    @staticmethod
    def _cache_key(
        *,
        image: PreparedImageInput,
        family_id: str,
        adapter_hash: str,
        quant_profile_id: str,
        metadata: dict[str, str],
    ) -> ImageFeatureCacheKey:
        return MultimodalFastPathController._cache_key_factory(
            family_id=family_id,
            adapter_hash=adapter_hash,
            quant_profile_id=quant_profile_id,
            metadata=metadata,
        )(image)

    @staticmethod
    def _fallback_decision(
        *,
        reason: str,
        quantized_load_mode: str,
        quantized_load_fallback_reason: str,
        hybrid_state_patch_mode: str = "fallback",
        hybrid_state_media_count: int = 0,
        family_fast_path_override_count: int = 0,
    ) -> MultimodalFastPathDecision:
        return MultimodalFastPathDecision(
            image_feature_cache_hits=0,
            image_feature_cache_misses=0,
            image_feature_cache_artifact_count=0,
            image_feature_cache_bytes=0,
            image_feature_encoder_calls_saved=0,
            image_feature_work_saved_bytes=0,
            image_feature_cache_fallback_reason="",
            multimodal_decode_mode=MULTIMODAL_DECODE_FALLBACK,
            multimodal_fallback_reason=reason,
            multimodal_decode_sync_mode=MULTIMODAL_DECODE_BASELINE,
            multi_image_scatter_mode="none",
            quantized_load_mode=quantized_load_mode,
            quantized_load_fallback_reason=quantized_load_fallback_reason,
            hybrid_state_patch_mode=hybrid_state_patch_mode,
            hybrid_state_media_count=hybrid_state_media_count,
            family_fast_path_override_count=family_fast_path_override_count,
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


def fast_path_probe_signature(
    loaded_model: Any,
    prepared_request: PreparedVisionRequest,
) -> tuple[str, ...]:
    top_level_repr = "()"
    metadata_repr = "()"
    if isinstance(loaded_model, dict):
        top_level_repr = _top_level_signature_repr(loaded_model)
        metadata_keys = _signature_metadata_keys(loaded_model, prepared_request)
        nested_metadata = loaded_model.get("metadata", {})
        nested_metadata_is_dict = isinstance(nested_metadata, dict)
        if metadata_keys == _FAST_PATH_SIGNATURE_CORE_METADATA_KEYS_SORTED:
            metadata_repr = _core_signature_metadata_repr(
                loaded_model,
                nested_metadata,
                nested_metadata_is_dict,
            )
        else:
            metadata_values = tuple(
                _signature_metadata_value(
                    loaded_model,
                    nested_metadata,
                    nested_metadata_is_dict,
                    key,
                )
                for key in metadata_keys
            )
            metadata_repr = _signature_key_values_repr(metadata_keys, metadata_values)
    return (
        prepared_request.multimodal_hash_hex,
        top_level_repr,
        metadata_repr,
    )


def _top_level_signature_repr(loaded_model: dict[str, Any]) -> str:
    return _top_level_signature_repr_values(
        str(loaded_model.get("model_id", "")),
        str(loaded_model.get("quant_profile_id", "")),
        str(loaded_model.get("revision", "")),
        str(loaded_model.get("tokenizer_hash", "")),
    )


@lru_cache(maxsize=1024)
def _top_level_signature_repr_values(
    model_id: str,
    quant_profile_id: str,
    revision: str,
    tokenizer_hash: str,
) -> str:
    return (
        "(('model_id', "
        + repr(model_id)
        + "), ('quant_profile_id', "
        + repr(quant_profile_id)
        + "), ('revision', "
        + repr(revision)
        + "), ('tokenizer_hash', "
        + repr(tokenizer_hash)
        + "))"
    )


def _core_signature_metadata_repr(
    loaded_model: dict[str, Any],
    nested_metadata: Any,
    nested_metadata_is_dict: bool,
) -> str:
    return _core_signature_metadata_repr_values(
        _signature_metadata_value(
            loaded_model,
            nested_metadata,
            nested_metadata_is_dict,
            _FAST_PATH_SIGNATURE_CORE_METADATA_KEYS_SORTED[0],
        ),
        _signature_metadata_value(
            loaded_model,
            nested_metadata,
            nested_metadata_is_dict,
            _FAST_PATH_SIGNATURE_CORE_METADATA_KEYS_SORTED[1],
        ),
        _signature_metadata_value(
            loaded_model,
            nested_metadata,
            nested_metadata_is_dict,
            _FAST_PATH_SIGNATURE_CORE_METADATA_KEYS_SORTED[2],
        ),
        _signature_metadata_value(
            loaded_model,
            nested_metadata,
            nested_metadata_is_dict,
            _FAST_PATH_SIGNATURE_CORE_METADATA_KEYS_SORTED[3],
        ),
        _signature_metadata_value(
            loaded_model,
            nested_metadata,
            nested_metadata_is_dict,
            _FAST_PATH_SIGNATURE_CORE_METADATA_KEYS_SORTED[4],
        ),
        _signature_metadata_value(
            loaded_model,
            nested_metadata,
            nested_metadata_is_dict,
            _FAST_PATH_SIGNATURE_CORE_METADATA_KEYS_SORTED[5],
        ),
        _signature_metadata_value(
            loaded_model,
            nested_metadata,
            nested_metadata_is_dict,
            _FAST_PATH_SIGNATURE_CORE_METADATA_KEYS_SORTED[6],
        ),
    )


@lru_cache(maxsize=2048)
def _core_signature_metadata_repr_values(
    melix_adapter_hash: str,
    execution_mode: str,
    adapter_hash: str,
    family_id: str,
    max_images_per_prompt: str,
    prompt_profile_id: str,
    tokenization_mode: str,
) -> str:
    return _signature_key_values_repr(
        _FAST_PATH_SIGNATURE_CORE_METADATA_KEYS_SORTED,
        (
            melix_adapter_hash,
            execution_mode,
            adapter_hash,
            family_id,
            max_images_per_prompt,
            prompt_profile_id,
            tokenization_mode,
        ),
    )


def _signature_metadata_value(
    loaded_model: dict[str, Any],
    nested_metadata: Any,
    nested_metadata_is_dict: bool,
    key: str,
) -> str:
    normalized = ""
    value = loaded_model.get(key)
    if isinstance(value, str) and value.strip():
        normalized = value.strip()
    if nested_metadata_is_dict and key in nested_metadata:
        # Nested runtime metadata is authoritative over import-time top-level copies.
        # The accepted key set is fixed, so probe those keys directly instead of
        # scanning and sorting arbitrary metadata payloads on every signature call.
        nested_normalized = str(nested_metadata[key]).strip()
        if nested_normalized:
            normalized = nested_normalized
    return normalized


def _signature_metadata_keys(
    loaded_model: dict[str, Any],
    prepared_request: PreparedVisionRequest,
) -> tuple[str, ...]:
    if not prepared_request.images and not prepared_request.videos:
        return _FAST_PATH_SIGNATURE_CORE_METADATA_KEYS_SORTED
    if _has_any_loaded_metadata(loaded_model, _FAST_PATH_SIGNATURE_PROCESSOR_METADATA_KEYS):
        return _FAST_PATH_SIGNATURE_METADATA_KEYS_SORTED
    return _FAST_PATH_SIGNATURE_CORE_METADATA_KEYS_SORTED


@lru_cache(maxsize=2048)
def _signature_key_values_repr(keys: tuple[str, ...], values: tuple[str, ...]) -> str:
    chunks = [
        f"({key!r}, {value!r})"
        for key, value in zip(keys, values, strict=True)
        if value
    ]
    if not chunks:
        return "()"
    if len(chunks) == 1:
        return f"({chunks[0]},)"
    return "(" + ", ".join(chunks) + ")"


def _signature_pairs_repr(pairs: Any) -> str:
    chunks = [f"({key!r}, {value!r})" for key, value in pairs]
    if not chunks:
        return "()"
    if len(chunks) == 1:
        return f"({chunks[0]},)"
    return "(" + ", ".join(chunks) + ")"


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
        "vision_processor_policy",
        "vision_processor_crop_grid",
        "vision_processor_patch_size",
        "vision_processor_max_crop_count",
        "vision_prompt_format",
        "vision_projected_feature_shape",
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


def _loaded_metadata_value(loaded_model: Any, key: str) -> str:
    if not isinstance(loaded_model, dict):
        return ""
    metadata = loaded_model.get("metadata", {})
    if isinstance(metadata, dict) and key in metadata:
        value = metadata[key]
        if value is not None:
            normalized = str(value).strip()
            if normalized:
                return normalized
    value = loaded_model.get(key, "")
    if value:
        return str(value).strip()
    return ""


def _has_any_loaded_metadata(loaded_model: dict[str, Any], keys: frozenset[str]) -> bool:
    for source in (loaded_model, loaded_model.get("metadata", {})):
        if not isinstance(source, dict) or keys.isdisjoint(source):
            continue
        for key in keys:
            value = source.get(key, "")
            if value and str(value).strip():
                return True
    return False


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


def _payload_byte_length(payload: Any) -> int:
    nbytes = getattr(payload, "nbytes", None)
    try:
        byte_length = int(nbytes)
    except (TypeError, ValueError):
        byte_length = 0
    if byte_length > 0:
        return byte_length
    if isinstance(payload, str):
        return len(payload.encode("utf-8"))
    if isinstance(payload, (bytes, bytearray, memoryview)):
        return len(payload)
    if isinstance(payload, (list, tuple)):
        return sum(_payload_byte_length(item) for item in payload)
    if isinstance(payload, dict):
        return sum(_payload_byte_length(item) for item in payload.values())
    try:
        return max(0, int(len(payload)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


@lru_cache(maxsize=256)
def _preprocessing_fingerprint(
    mime_type: str,
    image_format: str,
    vision_prompt_profile_id: str,
    vision_tokenization_mode: str,
    vision_max_images_per_prompt: str,
    vision_processor_policy: str,
    vision_processor_crop_grid: str,
    vision_processor_patch_size: str,
    vision_processor_max_crop_count: str,
    vision_prompt_format: str,
    vision_projected_feature_shape: str,
) -> str:
    digest = hashlib.sha256()
    for value in (
        mime_type,
        image_format,
        vision_prompt_profile_id,
        vision_tokenization_mode,
        vision_max_images_per_prompt,
        vision_processor_policy,
        vision_processor_crop_grid,
        vision_processor_patch_size,
        vision_processor_max_crop_count,
        vision_prompt_format,
        vision_projected_feature_shape,
    ):
        digest.update(str(value or "").encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()
