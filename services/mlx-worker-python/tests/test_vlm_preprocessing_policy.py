from __future__ import annotations

import hashlib
from types import SimpleNamespace
from threading import Event

import pytest

from packages.protocol.python.worker.v1 import common_pb2

from worker.runtime.mlx_vlm_runtime import AutoMLXVLMBackend, MLXVLMRuntime
from worker.runtime.multimodal_preprocessing import (
    MultimodalPreprocessError,
    PreparedImageInput,
    PreparedVisionRequest,
    prepare_vision_request,
    rebuild_multimodal_hash,
)
from worker.runtime.vlm_preprocessing_policy import (
    image_preprocessing_resize_shape,
    prepared_request_preprocessing_policy_receipt,
    preprocessing_policy_receipt_value,
    request_preprocessing_policy_signature,
)


def _image_message(hints: dict[str, str]) -> list[common_pb2.ChatMessage]:
    return [
        common_pb2.ChatMessage(
            role="user",
            parts=[
                common_pb2.MessagePart(text="Describe the image."),
                common_pb2.MessagePart(
                    image_bytes=b"policy-image",
                    media=common_pb2.MediaMetadata(
                        media_type=common_pb2.MEDIA_TYPE_IMAGE,
                        source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                        filename="sample.jpg",
                        format="jpg",
                        preprocessing_hints=hints,
                    ),
                ),
            ],
        )
    ]


def _prepared_request(
    *policies: dict[str, object] | None,
    prompt_hash_hex: str = "p" * 64,
    multimodal_hash_hex: str = "m" * 64,
) -> PreparedVisionRequest:
    images = [
        PreparedImageInput(
            bytes_data=f"image-{index}".encode("utf-8"),
            source_kind="inline",
            reference=f"inline:image-{index}",
            mime_type="image/jpeg",
            format="jpg",
            filename=f"image-{index}.jpg",
            sha256_hex=hashlib.sha256(f"image-{index}".encode("utf-8")).hexdigest(),
            preprocessing_policy=dict(policy) if policy else None,
        )
        for index, policy in enumerate(policies)
    ]
    return PreparedVisionRequest(
        prompt_text="Describe.",
        images=images,
        videos=[],
        video_frame_policies=[],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=0,
        preprocess_peak_memory_bytes=0,
        prompt_hash_hex=prompt_hash_hex,
        multimodal_hash_hex=multimodal_hash_hex,
        preprocessing_policy_signature=request_preprocessing_policy_signature(images),
    )


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


def test_prepare_vision_request_normalizes_image_preprocessing_hints() -> None:
    request = prepare_vision_request(
        _image_message(
            {
                "max_pixels": "8192",
                "min_pixels": "1024",
                "resized_height": "768",
                "resized_width": "1024",
                "input_data_format": "channels-last",
            }
        )
    )

    assert request.images[0].preprocessing_policy == {
        "input_data_format": "channels_last",
        "max_pixels": 8192,
        "min_pixels": 1024,
        "resized_height": 768,
        "resized_width": 1024,
    }


def test_prepare_vision_request_hash_changes_when_preprocessing_policy_changes() -> None:
    base = prepare_vision_request(_image_message({"min_pixels": "1024"}))
    changed = prepare_vision_request(_image_message({"min_pixels": "2048"}))

    assert base.images[0].sha256_hex == changed.images[0].sha256_hex
    assert base.prompt_hash_hex == changed.prompt_hash_hex
    assert base.preprocessing_policy_signature
    assert base.preprocessing_policy_signature != changed.preprocessing_policy_signature
    assert base.multimodal_hash_hex != changed.multimodal_hash_hex
    assert rebuild_multimodal_hash(base, base.prompt_hash_hex) == base.multimodal_hash_hex


def test_prepare_vision_request_omits_empty_image_preprocessing_hints() -> None:
    request = prepare_vision_request(_image_message({"layout": "", "min_pixels": "1024"}))

    assert request.images[0].preprocessing_policy == {"min_pixels": 1024}


def test_prepare_vision_request_uses_none_for_missing_preprocessing_hints() -> None:
    request = prepare_vision_request(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Describe the image."),
                    common_pb2.MessagePart(
                        image_bytes=b"policy-image",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            filename="sample.jpg",
                            format="jpg",
                        ),
                    ),
                ],
            )
        ]
    )

    assert request.images[0].preprocessing_policy is None
    assert request.preprocessing_policy_signature == ""


def test_prepare_vision_request_rejects_unsupported_image_preprocessing_hints() -> None:
    with pytest.raises(
        MultimodalPreprocessError,
        match="unsupported_preprocessing_field: image_processor_type",
    ):
        prepare_vision_request(
            _image_message(
                {
                    "image_processor_type": "SurprisingProcessor",
                    "min_pixels": "1024",
                }
            )
        )


@pytest.mark.parametrize(
    ("hints", "field"),
    [
        ({"min_pixels": "not-an-int"}, "min_pixels"),
        ({"max_pixels": "0"}, "max_pixels"),
        ({"layout": "hwc"}, "layout"),
    ],
)
def test_prepare_vision_request_rejects_invalid_image_preprocessing_hints(
    hints: dict[str, str],
    field: str,
) -> None:
    with pytest.raises(
        MultimodalPreprocessError,
        match=f"invalid_preprocessing_value: {field}",
    ):
        prepare_vision_request(_image_message(hints))


def test_preprocessing_policy_receipt_records_normalized_image_policy() -> None:
    request = _prepared_request(
        {
            "input_data_format": "channels_last",
            "max_pixels": 4096,
            "min_pixels": 1024,
        }
    )

    assert preprocessing_policy_receipt_value(request.images) == {
        "image_count": 1,
        "policy_count": 1,
        "accepted_fields": ["input_data_format", "max_pixels", "min_pixels"],
        "unsupported_fields": [],
        "policies": [
            {
                "image_index": 0,
                "policy": {
                    "input_data_format": "channels_last",
                    "max_pixels": 4096,
                    "min_pixels": 1024,
                },
            }
        ],
    }


def test_prepared_request_preprocessing_policy_receipt_skips_empty_policy_requests() -> None:
    assert prepared_request_preprocessing_policy_receipt(_prepared_request()) == {}
    assert prepared_request_preprocessing_policy_receipt(_prepared_request(None)) == {}


def test_prepared_request_preprocessing_policy_receipt_uses_request_signature_gate() -> None:
    request = _prepared_request({"min_pixels": 1024})

    assert prepared_request_preprocessing_policy_receipt(request) == {
        "image_count": 1,
        "policy_count": 1,
        "accepted_fields": ["min_pixels"],
        "unsupported_fields": [],
        "policies": [
            {
                "image_index": 0,
                "policy": {"min_pixels": 1024},
            }
        ],
    }


def test_image_preprocessing_resize_shape_requires_complete_consistent_dimensions() -> None:
    assert image_preprocessing_resize_shape(
        _prepared_request({"resized_height": 768, "resized_width": 1024}).images
    ) == (768, 1024)
    assert (
        image_preprocessing_resize_shape(_prepared_request({"resized_height": 768}).images)
        is None
    )
    assert (
        image_preprocessing_resize_shape(
            _prepared_request(
                {"resized_height": 768, "resized_width": 1024},
                {"resized_height": 512, "resized_width": 1024},
            ).images
        )
        is None
    )
    assert (
        image_preprocessing_resize_shape(
            _prepared_request({"resized_height": 768, "resized_width": 1024}, None).images
        )
        is None
    )
    assert (
        image_preprocessing_resize_shape(
            _prepared_request(
                {"resized_height": 768, "resized_width": 1024},
                {"min_pixels": 1024},
            ).images
        )
        is None
    )
    assert image_preprocessing_resize_shape(_prepared_request({}).images) is None


def test_mlx_vlm_runtime_forwards_resize_shape_without_leaking_pixel_policy_kwargs() -> None:
    stream_generate_calls: list[dict[str, object]] = []

    class FeatureModel:
        config = SimpleNamespace(model_type="gemma4")
        vision_tower = object()
        embed_vision = object()

    def stream_generate(model, processor, prompt, image=None, **kwargs):
        _ = model
        _ = processor
        _ = prompt
        _ = image
        stream_generate_calls.append(dict(kwargs))
        return iter(())

    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=lambda model_path, revision="main": (
                FeatureModel(),
                SimpleNamespace(image_processor=object()),
            ),
            stream_generate_fn=stream_generate,
            apply_chat_template_fn=lambda *args, **kwargs: "",
        )
    )
    loaded_model = runtime.load_model(_imported_gemma4_vlm_model())
    prepared = runtime.render_prompt(
        _image_message(
            {
                "min_pixels": "1024",
                "max_pixels": "4096",
                "resized_height": "768",
                "resized_width": "1024",
                "input_data_format": "channels-last",
            }
        ),
        loaded_model=loaded_model,
    )

    list(
        runtime.generate_tokens(
            loaded_model,
            prepared,
            common_pb2.SamplingConfig(max_output_tokens=1),
            Event(),
        )
    )

    assert stream_generate_calls[0]["resize_shape"] == (768, 1024)
    assert "min_pixels" not in stream_generate_calls[0]
    assert "max_pixels" not in stream_generate_calls[0]
    assert "input_data_format" not in stream_generate_calls[0]
    assert runtime.last_probe_snapshot().preprocessing_policy_receipt["accepted_fields"] == [
        "input_data_format",
        "max_pixels",
        "min_pixels",
        "resized_height",
        "resized_width",
    ]
