from __future__ import annotations

from threading import Event
from types import SimpleNamespace

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_registry.catalog import WorkerModelCatalog
from worker.runtime.deterministic_vlm_runtime import DeterministicVLMRuntime
from worker.runtime.mlx_vlm_runtime import AutoMLXVLMBackend, MLXVLMRuntime
from worker.runtime.multimodal_position_receipts import build_position_metadata_receipt
from worker.runtime.multimodal_preprocessing import (
    PreparedImageInput,
    PreparedVideoFramePolicy,
    PreparedVisionRequest,
)
from worker.runtime.video_preprocessing import PreparedVideoInput
from worker.runtime.vision_family_adapters import resolve_vision_family_config


def _imported_gemma4_vlm_model() -> common_pb2.ModelSpec:
    return common_pb2.ModelSpec(
        model_id="unsloth/gemma-4-E4B-it-MLX-8bit",
        model_path="unsloth/gemma-4-E4B-it-MLX-8bit",
        model_kind="vlm",
        revision="main",
        tokenizer_hash="hf.unsloth.gemma-4-E4B-it-MLX-8bit",
        quant_profile_id="q8",
        parser_mode="text",
        reasoning_mode="off",
        max_context=4096,
        ext={
            "melix.vlm.backend_id": "mlx_vlm",
            "vision_family_id": "gemma4-v1",
            "vision_prompt_profile_id": "gemma4-chatml-v1",
            "vision_tokenization_mode": "interleaved",
            "vision_max_images_per_prompt": "8",
            "vision_supports_tool_calls": "true",
            "melix.multimodal_adapter_hash": "vision-family-gemma4-v1",
        },
    )


def test_position_metadata_receipt_counts_tensor_shapes_and_media_positions() -> None:
    request = PreparedVisionRequest(
        prompt_text="Describe both.",
        images=[
            PreparedImageInput(
                bytes_data=b"image",
                source_kind="inline",
                reference="inline:image",
                mime_type="image/jpeg",
                format="jpg",
                filename="image.jpg",
                sha256_hex="abc123",
            )
        ],
        videos=[
            PreparedVideoInput(
                bytes_data=b"video",
                source_kind="inline",
                reference="inline:video",
                mime_type="video/mp4",
                format="mp4",
                filename="video.mp4",
                byte_length=5,
                sha256_hex="def456",
                duration_ms=2_000,
                frame_budget=0,
                start_ms=0,
                end_ms=2_000,
            )
        ],
        video_frame_policies=[
            PreparedVideoFramePolicy(
                reference="inline:video",
                sampling_strategy="uniform_sample",
                requested_frame_budget=4,
                effective_frame_count=4,
                clip_start_ms=0,
                clip_end_ms=2_000,
                clip_duration_ms=2_000,
            )
        ],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=10,
        preprocess_peak_memory_bytes=10,
    )

    receipt = build_position_metadata_receipt(
        prepared_request=request,
        seq_len=64,
        cache_offset=16,
        position_ids=SimpleNamespace(shape=(1, 64)),
        rope_deltas=SimpleNamespace(shape=(1, 3)),
        fallback_reason="shape_mismatch",
    )

    assert receipt == {
        "position_ids_present": True,
        "position_ids_count": 64,
        "rope_deltas_present": True,
        "rope_deltas_count": 3,
        "media_position_count": 5,
        "cache_offset": 16,
        "seq_len": 64,
        "rebuild_count": 1,
        "mismatch_fallback_count": 1,
        "fallback_reason": "shape_mismatch",
        "vision_metadata_guard": "aligned",
        "vision_metadata_reuse_allowed": True,
        "stale_metadata_fallback_count": 0,
        "companion_rederive_skip_reason": "multimodal_companion_rederive_skipped_has_media",
    }


def test_position_metadata_receipt_defaults_to_shape_only_baseline() -> None:
    assert build_position_metadata_receipt(seq_len=7) == {
        "position_ids_present": False,
        "position_ids_count": 0,
        "rope_deltas_present": False,
        "rope_deltas_count": 0,
        "media_position_count": 0,
        "cache_offset": 0,
        "seq_len": 7,
        "rebuild_count": 0,
        "mismatch_fallback_count": 0,
        "fallback_reason": "",
        "vision_metadata_guard": "no_media",
        "vision_metadata_reuse_allowed": True,
        "stale_metadata_fallback_count": 0,
        "companion_rederive_skip_reason": "",
    }


def test_position_metadata_receipt_counts_flat_metadata_values() -> None:
    receipt = build_position_metadata_receipt(
        seq_len=4,
        position_ids=[0, 1, 2, 3],
        rope_deltas={"row0": 1, "row1": 2},
    )

    assert receipt["position_ids_count"] == 4
    assert receipt["rope_deltas_count"] == 2


def test_position_metadata_receipt_blocks_media_reuse_when_position_metadata_is_missing() -> None:
    request = PreparedVisionRequest(
        prompt_text="Describe the image.",
        images=[
            PreparedImageInput(
                bytes_data=b"image",
                source_kind="inline",
                reference="inline:image",
                mime_type="image/jpeg",
                format="jpg",
                filename="image.jpg",
                sha256_hex="abc123",
            )
        ],
        videos=[],
        video_frame_policies=[],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=5,
        preprocess_peak_memory_bytes=5,
    )

    receipt = build_position_metadata_receipt(
        prepared_request=request,
        seq_len=12,
        fallback_reason="",
    )

    assert receipt["vision_metadata_guard"] == "missing_position_metadata"
    assert receipt["vision_metadata_reuse_allowed"] is False
    assert receipt["stale_metadata_fallback_count"] == 1
    assert receipt["companion_rederive_skip_reason"] == (
        "multimodal_companion_rederive_skipped_has_media"
    )


def test_position_metadata_receipt_allows_media_reuse_when_position_metadata_is_aligned() -> None:
    request = PreparedVisionRequest(
        prompt_text="Describe the image.",
        images=[
            PreparedImageInput(
                bytes_data=b"image",
                source_kind="inline",
                reference="inline:image",
                mime_type="image/jpeg",
                format="jpg",
                filename="image.jpg",
                sha256_hex="abc123",
            )
        ],
        videos=[],
        video_frame_policies=[],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=5,
        preprocess_peak_memory_bytes=5,
    )

    receipt = build_position_metadata_receipt(
        prepared_request=request,
        seq_len=12,
        position_ids=SimpleNamespace(shape=(1, 12)),
        rope_deltas=SimpleNamespace(shape=(1, 3)),
    )

    assert receipt["vision_metadata_guard"] == "aligned"
    assert receipt["vision_metadata_reuse_allowed"] is True
    assert receipt["stale_metadata_fallback_count"] == 0
    assert receipt["companion_rederive_skip_reason"] == (
        "multimodal_companion_rederive_skipped_has_media"
    )


def test_position_metadata_receipt_blocks_stale_position_metadata_shapes() -> None:
    request = PreparedVisionRequest(
        prompt_text="Describe the image.",
        images=[
            PreparedImageInput(
                bytes_data=b"image",
                source_kind="inline",
                reference="inline:image",
                mime_type="image/jpeg",
                format="jpg",
                filename="image.jpg",
                sha256_hex="abc123",
            )
        ],
        videos=[],
        video_frame_policies=[],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=5,
        preprocess_peak_memory_bytes=5,
    )

    receipt = build_position_metadata_receipt(
        prepared_request=request,
        seq_len=12,
        position_ids=SimpleNamespace(shape=(1, 8)),
        rope_deltas=SimpleNamespace(shape=(1, 3)),
    )

    assert receipt["vision_metadata_guard"] == "stale_position_metadata"
    assert receipt["vision_metadata_reuse_allowed"] is False
    assert receipt["stale_metadata_fallback_count"] == 1


def test_position_metadata_receipt_allows_flat_media_metadata_without_shape() -> None:
    request = PreparedVisionRequest(
        prompt_text="Describe the image.",
        images=[
            PreparedImageInput(
                bytes_data=b"image",
                source_kind="inline",
                reference="inline:image",
                mime_type="image/jpeg",
                format="jpg",
                filename="image.jpg",
                sha256_hex="abc123",
            )
        ],
        videos=[],
        video_frame_policies=[],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=5,
        preprocess_peak_memory_bytes=5,
    )

    receipt = build_position_metadata_receipt(
        prepared_request=request,
        seq_len=4,
        position_ids=[0, 1, 2, 3],
        rope_deltas={"row0": 0},
    )

    assert receipt["vision_metadata_guard"] == "aligned"
    assert receipt["vision_metadata_reuse_allowed"] is True
    assert receipt["stale_metadata_fallback_count"] == 0


def test_position_metadata_receipt_allows_unknown_extent_when_seq_len_is_zero() -> None:
    request = PreparedVisionRequest(
        prompt_text="Describe the image.",
        images=[
            PreparedImageInput(
                bytes_data=b"image",
                source_kind="inline",
                reference="inline:image",
                mime_type="image/jpeg",
                format="jpg",
                filename="image.jpg",
                sha256_hex="abc123",
            )
        ],
        videos=[],
        video_frame_policies=[],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=5,
        preprocess_peak_memory_bytes=5,
    )

    receipt = build_position_metadata_receipt(
        prepared_request=request,
        seq_len=0,
        position_ids=object(),
        rope_deltas={"row0": 0},
    )

    assert receipt["vision_metadata_guard"] == "aligned"
    assert receipt["vision_metadata_reuse_allowed"] is True


def test_position_metadata_receipt_counts_video_without_expanded_frame_policy() -> None:
    request = PreparedVisionRequest(
        prompt_text="Describe video.",
        images=[],
        videos=[
            PreparedVideoInput(
                bytes_data=b"",
                source_kind="uri",
                reference="https://example.com/video.mp4",
                mime_type="video/mp4",
                format="mp4",
                filename="video.mp4",
                byte_length=0,
                duration_ms=0,
                frame_budget=0,
                start_ms=0,
                end_ms=0,
                sha256_hex="video-uri",
            )
        ],
        video_frame_policies=[],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=0,
        preprocess_peak_memory_bytes=0,
    )

    receipt = build_position_metadata_receipt(
        prepared_request=request,
        seq_len=4,
        position_ids=object(),
    )

    assert receipt["position_ids_count"] == 1
    assert receipt["media_position_count"] == 1
    assert receipt["vision_metadata_guard"] == "missing_rope_metadata"
    assert receipt["vision_metadata_reuse_allowed"] is False


def test_deterministic_vlm_runtime_records_position_metadata_receipt() -> None:
    runtime = DeterministicVLMRuntime()
    loaded_model = runtime.load_model(WorkerModelCatalog.dev_vlm_model())
    prepared = resolve_vision_family_config(loaded_model).shape_request(
        PreparedVisionRequest(
            prompt_text="Describe the image.",
            images=[
                PreparedImageInput(
                    bytes_data=b"deterministic receipt image",
                    source_kind="inline",
                    reference="inline:image",
                    mime_type="image/jpeg",
                    format="jpg",
                    filename="image.jpg",
                    sha256_hex="deadbeef",
                )
            ],
            videos=[],
            video_frame_policies=[],
            preprocess_latency_ms=0.0,
            preprocess_input_bytes=len(b"deterministic receipt image"),
            preprocess_peak_memory_bytes=len(b"deterministic receipt image"),
            prompt_hash_hex="1" * 64,
            multimodal_hash_hex="2" * 64,
        )
    )

    list(runtime.generate_tokens(loaded_model, prepared, None, Event()))
    receipt = runtime.last_probe_snapshot().position_metadata_receipt

    assert receipt["media_position_count"] == 1
    assert receipt["seq_len"] > 1
    assert receipt["rebuild_count"] == 1
    assert receipt["mismatch_fallback_count"] == 1
    assert receipt["vision_metadata_guard"] == "missing_position_metadata"
    assert receipt["vision_metadata_reuse_allowed"] is False
    assert receipt["stale_metadata_fallback_count"] == 1
    assert receipt["companion_rederive_skip_reason"] == (
        "multimodal_companion_rederive_skipped_has_media"
    )


def test_mlx_vlm_runtime_records_position_metadata_receipt_for_media_requests() -> None:
    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        model = SimpleNamespace(
            config=SimpleNamespace(model_type="gemma4"),
            vision_tower=object(),
            embed_vision=object(),
        )
        processor = SimpleNamespace(image_processor=object())
        return model, processor

    def fake_apply_chat_template(processor, config, prompt: str, num_images: int = 0, **kwargs):
        _ = processor
        _ = config
        _ = num_images
        _ = kwargs
        return f"formatted::{prompt}"

    def fake_stream_generate(model, processor, prompt: str, image=None, **kwargs):
        _ = model
        _ = processor
        _ = prompt
        _ = image
        _ = kwargs
        yield SimpleNamespace(text="ok", prompt_tokens=9, generation_tokens=1)

    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=fake_stream_generate,
            apply_chat_template_fn=fake_apply_chat_template,
        )
    )
    loaded_model = runtime.load_model(_imported_gemma4_vlm_model())
    prepared = runtime.render_prompt(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Describe the image."),
                    common_pb2.MessagePart(
                        image_bytes=b"receipt-image",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            filename="receipt.jpg",
                            format="jpg",
                        ),
                    ),
                ],
            )
        ],
        loaded_model=loaded_model,
    )

    list(
        runtime.generate_tokens(
            loaded_model,
            prepared,
            common_pb2.SamplingConfig(max_output_tokens=8),
            Event(),
        )
    )
    receipt = runtime.last_probe_snapshot().position_metadata_receipt

    assert receipt == {
        "position_ids_present": False,
        "position_ids_count": 0,
        "rope_deltas_present": False,
        "rope_deltas_count": 0,
        "media_position_count": 1,
        "cache_offset": 0,
        "seq_len": 5,
        "rebuild_count": 1,
        "mismatch_fallback_count": 1,
        "fallback_reason": "",
        "vision_metadata_guard": "missing_position_metadata",
        "vision_metadata_reuse_allowed": False,
        "stale_metadata_fallback_count": 1,
        "companion_rederive_skip_reason": "multimodal_companion_rederive_skipped_has_media",
    }


def test_mlx_vlm_runtime_position_receipt_records_fallback_reason_for_text_backed_media() -> None:
    runtime = MLXVLMRuntime()
    loaded_model = {
        "metadata": {
            "vision_family_id": "gemma4-v1",
            "melix.vlm.execution_mode": "text_backed",
        },
        "model": SimpleNamespace(config=SimpleNamespace(model_type="gemma4")),
    }
    prepared = PreparedVisionRequest(
        prompt_text="Describe.",
        images=[
            PreparedImageInput(
                bytes_data=b"image",
                source_kind="inline",
                reference="inline:image",
                mime_type="image/jpeg",
                format="jpg",
                filename="image.jpg",
                sha256_hex="deadbeef",
            )
        ],
        videos=[],
        video_frame_policies=[],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=len(b"image"),
        preprocess_peak_memory_bytes=len(b"image"),
        prompt_hash_hex="1" * 64,
        multimodal_hash_hex="2" * 64,
    )

    runtime._record_fast_path_probe(loaded_model, prepared)
    receipt = runtime.last_probe_snapshot().position_metadata_receipt

    assert receipt["media_position_count"] == 1
    assert receipt["seq_len"] == 3
    assert receipt["mismatch_fallback_count"] == 1
    assert receipt["fallback_reason"] == "text_backed_no_vision_weights"
    assert receipt["vision_metadata_guard"] == "missing_position_metadata"
    assert receipt["vision_metadata_reuse_allowed"] is False
    assert receipt["stale_metadata_fallback_count"] == 1


def test_mlx_vlm_runtime_position_receipt_records_baseline_for_prompt_only_turns() -> None:
    runtime = MLXVLMRuntime()
    loaded_model = {
        "metadata": {
            "vision_family_id": "gemma4-v1",
            "melix.vlm.execution_mode": "multimodal",
        },
        "model": SimpleNamespace(config=SimpleNamespace(model_type="gemma4")),
    }
    prepared = PreparedVisionRequest(
        prompt_text="Say hello.",
        images=[],
        videos=[],
        video_frame_policies=[],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=0,
        preprocess_peak_memory_bytes=0,
        prompt_hash_hex="1" * 64,
        multimodal_hash_hex="2" * 64,
    )

    runtime._record_fast_path_probe(loaded_model, prepared)
    receipt = runtime.last_probe_snapshot().position_metadata_receipt

    assert receipt == {
        "position_ids_present": False,
        "position_ids_count": 0,
        "rope_deltas_present": False,
        "rope_deltas_count": 0,
        "media_position_count": 0,
        "cache_offset": 0,
        "seq_len": 3,
        "rebuild_count": 0,
        "mismatch_fallback_count": 0,
        "fallback_reason": "no_media",
        "vision_metadata_guard": "no_media",
        "vision_metadata_reuse_allowed": True,
        "stale_metadata_fallback_count": 0,
        "companion_rederive_skip_reason": "",
    }
