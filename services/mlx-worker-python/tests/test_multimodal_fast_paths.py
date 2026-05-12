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

    controller.plan(loaded_model, _request([first_image]))
    controller.plan(loaded_model, _request([second_image]))
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


def test_fast_path_documents_within_request_eviction_when_request_exceeds_cache_size() -> None:
    controller = MultimodalFastPathController(max_image_feature_cache_entries=1)
    loaded_model = _loaded_model()
    first_image = _image(b"first-image", filename="first.jpg")
    second_image = _image(b"second-image", filename="second.jpg")

    decision = controller.plan(loaded_model, _request([first_image, second_image]))
    repeat_first = controller.plan(loaded_model, _request([first_image]))

    assert decision.image_feature_cache_hits == 0
    assert decision.image_feature_cache_misses == 2
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


def test_fast_path_builds_request_scoped_cache_keys_with_one_fingerprint_per_media_shape(monkeypatch) -> None:
    controller = MultimodalFastPathController()
    loaded_model = _loaded_model()
    metadata = loaded_model["metadata"]
    assert isinstance(metadata, dict)
    first_image = _image(b"first-image", filename="first.jpg")
    second_image = _image(b"second-image", filename="second.jpg")
    fingerprint_calls: list[tuple[str, str, str, str, str]] = []

    def fake_fingerprint(
        mime_type: str,
        image_format: str,
        vision_prompt_profile_id: str,
        vision_tokenization_mode: str,
        vision_max_images_per_prompt: str,
    ) -> str:
        fingerprint_calls.append(
            (
                mime_type,
                image_format,
                vision_prompt_profile_id,
                vision_tokenization_mode,
                vision_max_images_per_prompt,
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
