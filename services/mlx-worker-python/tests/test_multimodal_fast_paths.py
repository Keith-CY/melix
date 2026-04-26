from __future__ import annotations

import logging

from worker.runtime.multimodal_fast_paths import (
    MULTIMODAL_DECODE_BASELINE,
    MULTIMODAL_DECODE_FALLBACK,
    MULTIMODAL_DECODE_IMAGE_CACHE_REUSE,
    MULTIMODAL_DECODE_SINGLE_STREAM,
    MULTIMODAL_LOAD_FALLBACK,
    MULTIMODAL_LOAD_NATIVE_QUANTIZED,
    MultimodalFastPathController,
)
from worker.runtime.multimodal_preprocessing import PreparedImageInput, PreparedVisionRequest


def _image(payload: bytes, *, filename: str = "sample.jpg") -> PreparedImageInput:
    import hashlib

    return PreparedImageInput(
        bytes_data=payload,
        source_kind="inline",
        reference=f"inline:{filename}",
        mime_type="image/jpeg",
        format="jpg",
        filename=filename,
        sha256_hex=hashlib.sha256(payload).hexdigest(),
    )


def _request(images: list[PreparedImageInput] | None = None) -> PreparedVisionRequest:
    return PreparedVisionRequest(
        prompt_text="Describe the image.",
        images=list(images or []),
        videos=[],
        video_frame_policies=[],
        preprocess_latency_ms=1.0,
        preprocess_input_bytes=sum(image.byte_length for image in images or []),
        preprocess_peak_memory_bytes=sum(image.byte_length for image in images or []),
        prompt_hash_hex="prompt",
        multimodal_hash_hex="multi",
    )


def _loaded_model(
    *,
    family_id: str = "gemma4-v1",
    execution_mode: str = "multimodal",
    quant_profile_id: str = "none",
    top_level_family_id: str | None = None,
) -> dict[str, object]:
    loaded_model: dict[str, object] = {
        "model_id": "melix-dev-vlm",
        "revision": "main",
        "tokenizer_hash": "tok",
        "quant_profile_id": quant_profile_id,
        "metadata": {
            "melix.vlm.execution_mode": execution_mode,
            "vision_family_id": family_id,
            "vision_prompt_profile_id": "gemma4-chatml-v1",
            "vision_tokenization_mode": "interleaved",
            "melix.multimodal_adapter_hash": "adapter-a",
        },
    }
    if top_level_family_id is not None:
        loaded_model["vision_family_id"] = top_level_family_id
    return loaded_model


def test_fast_path_records_cache_miss_then_hit_for_repeated_image() -> None:
    controller = MultimodalFastPathController()
    loaded_model = _loaded_model()
    request = _request([_image(b"same-image")])

    first = controller.plan(loaded_model, request)
    second = controller.plan(loaded_model, request)

    assert first.multimodal_decode_mode == MULTIMODAL_DECODE_SINGLE_STREAM
    assert first.image_feature_cache_hits == 0
    assert first.image_feature_cache_misses == 1
    assert second.multimodal_decode_mode == MULTIMODAL_DECODE_IMAGE_CACHE_REUSE
    assert second.image_feature_cache_hits == 1
    assert second.image_feature_cache_misses == 0
    assert second.multimodal_decode_sync_mode == "executor_stream"


def test_fast_path_records_partial_reuse_for_multi_image_turns() -> None:
    controller = MultimodalFastPathController()
    loaded_model = _loaded_model()
    first_image = _image(b"first-image", filename="first.jpg")
    second_image = _image(b"second-image", filename="second.jpg")

    controller.plan(loaded_model, _request([first_image]))
    decision = controller.plan(loaded_model, _request([first_image, second_image]))

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_IMAGE_CACHE_REUSE
    assert decision.image_feature_cache_hits == 1
    assert decision.image_feature_cache_misses == 1
    assert decision.multi_image_scatter_mode == "per_sample"


def test_fast_path_falls_back_for_text_backed_image_models() -> None:
    controller = MultimodalFastPathController()

    decision = controller.plan(
        _loaded_model(execution_mode="text_backed"),
        _request([_image(b"image")]),
    )

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_FALLBACK
    assert decision.multimodal_fallback_reason == "text_backed_no_vision_weights"
    assert decision.image_feature_cache_hits == 0
    assert decision.image_feature_cache_misses == 0


def test_fast_path_uses_baseline_for_text_only_turns() -> None:
    controller = MultimodalFastPathController()

    decision = controller.plan(_loaded_model(), _request([]))

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_BASELINE
    assert decision.multimodal_fallback_reason == "no_media"
    assert decision.multi_image_scatter_mode == "none"


def test_fast_path_admits_native_quantized_supported_multimodal_family() -> None:
    controller = MultimodalFastPathController()

    supported = controller.plan(
        _loaded_model(family_id="gemma4-v1", quant_profile_id="q8"),
        _request([_image(b"image")]),
    )
    unsupported = controller.plan(
        _loaded_model(family_id="unknown-vlm", quant_profile_id="q8"),
        _request([_image(b"image")]),
    )

    assert supported.quantized_load_mode == MULTIMODAL_LOAD_NATIVE_QUANTIZED
    assert supported.quantized_load_fallback_reason == ""
    assert unsupported.multimodal_decode_mode == MULTIMODAL_DECODE_FALLBACK
    assert unsupported.multimodal_fallback_reason == "unsupported_family"
    assert unsupported.quantized_load_mode == MULTIMODAL_LOAD_FALLBACK
    assert unsupported.quantized_load_fallback_reason == "unsupported_family"


def test_fast_path_warns_and_falls_back_when_family_metadata_is_missing(caplog) -> None:
    controller = MultimodalFastPathController()
    loaded_model = _loaded_model()
    metadata = loaded_model["metadata"]
    assert isinstance(metadata, dict)
    del metadata["vision_family_id"]

    caplog.set_level(logging.WARNING, logger="worker.runtime.multimodal_fast_paths")
    decision = controller.plan(loaded_model, _request([_image(b"image")]))

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_FALLBACK
    assert decision.multimodal_fallback_reason == "unsupported_family"
    assert "VLM fast-path metadata is incomplete" in caplog.text


def test_fast_path_uses_metadata_family_precedence_over_top_level_copy() -> None:
    controller = MultimodalFastPathController()

    decision = controller.plan(
        _loaded_model(family_id="gemma4-v1", top_level_family_id="unknown-vlm"),
        _request([_image(b"image")]),
    )

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_SINGLE_STREAM
    assert decision.multimodal_fallback_reason == ""


def test_fast_path_rejects_non_quantized_q_prefixed_profile_names() -> None:
    controller = MultimodalFastPathController()

    decision = controller.plan(
        _loaded_model(quant_profile_id="quality_high"),
        _request([_image(b"image")]),
    )

    assert decision.quantized_load_mode == MULTIMODAL_LOAD_FALLBACK
    assert decision.quantized_load_fallback_reason == "unsupported_quant_profile"
    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_SINGLE_STREAM


def test_fast_path_evicts_oldest_image_feature_key_when_cache_is_full() -> None:
    controller = MultimodalFastPathController(max_image_feature_cache_entries=1)
    loaded_model = _loaded_model()
    first_image = _image(b"first-image", filename="first.jpg")
    second_image = _image(b"second-image", filename="second.jpg")

    controller.plan(loaded_model, _request([first_image]))
    controller.plan(loaded_model, _request([second_image]))
    decision = controller.plan(loaded_model, _request([first_image]))

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_SINGLE_STREAM
    assert decision.image_feature_cache_hits == 0
    assert decision.image_feature_cache_misses == 1
