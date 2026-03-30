from pathlib import Path
from threading import Event

import pytest

from packages.protocol.python.worker.v1 import cache_pb2, common_pb2, inference_pb2, maintenance_pb2, runtime_pb2

from worker.engine.maintenance_core import MaintenanceCore
from worker.grpc_server import WorkerCacheService, WorkerInferenceService, WorkerRuntimeService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime.deterministic_ocr_runtime import DeterministicOCRRuntime
from worker.runtime.deterministic_vlm_runtime import DeterministicVLMRuntime
from worker.runtime.mlx_text_runtime import MLXTextRuntime
from worker.runtime.multimodal_preprocessing import (
    MultimodalPreprocessError,
    _prepare_image_part,
    prepare_vision_request,
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


def test_prepare_vision_request_rejects_missing_and_non_file_inputs(tmp_path: Path) -> None:
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

    with pytest.raises(MultimodalPreprocessError, match="Unsupported image URI scheme"):
        prepare_vision_request(
            [
                common_pb2.ChatMessage(
                    role="user",
                    parts=[common_pb2.MessagePart(image_uri="https://example.com/cat.png")],
                )
            ]
        )


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
