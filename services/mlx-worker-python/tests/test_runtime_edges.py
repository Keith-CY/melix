from __future__ import annotations

import json
import os
import runpy
from argparse import Namespace
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, maintenance_pb2, runtime_pb2

from worker.grpc_server import (
    BootstrapMetricsExporter,
    WorkerInferenceService,
    WorkerMaintenanceService,
    WorkerRuntimeService,
    _deterministic_benchmark_fetch_json,
    _default_melix_home,
    _elapsed_milliseconds_from_origin,
    _elapsed_milliseconds_since,
    build_maintenance_service,
    build_registry_for_backend,
    build_server,
    main,
)
from worker.model_ops.deterministic_lora_runner import DeterministicLoRARunner
from worker.model_ops.mlx_lm_runner import ActivationRequest, TrainingRequest
from worker.model_ops.training_config import LoRATrainingConfig
from worker.model_registry.catalog import WorkerModelCatalog
from worker.productization.benchmark_suites import BenchmarkSuiteCatalog
from worker.registry import LoadedModel, MemoryBudgetExceeded, WorkerRegistry
from worker.runtime.audio_runtime_protocols import AudioBackendUnavailableError
from worker.runtime.deterministic_delay import configured_delay_ms
from worker.runtime.mlx_text_runtime import AutoMLXBackend, MLXTextRuntime, RuntimeUnavailableError


class FakeBackend:
    runtime_name = "fake-mlx"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id, "model_path": model_spec.model_path}

    def estimate_resident_bytes(self, model_spec):
        return 4096

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
        if prompt == "explode":
            raise RuntimeError("backend exploded")
        yield "token-1"
        if cancel_event.is_set():
            return
        yield "token-2"


class FailingBackend(FakeBackend):
    def load_model(self, model_spec):
        raise RuntimeError("cannot load model")


class StubAudioRuntime:
    def __init__(self, runtime_name: str):
        self.runtime_name = runtime_name

    def load_model(self, model_spec):
        return {"runtime_name": self.runtime_name, "model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 2048


class UnavailableAudioRuntime(StubAudioRuntime):
    def load_model(self, model_spec):
        raise AudioBackendUnavailableError("mlx-audio speech backend is unavailable")


class FailingAudioRuntime(StubAudioRuntime):
    def load_model(self, model_spec):
        raise RuntimeError("mlx-audio speech backend failed to load model")


class FakeBenchmarkHFDatasetFetcher:
    def __call__(self, endpoint: str, params: dict[str, str]) -> dict[str, object]:
        dataset = params.get("dataset", "")
        offset = params.get("offset", "0")
        if endpoint == "rows" and offset != "0":
            return {"rows": []}

        if dataset == "HuggingFaceH4/ultrachat_200k":
            if endpoint == "rows":
                return {
                    "rows": [
                        {
                            "row": {
                                "messages": [
                                    {"role": "user", "content": "Say hi."},
                                    {"role": "assistant", "content": "Hi."},
                                ]
                            }
                        },
                        {
                            "row": {
                                "messages": [
                                    {"role": "user", "content": "Say bye."},
                                    {"role": "assistant", "content": "Bye."},
                                ]
                            }
                        },
                    ]
                }
            return {"splits": [{"dataset": dataset, "config": "default", "split": "train_sft"}]}

        if dataset == "databricks/databricks-dolly-15k":
            if endpoint == "rows":
                return {
                    "rows": [
                        {"row": {"instruction": "List two colors.", "response": "Red and blue."}},
                        {"row": {"instruction": "List two animals.", "response": "Cat and dog."}},
                    ]
                }
            return {"splits": [{"dataset": dataset, "config": "default", "split": "train"}]}

        raise AssertionError(f"Unexpected benchmark fetch: endpoint={endpoint} dataset={dataset}")


def test_fake_benchmark_hf_dataset_fetcher_covers_supported_and_error_paths() -> None:
    fetcher = FakeBenchmarkHFDatasetFetcher()

    assert fetcher("rows", {"dataset": "HuggingFaceH4/ultrachat_200k", "offset": "1"}) == {"rows": []}
    assert fetcher("splits", {"dataset": "HuggingFaceH4/ultrachat_200k"}) == {
        "splits": [
            {
                "dataset": "HuggingFaceH4/ultrachat_200k",
                "config": "default",
                "split": "train_sft",
            }
        ]
    }
    assert fetcher("splits", {"dataset": "databricks/databricks-dolly-15k"}) == {
        "splits": [
            {
                "dataset": "databricks/databricks-dolly-15k",
                "config": "default",
                "split": "train",
            }
        ]
    }

    with pytest.raises(AssertionError, match="Unexpected benchmark fetch"):
        fetcher("splits", {"dataset": "unknown/dataset"})


def build_registry(
    backend=None,
    process_memory_budget_bytes: int = 0,
    memory_headroom_bytes: int = 0,
) -> WorkerRegistry:
    return WorkerRegistry(
        runtime=MLXTextRuntime(backend=backend or FakeBackend()),
        model_catalog=WorkerModelCatalog(),
        process_memory_budget_bytes=process_memory_budget_bytes,
        memory_headroom_bytes=memory_headroom_bytes,
    )


def build_services(backend=None):
    registry = build_registry(backend=backend)
    return registry, WorkerRuntimeService(registry), WorkerInferenceService(registry)


def test_worker_registry_multimodal_request_kind_uses_expected_membership() -> None:
    multimodal_kinds = ("ocr", "vlm", "transcription", "speech", "image")
    non_multimodal_kinds = ("text", "embedding", "rerank", "", "unknown")

    for runtime_kind in multimodal_kinds:
        assert WorkerRegistry._is_multimodal_request_kind(runtime_kind) is True

    for runtime_kind in non_multimodal_kinds:
        assert WorkerRegistry._is_multimodal_request_kind(runtime_kind) is False


def test_worker_registry_sparse_model_request_fast_path_preserves_semantics() -> None:
    sparse = common_pb2.ModelSpec(model_id="melix-dev-text")
    empty = common_pb2.ModelSpec()
    full = WorkerModelCatalog.dev_text_model()
    with_path = common_pb2.ModelSpec(model_id="melix-dev-text", model_path="/models/dev")

    assert WorkerRegistry._is_sparse_model_request(sparse) is True
    assert WorkerRegistry._is_sparse_model_request(empty) is True
    assert WorkerRegistry._is_sparse_model_request(full) is False
    assert WorkerRegistry._is_sparse_model_request(with_path) is False

    non_sparse_variants = [
        common_pb2.ModelSpec(model_id="melix-dev-text", model_kind="text"),
        common_pb2.ModelSpec(model_id="melix-dev-text", revision="main"),
        common_pb2.ModelSpec(model_id="melix-dev-text", tokenizer_hash="tok"),
        common_pb2.ModelSpec(model_id="melix-dev-text", quant_profile_id="q4"),
        common_pb2.ModelSpec(model_id="melix-dev-text", parser_mode="json"),
        common_pb2.ModelSpec(model_id="melix-dev-text", reasoning_mode="off"),
        common_pb2.ModelSpec(model_id="melix-dev-text", max_context=4096),
        common_pb2.ModelSpec(model_id="melix-dev-text", ext={"k": "v"}),
        common_pb2.ModelSpec(
            model_id="melix-dev-text",
            capability_class=common_pb2.MODEL_CAPABILITY_TEXT,
        ),
        common_pb2.ModelSpec(
            model_id="melix-dev-text",
            route_class=common_pb2.WORKER_ROUTE_SWIFT_TEXT,
        ),
        common_pb2.ModelSpec(
            model_id="melix-dev-text",
            settings=common_pb2.ModelSettings(pin_on_load=True),
        ),
        common_pb2.ModelSpec(model_id="melix-dev-text", features=["chat"]),
        common_pb2.ModelSpec(
            model_id="melix-dev-text",
            runtime_mode=common_pb2.RUNTIME_MODE_FUSED_DERIVED_MODEL,
        ),
    ]
    assert all(not WorkerRegistry._is_sparse_model_request(variant) for variant in non_sparse_variants)

    registry = build_registry()
    loaded = registry.load_model(sparse)

    assert loaded.spec.model_id == "melix-dev-text"
    assert loaded.spec.model_path == WorkerModelCatalog.dev_text_model().model_path
    assert loaded.runtime_model["model_path"] == WorkerModelCatalog.dev_text_model().model_path


def load_default_model(runtime_service: WorkerRuntimeService) -> str:
    response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )
    assert response.ok is True
    return response.model_handle


def test_runtime_service_handles_failures_and_state_transitions() -> None:
    failing_registry, failing_runtime_service, _ = build_services(backend=FailingBackend())
    _ = failing_registry

    failed = failing_runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )
    assert failed.ok is False
    assert failed.error.code == "load_failed"

    registry, runtime_service, _ = build_services()
    model_handle = load_default_model(runtime_service)

    stats = runtime_service.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), context=None)
    assert stats.stats.worker_state == "idle"
    assert stats.stats.resident_bytes == 4096
    assert stats.stats.model_resident_bytes == 4096
    assert stats.stats.cache_resident_bytes == 0
    assert stats.stats.kv_cache_bytes == 0
    assert stats.stats.peak_allocation_bytes == 0
    assert stats.stats.memory_headroom_bytes == 0

    drained = runtime_service.Drain(
        runtime_pb2.DrainRequest(stop_accepting_new=True),
        context=None,
    )
    assert drained.ok is True
    draining_stats = runtime_service.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), context=None)
    assert draining_stats.stats.worker_state == "draining"

    found = runtime_service.UnloadModel(
        runtime_pb2.UnloadModelRequest(model_handle=model_handle),
        context=None,
    )
    missing = runtime_service.UnloadModel(
        runtime_pb2.UnloadModelRequest(model_handle="missing-handle"),
        context=None,
    )
    warmup = runtime_service.WarmupModel(
        runtime_pb2.WarmupModelRequest(model_handle=model_handle),
        context=None,
    )
    shutdown = runtime_service.Shutdown(
        runtime_pb2.ShutdownRequest(flush_l2=True),
        context=None,
    )

    assert found.ok is True
    assert missing.ok is False
    assert missing.error.code == "not_found"
    assert warmup.ok is False
    assert warmup.error.code == "not_found"
    assert shutdown.ok is True
    assert registry.list_loaded_models() == []


def test_runtime_service_rejects_model_loads_that_exceed_process_budget_and_reports_headroom() -> None:
    registry = build_registry(
        process_memory_budget_bytes=4_500,
        memory_headroom_bytes=1_024,
    )
    runtime_service = WorkerRuntimeService(registry)

    rejected = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )

    assert rejected.ok is False
    assert rejected.error.code == "memory_budget_exceeded"
    assert rejected.error.message == "Projected resident memory would exceed the process budget."
    assert rejected.error.details == {
        "budget_bytes": "4500",
        "headroom_bytes": "1024",
        "projected_resident_bytes": "4096",
        "required_bytes": "5120",
    }
    assert registry.list_loaded_models() == []

    stats = runtime_service.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), context=None)
    assert stats.stats.memory_headroom_bytes == 1024
    assert stats.stats.resident_bytes == 0


def test_worker_registry_reserves_resident_bytes_across_concurrent_loads() -> None:
    class BlockingBackend(FakeBackend):
        def __init__(self) -> None:
            self.started = Event()
            self.release = Event()

        def load_model(self, model_spec):
            self.started.set()
            self.release.wait(timeout=5)
            return super().load_model(model_spec)

    backend = BlockingBackend()
    registry = build_registry(
        backend=backend,
        process_memory_budget_bytes=9_000,
        memory_headroom_bytes=1_000,
    )
    results: list[object] = [None]

    def load_first() -> None:
        results[0] = registry.load_model(WorkerModelCatalog.dev_text_model())

    first_thread = Thread(target=load_first)
    first_thread.start()
    assert backend.started.wait(timeout=5) is True

    with pytest.raises(MemoryBudgetExceeded) as excinfo:
        registry.load_model(WorkerModelCatalog.dev_text_model())

    backend.release.set()
    first_thread.join(timeout=5)

    first = results[0]
    assert isinstance(first, LoadedModel)
    assert excinfo.value.projected_resident_bytes == 8_192
    assert excinfo.value.required_bytes == 9_192
    stats = registry.runtime_stats()
    assert stats.model_resident_bytes == 4_096
    assert registry._reserved_model_resident_bytes == 0
    assert registry.unload_model(first.handle) is True



def test_worker_registry_releases_reserved_bytes_when_load_fails() -> None:
    registry = build_registry(backend=FailingBackend())

    with pytest.raises(RuntimeError, match="cannot load model"):
        registry.load_model(WorkerModelCatalog.dev_text_model())

    assert registry._reserved_model_resident_bytes == 0
    assert registry.runtime_stats().model_resident_bytes == 0
    assert registry.list_loaded_models() == []



def test_worker_registry_avoids_rescanning_loaded_models_for_resident_bytes() -> None:
    registry = build_registry()
    first = registry.load_model(WorkerModelCatalog.dev_text_model())

    class ValuesFailDict(dict):
        def values(self):
            raise AssertionError("loaded model resident bytes should not rescan dict values")

    registry._loaded_models = ValuesFailDict(registry._loaded_models)

    second = registry.load_model(WorkerModelCatalog.dev_text_model())
    stats = registry.runtime_stats()

    assert second.handle != first.handle
    assert stats.model_resident_bytes == first.estimated_resident_bytes + second.estimated_resident_bytes
    assert registry.unload_model(first.handle) is True
    assert registry.unload_model(second.handle) is True
    assert registry.unload_model("missing-handle") is False
    assert registry.runtime_stats().model_resident_bytes == 0



def test_worker_registry_reuses_sorted_handles_across_listing_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = build_registry()
    for _ in range(3):
        registry.load_model(WorkerModelCatalog.dev_text_model())

    sorted_calls = 0
    original_sorted = sorted

    def tracked_sorted(*args, **kwargs):
        nonlocal sorted_calls
        sorted_calls += 1
        return original_sorted(*args, **kwargs)

    monkeypatch.setattr("builtins.sorted", tracked_sorted)

    handles = registry.list_loaded_models()
    summaries = registry.list_loaded_model_summaries()
    repeated_handles = registry.list_loaded_models()

    assert repeated_handles == handles
    assert [summary.model_handle for summary in summaries] == handles
    assert sorted_calls == 1

    registry.unload_model(handles[0])
    invalidated_handles = registry.list_loaded_models()

    assert len(invalidated_handles) == 2
    assert sorted_calls == 2



def test_registry_capabilities_and_request_lifecycle() -> None:
    registry = build_registry()

    capabilities = registry.capabilities()
    assert capabilities.cache.supports_prefix_cache is True
    assert capabilities.cache.kv_quant_profiles == ["q4"]
    assert capabilities.execution.supports_continuous_batching is False
    assert capabilities.execution.supports_disk_streaming is False

    state = registry.start_request("req-1")
    assert registry.get_request("req-1") is state
    assert registry.abort_request("req-1") is True
    assert state.cancel_event.is_set() is True
    assert registry.abort_request("missing") is False

    registry.finish_request("req-1")
    assert registry.get_request("req-1") is None

    vision_state = registry.start_request("req-vision", runtime_kind="ocr")
    transcription_state = registry.start_request("req-transcription", runtime_kind="transcription")
    speech_state = registry.start_request("req-speech", runtime_kind="speech")
    registry.set_request_phase("req-vision", "prefill")
    registry.set_request_phase("req-transcription", "decode")
    registry.set_request_phase("missing", "prefill")
    assert vision_state.runtime_kind == "ocr"
    assert transcription_state.runtime_kind == "transcription"
    assert speech_state.runtime_kind == "speech"

    registry.record_vision_probe(
        "ocr",
        SimpleNamespace(
            preprocess_latency_ms=12.0,
            preprocess_input_bytes=64,
            preprocess_peak_memory_bytes=2048,
            first_token_latency_ms=5.0,
            temp_media_artifact_count=2,
            temp_media_artifact_bytes=96,
            temp_media_cleanup_latency_ms=1.25,
            temp_media_cleanup_failure_count=1,
        ),
    )
    vision_stats = registry.runtime_stats()
    assert vision_stats.active_requests == 3
    assert vision_stats.active_prefills == 1
    assert vision_stats.active_decodes == 1
    assert vision_stats.active_multimodal_requests == 3
    assert vision_stats.last_probe_kind == "ocr"
    assert vision_stats.last_preprocess_latency_ms == 12.0
    assert vision_stats.last_preprocess_input_bytes == 64
    assert vision_stats.last_preprocess_peak_memory_bytes == 2048
    assert vision_stats.last_first_token_latency_ms == 5.0
    assert vision_stats.last_temp_media_artifact_count == 2
    assert vision_stats.last_temp_media_artifact_bytes == 96
    assert vision_stats.last_temp_media_cleanup_latency_ms == 1.25
    assert vision_stats.last_temp_media_cleanup_failure_count == 1

    registry.record_transcription_probe(
        SimpleNamespace(
            preprocess_latency_ms=18.0,
            preprocess_input_bytes=96,
            preprocess_peak_memory_bytes=4096,
            transcription_latency_ms=9.0,
            estimated_duration_seconds=0.75,
            chunk_count=4,
        )
    )
    transcription_stats = registry.runtime_stats()
    assert transcription_stats.last_probe_kind == "transcription"
    assert transcription_stats.last_transcription_latency_ms == 9.0
    assert transcription_stats.last_audio_duration_seconds == 0.75
    assert transcription_stats.last_audio_chunk_count == 4
    assert transcription_stats.last_temp_media_artifact_count == 0
    assert transcription_stats.last_temp_media_cleanup_failure_count == 0

    registry.record_speech_probe(
        SimpleNamespace(
            speech_latency_ms=7.5,
            output_bytes=128,
        )
    )
    speech_stats = registry.runtime_stats()
    assert speech_stats.last_probe_kind == "speech"
    assert speech_stats.last_speech_latency_ms == 7.5
    assert speech_stats.last_audio_output_bytes == 128
    assert speech_stats.last_image_job_latency_ms == 0.0
    assert speech_stats.last_temp_media_artifact_count == 0

    registry.record_image_probe(
        SimpleNamespace(
            job_latency_ms=42.5,
            artifact_publish_ms=3.25,
            output_bytes=512,
            peak_memory_bytes=40960,
        )
    )
    image_stats = registry.runtime_stats()
    assert image_stats.last_probe_kind == "image"
    assert image_stats.last_image_job_latency_ms == 42.5
    assert image_stats.last_image_artifact_publish_ms == 3.25
    assert image_stats.last_image_output_bytes == 512
    assert image_stats.last_image_peak_memory_bytes == 40960
    assert image_stats.last_temp_media_artifact_count == 0
    assert image_stats.model_resident_bytes == 0
    assert image_stats.cache_resident_bytes == 0
    assert image_stats.kv_cache_bytes == 0

    registry.finish_request("req-vision")
    registry.finish_request("req-transcription")
    registry.finish_request("req-speech")
    assert registry.runtime_stats().active_multimodal_requests == 0


def test_runtime_stats_request_counters_stay_consistent_without_request_scan() -> None:
    registry = build_registry()

    registry.start_request("req-reused", runtime_kind="ocr")
    registry.set_request_phase("req-reused", "prefill")
    registry.start_request("req-reused", runtime_kind="text")
    registry.set_request_phase("req-reused", "decode")
    registry.start_request("req-image", runtime_kind="image")

    stats = registry.runtime_stats()
    assert stats.active_requests == 2
    assert stats.active_prefills == 0
    assert stats.active_decodes == 1
    assert stats.active_multimodal_requests == 1

    registry.finish_request("req-reused")
    registry.finish_request("missing")
    stats = registry.runtime_stats()
    assert stats.active_requests == 1
    assert stats.active_prefills == 0
    assert stats.active_decodes == 0
    assert stats.active_multimodal_requests == 1

    registry.finish_request("req-image")
    stats = registry.runtime_stats()
    assert stats.active_requests == 0
    assert stats.active_prefills == 0
    assert stats.active_decodes == 0
    assert stats.active_multimodal_requests == 0


def test_audio_runtime_selection_uses_backend_metadata_and_rejects_missing_backend_configuration() -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=FakeBackend()),
        transcription_runtime=StubAudioRuntime("deterministic-transcription"),
        speech_runtime=StubAudioRuntime("deterministic-speech"),
        mlx_audio_transcription_runtime=StubAudioRuntime("mlx-audio-stt"),
        mlx_audio_speech_runtime=StubAudioRuntime("mlx-audio-tts"),
        model_catalog=WorkerModelCatalog(),
    )

    _, deterministic_transcription = registry._runtime_for_model(WorkerModelCatalog.dev_transcription_model())
    _, deterministic_speech = registry._runtime_for_model(WorkerModelCatalog.dev_speech_model())
    _, whisper = registry._runtime_for_model(WorkerModelCatalog.mlx_whisper_model())
    _, parakeet = registry._runtime_for_model(WorkerModelCatalog.mlx_parakeet_model())
    _, kokoro = registry._runtime_for_model(WorkerModelCatalog.mlx_kokoro_model())
    _, qwen3_tts = registry._runtime_for_model(WorkerModelCatalog.mlx_qwen3_tts_model())

    missing_backend = common_pb2.ModelSpec(
        model_id="missing-audio-backend",
        model_path="models/missing-audio-backend",
        model_kind="speech",
    )

    assert deterministic_transcription.runtime_name == "deterministic-transcription"
    assert deterministic_speech.runtime_name == "deterministic-speech"
    assert whisper.runtime_name == "mlx-audio-stt"
    assert parakeet.runtime_name == "mlx-audio-stt"
    assert kokoro.runtime_name == "mlx-audio-tts"
    assert qwen3_tts.runtime_name == "mlx-audio-tts"

    with pytest.raises(RuntimeError, match="requires an explicit melix.audio.backend_id"):
        registry._runtime_for_model(missing_backend)


def test_registry_runtime_stats_include_vlm_cache_bytes_after_generation() -> None:
    registry, runtime_service, inference_service = build_services()
    load_response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_vlm_model()),
        context=None,
    )
    assert load_response.ok is True

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-vlm-cache"),
            model_handle=load_response.model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Summarize the image."),
                    common_pb2.MessagePart(
                        image_bytes=b"runtime-cache-image",
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

    list(inference_service.Generate(request, context=None))

    cache_stats = registry.cache_stats_response()
    runtime_stats = registry.runtime_stats()

    assert cache_stats.stats.l1_bytes > 0
    assert runtime_stats.l1_cache_bytes == cache_stats.stats.l1_bytes
    assert runtime_stats.cache_resident_bytes == cache_stats.stats.l1_bytes
    assert runtime_stats.l1_hit_rate == cache_stats.stats.l1_hit_rate


def test_registry_runtime_stats_include_audio_load_and_fallback_probes() -> None:
    registry = build_registry()

    registry.record_audio_model_load_probe(12.5)
    registry.increment_audio_backend_unavailable()
    registry.record_transcription_probe(
        SimpleNamespace(
            preprocess_latency_ms=18.0,
            preprocess_input_bytes=96,
            preprocess_peak_memory_bytes=4096,
            transcription_latency_ms=9.0,
            estimated_duration_seconds=0.75,
            chunk_count=4,
            language_fallback_count=2,
        )
    )
    registry.record_speech_probe(
        SimpleNamespace(
            speech_latency_ms=7.5,
            output_bytes=128,
            voice_fallback_count=1,
        )
    )

    stats = registry.runtime_stats()

    assert stats.last_audio_model_load_latency_ms == 12.5
    assert stats.last_audio_backend_unavailable_count == 1
    assert stats.last_voice_fallback_count == 1
    assert stats.last_language_fallback_count == 2


def test_runtime_service_maps_real_audio_load_failures_to_unavailable_and_runtime_error() -> None:
    unavailable_registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=FakeBackend()),
        transcription_runtime=StubAudioRuntime("deterministic-transcription"),
        speech_runtime=StubAudioRuntime("deterministic-speech"),
        mlx_audio_transcription_runtime=StubAudioRuntime("mlx-audio-stt"),
        mlx_audio_speech_runtime=UnavailableAudioRuntime("mlx-audio-tts"),
        model_catalog=WorkerModelCatalog(),
    )
    unavailable_service = WorkerRuntimeService(unavailable_registry)
    unavailable = unavailable_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.mlx_kokoro_model()),
        context=None,
    )

    assert unavailable.ok is False
    assert unavailable.error.code == "unavailable"
    assert "unavailable" in unavailable.error.message
    assert unavailable_service.GetRuntimeStats(
        runtime_pb2.GetRuntimeStatsRequest(),
        context=None,
    ).stats.last_audio_backend_unavailable_count == 1

    failing_registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=FakeBackend()),
        transcription_runtime=StubAudioRuntime("deterministic-transcription"),
        speech_runtime=StubAudioRuntime("deterministic-speech"),
        mlx_audio_transcription_runtime=StubAudioRuntime("mlx-audio-stt"),
        mlx_audio_speech_runtime=FailingAudioRuntime("mlx-audio-tts"),
        model_catalog=WorkerModelCatalog(),
    )
    failing_service = WorkerRuntimeService(failing_registry)
    failed = failing_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.mlx_kokoro_model()),
        context=None,
    )

    assert failed.ok is False
    assert failed.error.code == "runtime_error"
    assert "failed to load model" in failed.error.message


def test_deterministic_multimodal_delay_prefers_specific_keys_and_shared_fallback() -> None:
    assert configured_delay_ms("transcription", {}) == 0.0
    assert configured_delay_ms("transcription", {"MELIX_DETERMINISTIC_MULTIMODAL_DELAY_MS": "25"}) == 25.0
    assert configured_delay_ms(
        "transcription",
        {
            "MELIX_DETERMINISTIC_MULTIMODAL_DELAY_MS": "25",
            "MELIX_DETERMINISTIC_TRANSCRIPTION_DELAY_MS": "150",
        },
    ) == 150.0
    assert configured_delay_ms("ocr", {"MELIX_DETERMINISTIC_OCR_DELAY_MS": "invalid"}) == 0.0


def test_runtime_wrapper_and_unavailable_backend_paths() -> None:
    runtime = MLXTextRuntime(backend=FakeBackend())
    prompt = runtime.render_prompt(
        [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="hello"),
                    common_pb2.MessagePart(image_uri="file://ignored"),
                ],
            ),
            common_pb2.ChatMessage(
                role="assistant",
                parts=[common_pb2.MessagePart(text="world")],
            ),
        ]
    )

    assert runtime.runtime_name == "fake-mlx"
    assert prompt == "hello\nworld"
    assert runtime.estimate_resident_bytes(WorkerModelCatalog.dev_text_model()) == 4096

    unavailable = AutoMLXBackend()
    assert unavailable.estimate_resident_bytes(WorkerModelCatalog.dev_text_model()) == 0
    if unavailable.runtime_name == "mlx-unavailable":
        with pytest.raises(RuntimeUnavailableError):
            unavailable.load_model(WorkerModelCatalog.dev_text_model())
        with pytest.raises(RuntimeUnavailableError):
            list(
                unavailable.generate_tokens(
                    {},
                    "prompt",
                    common_pb2.SamplingConfig(),
                    Event(),
                )
            )


def test_inference_service_covers_error_and_unimplemented_paths() -> None:
    _, runtime_service, inference_service = build_services()
    model_handle = load_default_model(runtime_service)

    missing_model_events = list(
        inference_service.Generate(
            inference_pb2.GenerateRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id="req-missing-model"),
                    model_handle="missing-handle",
                )
            ),
            context=None,
        )
    )
    assert missing_model_events[0].error.error.code == "not_found"

    runtime_error_events = list(
        inference_service.Generate(
            inference_pb2.GenerateRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id="req-runtime-error"),
                    model_handle=model_handle,
                ),
                messages=[
                    common_pb2.ChatMessage(
                        role="user",
                        parts=[common_pb2.MessagePart(text="explode")],
                    )
                ],
                sampling=common_pb2.SamplingConfig(max_output_tokens=4),
            ),
            context=None,
        )
    )
    assert runtime_error_events[-1].error.error.code == "runtime_error"

    decode_events = list(
        inference_service.Decode(
            inference_pb2.DecodeRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id="req-decode"),
                    model_handle=model_handle,
                )
            ),
            context=None,
        )
    )
    assert decode_events[0].error.error.code == "unimplemented"

    abort_response = inference_service.Abort(
        inference_pb2.AbortRequest(request_id="missing-request"),
        context=None,
    )
    assert abort_response.ok is False
    assert abort_response.found is False

    embed_model = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_embedding_model()),
        context=None,
    )
    assert embed_model.ok is True

    embed = inference_service.Embed(
        inference_pb2.EmbedRequest(
            id=common_pb2.RequestIdentity(request_id="req-embed"),
            model_handle=embed_model.model_handle,
            inputs=["one", "two"],
        ),
        context=None,
    )
    rerank_model = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_rerank_model()),
        context=None,
    )
    assert rerank_model.ok is True

    rerank = inference_service.Rerank(
        inference_pb2.RerankRequest(
            id=common_pb2.RequestIdentity(request_id="req-rerank"),
            model_handle=rerank_model.model_handle,
            query="swift runtime worker",
            documents=["swift runtime worker", "image generation", "embedding vector"],
            top_k=2,
        ),
        context=None,
    )
    transcribe = inference_service.Transcribe(inference_pb2.TranscribeRequest(), context=None)
    speak = inference_service.Speak(inference_pb2.SpeakRequest(), context=None)
    image_generate = inference_service.ImageGenerate(inference_pb2.ImageGenerateRequest(), context=None)
    image_edit = inference_service.ImageEdit(inference_pb2.ImageEditRequest(), context=None)

    assert embed.error.code == ""
    assert len(embed.embeddings) == 2
    assert rerank.error.code == ""
    assert len(rerank.items) == 2
    assert transcribe.error.code == "not_found"
    assert speak.error.code == "not_found"
    assert image_generate.error.code == "not_found"
    assert image_edit.error.code == "not_found"
    assert image_generate.job.state == common_pb2.IMAGE_JOB_FAILED
    assert image_generate.job.operation == "image_generate"
    assert image_edit.job.state == common_pb2.IMAGE_JOB_FAILED
    assert image_edit.job.operation == "image_edit"


def test_build_server_and_main_bootstrap(monkeypatch, tmp_path: Path) -> None:
    registry = build_registry()
    seen_build = {}
    maintenance_method_count = len(
        maintenance_pb2.DESCRIPTOR.services_by_name["MaintenanceService"].methods
    )

    class FakeBoundServer:
        def add_generic_rpc_handlers(self, handlers) -> None:
            seen_build["handlers"] = seen_build.get("handlers", 0) + len(handlers)

        def add_registered_method_handlers(self, service_name, handlers) -> None:
            services = seen_build.setdefault("registered_services", [])
            services.append((service_name, len(handlers)))

        def add_insecure_port(self, address: str) -> int:
            seen_build["address"] = address
            return 1

        def stop(self, grace: int) -> None:
            seen_build["stopped"] = grace

    monkeypatch.setattr("worker.grpc_server.grpc.server", lambda executor: FakeBoundServer())
    metrics_path = tmp_path / "python-worker-metrics.json"
    exporter = BootstrapMetricsExporter(str(metrics_path))
    server, runtime_service, inference_service = build_server(
        "/tmp/melix-test.sock",
        registry=registry,
        metrics_exporter=exporter,
    )
    server.stop(0)

    assert isinstance(runtime_service, WorkerRuntimeService)
    assert isinstance(inference_service, WorkerInferenceService)
    assert seen_build == {
        "handlers": 4,
                "registered_services": [
                    ("melix.worker.v1.RuntimeService", 8),
                    ("melix.worker.v1.InferenceService", 11),
                    ("melix.worker.v1.MaintenanceService", maintenance_method_count),
                    ("melix.worker.v1.CacheService", 6),
                ],
        "address": f"unix://{Path('/tmp/melix-test.sock').resolve()}",
        "stopped": 0,
    }
    build_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))["values"]
    assert build_metrics["python_worker.registry_init_ms"] >= 0
    assert build_metrics["python_worker.server_build_ms"] >= 0

    seen = {}

    class FakeServer:
        def start(self):
            seen["started"] = True

        def wait_for_termination(self):
            seen["waited"] = True

    def fake_build_server(
        socket_path: str,
        backend_mode: str = "auto",
        metrics_exporter: BootstrapMetricsExporter | None = None,
    ):
        seen["socket_path"] = socket_path
        seen["backend_mode"] = backend_mode
        if metrics_exporter is not None:
            metrics_exporter.set_milliseconds("python_worker.registry_init_ms", 7.0)
            metrics_exporter.set_milliseconds("python_worker.server_build_ms", 5.0)
        return FakeServer(), None, None

    monkeypatch.setattr("worker.grpc_server.build_server", fake_build_server)
    perf_counter_values = iter(
        [
            1_000_000_000,
            1_030_000_000,
            1_060_000_000,
            1_062_000_000,
            1_080_000_000,
        ]
    )
    monkeypatch.setattr("worker.grpc_server.time.perf_counter_ns", lambda: next(perf_counter_values))
    monkeypatch.setenv("MELIX_PYTHON_WORKER_METRICS_PATH", str(metrics_path))
    monkeypatch.setenv("MELIX_PYTHON_WORKER_STARTUP_T0_NS", "900000000")
    monkeypatch.setattr(
        "argparse.ArgumentParser.parse_args",
        lambda self: Namespace(socket_path="/tmp/from-main.sock", backend_mode="auto"),
    )
    main()

    assert seen == {
        "backend_mode": "auto",
        "socket_path": "/tmp/from-main.sock",
        "started": True,
        "waited": True,
    }
    main_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))["values"]
    assert main_metrics["python_worker.spawn_to_bootstrap_ms"] == 100
    assert main_metrics["python_worker.arg_parse_ms"] == 30
    assert main_metrics["python_worker.registry_init_ms"] == 7
    assert main_metrics["python_worker.server_build_ms"] == 5
    assert main_metrics["python_worker.server_start_ms"] == 2
    assert main_metrics["python_worker.bootstrap_ms"] == 80


def test_bootstrap_metrics_exporter_writes_atomically(monkeypatch, tmp_path: Path) -> None:
    metrics_path = tmp_path / "python-worker-metrics.json"
    seen: dict[str, str] = {}
    original_replace = os.replace

    def record_replace(source: str, destination: str) -> None:
        seen["source"] = source
        seen["destination"] = destination
        original_replace(source, destination)

    monkeypatch.setattr("worker.grpc_server.os.replace", record_replace)

    exporter = BootstrapMetricsExporter(str(metrics_path))
    exporter.set_milliseconds("python_worker.bootstrap_ms", 42.0)

    assert seen["destination"] == os.fspath(metrics_path)
    assert Path(seen["source"]).parent == metrics_path.parent
    assert json.loads(metrics_path.read_text(encoding="utf-8"))["values"]["python_worker.bootstrap_ms"] == 42


def test_bootstrap_metrics_exporter_is_noop_without_export_path() -> None:
    exporter = BootstrapMetricsExporter(None)
    exporter.set_milliseconds("python_worker.bootstrap_ms", 12.0)


def test_build_registry_for_backend_uses_deterministic_runtime() -> None:
    registry = build_registry_for_backend("deterministic")

    assert registry.runtime.runtime_name == "deterministic-text"
    assert registry.embedding_runtime.runtime_name == "deterministic-embed"
    assert registry.rerank_runtime.runtime_name == "deterministic-rerank"


def test_build_registry_for_backend_reads_process_memory_budget_env(monkeypatch) -> None:
    monkeypatch.setenv("MELIX_PYTHON_WORKER_PROCESS_MEMORY_BUDGET_BYTES", "8192")
    monkeypatch.setenv("MELIX_PYTHON_WORKER_MODEL_LOAD_HEADROOM_BYTES", "512")

    registry = build_registry_for_backend("deterministic")
    stats = registry.runtime_stats()

    assert stats.memory_headroom_bytes == 512


def test_build_maintenance_service_uses_deterministic_lora_runner() -> None:
    service = build_maintenance_service(
        build_registry_for_backend("deterministic"),
        jobs_root=Path("/tmp/melix-test-maintenance"),
        backend_mode="deterministic",
    )

    assert isinstance(service._core._lora_training_pipeline._runner, DeterministicLoRARunner)
    assert isinstance(service._core._adapter_activation_pipeline._runner, DeterministicLoRARunner)
    suite = service._core._benchmark_suite_catalog.resolve_suite(
        "smoke",
        jobs_root=Path("/tmp/melix-test-maintenance"),
        parameters={},
        task_kind="text-generation",
    )
    assert suite.prompt_batches
    assert "Say hi." in suite.prompt_batches[0]


def test_build_maintenance_service_keeps_default_lora_runner_for_auto_backend() -> None:
    service = build_maintenance_service(
        build_registry(),
        jobs_root=Path("/tmp/melix-test-maintenance-auto"),
        backend_mode="auto",
    )

    assert not isinstance(service._core._lora_training_pipeline._runner, DeterministicLoRARunner)
    assert not isinstance(service._core._adapter_activation_pipeline._runner, DeterministicLoRARunner)


def _deterministic_training_config() -> LoRATrainingConfig:
    return LoRATrainingConfig(
        training_mode="lora",
        quantization_mode="none",
        family_id="llama",
        rank=8,
        alpha=16.0,
        dropout=0.0,
        target_modules=["q_proj"],
        expanded_target_modules=["model.layers.0.self_attn.q_proj"],
        backend_target_modules=["layers.0.self_attn.q_proj"],
        selected_layer_indices=[0],
        total_layer_count=1,
        num_layers=1,
        learning_rate=1e-5,
        batch_size=1,
        epochs=1,
        iters=1,
        max_steps=0,
        response_only=False,
        gradient_checkpointing=False,
        gradient_accumulation=1,
        mask_prompt=False,
        max_seq_length=128,
        steps_per_report=1,
        steps_per_eval=0,
        steps_per_save=1,
        validation_strategy="none",
        validation_split="",
        validation_sample_count=0,
        preset_id="",
        preset_title="",
        desired_derived_model_alias="deterministic-derived",
        adapter_name="phase8-acceptance",
        target_repo="",
        chunked_training=False,
        chunk_size=2048,
    )


def test_deterministic_lora_runner_train_native_writes_adapter_artifacts(tmp_path: Path) -> None:
    runner = DeterministicLoRARunner()
    request = TrainingRequest(
        job_id="job-1",
        base_model_id="melix-dev-qwen-local",
        model_path=tmp_path / "base-model",
        model_revision="main",
        adapter_output_dir=tmp_path / "output" / "adapter",
        normalized_dataset_dir=tmp_path / "dataset",
        config=_deterministic_training_config(),
        dataset_format="chat_messages",
    )

    result = runner.train_native(request)
    adapter_config = json.loads(result.adapter_config_path.read_text(encoding="utf-8"))

    assert result.weights_path.read_bytes() == b"melix-deterministic-adapter"
    assert adapter_config["fine_tune_type"] == "lora"
    assert adapter_config["num_layers"] == 1
    assert adapter_config["lora_parameters"]["rank"] == 8
    assert result.metrics.tokens_seen == 1024
    assert result.execution_backend == "native"


def test_deterministic_lora_runner_activate_native_copies_runtime_bundle(tmp_path: Path) -> None:
    runner = DeterministicLoRARunner()
    source_root = tmp_path / "base-model"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "config.json").write_text('{"model_type":"llama"}\n', encoding="utf-8")
    (source_root / "tokenizer.json").write_text('{"version":"1.0"}\n', encoding="utf-8")
    (source_root / "model.safetensors").write_bytes(b"base-model")

    request = ActivationRequest(
        job_id="job-2",
        base_model_id="melix-dev-qwen-local",
        model_path=source_root,
        adapter_dir=tmp_path / "adapter",
        adapter_manifest_path=tmp_path / "adapter" / "manifest.json",
        derived_model_dir=tmp_path / "derived-model",
        activation_mode="fuse",
    )

    result = runner.activate_native(request)

    assert (result.derived_model_dir / "config.json").read_text(encoding="utf-8") == '{"model_type":"llama"}\n'
    assert (result.derived_model_dir / "tokenizer.json").read_text(encoding="utf-8") == '{"version":"1.0"}\n'
    assert (result.derived_model_dir / "model.safetensors").read_bytes() == b"base-model"
    assert json.loads(result.manifest_path.read_text(encoding="utf-8")) == {
        "schema_version": "melix.derived_text_model.v1"
    }
    assert result.execution_backend == "native"


def test_deterministic_lora_runner_activate_native_writes_fallback_bundle_when_source_files_missing(
    tmp_path: Path,
) -> None:
    runner = DeterministicLoRARunner()
    source_root = tmp_path / "empty-model"
    source_root.mkdir(parents=True, exist_ok=True)
    request = ActivationRequest(
        job_id="job-3",
        base_model_id="melix-dev-qwen-local",
        model_path=source_root,
        adapter_dir=tmp_path / "adapter",
        adapter_manifest_path=tmp_path / "adapter" / "manifest.json",
        derived_model_dir=tmp_path / "derived-model",
        activation_mode="fuse",
    )

    result = runner.activate_native(request)

    assert (result.derived_model_dir / "config.json").read_text(encoding="utf-8") == (
        '{"model_type":"melix-deterministic"}\n'
    )
    assert (result.derived_model_dir / "tokenizer.json").read_text(encoding="utf-8") == '{"version":"1.0"}\n'
    assert (result.derived_model_dir / "model.safetensors").read_bytes() == b"melix-deterministic-model"


def test_deterministic_benchmark_fetch_json_returns_ultrachat_rows_and_splits() -> None:
    rows = _deterministic_benchmark_fetch_json(
        "rows",
        {"dataset": "HuggingFaceH4/ultrachat_200k", "offset": "0"},
    )
    splits = _deterministic_benchmark_fetch_json(
        "splits",
        {"dataset": "HuggingFaceH4/ultrachat_200k"},
    )

    assert rows["rows"][0]["row"]["messages"][0]["content"] == "Say hi."
    assert splits["splits"][0]["split"] == "train_sft"


def test_deterministic_benchmark_fetch_json_returns_dolly_rows_and_splits() -> None:
    rows = _deterministic_benchmark_fetch_json(
        "rows",
        {"dataset": "databricks/databricks-dolly-15k", "offset": "0"},
    )
    splits = _deterministic_benchmark_fetch_json(
        "splits",
        {"dataset": "databricks/databricks-dolly-15k"},
    )

    assert rows["rows"][0]["row"]["instruction"] == "List two colors."
    assert splits["splits"][0]["split"] == "train"


def test_deterministic_benchmark_fetch_json_returns_image_rows_and_empty_offsets() -> None:
    rows = _deterministic_benchmark_fetch_json(
        "rows",
        {"dataset": "huggingface/documentation-images", "offset": "0"},
    )
    offset_rows = _deterministic_benchmark_fetch_json(
        "rows",
        {"dataset": "huggingface/documentation-images", "offset": "4"},
    )

    assert rows["rows"][0]["row"]["image"]["src"] == "https://example.com/doc-image-1.jpg"
    assert offset_rows == {"rows": []}


def test_deterministic_benchmark_fetch_json_rejects_unknown_datasets() -> None:
    with pytest.raises(AssertionError, match="Unexpected deterministic benchmark fetch"):
        _deterministic_benchmark_fetch_json("rows", {"dataset": "unknown/demo", "offset": "0"})


def test_build_server_normalizes_relative_socket_path(monkeypatch, tmp_path: Path) -> None:
    registry = build_registry()
    seen: dict[str, object] = {}

    class FakeBoundServer:
        def add_generic_rpc_handlers(self, handlers) -> None:
            seen["handlers"] = seen.get("handlers", 0) + len(handlers)

        def add_registered_method_handlers(self, service_name, handlers) -> None:
            services = seen.setdefault("registered_services", [])
            assert isinstance(services, list)
            services.append((service_name, len(handlers)))

        def add_insecure_port(self, address: str) -> int:
            seen["address"] = address
            return 1

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("worker.grpc_server.grpc.server", lambda executor: FakeBoundServer())

    build_server("relative-worker.sock", registry=registry)

    assert seen["address"] == f"unix://{tmp_path / 'relative-worker.sock'}"


def test_build_server_removes_existing_socket_file(monkeypatch, tmp_path: Path) -> None:
    registry = build_registry()
    socket_path = tmp_path / "existing.sock"
    socket_path.write_text("stale", encoding="utf-8")

    class FakeBoundServer:
        def add_generic_rpc_handlers(self, handlers) -> None:
            return None

        def add_registered_method_handlers(self, service_name, handlers) -> None:
            return None

        def add_insecure_port(self, address: str) -> int:
            return 1

    monkeypatch.setattr("worker.grpc_server.grpc.server", lambda executor: FakeBoundServer())

    build_server(os.fspath(socket_path), registry=registry)

    assert not socket_path.exists()


def test_build_server_routes_tooling_roots_from_environment(monkeypatch, tmp_path: Path) -> None:
    registry = build_registry()
    seen: dict[str, object] = {}

    class FakeBoundServer:
        def add_generic_rpc_handlers(self, handlers) -> None:
            return None

        def add_registered_method_handlers(self, service_name, handlers) -> None:
            return None

        def add_insecure_port(self, address: str) -> int:
            return 1

    class FakeMaintenanceService:
        def __init__(self, registry, jobs_root=None, evaluation_jobs_root=None, **kwargs) -> None:
            seen["jobs_root"] = jobs_root
            seen["evaluation_jobs_root"] = evaluation_jobs_root

    monkeypatch.setenv("MELIX_MODEL_OPS_JOBS_ROOT", os.fspath(tmp_path / "ops"))
    monkeypatch.setenv("MELIX_EVALUATION_JOBS_ROOT", os.fspath(tmp_path / "ops/evals"))
    monkeypatch.setattr("worker.grpc_server.grpc.server", lambda executor: FakeBoundServer())
    monkeypatch.setattr("worker.grpc_server.WorkerMaintenanceService", FakeMaintenanceService)
    monkeypatch.setattr("worker.grpc_server.maintenance_pb2_grpc.add_MaintenanceServiceServicer_to_server", lambda servicer, server: None)

    build_server(os.fspath(tmp_path / "worker.sock"), registry=registry)

    assert seen["jobs_root"] == (tmp_path / "ops").resolve()
    assert seen["evaluation_jobs_root"] == (tmp_path / "ops/evals").resolve()


def test_default_melix_home_ignores_blank_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", os.fspath(tmp_path / "user-home"))
    monkeypatch.setenv("MELIX_HOME", " ")

    assert _default_melix_home() == (tmp_path / "user-home/.melix").resolve()


def test_maintenance_service_defaults_jobs_under_melix_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    melix_home = tmp_path / "melix-home"
    monkeypatch.setenv("MELIX_HOME", os.fspath(melix_home))

    service = WorkerMaintenanceService(build_registry())

    assert service._core._jobs_root == (melix_home / "jobs/model-ops").resolve()
    assert service._evaluation_jobs_root == (melix_home / "jobs/evaluation").resolve()


def test_elapsed_helpers_guard_invalid_origins() -> None:
    assert _elapsed_milliseconds_since(10, now_nanoseconds=5) == 0.0
    assert _elapsed_milliseconds_from_origin(None, now_nanoseconds=100) == 0.0
    assert _elapsed_milliseconds_from_origin("bad", now_nanoseconds=100) == 0.0
    assert _elapsed_milliseconds_from_origin("-1", now_nanoseconds=100) == 0.0


def test_maintenance_service_keeps_doctor_and_bench_structured(tmp_path: Path) -> None:
    service = WorkerMaintenanceService(build_registry(), jobs_root=tmp_path / "ops")
    service._core._benchmark_suite_catalog = BenchmarkSuiteCatalog(
        hf_dataset_fetcher=FakeBenchmarkHFDatasetFetcher()
    )

    doctor = service.RunDoctor(
        maintenance_pb2.RunDoctorRequest(
            model_handle="melix-dev-text::1",
            include_cache_diagnostics=True,
            include_memory_report=True,
        ),
        context=None,
    )
    bench_events = list(
        service.RunBench(
            maintenance_pb2.RunBenchRequest(model_handle="melix-dev-text::1", suites=["smoke", "latency"]),
            context=None,
        )
    )

    assert doctor.ok is True
    assert "# Melix Doctor" in doctor.report_markdown
    assert "## Cache" in doctor.report_markdown
    assert "## Memory" in doctor.report_markdown
    assert bench_events[0].started.job_id == "model-ops-0001"
    assert any(event.HasField("metric") and event.metric.name == "bench.smoke.ttft_ms" for event in bench_events)
    assert any(event.HasField("metric") and event.metric.name == "bench.latency.p50_ms" for event in bench_events)
    assert bench_events[-1].completed.report_path.endswith("bench-report.md")


def test_bootstrap_module_invokes_grpc_main(monkeypatch) -> None:
    called = {"count": 0}

    def fake_main() -> None:
        called["count"] += 1

    monkeypatch.setattr("worker.grpc_server.main", fake_main)
    runpy.run_module("worker.bootstrap", run_name="__main__")

    assert called["count"] == 1
