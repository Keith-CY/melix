from pathlib import Path
from threading import Event
from urllib.error import URLError

import pytest

from packages.protocol.python.worker.v1 import cache_pb2, common_pb2, inference_pb2, maintenance_pb2, runtime_pb2

from worker.engine.maintenance_core import MaintenanceCore
from worker.grpc_server import WorkerCacheService, WorkerInferenceService, WorkerRuntimeService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime.deterministic_ocr_runtime import DeterministicOCRRuntime
from worker.runtime.deterministic_vlm_runtime import DeterministicVLMRuntime
from worker.runtime.mlx_text_runtime import MLXTextRuntime
from worker.runtime import multimodal_preprocessing
from worker.runtime.multimodal_fast_paths import fast_path_probe_signature
from worker.runtime.multimodal_preprocessing import (
    MultimodalPreprocessError,
    _bytes_from_image_uri,
    _path_from_uri,
    _prepare_image_part,
    prepare_vision_request,
)
from worker.runtime.vision_family_adapters import resolve_vision_family_config


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
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    maintenance_core = MaintenanceCore(registry, jobs_root=Path(".runtime/test-model-ops"))
    return runtime_service, inference_service, maintenance_core


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


def test_generate_streams_ocr_text_from_inline_image_bytes() -> None:
    runtime_service, inference_service, maintenance_core = build_services()
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_ocr_model())

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="ocr-1"),
            model_handle=model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Extract the receipt text."),
                        common_pb2.MessagePart(
                            image_bytes=b"Receipt Total 42",
                            media=common_pb2.MediaMetadata(
                                media_type=common_pb2.MEDIA_TYPE_IMAGE,
                                mime_type="image/png",
                                source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                                filename="receipt.png",
                            ),
                    ),
                ],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=32),
        stream=True,
        return_usage=True,
    )

    events = list(inference_service.Generate(request, context=None))
    token_text = "".join(event.token_delta.text for event in events if event.HasField("token_delta"))
    completed = next(event.completed for event in events if event.HasField("completed"))
    model_info = maintenance_core.get_model_info(
        maintenance_pb2.GetModelInfoRequest(source_model="melix-dev-ocr")
    )

    assert token_text == "Receipt Total 42"
    assert completed.assistant_text == "Receipt Total 42"
    assert model_info.ok is True
    assert model_info.supported_modalities == ["text", "image"]
    assert model_info.supported_tasks == ["ocr", "generate"]


def test_generate_streams_vlm_response_from_file_image_uri(tmp_path: Path) -> None:
    runtime_service, inference_service, maintenance_core = build_services()
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_vlm_model())
    image_path = tmp_path / "image.txt"
    image_path.write_text("cat on mat")

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="vlm-1"),
            model_handle=model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Describe the image."),
                        common_pb2.MessagePart(
                            image_uri=image_path.as_uri(),
                            media=common_pb2.MediaMetadata(
                                media_type=common_pb2.MEDIA_TYPE_IMAGE,
                                mime_type="image/png",
                                source_kind=common_pb2.MEDIA_SOURCE_URI,
                                filename=image_path.name,
                            ),
                    ),
                ],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=64),
        stream=True,
        return_usage=True,
    )

    events = list(inference_service.Generate(request, context=None))
    token_text = "".join(event.token_delta.text for event in events if event.HasField("token_delta"))
    completed = next(event.completed for event in events if event.HasField("completed"))
    model_info = maintenance_core.get_model_info(
        maintenance_pb2.GetModelInfoRequest(source_model="melix-dev-vlm")
    )

    assert token_text == "Image content: cat on mat\nPrompt: Describe the image."
    assert completed.assistant_text == "Image content: cat on mat\nPrompt: Describe the image."
    assert model_info.ok is True
    assert model_info.supported_modalities == ["text", "image"]
    assert model_info.supported_tasks == ["vlm", "generate"]
    assert model_info.supported_parsers == ["text", "qwen"]


def test_generate_streams_vlm_response_from_image_only_prompt(tmp_path: Path) -> None:
    runtime_service, inference_service, _ = build_services()
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_vlm_model())
    image_path = tmp_path / "image-only.txt"
    image_path.write_text("standalone image")

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="vlm-image-only"),
            model_handle=model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(
                        image_uri=image_path.as_uri(),
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_URI,
                            filename=image_path.name,
                        ),
                    )
                ],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=64),
        stream=True,
        return_usage=True,
    )

    events = list(inference_service.Generate(request, context=None))
    token_text = "".join(event.token_delta.text for event in events if event.HasField("token_delta"))
    completed = next(event.completed for event in events if event.HasField("completed"))

    assert token_text == "Image content: standalone image\nPrompt: Describe the image."
    assert completed.assistant_text == token_text


def test_prepare_vision_request_accepts_video_only_inputs_and_exposes_frame_policy() -> None:
    request = prepare_vision_request(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Summarize the clip."),
                    common_pb2.MessagePart(
                        video_bytes=b"video fixture",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_VIDEO,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            mime_type="video/mp4",
                            format="mp4",
                            filename="clip.mp4",
                            duration_ms=10_000,
                            frame_budget=6,
                            start_ms=1_000,
                            end_ms=5_000,
                        ),
                    ),
                ],
            )
        ]
    )

    assert request.prompt_text == "Summarize the clip."
    assert request.images == []
    assert len(request.videos) == 1
    assert request.videos[0].filename == "clip.mp4"
    assert request.videos[0].frame_budget == 6
    assert len(request.videos[0].sha256_hex) == 64
    assert len(request.video_frame_policies) == 1
    assert request.video_frame_policies[0].sampling_strategy == "uniform_sample"
    assert request.video_frame_policies[0].requested_frame_budget == 6
    assert request.video_frame_policies[0].effective_frame_count == 6
    assert request.video_frame_policies[0].clip_start_ms == 1_000
    assert request.video_frame_policies[0].clip_end_ms == 5_000
    assert request.video_frame_policies[0].clip_duration_ms == 4_000
    assert request.preprocess_input_bytes == len(b"video fixture")
    assert request.preprocess_peak_memory_bytes == len(b"video fixture")
    assert request.effective_video_frame_count == 6
    assert request.requested_video_frame_budget == 6
    assert request.effective_video_window_ms == 4_000
    assert len(request.multimodal_hash_hex) == 64


def test_prepare_vision_request_uses_duration_when_video_end_is_missing() -> None:
    request = prepare_vision_request(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(
                        video_bytes=b"duration-only fixture",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_VIDEO,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            mime_type="video/mp4",
                            format="mp4",
                            filename="duration-only.mp4",
                            duration_ms=12_000,
                        ),
                    ),
                ],
            )
        ]
    )

    assert request.contains_video is True
    assert request.video_frame_policies[0].clip_end_ms == 12_000
    assert request.video_frame_policies[0].clip_duration_ms == 12_000
    assert request.video_frame_policies[0].effective_frame_count == 4
    assert request.effective_video_frame_count == 4
    assert request.effective_video_window_ms == 12_000


def test_prepare_vision_request_defaults_video_frame_budget_when_window_is_unknown() -> None:
    request = prepare_vision_request(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(
                        video_bytes=b"unknown-window fixture",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_VIDEO,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            mime_type="video/mp4",
                            format="mp4",
                            filename="unknown-window.mp4",
                        ),
                    ),
                ],
            )
        ]
    )

    assert request.contains_video is True
    assert request.video_frame_policies[0].clip_end_ms == 0
    assert request.video_frame_policies[0].clip_duration_ms == 0
    assert request.video_frame_policies[0].effective_frame_count == 8
    assert request.effective_video_frame_count == 8
    assert request.effective_video_window_ms == 0


def test_prepare_vision_request_rejects_requests_without_image_or_video() -> None:
    with pytest.raises(MultimodalPreprocessError, match="No image or video input provided."):
        prepare_vision_request(
            [
                common_pb2.ChatMessage(
                    role="user",
                    parts=[common_pb2.MessagePart(text="Only text is not multimodal.")],
                )
            ]
        )


def test_generate_streams_vlm_response_from_video_only_prompt() -> None:
    runtime_service, inference_service, _ = build_services()
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_vlm_model())

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="vlm-video-only"),
            model_handle=model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Summarize the clip."),
                    common_pb2.MessagePart(
                        video_bytes=b"video fixture",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_VIDEO,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            mime_type="video/mp4",
                            format="mp4",
                            filename="clip.mp4",
                            frame_budget=6,
                            start_ms=1_000,
                            end_ms=5_000,
                        ),
                    ),
                ],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=64),
        stream=True,
        return_usage=True,
    )

    events = list(inference_service.Generate(request, context=None))
    token_text = "".join(event.token_delta.text for event in events if event.HasField("token_delta"))
    completed = next(event.completed for event in events if event.HasField("completed"))
    stats = runtime_service.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), context=None).stats

    assert token_text == (
        "Video content: clip.mp4\n"
        "Frame policy: uniform_sample 6 frame(s) from 1000ms to 5000ms\n"
        "Prompt: Summarize the clip."
    )
    assert completed.assistant_text == token_text
    assert stats.last_probe_kind == "vlm"
    assert stats.last_video_effective_frame_count == 6
    assert stats.last_video_requested_frame_budget == 6
    assert stats.last_video_window_ms == 4_000


def test_deterministic_vlm_runtime_formats_multi_video_prompts() -> None:
    request = prepare_vision_request(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Compare the two clips."),
                    common_pb2.MessagePart(
                        video_bytes=b"first video fixture",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_VIDEO,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            format="mp4",
                            filename="first.mp4",
                            frame_budget=4,
                            start_ms=0,
                            end_ms=2_000,
                        ),
                    ),
                    common_pb2.MessagePart(
                        video_bytes=b"second video fixture",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_VIDEO,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            format="mp4",
                            filename="second.mp4",
                            frame_budget=3,
                            start_ms=500,
                            end_ms=3_500,
                        ),
                    ),
                ],
            )
        ]
    )

    response_text = DeterministicVLMRuntime._response_text(request)

    assert response_text == (
        "Video 1: first.mp4 [frames=4;start_ms=0;end_ms=2000]\n"
        "Video 2: second.mp4 [frames=3;start_ms=500;end_ms=3500]\n"
        "Prompt: Compare the two clips."
    )


def test_deterministic_vlm_runtime_formats_mixed_image_and_video_prompts() -> None:
    request = prepare_vision_request(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Describe both media items."),
                    common_pb2.MessagePart(
                        image_bytes=b"mixed image fixture",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            filename="mixed-1.png",
                        ),
                    ),
                    common_pb2.MessagePart(
                        image_bytes=b"second image fixture",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            filename="mixed-2.png",
                        ),
                    ),
                    common_pb2.MessagePart(
                        video_bytes=b"mixed video fixture",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_VIDEO,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            format="mp4",
                            filename="mixed.mp4",
                            frame_budget=5,
                            start_ms=250,
                            end_ms=2_250,
                        ),
                    ),
                ],
            )
        ]
    )

    response_text = DeterministicVLMRuntime._response_text(request)

    assert response_text == (
        "Image 1 content: mixed image fixture\n"
        "Image 2 content: second image fixture\n"
        "Video 1: mixed.mp4 [frames=5;start_ms=250;end_ms=2250]\n"
        "Prompt: Describe both media items."
    )


def test_vlm_runtime_load_model_exposes_family_capabilities() -> None:
    runtime = DeterministicVLMRuntime()

    loaded_model = runtime.load_model(paligemma_vlm_model())

    assert loaded_model["vision_family_id"] == "paligemma-v1"
    assert loaded_model["vision_prompt_profile_id"] == "paligemma-caption-v1"
    assert loaded_model["vision_tokenization_mode"] == "prefix"
    assert loaded_model["vision_max_images_per_prompt"] == "1"
    assert loaded_model["vision_supports_tool_calls"] == "false"
    assert loaded_model["multimodal_adapter_hash"] == "vision-family-paligemma-v1"


def test_vlm_render_prompt_reuses_prepared_prompt_metadata() -> None:
    runtime = DeterministicVLMRuntime()
    loaded_model = runtime.load_model(paligemma_vlm_model())
    messages = [
        common_pb2.ChatMessage(
            role="user",
            parts=[
                common_pb2.MessagePart(text="Summarize the image."),
                common_pb2.MessagePart(
                    image_bytes=b"render prompt image",
                    media=common_pb2.MediaMetadata(
                        media_type=common_pb2.MEDIA_TYPE_IMAGE,
                        source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                        mime_type="image/png",
                        filename="render-prompt.png",
                    ),
                ),
            ],
        )
    ]

    prepared = runtime.render_prompt(messages, loaded_model=loaded_model)
    snapshot = runtime.last_probe_snapshot()

    assert prepared.prompt_text == "Summarize the image."
    assert snapshot.cache_identity
    assert snapshot.cache_scope_id
    assert snapshot.cache_hit is False
    assert loaded_model["_vision_family_config"].family_id == "paligemma-v1"


def test_vlm_prefill_reuses_prompt_metadata_without_recomputing_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = DeterministicVLMRuntime()
    loaded_model = runtime.load_model(paligemma_vlm_model())
    messages = [
        common_pb2.ChatMessage(
            role="user",
            parts=[
                common_pb2.MessagePart(text="Summarize the image."),
                common_pb2.MessagePart(
                    image_bytes=b"phase aware image",
                    media=common_pb2.MediaMetadata(
                        media_type=common_pb2.MEDIA_TYPE_IMAGE,
                        source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                        mime_type="image/png",
                        filename="phase-aware.png",
                    ),
                ),
            ],
        )
    ]
    call_counts = {
        "family_config": 0,
        "cache_identity": 0,
        "prompt_token_count": 0,
    }
    original_family_config = runtime._family_config
    original_cache_identity = runtime._cache_identity
    original_prompt_token_count = runtime.prompt_token_count

    def counted_family_config(model):
        call_counts["family_config"] += 1
        return original_family_config(model)

    def counted_cache_identity(prepared_request, model, execution_ext=None):
        call_counts["cache_identity"] += 1
        return original_cache_identity(prepared_request, model, execution_ext=execution_ext)

    def counted_prompt_token_count(prepared_request, loaded_model=None, family_config=None):
        call_counts["prompt_token_count"] += 1
        return original_prompt_token_count(
            prepared_request,
            loaded_model=loaded_model,
            family_config=family_config,
        )

    monkeypatch.setattr(runtime, "_family_config", counted_family_config)
    monkeypatch.setattr(runtime, "_cache_identity", counted_cache_identity)
    monkeypatch.setattr(runtime, "prompt_token_count", counted_prompt_token_count)

    session = runtime.prefill("prefill-reuse", loaded_model, messages)
    events = list(runtime.decode_tokens(loaded_model, session.decode_handle, None, Event()))

    assert session.cache_hit is False
    assert session.prompt_tokens > 0
    assert "_vision_family_config" in loaded_model
    assert call_counts == {
        "family_config": 2,
        "cache_identity": 1,
        "prompt_token_count": 1,
    }
    assert len(events) == 1
    assert events[0].text == "Image content: phase aware image\nPrompt: Summarize the image."


def test_resolve_vision_family_config_handles_invalid_family_overrides() -> None:
    with pytest.raises(ValueError, match="Unsupported vision family adapter"):
        resolve_vision_family_config({"vision_family_id": "unknown-family"})

    family_config = resolve_vision_family_config(
        {
            "vision_family_id": "paligemma-v1",
            "vision_max_images_per_prompt": "invalid",
            "vision_supports_tool_calls": "maybe",
        }
    )

    assert family_config.max_images_per_prompt == 1
    assert family_config.supports_tool_calls is False


def test_resolve_vision_family_config_rejects_multi_video_requests_for_single_video_families() -> None:
    family_config = resolve_vision_family_config({"vision_family_id": "paligemma-v1"})
    request = prepare_vision_request(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(
                        video_bytes=b"video-one",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_VIDEO,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            filename="one.mp4",
                        ),
                    ),
                    common_pb2.MessagePart(
                        video_bytes=b"video-two",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_VIDEO,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            filename="two.mp4",
                        ),
                    ),
                ],
            )
        ]
    )

    with pytest.raises(ValueError, match="supports at most 1 video input"):
        family_config.shape_request(request)


def test_generate_streams_vlm_response_uses_family_specific_image_only_prompt_default() -> None:
    runtime_service, inference_service, _ = build_services()
    model_handle = load_model(runtime_service, paligemma_vlm_model())

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="paligemma-image-only"),
            model_handle=model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(
                        image_bytes=b"paligemma image",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            filename="paligemma.png",
                        ),
                    )
                ],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=64),
        stream=True,
        return_usage=True,
    )

    events = list(inference_service.Generate(request, context=None))
    token_text = "".join(event.token_delta.text for event in events if event.HasField("token_delta"))
    completed = next(event.completed for event in events if event.HasField("completed"))

    assert token_text == "Image content: paligemma image\nPrompt: Caption the image."
    assert completed.assistant_text == token_text


def test_generate_streams_vlm_family_disables_tool_call_delta() -> None:
    runtime_service, inference_service, _ = build_services()
    model_handle = load_model(runtime_service, paligemma_vlm_model())

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="paligemma-tool-call"),
            model_handle=model_handle,
            ext={
                "melix.tool_parser.mode": "qwen",
                "melix.tool_parser.namespaces": "tools.vision",
            },
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Call the tool for this image."),
                    common_pb2.MessagePart(
                        image_bytes=b"tool disabled image",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            filename="tool-disabled.png",
                        ),
                    ),
                ],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=64),
        stream=True,
        return_usage=True,
    )

    events = list(inference_service.Generate(request, context=None))

    assert not any(event.HasField("tool_call_delta") for event in events)


def test_prefill_rejects_multi_image_for_single_image_family() -> None:
    runtime_service, inference_service, _ = build_services()
    model_handle = load_model(runtime_service, paligemma_vlm_model())

    response = inference_service.Prefill(
        inference_pb2.PrefillRequest(
            execution=inference_pb2.ExecutionMetadata(
                id=common_pb2.RequestIdentity(request_id="paligemma-multi-image"),
                model_handle=model_handle,
            ),
            messages=[
                common_pb2.ChatMessage(
                    role="user",
                    parts=[
                        common_pb2.MessagePart(text="Compare both images."),
                        common_pb2.MessagePart(
                            image_bytes=b"first image",
                            media=common_pb2.MediaMetadata(
                                media_type=common_pb2.MEDIA_TYPE_IMAGE,
                                source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                                filename="first.png",
                            ),
                        ),
                        common_pb2.MessagePart(
                            image_bytes=b"second image",
                            media=common_pb2.MediaMetadata(
                                media_type=common_pb2.MEDIA_TYPE_IMAGE,
                                source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                                filename="second.png",
                            ),
                        ),
                    ],
                )
            ],
            return_decode_handle=True,
            prefill_step_size=16,
        ),
        context=None,
    )

    assert response.ok is False
    assert response.error.code == "runtime_error"
    assert "supports at most 1 image" in response.error.message


def test_generate_streams_vlm_response_from_multi_image_prompt(tmp_path: Path) -> None:
    runtime_service, inference_service, _ = build_services()
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_vlm_model())
    first_image = tmp_path / "image-1.txt"
    second_image = tmp_path / "image-2.txt"
    first_image.write_text("cat on mat")
    second_image.write_text("dog on rug")

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="vlm-multi-1"),
            model_handle=model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Compare the two images."),
                    common_pb2.MessagePart(
                        image_uri=first_image.as_uri(),
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_URI,
                            filename=first_image.name,
                        ),
                    ),
                    common_pb2.MessagePart(
                        image_uri=second_image.as_uri(),
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_URI,
                            filename=second_image.name,
                        ),
                    ),
                ],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=64),
        stream=True,
        return_usage=True,
    )

    events = list(inference_service.Generate(request, context=None))
    token_text = "".join(event.token_delta.text for event in events if event.HasField("token_delta"))
    completed = next(event.completed for event in events if event.HasField("completed"))

    assert token_text == (
        "Image 1 content: cat on mat\n"
        "Image 2 content: dog on rug\n"
        "Prompt: Compare the two images."
    )
    assert completed.assistant_text == token_text


def test_generate_streams_vlm_tool_call_delta_when_tool_parser_is_enabled() -> None:
    runtime_service, inference_service, _ = build_services()
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_vlm_model())

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="vlm-tool-call-1"),
            model_handle=model_handle,
            ext={
                "melix.tool_parser.mode": "qwen",
                "melix.tool_parser.namespaces": "tools.vision",
                "melix.tool_parser.fallback_mode": "xml",
            },
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Call the tool for this image."),
                    common_pb2.MessagePart(
                        image_bytes=b"vision tool image",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            mime_type="image/png",
                            filename="tool-image.png",
                        ),
                    ),
                ],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=64),
        stream=True,
    )

    events = list(inference_service.Generate(request, context=None))
    tool_call = next(event.tool_call_delta for event in events if event.HasField("tool_call_delta"))
    token_text = "".join(event.token_delta.text for event in events if event.HasField("token_delta"))
    completed = next(event.completed for event in events if event.HasField("completed"))

    assert tool_call.tool_name == "tools.vision"
    assert tool_call.call_id.startswith("tool:")
    assert tool_call.arguments_json_fragment == '{"prompt":"Call the tool for this image.","image_count":1}'
    assert token_text == "Image content: vision tool image\nPrompt: Call the tool for this image."
    assert completed.assistant_text == token_text


def test_vlm_prefill_and_decode_expose_explicit_runtime_lifecycle() -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=PassiveTextBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_vlm_model())

    request_id = "vlm-phase-aware-1"
    messages = [
        common_pb2.ChatMessage(
            role="user",
            parts=[
                common_pb2.MessagePart(text="Summarize the image."),
                common_pb2.MessagePart(
                    image_bytes=b"phase aware image",
                    media=common_pb2.MediaMetadata(
                        media_type=common_pb2.MEDIA_TYPE_IMAGE,
                        source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                        mime_type="image/png",
                        filename="phase-aware.png",
                    ),
                ),
            ],
        )
    ]

    prefill_response = inference_service.Prefill(
        inference_pb2.PrefillRequest(
            execution=inference_pb2.ExecutionMetadata(
                id=common_pb2.RequestIdentity(request_id=request_id),
                model_handle=model_handle,
            ),
            messages=messages,
            return_decode_handle=True,
            prefill_step_size=16,
        ),
        context=None,
    )

    assert prefill_response.ok is True
    assert prefill_response.decode_handle == f"vlm:{request_id}"
    assert prefill_response.block_table_id.startswith("vlm-block:")
    assert prefill_response.block_table.total_token_count > 0
    assert prefill_response.prompt_tokens > 0
    assert prefill_response.lifecycle_phase == common_pb2.EXECUTION_PREFILLING
    assert prefill_response.admission_state == common_pb2.ADMISSION_ADMITTED
    assert prefill_response.applied_acceleration.mode == common_pb2.ACCELERATION_MODE_BASELINE

    prefill_stats = runtime_service.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), context=None).stats
    assert prefill_stats.active_prefills == 1
    assert prefill_stats.active_decodes == 0

    decode_events = inference_service.Decode(
        inference_pb2.DecodeRequest(
            execution=inference_pb2.ExecutionMetadata(
                id=common_pb2.RequestIdentity(request_id=request_id),
                model_handle=model_handle,
            ),
            decode_handle=prefill_response.decode_handle,
            sampling=common_pb2.SamplingConfig(max_output_tokens=64),
            max_output_tokens=64,
            return_usage=True,
        ),
        context=None,
    )
    first_event = next(decode_events)

    assert first_event.decode_started.decode_handle == prefill_response.decode_handle
    assert first_event.decode_started.max_output_tokens == 64
    assert first_event.decode_started.resumed_from_prefill is True
    assert first_event.phase == common_pb2.EXECUTION_DECODING

    decode_stats = runtime_service.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), context=None).stats
    assert decode_stats.active_prefills == 0
    assert decode_stats.active_decodes == 1

    remaining_events = list(decode_events)
    token_text = "".join(event.token_delta.text for event in remaining_events if event.HasField("token_delta"))
    usage = next(event.usage_delta for event in remaining_events if event.HasField("usage_delta"))
    completed = next(event.completed for event in remaining_events if event.HasField("completed"))

    assert token_text == "Image content: phase aware image\nPrompt: Summarize the image."
    assert usage.prompt_tokens == prefill_response.prompt_tokens
    assert usage.completion_tokens > 0
    assert completed.finish_reason == "stop"
    assert completed.assistant_text == token_text

    final_stats = runtime_service.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), context=None).stats
    assert final_stats.active_prefills == 0
    assert final_stats.active_decodes == 0
    assert final_stats.last_probe_kind == "vlm"


def test_vlm_phase_aware_decode_streams_tool_call_delta_when_tool_parser_is_enabled() -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=PassiveTextBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_vlm_model())

    request_id = "vlm-phase-aware-tool-1"
    messages = [
        common_pb2.ChatMessage(
            role="user",
            parts=[
                common_pb2.MessagePart(text="Call the tool for this image."),
                common_pb2.MessagePart(
                    image_bytes=b"phase aware tool image",
                    media=common_pb2.MediaMetadata(
                        media_type=common_pb2.MEDIA_TYPE_IMAGE,
                        source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                        mime_type="image/png",
                        filename="phase-aware-tool.png",
                    ),
                ),
            ],
        )
    ]

    prefill_response = inference_service.Prefill(
        inference_pb2.PrefillRequest(
            execution=inference_pb2.ExecutionMetadata(
                id=common_pb2.RequestIdentity(request_id=request_id),
                model_handle=model_handle,
                ext={
                    "melix.tool_parser.mode": "qwen",
                    "melix.tool_parser.namespaces": "tools.vision",
                },
            ),
            messages=messages,
            return_decode_handle=True,
            prefill_step_size=16,
        ),
        context=None,
    )

    assert prefill_response.ok is True

    decode_events = list(
        inference_service.Decode(
            inference_pb2.DecodeRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id=request_id),
                    model_handle=model_handle,
                ),
                decode_handle=prefill_response.decode_handle,
                sampling=common_pb2.SamplingConfig(max_output_tokens=64),
                max_output_tokens=64,
            ),
            context=None,
        )
    )

    tool_call = next(event.tool_call_delta for event in decode_events if event.HasField("tool_call_delta"))
    token_text = "".join(event.token_delta.text for event in decode_events if event.HasField("token_delta"))
    completed = next(event.completed for event in decode_events if event.HasField("completed"))

    assert tool_call.tool_name == "tools.vision"
    assert token_text == "Image content: phase aware tool image\nPrompt: Call the tool for this image."
    assert completed.assistant_text == token_text


def test_prepare_vision_request_accepts_plain_local_paths(tmp_path: Path) -> None:
    image_path = tmp_path / "plain-local-path.txt"
    image_path.write_text("diagram text")
    request = prepare_vision_request(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Read this image."),
                    common_pb2.MessagePart(
                        image_uri=str(image_path),
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_URI,
                            filename=image_path.name,
                        ),
                    ),
                ],
            )
        ]
    )

    assert request.prompt_text == "Read this image."
    assert len(request.images) == 1
    assert request.images[0].source_kind == "uri"
    assert request.images[0].filename == image_path.name
    assert request.images[0].decoded_text() == "diagram text"
    assert len(request.images[0].sha256_hex) == 64
    assert len(request.prompt_hash_hex) == 64
    assert len(request.multimodal_hash_hex) == 64
    assert request.preprocess_input_bytes == len(b"diagram text")
    assert request.preprocess_peak_memory_bytes == len(b"diagram text")


def test_generate_streams_ocr_text_from_image_only_prompt() -> None:
    runtime_service, inference_service, _ = build_services()
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_ocr_model())

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="ocr-image-only"),
            model_handle=model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(
                        image_bytes=b"image only ocr",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            mime_type="image/png",
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            filename="image-only.png",
                        ),
                    )
                ],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=32),
        stream=True,
        return_usage=True,
    )

    events = list(inference_service.Generate(request, context=None))
    token_text = "".join(event.token_delta.text for event in events if event.HasField("token_delta"))
    completed = next(event.completed for event in events if event.HasField("completed"))

    assert token_text == "image only ocr"
    assert completed.assistant_text == "image only ocr"


def test_generate_streams_ocr_text_with_default_stop_sequence_and_request_override() -> None:
    runtime_service, inference_service, _ = build_services()
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_ocr_model())
    messages = [
        common_pb2.ChatMessage(
            role="user",
            parts=[
                common_pb2.MessagePart(text="Extract the title only."),
                common_pb2.MessagePart(
                    image_bytes=b"title<ocr:end>body",
                    media=common_pb2.MediaMetadata(
                        media_type=common_pb2.MEDIA_TYPE_IMAGE,
                        mime_type="image/png",
                        source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                        filename="ocr-stop.png",
                    ),
                ),
            ],
        )
    ]

    default_events = list(
        inference_service.Generate(
            inference_pb2.GenerateRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id="ocr-default-stop"),
                    model_handle=model_handle,
                ),
                messages=messages,
                sampling=common_pb2.SamplingConfig(max_output_tokens=32),
                stream=True,
            ),
            context=None,
        )
    )
    override_events = list(
        inference_service.Generate(
            inference_pb2.GenerateRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id="ocr-request-stop"),
                    model_handle=model_handle,
                ),
                messages=messages,
                sampling=common_pb2.SamplingConfig(max_output_tokens=32, stop=["body"]),
                stream=True,
            ),
            context=None,
        )
    )

    default_text = "".join(event.token_delta.text for event in default_events if event.HasField("token_delta"))
    override_text = "".join(event.token_delta.text for event in override_events if event.HasField("token_delta"))
    default_completed = next(event.completed for event in default_events if event.HasField("completed"))
    override_completed = next(event.completed for event in override_events if event.HasField("completed"))

    assert default_text == "title"
    assert default_completed.assistant_text == "title"
    assert override_text == "title<ocr:end>"
    assert override_completed.assistant_text == "title<ocr:end>"


def test_prepare_vision_request_accepts_remote_http_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeHeaders:
        def get_content_type(self) -> str:
            return "image/png"

    class FakeResponse:
        headers = FakeHeaders()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return b"remote diagram text"

    monkeypatch.setattr(multimodal_preprocessing, "urlopen", lambda url, timeout=5.0: FakeResponse())

    request = prepare_vision_request(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Read this remote image."),
                    common_pb2.MessagePart(
                        image_uri="https://example.com/fixtures/diagram.png",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_URI,
                            mime_type="image/png",
                        ),
                    ),
                ],
            )
        ]
    )

    assert request.prompt_text == "Read this remote image."
    assert len(request.images) == 1
    assert request.images[0].source_kind == "uri"
    assert request.images[0].reference == "https://example.com/fixtures/diagram.png"
    assert request.images[0].filename == "diagram.png"
    assert request.images[0].format == "png"
    assert request.images[0].decoded_text() == "remote diagram text"
    assert request.preprocess_input_bytes == len(b"remote diagram text")


def test_prepare_vision_request_hash_changes_when_prompt_or_image_changes(tmp_path: Path) -> None:
    image_a = tmp_path / "image-a.txt"
    image_b = tmp_path / "image-b.txt"
    image_a.write_text("diagram text")
    image_b.write_text("diagram text but different")

    def build_request(prompt: str, path: Path):
        return prepare_vision_request(
            [
                common_pb2.ChatMessage(
                    role="user",
                    parts=[
                        common_pb2.MessagePart(text=prompt),
                        common_pb2.MessagePart(
                            image_uri=str(path),
                            media=common_pb2.MediaMetadata(
                                media_type=common_pb2.MEDIA_TYPE_IMAGE,
                                source_kind=common_pb2.MEDIA_SOURCE_URI,
                                filename=path.name,
                            ),
                        ),
                    ],
                )
            ]
        )

    request_a = build_request("Read this image.", image_a)
    request_b = build_request("Read this image.", image_a)
    request_c = build_request("Read this other image.", image_a)
    request_d = build_request("Read this image.", image_b)

    assert request_a.prompt_hash_hex == request_b.prompt_hash_hex
    assert request_a.images[0].sha256_hex == request_b.images[0].sha256_hex
    assert request_a.multimodal_hash_hex == request_b.multimodal_hash_hex
    assert request_a.multimodal_hash_hex != request_c.multimodal_hash_hex
    assert request_a.multimodal_hash_hex != request_d.multimodal_hash_hex


def test_prepare_vision_request_preserves_multi_image_order_in_payload_and_hash(tmp_path: Path) -> None:
    image_a = tmp_path / "image-a.txt"
    image_b = tmp_path / "image-b.txt"
    image_a.write_text("first image")
    image_b.write_text("second image")

    def build_request(images: list[Path]):
        return prepare_vision_request(
            [
                common_pb2.ChatMessage(
                    role="user",
                    parts=[
                        common_pb2.MessagePart(text="Compare the images."),
                        *[
                            common_pb2.MessagePart(
                                image_uri=str(path),
                                media=common_pb2.MediaMetadata(
                                    media_type=common_pb2.MEDIA_TYPE_IMAGE,
                                    source_kind=common_pb2.MEDIA_SOURCE_URI,
                                    filename=path.name,
                                ),
                            )
                            for path in images
                        ],
                    ],
                )
            ]
        )

    request_a = build_request([image_a, image_b])
    request_b = build_request([image_b, image_a])

    assert [image.filename for image in request_a.images] == [image_a.name, image_b.name]
    assert [image.filename for image in request_b.images] == [image_b.name, image_a.name]
    assert request_a.multimodal_hash_hex != request_b.multimodal_hash_hex


def test_prepare_vision_request_rejects_missing_remote_and_unsupported_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing_path = tmp_path / "missing-image.txt"

    with pytest.raises(MultimodalPreprocessError, match="Missing local image input"):
        prepare_vision_request(
            [
                common_pb2.ChatMessage(
                    role="user",
                    parts=[common_pb2.MessagePart(image_uri=str(missing_path))],
                )
            ]
        )

    def failing_urlopen(url: str, timeout: float = 5.0):
        raise URLError("unreachable")

    monkeypatch.setattr(multimodal_preprocessing, "urlopen", failing_urlopen)

    with pytest.raises(MultimodalPreprocessError, match="Remote image fetch failed"):
        prepare_vision_request(
            [
                common_pb2.ChatMessage(
                    role="user",
                    parts=[common_pb2.MessagePart(image_uri="https://example.com/cat.png")],
                )
            ]
        )

    with pytest.raises(MultimodalPreprocessError, match="Unsupported image URI scheme"):
        prepare_vision_request(
            [
                common_pb2.ChatMessage(
                    role="user",
                    parts=[common_pb2.MessagePart(image_uri="ftp://example.com/cat.png")],
                )
            ]
        )


def test_path_from_uri_preserves_direct_helper_behavior(tmp_path: Path) -> None:
    image_path = tmp_path / "direct-helper-image.txt"
    image_path.write_bytes(b"direct image bytes")

    assert _path_from_uri(str(image_path)) == image_path


def test_bytes_from_local_image_uri_reuses_single_parsed_uri(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image_path = tmp_path / "single-parse-image.txt"
    image_path.write_bytes(b"local image bytes")
    calls: list[str] = []
    original_urlparse = multimodal_preprocessing.urlparse

    def tracked_urlparse(uri: str):
        calls.append(uri)
        return original_urlparse(uri)

    monkeypatch.setattr(multimodal_preprocessing, "urlparse", tracked_urlparse)

    bytes_data, reference, mime_type, format_name, filename = _bytes_from_image_uri(image_path.as_uri())

    assert bytes_data == b"local image bytes"
    assert reference == image_path.as_uri()
    assert mime_type == ""
    assert format_name == "txt"
    assert filename == image_path.name
    assert calls == [image_path.as_uri()]


def test_prepare_image_part_rejects_parts_without_any_image_payload() -> None:
    with pytest.raises(MultimodalPreprocessError, match="No image input provided"):
        _prepare_image_part(common_pb2.MessagePart())


def test_ocr_and_vlm_runtimes_expose_probe_snapshots_after_cancelled_generation() -> None:
    messages = [
        common_pb2.ChatMessage(
            role="user",
            parts=[
                common_pb2.MessagePart(text="Inspect the image."),
                common_pb2.MessagePart(
                    image_bytes=b"cancelled vision input",
                    media=common_pb2.MediaMetadata(
                        media_type=common_pb2.MEDIA_TYPE_IMAGE,
                        source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                    ),
                ),
            ],
        )
    ]
    cancel_event = Event()
    cancel_event.set()

    ocr_runtime = DeterministicOCRRuntime()
    ocr_prepared = ocr_runtime.render_prompt(messages)
    assert list(ocr_runtime.generate_tokens({}, ocr_prepared, None, cancel_event)) == []
    ocr_probe = ocr_runtime.last_probe_snapshot()
    assert ocr_probe.preprocess_input_bytes == len(b"cancelled vision input")
    assert ocr_probe.first_token_latency_ms >= 0.0

    vlm_runtime = DeterministicVLMRuntime()
    vlm_prepared = vlm_runtime.render_prompt(messages)
    assert list(vlm_runtime.generate_tokens({}, vlm_prepared, None, cancel_event)) == []
    vlm_probe = vlm_runtime.last_probe_snapshot()
    assert vlm_probe.preprocess_input_bytes == len(b"cancelled vision input")
    assert vlm_probe.first_token_latency_ms >= 0.0
    assert vlm_probe.temp_media_artifact_count == 1
    assert vlm_probe.temp_media_artifact_bytes == len(b"cancelled vision input")
    assert vlm_probe.temp_media_cleanup_latency_ms >= 0.0
    assert vlm_probe.temp_media_cleanup_failure_count == 0


def test_ocr_runtime_render_prompt_accepts_chat_template_kwargs() -> None:
    runtime = DeterministicOCRRuntime()
    prepared = runtime.render_prompt(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Inspect the image."),
                    common_pb2.MessagePart(
                        image_bytes=b"ocr template kwargs",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                        ),
                    ),
                ],
            )
        ],
        template_kwargs={"continue_final_message": True},
    )

    assert prepared.prompt_text == "Inspect the image."
    assert prepared.images[0].decoded_text() == "ocr template kwargs"


def test_ocr_runtime_applies_model_aware_auto_prompt_when_metadata_is_present() -> None:
    runtime = DeterministicOCRRuntime()
    loaded_model = runtime.load_model(WorkerModelCatalog.dev_ocr_model())
    prepared = runtime.render_prompt(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(
                        image_bytes=b"ocr auto prompt",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                        ),
                    ),
                ],
            )
        ],
        loaded_model=loaded_model,
    )

    assert prepared.prompt_text == "OCR instruction: Extract the text from the image exactly as written."
    assert prepared.images[0].decoded_text() == "ocr auto prompt"


def test_ocr_runtime_rejects_multi_image_prompts() -> None:
    runtime = DeterministicOCRRuntime()

    with pytest.raises(MultimodalPreprocessError, match="OCR only supports single-image requests"):
        runtime.render_prompt(
            [
                common_pb2.ChatMessage(
                    role="user",
                    parts=[
                        common_pb2.MessagePart(text="Read both images."),
                        common_pb2.MessagePart(
                            image_bytes=b"first image",
                            media=common_pb2.MediaMetadata(
                                media_type=common_pb2.MEDIA_TYPE_IMAGE,
                                source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            ),
                        ),
                        common_pb2.MessagePart(
                            image_bytes=b"second image",
                            media=common_pb2.MediaMetadata(
                                media_type=common_pb2.MEDIA_TYPE_IMAGE,
                                source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            ),
                        ),
                    ],
                )
            ]
        )


def test_vlm_runtime_render_prompt_accepts_chat_template_kwargs() -> None:
    runtime = DeterministicVLMRuntime()
    loaded_model = runtime.load_model(WorkerModelCatalog.dev_vlm_model())
    prepared = runtime.render_prompt(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Describe the image."),
                    common_pb2.MessagePart(
                        image_bytes=b"vlm template kwargs",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                        ),
                    ),
                ],
            )
        ],
        loaded_model=loaded_model,
        template_kwargs={"continue_final_message": True},
    )

    assert prepared.prompt_text == "Describe the image."
    assert prepared.images[0].decoded_text() == "vlm template kwargs"


def test_vlm_runtime_reuses_cache_for_identical_multimodal_requests() -> None:
    runtime = DeterministicVLMRuntime()
    loaded_model = runtime.load_model(WorkerModelCatalog.dev_vlm_model())
    messages = [
        common_pb2.ChatMessage(
            role="user",
            parts=[
                common_pb2.MessagePart(text="Summarize the image."),
                common_pb2.MessagePart(
                    image_bytes=b"cacheable image payload",
                    media=common_pb2.MediaMetadata(
                        media_type=common_pb2.MEDIA_TYPE_IMAGE,
                        source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                    ),
                ),
            ],
        )
    ]

    first_prepared = runtime.render_prompt(messages, loaded_model=loaded_model)
    list(runtime.generate_tokens(loaded_model, first_prepared, None, Event()))
    first_probe = runtime.last_probe_snapshot()

    second_prepared = runtime.render_prompt(messages, loaded_model=loaded_model)
    list(runtime.generate_tokens(loaded_model, second_prepared, None, Event()))
    second_probe = runtime.last_probe_snapshot()
    cache_stats = runtime.cache_stats_response()

    assert first_probe.cache_hit is False
    assert second_probe.cache_hit is True
    assert second_probe.cache_identity == first_probe.cache_identity
    assert cache_stats.stats.l1_bytes > 0
    assert cache_stats.stats.block_count == 1
    assert cache_stats.stats.l1_hit_rate == 0.5
    assert cache_stats.snapshot.hot_prefixes[0].scope.model_id == "melix-dev-vlm"


def test_vlm_runtime_reuses_cached_snapshot_between_stats_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = DeterministicVLMRuntime()
    loaded_model = runtime.load_model(WorkerModelCatalog.dev_vlm_model())
    messages = [
        common_pb2.ChatMessage(
            role="user",
            parts=[
                common_pb2.MessagePart(text="Describe the image."),
                common_pb2.MessagePart(
                    image_bytes=b"cache snapshot reuse payload",
                    media=common_pb2.MediaMetadata(
                        media_type=common_pb2.MEDIA_TYPE_IMAGE,
                        source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                    ),
                ),
            ],
        )
    ]

    prepared = runtime.render_prompt(messages, loaded_model=loaded_model)
    list(runtime.generate_tokens(loaded_model, prepared, None, Event()))

    prefix_ref_calls = 0
    original_prefix_ref = common_pb2.PrefixRef

    def counting_prefix_ref(*args, **kwargs):
        nonlocal prefix_ref_calls
        prefix_ref_calls += 1
        return original_prefix_ref(*args, **kwargs)

    monkeypatch.setattr("worker.runtime.deterministic_vlm_runtime.common_pb2.PrefixRef", counting_prefix_ref)

    first_stats = runtime.cache_stats_response()
    second_stats = runtime.cache_stats_response()

    assert prefix_ref_calls == 1
    assert first_stats == second_stats
    assert second_stats.snapshot.hot_prefixes[0].scope.model_id == "melix-dev-vlm"


def test_vlm_runtime_plans_fast_path_when_generate_is_called_directly() -> None:
    runtime = DeterministicVLMRuntime()
    loaded_model = runtime.load_model(WorkerModelCatalog.dev_vlm_model())
    messages = [
        common_pb2.ChatMessage(
            role="user",
            parts=[
                common_pb2.MessagePart(text="Describe the image."),
                common_pb2.MessagePart(
                    image_bytes=b"direct deterministic fast path",
                    media=common_pb2.MediaMetadata(
                        media_type=common_pb2.MEDIA_TYPE_IMAGE,
                        source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                    ),
                ),
            ],
        )
    ]
    prepared = resolve_vision_family_config(loaded_model).shape_request(prepare_vision_request(messages))

    events = list(runtime.generate_tokens(loaded_model, prepared, None, Event()))
    probe = runtime.last_probe_snapshot()

    assert events[-1].text.startswith("Image content:")
    assert probe.image_feature_cache_hits == 0
    assert probe.image_feature_cache_misses == 1
    assert probe.multimodal_decode_mode == "native_quantized"
    assert probe.quantized_load_mode == "native_quantized"


def test_vlm_runtime_fast_path_signature_uses_nested_runtime_metadata() -> None:
    runtime = DeterministicVLMRuntime()
    loaded_model = runtime.load_model(WorkerModelCatalog.dev_vlm_model())
    loaded_model["metadata"] = {
        "vision_family_id": "paligemma-v1",
        "vision_prompt_profile_id": "paligemma-caption-v1",
        "vision_tokenization_mode": "prefix",
        "ignored": "not-part-of-signature",
    }
    prepared = prepare_vision_request(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Describe the image."),
                    common_pb2.MessagePart(
                        image_bytes=b"signature metadata image",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                        ),
                    ),
                ],
            )
        ]
    )

    signature = fast_path_probe_signature(loaded_model, prepared)

    assert "paligemma-v1" in signature[2]
    assert "paligemma-caption-v1" in signature[2]
    assert "ignored" not in signature[2]


def test_cache_service_reports_vlm_cache_state_after_generation() -> None:
    runtime_service, inference_service, _ = build_services()
    cache_service = WorkerCacheService(inference_service._registry)
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_vlm_model())

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="vlm-cache-service"),
            model_handle=model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Summarize the image."),
                    common_pb2.MessagePart(
                        image_bytes=b"cache service image",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                        ),
                    ),
                ],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=32),
        stream=True,
        return_usage=True,
    )

    list(inference_service.Generate(request, context=None))
    cache_stats = cache_service.GetCacheStats(cache_pb2.GetCacheStatsRequest(), context=None)

    assert cache_stats.stats.l1_bytes > 0
    assert cache_stats.snapshot.hot_prefixes


def test_cache_service_unimplemented_mutation_methods_return_structured_errors() -> None:
    runtime_service, inference_service, _ = build_services()
    cache_service = WorkerCacheService(inference_service._registry)
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_vlm_model())

    pin_response = cache_service.PinPrefix(cache_pb2.PinPrefixRequest(), context=None)
    unpin_response = cache_service.UnpinPrefix(cache_pb2.UnpinPrefixRequest(), context=None)
    save_response = cache_service.SaveBoundarySnapshot(
        cache_pb2.SaveBoundarySnapshotRequest(request_id="req", decode_handle=model_handle),
        context=None,
    )
    restore_response = cache_service.RestoreBoundarySnapshot(
        cache_pb2.RestoreBoundarySnapshotRequest(snapshot_id="snapshot-1"),
        context=None,
    )
    purge_response = cache_service.PurgeCache(cache_pb2.PurgeCacheRequest(), context=None)

    assert pin_response.ok is False
    assert pin_response.error.code == "unimplemented"
    assert unpin_response.ok is False
    assert unpin_response.error.code == "unimplemented"
    assert save_response.ok is False
    assert save_response.error.code == "unimplemented"
    assert restore_response.ok is False
    assert restore_response.error.code == "unimplemented"
    assert purge_response.ok is False
    assert purge_response.error.code == "unimplemented"
