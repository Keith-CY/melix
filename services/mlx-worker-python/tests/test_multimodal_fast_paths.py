from __future__ import annotations

import logging

from worker.runtime.multimodal_fast_paths import (
    ImageFeatureCacheKey,
    MULTIMODAL_DECODE_BASELINE,
    MULTIMODAL_DECODE_FALLBACK,
    MULTIMODAL_DECODE_IMAGE_CACHE_REUSE,
    MULTIMODAL_DECODE_SINGLE_STREAM,
    MULTIMODAL_LOAD_FALLBACK,
    MULTIMODAL_LOAD_NATIVE_QUANTIZED,
    MultimodalFastPathController,
    _preprocessing_fingerprint,
    _FAST_PATH_SIGNATURE_TOP_LEVEL_KEYS_SORTED,
    _signature_pairs_repr,
    fast_path_probe_signature,
)
from worker.runtime.multimodal_position_receipts import build_mixed_batch_geometry_receipt
from worker.runtime.multimodal_preprocessing import PreparedImageInput, PreparedVisionRequest
from worker.runtime.video_preprocessing import PreparedVideoInput


def _image(
    payload: bytes,
    *,
    filename: str = "sample.jpg",
    sha256_hex: str | None = None,
) -> PreparedImageInput:
    import hashlib

    return PreparedImageInput(
        bytes_data=payload,
        source_kind="inline",
        reference=f"inline:{filename}",
        mime_type="image/jpeg",
        format="jpg",
        filename=filename,
        sha256_hex=hashlib.sha256(payload).hexdigest() if sha256_hex is None else sha256_hex,
    )


def _video(payload: bytes = b"video") -> PreparedVideoInput:
    import hashlib

    return PreparedVideoInput(
        source_kind="inline",
        reference="inline:video.mp4",
        bytes_data=payload,
        mime_type="video/mp4",
        format="mp4",
        filename="video.mp4",
        byte_length=len(payload),
        duration_ms=1000,
        frame_budget=4,
        start_ms=0,
        end_ms=1000,
        sha256_hex=hashlib.sha256(payload).hexdigest(),
    )


def _request(
    images: list[PreparedImageInput] | None = None,
    *,
    videos: list[PreparedVideoInput] | None = None,
) -> PreparedVisionRequest:
    return PreparedVisionRequest(
        prompt_text="Describe the image.",
        images=list(images or []),
        videos=list(videos or []),
        video_frame_policies=[],
        preprocess_latency_ms=1.0,
        preprocess_input_bytes=sum(image.byte_length for image in images or [])
        + sum(video.byte_length for video in videos or []),
        preprocess_peak_memory_bytes=sum(image.byte_length for image in images or [])
        + sum(video.byte_length for video in videos or []),
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
    stored = controller.put_image_feature_payloads(
        loaded_model=loaded_model,
        prepared_request=request,
        payloads=(b"encoded-same-image",),
    )
    second = controller.plan(loaded_model, request)

    assert first.multimodal_decode_mode == MULTIMODAL_DECODE_SINGLE_STREAM
    assert first.image_feature_cache_hits == 0
    assert first.image_feature_cache_misses == 1
    assert first.image_feature_cache_artifact_count == 0
    assert stored == (True,)
    assert second.multimodal_decode_mode == MULTIMODAL_DECODE_IMAGE_CACHE_REUSE
    assert second.image_feature_cache_hits == 1
    assert second.image_feature_cache_misses == 0
    assert second.image_feature_cache_artifact_count == 1
    assert second.image_feature_cache_bytes == len(b"encoded-same-image")
    assert second.image_feature_encoder_calls_saved == 1
    assert second.image_feature_work_saved_bytes == len(b"same-image")
    assert second.multimodal_decode_sync_mode == "executor_stream"
    assert controller.image_feature_payloads(
        loaded_model=loaded_model,
        prepared_request=request,
    ) == (b"encoded-same-image",)


def test_fast_path_records_partial_reuse_for_multi_image_turns() -> None:
    controller = MultimodalFastPathController()
    loaded_model = _loaded_model()
    first_image = _image(b"first-image", filename="first.jpg")
    second_image = _image(b"second-image", filename="second.jpg")

    first_request = _request([first_image])
    controller.plan(loaded_model, first_request)
    controller.put_image_feature_payloads(
        loaded_model=loaded_model,
        prepared_request=first_request,
        payloads=(b"encoded-first-image",),
    )
    decision = controller.plan(loaded_model, _request([first_image, second_image]))

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_IMAGE_CACHE_REUSE
    assert decision.image_feature_cache_hits == 1
    assert decision.image_feature_cache_misses == 1
    assert decision.multi_image_scatter_mode == "per_sample"
    assert decision.image_feature_encoder_calls_saved == 1
    assert decision.image_feature_work_saved_bytes == len(b"first-image")


def test_fast_path_records_row_local_per_sample_scatter_for_heterogeneous_multi_image_rows() -> None:
    controller = MultimodalFastPathController()
    loaded_model = _loaded_model()
    row_images = [
        [_image(b"row-0-image", filename="row-0.jpg")],
        [
            _image(b"row-1-first-image", filename="row-1-first.jpg"),
            _image(b"row-1-second-image", filename="row-1-second.jpg"),
        ],
        [_image(b"row-2-image", filename="row-2.jpg")],
    ]

    decisions = [controller.plan(loaded_model, _request(images)) for images in row_images]
    receipt = build_mixed_batch_geometry_receipt(
        rows=[
            {
                "row_index": index,
                "prompt_kwargs": {
                    "input_ids_len": 8 + index,
                    "attention_mask_len": 8 + index + left_padding,
                },
                "seq_len": 8 + index,
                "left_padding": left_padding,
                "media_count": len(images),
                "mrope_delta_override": [image.sha256_hex for image in images],
                "mrope_delta_override_identity": [image.sha256_hex for image in images],
                "expected_mrope_delta_override_identity": [image.sha256_hex for image in images],
                "visual_embed_count": len(images) * 64,
                "expected_visual_embed_count": len(images) * 64,
                "visual_embed_identity": [image.sha256_hex for image in images],
                "expected_visual_embed_identity": [image.sha256_hex for image in images],
            }
            for index, (images, left_padding) in enumerate(zip(row_images, [4, 0, 7], strict=True))
        ]
    )

    assert [decision.multi_image_scatter_mode for decision in decisions] == [
        "single",
        "per_sample",
        "single",
    ]
    assert [decision.image_feature_cache_misses for decision in decisions] == [1, 2, 1]
    assert receipt["row_geometry_guard"] == "aligned"
    assert [row["visual_embed_count"] for row in receipt["rows"]] == [64, 128, 64]
    assert [row["visual_embed_identity"] for row in receipt["rows"]] == [
        [row_images[0][0].sha256_hex],
        [row_images[1][0].sha256_hex, row_images[1][1].sha256_hex],
        [row_images[2][0].sha256_hex],
    ]


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


def test_fast_path_does_not_warn_for_text_backed_models_without_family_metadata(caplog) -> None:
    controller = MultimodalFastPathController()
    loaded_model = _loaded_model(execution_mode="text_backed")
    metadata = loaded_model["metadata"]
    assert isinstance(metadata, dict)
    del metadata["vision_family_id"]

    caplog.set_level(logging.WARNING, logger="worker.runtime.multimodal_fast_paths")
    decision = controller.plan(loaded_model, _request([_image(b"image")]))

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_FALLBACK
    assert decision.multimodal_fallback_reason == "text_backed_no_vision_weights"
    assert "VLM fast-path metadata is incomplete" not in caplog.text


def test_fast_path_uses_baseline_for_text_only_turns() -> None:
    controller = MultimodalFastPathController()

    decision = controller.plan(_loaded_model(), _request([]))

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_BASELINE
    assert decision.multimodal_fallback_reason == "no_media"
    assert decision.multi_image_scatter_mode == "none"


def test_fast_path_text_only_plan_uses_lightweight_metadata_lookup() -> None:
    class FixedKeyMetadata(dict):
        def items(self):  # type: ignore[override]  # pragma: no cover
            raise AssertionError("text-only plan should not scan arbitrary metadata items")

    controller = MultimodalFastPathController()
    loaded_model = _loaded_model(quant_profile_id="q8")
    loaded_model["metadata"] = FixedKeyMetadata(
        {
            "melix.vlm.execution_mode": "multimodal",
            "vision_family_id": "gemma4-v1",
            "vision_prompt_profile_id": "gemma4-chatml-v1",
            **{"unrelated." + str(index): "ignored" for index in range(1000)},
        }
    )

    decision = controller.plan(loaded_model, _request([]))

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_BASELINE
    assert decision.multimodal_fallback_reason == "no_media"
    assert decision.quantized_load_mode == MULTIMODAL_LOAD_NATIVE_QUANTIZED


def test_fast_path_text_only_plan_handles_non_dict_loaded_models() -> None:
    controller = MultimodalFastPathController()

    decision = controller.plan(object(), _request([]))

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_BASELINE
    assert decision.multimodal_fallback_reason == "no_media"
    assert decision.quantized_load_mode == MULTIMODAL_LOAD_FALLBACK
    assert decision.quantized_load_fallback_reason == "not_quantized"


def test_fast_path_text_only_plan_falls_back_when_metadata_value_is_blank() -> None:
    controller = MultimodalFastPathController()
    loaded_model = _loaded_model(quant_profile_id="q8")
    metadata = loaded_model["metadata"]
    assert isinstance(metadata, dict)
    metadata["melix.vlm.execution_mode"] = "  "

    decision = controller.plan(loaded_model, _request([]))

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_BASELINE
    assert decision.multimodal_fallback_reason == "no_media"
    assert decision.quantized_load_mode == MULTIMODAL_LOAD_NATIVE_QUANTIZED


def test_fast_path_text_only_plan_falls_back_when_metadata_value_is_none() -> None:
    controller = MultimodalFastPathController()
    loaded_model = _loaded_model(quant_profile_id="q8")
    loaded_model["melix.vlm.execution_mode"] = "multimodal"
    metadata = loaded_model["metadata"]
    assert isinstance(metadata, dict)
    metadata["melix.vlm.execution_mode"] = None

    decision = controller.plan(loaded_model, _request([]))

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_BASELINE
    assert decision.multimodal_fallback_reason == "no_media"
    assert decision.quantized_load_mode == MULTIMODAL_LOAD_NATIVE_QUANTIZED


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


def test_fast_path_records_hybrid_state_patch_mode_for_supported_family() -> None:
    controller = MultimodalFastPathController()

    decision = controller.plan(
        _loaded_model(family_id="gemma4-v1"),
        _request([_image(b"image")]),
    )

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_SINGLE_STREAM
    assert decision.hybrid_state_patch_mode == "family_scoped"
    assert decision.hybrid_state_media_count == 1
    assert decision.family_fast_path_override_count == 0


def test_fast_path_records_not_applicable_hybrid_state_for_supported_family_without_patch() -> None:
    controller = MultimodalFastPathController()

    decision = controller.plan(
        _loaded_model(family_id="paligemma-v1"),
        _request([_image(b"image")]),
    )

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_SINGLE_STREAM
    assert decision.multimodal_fallback_reason == ""
    assert decision.image_feature_cache_hits == 0
    assert decision.image_feature_cache_misses == 1
    assert decision.hybrid_state_patch_mode == "not_applicable"
    assert decision.hybrid_state_media_count == 0
    assert decision.family_fast_path_override_count == 0


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


def test_fast_path_rejects_unknown_digit_quant_profile_names() -> None:
    controller = MultimodalFastPathController()

    decision = controller.plan(
        _loaded_model(quant_profile_id="q16"),
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

    first_request = _request([first_image])
    second_request = _request([second_image])
    controller.put_image_feature_payloads(
        loaded_model=loaded_model,
        prepared_request=first_request,
        payloads=(b"encoded-first",),
    )
    controller.put_image_feature_payloads(
        loaded_model=loaded_model,
        prepared_request=second_request,
        payloads=(b"encoded-second",),
    )
    decision = controller.plan(loaded_model, _request([first_image]))

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_SINGLE_STREAM
    assert decision.image_feature_cache_hits == 0
    assert decision.image_feature_cache_misses == 1


def test_fast_path_treats_images_without_sha_as_non_cacheable_misses() -> None:
    controller = MultimodalFastPathController()
    loaded_model = _loaded_model()

    first = controller.plan(loaded_model, _request([_image(b"first", sha256_hex="")]))
    second = controller.plan(loaded_model, _request([_image(b"second", sha256_hex="")]))

    assert first.image_feature_cache_hits == 0
    assert first.image_feature_cache_misses == 1
    assert second.image_feature_cache_hits == 0
    assert second.image_feature_cache_misses == 1


def test_fast_path_documents_within_request_payload_eviction_when_request_exceeds_cache_size() -> None:
    controller = MultimodalFastPathController(max_image_feature_cache_entries=1)
    loaded_model = _loaded_model()
    first_image = _image(b"first-image", filename="first.jpg")
    second_image = _image(b"second-image", filename="second.jpg")

    request = _request([first_image, second_image])
    stored = controller.put_image_feature_payloads(
        loaded_model=loaded_model,
        prepared_request=request,
        payloads=(b"encoded-first", b"encoded-second"),
    )
    decision = controller.plan(loaded_model, request)
    repeat_first = controller.plan(loaded_model, _request([first_image]))

    assert stored == (True, True)
    assert decision.image_feature_cache_hits == 1
    assert decision.image_feature_cache_misses == 1
    assert repeat_first.image_feature_cache_hits == 0
    assert repeat_first.image_feature_cache_misses == 1


def test_fast_path_avoids_repeating_preprocessing_fingerprint_lookups_for_same_request_shape() -> None:
    _preprocessing_fingerprint.cache_clear()
    controller = MultimodalFastPathController()
    loaded_model = _loaded_model()
    first_image = _image(b"first-image", filename="first.jpg")
    second_image = _image(b"second-image", filename="second.jpg")

    try:
        before = _preprocessing_fingerprint.cache_info()
        decision = controller.plan(loaded_model, _request([first_image, second_image]))
        after = _preprocessing_fingerprint.cache_info()

        assert decision.image_feature_cache_hits == 0
        assert decision.image_feature_cache_misses == 2
        assert after.misses - before.misses == 1
        assert after.hits - before.hits == 0
    finally:
        _preprocessing_fingerprint.cache_clear()


def test_fast_path_cache_misses_when_processor_shape_metadata_changes() -> None:
    controller = MultimodalFastPathController()
    first_model = _loaded_model()
    second_model = _loaded_model()
    first_metadata = first_model["metadata"]
    second_metadata = second_model["metadata"]
    assert isinstance(first_metadata, dict)
    assert isinstance(second_metadata, dict)
    first_metadata.update(
        {
            "vision_processor_policy": "gemma4-multicrop-v1",
            "vision_processor_crop_grid": "2x2",
            "vision_processor_patch_size": "14",
            "vision_processor_max_crop_count": "4",
            "vision_prompt_format": "interleaved-image-text",
            "vision_projected_feature_shape": "4x256x4096",
        }
    )
    second_metadata.update(
        {
            "vision_processor_policy": "gemma4-multicrop-v2",
            "vision_processor_crop_grid": "3x3",
            "vision_processor_patch_size": "14",
            "vision_processor_max_crop_count": "9",
            "vision_prompt_format": "interleaved-image-text",
            "vision_projected_feature_shape": "9x256x4096",
        }
    )
    image = _image(b"same-processor-sensitive-image")

    first = controller.plan(first_model, _request([image]))
    first_request = _request([image])
    controller.put_image_feature_payloads(
        loaded_model=first_model,
        prepared_request=first_request,
        payloads=(b"encoded-same-processor-sensitive-image",),
    )
    same_shape = controller.plan(first_model, first_request)
    changed_shape = controller.plan(second_model, _request([image]))

    assert first.image_feature_cache_hits == 0
    assert first.image_feature_cache_misses == 1
    assert same_shape.image_feature_cache_hits == 1
    assert same_shape.image_feature_cache_misses == 0
    assert changed_shape.image_feature_cache_hits == 0
    assert changed_shape.image_feature_cache_misses == 1


def test_fast_path_builds_request_scoped_cache_keys_with_one_fingerprint_per_media_shape(monkeypatch) -> None:
    controller = MultimodalFastPathController()
    loaded_model = _loaded_model()
    metadata = loaded_model["metadata"]
    assert isinstance(metadata, dict)
    first_image = _image(b"first-image", filename="first.jpg")
    second_image = _image(b"second-image", filename="second.jpg")
    fingerprint_calls: list[tuple[str, str, str, str, str, str, str, str, str, str, str]] = []

    def fake_fingerprint(
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
        fingerprint_calls.append(
            (
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
            )
        )
        return "fake-fingerprint"

    monkeypatch.setattr("worker.runtime.multimodal_fast_paths._preprocessing_fingerprint", fake_fingerprint)

    factory = controller._cache_key_factory(
        family_id="gemma4-v1",
        adapter_hash="adapter-a",
        quant_profile_id="none",
        metadata=metadata,
    )

    first_key = factory(first_image)
    second_key = factory(second_image)

    assert first_key == ImageFeatureCacheKey(
        family_id="gemma4-v1",
        adapter_hash="adapter-a",
        preprocessing_fingerprint="fake-fingerprint",
        quant_profile_id="none",
        sha256_hex=first_image.sha256_hex,
    )
    assert second_key == ImageFeatureCacheKey(
        family_id="gemma4-v1",
        adapter_hash="adapter-a",
        preprocessing_fingerprint="fake-fingerprint",
        quant_profile_id="none",
        sha256_hex=second_image.sha256_hex,
    )
    assert fingerprint_calls == [
        (
            "image/jpeg",
            "jpg",
            "gemma4-chatml-v1",
            "interleaved",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        )
    ]


def test_fast_path_cache_key_wrapper_preserves_existing_key_shape() -> None:
    loaded_model = _loaded_model()
    metadata = loaded_model["metadata"]
    assert isinstance(metadata, dict)
    image = _image(b"first-image", filename="first.jpg")

    key = MultimodalFastPathController._cache_key(
        image=image,
        family_id="gemma4-v1",
        adapter_hash="adapter-a",
        quant_profile_id="none",
        metadata=metadata,
    )

    assert key == ImageFeatureCacheKey(
        family_id="gemma4-v1",
        adapter_hash="adapter-a",
        preprocessing_fingerprint=_preprocessing_fingerprint(
            "image/jpeg",
            "jpg",
            "gemma4-chatml-v1",
            "interleaved",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ),
        quant_profile_id="none",
        sha256_hex=image.sha256_hex,
    )


def test_fast_path_falls_back_for_video_only_requests() -> None:
    controller = MultimodalFastPathController()

    decision = controller.plan(_loaded_model(), _request(videos=[_video()]))

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_FALLBACK
    assert decision.multimodal_fallback_reason == "video_fast_path_unimplemented"
    assert decision.image_feature_cache_hits == 0
    assert decision.image_feature_cache_misses == 0


def test_fast_path_falls_back_for_mixed_image_video_requests() -> None:
    controller = MultimodalFastPathController()
    image = _image(b"image")

    stored = controller.put_image_feature_payloads(
        loaded_model=_loaded_model(),
        prepared_request=_request([image]),
        payloads=(b"encoded-image",),
    )
    decision = controller.plan(_loaded_model(), _request([image], videos=[_video()]))

    assert stored == (True,)
    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_FALLBACK
    assert decision.multimodal_fallback_reason == "video_fast_path_unimplemented"
    assert decision.image_feature_cache_hits == 0
    assert decision.image_feature_cache_misses == 0


def test_fast_path_controller_image_feature_payload_cache_requires_store_before_hit() -> None:
    controller = MultimodalFastPathController()
    loaded_model = _loaded_model()
    request = _request([_image(b"cacheable-image")])

    first = controller.plan(loaded_model, request)
    second = controller.plan(loaded_model, request)
    payloads_before_store = controller.image_feature_payloads(
        loaded_model=loaded_model,
        prepared_request=request,
    )

    stored = controller.put_image_feature_payloads(
        loaded_model=loaded_model,
        prepared_request=request,
        payloads=("encoded-cacheable-image",),
    )
    payloads_after_store = controller.image_feature_payloads(
        loaded_model=loaded_model,
        prepared_request=request,
    )
    third = controller.plan(loaded_model, request)

    assert first.image_feature_cache_misses == 1
    assert second.image_feature_cache_hits == 0
    assert second.image_feature_cache_misses == 1
    assert payloads_before_store == (None,)
    assert stored == (True,)
    assert payloads_after_store == ("encoded-cacheable-image",)
    assert third.multimodal_decode_mode == MULTIMODAL_DECODE_IMAGE_CACHE_REUSE
    assert third.image_feature_cache_hits == 1
    assert third.image_feature_cache_misses == 0


def test_fast_path_controller_image_feature_payload_cache_summarizes_bytes() -> None:
    controller = MultimodalFastPathController()
    loaded_model = _loaded_model()
    first = _image(b"first", filename="first.jpg")
    second = _image(b"second", filename="second.jpg")

    stored = controller.put_image_feature_payloads(
        loaded_model=loaded_model,
        prepared_request=_request([first, second]),
        payloads=(b"abc", "encoded-second"),
    )

    assert stored == (True, True)
    assert controller.image_feature_cache_summary() == (2, len(b"abc") + len("encoded-second"))
    keys = controller.image_feature_cache_keys()
    assert [key.sha256_hex for key in keys] == [first.sha256_hex, second.sha256_hex]


def test_fast_path_controller_skips_invalid_feature_payloads_and_uncacheable_images() -> None:
    controller = MultimodalFastPathController()
    loaded_model = _loaded_model()
    cacheable = _image(b"cacheable", filename="cacheable.jpg")
    no_sha = _image(b"no-sha", filename="no-sha.jpg", sha256_hex="")

    stored = controller.put_image_feature_payloads(
        loaded_model=loaded_model,
        prepared_request=_request([cacheable, no_sha]),
        payloads=(None, b"encoded-no-sha"),
    )

    assert stored == (False, False)
    assert controller.image_feature_cache_summary() == (0, 0)


def test_fast_path_controller_payload_api_handles_empty_and_unsupported_requests() -> None:
    controller = MultimodalFastPathController()
    loaded_model = _loaded_model(family_id="unsupported-vlm")
    image = _image(b"unsupported")

    assert controller.image_feature_payloads(
        loaded_model=loaded_model,
        prepared_request=_request([]),
    ) == ()
    assert controller.put_image_feature_payloads(
        loaded_model=loaded_model,
        prepared_request=_request([]),
        payloads=(),
    ) == ()
    assert controller.image_feature_payloads(
        loaded_model=loaded_model,
        prepared_request=_request([image]),
    ) == (None,)
    assert controller.put_image_feature_payloads(
        loaded_model=loaded_model,
        prepared_request=_request([image]),
        payloads=(b"encoded",),
    ) == (False,)


def test_fast_path_controller_payload_api_handles_partial_payload_lists() -> None:
    controller = MultimodalFastPathController()
    loaded_model = _loaded_model()
    first = _image(b"first", filename="first.jpg")
    second = _image(b"second", filename="second.jpg")

    stored = controller.put_image_feature_payloads(
        loaded_model=loaded_model,
        prepared_request=_request([first, second]),
        payloads=(b"encoded-first",),
    )

    assert stored == (True, False)
    assert controller.image_feature_payloads(
        loaded_model=loaded_model,
        prepared_request=_request([first, second]),
    ) == (b"encoded-first", None)


def test_fast_path_controller_payload_byte_length_falls_back_to_len_or_zero() -> None:
    class BytePayload:
        nbytes = 11

    class LenOnlyPayload:
        def __len__(self) -> int:
            return 7

    class BadLenPayload:
        def __len__(self) -> int:
            raise TypeError("len unavailable")

    controller = MultimodalFastPathController()
    loaded_model = _loaded_model()
    first = _image(b"first", filename="first.jpg")
    second = _image(b"second", filename="second.jpg")

    stored = controller.put_image_feature_payloads(
        loaded_model=loaded_model,
        prepared_request=_request([first, second]),
        payloads=(
            [BytePayload(), b"abc"],
            {"len_only": LenOnlyPayload(), "bad_len": BadLenPayload()},
        ),
    )

    assert stored == (True, True)
    assert controller.image_feature_cache_summary() == (2, 21)


def test_fast_path_probe_signature_uses_nested_metadata_precedence() -> None:
    loaded_model = _loaded_model(top_level_family_id="stale-family")
    signature = fast_path_probe_signature(loaded_model, _request([_image(b"image")]))

    assert signature[0] == "multi"
    assert "stale-family" not in signature[2]
    assert "gemma4-v1" in signature[2]
    assert "melix-dev-vlm" in signature[1]


def test_fast_path_probe_signature_ignores_non_dict_loaded_models() -> None:
    signature = fast_path_probe_signature(object(), _request([_image(b"image")]))

    assert signature == ("multi", "()", "()")


def test_fast_path_probe_signature_reuses_pre_sorted_top_level_keys() -> None:
    loaded_model = {
        "quant_profile_id": "q8",
        "tokenizer_hash": "tok",
        "revision": "main",
        "model_id": "melix-dev-vlm",
        "metadata": {
            "vision_family_id": "gemma4-v1",
        },
    }

    signature = fast_path_probe_signature(loaded_model, _request([_image(b"image")]))

    expected_top_level_items = tuple(
        (key, str(loaded_model.get(key, "")))
        for key in _FAST_PATH_SIGNATURE_TOP_LEVEL_KEYS_SORTED
    )
    assert signature[1] == repr(expected_top_level_items)
    assert signature[1] == (
        "(('model_id', 'melix-dev-vlm'), ('quant_profile_id', 'q8'), "
        "('revision', 'main'), ('tokenizer_hash', 'tok'))"
    )


def test_fast_path_probe_signature_only_expands_processor_keys_when_present() -> None:
    loaded_model = _loaded_model()

    text_signature = fast_path_probe_signature(loaded_model, _request([]))
    assert "vision_processor_policy" not in text_signature[2]
    assert "vision_projected_feature_shape" not in text_signature[2]

    legacy_signature = fast_path_probe_signature(loaded_model, _request([_image(b"image")]))
    assert "vision_processor_policy" not in legacy_signature[2]
    assert "vision_projected_feature_shape" not in legacy_signature[2]

    metadata = loaded_model["metadata"]
    assert isinstance(metadata, dict)
    metadata["vision_processor_policy"] = "gemma4-multicrop-v1"
    metadata["vision_projected_feature_shape"] = "4x256x4096"

    processor_signature = fast_path_probe_signature(loaded_model, _request([_image(b"image")]))
    assert "('vision_processor_policy', 'gemma4-multicrop-v1')" in processor_signature[2]
    assert "('vision_projected_feature_shape', '4x256x4096')" in processor_signature[2]


def test_fast_path_probe_signature_serializes_pairs_like_tuple_repr() -> None:
    pairs = [("vision_family_id", "gemma4-v1"), ("quoted", "value'with\\nnewline")]

    assert _signature_pairs_repr([]) == repr(())
    assert _signature_pairs_repr(pairs[:1]) == repr(tuple(pairs[:1]))
    assert _signature_pairs_repr(pairs) == repr(tuple(pairs))


def test_fast_path_probe_signature_probes_fixed_metadata_keys_without_scanning_nested_items() -> None:
    class FixedKeyMetadata(dict):
        def items(self):  # type: ignore[override]
            raise AssertionError("signature should not scan arbitrary nested metadata items")

    loaded_model = _loaded_model(top_level_family_id="stale-family")
    loaded_model["metadata"] = FixedKeyMetadata(
        {"unrelated." + str(index): "ignored" for index in range(1000)}
    )
    loaded_model["metadata"].update(  # type: ignore[union-attr]
        {
            "vision_family_id": "gemma4-v1",
            "vision_prompt_profile_id": "gemma4-chatml-v1",
            "melix.vlm.execution_mode": "multimodal",
            "vision_tokenization_mode": "interleaved",
            "vision_max_images_per_prompt": 8,
            "melix.multimodal_adapter_hash": "adapter-a",
        }
    )

    signature = fast_path_probe_signature(loaded_model, _request([_image(b"image")]))
    try:
        loaded_model["metadata"].items()  # type: ignore[union-attr]
    except AssertionError as exc:
        assert "should not scan" in str(exc)
    else:  # pragma: no cover - defensive guard for the test helper itself.
        raise AssertionError("test metadata helper did not guard items() scans")

    assert "stale-family" not in signature[2]
    assert "gemma4-v1" in signature[2]
    assert "unrelated." not in signature[2]
    assert "('vision_max_images_per_prompt', '8')" in signature[2]
