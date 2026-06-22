from threading import Event

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, runtime_pb2

from worker.grpc_server import WorkerInferenceService, WorkerRuntimeService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime.deterministic_vlm_runtime import DeterministicVLMRuntime
from worker.runtime.mlx_text_runtime import MLXTextRuntime
from worker.runtime.multimodal_preprocessing import PreparedImageInput, PreparedVisionRequest
from worker.runtime.vision_family_adapters import (
    resolve_vision_family_config,
    vision_processor_capability_metadata,
)


class PassiveTextBackend:
    runtime_name = "passive-text"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 1024


def build_services():
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=PassiveTextBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    return WorkerRuntimeService(registry), WorkerInferenceService(registry)


def load_model(runtime_service: WorkerRuntimeService, model: common_pb2.ModelSpec) -> str:
    response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=model),
        context=None,
    )
    assert response.ok is True
    return response.model_handle


def paligemma_vlm_model() -> common_pb2.ModelSpec:
    model = WorkerModelCatalog.dev_vlm_model()
    model.model_id = "melix-test-paligemma-vlm"
    model.model_path = "models/melix-test-paligemma-vlm"
    model.ext["vision_family_id"] = "paligemma-v1"
    model.ext["vision_prompt_profile_id"] = "paligemma-caption-v1"
    model.ext["vision_tokenization_mode"] = "prefix"
    model.ext["vision_max_images_per_prompt"] = "1"
    model.ext["vision_supports_tool_calls"] = "false"
    model.ext["melix.multimodal_adapter_hash"] = "vision-family-paligemma-v1"
    model.ext["melix.adapter_set_hash"] = "vision-family-paligemma-v1"
    model.ext["melix.capability.route_kind"] = "python_vlm"
    model.ext["melix.capability.class"] = "vlm"
    model.ext["melix.capability.supported_modalities"] = "text,image"
    model.ext["melix.capability.supported_tasks"] = "vlm,generate"
    model.ext["melix.capability.supported_parsers"] = "text"
    model.ext["tool_parser_mode"] = ""
    model.ext["tool_parser_namespaces"] = ""
    model.ext["tool_parser_xml_fallback"] = ""
    return model


def text_only_vlm_request(prompt_text: str) -> PreparedVisionRequest:
    return PreparedVisionRequest(
        prompt_text=prompt_text,
        images=[],
        videos=[],
        video_frame_policies=[],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=len(prompt_text.encode("utf-8")),
        preprocess_peak_memory_bytes=0,
        prompt_hash_hex="1" * 64,
        multimodal_hash_hex="2" * 64,
    )


def processor_shape_model(
    *,
    policy: str = "paligemma-multicrop-v2",
    crop_grid: str = "2x2",
    max_crop_count: str = "4",
    projected_feature_shape: str = "4x256x2048",
) -> common_pb2.ModelSpec:
    model = paligemma_vlm_model()
    model.ext["vision_processor_policy"] = policy
    model.ext["vision_processor_crop_grid"] = crop_grid
    model.ext["vision_processor_patch_size"] = "14"
    model.ext["vision_processor_max_crop_count"] = max_crop_count
    model.ext["vision_prompt_format"] = "prefix-image-first"
    model.ext["vision_projected_feature_shape"] = projected_feature_shape
    return model


def image_messages(payload: bytes):
    return [
        common_pb2.ChatMessage(
            role="user",
            parts=[
                common_pb2.MessagePart(text="Caption the image."),
                common_pb2.MessagePart(
                    image_bytes=payload,
                    media=common_pb2.MediaMetadata(
                        media_type=common_pb2.MEDIA_TYPE_IMAGE,
                        source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                    ),
                ),
            ],
        )
    ]


def test_text_only_generate_rejects_image_before_prompt_conversion() -> None:
    runtime_service, inference_service = build_services()
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_text_model())

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="text-media-rejected"),
            model_handle=model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Describe this."),
                    common_pb2.MessagePart(
                        image_bytes=b"text runtime must not drop this image",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                        ),
                    ),
                ],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
        return_usage=True,
    )

    events = list(inference_service.Generate(request, context=None))

    assert len(events) == 1
    assert events[0].HasField("error")
    assert events[0].error.error.code == "unsupported_media"
    assert events[0].error.error.details["reason"] == "text_runtime_media_unsupported"
    assert events[0].error.error.details["runtime_kind"] == "text"
    assert events[0].error.error.details["media_types"] == "image"
    assert events[0].error.error.details["image_count"] == "1"
    assert events[0].error.error.details["video_count"] == "0"


def test_text_only_generate_rejects_audio_video_media_before_prompt_conversion() -> None:
    runtime_service, inference_service = build_services()
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_text_model())

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="text-audio-video-rejected"),
            model_handle=model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Summarize these media inputs."),
                    common_pb2.MessagePart(
                        audio_bytes=b"audio payload",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_AUDIO,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                        ),
                    ),
                    common_pb2.MessagePart(
                        video_bytes=b"video payload",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_VIDEO,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                        ),
                    ),
                ],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
        return_usage=True,
    )

    events = list(inference_service.Generate(request, context=None))

    assert len(events) == 1
    assert events[0].error.error.code == "unsupported_media"
    assert events[0].error.error.details["reason"] == "text_runtime_media_unsupported"
    assert events[0].error.error.details["media_types"] == "audio,video"
    assert events[0].error.error.details["audio_count"] == "1"
    assert events[0].error.error.details["video_count"] == "1"


def test_text_only_generate_rejects_video_only_media_before_prompt_conversion() -> None:
    runtime_service, inference_service = build_services()
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_text_model())

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="text-video-rejected"),
            model_handle=model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(
                        video_bytes=b"video-only payload",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_VIDEO,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                        ),
                    ),
                ],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
        return_usage=True,
    )

    events = list(inference_service.Generate(request, context=None))

    assert len(events) == 1
    assert events[0].error.error.code == "unsupported_media"
    assert events[0].error.error.details["media_types"] == "video"
    assert events[0].error.error.details["video_count"] == "1"


def test_media_admission_scan_skips_empty_parts_before_media() -> None:
    runtime_service, inference_service = build_services()
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_text_model())

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="text-empty-part-then-image-rejected"),
            model_handle=model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(),
                    common_pb2.MessagePart(text="Describe this."),
                    common_pb2.MessagePart(
                        image_bytes=b"image after empty part",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                        ),
                    ),
                ],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
        return_usage=True,
    )

    events = list(inference_service.Generate(request, context=None))

    assert len(events) == 1
    assert events[0].error.error.code == "unsupported_media"
    assert events[0].error.error.details["media_count"] == "1"
    assert events[0].error.error.details["image_count"] == "1"


def test_vlm_runtime_records_processor_shape_receipt() -> None:
    runtime = DeterministicVLMRuntime()
    loaded_model = runtime.load_model(processor_shape_model())
    messages = [
        common_pb2.ChatMessage(
            role="user",
            parts=[
                common_pb2.MessagePart(text="Caption the image."),
                common_pb2.MessagePart(
                    image_bytes=b"processor receipt image",
                    media=common_pb2.MediaMetadata(
                        media_type=common_pb2.MEDIA_TYPE_IMAGE,
                        source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                        preprocessing_hints={
                            "min_pixels": "1024",
                            "max_pixels": "4096",
                            "layout": "channels-first",
                        },
                    ),
                ),
            ],
        )
    ]

    prepared = runtime.render_prompt(messages, loaded_model=loaded_model)
    list(runtime.generate_tokens(loaded_model, prepared, None, Event()))
    probe = runtime.last_probe_snapshot()

    assert probe.processor_shape_receipt == {
        "processor_policy": "paligemma-multicrop-v2",
        "media_count": 1,
        "image_count": 1,
        "video_count": 0,
        "crop_grid": "2x2",
        "patch_size": "14",
        "max_crop_count": 4,
        "prompt_format": "prefix-image-first",
        "projected_feature_shape": "4x256x2048",
    }
    assert probe.preprocessing_policy_receipt == {
        "image_count": 1,
        "policy_count": 1,
        "accepted_fields": ["layout", "max_pixels", "min_pixels"],
        "unsupported_fields": [],
        "policies": [
            {
                "image_index": 0,
                "policy": {
                    "layout": "channels_first",
                    "max_pixels": 4096,
                    "min_pixels": 1024,
                },
            }
        ],
    }
    assert probe.image_feature_cache_hits == 0
    assert probe.image_feature_cache_misses == 1


def test_vision_family_config_exposes_processor_shape_metadata() -> None:
    family_config = resolve_vision_family_config(
        {
            "vision_family_id": "paligemma-v1",
            "vision_processor_policy": "paligemma-multicrop-v2",
            "vision_processor_crop_grid": "2x2",
            "vision_processor_patch_size": "14",
            "vision_processor_max_crop_count": "4",
            "vision_prompt_format": "prefix-image-first",
            "vision_projected_feature_shape": "4x256x2048",
        }
    )
    metadata = {
        **family_config.capability_metadata(),
        **vision_processor_capability_metadata(
            {
                "vision_family_id": "paligemma-v1",
                "vision_processor_policy": "paligemma-multicrop-v2",
                "vision_processor_crop_grid": "2x2",
                "vision_processor_patch_size": "14",
                "vision_processor_max_crop_count": "4",
                "vision_prompt_format": "prefix-image-first",
                "vision_projected_feature_shape": "4x256x2048",
            }
        ),
    }

    assert {
        key: metadata[key]
        for key in (
            "vision_processor_policy",
            "vision_processor_crop_grid",
            "vision_processor_patch_size",
            "vision_processor_max_crop_count",
            "vision_prompt_format",
            "vision_projected_feature_shape",
        )
    } == {
        "vision_processor_policy": "paligemma-multicrop-v2",
        "vision_processor_crop_grid": "2x2",
        "vision_processor_patch_size": "14",
        "vision_processor_max_crop_count": "4",
        "vision_prompt_format": "prefix-image-first",
        "vision_projected_feature_shape": "4x256x2048",
    }


def test_vlm_processor_shape_receipt_uses_defaults_without_metadata() -> None:
    runtime = DeterministicVLMRuntime()
    prepared = text_only_vlm_request("Caption this.")

    assert runtime._processor_shape_receipt(
        loaded_model={},
        prepared_request=prepared,
    ) == {
        "processor_policy": "",
        "media_count": 0,
        "image_count": 0,
        "video_count": 0,
        "crop_grid": "",
        "patch_size": "",
        "max_crop_count": 0,
        "prompt_format": "",
        "projected_feature_shape": "",
    }


def test_vlm_processor_shape_receipt_ignores_invalid_max_crop_count() -> None:
    runtime = DeterministicVLMRuntime()
    loaded_model = {
        "vision_processor_policy": "paligemma-multicrop-v2",
        "vision_processor_max_crop_count": "2x2",
    }

    receipt = runtime._processor_shape_receipt(
        loaded_model=loaded_model,
        prepared_request=text_only_vlm_request("Caption this."),
    )

    assert receipt["processor_policy"] == "paligemma-multicrop-v2"
    assert receipt["max_crop_count"] == 0


def test_vlm_text_only_cache_fingerprint_preserves_existing_multimodal_hash() -> None:
    runtime = DeterministicVLMRuntime()
    prepared = text_only_vlm_request("Caption this.")
    cache_identity, scope_id = runtime._cache_identity(
        prepared,
        processor_shape_model(),
    )

    assert cache_identity.endswith(prepared.multimodal_hash_hex)
    assert scope_id == f"melix-dev-vlm:{prepared.multimodal_hash_hex[:16]}"


def test_vlm_cache_identity_fingerprint_uses_identity_segment_for_media() -> None:
    runtime = DeterministicVLMRuntime()
    prepared = text_only_vlm_request("Caption this.")
    assert (
        runtime._cache_identity_fingerprint_hash_hex(
            cache_identity="model:dev:q8:text:off:fingerprint",
            prepared_request=prepared,
        )
        == prepared.multimodal_hash_hex
    )
    prepared.images.append(
        PreparedImageInput(
            bytes_data=b"image",
            source_kind="inline",
            reference="inline:image.jpg",
            mime_type="image/jpeg",
            format="jpg",
            filename="image.jpg",
            sha256_hex="3" * 64,
        )
    )

    assert (
        runtime._cache_identity_fingerprint_hash_hex(
            cache_identity="model:dev:q8:text:off:fingerprint",
            prepared_request=prepared,
        )
        == "fingerprint"
    )


def test_vlm_runtime_cache_misses_when_processor_shape_changes() -> None:
    runtime = DeterministicVLMRuntime()
    messages = image_messages(b"same payload different processor")
    loaded_a = runtime.load_model(processor_shape_model())
    loaded_b = runtime.load_model(
        processor_shape_model(
            policy="paligemma-multicrop-v3",
            crop_grid="3x3",
            max_crop_count="9",
            projected_feature_shape="9x256x2048",
        )
    )

    prepared_a = runtime.render_prompt(messages, loaded_model=loaded_a)
    list(runtime.generate_tokens(loaded_a, prepared_a, None, Event()))
    first_probe = runtime.last_probe_snapshot()
    prepared_b = runtime.render_prompt(messages, loaded_model=loaded_b)
    list(runtime.generate_tokens(loaded_b, prepared_b, None, Event()))
    second_probe = runtime.last_probe_snapshot()

    assert first_probe.cache_hit is False
    assert second_probe.cache_hit is False
    assert first_probe.cache_identity != second_probe.cache_identity
    assert second_probe.image_feature_cache_hits == 0
    assert second_probe.image_feature_cache_misses == 1
