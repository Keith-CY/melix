from __future__ import annotations

from dataclasses import dataclass
from threading import Event
from threading import Lock
import time
from typing import Any

from packages.protocol.python.worker.v1 import cache_pb2, common_pb2, runtime_pb2

from worker.engine.request_state import RequestState
from worker.model_registry.catalog import WorkerModelCatalog
from worker.runtime.deterministic_ocr_runtime import DeterministicOCRRuntime
from worker.runtime.deterministic_speech_runtime import DeterministicSpeechRuntime
from worker.runtime.deterministic_transcription_runtime import DeterministicTranscriptionRuntime
from worker.runtime.deterministic_vlm_runtime import DeterministicVLMRuntime
from worker.runtime.deterministic_image_generation_runtime import DeterministicImageGenerationRuntime
from worker.runtime.audio_runtime_protocols import SpeechRuntimeProtocol, TranscriptionRuntimeProtocol
from worker.runtime.mlx_audio_runtime import MLXAudioSpeechRuntime, MLXAudioTranscriptionRuntime
from worker.runtime.mlx_executor import MLXRuntimeExecutor
from worker.runtime.mlx_text_runtime import MLXTextRuntime
from worker.runtime.mlx_vlm_runtime import MLXVLMRuntime
from worker.runtime.deterministic_embedding_runtime import DeterministicEmbeddingRuntime
from worker.runtime.deterministic_rerank_runtime import DeterministicRerankRuntime


@dataclass
class LoadedModel:
    handle: str
    spec: common_pb2.ModelSpec
    runtime_model: object
    runtime: object
    estimated_resident_bytes: int
    runtime_kind: str
    residency: common_pb2.ResidencyInfo


@dataclass
class MemoryBudgetExceeded(Exception):
    budget_bytes: int
    headroom_bytes: int
    projected_resident_bytes: int
    required_bytes: int

    def __str__(self) -> str:
        return "Projected resident memory would exceed the process budget."

    @property
    def details(self) -> dict[str, str]:
        return {
            "budget_bytes": str(self.budget_bytes),
            "headroom_bytes": str(self.headroom_bytes),
            "projected_resident_bytes": str(self.projected_resident_bytes),
            "required_bytes": str(self.required_bytes),
        }


@dataclass
class DiskStreamingUnsupported(Exception):
    model_id: str
    requested_mode: int

    def __str__(self) -> str:
        return "The selected runtime does not support disk-streaming mode."

    @property
    def details(self) -> dict[str, str]:
        return {
            "model_id": self.model_id,
            "requested_mode": {
                common_pb2.DISK_STREAMING_DISABLED: "DISK_STREAMING_DISABLED",
                common_pb2.DISK_STREAMING_PREFER_DISK: "DISK_STREAMING_PREFER_DISK",
                common_pb2.DISK_STREAMING_REQUIRE_DISK: "DISK_STREAMING_REQUIRE_DISK",
            }.get(self.requested_mode, "DISK_STREAMING_MODE_UNSPECIFIED"),
        }


class WorkerRegistry:
    def __init__(
        self,
        runtime: MLXTextRuntime | None = None,
        embedding_runtime: DeterministicEmbeddingRuntime | None = None,
        rerank_runtime: DeterministicRerankRuntime | None = None,
        ocr_runtime: DeterministicOCRRuntime | None = None,
        vlm_runtime: DeterministicVLMRuntime | None = None,
        mlx_vlm_runtime: MLXVLMRuntime | None = None,
        transcription_runtime: TranscriptionRuntimeProtocol | None = None,
        speech_runtime: SpeechRuntimeProtocol | None = None,
        mlx_audio_transcription_runtime: TranscriptionRuntimeProtocol | None = None,
        mlx_audio_speech_runtime: SpeechRuntimeProtocol | None = None,
        image_generation_runtime: DeterministicImageGenerationRuntime | None = None,
        model_catalog: WorkerModelCatalog | None = None,
        worker_id: str = "worker-text-001",
        process_memory_budget_bytes: int = 0,
        memory_headroom_bytes: int = 0,
        mlx_executor: MLXRuntimeExecutor | None = None,
    ) -> None:
        self._mlx_executor = mlx_executor or MLXRuntimeExecutor()
        self.runtime = runtime or MLXTextRuntime(executor=self._mlx_executor)
        self.embedding_runtime = embedding_runtime or DeterministicEmbeddingRuntime()
        self.rerank_runtime = rerank_runtime or DeterministicRerankRuntime()
        self.ocr_runtime = ocr_runtime or DeterministicOCRRuntime()
        self.vlm_runtime = vlm_runtime or DeterministicVLMRuntime()
        self.mlx_vlm_runtime = mlx_vlm_runtime or MLXVLMRuntime(executor=self._mlx_executor)
        audio_execution_gate = Lock()
        self.transcription_runtime = transcription_runtime or DeterministicTranscriptionRuntime()
        self.speech_runtime = speech_runtime or DeterministicSpeechRuntime()
        self.mlx_audio_transcription_runtime = (
            mlx_audio_transcription_runtime or MLXAudioTranscriptionRuntime(execution_gate=audio_execution_gate)
        )
        self.mlx_audio_speech_runtime = (
            mlx_audio_speech_runtime or MLXAudioSpeechRuntime(execution_gate=audio_execution_gate)
        )
        self.image_generation_runtime = image_generation_runtime or DeterministicImageGenerationRuntime()
        self.model_catalog = model_catalog or WorkerModelCatalog()
        self.worker_id = worker_id
        self._process_memory_budget_bytes = max(0, process_memory_budget_bytes)
        self._memory_headroom_bytes = max(0, memory_headroom_bytes)
        self._lock = Lock()
        self._next_model_handle = 1
        self._loaded_models: dict[str, LoadedModel] = {}
        self._sorted_loaded_model_handles: tuple[str, ...] | None = None
        self._loaded_model_resident_bytes = 0
        self._reserved_model_resident_bytes = 0
        self._requests: dict[str, RequestState] = {}
        self._active_request_count = 0
        self._active_prefill_count = 0
        self._active_decode_count = 0
        self._active_multimodal_request_count = 0
        self._draining = False
        self._last_probe_kind = ""
        self._last_preprocess_latency_ms = 0.0
        self._last_preprocess_input_bytes = 0
        self._last_preprocess_peak_memory_bytes = 0
        self._last_first_token_latency_ms = 0.0
        self._last_transcription_latency_ms = 0.0
        self._last_speech_latency_ms = 0.0
        self._last_audio_duration_seconds = 0.0
        self._last_audio_chunk_count = 0
        self._last_audio_output_bytes = 0
        self._last_audio_model_load_latency_ms = 0.0
        self._last_audio_backend_unavailable_count = 0
        self._last_voice_fallback_count = 0
        self._last_language_fallback_count = 0
        self._last_video_effective_frame_count = 0
        self._last_video_requested_frame_budget = 0
        self._last_video_window_ms = 0
        self._last_temp_media_artifact_count = 0
        self._last_temp_media_artifact_bytes = 0
        self._last_temp_media_cleanup_latency_ms = 0.0
        self._last_temp_media_cleanup_failure_count = 0
        self._last_image_job_latency_ms = 0.0
        self._last_image_artifact_publish_ms = 0.0
        self._last_image_output_bytes = 0
        self._last_image_peak_memory_bytes = 0

    def capabilities(self) -> common_pb2.RuntimeCapabilities:
        return common_pb2.RuntimeCapabilities(
            cache=common_pb2.CacheCapabilities(
                supports_prefix_cache=True,
                supports_paged_cache=False,
                supports_disk_cache=False,
                kv_quant_profiles=["q4"],
                supports_boundary_snapshots=False,
            ),
            execution=common_pb2.ExecutionCapabilities(
                supports_continuous_batching=False,
                supports_speculative_decoding=False,
                supports_disk_streaming=False,
            ),
            parsing=common_pb2.ParserCapabilities(
                supports_tool_call_auto_parsing=False,
                supports_reasoning_separation=False,
            ),
            multimodal=common_pb2.MultimodalCapabilities(
                supports_ocr=True,
                supports_vlm=True,
                supports_transcription=True,
                supports_speech=True,
                supports_image_generation=True,
            ),
        )

    def load_model(
        self,
        model_spec: common_pb2.ModelSpec,
        pin_on_load: bool = False,
        memory_budget_bytes: int = 0,
        disk_streaming_mode: int = common_pb2.DISK_STREAMING_MODE_UNSPECIFIED,
    ) -> LoadedModel:
        resolved = self._resolved_model_spec(model_spec)
        requested_disk_streaming_mode = self._effective_disk_streaming_mode_request(
            resolved,
            request_mode=disk_streaming_mode,
        )
        if requested_disk_streaming_mode in {
            common_pb2.DISK_STREAMING_PREFER_DISK,
            common_pb2.DISK_STREAMING_REQUIRE_DISK,
        }:
            raise DiskStreamingUnsupported(
                model_id=resolved.model_id,
                requested_mode=requested_disk_streaming_mode,
            )
        runtime_kind, runtime = self._runtime_for_model(resolved)
        estimated = runtime.estimate_resident_bytes(resolved)
        with self._lock:
            existing_resident_bytes = self._loaded_model_resident_bytes + self._reserved_model_resident_bytes
            projected_resident_bytes = existing_resident_bytes + estimated
            required_process_bytes = projected_resident_bytes + self._memory_headroom_bytes
            if self._process_memory_budget_bytes > 0 and required_process_bytes > self._process_memory_budget_bytes:
                raise MemoryBudgetExceeded(
                    budget_bytes=self._process_memory_budget_bytes,
                    headroom_bytes=self._memory_headroom_bytes,
                    projected_resident_bytes=projected_resident_bytes,
                    required_bytes=required_process_bytes,
                )
            self._reserved_model_resident_bytes += estimated

        effective_request_budget_bytes = max(0, memory_budget_bytes)
        required_request_bytes = estimated + self._memory_headroom_bytes
        if effective_request_budget_bytes > 0 and required_request_bytes > effective_request_budget_bytes:
            with self._lock:
                self._reserved_model_resident_bytes = max(0, self._reserved_model_resident_bytes - estimated)
            raise MemoryBudgetExceeded(
                budget_bytes=effective_request_budget_bytes,
                headroom_bytes=self._memory_headroom_bytes,
                projected_resident_bytes=estimated,
                required_bytes=required_request_bytes,
            )

        try:
            runtime_model = runtime.load_model(resolved)
            residency = self._loaded_residency(
                resolved,
                pin_on_load=pin_on_load,
                effective_disk_streaming_mode=requested_disk_streaming_mode,
            )
        except Exception:
            with self._lock:
                self._reserved_model_resident_bytes = max(0, self._reserved_model_resident_bytes - estimated)
            raise

        with self._lock:
            self._reserved_model_resident_bytes = max(0, self._reserved_model_resident_bytes - estimated)
            handle = f"{resolved.model_id}::{self._next_model_handle}"
            self._next_model_handle += 1
            loaded = LoadedModel(
                handle=handle,
                spec=resolved,
                runtime_model=runtime_model,
                runtime=runtime,
                estimated_resident_bytes=estimated,
                runtime_kind=runtime_kind,
                residency=residency,
            )
            self._loaded_models[handle] = loaded
            self._invalidate_loaded_model_order_locked()
            self._loaded_model_resident_bytes += estimated
            if runtime_kind in {"transcription", "speech"}:
                self._last_audio_model_load_latency_ms = float(getattr(runtime_model, "load_latency_ms", 0.0))
            return loaded

    def _resolved_model_spec(self, requested: common_pb2.ModelSpec) -> common_pb2.ModelSpec:
        catalog_model = self.model_catalog.get(requested.model_id)
        if catalog_model is None:
            return requested
        if self._is_sparse_model_request(requested):
            return catalog_model
        return requested

    @staticmethod
    def _is_sparse_model_request(model_spec: common_pb2.ModelSpec) -> bool:
        populated_fields = model_spec.ListFields()
        if not populated_fields:
            return True
        return len(populated_fields) == 1 and populated_fields[0][0].name == "model_id"

    def unload_model(self, handle: str) -> bool:
        with self._lock:
            loaded = self._loaded_models.pop(handle, None)
            if loaded is None:
                return False
            self._invalidate_loaded_model_order_locked()
            self._loaded_model_resident_bytes = max(0, self._loaded_model_resident_bytes - loaded.estimated_resident_bytes)
            return True

    def _invalidate_loaded_model_order_locked(self) -> None:
        self._sorted_loaded_model_handles = None

    def _sorted_loaded_model_handles_locked(self) -> tuple[str, ...]:
        cached_handles = self._sorted_loaded_model_handles
        if cached_handles is None:
            cached_handles = tuple(sorted(self._loaded_models))
            self._sorted_loaded_model_handles = cached_handles
        return cached_handles

    def warmup_model(self, handle: str, synthetic_messages=None) -> int | None:
        loaded = self.get_loaded_model(handle)
        if loaded is None:
            return None
        runtime = self.runtime_for_loaded_model(loaded)
        if not hasattr(runtime, "render_prompt") or not hasattr(runtime, "generate_tokens"):
            raise NotImplementedError("Warmup is only available for generation runtimes.")

        messages = list(synthetic_messages or [])
        if not messages:
            messages = [
                common_pb2.ChatMessage(
                    role="user",
                    parts=[common_pb2.MessagePart(text="Warm up the local runtime.")],
                )
            ]

        started_at = time.perf_counter()
        prompt = runtime.render_prompt(
            messages,
            loaded_model=loaded.runtime_model,
            template_kwargs=None,
            execution_ext={},
        )
        sampling = common_pb2.SamplingConfig(
            temperature=0.0,
            top_p=1.0,
            top_k=1,
            max_output_tokens=1,
        )
        cancel_event = Event()
        token_stream = runtime.generate_tokens(
            loaded.runtime_model,
            prompt,
            sampling,
            cancel_event,
            execution_ext={},
        )
        try:
            for _ in token_stream:
                cancel_event.set()
                break
        finally:
            close = getattr(token_stream, "close", None)
            if callable(close):
                close()
        return int(round(max(0.0, (time.perf_counter() - started_at) * 1000.0)))

    def get_loaded_model(self, handle: str) -> LoadedModel | None:
        with self._lock:
            return self._loaded_models.get(handle)

    def list_loaded_models(self) -> list[str]:
        with self._lock:
            return list(self._sorted_loaded_model_handles_locked())

    def list_loaded_model_summaries(self) -> list[runtime_pb2.LoadedModelSummary]:
        with self._lock:
            loaded_models = [
                self._loaded_models[handle] for handle in self._sorted_loaded_model_handles_locked()
            ]
        return [self._loaded_model_summary(loaded) for loaded in loaded_models]

    def start_request(self, request_id: str, runtime_kind: str = "text") -> RequestState:
        state = RequestState(request_id=request_id, runtime_kind=runtime_kind)
        with self._lock:
            existing = self._requests.get(request_id)
            if existing is not None:
                self._remove_request_from_counters(existing)
            self._requests[request_id] = state
            self._add_request_to_counters(state)
        return state

    def get_request(self, request_id: str) -> RequestState | None:
        with self._lock:
            return self._requests.get(request_id)

    def set_request_phase(self, request_id: str, phase: str) -> None:
        with self._lock:
            state = self._requests.get(request_id)
            if state is not None:
                self._remove_request_from_counters(state)
                state.phase = phase
                self._add_request_to_counters(state)

    def finish_request(self, request_id: str) -> None:
        with self._lock:
            state = self._requests.pop(request_id, None)
            if state is not None:
                self._remove_request_from_counters(state)

    def abort_request(self, request_id: str) -> bool:
        with self._lock:
            state = self._requests.get(request_id)
        if state is None:
            return False
        state.cancel_event.set()
        return True

    def runtime_stats(self) -> runtime_pb2.RuntimeStats:
        cache_stats = self.cache_stats_response().stats
        with self._lock:
            active_requests = self._active_request_count
            active_prefills = self._active_prefill_count
            active_decodes = self._active_decode_count
            active_multimodal_requests = self._active_multimodal_request_count
            model_resident_bytes = self._loaded_model_resident_bytes
            cache_resident_bytes = cache_stats.l1_bytes + cache_stats.l2_bytes
            kv_cache_bytes = 0
            peak_allocation_bytes = 0
            memory_headroom_bytes = self._memory_headroom_bytes
            resident_bytes = model_resident_bytes + cache_resident_bytes + kv_cache_bytes
            last_probe_kind = self._last_probe_kind
            last_preprocess_latency_ms = self._last_preprocess_latency_ms
            last_preprocess_input_bytes = self._last_preprocess_input_bytes
            last_preprocess_peak_memory_bytes = self._last_preprocess_peak_memory_bytes
            last_first_token_latency_ms = self._last_first_token_latency_ms
            last_transcription_latency_ms = self._last_transcription_latency_ms
            last_speech_latency_ms = self._last_speech_latency_ms
            last_audio_duration_seconds = self._last_audio_duration_seconds
            last_audio_chunk_count = self._last_audio_chunk_count
            last_audio_output_bytes = self._last_audio_output_bytes
            last_audio_model_load_latency_ms = self._last_audio_model_load_latency_ms
            last_audio_backend_unavailable_count = self._last_audio_backend_unavailable_count
            last_voice_fallback_count = self._last_voice_fallback_count
            last_language_fallback_count = self._last_language_fallback_count
            last_video_effective_frame_count = self._last_video_effective_frame_count
            last_video_requested_frame_budget = self._last_video_requested_frame_budget
            last_video_window_ms = self._last_video_window_ms
            last_temp_media_artifact_count = self._last_temp_media_artifact_count
            last_temp_media_artifact_bytes = self._last_temp_media_artifact_bytes
            last_temp_media_cleanup_latency_ms = self._last_temp_media_cleanup_latency_ms
            last_temp_media_cleanup_failure_count = self._last_temp_media_cleanup_failure_count
            last_image_job_latency_ms = self._last_image_job_latency_ms
            last_image_artifact_publish_ms = self._last_image_artifact_publish_ms
            last_image_output_bytes = self._last_image_output_bytes
            last_image_peak_memory_bytes = self._last_image_peak_memory_bytes
        mlx_executor_snapshot = self._mlx_executor.snapshot()
        stats = runtime_pb2.RuntimeStats(
            worker_state="draining" if self._draining else "idle",
            resident_bytes=resident_bytes,
            active_requests=active_requests,
            active_prefills=active_prefills,
            active_decodes=active_decodes,
            l1_cache_bytes=cache_stats.l1_bytes,
            l2_cache_bytes=cache_stats.l2_bytes,
            l1_hit_rate=cache_stats.l1_hit_rate,
            l2_hit_rate=cache_stats.l2_hit_rate,
            active_multimodal_requests=active_multimodal_requests,
            last_probe_kind=last_probe_kind,
            last_preprocess_latency_ms=last_preprocess_latency_ms,
            last_preprocess_input_bytes=last_preprocess_input_bytes,
            last_preprocess_peak_memory_bytes=last_preprocess_peak_memory_bytes,
            last_first_token_latency_ms=last_first_token_latency_ms,
            last_transcription_latency_ms=last_transcription_latency_ms,
            last_speech_latency_ms=last_speech_latency_ms,
            last_audio_duration_seconds=last_audio_duration_seconds,
            last_audio_chunk_count=last_audio_chunk_count,
            last_audio_output_bytes=last_audio_output_bytes,
            last_audio_model_load_latency_ms=last_audio_model_load_latency_ms,
            last_audio_backend_unavailable_count=last_audio_backend_unavailable_count,
            last_voice_fallback_count=last_voice_fallback_count,
            last_language_fallback_count=last_language_fallback_count,
            last_video_effective_frame_count=last_video_effective_frame_count,
            last_video_requested_frame_budget=last_video_requested_frame_budget,
            last_video_window_ms=last_video_window_ms,
            last_temp_media_artifact_count=last_temp_media_artifact_count,
            last_temp_media_artifact_bytes=last_temp_media_artifact_bytes,
            last_temp_media_cleanup_latency_ms=last_temp_media_cleanup_latency_ms,
            last_temp_media_cleanup_failure_count=last_temp_media_cleanup_failure_count,
            last_image_job_latency_ms=last_image_job_latency_ms,
            last_image_artifact_publish_ms=last_image_artifact_publish_ms,
            last_image_output_bytes=last_image_output_bytes,
            last_image_peak_memory_bytes=last_image_peak_memory_bytes,
            generation_stream_owner_mode=mlx_executor_snapshot.generation_stream_owner_mode,
            worker_thread_init_latency_ms=mlx_executor_snapshot.worker_thread_init_latency_ms,
            stream_sync_fallback_count=mlx_executor_snapshot.stream_sync_fallback_count,
        )
        stats.model_resident_bytes = model_resident_bytes
        stats.cache_resident_bytes = cache_resident_bytes
        stats.kv_cache_bytes = kv_cache_bytes
        stats.peak_allocation_bytes = peak_allocation_bytes
        stats.memory_headroom_bytes = memory_headroom_bytes
        return stats

    @staticmethod
    def _is_multimodal_request_kind(runtime_kind: str) -> bool:
        return runtime_kind in {"ocr", "vlm", "transcription", "speech", "image"}

    def _add_request_to_counters(self, state: RequestState) -> None:
        self._active_request_count += 1
        if state.phase == "prefill":
            self._active_prefill_count += 1
        elif state.phase == "decode":
            self._active_decode_count += 1
        if self._is_multimodal_request_kind(state.runtime_kind):
            self._active_multimodal_request_count += 1

    def _remove_request_from_counters(self, state: RequestState) -> None:
        self._active_request_count = max(0, self._active_request_count - 1)
        if state.phase == "prefill":
            self._active_prefill_count = max(0, self._active_prefill_count - 1)
        elif state.phase == "decode":
            self._active_decode_count = max(0, self._active_decode_count - 1)
        if self._is_multimodal_request_kind(state.runtime_kind):
            self._active_multimodal_request_count = max(0, self._active_multimodal_request_count - 1)

    def cache_stats_response(self) -> cache_pb2.GetCacheStatsResponse:
        response = cache_pb2.GetCacheStatsResponse()
        runtime = self.vlm_runtime
        if hasattr(runtime, "cache_stats_response"):
            runtime_response = runtime.cache_stats_response()
            if isinstance(runtime_response, cache_pb2.GetCacheStatsResponse):
                return runtime_response
        return response

    def set_draining(self, draining: bool) -> None:
        with self._lock:
            self._draining = draining

    def runtime_for_loaded_model(self, loaded_model: LoadedModel) -> Any:
        return loaded_model.runtime

    def record_vision_probe(self, runtime_kind: str, probe: Any) -> None:
        with self._lock:
            self._last_probe_kind = runtime_kind
            self._last_preprocess_latency_ms = float(getattr(probe, "preprocess_latency_ms", 0.0))
            self._last_preprocess_input_bytes = int(getattr(probe, "preprocess_input_bytes", 0))
            self._last_preprocess_peak_memory_bytes = int(getattr(probe, "preprocess_peak_memory_bytes", 0))
            self._last_first_token_latency_ms = float(getattr(probe, "first_token_latency_ms", 0.0))
            self._last_transcription_latency_ms = 0.0
            self._last_speech_latency_ms = 0.0
            self._last_audio_duration_seconds = 0.0
            self._last_audio_chunk_count = 0
            self._last_audio_output_bytes = 0
            self._last_video_effective_frame_count = int(getattr(probe, "video_effective_frame_count", 0))
            self._last_video_requested_frame_budget = int(getattr(probe, "video_requested_frame_budget", 0))
            self._last_video_window_ms = int(getattr(probe, "video_window_ms", 0))
            self._last_temp_media_artifact_count = int(getattr(probe, "temp_media_artifact_count", 0))
            self._last_temp_media_artifact_bytes = int(getattr(probe, "temp_media_artifact_bytes", 0))
            self._last_temp_media_cleanup_latency_ms = float(getattr(probe, "temp_media_cleanup_latency_ms", 0.0))
            self._last_temp_media_cleanup_failure_count = int(getattr(probe, "temp_media_cleanup_failure_count", 0))
            self._last_image_job_latency_ms = 0.0
            self._last_image_artifact_publish_ms = 0.0
            self._last_image_output_bytes = 0
            self._last_image_peak_memory_bytes = 0

    def record_transcription_probe(self, probe: Any) -> None:
        with self._lock:
            self._last_probe_kind = "transcription"
            self._last_preprocess_latency_ms = float(getattr(probe, "preprocess_latency_ms", 0.0))
            self._last_preprocess_input_bytes = int(getattr(probe, "preprocess_input_bytes", 0))
            self._last_preprocess_peak_memory_bytes = int(getattr(probe, "preprocess_peak_memory_bytes", 0))
            self._last_first_token_latency_ms = 0.0
            self._last_transcription_latency_ms = float(getattr(probe, "transcription_latency_ms", 0.0))
            self._last_speech_latency_ms = 0.0
            self._last_audio_duration_seconds = float(getattr(probe, "estimated_duration_seconds", 0.0))
            self._last_audio_chunk_count = int(getattr(probe, "chunk_count", 0))
            self._last_audio_output_bytes = 0
            self._last_language_fallback_count = int(getattr(probe, "language_fallback_count", 0))
            self._last_video_effective_frame_count = 0
            self._last_video_requested_frame_budget = 0
            self._last_video_window_ms = 0
            self._last_temp_media_artifact_count = 0
            self._last_temp_media_artifact_bytes = 0
            self._last_temp_media_cleanup_latency_ms = 0.0
            self._last_temp_media_cleanup_failure_count = 0
            self._last_image_job_latency_ms = 0.0
            self._last_image_artifact_publish_ms = 0.0
            self._last_image_output_bytes = 0
            self._last_image_peak_memory_bytes = 0

    def record_speech_probe(self, probe: Any) -> None:
        with self._lock:
            self._last_probe_kind = "speech"
            self._last_preprocess_latency_ms = 0.0
            self._last_preprocess_input_bytes = 0
            self._last_preprocess_peak_memory_bytes = 0
            self._last_first_token_latency_ms = 0.0
            self._last_transcription_latency_ms = 0.0
            self._last_speech_latency_ms = float(getattr(probe, "speech_latency_ms", 0.0))
            self._last_audio_duration_seconds = 0.0
            self._last_audio_chunk_count = 0
            self._last_audio_output_bytes = int(getattr(probe, "output_bytes", 0))
            self._last_voice_fallback_count = int(getattr(probe, "voice_fallback_count", 0))
            self._last_video_effective_frame_count = 0
            self._last_video_requested_frame_budget = 0
            self._last_video_window_ms = 0
            self._last_temp_media_artifact_count = 0
            self._last_temp_media_artifact_bytes = 0
            self._last_temp_media_cleanup_latency_ms = 0.0
            self._last_temp_media_cleanup_failure_count = 0
            self._last_image_job_latency_ms = 0.0
            self._last_image_artifact_publish_ms = 0.0
            self._last_image_output_bytes = 0
            self._last_image_peak_memory_bytes = 0

    def record_audio_model_load_probe(self, load_latency_ms: float) -> None:
        with self._lock:
            self._last_audio_model_load_latency_ms = float(load_latency_ms)

    def increment_audio_backend_unavailable(self) -> None:
        with self._lock:
            self._last_audio_backend_unavailable_count += 1

    def record_image_probe(self, probe: Any) -> None:
        with self._lock:
            self._last_probe_kind = "image"
            self._last_preprocess_latency_ms = 0.0
            self._last_preprocess_input_bytes = 0
            self._last_preprocess_peak_memory_bytes = 0
            self._last_first_token_latency_ms = 0.0
            self._last_transcription_latency_ms = 0.0
            self._last_speech_latency_ms = 0.0
            self._last_audio_duration_seconds = 0.0
            self._last_audio_chunk_count = 0
            self._last_audio_output_bytes = 0
            self._last_video_effective_frame_count = 0
            self._last_video_requested_frame_budget = 0
            self._last_video_window_ms = 0
            self._last_temp_media_artifact_count = 0
            self._last_temp_media_artifact_bytes = 0
            self._last_temp_media_cleanup_latency_ms = 0.0
            self._last_temp_media_cleanup_failure_count = 0
            self._last_image_job_latency_ms = float(getattr(probe, "job_latency_ms", 0.0))
            self._last_image_artifact_publish_ms = float(getattr(probe, "artifact_publish_ms", 0.0))
            self._last_image_output_bytes = int(getattr(probe, "output_bytes", 0))
            self._last_image_peak_memory_bytes = int(getattr(probe, "peak_memory_bytes", 0))

    def _runtime_for_model(self, model_spec: common_pb2.ModelSpec) -> tuple[str, Any]:
        if model_spec.model_kind == "embedding":
            return "embedding", self.embedding_runtime
        if model_spec.model_kind == "rerank":
            return "rerank", self.rerank_runtime
        if model_spec.model_kind == "ocr":
            return "ocr", self.ocr_runtime
        if model_spec.model_kind == "vlm":
            backend_id = self._vlm_backend_id_for_model(model_spec)
            if backend_id == "deterministic":
                return "vlm", self.vlm_runtime
            if backend_id == "mlx_vlm":
                return "vlm", self.mlx_vlm_runtime
            raise RuntimeError(
                f"Vision-language model {model_spec.model_id} declares unsupported backend {backend_id!r}."
            )
        if model_spec.model_kind == "transcription":
            backend_id = self._audio_backend_id_for_model(model_spec)
            if backend_id == "deterministic":
                return "transcription", self.transcription_runtime
            if backend_id == "mlx_audio.stt":
                return "transcription", self.mlx_audio_transcription_runtime
            raise RuntimeError(
                f"Audio transcription model {model_spec.model_id} declares unsupported backend {backend_id!r}."
            )
        if model_spec.model_kind == "speech":
            backend_id = self._audio_backend_id_for_model(model_spec)
            if backend_id == "deterministic":
                return "speech", self.speech_runtime
            if backend_id == "mlx_audio.tts":
                return "speech", self.mlx_audio_speech_runtime
            raise RuntimeError(
                f"Audio speech model {model_spec.model_id} declares unsupported backend {backend_id!r}."
            )
        if model_spec.model_kind == "image":
            return "image", self.image_generation_runtime
        return "text", self.runtime

    @staticmethod
    def _audio_backend_id_for_model(model_spec: common_pb2.ModelSpec) -> str:
        backend_id = model_spec.ext.get("melix.audio.backend_id", "").strip()
        if backend_id:
            return backend_id
        if model_spec.model_id in {"melix-dev-transcribe", "melix-dev-speech"}:
            return "deterministic"
        raise RuntimeError(
            f"Audio model {model_spec.model_id} requires an explicit melix.audio.backend_id."
        )

    @staticmethod
    def _vlm_backend_id_for_model(model_spec: common_pb2.ModelSpec) -> str:
        backend_id = model_spec.ext.get("melix.vlm.backend_id", "").strip()
        if backend_id:
            return backend_id
        if model_spec.model_id == "melix-dev-vlm":
            return "deterministic"
        return "mlx_vlm"

    def _loaded_model_summary(self, loaded: LoadedModel) -> runtime_pb2.LoadedModelSummary:
        summary = runtime_pb2.LoadedModelSummary()
        summary.model_handle = loaded.handle
        summary.model.CopyFrom(loaded.spec)
        summary.residency.CopyFrom(loaded.residency)
        summary.estimated_resident_bytes = loaded.estimated_resident_bytes
        return summary

    def _loaded_residency(
        self,
        model_spec: common_pb2.ModelSpec,
        *,
        pin_on_load: bool,
        effective_disk_streaming_mode: int,
    ) -> common_pb2.ResidencyInfo:
        policy = self._effective_residency_policy(model_spec, pin_on_load=pin_on_load)
        residency = common_pb2.ResidencyInfo()
        residency.state = (
            common_pb2.RESIDENCY_STATE_PINNED
            if policy == common_pb2.MEMORY_RESIDENCY_PINNED
            else common_pb2.RESIDENCY_STATE_WARM
        )
        residency.policy = policy
        residency.pin_requested = pin_on_load or model_spec.settings.pin_on_load
        residency.pinned = residency.state == common_pb2.RESIDENCY_STATE_PINNED
        residency.ttl_seconds = model_spec.settings.ttl_seconds
        residency.transition_reason = "load_model"
        residency.effective_disk_streaming_mode = effective_disk_streaming_mode
        return residency

    def _effective_residency_policy(
        self,
        model_spec: common_pb2.ModelSpec,
        *,
        pin_on_load: bool,
    ) -> int:
        settings = model_spec.settings
        if pin_on_load or settings.pin_on_load:
            return common_pb2.MEMORY_RESIDENCY_PINNED
        if settings.memory_policy != common_pb2.MEMORY_RESIDENCY_POLICY_UNSPECIFIED:
            return settings.memory_policy
        if settings.ttl_seconds > 0:
            return common_pb2.MEMORY_RESIDENCY_TTL
        return common_pb2.MEMORY_RESIDENCY_EVICTABLE

    def _effective_disk_streaming_mode_request(
        self,
        model_spec: common_pb2.ModelSpec,
        *,
        request_mode: int,
    ) -> int:
        if request_mode != common_pb2.DISK_STREAMING_MODE_UNSPECIFIED:
            return request_mode
        if model_spec.settings.disk_streaming_mode != common_pb2.DISK_STREAMING_MODE_UNSPECIFIED:
            return model_spec.settings.disk_streaming_mode
        return common_pb2.DISK_STREAMING_DISABLED
