from __future__ import annotations

from pathlib import Path
from threading import Event

from packages.protocol.python.worker.v1 import cache_pb2, common_pb2, inference_pb2, runtime_pb2

from worker.engine.maintenance_core import MaintenanceCore
from worker.grpc_server import WorkerCacheService, WorkerInferenceService, WorkerRuntimeService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime.deterministic_vlm_runtime import DeterministicVLMRuntime
from worker.runtime.mlx_text_runtime import MLXTextRuntime


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


def test_vlm_runtime_close_loaded_model_clears_cache_by_model_scope() -> None:
    runtime = DeterministicVLMRuntime()
    loaded_model = runtime.load_model(WorkerModelCatalog.dev_vlm_model())
    messages = [
        common_pb2.ChatMessage(
            role="user",
            parts=[
                common_pb2.MessagePart(text="Summarize the image."),
                common_pb2.MessagePart(
                    image_bytes=b"close loaded model cache payload",
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

    assert runtime.cache_stats_response().stats.block_count == 1

    runtime.close_loaded_model({"model_id": "other-vlm"})

    assert runtime.cache_stats_response().stats.block_count == 1

    runtime.close_loaded_model({})
    cleared_stats = runtime.cache_stats_response().stats

    assert cleared_stats.block_count == 0
    assert cleared_stats.l1_bytes == 0


def test_vlm_stream_close_preserves_cache_until_explicit_unload() -> None:
    runtime_service, inference_service, _ = build_services()
    registry = inference_service._registry
    cache_service = WorkerCacheService(registry)
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_vlm_model())

    def image_request(request_id: str) -> inference_pb2.GenerateRequest:
        return inference_pb2.GenerateRequest(
            execution=inference_pb2.ExecutionMetadata(
                id=common_pb2.RequestIdentity(request_id=request_id),
                model_handle=model_handle,
            ),
            messages=[
                common_pb2.ChatMessage(
                    role="user",
                    parts=[
                        common_pb2.MessagePart(text="Summarize the reusable image."),
                        common_pb2.MessagePart(
                            image_bytes=b"stream finalizer reusable cache image",
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

    drained_events = list(inference_service.Generate(image_request("vlm-stream-drain"), context=None))
    after_drain = cache_service.GetCacheStats(cache_pb2.GetCacheStatsRequest(), context=None)

    assert drained_events[-1].HasField("completed")
    assert after_drain.stats.block_count == 1
    assert after_drain.stats.l1_bytes > 0

    list(inference_service.Generate(image_request("vlm-stream-cache-hit"), context=None))
    after_repeat = cache_service.GetCacheStats(cache_pb2.GetCacheStatsRequest(), context=None)

    assert after_repeat.stats.block_count == 1
    assert after_repeat.stats.l1_hit_rate > 0.0

    early_stream = inference_service.Generate(image_request("vlm-stream-early-close"), context=None)
    first_event = next(early_stream)
    early_stream.close()
    after_early_close = cache_service.GetCacheStats(cache_pb2.GetCacheStatsRequest(), context=None)
    runtime_stats = runtime_service.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), context=None).stats

    assert first_event.HasField("token_delta")
    assert registry.get_request("vlm-stream-early-close") is None
    assert runtime_stats.active_requests == 0
    assert runtime_stats.active_multimodal_requests == 0
    assert after_early_close.stats.block_count == 1
    assert after_early_close.stats.l1_bytes == after_repeat.stats.l1_bytes

    unload = runtime_service.UnloadModel(
        runtime_pb2.UnloadModelRequest(model_handle=model_handle),
        context=None,
    )
    receipt = registry.pending_unload_receipt(model_handle)
    after_unload = cache_service.GetCacheStats(cache_pb2.GetCacheStatsRequest(), context=None)

    assert unload.ok is True
    assert receipt is not None
    assert receipt.unloaded is True
    assert receipt.pending_unload is False
    assert receipt.unloaded_at
    assert after_unload.stats.block_count == 0
    assert after_unload.stats.l1_bytes == 0
