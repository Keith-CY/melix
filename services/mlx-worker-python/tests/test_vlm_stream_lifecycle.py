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
from worker.runtime.temp_media_lifecycle import TempMediaSession


class PassiveTextBackend:
    runtime_name = "passive-text"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 1024


def build_services(vlm_runtime: DeterministicVLMRuntime | None = None):
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=PassiveTextBackend()),
        vlm_runtime=vlm_runtime,
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


def vlm_model(model_id: str) -> common_pb2.ModelSpec:
    model = WorkerModelCatalog.dev_vlm_model()
    model.model_id = model_id
    model.model_path = f"models/{model_id}"
    return model


def image_request(
    *,
    model_handle: str,
    request_id: str,
    payload: bytes = b"stream lifecycle reusable cache image",
    prompt: str = "Summarize the reusable image.",
    return_usage: bool = True,
) -> inference_pb2.GenerateRequest:
    return inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id=request_id),
            model_handle=model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text=prompt),
                    common_pb2.MessagePart(
                        image_bytes=payload,
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
        return_usage=return_usage,
    )


def completed_event(events: list[inference_pb2.ExecuteEvent]) -> inference_pb2.Completed:
    return next(event.completed for event in events if event.HasField("completed"))


def runtime_error_event(events: list[inference_pb2.ExecuteEvent]) -> inference_pb2.ErrorEvent:
    return next(event.error for event in events if event.HasField("error"))


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


def test_vlm_cache_hit_replay_uses_fresh_request_local_stream_boundary() -> None:
    runtime_service, inference_service, _ = build_services()
    runtime = inference_service._registry.vlm_runtime
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_vlm_model())

    first_events = list(
        inference_service.Generate(
            image_request(model_handle=model_handle, request_id="vlm-cache-boundary-first"),
            context=None,
        )
    )
    second_events = list(
        inference_service.Generate(
            image_request(model_handle=model_handle, request_id="vlm-cache-boundary-second"),
            context=None,
        )
    )

    first_completed = completed_event(first_events)
    second_completed = completed_event(second_events)
    first_seqs = [event.seq for event in first_events]
    second_seqs = [event.seq for event in second_events]

    assert first_events[0].request_id == "vlm-cache-boundary-first"
    assert second_events[0].request_id == "vlm-cache-boundary-second"
    assert first_seqs[0] == 1
    assert second_seqs[0] == 1
    assert first_completed.parser_metrics["response_id"] == "vlm-cache-boundary-first"
    assert second_completed.parser_metrics["response_id"] == "vlm-cache-boundary-second"
    assert first_completed.parser_metrics["stream_mode"] == "true"
    assert second_completed.parser_metrics["stream_mode"] == "true"
    assert first_completed.assistant_text == second_completed.assistant_text
    assert runtime.last_probe_snapshot().cache_hit is True


def test_vlm_model_switch_keeps_cache_scopes_isolated_until_each_unload() -> None:
    runtime_service, inference_service, _ = build_services()
    registry = inference_service._registry
    cache_service = WorkerCacheService(registry)
    first_handle = load_model(runtime_service, vlm_model("melix-test-vlm-switch-a"))
    second_handle = load_model(runtime_service, vlm_model("melix-test-vlm-switch-b"))

    list(
        inference_service.Generate(
            image_request(model_handle=first_handle, request_id="vlm-switch-a"),
            context=None,
        )
    )
    list(
        inference_service.Generate(
            image_request(model_handle=second_handle, request_id="vlm-switch-b"),
            context=None,
        )
    )
    switched_stats = cache_service.GetCacheStats(cache_pb2.GetCacheStatsRequest(), context=None)

    assert switched_stats.stats.block_count == 2
    assert {prefix.scope.model_id for prefix in switched_stats.snapshot.hot_prefixes} == {
        "melix-test-vlm-switch-a",
        "melix-test-vlm-switch-b",
    }
    assert registry.vlm_runtime.last_probe_snapshot().cache_hit is False

    unload_first = runtime_service.UnloadModel(
        runtime_pb2.UnloadModelRequest(model_handle=first_handle),
        context=None,
    )
    after_first_unload = cache_service.GetCacheStats(cache_pb2.GetCacheStatsRequest(), context=None)

    assert unload_first.ok is True
    assert after_first_unload.stats.block_count == 1
    assert [prefix.scope.model_id for prefix in after_first_unload.snapshot.hot_prefixes] == [
        "melix-test-vlm-switch-b"
    ]

    list(
        inference_service.Generate(
            image_request(model_handle=second_handle, request_id="vlm-switch-b-replay"),
            context=None,
        )
    )
    after_replay = cache_service.GetCacheStats(cache_pb2.GetCacheStatsRequest(), context=None)

    assert registry.vlm_runtime.last_probe_snapshot().cache_hit is True
    assert after_replay.stats.block_count == 1
    assert after_replay.stats.l1_hit_rate > 0.0


def test_vlm_warmup_wake_releases_stream_and_resume_uses_fresh_boundary() -> None:
    runtime_service, inference_service, _ = build_services()
    registry = inference_service._registry
    cache_service = WorkerCacheService(registry)
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_vlm_model())
    payload = b"warmup wake resume image"
    synthetic_messages = image_request(
        model_handle=model_handle,
        request_id="unused-warmup-request",
        payload=payload,
    ).messages

    warmup = runtime_service.WarmupModel(
        runtime_pb2.WarmupModelRequest(
            model_handle=model_handle,
            synthetic_messages=synthetic_messages,
        ),
        context=None,
    )
    after_warmup_stats = runtime_service.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), context=None).stats
    after_warmup_cache = cache_service.GetCacheStats(cache_pb2.GetCacheStatsRequest(), context=None)
    resumed_events = list(
        inference_service.Generate(
            image_request(
                model_handle=model_handle,
                request_id="vlm-warmup-resume",
                payload=payload,
            ),
            context=None,
        )
    )
    resumed_completed = completed_event(resumed_events)
    after_resume_stats = runtime_service.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), context=None).stats

    assert warmup.ok is True
    assert after_warmup_stats.active_requests == 0
    assert after_warmup_stats.active_multimodal_requests == 0
    assert after_warmup_cache.stats.block_count == 1
    assert resumed_events[0].seq == 1
    assert resumed_completed.parser_metrics["response_id"] == "vlm-warmup-resume"
    assert registry.vlm_runtime.last_probe_snapshot().cache_hit is True
    assert after_resume_stats.active_requests == 0
    assert after_resume_stats.active_multimodal_requests == 0


class StageThenFailTempMediaSession(TempMediaSession):
    def write_bytes(self, relative_name: str, payload: bytes) -> Path:
        path = super().write_bytes(relative_name, payload)
        raise OSError(f"staging failed after {path.name}")


def test_vlm_failed_generation_cleans_staged_temp_media_and_releases_stream(tmp_path: Path) -> None:
    sessions: list[StageThenFailTempMediaSession] = []

    def session_factory(**kwargs) -> StageThenFailTempMediaSession:
        session = StageThenFailTempMediaSession(**kwargs)
        sessions.append(session)
        return session

    runtime = DeterministicVLMRuntime(
        temp_root=tmp_path,
        temp_media_session_factory=session_factory,
    )
    runtime_service, inference_service, _ = build_services(vlm_runtime=runtime)
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_vlm_model())

    events = list(
        inference_service.Generate(
            image_request(model_handle=model_handle, request_id="vlm-staging-failure"),
            context=None,
        )
    )
    error = runtime_error_event(events).error
    stats = runtime_service.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), context=None).stats
    probe = runtime.last_probe_snapshot()

    assert error.code == "runtime_error"
    assert "staging failed after image-0.bin" in error.message
    assert sessions[0].session_root is not None
    assert not sessions[0].session_root.exists()
    assert probe.temp_media_artifact_count == 1
    assert probe.temp_media_artifact_bytes == len(b"stream lifecycle reusable cache image")
    assert probe.temp_media_cleanup_failure_count == 0
    assert stats.active_requests == 0
    assert stats.active_multimodal_requests == 0


def test_vlm_abort_cleans_temp_media_and_releases_request_state() -> None:
    runtime_service, inference_service, _ = build_services()
    registry = inference_service._registry
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_vlm_model())
    stream = inference_service.Generate(
        image_request(model_handle=model_handle, request_id="vlm-abort-cleanup"),
        context=None,
    )

    first_event = next(stream)
    abort = inference_service.Abort(
        inference_pb2.AbortRequest(request_id="vlm-abort-cleanup"),
        context=None,
    )
    remaining_events = list(stream)
    completed = completed_event(remaining_events)
    stats = runtime_service.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), context=None).stats
    probe = registry.vlm_runtime.last_probe_snapshot()

    assert first_event.HasField("token_delta")
    assert abort.ok is True
    assert completed.finish_reason == "cancelled"
    assert registry.get_request("vlm-abort-cleanup") is None
    assert stats.active_requests == 0
    assert stats.active_multimodal_requests == 0
    assert probe.temp_media_artifact_count == 1
    assert probe.temp_media_artifact_bytes == len(b"stream lifecycle reusable cache image")
    assert probe.temp_media_cleanup_failure_count == 0
