from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from worker.engine import maintenance_core as maintenance_core_module
from worker.engine.maintenance_core import MaintenanceCore
from worker.runtime.deterministic_vlm_runtime import DeterministicVLMRuntime
from worker.runtime.deterministic_vlm_runtime import probe_receipt_fallback_reason
from worker.runtime.mlx_vlm_runtime import MLXVLMRuntime
from worker.runtime.multimodal_fast_paths import (
    ImageFeatureCacheEntry,
    ImageFeatureCacheKey,
    MEDIA_FEATURE_REUSE_UNSUPPORTED_AUDIO,
    MEDIA_FEATURE_REUSE_UNSUPPORTED_VIDEO,
    MULTIMODAL_DECODE_BASELINE,
    MULTIMODAL_DECODE_FALLBACK,
    MULTIMODAL_DECODE_IMAGE_CACHE_REUSE,
    MULTIMODAL_DECODE_IMAGE_BATCH1_STEP_ADMISSION,
    MULTIMODAL_DECODE_SINGLE_STREAM,
    MULTIMODAL_LOAD_FALLBACK,
    MULTIMODAL_LOAD_NATIVE_QUANTIZED,
    MultimodalFastPathController,
    _preprocessing_fingerprint,
    _video_preprocessing_fingerprint,
    _FAST_PATH_SIGNATURE_TOP_LEVEL_KEYS_SORTED,
    _FAST_PATH_SIGNATURE_PROCESSOR_METADATA_KEYS,
    _has_any_loaded_metadata,
    _signature_pairs_repr,
    fast_path_probe_signature,
    media_feature_reuse_unsupported_reason,
)
from worker.runtime.multimodal_position_receipts import build_mixed_batch_geometry_receipt
from worker.runtime.multimodal_position_receipts import build_position_metadata_receipt
from worker.runtime.multimodal_preprocessing import (
    PreparedImageInput,
    PreparedVideoFramePolicy,
    PreparedVisionRequest,
)
from worker.runtime.quantized_load_acceptance import quantized_load_acceptance_receipt
from worker.runtime.quantized_tensor_metadata import (
    EMPTY_QUANTIZED_TENSOR_METADATA,
    QuantizedTensorMetadata,
    cross_shard_quantized_metadata_fixup_count,
)
from worker.runtime.video_preprocessing import PreparedVideoInput
from worker.runtime.vlm_preprocessing_policy import request_preprocessing_policy_signature


def _image(
    payload: bytes,
    *,
    filename: str = "sample.jpg",
    sha256_hex: str | None = None,
    preprocessing_policy: dict[str, object] | None = None,
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
        preprocessing_policy=dict(preprocessing_policy) if preprocessing_policy else None,
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
    video_frame_policies: list[PreparedVideoFramePolicy] | None = None,
) -> PreparedVisionRequest:
    videos = list(videos or [])
    if video_frame_policies is None:
        video_frame_policies = [
            PreparedVideoFramePolicy(
                reference=video.reference,
                sampling_strategy="uniform_sample",
                requested_frame_budget=video.frame_budget,
                effective_frame_count=video.frame_budget or 8,
                clip_start_ms=video.start_ms,
                clip_end_ms=video.end_ms,
                clip_duration_ms=max(0, video.end_ms - video.start_ms) if video.end_ms else 0,
            )
            for video in videos
        ]
    return PreparedVisionRequest(
        prompt_text="Describe the image.",
        images=list(images or []),
        videos=videos,
        video_frame_policies=list(video_frame_policies),
        preprocess_latency_ms=1.0,
        preprocess_input_bytes=sum(image.byte_length for image in images or [])
        + sum(video.byte_length for video in videos),
        preprocess_peak_memory_bytes=sum(image.byte_length for image in images or [])
        + sum(video.byte_length for video in videos),
        prompt_hash_hex="prompt",
        multimodal_hash_hex="multi",
        preprocessing_policy_signature=request_preprocessing_policy_signature(images or []),
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


def test_processor_metadata_absent_uses_disjoint_fast_path() -> None:
    class CountingDict(dict[str, object]):
        processor_key_gets = 0

        def get(self, key: str, default: object = None) -> object:
            if key in _FAST_PATH_SIGNATURE_PROCESSOR_METADATA_KEYS:
                self.processor_key_gets += 1
            return super().get(key, default)

    metadata = CountingDict(
        {
            "melix.vlm.execution_mode": "multimodal",
            "vision_family_id": "gemma4-v1",
        }
    )
    loaded_model = CountingDict(
        {
            "model_id": "melix-dev-vlm",
            "metadata": metadata,
        }
    )

    assert _has_any_loaded_metadata(loaded_model, _FAST_PATH_SIGNATURE_PROCESSOR_METADATA_KEYS) is False
    assert loaded_model.processor_key_gets == 0
    assert metadata.processor_key_gets == 0


def test_fast_path_records_cache_miss_then_hit_for_repeated_image() -> None:
    extractor_calls: list[str] = []

    def extractor(key: ImageFeatureCacheKey, image: PreparedImageInput) -> ImageFeatureCacheEntry:
        extractor_calls.append(image.sha256_hex)
        return ImageFeatureCacheEntry(
            cache_key=key,
            artifact_id=f"feature:{image.sha256_hex}",
            payload=None,
            feature_byte_length=image.byte_length * 4,
            source_image_bytes=image.byte_length,
            encoder_call_count=1,
        )

    controller = MultimodalFastPathController(image_feature_extractor=extractor)
    loaded_model = _loaded_model()
    image = _image(b"same-image")
    request = _request([image])

    first = controller.plan(loaded_model, request)
    second = controller.plan(loaded_model, request)
    stored = controller.put_image_feature_payloads(loaded_model, request, ("feature-payload",))
    third = controller.plan(loaded_model, request)

    assert extractor_calls == [image.sha256_hex]
    assert stored == (True,)
    assert first.multimodal_decode_mode == MULTIMODAL_DECODE_SINGLE_STREAM
    assert first.image_feature_cache_hits == 0
    assert first.image_feature_cache_misses == 1
    assert first.image_feature_cache_artifact_count == 0
    assert first.image_feature_cache_bytes == 0
    assert first.image_feature_encoder_calls_saved == 0
    assert first.image_feature_work_saved_bytes == 0
    assert first.image_feature_cache_fallback_reason == ""
    assert second.multimodal_decode_mode == MULTIMODAL_DECODE_SINGLE_STREAM
    assert second.image_feature_cache_hits == 0
    assert second.image_feature_cache_misses == 1
    assert second.image_feature_cache_artifact_count == 0
    assert third.multimodal_decode_mode == MULTIMODAL_DECODE_IMAGE_CACHE_REUSE
    assert third.image_feature_cache_hits == 1
    assert third.image_feature_cache_misses == 0
    assert third.image_feature_cache_artifact_count == 1
    assert third.image_feature_cache_bytes == image.byte_length * 4
    assert third.image_feature_encoder_calls_saved == 1
    assert third.image_feature_work_saved_bytes == image.byte_length
    assert third.image_feature_cache_fallback_reason == ""
    assert third.multimodal_decode_sync_mode == "executor_stream"


def test_fast_path_records_partial_reuse_for_multi_image_turns() -> None:
    extractor_calls: list[str] = []

    def extractor(key: ImageFeatureCacheKey, image: PreparedImageInput) -> ImageFeatureCacheEntry:
        extractor_calls.append(image.sha256_hex)
        return ImageFeatureCacheEntry(
            cache_key=key,
            artifact_id=f"feature:{image.sha256_hex}",
            payload=None,
            feature_byte_length=image.byte_length * 2,
            source_image_bytes=image.byte_length,
            encoder_call_count=1,
        )

    controller = MultimodalFastPathController(image_feature_extractor=extractor)
    loaded_model = _loaded_model()
    first_image = _image(b"first-image", filename="first.jpg")
    second_image = _image(b"second-image", filename="second.jpg")

    assert controller.plan(loaded_model, _request([first_image])).image_feature_cache_misses == 1
    controller.put_image_feature_payloads(loaded_model, _request([first_image]), ("first-payload",))
    decision = controller.plan(loaded_model, _request([first_image, second_image]))

    assert extractor_calls == [first_image.sha256_hex]
    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_IMAGE_CACHE_REUSE
    assert decision.image_feature_cache_hits == 1
    assert decision.image_feature_cache_misses == 1
    assert decision.image_feature_cache_artifact_count == 1
    assert decision.image_feature_cache_bytes == first_image.byte_length * 2
    assert decision.image_feature_encoder_calls_saved == 1
    assert decision.image_feature_work_saved_bytes == first_image.byte_length
    assert decision.multi_image_scatter_mode == "per_sample"


def test_fast_path_returns_stable_image_feature_payloads_after_store() -> None:
    controller = MultimodalFastPathController()
    loaded_model = _loaded_model()
    image = _image(b"same-image")
    request = _request([image])

    assert controller.image_feature_payloads(loaded_model, request) == (None,)
    assert controller.put_image_feature_payloads(loaded_model, request, ("projected-features",)) == (
        True,
    )

    assert controller.image_feature_payloads(loaded_model, request) == ("projected-features",)
    repeat = controller.plan(loaded_model, request)
    assert repeat.image_feature_cache_hits == 1
    assert repeat.image_feature_cache_misses == 0
    assert repeat.image_feature_cache_artifact_count == 1


def test_fast_path_rejects_mismatched_image_feature_payload_count() -> None:
    controller = MultimodalFastPathController()
    loaded_model = _loaded_model()
    images = [
        _image(b"first-image", filename="first.jpg"),
        _image(b"second-image", filename="second.jpg"),
    ]
    request = _request(images)

    assert controller.put_image_feature_payloads(loaded_model, request, ("only-first",)) == (
        False,
        False,
    )
    assert controller.put_image_feature_payloads(
        loaded_model,
        request,
        ("first", "second", "extra"),
    ) == (
        False,
        False,
    )

    assert controller.image_feature_payloads(loaded_model, request) == (None, None)
    decision = controller.plan(loaded_model, request)
    assert decision.image_feature_cache_hits == 0
    assert decision.image_feature_cache_misses == 2
    assert decision.image_feature_cache_artifact_count == 0


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
        "none",
        "per_sample",
        "none",
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
    extractor_calls = 0

    def extractor(key: ImageFeatureCacheKey, image: PreparedImageInput) -> ImageFeatureCacheEntry:
        nonlocal extractor_calls
        pytest.fail("text-backed routes must not extract image features")  # pragma: no cover

    controller = MultimodalFastPathController(image_feature_extractor=extractor)

    decision = controller.plan(
        _loaded_model(execution_mode="text_backed"),
        _request([_image(b"image")]),
    )

    assert extractor_calls == 0
    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_FALLBACK
    assert decision.multimodal_fallback_reason == "text_backed_no_vision_weights"
    assert decision.image_feature_cache_hits == 0
    assert decision.image_feature_cache_misses == 0
    assert decision.image_feature_cache_artifact_count == 0
    assert decision.image_feature_cache_fallback_reason == "text_backed_no_vision_weights"


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


def test_quantized_load_acceptance_receipt_counts_native_and_bridge_fallbacks() -> None:
    native = quantized_load_acceptance_receipt(
        quantized_load_mode="native_quantized",
        quantized_load_fallback_reason="",
        quant_profile_id="q8",
        cross_shard_metadata_fixup_count=2,
    )
    unsupported = quantized_load_acceptance_receipt(
        quantized_load_mode="fallback",
        quantized_load_fallback_reason="unsupported_family",
        quant_profile_id="q8",
    )
    unquantized = quantized_load_acceptance_receipt(
        quantized_load_mode="fallback",
        quantized_load_fallback_reason="not_quantized",
        quant_profile_id="none",
    )
    unquantized_unsupported_family = quantized_load_acceptance_receipt(
        quantized_load_mode="fallback",
        quantized_load_fallback_reason="unsupported_family",
        quant_profile_id="none",
    )
    unquantized_bfloat16 = quantized_load_acceptance_receipt(
        quantized_load_mode="fallback",
        quantized_load_fallback_reason="unsupported_family",
        quant_profile_id="bf16",
    )

    assert native.native_quantized_load_count == 1
    assert native.bridge_quantized_fallback_count == 0
    assert native.cross_shard_metadata_fixup_count == 2
    assert unsupported.native_quantized_load_count == 0
    assert unsupported.bridge_quantized_fallback_count == 1
    assert unsupported.cross_shard_metadata_fixup_count == 0
    assert unquantized.native_quantized_load_count == 0
    assert unquantized.bridge_quantized_fallback_count == 0
    assert unquantized_unsupported_family.native_quantized_load_count == 0
    assert unquantized_unsupported_family.bridge_quantized_fallback_count == 0
    assert unquantized_bfloat16.native_quantized_load_count == 0
    assert unquantized_bfloat16.bridge_quantized_fallback_count == 0


def test_cross_shard_quantized_metadata_fixup_count_counts_weight_scale_pairs() -> None:
    metadata = QuantizedTensorMetadata(
        {
            "language_model.layers.0.q_proj.weight": "model-00001.safetensors",
            "language_model.layers.0.q_proj.scales": "model-00002.safetensors",
            "language_model.layers.1.q_proj.weight": "model-00003.safetensors",
            "language_model.layers.1.q_proj.scales": "model-00003.safetensors",
            "language_model.layers.2.q_proj.scales": "model-00004.safetensors",
        }
    )

    assert cross_shard_quantized_metadata_fixup_count(metadata) == 1
    assert cross_shard_quantized_metadata_fixup_count(EMPTY_QUANTIZED_TENSOR_METADATA) == 0


def test_fast_path_fails_closed_without_extracting_features_for_unsupported_family() -> None:
    extractor_calls = 0

    def extractor(key: ImageFeatureCacheKey, image: PreparedImageInput) -> ImageFeatureCacheEntry:
        nonlocal extractor_calls
        pytest.fail("unsupported families must not extract image features")  # pragma: no cover

    controller = MultimodalFastPathController(image_feature_extractor=extractor)

    decision = controller.plan(
        _loaded_model(family_id="unknown-vlm"),
        _request([_image(b"image")]),
    )

    assert extractor_calls == 0
    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_FALLBACK
    assert decision.multimodal_fallback_reason == "unsupported_family"
    assert decision.image_feature_cache_fallback_reason == "unsupported_family"
    assert decision.image_feature_cache_artifact_count == 0
    assert decision.image_feature_cache_bytes == 0
    assert decision.image_feature_encoder_calls_saved == 0


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


def test_fast_path_admits_image_batch1_step_when_receipts_and_sampling_are_eligible() -> None:
    controller = MultimodalFastPathController()
    prepared_request = _request([_image(b"image")])
    decision = controller.plan(
        _loaded_model(family_id="gemma4-v1"),
        prepared_request,
        image_batch1_step_position_receipt=build_position_metadata_receipt(
            prepared_request=prepared_request,
            seq_len=8,
            position_ids=SimpleNamespace(shape=(1, 8)),
            rope_deltas=SimpleNamespace(shape=(1, 3)),
        ),
        image_batch1_step_supported=True,
        image_batch1_step_greedy_sampling=True,
    )

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_IMAGE_BATCH1_STEP_ADMISSION
    assert decision.multimodal_fallback_reason == ""
    assert decision.multimodal_decode_sync_mode == "executor_step_admission"
    assert decision.image_batch1_step_admission_reason == ""


def test_fast_path_probe_receipt_fallback_reason_strips_decode_admission_reasons() -> None:
    assert probe_receipt_fallback_reason("image_batch1_step_non_greedy_sampling") == ""
    assert probe_receipt_fallback_reason("cache_missing") == "cache_missing"


def test_fast_path_bench_metrics_encode_image_batch1_step_admission_receipts() -> None:
    metrics = MaintenanceCore._vlm_fast_path_bench_metrics(
        suite_id="smoke",
        samples=[
            maintenance_core_module.BenchSample(
                ttft_ms=10.0,
                total_latency_ms=20.0,
                completion_tokens=2,
                multimodal_decode_mode="image_batch1_step_admission",
                multimodal_decode_sync_mode="executor_step_admission",
                multimodal_fallback_reason="image_batch1_step_non_greedy_sampling",
            ),
        ],
    )

    metrics_by_name = {metric.name: metric for metric in metrics}
    assert metrics_by_name["bench.smoke.multimodal_decode_mode"].value == 8.0
    assert metrics_by_name["bench.smoke.multimodal_decode_sync_mode"].value == 5.0
    assert metrics_by_name["bench.smoke.multimodal_fallback_reason"].value == 10.0


def test_deterministic_vlm_runtime_records_image_batch1_step_admission_receipt() -> None:
    runtime = DeterministicVLMRuntime()
    prepared_request = _request([_image(b"deterministic-image-batch1")])

    runtime._record_fast_path_probe(
        _loaded_model(family_id="gemma4-v1"),
        prepared_request,
        seq_len=8,
        position_ids=SimpleNamespace(shape=(1, 8)),
        rope_deltas=SimpleNamespace(shape=(1, 1)),
        image_batch1_step_supported=True,
        image_batch1_step_greedy_sampling=True,
    )

    probe = runtime.last_probe_snapshot()
    assert probe.multimodal_decode_mode == MULTIMODAL_DECODE_IMAGE_BATCH1_STEP_ADMISSION
    assert probe.multimodal_decode_sync_mode == "executor_step_admission"
    assert probe.multimodal_fallback_reason == ""
    assert probe.image_batch1_step_admission_reason == ""
    assert probe.position_metadata_receipt["vision_metadata_guard"] == "aligned"
    assert probe.position_metadata_receipt["vision_metadata_reuse_allowed"] is True


def test_deterministic_vlm_runtime_preserves_non_admission_fallback_in_position_receipt() -> None:
    runtime = DeterministicVLMRuntime()
    prepared_request = _request([_image(b"deterministic-unsupported-family")])

    runtime._record_fast_path_probe(
        _loaded_model(family_id="unsupported-vlm"),
        prepared_request,
        seq_len=8,
        position_ids=SimpleNamespace(shape=(1, 8)),
        rope_deltas=SimpleNamespace(shape=(1, 1)),
        image_batch1_step_supported=True,
        image_batch1_step_greedy_sampling=True,
    )

    probe = runtime.last_probe_snapshot()
    assert probe.multimodal_decode_mode == MULTIMODAL_DECODE_FALLBACK
    assert probe.multimodal_fallback_reason == "unsupported_family"
    assert probe.position_metadata_receipt["fallback_reason"] == "unsupported_family"
    assert probe.hybrid_state_patch_receipt["fallback_reason"] == "unsupported_family"


def test_mlx_vlm_runtime_preserves_non_admission_fallback_in_position_receipt() -> None:
    runtime = MLXVLMRuntime()
    prepared_request = _request([_image(b"mlx-unsupported-family")])

    runtime._record_fast_path_probe(
        _loaded_model(family_id="unsupported-vlm"),
        prepared_request,
        seq_len=8,
        family_config=SimpleNamespace(family_id="unsupported-vlm"),
        position_ids=SimpleNamespace(shape=(1, 8)),
        rope_deltas=SimpleNamespace(shape=(1, 1)),
        image_batch1_step_supported=True,
        image_batch1_step_greedy_sampling=True,
    )

    probe = runtime.last_probe_snapshot()
    assert probe.multimodal_decode_mode == MULTIMODAL_DECODE_FALLBACK
    assert probe.multimodal_fallback_reason == "unsupported_family"
    assert probe.position_metadata_receipt["fallback_reason"] == "unsupported_family"
    assert probe.hybrid_state_patch_receipt["fallback_reason"] == "unsupported_family"


def test_fast_path_keeps_image_batch1_non_greedy_requests_on_baseline_with_reason() -> None:
    controller = MultimodalFastPathController()
    prepared_request = _request([_image(b"image")])
    decision = controller.plan(
        _loaded_model(family_id="gemma4-v1"),
        prepared_request,
        image_batch1_step_position_receipt=build_position_metadata_receipt(
            prepared_request=prepared_request,
            seq_len=8,
            position_ids=SimpleNamespace(shape=(1, 8)),
            rope_deltas=SimpleNamespace(shape=(1, 3)),
        ),
        image_batch1_step_supported=True,
        image_batch1_step_greedy_sampling=False,
    )

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_SINGLE_STREAM
    assert decision.multimodal_fallback_reason == "image_batch1_step_non_greedy_sampling"
    assert decision.multimodal_decode_sync_mode == "executor_stream"
    assert decision.image_batch1_step_admission_reason == "image_batch1_step_non_greedy_sampling"


def test_fast_path_keeps_image_batch1_missing_cache_receipt_on_baseline_with_reason() -> None:
    controller = MultimodalFastPathController()
    prepared_request = _request([_image(b"image", sha256_hex="")])
    decision = controller.plan(
        _loaded_model(family_id="gemma4-v1"),
        prepared_request,
        image_batch1_step_position_receipt=build_position_metadata_receipt(
            prepared_request=prepared_request,
            seq_len=8,
            position_ids=SimpleNamespace(shape=(1, 8)),
            rope_deltas=SimpleNamespace(shape=(1, 3)),
        ),
        image_batch1_step_supported=True,
        image_batch1_step_greedy_sampling=True,
    )

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_SINGLE_STREAM
    assert decision.multimodal_fallback_reason == "image_batch1_step_cache_receipt_missing"
    assert decision.image_batch1_step_admission_reason == "image_batch1_step_cache_receipt_missing"


def test_fast_path_keeps_image_batch1_missing_position_receipt_on_baseline_with_reason() -> None:
    controller = MultimodalFastPathController()
    prepared_request = _request([_image(b"image")])
    decision = controller.plan(
        _loaded_model(family_id="gemma4-v1"),
        prepared_request,
        image_batch1_step_supported=True,
        image_batch1_step_greedy_sampling=True,
    )

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_SINGLE_STREAM
    assert decision.multimodal_fallback_reason == "image_batch1_step_position_receipt_missing"
    assert decision.image_batch1_step_admission_reason == "image_batch1_step_position_receipt_missing"


def test_fast_path_keeps_non_batch1_media_routes_on_baseline_with_reason() -> None:
    controller = MultimodalFastPathController()
    prepared_request = _request([_image(b"first"), _image(b"second")])
    decision = controller.plan(
        _loaded_model(family_id="gemma4-v1"),
        prepared_request,
        image_batch1_step_position_receipt=build_position_metadata_receipt(
            prepared_request=prepared_request,
            seq_len=8,
            position_ids=SimpleNamespace(shape=(1, 8)),
            rope_deltas=SimpleNamespace(shape=(1, 3)),
        ),
        image_batch1_step_supported=True,
        image_batch1_step_greedy_sampling=True,
    )

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_SINGLE_STREAM
    assert decision.multimodal_fallback_reason == "image_batch1_step_media_route_ineligible"
    assert decision.image_batch1_step_admission_reason == "image_batch1_step_media_route_ineligible"


def test_fast_path_keeps_image_batch1_unsupported_backend_on_baseline_with_reason() -> None:
    controller = MultimodalFastPathController()
    prepared_request = _request([_image(b"image")])
    decision = controller.plan(
        _loaded_model(family_id="gemma4-v1"),
        prepared_request,
        image_batch1_step_position_receipt=build_position_metadata_receipt(
            prepared_request=prepared_request,
            seq_len=8,
            position_ids=SimpleNamespace(shape=(1, 8)),
            rope_deltas=SimpleNamespace(shape=(1, 3)),
        ),
        image_batch1_step_supported=False,
        image_batch1_step_greedy_sampling=True,
    )

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_SINGLE_STREAM
    assert decision.multimodal_fallback_reason == "image_batch1_step_backend_unsupported"
    assert decision.image_batch1_step_admission_reason == "image_batch1_step_backend_unsupported"


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

    controller.put_image_feature_payloads(loaded_model, _request([first_image]), ("first",))
    controller.put_image_feature_payloads(loaded_model, _request([second_image]), ("second",))
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

    stored = controller.put_image_feature_payloads(
        loaded_model,
        _request([first_image, second_image]),
        ("first", "second"),
    )
    decision = controller.plan(loaded_model, _request([first_image, second_image]))
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
    controller.put_image_feature_payloads(first_model, _request([image]), ("shape-v1",))
    same_shape = controller.plan(first_model, _request([image]))
    changed_shape = controller.plan(second_model, _request([image]))

    assert first.image_feature_cache_hits == 0
    assert first.image_feature_cache_misses == 1
    assert same_shape.image_feature_cache_hits == 1
    assert same_shape.image_feature_cache_misses == 0
    assert changed_shape.image_feature_cache_hits == 0
    assert changed_shape.image_feature_cache_misses == 1


def test_fast_path_cache_misses_when_request_preprocessing_policy_changes() -> None:
    controller = MultimodalFastPathController()
    loaded_model = _loaded_model()
    base_image = _image(
        b"same-policy-sensitive-image",
        preprocessing_policy={
            "min_pixels": 1024,
            "max_pixels": 4096,
            "layout": "channels_last",
        },
    )
    resized_image = _image(
        b"same-policy-sensitive-image",
        preprocessing_policy={
            "min_pixels": 2048,
            "max_pixels": 8192,
            "layout": "channels_last",
        },
    )

    first = controller.plan(loaded_model, _request([base_image]))
    controller.put_image_feature_payloads(loaded_model, _request([base_image]), ("policy-a",))
    same_policy = controller.plan(loaded_model, _request([base_image]))
    changed_policy = controller.plan(loaded_model, _request([resized_image]))

    assert first.image_feature_cache_hits == 0
    assert first.image_feature_cache_misses == 1
    assert same_policy.image_feature_cache_hits == 1
    assert same_policy.image_feature_cache_misses == 0
    assert changed_policy.image_feature_cache_hits == 0
    assert changed_policy.image_feature_cache_misses == 1


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
    assert decision.image_feature_cache_fallback_reason == MEDIA_FEATURE_REUSE_UNSUPPORTED_VIDEO
    assert decision.image_feature_cache_hits == 0
    assert decision.image_feature_cache_misses == 0


def test_fast_path_builds_modality_safe_video_feature_cache_identity() -> None:
    controller = MultimodalFastPathController()
    loaded_model = _loaded_model()
    metadata = loaded_model["metadata"]
    assert isinstance(metadata, dict)
    metadata.update(
        {
            "vision_max_videos_per_prompt": "1",
            "vision_processor_policy": "gemma4-video-uniform-v1",
            "vision_video_frame_token_cost": "4",
        }
    )
    video = _video(b"same-video")
    first_policy = PreparedVideoFramePolicy(
        reference=video.reference,
        sampling_strategy="uniform_sample",
        requested_frame_budget=4,
        effective_frame_count=4,
        clip_start_ms=0,
        clip_end_ms=1000,
        clip_duration_ms=1000,
    )
    changed_policy = PreparedVideoFramePolicy(
        reference=video.reference,
        sampling_strategy="uniform_sample",
        requested_frame_budget=8,
        effective_frame_count=8,
        clip_start_ms=0,
        clip_end_ms=1000,
        clip_duration_ms=1000,
    )

    same_keys = controller.video_feature_cache_keys(
        loaded_model,
        _request(videos=[video], video_frame_policies=[first_policy]),
    )
    repeat_keys = controller.video_feature_cache_keys(
        loaded_model,
        _request(videos=[video], video_frame_policies=[first_policy]),
    )
    changed_keys = controller.video_feature_cache_keys(
        loaded_model,
        _request(videos=[video], video_frame_policies=[changed_policy]),
    )

    assert same_keys == repeat_keys
    assert same_keys[0] is not None
    assert changed_keys[0] is not None
    assert same_keys[0].family_id == "gemma4-v1"
    assert same_keys[0].adapter_hash == "adapter-a"
    assert same_keys[0].quant_profile_id == "none"
    assert same_keys[0].sha256_hex == video.sha256_hex
    assert same_keys[0].preprocessing_fingerprint == _video_preprocessing_fingerprint(
        "video/mp4",
        "mp4",
        "gemma4-chatml-v1",
        "interleaved",
        "1",
        "gemma4-video-uniform-v1",
        "4",
        "uniform_sample",
        "4",
        "4",
        "0",
        "1000",
        "1000",
    )
    assert changed_keys[0].sha256_hex == same_keys[0].sha256_hex
    assert changed_keys[0].preprocessing_fingerprint != same_keys[0].preprocessing_fingerprint


def test_fast_path_video_feature_cache_keys_are_fail_closed_for_unkeyable_inputs() -> None:
    controller = MultimodalFastPathController()
    loaded_model = _loaded_model()
    video = _video(b"video-without-policy")
    unhashable_video = _video(b"video-without-sha")
    unhashable_video = PreparedVideoInput(
        source_kind=unhashable_video.source_kind,
        reference=unhashable_video.reference,
        bytes_data=unhashable_video.bytes_data,
        mime_type=unhashable_video.mime_type,
        format=unhashable_video.format,
        filename=unhashable_video.filename,
        byte_length=unhashable_video.byte_length,
        duration_ms=unhashable_video.duration_ms,
        frame_budget=unhashable_video.frame_budget,
        start_ms=unhashable_video.start_ms,
        end_ms=unhashable_video.end_ms,
        sha256_hex="",
    )

    assert controller.video_feature_cache_keys(loaded_model, _request()) == ()
    assert controller.video_feature_cache_keys(
        _loaded_model(family_id="unsupported-v1"),
        _request(videos=[video]),
    ) == (None,)
    assert controller.video_feature_cache_keys(
        loaded_model,
        _request(videos=[unhashable_video]),
    ) == (None,)
    assert controller.video_feature_cache_keys(
        loaded_model,
        _request(videos=[video], video_frame_policies=[]),
    ) == (None,)


def test_fast_path_refuses_video_feature_reuse_without_polluting_image_cache() -> None:
    controller = MultimodalFastPathController()
    loaded_model = _loaded_model()
    video = _video(b"repeat-video")
    request = _request(videos=[video])

    first = controller.plan(loaded_model, request)
    second = controller.plan(loaded_model, request)
    stored = controller.put_image_feature_payloads(loaded_model, request, ())

    assert first.multimodal_fallback_reason == "video_fast_path_unimplemented"
    assert second.multimodal_fallback_reason == "video_fast_path_unimplemented"
    assert first.image_feature_cache_fallback_reason == MEDIA_FEATURE_REUSE_UNSUPPORTED_VIDEO
    assert second.image_feature_cache_fallback_reason == MEDIA_FEATURE_REUSE_UNSUPPORTED_VIDEO
    assert first.image_feature_cache_hits == 0
    assert first.image_feature_cache_misses == 0
    assert second.image_feature_cache_hits == 0
    assert second.image_feature_cache_misses == 0
    assert first.image_feature_work_saved_bytes == 0
    assert second.image_feature_work_saved_bytes == 0
    assert stored == ()
    assert controller.image_feature_cache_summary() == (0, 0)


def test_fast_path_uses_stable_audio_video_feature_reuse_refusal_reasons() -> None:
    assert media_feature_reuse_unsupported_reason("audio") == MEDIA_FEATURE_REUSE_UNSUPPORTED_AUDIO
    assert media_feature_reuse_unsupported_reason("input_audio") == MEDIA_FEATURE_REUSE_UNSUPPORTED_AUDIO
    assert media_feature_reuse_unsupported_reason("video") == MEDIA_FEATURE_REUSE_UNSUPPORTED_VIDEO
    assert media_feature_reuse_unsupported_reason("input_video") == MEDIA_FEATURE_REUSE_UNSUPPORTED_VIDEO
    assert media_feature_reuse_unsupported_reason("application/pdf") == "media_feature_reuse_unsupported"


def test_fast_path_falls_back_for_mixed_image_video_requests_without_caching_image_payloads() -> None:
    controller = MultimodalFastPathController()
    image = _image(b"image")

    decision = controller.plan(_loaded_model(), _request([image], videos=[_video()]))
    stored = controller.put_image_feature_payloads(
        _loaded_model(),
        _request([image], videos=[_video()]),
        ("feature",),
    )

    assert decision.multimodal_decode_mode == MULTIMODAL_DECODE_FALLBACK
    assert decision.multimodal_fallback_reason == "video_fast_path_unimplemented"
    assert decision.image_feature_cache_fallback_reason == MEDIA_FEATURE_REUSE_UNSUPPORTED_VIDEO
    assert decision.image_feature_cache_hits == 0
    assert decision.image_feature_cache_misses == 0
    assert stored == (False,)


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

    loaded_model_with_top_level_processor = _loaded_model()
    loaded_model_with_top_level_processor["vision_processor_policy"] = "top-level-policy"
    top_level_signature = fast_path_probe_signature(
        loaded_model_with_top_level_processor,
        _request([_image(b"image")]),
    )
    assert "('vision_processor_policy', 'top-level-policy')" in top_level_signature[2]

    loaded_model_with_non_dict_metadata = _loaded_model()
    loaded_model_with_non_dict_metadata["metadata"] = "not-a-dict"
    loaded_model_with_non_dict_metadata["vision_processor_policy"] = "top-level-only-policy"
    non_dict_signature = fast_path_probe_signature(
        loaded_model_with_non_dict_metadata,
        _request([_image(b"image")]),
    )
    assert "('vision_processor_policy', 'top-level-only-policy')" in non_dict_signature[2]


def test_loaded_metadata_presence_helper_preserves_generic_key_sets() -> None:
    assert _has_any_loaded_metadata({"metadata": {"custom_key": " value "}}, frozenset({"custom_key"}))


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
