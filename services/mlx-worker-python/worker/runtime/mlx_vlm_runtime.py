from __future__ import annotations

from copy import copy
from dataclasses import dataclass, field, replace
import hashlib
import importlib.util
import logging
import os
from queue import Queue
import time
from pathlib import Path
from threading import Event
from threading import Condition
from threading import Thread
from typing import Any, Callable, Iterable

from packages.protocol.python.worker.v1 import common_pb2
from worker.runtime.deterministic_vlm_runtime import VisionProbeSnapshot
from worker.runtime.mlx_executor import MLXRuntimeExecutor
from worker.runtime.mlx_text_runtime import (
    RuntimeTokenEvent,
    _bytes_value,
    _first_present,
    _float_tuple,
    _int_tuple,
)
from worker.runtime.multimodal_fast_paths import MultimodalFastPathController, fast_path_probe_signature
from worker.runtime.multimodal_preprocessing import PreparedVisionRequest, prepare_vision_request, rebuild_multimodal_hash
from worker.runtime.runtime_utils import (
    callable_accepts_kwarg as _callable_accepts_kwarg,
    callable_declares_kwarg as _callable_declares_kwarg,
    installed_package_version as _installed_package_version,
)
from worker.runtime.temp_media_lifecycle import TempMediaSession
from worker.runtime.vision_family_adapters import resolve_vision_family_config

logger = logging.getLogger(__name__)
_GEMMA4_PRESENCE_NONE = (False, False)
_GEMMA4_PRESENCE_VISION = (True, False)
_GEMMA4_PRESENCE_AUDIO = (False, True)
_GEMMA4_PRESENCE_BOTH = (True, True)

_TEXT_ONLY_BATCH_GENERATOR_EXT_KEY = "melix.vlm.text_only_batch_generator"
_TEXT_ONLY_STEP_COOPERATIVE_EXT_KEY = "melix.vlm.text_only_step_cooperative"
_TEXT_ONLY_BATCH_PREFILL_STEP_SIZE_ENV = "MELIX_VLM_TEXT_BATCH_PREFILL_STEP_SIZE"
_TEXT_ONLY_BATCH_DEFAULT_PREFILL_STEP_SIZE = 512
_TEXT_ONLY_BATCH_DONE = object()
_GEMMA4_OPEN_MARKER = "<|channel>thought\n"
_GEMMA4_OPEN_MARKER_BARE = "<|channel>"
_GEMMA4_CLOSE_MARKER = "<channel|>"
_GEMMA4_TURN_END_MARKER = "<turn|>"
_GEMMA4_TOOL_RESPONSE_OPEN = "<|tool_response>"
_GEMMA4_TOOL_RESPONSE_CLOSE = "<tool_response|>"

class RuntimeUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class MaterializedMediaPaths:
    image_paths: tuple[str, ...]
    video_paths: tuple[str, ...]


class _Gemma4TextBackedModelShim:
    def __init__(self, language_model: Any) -> None:
        self.language_model = language_model
        self.config = type("Gemma4TextBackedConfig", (), {})()
        self.config.__dict__.update(getattr(language_model.config, "__dict__", {}))
        self.config.model_type = "gemma4"
        self.config.image_token_id = getattr(self.config, "image_token_id", -1)
        self.config.audio_token_id = getattr(self.config, "audio_token_id", -2)

    def get_input_embeddings(self, input_ids=None, pixel_values=None, **kwargs):
        _ = pixel_values
        _ = kwargs
        from mlx_vlm.models.base import InputEmbeddingsFeatures

        inputs_embeds = self.language_model.model.embed_tokens(input_ids)
        inputs_embeds = inputs_embeds * self.language_model.model.embed_scale
        per_layer_inputs = None
        if self.language_model.model.hidden_size_per_layer_input:
            per_layer_inputs = self.language_model.model.get_per_layer_inputs(input_ids)
        return InputEmbeddingsFeatures(
            inputs_embeds=inputs_embeds,
            per_layer_inputs=per_layer_inputs,
        )


class _TextOnlyVLMDecodeAdapter:
    def __init__(self, vlm_model: Any) -> None:
        self._vlm_model = vlm_model
        self._language_model = getattr(vlm_model, "language_model", vlm_model)

    @property
    def layers(self):
        model = getattr(self._language_model, "model", None)
        if model is not None and hasattr(model, "layers"):
            return model.layers
        return getattr(self._language_model, "layers")

    @property
    def config(self):
        return getattr(self._vlm_model, "config", getattr(self._language_model, "config", None))

    @property
    def args(self):
        return getattr(self._language_model, "args", self.config)

    def make_cache(self):
        if hasattr(self._language_model, "make_cache"):
            return self._language_model.make_cache()
        from mlx_lm.models.cache import KVCache

        return [KVCache() for _ in range(len(self.layers))]

    def __call__(self, input_ids, cache=None, **kwargs):
        if hasattr(self._vlm_model, "_set_position_state"):
            self._vlm_model._set_position_state(input_ids)
        result = self._language_model(input_ids, cache=cache, **kwargs)
        return result.logits if hasattr(result, "logits") else result


class _CallableTokenizerProcessor:
    def __init__(self, tokenizer_wrapper: Any) -> None:
        self._tokenizer_wrapper = tokenizer_wrapper

    def __getattr__(self, attr: str) -> Any:
        return getattr(self._tokenizer_wrapper, attr)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        tokenizer = getattr(self._tokenizer_wrapper, "_tokenizer", self._tokenizer_wrapper)
        return tokenizer(*args, **kwargs)


class _TextOnlyBatchRequest:
    def __init__(
        self,
        *,
        loaded_model: dict[str, Any],
        input_ids: list[int],
        max_tokens: int,
        detokenizer: Any,
        stop_token_ids: set[int],
        cancel_event: Event,
        prompt_tokens: int,
        started_at: float | None = None,
        prepare_ms: float = 0.0,
    ) -> None:
        self.loaded_model = loaded_model
        self.input_ids = input_ids
        self.max_tokens = max_tokens
        self.detokenizer = detokenizer
        self.stop_token_ids = stop_token_ids
        self.cancel_event = cancel_event
        self.prompt_tokens = prompt_tokens
        self.queue: Queue[Any] = Queue()
        self.uid: int | None = None
        self.started_at = started_at if started_at is not None else time.perf_counter()
        self.prepare_ms = max(0.0, float(prepare_ms))
        self.submitted_at = time.perf_counter()
        self.first_token_at: float | None = None
        self.first_generated_response_at: float | None = None
        self.first_visible_text_at: float | None = None
        self.empty_text_token_count_before_first_visible = 0
        self.completion_tokens = 0
        self.cumulative_raw_text = ""


@dataclass
class _TextOnlyBatchGeneratorStats:
    submitted_request_count: int = 0
    completed_request_count: int = 0
    step_count: int = 0
    generated_token_count: int = 0
    peak_active_batch_size: int = 0
    queue_wait_ms_total: float = 0.0
    insert_ms_total: float = 0.0
    executor_step_ms_total: float = 0.0
    next_ms_total: float = 0.0
    emit_ms_total: float = 0.0
    active_batch_size: int = 0
    generated_response_count: int = 0
    failed_request_count: int = 0
    prepare_ms_total: float = 0.0
    first_response_ms_total: float = 0.0
    first_visible_ms_total: float = 0.0
    first_visible_token_index_total: int = 0
    first_empty_segment_count: int = 0
    prefill_response_count: int = 0
    prefill_step_count: int = 0
    prefill_processed_token_count: int = 0
    prefill_total_token_count: int = 0
    prefill_completed_request_count: int = 0
    prefill_step_size: int = _TEXT_ONLY_BATCH_DEFAULT_PREFILL_STEP_SIZE

    def snapshot(self) -> "_TextOnlyBatchGeneratorStats":
        return replace(self)


def _text_batch_generator_stats_snapshot(scheduler: Any) -> _TextOnlyBatchGeneratorStats:
    stats_snapshot = getattr(scheduler, "stats_snapshot", None)
    if not callable(stats_snapshot):
        return _TextOnlyBatchGeneratorStats()
    stats = stats_snapshot()
    return stats if isinstance(stats, _TextOnlyBatchGeneratorStats) else _TextOnlyBatchGeneratorStats()


def _text_batch_generator_probe_kwargs(stats: _TextOnlyBatchGeneratorStats) -> dict[str, float | int]:
    return {
        "text_batch_generator_submitted_request_count": stats.submitted_request_count,
        "text_batch_generator_completed_request_count": stats.completed_request_count,
        "text_batch_generator_step_count": stats.step_count,
        "text_batch_generator_generated_token_count": stats.generated_token_count,
        "text_batch_generator_peak_active_batch_size": stats.peak_active_batch_size,
        "text_batch_generator_queue_wait_ms_total": stats.queue_wait_ms_total,
        "text_batch_generator_insert_ms_total": stats.insert_ms_total,
        "text_batch_generator_executor_step_ms_total": stats.executor_step_ms_total,
        "text_batch_generator_next_ms_total": stats.next_ms_total,
        "text_batch_generator_emit_ms_total": stats.emit_ms_total,
        "text_batch_generator_active_batch_size": stats.active_batch_size,
        "text_batch_generator_generated_response_count": stats.generated_response_count,
        "text_batch_generator_failed_request_count": stats.failed_request_count,
        "text_batch_generator_prepare_ms_total": stats.prepare_ms_total,
        "text_batch_generator_first_response_ms_total": stats.first_response_ms_total,
        "text_batch_generator_first_visible_ms_total": stats.first_visible_ms_total,
        "text_batch_generator_first_visible_token_index_total": stats.first_visible_token_index_total,
        "text_batch_generator_first_empty_segment_count": stats.first_empty_segment_count,
        "text_batch_generator_prefill_response_count": stats.prefill_response_count,
        "text_batch_generator_prefill_step_count": stats.prefill_step_count,
        "text_batch_generator_prefill_processed_token_count": stats.prefill_processed_token_count,
        "text_batch_generator_prefill_total_token_count": stats.prefill_total_token_count,
        "text_batch_generator_prefill_completed_request_count": stats.prefill_completed_request_count,
        "text_batch_generator_prefill_step_size": stats.prefill_step_size,
    }


def _text_only_batch_prefill_step_size(value: object | None = None) -> int:
    raw_value = os.environ.get(_TEXT_ONLY_BATCH_PREFILL_STEP_SIZE_ENV) if value is None else value
    if raw_value is None or str(raw_value).strip() == "":
        return _TEXT_ONLY_BATCH_DEFAULT_PREFILL_STEP_SIZE
    try:
        parsed = int(str(raw_value).strip())
    except ValueError:
        logger.warning(
            "Ignoring invalid %s=%r; using %d.",
            _TEXT_ONLY_BATCH_PREFILL_STEP_SIZE_ENV,
            raw_value,
            _TEXT_ONLY_BATCH_DEFAULT_PREFILL_STEP_SIZE,
        )
        return _TEXT_ONLY_BATCH_DEFAULT_PREFILL_STEP_SIZE
    return min(8192, max(1, parsed))


class _TextOnlyBatchGeneratorScheduler:
    def __init__(
        self,
        *,
        model: Any,
        processor: Any,
        adapter: _TextOnlyVLMDecodeAdapter,
        executor: MLXRuntimeExecutor | None = None,
        max_batch_size: int = 8,
        wait_ms: float = 2.0,
        prefill_step_size: int | None = None,
    ) -> None:
        self._model = model
        self._processor = processor
        self._adapter = adapter
        self._executor = executor
        self._max_batch_size = max(1, int(max_batch_size))
        self._wait_seconds = max(0.0, float(wait_ms) / 1000.0)
        self._prefill_step_size = _text_only_batch_prefill_step_size(prefill_step_size)
        self._condition = Condition()
        self._pending: list[_TextOnlyBatchRequest] = []
        self._active_by_uid: dict[int, _TextOnlyBatchRequest] = {}
        self._stats = _TextOnlyBatchGeneratorStats(prefill_step_size=self._prefill_step_size)
        self._closed = False
        self._thread = Thread(
            target=self._run,
            name="melix-vlm-text-batch-generator",
            daemon=True,
        )
        self._thread.start()

    def submit(self, request: _TextOnlyBatchRequest):
        with self._condition:
            if self._closed:
                request.queue.put(RuntimeError("The VLM text batch generator is closed."))
                request.queue.put(_TEXT_ONLY_BATCH_DONE)
                return self._drain_request(request)
            self._stats.submitted_request_count += 1
            self._stats.prepare_ms_total += request.prepare_ms
            self._pending.append(request)
            self._condition.notify()
        return self._drain_request(request)

    def stats_snapshot(self) -> _TextOnlyBatchGeneratorStats:
        with self._condition:
            return self._stats.snapshot()

    def _drain_request(self, request: _TextOnlyBatchRequest):
        while True:
            item = request.queue.get()
            if item is _TEXT_ONLY_BATCH_DONE:
                return
            if isinstance(item, BaseException):
                raise item
            yield item

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def _run(self) -> None:
        try:
            while True:
                pending: list[_TextOnlyBatchRequest] = []
                with self._condition:
                    while not self._closed and not self._pending and not self._active_by_uid:
                        self._condition.wait()
                    if self._closed:
                        self._cancel_locked()
                    if self._closed and not self._pending and not self._active_by_uid:
                        return
                    if self._pending and self._wait_seconds:
                        self._condition.wait(timeout=self._wait_seconds)
                    pending = self._take_pending_locked()
                try:
                    insert_started_at = time.perf_counter()
                    self._run_on_executor(lambda: self._insert_pending(pending))
                    insert_elapsed_ms = (time.perf_counter() - insert_started_at) * 1000.0
                    step_started_at = time.perf_counter()
                    self._run_on_executor(self._remove_cancelled_active_requests)
                    self._run_on_executor(self._step)
                    self._run_on_executor(self._remove_cancelled_active_requests)
                    step_elapsed_ms = (time.perf_counter() - step_started_at) * 1000.0
                except BaseException as exc:
                    self._fail_requests([request for request in pending if request.uid is None], exc)
                    raise
                with self._condition:
                    self._stats.insert_ms_total += insert_elapsed_ms
                    self._stats.executor_step_ms_total += step_elapsed_ms
        except BaseException as exc:  # pragma: no cover - defensive batch worker cleanup
            self._fail_all(exc)

    def _take_pending_locked(self) -> list[_TextOnlyBatchRequest]:
        available_slots = self._max_batch_size - len(self._active_by_uid)
        if available_slots <= 0 or not self._pending:
            return []
        taken = self._pending[:available_slots]
        del self._pending[:available_slots]
        return taken

    def _insert_pending(self, requests: list[_TextOnlyBatchRequest]) -> None:
        if not requests:
            return
        batch_generator = self._batch_generator()
        uids = batch_generator.insert(
            [request.input_ids for request in requests],
            max_tokens=[request.max_tokens for request in requests],
        )
        for uid, request in zip(uids, requests):
            request.uid = int(uid)
            self._active_by_uid[int(uid)] = request
            self._stats.queue_wait_ms_total += max(
                0.0,
                (time.perf_counter() - request.submitted_at) * 1000.0,
            )
        self._stats.active_batch_size = len(self._active_by_uid)
        self._stats.peak_active_batch_size = max(
            self._stats.peak_active_batch_size,
            len(self._active_by_uid),
        )

    def _step(self) -> None:
        if not self._active_by_uid:
            return
        next_started_at = time.perf_counter()
        prompt_responses, generation_responses = self._batch_generator().next()
        self._stats.next_ms_total += (time.perf_counter() - next_started_at) * 1000.0
        self._stats.step_count += 1
        self._record_prompt_responses(prompt_responses or ())
        self._stats.generated_response_count += len(generation_responses or ())
        if not generation_responses:
            return
        for response in generation_responses:
            request = self._active_by_uid.get(int(response.uid))
            if request is None:
                continue
            if request.cancel_event.is_set():
                self._finish_request(request)
                continue
            emit_started_at = time.perf_counter()
            self._emit_response(request, response)
            self._stats.emit_ms_total += (time.perf_counter() - emit_started_at) * 1000.0
            if getattr(response, "finish_reason", None):
                self._finish_request(request)

    def _record_prompt_responses(self, responses: Iterable[Any]) -> None:
        for response in responses:
            self._stats.prefill_response_count += 1
            self._stats.prefill_step_count += 1
            progress = getattr(response, "progress", None)
            if isinstance(progress, tuple | list) and len(progress) >= 2:
                try:
                    processed = int(progress[0])
                    total = int(progress[1])
                except (TypeError, ValueError):
                    continue
                self._stats.prefill_processed_token_count = max(
                    self._stats.prefill_processed_token_count,
                    max(0, processed),
                )
                self._stats.prefill_total_token_count = max(
                    self._stats.prefill_total_token_count,
                    max(0, total),
                )
                if total > 0 and processed >= total:
                    self._stats.prefill_completed_request_count += 1

    def _remove_cancelled_active_requests(self) -> None:
        cancelled_uids = [
            uid for uid, request in self._active_by_uid.items() if request.cancel_event.is_set()
        ]
        if not cancelled_uids:
            return
        generator = getattr(self._adapter, "_melix_batch_generator", None)
        remove = getattr(generator, "remove", None)
        if callable(remove):
            remove(cancelled_uids)
        for uid in cancelled_uids:
            request = self._active_by_uid.get(uid)
            if request is not None:
                self._finish_request(request)

    def _emit_response(self, request: _TextOnlyBatchRequest, response: Any) -> None:
        token_id = int(getattr(response, "token"))
        if token_id in request.stop_token_ids:
            self._finish_request(request)
            return
        now = time.perf_counter()
        if request.first_generated_response_at is None:
            request.first_generated_response_at = now
            self._stats.first_response_ms_total += max(0.0, (now - request.started_at) * 1000.0)
        if request.first_token_at is None:
            request.first_token_at = now
        request.detokenizer.add_token(token_id)
        request.completion_tokens += 1
        self._stats.generated_token_count += 1
        text = str(getattr(request.detokenizer, "last_segment", "") or "")
        if not text:
            if request.first_visible_text_at is None:
                request.empty_text_token_count_before_first_visible += 1
            return
        request.cumulative_raw_text += text
        now = time.perf_counter()
        if request.first_visible_text_at is None:
            request.first_visible_text_at = now
            self._stats.first_visible_ms_total += max(0.0, (now - request.started_at) * 1000.0)
            self._stats.first_visible_token_index_total += request.completion_tokens
            self._stats.first_empty_segment_count += request.empty_text_token_count_before_first_visible
        generation_elapsed = max(0.0, now - (request.first_token_at or now))
        request.queue.put(
            RuntimeTokenEvent(
                text=text,
                raw_text=request.cumulative_raw_text,
                token_ids=(token_id,),
                token_logprobs=_float_tuple(getattr(response, "logprobs", None)),
                prompt_tokens=request.prompt_tokens,
                completion_tokens=request.completion_tokens,
                prompt_tps=float(getattr(response, "prompt_tps", 0.0) or 0.0),
                generation_tps=(request.completion_tokens / generation_elapsed) if generation_elapsed > 0 else 0.0,
                peak_memory=float(getattr(response, "peak_memory", 0.0) or 0.0),
                finish_reason=str(getattr(response, "finish_reason", "") or "") or None,
            )
        )

    def _finish_request(self, request: _TextOnlyBatchRequest) -> None:
        if request.uid is not None:
            removed = self._active_by_uid.pop(request.uid, None)
            if removed is not None:
                self._stats.completed_request_count += 1
            self._stats.active_batch_size = len(self._active_by_uid)
            request.uid = None
        try:
            request.detokenizer.finalize()
            text = str(getattr(request.detokenizer, "last_segment", "") or "")
            if text:
                request.cumulative_raw_text += text
                request.queue.put(
                    RuntimeTokenEvent(
                        text=text,
                        raw_text=request.cumulative_raw_text,
                        prompt_tokens=request.prompt_tokens,
                        completion_tokens=request.completion_tokens,
                        finish_reason="stop",
                    )
                )
        finally:
            request.queue.put(_TEXT_ONLY_BATCH_DONE)

    def _fail_all(self, exc: BaseException) -> None:
        with self._condition:
            requests = [*self._pending, *self._active_by_uid.values()]
            self._pending.clear()
            self._active_by_uid.clear()
            self._stats.active_batch_size = 0
            self._stats.failed_request_count += len(requests)
        for request in requests:
            request.queue.put(exc)
            request.queue.put(_TEXT_ONLY_BATCH_DONE)

    def _fail_requests(self, requests: list[_TextOnlyBatchRequest], exc: BaseException) -> None:
        if not requests:
            return
        with self._condition:
            self._stats.failed_request_count += len(requests)
        for request in requests:
            request.queue.put(exc)
            request.queue.put(_TEXT_ONLY_BATCH_DONE)

    def _cancel_locked(self) -> None:
        requests = [*self._pending, *self._active_by_uid.values()]
        self._pending.clear()
        self._active_by_uid.clear()
        self._stats.active_batch_size = 0
        for request in requests:
            request.queue.put(_TEXT_ONLY_BATCH_DONE)

    def _batch_generator(self):
        generator = getattr(self._adapter, "_melix_batch_generator", None)
        if generator is None:
            from mlx_lm.generate import BatchGenerator
            from mlx_lm.sample_utils import make_sampler

            generator = BatchGenerator(
                model=self._adapter,
                stop_tokens=self._stop_tokens(),
                sampler=make_sampler(temp=0.0, top_p=1.0, top_k=0),
                prefill_batch_size=1,
                completion_batch_size=self._max_batch_size,
                prefill_step_size=self._prefill_step_size,
            )
            self._adapter._melix_batch_generator = generator
        return generator

    def _run_on_executor(self, callback: Callable[[], Any]) -> Any:
        if self._executor is None:
            return callback()
        return self._executor.run(callback)

    def _stop_tokens(self) -> list[list[int]] | None:
        tokenizer = (
            getattr(self._processor, "tokenizer", None)
            if hasattr(self._processor, "tokenizer")
            else self._processor
        )
        token_ids = _tokenizer_stop_token_ids(tokenizer)
        if not token_ids:
            return None
        return [[token_id] for token_id in token_ids]


def _tokenizer_stop_token_ids(tokenizer: Any) -> list[int]:
    token_ids: list[int] = []
    for attr_name in ("eos_token_id", "eos_token_ids", "all_special_ids"):
        try:
            value = getattr(tokenizer, attr_name, None)
        except Exception:
            continue
        if value is None:
            continue
        if isinstance(value, list | tuple | set):
            token_ids.extend(int(item) for item in value if str(item).strip())
        elif str(value).strip():
            token_ids.append(int(value))
    return list(dict.fromkeys(token_ids))


def _gemma4_multimodal_weight_presence(weight_names: Iterable[str]) -> tuple[bool, bool]:
    has_vision = False
    has_audio = False
    for name in weight_names:
        first_character = name[0]
        if first_character == "v":
            if not has_vision and name.startswith("vision_tower."):
                if has_audio:
                    return _GEMMA4_PRESENCE_BOTH
                has_vision = True
        elif first_character == "a":
            if not has_audio and name.startswith("audio_tower."):
                if has_vision:
                    return _GEMMA4_PRESENCE_BOTH
                has_audio = True
        elif first_character == "e":
            if not has_vision and name.startswith("embed_vision."):
                if has_audio:
                    return _GEMMA4_PRESENCE_BOTH
                has_vision = True
            elif not has_audio and name.startswith("embed_audio."):
                if has_vision:
                    return _GEMMA4_PRESENCE_BOTH
                has_audio = True
    if has_vision:
        return _GEMMA4_PRESENCE_VISION
    if has_audio:
        return _GEMMA4_PRESENCE_AUDIO
    return _GEMMA4_PRESENCE_NONE


def _mlx_peak_memory_gb(mx_module: Any) -> float:
    get_peak_memory = getattr(mx_module, "get_peak_memory", None)
    if callable(get_peak_memory):
        return float(get_peak_memory() / 1_000_000_000)
    metal = getattr(mx_module, "metal", None)
    metal_get_peak_memory = getattr(metal, "get_peak_memory", None)
    if callable(metal_get_peak_memory):
        return float(metal_get_peak_memory() / 1_000_000_000)
    return 0.0


def _isolated_streaming_detokenizer(processor: Any) -> Any | None:
    detokenizer = getattr(processor, "detokenizer", None)
    if detokenizer is None:
        return None
    try:
        cloned = copy(detokenizer)
    except Exception:
        return None
    if cloned is detokenizer:
        return None
    reset = getattr(cloned, "reset", None)
    add_token = getattr(cloned, "add_token", None)
    finalize = getattr(cloned, "finalize", None)
    if not callable(reset) or not callable(add_token) or not callable(finalize):
        return None
    reset()
    return cloned


def _supports_isolated_streaming_detokenizer(processor: Any) -> bool:
    return _isolated_streaming_detokenizer(processor) is not None


def _matching_prefix_len(source: str, marker: str) -> int:
    limit = min(len(source), len(marker) - 1)
    for length in range(limit, 0, -1):
        if marker.startswith(source[-length:]):
            return length
    return 0


def _tokenizer_streaming_detokenizer(tokenizer: Any) -> Any | None:
    detokenizer = getattr(tokenizer, "detokenizer", None)
    if detokenizer is not None:
        try:
            cloned = copy(detokenizer)
        except Exception:
            cloned = detokenizer
        if cloned is not None and cloned is not detokenizer:
            reset = getattr(cloned, "reset", None)
            add_token = getattr(cloned, "add_token", None)
            finalize = getattr(cloned, "finalize", None)
            if callable(reset) and callable(add_token) and callable(finalize):
                reset()
                return cloned
    try:
        from mlx_lm.tokenizer_utils import NaiveStreamingDetokenizer
    except Exception:
        return None
    try:
        detokenizer = NaiveStreamingDetokenizer(tokenizer)
    except Exception:
        return None
    reset = getattr(detokenizer, "reset", None)
    if callable(reset):
        reset()
    return detokenizer


class _Gemma4TextOnlyStreamingParser:
    def __init__(self, tokenizer: Any, detokenizer: Any | None) -> None:
        self._tokenizer = tokenizer
        self._detokenizer = detokenizer
        self._buffer = ""
        self._in_thought = False
        self.text = ""
        self.last_segment = ""

    def reset(self) -> None:
        self._buffer = ""
        self._in_thought = False
        self.text = ""
        self.last_segment = ""
        reset = getattr(self._detokenizer, "reset", None)
        if callable(reset):
            reset()

    def add_token(self, token: int) -> None:
        if self._detokenizer is not None:
            self._detokenizer.add_token(token)
            decoded = str(getattr(self._detokenizer, "last_segment", "") or "")
        else:
            decoded = str(self._tokenizer.decode([token]) or "")
        self.last_segment = self._consume_text(decoded)
        self.text += self.last_segment

    def finalize(self) -> None:
        decoded = ""
        finalize = getattr(self._detokenizer, "finalize", None)
        if callable(finalize):
            finalize()
            decoded = str(getattr(self._detokenizer, "last_segment", "") or "")
        self.last_segment = self._consume_text(decoded, final=True)
        if self._buffer:
            self.last_segment += self._buffer
            self._buffer = ""
        if self._in_thought:
            self.last_segment += "</think>\n"
            self._in_thought = False
        self.text += self.last_segment

    @staticmethod
    def _find_next_marker(source: str, markers: tuple[str, ...]) -> tuple[int | None, str | None]:
        next_index: int | None = None
        next_marker: str | None = None
        for marker in markers:
            index = source.find(marker)
            if index >= 0 and (next_index is None or index < next_index):
                next_index = index
                next_marker = marker
        return next_index, next_marker

    def _consume_text(self, decoded: str, *, final: bool = False) -> str:
        source = self._buffer + decoded
        self._buffer = ""
        if not source:
            return ""

        markers = (
            _GEMMA4_OPEN_MARKER,
            _GEMMA4_OPEN_MARKER_BARE,
            _GEMMA4_CLOSE_MARKER,
            _GEMMA4_TURN_END_MARKER,
            _GEMMA4_TOOL_RESPONSE_OPEN,
            _GEMMA4_TOOL_RESPONSE_CLOSE,
        )
        parts: list[str] = []
        position = 0
        while position < len(source):
            marker_index: int | None = None
            marker_value: str | None = None
            for marker in markers:
                index = source.find(marker, position)
                if index >= 0 and (marker_index is None or index < marker_index):
                    marker_index = index
                    marker_value = marker

            if marker_index is None or marker_value is None:
                remainder = source[position:]
                if not final:
                    keep = max(_matching_prefix_len(remainder, marker) for marker in markers)
                    if keep:
                        parts.append(remainder[:-keep])
                        self._buffer = remainder[-keep:]
                    else:
                        parts.append(remainder)
                else:
                    parts.append(remainder)
                break

            if not final and marker_value == _GEMMA4_OPEN_MARKER_BARE:
                suffix = source[marker_index:]
                if len(suffix) < len(_GEMMA4_OPEN_MARKER) and _GEMMA4_OPEN_MARKER.startswith(suffix):
                    parts.append(source[position:marker_index])
                    self._buffer = suffix
                    return "".join(parts)

            parts.append(source[position:marker_index])
            advance = len(marker_value)
            if marker_value in (_GEMMA4_OPEN_MARKER, _GEMMA4_OPEN_MARKER_BARE):
                if not self._in_thought:
                    parts.append("<think>\n")
                    self._in_thought = True
                after = marker_index + advance
                if marker_value == _GEMMA4_OPEN_MARKER_BARE:
                    if source.startswith("thought\n", after):
                        advance += len("thought\n")
                    elif source.startswith("thought", after):
                        advance += len("thought")
            elif marker_value == _GEMMA4_CLOSE_MARKER and self._in_thought:
                parts.append("</think>\n")
                self._in_thought = False

            position = marker_index + advance

        return "".join(parts)


def _text_only_streaming_decoder(processor: Any, loaded_model: Any) -> Any | None:
    tokenizer = processor.tokenizer if hasattr(processor, "tokenizer") else processor
    metadata = dict(loaded_model.get("metadata", {})) if isinstance(loaded_model, dict) else {}
    model_type = str(
        getattr(getattr(loaded_model.get("model") if isinstance(loaded_model, dict) else None, "config", None), "model_type", "")
        or ""
    ).lower()
    if metadata.get("vision_family_id", "").strip() == "gemma4-v1" or model_type.startswith("gemma4"):
        detokenizer = _tokenizer_streaming_detokenizer(tokenizer)
        if detokenizer is not None or callable(getattr(tokenizer, "decode", None)):
            return _Gemma4TextOnlyStreamingParser(tokenizer, detokenizer)
    return _isolated_streaming_detokenizer(processor)


def _gemma4_loaded_execution_mode(model: Any, processor: Any) -> str:
    if getattr(model, "vision_tower", None) is not None or getattr(model, "embed_vision", None) is not None:
        return "multimodal"
    if getattr(processor, "image_processor", None) is not None:
        return "multimodal"
    return "text_backed"


def _patch_gemma4_scaled_linear_quantization() -> None:
    import mlx.nn as nn
    import mlx_vlm.models.gemma4.language as gemma4_language

    scaled_linear = getattr(gemma4_language, "ScaledLinear", None)
    if scaled_linear is None or hasattr(scaled_linear, "to_quantized"):
        return

    class QuantizedScaledLinear(nn.QuantizedLinear):
        def __init__(
            self,
            in_features: int,
            out_features: int,
            scalar: float,
            *,
            group_size: int | None = None,
            bits: int | None = None,
            mode: str = "affine",
        ) -> None:
            super().__init__(
                in_features,
                out_features,
                bias=False,
                group_size=group_size,
                bits=bits,
                mode=mode,
            )
            self.scalar = scalar

        def __call__(self, x):
            return super().__call__(x) * self.scalar

    def to_quantized(
        self,
        group_size: int | None = None,
        bits: int | None = None,
        mode: str = "affine",
        quantize_input: bool = False,
    ):
        _ = quantize_input
        return QuantizedScaledLinear(
            self.weight.shape[1],
            self.weight.shape[0],
            self.scalar,
            group_size=group_size,
            bits=bits,
            mode=mode,
        )

    scaled_linear.to_quantized = to_quantized


@dataclass
class AutoMLXVLMBackend:
    load_fn: Any | None = None
    stream_generate_fn: Any | None = None
    apply_chat_template_fn: Any | None = None
    batch_generate_fn: Any | None = None
    generate_step_fn: Any | None = None
    load_drafter_fn: Any | None = None
    runtime_name: str = "mlx-vlm-unavailable"
    _drafter_cache: dict[tuple[str, str], Any] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if self.load_fn is not None and self.stream_generate_fn is not None and self.apply_chat_template_fn is not None:
            self.runtime_name = "mlx-vlm"
            self._available = True
            self._error = None
            return
        self._available = importlib.util.find_spec("mlx_vlm") is not None
        self._error = None if self._available else ModuleNotFoundError("mlx_vlm is not installed")
        if self._available:
            self.runtime_name = "mlx-vlm"

    def _ensure_runtime(self) -> None:
        if self.load_fn is not None and self.stream_generate_fn is not None and self.apply_chat_template_fn is not None:
            return
        try:
            from mlx_vlm import apply_chat_template, load, stream_generate
        except ModuleNotFoundError as exc:
            self._available = False
            self._error = exc
            self.runtime_name = "mlx-vlm-unavailable"
            raise RuntimeUnavailableError("mlx-vlm is not installed") from exc
        try:
            from mlx_vlm.generate import batch_generate, generate_step
        except (ImportError, ModuleNotFoundError):
            batch_generate = None
            generate_step = None
        try:
            from mlx_vlm.speculative.drafters import load_drafter
        except (ImportError, ModuleNotFoundError):
            load_drafter = None
        self._available = True
        self._error = None
        self.runtime_name = "mlx-vlm"
        self.load_fn = load
        self.stream_generate_fn = stream_generate
        self.apply_chat_template_fn = apply_chat_template
        self.batch_generate_fn = self.batch_generate_fn or batch_generate
        self.generate_step_fn = self.generate_step_fn or generate_step
        self.load_drafter_fn = self.load_drafter_fn or load_drafter

    def supports_mtp_speculative(self) -> bool:
        if self.load_drafter_fn is None:
            return False
        if self.generate_step_fn is not None and (
            _callable_declares_kwarg(self.generate_step_fn, "draft_model")
            and _callable_declares_kwarg(self.generate_step_fn, "draft_kind")
            and _callable_declares_kwarg(self.generate_step_fn, "draft_block_size")
        ):
            return True
        if self.batch_generate_fn is None:
            return False
        return (
            _callable_declares_kwarg(self.batch_generate_fn, "draft_model")
            and _callable_declares_kwarg(self.batch_generate_fn, "draft_kind")
            and _callable_declares_kwarg(self.batch_generate_fn, "draft_block_size")
        )

    def load_drafter(self, model_id: str, *, kind: str = "mtp") -> Any:
        self._ensure_runtime()
        if self.load_drafter_fn is None:
            raise RuntimeUnavailableError("mlx-vlm drafter loading is unavailable")
        cache_key = (model_id, kind)
        cached = self._drafter_cache.get(cache_key)
        if cached is not None:
            return cached
        if _callable_declares_kwarg(self.load_drafter_fn, "kind"):
            drafter = self.load_drafter_fn(model_id, kind=kind)
        else:
            drafter = self.load_drafter_fn(model_id)
        self._drafter_cache[cache_key] = drafter
        return drafter

    def load_model(self, model_spec, *, trust_remote_code: bool = False):
        if not self._available:
            raise RuntimeUnavailableError("mlx-vlm is not installed") from self._error
        self._ensure_runtime()
        if trust_remote_code and not _callable_accepts_kwarg(self.load_fn, "trust_remote_code"):
            raise RuntimeError("mlx-vlm loader cannot honor trust_remote_code.")
        metadata = dict(model_spec.ext)
        metadata["mlx_version"] = _installed_package_version("mlx")
        metadata["mlx_lm_version"] = _installed_package_version("mlx-lm")
        metadata["mlx_vlm_version"] = _installed_package_version("mlx-vlm")
        execution_mode = metadata.get("melix.vlm.execution_mode", "").strip() or "multimodal"
        try:
            load_kwargs: dict[str, Any] = {"revision": model_spec.revision or "main"}
            if trust_remote_code:
                load_kwargs["trust_remote_code"] = True
            model, processor = self.load_fn(model_spec.model_path, **load_kwargs)
            if self._should_attempt_gemma4_text_backed_fallback(model_spec):
                execution_mode = _gemma4_loaded_execution_mode(model, processor)
        except Exception as exc:
            if not self._should_attempt_gemma4_text_backed_fallback(model_spec):
                raise
            model, processor, execution_mode = self._load_gemma4_text_backed_model(
                model_spec=model_spec,
                original_error=exc,
            )
        metadata["melix.vlm.execution_mode"] = execution_mode
        metadata["melix.vlm.text_only_step_cooperative"] = (
            "true"
            if self.generate_step_fn is not None and _supports_isolated_streaming_detokenizer(processor)
            else "false"
        )
        metadata[_TEXT_ONLY_BATCH_GENERATOR_EXT_KEY] = "false"
        family_config = resolve_vision_family_config(dict(model_spec.ext))
        capability_metadata = family_config.capability_metadata()
        capability_metadata["melix.vlm.text_only_step_cooperative"] = metadata[
            "melix.vlm.text_only_step_cooperative"
        ]
        capability_metadata[_TEXT_ONLY_BATCH_GENERATOR_EXT_KEY] = metadata[
            _TEXT_ONLY_BATCH_GENERATOR_EXT_KEY
        ]
        return {
            "model_id": model_spec.model_id,
            "model_kind": model_spec.model_kind,
            "model_path": model_spec.model_path,
            "revision": model_spec.revision,
            "tokenizer_hash": model_spec.tokenizer_hash,
            "quant_profile_id": model_spec.quant_profile_id,
            "parser_mode": model_spec.parser_mode,
            "reasoning_mode": model_spec.reasoning_mode,
            "model": model,
            "processor": processor,
            "metadata": metadata,
            "_vision_family_config": family_config,
            **capability_metadata,
        }

    @staticmethod
    def estimate_resident_bytes(model_spec) -> int:
        _ = model_spec
        return 0

    @staticmethod
    def _should_attempt_gemma4_text_backed_fallback(model_spec) -> bool:
        metadata = dict(getattr(model_spec, "ext", {}))
        if metadata.get("vision_family_id", "").strip() == "gemma4-v1":
            return True
        model_path = str(getattr(model_spec, "model_path", "") or "").lower()
        return "gemma-4" in model_path or "gemma4" in model_path

    @staticmethod
    def _load_gemma4_text_backed_model(model_spec, original_error: Exception):
        import mlx.core as mx
        import mlx.nn as nn
        from mlx_vlm.utils import (
            get_model_and_args,
            get_model_path,
            load_config,
            load_processor,
            update_module_configs,
        )

        _patch_gemma4_scaled_linear_quantization()

        model_path = get_model_path(model_spec.model_path, revision=model_spec.revision or "main")
        config = load_config(model_path)
        weights: dict[str, Any] = {}
        for entry in os.scandir(model_path):
            try:
                if not entry.is_file() or not entry.name.endswith(".safetensors"):
                    continue
            except OSError:
                continue
            weights.update(mx.load(entry.path))

        has_vision_weights, has_audio_weights = _gemma4_multimodal_weight_presence(weights.keys())
        if has_vision_weights:
            raise original_error

        if config.get("model_type") == "gemma4_text":
            from mlx_vlm.utils import load_tokenizer

            model = AutoMLXVLMBackend._load_gemma4_text_only_language_model(
                config=config,
                weights=weights,
            )
            processor = _CallableTokenizerProcessor(
                load_tokenizer(
                    model_path,
                    return_tokenizer=True,
                )
            )
            return model, processor, "text_backed"

        model_class, _ = get_model_and_args(config=config)
        config.setdefault("text_config", config.pop("llm_config", {}))
        config.setdefault("vision_config", {})
        config.setdefault("audio_config", {})

        model_config = model_class.ModelConfig.from_dict(config)
        model_config = update_module_configs(
            model_config,
            model_class,
            config,
            ["text", "vision", "perceiver", "projector", "audio"],
        )
        model = model_class.Model(model_config)
        model.vision_tower = None
        model.embed_vision = None
        if not has_audio_weights:
            model.audio_tower = None
            model.embed_audio = None

        quantization = config.get("quantization")
        if quantization is not None:
            def get_class_predicate(path: str, module: Any):
                if path.startswith(("vision_tower", "embed_vision")):
                    return False
                if path.startswith(("audio_tower", "embed_audio")) and not has_audio_weights:
                    return False
                if path in quantization:
                    return quantization[path]
                if not hasattr(module, "to_quantized"):
                    return False
                if hasattr(module, "weight") and module.weight.size % 64 != 0:
                    return False
                return f"{path}.scales" in weights

            nn.quantize(
                model,
                group_size=quantization["group_size"],
                bits=quantization["bits"],
                mode=quantization.get("mode", "affine"),
                class_predicate=get_class_predicate,
            )

        filtered_weights = [
            (key, value)
            for key, value in weights.items()
            if not key.startswith(("vision_tower.", "embed_vision."))
            and (has_audio_weights or not key.startswith(("audio_tower.", "embed_audio.")))
        ]
        model.load_weights(filtered_weights)

        processor = load_processor(
            model_path,
            True,
            eos_token_ids=getattr(model.config, "eos_token_id", None),
        )
        execution_mode = "text_backed"
        return model, processor, execution_mode

    @staticmethod
    def _load_gemma4_text_only_language_model(*, config: dict[str, Any], weights: dict[str, Any]):
        import mlx.core as mx
        import mlx.nn as nn
        from mlx_vlm.models.gemma4.language import LanguageModel, TextConfig

        model_config = TextConfig.from_dict(config)
        model = LanguageModel(model_config)
        quantization = config.get("quantization")
        if quantization is not None:
            def get_class_predicate(path: str, module: Any):
                if path in quantization:
                    return quantization[path]
                if not hasattr(module, "to_quantized"):
                    return False
                if hasattr(module, "weight") and module.weight.size % 64 != 0:
                    return False
                return f"{path}.scales" in weights

            nn.quantize(
                model,
                group_size=quantization["group_size"],
                bits=quantization["bits"],
                mode=quantization.get("mode", "affine"),
                class_predicate=get_class_predicate,
            )

        if hasattr(model, "sanitize"):
            weights = model.sanitize(weights)
        model.load_weights(list(weights.items()))
        mx.eval(model.parameters())
        model.eval()
        return _Gemma4TextBackedModelShim(model)


class MLXVLMRuntime:
    def __init__(
        self,
        backend: AutoMLXVLMBackend | None = None,
        temp_root: Path | str | None = None,
        temp_media_session_factory: Callable[..., TempMediaSession] | None = None,
        fast_path_controller: MultimodalFastPathController | None = None,
        executor: MLXRuntimeExecutor | None = None,
    ) -> None:
        self._backend = backend or AutoMLXVLMBackend()
        self._temp_root = Path(temp_root) if temp_root is not None else None
        self._temp_media_session_factory = temp_media_session_factory or TempMediaSession
        self._fast_path_controller = fast_path_controller or MultimodalFastPathController()
        self._executor = executor
        self._last_probe = VisionProbeSnapshot(0.0, 0, 0, 0.0)
        self._last_fast_path_signature: tuple[str, ...] | None = None
        self._loaded_models_with_schedulers: list[dict[str, Any]] = []

    @property
    def runtime_name(self) -> str:
        return getattr(self._backend, "runtime_name", "mlx-vlm-unavailable")

    @property
    def supports_trust_policy(self) -> bool:
        explicit_support = getattr(self._backend, "supports_trust_policy", None)
        if explicit_support is not None:
            return bool(explicit_support)
        runtime_name = self.runtime_name.strip().lower().replace("-", "_")
        return runtime_name in {"mlx_vlm", "mlx_vlm_unavailable"}

    def load_model(self, model_spec, *, trust_remote_code: bool = False):
        def load_backend():
            if _callable_accepts_kwarg(self._backend.load_model, "trust_remote_code"):
                return self._backend.load_model(model_spec, trust_remote_code=trust_remote_code)
            if trust_remote_code:
                raise RuntimeError("VLM runtime backend cannot honor trust_remote_code.")
            return self._backend.load_model(model_spec)

        if self._executor is None:
            return load_backend()
        return self._executor.run(load_backend)

    def estimate_resident_bytes(self, model_spec) -> int:
        return int(self._backend.estimate_resident_bytes(model_spec))

    def close_loaded_model(self, loaded_model) -> None:
        if not isinstance(loaded_model, dict):
            return
        self._loaded_models_with_schedulers = [
            candidate for candidate in self._loaded_models_with_schedulers if candidate is not loaded_model
        ]
        scheduler = loaded_model.pop("_melix_text_only_batch_generator_scheduler", None)
        if isinstance(scheduler, _TextOnlyBatchGeneratorScheduler):
            scheduler.close()

    def render_prompt(
        self,
        messages,
        loaded_model=None,
        template_kwargs=None,
        execution_ext: dict[str, str] | None = None,
    ) -> PreparedVisionRequest:
        if self._executor is not None:
            return self._executor.run(
                lambda: self._render_prompt(
                    messages,
                    loaded_model=loaded_model,
                    template_kwargs=template_kwargs,
                    execution_ext=execution_ext,
                )
            )
        return self._render_prompt(
            messages,
            loaded_model=loaded_model,
            template_kwargs=template_kwargs,
            execution_ext=execution_ext,
        )

    def _render_prompt(
        self,
        messages,
        loaded_model=None,
        template_kwargs=None,
        execution_ext: dict[str, str] | None = None,
    ) -> PreparedVisionRequest:
        _ = template_kwargs
        started_at = time.perf_counter()
        metadata = loaded_model.get("metadata", {}) if isinstance(loaded_model, dict) else {}
        execution_mode = str(metadata.get("melix.vlm.execution_mode", "") or "").strip() or "multimodal"
        family_config = self._family_config(loaded_model)
        prompt_text, has_non_text_media = self._prompt_text_and_media_presence(messages)
        include_chat_messages = (
            bool(execution_ext)
            and self._truthy_ext(execution_ext, _TEXT_ONLY_BATCH_GENERATOR_EXT_KEY)
        )
        if execution_mode == "text_backed":
            if has_non_text_media:
                prepared = family_config.shape_request(prepare_vision_request(messages))
                if prepared.videos and not prepared.images:
                    prepared = self._replace_prompt_text(
                        prepared,
                        prompt_text=self._text_backed_video_prompt(prepared),
                    )
                prepared = replace(
                    prepared,
                    preprocess_latency_ms=max(0.0, (time.perf_counter() - started_at) * 1000.0),
                    preprocess_input_bytes=prepared.preprocess_input_bytes,
                    preprocess_peak_memory_bytes=prepared.preprocess_peak_memory_bytes,
                )
            else:
                prepared = self._prompt_only_request(
                    messages,
                    family_config=family_config,
                    started_at=started_at,
                    prompt_text=prompt_text,
                    include_chat_messages=include_chat_messages,
                )
        else:
            if has_non_text_media:
                prepared = family_config.shape_request(prepare_vision_request(messages))
            else:
                prepared = self._prompt_only_request(
                    messages,
                    family_config=family_config,
                    started_at=started_at,
                    prompt_text=prompt_text,
                    include_chat_messages=include_chat_messages,
                )
        self._record_fast_path_probe(loaded_model, prepared)
        return prepared

    def prompt_token_count(
        self,
        prepared_request: PreparedVisionRequest,
        loaded_model=None,
    ) -> int:
        return self._family_config(loaded_model).prompt_token_count(prepared_request)

    def generate_tokens(
        self,
        loaded_model,
        prepared_request: PreparedVisionRequest,
        sampling,
        cancel_event: Event,
        execution_ext: dict[str, str] | None = None,
        acceleration_policy: common_pb2.AccelerationPolicy | None = None,
    ):
        metadata = loaded_model.get("metadata", {}) if isinstance(loaded_model, dict) else {}
        execution_mode = str(metadata.get("melix.vlm.execution_mode", "") or "").strip() or "multimodal"
        speculative_fallback_reason = ""
        if self._mtp_speculative_requested(acceleration_policy):
            speculative_fallback_reason = self._mtp_speculative_unsupported_reason(
                loaded_model=loaded_model,
                prepared_request=prepared_request,
                sampling=sampling,
                execution_mode=execution_mode,
                acceleration_policy=acceleration_policy,
            )
            if not speculative_fallback_reason:
                yield from self._generate_mtp_speculative_tokens(
                    loaded_model=loaded_model,
                    prepared_request=prepared_request,
                    sampling=sampling,
                    cancel_event=cancel_event,
                    acceleration_policy=acceleration_policy,
                )
                return
            if not bool(getattr(acceleration_policy, "allow_baseline_fallback", False)):
                raise RuntimeError(
                    f"MTP speculative decode is unavailable for this request: {speculative_fallback_reason}."
                )

        if execution_mode == "text_backed" and prepared_request.images:
            raise RuntimeError(
                "The loaded Gemma 4 MLX package does not include vision weights, so image inputs are unavailable."
            )
        self._ensure_fast_path_probe(loaded_model, prepared_request)
        if cancel_event.is_set():
            return

        prompt_tokens = self.prompt_token_count(prepared_request, loaded_model=loaded_model)
        text_only_batch_generator_unsupported_reason = (
            self._text_only_batch_generator_unsupported_reason(
                loaded_model=loaded_model,
                prepared_request=prepared_request,
                sampling=sampling,
                execution_ext=execution_ext,
            )
        )
        if self._can_use_text_only_batch_generator(
            loaded_model=loaded_model,
            prepared_request=prepared_request,
            sampling=sampling,
            execution_ext=execution_ext,
        ):
            yield from self._generate_text_only_batch_generator_events(
                loaded_model=loaded_model,
                prepared_request=prepared_request,
                sampling=sampling,
                cancel_event=cancel_event,
                prompt_tokens=prompt_tokens,
            )
            return
        if self._can_use_text_only_step_fast_path(
            loaded_model=loaded_model,
            prepared_request=prepared_request,
        ):

            def text_only_backend_events():
                # Must run on the executor-owned thread so the MLX runtime is
                # initialized inside the same stream ownership context used for
                # the subsequent token generation work.
                self._backend._ensure_runtime()
                if cancel_event.is_set():
                    return
                yield from self._generate_text_only_step_events(
                    loaded_model=loaded_model,
                    prepared_request=prepared_request,
                    sampling=sampling,
                    cancel_event=cancel_event,
                    prompt_tokens=prompt_tokens,
                    speculative_fallback_reason=speculative_fallback_reason,
                    text_only_batch_generator_unsupported_reason=(
                        text_only_batch_generator_unsupported_reason
                    ),
                )

            event_iterable = (
                text_only_backend_events()
                if self._executor is None
                else self._executor.iterate_cooperatively(text_only_backend_events)
            )
            for event in event_iterable:
                yield event
            return

        temp_media_session = self._temp_media_session_factory(
            temp_root=self._temp_root,
            prefix="melix-vlm-",
        )
        try:
            media_paths = self._materialize_media(prepared_request, temp_media_session)

            def backend_events():
                # Must run on the executor-owned thread so the MLX runtime is
                # initialized inside the same stream ownership context used for
                # the subsequent token generation work.
                self._backend._ensure_runtime()
                if cancel_event.is_set():
                    return

                formatted_prompt = self._backend.apply_chat_template_fn(
                    loaded_model["processor"],
                    loaded_model["model"].config,
                    prepared_request.prompt_text,
                    num_images=len(media_paths.image_paths),
                )
                image_argument = list(media_paths.image_paths) if media_paths.image_paths else None
                stream_kwargs: dict[str, Any] = {
                    "image": image_argument,
                    "max_tokens": int(getattr(sampling, "max_output_tokens", 0) or 64),
                    "temperature": float(getattr(sampling, "temperature", 0.0)),
                    "top_p": float(getattr(sampling, "top_p", 1.0)),
                    "top_k": int(getattr(sampling, "top_k", 0)),
                    "verbose": False,
                }
                if media_paths.video_paths:
                    if _callable_declares_kwarg(self._backend.stream_generate_fn, "video"):
                        stream_kwargs["video"] = list(media_paths.video_paths)
                    else:
                        logger.warning(
                            "mlx-vlm stream_generate does not accept video=; "
                            "falling back to prompt/image-only routing for %d video artifact(s)",
                            len(media_paths.video_paths),
                        )
                        self._last_probe = replace(
                            self._last_probe,
                            multimodal_decode_mode="fallback",
                            multimodal_fallback_reason="backend_video_kwarg_unsupported",
                        )

                started_at = time.perf_counter()
                first_token_at: float | None = None
                completion_tokens = 0
                cumulative_raw_text = ""
                for response in self._backend.stream_generate_fn(
                    loaded_model["model"],
                    loaded_model["processor"],
                    formatted_prompt,
                    **stream_kwargs,
                ):
                    if cancel_event.is_set():
                        return
                    text = str(getattr(response, "text", "") or "")
                    if not text:
                        continue
                    cumulative_raw_text += text
                    now = time.perf_counter()
                    if first_token_at is None:
                        first_token_at = now
                        self._last_probe = replace(
                            self._last_probe,
                            preprocess_latency_ms=prepared_request.preprocess_latency_ms,
                            preprocess_input_bytes=prepared_request.preprocess_input_bytes,
                            preprocess_peak_memory_bytes=prepared_request.preprocess_peak_memory_bytes,
                            first_token_latency_ms=max(0.0, (first_token_at - started_at) * 1000.0),
                            video_effective_frame_count=prepared_request.effective_video_frame_count,
                            video_requested_frame_budget=prepared_request.requested_video_frame_budget,
                            video_window_ms=prepared_request.effective_video_window_ms,
                            cache_identity="",
                            cache_scope_id="",
                            cache_hit=False,
                        )
                    completion_tokens = max(
                        completion_tokens,
                        int(getattr(response, "generation_tokens", 0) or (completion_tokens + 1)),
                    )
                    yield RuntimeTokenEvent(
                        text=text,
                        raw_text=cumulative_raw_text,
                        token_ids=_int_tuple(
                            _first_present(
                                getattr(response, "token_ids", None),
                                getattr(response, "tokens", None),
                                getattr(response, "token", None),
                                getattr(response, "token_id", None),
                            )
                        ),
                        token_logprobs=_float_tuple(
                            _first_present(
                                getattr(response, "token_logprobs", None),
                                getattr(response, "logprobs", None),
                                getattr(response, "logprob", None),
                            )
                        ),
                        token_bytes=_bytes_value(
                            _first_present(
                                getattr(response, "token_bytes", None),
                                getattr(response, "byte_fallback_bytes", None),
                            )
                        ),
                        parser_observation=str(getattr(response, "parser_observation", "") or ""),
                        prompt_tokens=int(getattr(response, "prompt_tokens", 0) or prompt_tokens),
                        completion_tokens=completion_tokens,
                        prompt_tps=float(getattr(response, "prompt_tps", 0.0) or 0.0),
                        generation_tps=float(getattr(response, "generation_tps", 0.0) or 0.0),
                        peak_memory=float(getattr(response, "peak_memory", 0.0) or 0.0),
                        finish_reason="stop",
                        speculative_fallback_count=1 if speculative_fallback_reason else None,
                        speculative_num_draft_tokens=0 if speculative_fallback_reason else None,
                        speculative_draft_model_configured=False if speculative_fallback_reason else None,
                    )

            event_iterable = backend_events() if self._executor is None else self._executor.iterate(backend_events)
            for event in event_iterable:
                yield event
        finally:
            cleanup_report = temp_media_session.cleanup()
            self._last_probe = replace(
                self._last_probe,
                temp_media_artifact_count=cleanup_report.artifact_count,
                temp_media_artifact_bytes=cleanup_report.artifact_bytes,
                temp_media_cleanup_latency_ms=cleanup_report.cleanup_latency_ms,
                temp_media_cleanup_failure_count=cleanup_report.cleanup_failure_count,
            )

    def _generate_mtp_speculative_tokens(
        self,
        *,
        loaded_model,
        prepared_request: PreparedVisionRequest,
        sampling,
        cancel_event: Event,
        acceleration_policy: common_pb2.AccelerationPolicy,
    ):
        self._ensure_fast_path_probe(loaded_model, prepared_request)
        if cancel_event.is_set():
            return
        prompt_tokens = self.prompt_token_count(prepared_request, loaded_model=loaded_model)
        draft_model_id = str(getattr(acceleration_policy, "draft_model_id", "") or "").strip()
        draft_block_size = self._mtp_draft_block_size(acceleration_policy)

        def backend_events():
            self._backend._ensure_runtime()
            if cancel_event.is_set():
                return
            drafter = self._backend.load_drafter(draft_model_id, kind="mtp")
            if self._backend.generate_step_fn is not None:
                yield from self._generate_mtp_speculative_step_events(
                    loaded_model=loaded_model,
                    prepared_request=prepared_request,
                    sampling=sampling,
                    cancel_event=cancel_event,
                    drafter=drafter,
                    draft_block_size=draft_block_size,
                    prompt_tokens=prompt_tokens,
                )
                return

            batch_kwargs: dict[str, Any] = {
                "prompts": [prepared_request.prompt_text],
                "max_tokens": int(getattr(sampling, "max_output_tokens", 0) or 64),
                "draft_model": drafter,
                "draft_kind": "mtp",
                "draft_block_size": draft_block_size,
            }

            started_at = time.perf_counter()
            response_batch = self._backend.batch_generate_fn(
                loaded_model["model"],
                loaded_model["processor"],
                **batch_kwargs,
            )
            if cancel_event.is_set():
                return
            response = self._first_batch_response(response_batch)
            text = self._batch_response_text(response)
            if not text:
                return
            first_token_at = time.perf_counter()
            self._last_probe = replace(
                self._last_probe,
                preprocess_latency_ms=prepared_request.preprocess_latency_ms,
                preprocess_input_bytes=prepared_request.preprocess_input_bytes,
                preprocess_peak_memory_bytes=prepared_request.preprocess_peak_memory_bytes,
                first_token_latency_ms=max(0.0, (first_token_at - started_at) * 1000.0),
                video_effective_frame_count=prepared_request.effective_video_frame_count,
                video_requested_frame_budget=prepared_request.requested_video_frame_budget,
                video_window_ms=prepared_request.effective_video_window_ms,
                cache_identity="",
                cache_scope_id="",
                cache_hit=False,
            )
            completion_tokens = int(
                self._response_number(response, "generation_tokens", "completion_tokens", default=1)
                or 1
            )
            yield RuntimeTokenEvent(
                text=text,
                prompt_tokens=int(self._response_number(response, "prompt_tokens", default=prompt_tokens) or prompt_tokens),
                completion_tokens=completion_tokens,
                prompt_tps=float(self._response_number(response, "prompt_tps", default=0.0) or 0.0),
                generation_tps=float(self._response_number(response, "generation_tps", default=0.0) or 0.0),
                peak_memory=float(self._response_number(response, "peak_memory", default=0.0) or 0.0),
                finish_reason=str(getattr(response, "finish_reason", "") or "stop"),
                speculative_acceptance_rate=self._optional_response_float(response, "speculative_acceptance_rate"),
                speculative_rollback_rate=self._optional_response_float(response, "speculative_rollback_rate"),
                speculative_accepted_tokens=self._optional_response_int(response, "speculative_accepted_tokens"),
                speculative_rejected_tokens=self._optional_response_int(response, "speculative_rejected_tokens"),
                speculative_fallback_count=int(
                    self._response_number(response, "speculative_fallback_count", default=0) or 0
                ),
                speculative_num_draft_tokens=draft_block_size,
                speculative_draft_model_configured=True,
                speculative_draft_propose_ms=self._optional_response_float(response, "speculative_draft_propose_ms"),
                speculative_target_verify_ms=self._optional_response_float(response, "speculative_target_verify_ms"),
            )

        event_iterable = backend_events() if self._executor is None else self._executor.iterate(backend_events)
        for event in event_iterable:
            yield event

    def _generate_mtp_speculative_step_events(
        self,
        *,
        loaded_model,
        prepared_request: PreparedVisionRequest,
        sampling,
        cancel_event: Event,
        drafter: Any,
        draft_block_size: int,
        prompt_tokens: int,
    ):
        import mlx.core as mx
        from mlx_vlm.utils import prepare_inputs

        started_at = time.perf_counter()
        formatted_prompt = self._backend.apply_chat_template_fn(
            loaded_model["processor"],
            loaded_model["model"].config,
            prepared_request.prompt_text,
            num_images=0,
        )
        add_special_tokens = (
            getattr(loaded_model["processor"], "chat_template", None) is None
            if getattr(loaded_model["model"].config, "model_type", "") in ["gemma3", "gemma3n", "gemma4"]
            else True
        )
        inputs = prepare_inputs(
            loaded_model["processor"],
            prompts=[formatted_prompt],
            add_special_tokens=add_special_tokens,
            return_tensors="mlx",
        )
        input_ids = inputs["input_ids"]
        mask = inputs.get("attention_mask")
        prompt_tokens = int(getattr(input_ids, "shape", [0, prompt_tokens])[-1] or prompt_tokens)

        detokenizer = _isolated_streaming_detokenizer(loaded_model["processor"])
        if detokenizer is None:
            detokenizer = loaded_model["processor"].detokenizer
            detokenizer.reset()
        first_token_at: float | None = None
        completion_tokens = 0
        for token, _logprobs in self._backend.generate_step_fn(
            input_ids,
            loaded_model["model"],
            None,
            mask,
            max_tokens=int(getattr(sampling, "max_output_tokens", 0) or 64),
            draft_model=drafter,
            draft_kind="mtp",
            draft_block_size=draft_block_size,
            prefill_step_size=None,
        ):
            if cancel_event.is_set():
                return
            if first_token_at is None:
                first_token_at = time.perf_counter()
            token_values = token if isinstance(token, list) else [token]
            for token_value in token_values:
                detokenizer.add_token(int(token_value))
                completion_tokens += 1
        detokenizer.finalize()
        text = str(getattr(detokenizer, "text", "") or "")
        if not text:
            return
        finished_at = time.perf_counter()
        self._last_probe = replace(
            self._last_probe,
            preprocess_latency_ms=prepared_request.preprocess_latency_ms,
            preprocess_input_bytes=prepared_request.preprocess_input_bytes,
            preprocess_peak_memory_bytes=prepared_request.preprocess_peak_memory_bytes,
            first_token_latency_ms=max(0.0, ((first_token_at or finished_at) - started_at) * 1000.0),
            video_effective_frame_count=prepared_request.effective_video_frame_count,
            video_requested_frame_budget=prepared_request.requested_video_frame_budget,
            video_window_ms=prepared_request.effective_video_window_ms,
            cache_identity="",
            cache_scope_id="",
            cache_hit=False,
        )
        generation_time = max(0.0, finished_at - (first_token_at or finished_at))
        acceptance_stats = self._mtp_drafter_acceptance_stats(drafter, draft_block_size) or {}
        yield RuntimeTokenEvent(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            prompt_tps=0.0,
            generation_tps=(completion_tokens / generation_time) if generation_time > 0 else 0.0,
            peak_memory=_mlx_peak_memory_gb(mx),
            finish_reason="stop",
            speculative_acceptance_rate=acceptance_stats.get("acceptance_rate"),
            speculative_rollback_rate=acceptance_stats.get("rollback_rate"),
            speculative_accepted_tokens=acceptance_stats.get("accepted_tokens"),
            speculative_rejected_tokens=acceptance_stats.get("rejected_tokens"),
            speculative_fallback_count=0,
            speculative_num_draft_tokens=draft_block_size,
            speculative_draft_model_configured=True,
        )

    def _generate_text_only_step_events(
        self,
        *,
        loaded_model,
        prepared_request: PreparedVisionRequest,
        sampling,
        cancel_event: Event,
        prompt_tokens: int,
        speculative_fallback_reason: str,
        text_only_batch_generator_unsupported_reason: str = "",
    ):
        import mlx.core as mx
        from mlx_vlm.utils import prepare_inputs

        started_at = time.perf_counter()
        formatted_prompt = self._backend.apply_chat_template_fn(
            loaded_model["processor"],
            loaded_model["model"].config,
            prepared_request.prompt_text,
            num_images=0,
        )
        add_special_tokens = (
            getattr(loaded_model["processor"], "chat_template", None) is None
            if getattr(loaded_model["model"].config, "model_type", "") in ["gemma3", "gemma3n", "gemma4"]
            else True
        )
        inputs = prepare_inputs(
            loaded_model["processor"],
            prompts=[formatted_prompt],
            add_special_tokens=add_special_tokens,
            return_tensors="mlx",
        )
        input_ids = inputs["input_ids"]
        mask = inputs.get("attention_mask")
        prompt_tokens = int(getattr(input_ids, "shape", [0, prompt_tokens])[-1] or prompt_tokens)

        detokenizer = _isolated_streaming_detokenizer(loaded_model["processor"])
        if detokenizer is None:
            raise RuntimeError("The VLM processor does not expose an isolated streaming detokenizer.")
        tokenizer = (
            loaded_model["processor"].tokenizer
            if hasattr(loaded_model["processor"], "tokenizer")
            else loaded_model["processor"]
        )
        stopping_criteria = getattr(tokenizer, "stopping_criteria", None)
        first_token_at: float | None = None
        completion_tokens = 0
        cumulative_raw_text = ""
        peak_memory_gb: float | None = None

        def cached_peak_memory_gb() -> float:
            nonlocal peak_memory_gb
            if peak_memory_gb is None:
                peak_memory_gb = _mlx_peak_memory_gb(mx)
            return peak_memory_gb

        def finalized_text_event():
            nonlocal cumulative_raw_text
            detokenizer.finalize()
            text = str(getattr(detokenizer, "last_segment", "") or "")
            if not text:
                return None
            cumulative_raw_text += text
            finished_at = time.perf_counter()
            generation_elapsed = max(0.0, finished_at - (first_token_at or finished_at))
            return RuntimeTokenEvent(
                text=text,
                raw_text=cumulative_raw_text,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                prompt_tps=0.0,
                generation_tps=(completion_tokens / generation_elapsed) if generation_elapsed > 0 else 0.0,
                peak_memory=cached_peak_memory_gb(),
                finish_reason="stop",
                speculative_fallback_count=1 if speculative_fallback_reason else None,
                speculative_num_draft_tokens=0 if speculative_fallback_reason else None,
                speculative_draft_model_configured=False if speculative_fallback_reason else None,
            )

        for token, logprobs in self._backend.generate_step_fn(
            input_ids,
            loaded_model["model"],
            None,
            mask,
            max_tokens=int(getattr(sampling, "max_output_tokens", 0) or 64),
            temperature=float(getattr(sampling, "temperature", 0.0)),
            top_p=float(getattr(sampling, "top_p", 1.0)),
            top_k=int(getattr(sampling, "top_k", 0)),
            prefill_step_size=None,
        ):
            if cancel_event.is_set():
                return
            if first_token_at is None:
                first_token_at = time.perf_counter()
                self._last_probe = replace(
                    self._last_probe,
                    preprocess_latency_ms=prepared_request.preprocess_latency_ms,
                    preprocess_input_bytes=prepared_request.preprocess_input_bytes,
                    preprocess_peak_memory_bytes=prepared_request.preprocess_peak_memory_bytes,
                    first_token_latency_ms=max(0.0, (first_token_at - started_at) * 1000.0),
                    video_effective_frame_count=prepared_request.effective_video_frame_count,
                    video_requested_frame_budget=prepared_request.requested_video_frame_budget,
                    video_window_ms=prepared_request.effective_video_window_ms,
                    cache_identity="",
                    cache_scope_id="",
                    cache_hit=False,
                    multimodal_decode_mode="text_only_step",
                    multimodal_fallback_reason=text_only_batch_generator_unsupported_reason or "not_reported",
                    multimodal_decode_sync_mode="executor_step",
                )

            token_values = token if isinstance(token, list) else [token]
            for token_value in token_values:
                try:
                    token_id = int(token_value)
                except (TypeError, ValueError):
                    continue
                if callable(stopping_criteria) and stopping_criteria(token_id):
                    event = finalized_text_event()
                    if event is not None:
                        yield event
                    return
                detokenizer.add_token(token_id)
                completion_tokens += 1
                text = str(getattr(detokenizer, "last_segment", "") or "")
                if not text:
                    continue
                cumulative_raw_text += text
                now = time.perf_counter()
                generation_elapsed = max(0.0, now - (first_token_at or now))
                yield RuntimeTokenEvent(
                    text=text,
                    raw_text=cumulative_raw_text,
                    token_ids=(token_id,),
                    token_logprobs=_float_tuple(logprobs),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    prompt_tps=0.0,
                    generation_tps=(completion_tokens / generation_elapsed) if generation_elapsed > 0 else 0.0,
                    peak_memory=cached_peak_memory_gb(),
                    finish_reason="stop",
                    speculative_fallback_count=1 if speculative_fallback_reason else None,
                    speculative_num_draft_tokens=0 if speculative_fallback_reason else None,
                    speculative_draft_model_configured=False if speculative_fallback_reason else None,
                )

        event = finalized_text_event()
        if event is not None:
            yield event

    def _can_use_text_only_step_fast_path(
        self,
        *,
        loaded_model,
        prepared_request: PreparedVisionRequest,
    ) -> bool:
        return (
            self._backend.generate_step_fn is not None
            and not prepared_request.images
            and not prepared_request.videos
            and _supports_isolated_streaming_detokenizer(loaded_model["processor"])
        )

    def _can_use_text_only_batch_generator(
        self,
        *,
        loaded_model,
        prepared_request: PreparedVisionRequest,
        sampling,
        execution_ext: dict[str, str] | None,
    ) -> bool:
        return not self._text_only_batch_generator_unsupported_reason(
            loaded_model=loaded_model,
            prepared_request=prepared_request,
            sampling=sampling,
            execution_ext=execution_ext,
        )

    @staticmethod
    def _text_only_template_messages(prepared_request: PreparedVisionRequest) -> list[dict[str, object]]:
        if prepared_request.chat_messages:
            return [dict(message) for message in prepared_request.chat_messages]
        return [{"role": "user", "content": prepared_request.prompt_text}]

    @staticmethod
    def _text_only_tokenizer_prompt(processor: Any, prepared_request: PreparedVisionRequest) -> str | None:
        tokenizer = processor.tokenizer if hasattr(processor, "tokenizer") else processor
        apply_chat_template = getattr(tokenizer, "apply_chat_template", None)
        if not callable(apply_chat_template):
            return None
        messages = MLXVLMRuntime._text_only_template_messages(prepared_request)
        try:
            prompt = apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        except TypeError:
            return None
        except ValueError:
            return None
        return prompt if isinstance(prompt, str) else None

    def _text_only_batch_generator_unsupported_reason(
        self,
        *,
        loaded_model,
        prepared_request: PreparedVisionRequest,
        sampling,
        execution_ext: dict[str, str] | None,
    ) -> str:
        if not self._truthy_ext(execution_ext, _TEXT_ONLY_BATCH_GENERATOR_EXT_KEY):
            return "text_only_batch_generator_not_enabled"
        if prepared_request.images or prepared_request.videos:
            return "media_inputs_present"
        if _text_only_streaming_decoder(loaded_model["processor"], loaded_model) is None:
            return "isolated_detokenizer_unavailable"
        if not self._sampling_is_greedy(sampling):
            return "non_greedy_sampling"
        return ""

    @staticmethod
    def _truthy_ext(execution_ext: dict[str, str] | None, key: str) -> bool:
        value = str((execution_ext or {}).get(key, "") or "").strip().lower()
        return value in {"1", "true", "yes", "on", "enabled"}

    def _generate_text_only_batch_generator_events(
        self,
        *,
        loaded_model,
        prepared_request: PreparedVisionRequest,
        sampling,
        cancel_event: Event,
        prompt_tokens: int,
    ):
        from mlx_vlm.utils import prepare_inputs

        started_at = time.perf_counter()
        formatted_prompt = self._text_only_tokenizer_prompt(
            loaded_model["processor"],
            prepared_request,
        )
        if formatted_prompt is None:
            formatted_prompt = self._backend.apply_chat_template_fn(
                loaded_model["processor"],
                loaded_model["model"].config,
                prepared_request.prompt_text,
                num_images=0,
            )
        add_special_tokens = (
            getattr(loaded_model["processor"], "chat_template", None) is None
            if getattr(loaded_model["model"].config, "model_type", "") in ["gemma3", "gemma3n", "gemma4"]
            else True
        )
        inputs = self._run_on_executor(
            lambda: prepare_inputs(
                loaded_model["processor"],
                prompts=[formatted_prompt],
                add_special_tokens=add_special_tokens,
                return_tensors="mlx",
            )
        )
        prepare_ms = max(0.0, (time.perf_counter() - started_at) * 1000.0)
        input_ids = inputs["input_ids"][0].tolist()
        prompt_tokens = len(input_ids) or prompt_tokens
        detokenizer = _text_only_streaming_decoder(loaded_model["processor"], loaded_model)
        if detokenizer is None:
            raise RuntimeError("The VLM processor does not expose an isolated streaming detokenizer.")
        tokenizer = (
            loaded_model["processor"].tokenizer
            if hasattr(loaded_model["processor"], "tokenizer")
            else loaded_model["processor"]
        )
        scheduler = self._text_only_batch_generator_scheduler(loaded_model)
        request = _TextOnlyBatchRequest(
            loaded_model=loaded_model,
            input_ids=input_ids,
            max_tokens=int(getattr(sampling, "max_output_tokens", 0) or 64),
            detokenizer=detokenizer,
            stop_token_ids=set(_tokenizer_stop_token_ids(tokenizer)),
            cancel_event=cancel_event,
            prompt_tokens=prompt_tokens,
            started_at=started_at,
            prepare_ms=prepare_ms,
        )
        first_event = True
        for event in scheduler.submit(request):
            if first_event:
                first_event = False
                scheduler_stats = _text_batch_generator_stats_snapshot(scheduler)
                self._last_probe = replace(
                    self._last_probe,
                    preprocess_latency_ms=prepared_request.preprocess_latency_ms,
                    preprocess_input_bytes=prepared_request.preprocess_input_bytes,
                    preprocess_peak_memory_bytes=prepared_request.preprocess_peak_memory_bytes,
                    first_token_latency_ms=max(0.0, (time.perf_counter() - started_at) * 1000.0),
                    video_effective_frame_count=prepared_request.effective_video_frame_count,
                    video_requested_frame_budget=prepared_request.requested_video_frame_budget,
                    video_window_ms=prepared_request.effective_video_window_ms,
                    cache_identity="",
                    cache_scope_id="",
                    cache_hit=False,
                    multimodal_decode_mode="text_only_batch_generator",
                    multimodal_fallback_reason="not_reported",
                    multimodal_decode_sync_mode="executor_batch_generator",
                    **_text_batch_generator_probe_kwargs(scheduler_stats),
                )
            yield event
        if not first_event:
            self._last_probe = replace(
                self._last_probe,
                **_text_batch_generator_probe_kwargs(
                    _text_batch_generator_stats_snapshot(scheduler)
                ),
            )

    def _text_only_batch_generator_scheduler(self, loaded_model) -> _TextOnlyBatchGeneratorScheduler:
        scheduler_key = "_melix_text_only_batch_generator_scheduler"
        scheduler = loaded_model.get(scheduler_key)
        if isinstance(scheduler, _TextOnlyBatchGeneratorScheduler):
            return scheduler
        adapter = _TextOnlyVLMDecodeAdapter(loaded_model["model"])
        scheduler = _TextOnlyBatchGeneratorScheduler(
            model=loaded_model["model"],
            processor=loaded_model["processor"],
            adapter=adapter,
            executor=self._executor,
            max_batch_size=8,
            wait_ms=2.0,
        )
        loaded_model[scheduler_key] = scheduler
        if not any(candidate is loaded_model for candidate in self._loaded_models_with_schedulers):
            self._loaded_models_with_schedulers.append(loaded_model)
        return scheduler

    def _run_on_executor(self, callback: Callable[[], Any]) -> Any:
        if self._executor is None:
            return callback()
        return self._executor.run(callback)

    @staticmethod
    def _mtp_speculative_requested(acceleration_policy: common_pb2.AccelerationPolicy | None) -> bool:
        if acceleration_policy is None:
            return False
        return int(getattr(acceleration_policy, "mode", 0) or 0) == int(
            common_pb2.ACCELERATION_MODE_SPECULATIVE_DECODE
        )

    def _mtp_speculative_unsupported_reason(
        self,
        *,
        loaded_model,
        prepared_request: PreparedVisionRequest,
        sampling,
        execution_mode: str,
        acceleration_policy: common_pb2.AccelerationPolicy | None,
    ) -> str:
        if acceleration_policy is None:
            return "missing acceleration policy"
        if not str(getattr(acceleration_policy, "draft_model_id", "") or "").strip():
            return "draft_model_id is required"
        if not self._is_gemma4_target(loaded_model):
            return "target model is not Gemma 4"
        if execution_mode != "text_backed":
            return f"target execution mode is {execution_mode}"
        if prepared_request.images or prepared_request.videos:
            return "media inputs are not supported by the Gemma 4 MTP path yet"
        if not self._sampling_is_greedy(sampling):
            return "only greedy sampling is supported"
        self._backend._ensure_runtime()
        if not self._backend.supports_mtp_speculative():
            return "the installed mlx-vlm runtime does not expose MTP drafter support"
        return ""

    @staticmethod
    def _is_gemma4_target(loaded_model) -> bool:
        if not isinstance(loaded_model, dict):
            return False
        metadata = loaded_model.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        family_id = str(metadata.get("vision_family_id") or loaded_model.get("vision_family_id") or "").strip()
        if family_id == "gemma4-v1":
            return True
        model_type = str(getattr(getattr(loaded_model.get("model"), "config", None), "model_type", "") or "").lower()
        return model_type.startswith("gemma4")

    @classmethod
    def _sampling_is_greedy(cls, sampling) -> bool:
        temperature = float(getattr(sampling, "temperature", 0.0) or 0.0)
        top_p = cls._effective_top_p(sampling)
        top_k = int(getattr(sampling, "top_k", 0) or 0)
        return abs(temperature) < 1e-9 and abs(top_p - 1.0) < 1e-9 and top_k in {0, 1}

    @staticmethod
    def _effective_top_p(sampling) -> float:
        return float(getattr(sampling, "top_p", 0.0) or 1.0)

    @staticmethod
    def _mtp_draft_block_size(acceleration_policy: common_pb2.AccelerationPolicy) -> int:
        return int(getattr(acceleration_policy, "num_draft_tokens", 0) or 6)

    @staticmethod
    def _first_batch_response(response_batch: Any) -> Any:
        if isinstance(response_batch, (list, tuple)):
            return response_batch[0] if response_batch else ""
        return response_batch

    @staticmethod
    def _batch_response_text(response: Any) -> str:
        if isinstance(response, str):
            return response
        texts = getattr(response, "texts", None)
        if isinstance(texts, (list, tuple)) and texts:
            return str(texts[0])
        for attr_name in ("text", "response", "content"):
            value = getattr(response, attr_name, None)
            if value is not None:
                return str(value)
        return str(response or "")

    @staticmethod
    def _response_number(response: Any, *attr_names: str, default: float | int = 0) -> float | int:
        for attr_name in attr_names:
            value = getattr(response, attr_name, None)
            if value is not None:
                return value
        stats = getattr(response, "stats", None)
        if stats is not None:
            for attr_name in attr_names:
                value = getattr(stats, attr_name, None)
                if value is not None:
                    return value
        return default

    @classmethod
    def _optional_response_float(cls, response: Any, attr_name: str) -> float | None:
        value = cls._response_number(response, attr_name, default=None)
        if value is None:
            return None
        return float(value)

    @classmethod
    def _optional_response_int(cls, response: Any, attr_name: str) -> int | None:
        value = cls._response_number(response, attr_name, default=None)
        if value is None:
            return None
        return int(value)

    @staticmethod
    def _mtp_drafter_acceptance_stats(drafter: Any, draft_block_size: int) -> dict[str, float | int] | None:
        drafter_model = getattr(drafter, "model", drafter)
        accept_lens = getattr(drafter_model, "accept_lens", None)
        if not accept_lens:
            return None
        try:
            lens = [int(value) for value in accept_lens]
        except (TypeError, ValueError):
            return None
        rounds = len(lens)
        if rounds == 0:
            return None
        accepted_tokens = sum(lens)
        if accepted_tokens < 0:
            return None
        max_per_round = int(draft_block_size or 0) - 1
        if max_per_round <= 0:
            return None
        attempted_tokens = rounds * max_per_round
        rejected_tokens = max(0, attempted_tokens - accepted_tokens)
        acceptance_rate = accepted_tokens / attempted_tokens
        return {
            "acceptance_rate": acceptance_rate,
            "rollback_rate": rejected_tokens / attempted_tokens,
            "accepted_tokens": accepted_tokens,
            "rejected_tokens": rejected_tokens,
        }

    def last_probe_snapshot(self) -> VisionProbeSnapshot:
        probe = self._last_probe
        stats_kwargs: dict[str, float | int] = {}
        for loaded_model in self._loaded_models_with_schedulers:
            if not isinstance(loaded_model, dict):
                continue
            scheduler = loaded_model.get("_melix_text_only_batch_generator_scheduler")
            if isinstance(scheduler, _TextOnlyBatchGeneratorScheduler):
                stats_kwargs = _text_batch_generator_probe_kwargs(
                    _text_batch_generator_stats_snapshot(scheduler)
                )
        return replace(probe, **stats_kwargs) if stats_kwargs else probe

    def _ensure_fast_path_probe(
        self,
        loaded_model,
        prepared_request: PreparedVisionRequest,
    ) -> None:
        """Call plan() when generate_tokens() did not follow render_prompt().

        The signature guard deduplicates the normal render_prompt/generate_tokens
        sequence for one prepared request. If shared-runtime tests reuse identical
        multimodal_hash_hex and model metadata for different requests, the second
        request can inherit the previous probe's cache counts; production request
        hashes should include real prompt and media identity, so the edge case is
        metrics-only and does not affect generated data.
        """
        signature = fast_path_probe_signature(loaded_model, prepared_request)
        if self._last_fast_path_signature == signature:
            return
        self._record_fast_path_probe(loaded_model, prepared_request, signature=signature)

    def _record_fast_path_probe(
        self,
        loaded_model,
        prepared_request: PreparedVisionRequest,
        *,
        signature: tuple[str, ...] | None = None,
    ) -> None:
        signature = signature or fast_path_probe_signature(
            loaded_model,
            prepared_request,
        )
        if self._last_fast_path_signature == signature and not prepared_request.images and not prepared_request.videos:
            return
        fast_path = self._fast_path_controller.plan(loaded_model, prepared_request)
        self._last_fast_path_signature = signature
        self._last_probe = VisionProbeSnapshot(
            preprocess_latency_ms=prepared_request.preprocess_latency_ms,
            preprocess_input_bytes=prepared_request.preprocess_input_bytes,
            preprocess_peak_memory_bytes=prepared_request.preprocess_peak_memory_bytes,
            first_token_latency_ms=0.0,
            video_effective_frame_count=prepared_request.effective_video_frame_count,
            video_requested_frame_budget=prepared_request.requested_video_frame_budget,
            video_window_ms=prepared_request.effective_video_window_ms,
            cache_identity="",
            cache_scope_id="",
            cache_hit=False,
            image_feature_cache_hits=fast_path.image_feature_cache_hits,
            image_feature_cache_misses=fast_path.image_feature_cache_misses,
            multimodal_decode_mode=fast_path.multimodal_decode_mode,
            multimodal_fallback_reason=fast_path.multimodal_fallback_reason,
            multimodal_decode_sync_mode=fast_path.multimodal_decode_sync_mode,
            multi_image_scatter_mode=fast_path.multi_image_scatter_mode,
            quantized_load_mode=fast_path.quantized_load_mode,
            quantized_load_fallback_reason=fast_path.quantized_load_fallback_reason,
        )

    @staticmethod
    def _materialize_media(
        prepared_request: PreparedVisionRequest,
        temp_media_session: TempMediaSession,
    ) -> MaterializedMediaPaths:
        image_paths: list[str] = []
        for index, image in enumerate(prepared_request.images):
            suffix = MLXVLMRuntime._media_suffix(image.filename, image.format)
            image_path = temp_media_session.write_bytes(f"image-{index}.{suffix}", image.bytes_data)
            image_paths.append(str(image_path))
        video_paths: list[str] = []
        for index, video in enumerate(prepared_request.videos):
            if not video.bytes_data:
                continue
            suffix = MLXVLMRuntime._media_suffix(video.filename, video.format)
            video_path = temp_media_session.write_bytes(f"video-{index}.{suffix}", video.bytes_data)
            video_paths.append(str(video_path))
        return MaterializedMediaPaths(image_paths=tuple(image_paths), video_paths=tuple(video_paths))

    @staticmethod
    def _media_suffix(filename: str, format_name: str) -> str:
        if format_name:
            return format_name
        if "." in filename:
            return filename.rsplit(".", 1)[-1]
        return "bin"

    @staticmethod
    def _family_config(loaded_model) -> Any:
        metadata: dict[str, str] = {}
        if isinstance(loaded_model, dict):
            cached_config = loaded_model.get("_vision_family_config")
            if cached_config is not None:
                return cached_config
            raw_metadata = loaded_model.get("metadata")
            if isinstance(raw_metadata, dict):
                metadata = {
                    str(key): str(value)
                    for key, value in raw_metadata.items()
                }
        family_config = resolve_vision_family_config(metadata)
        if isinstance(loaded_model, dict):
            loaded_model["_vision_family_config"] = family_config
        return family_config

    @staticmethod
    def _prompt_text_and_media_presence(messages) -> tuple[str, bool]:
        prompt_segments: list[str] = []
        has_non_text_media = False
        for message in messages:
            for part in message.parts:
                text = str(getattr(part, "text", "") or "").strip()
                if text:
                    prompt_segments.append(text)
                if not has_non_text_media:
                    if getattr(part, "image_bytes", b"") or getattr(part, "image_uri", ""):
                        has_non_text_media = True
                    elif getattr(part, "video_bytes", b"") or getattr(part, "video_uri", ""):
                        has_non_text_media = True
        return "\n".join(prompt_segments).strip(), has_non_text_media

    @staticmethod
    def _prompt_text_from_messages(messages) -> str:
        prompt_text, _ = MLXVLMRuntime._prompt_text_and_media_presence(messages)
        return prompt_text

    @staticmethod
    def _replace_prompt_text(
        prepared_request: PreparedVisionRequest,
        *,
        prompt_text: str,
    ) -> PreparedVisionRequest:
        normalized_prompt_text = prompt_text.strip()
        prompt_hash_hex = hashlib.sha256(normalized_prompt_text.encode("utf-8")).hexdigest()
        return replace(
            prepared_request,
            prompt_text=normalized_prompt_text,
            prompt_hash_hex=prompt_hash_hex,
            multimodal_hash_hex=rebuild_multimodal_hash(prepared_request, prompt_hash_hex),
        )

    @staticmethod
    def _prompt_only_request(
        messages,
        *,
        family_config,
        started_at: float,
        prompt_text: str | None = None,
        include_chat_messages: bool = False,
    ) -> PreparedVisionRequest:
        if prompt_text is None:
            prompt_text = MLXVLMRuntime._prompt_text_from_messages(messages)
        chat_messages = (
            MLXVLMRuntime._chat_messages_for_text_only_template(messages)
            if include_chat_messages
            else ()
        )
        prepared = PreparedVisionRequest(
            prompt_text=prompt_text,
            images=[],
            videos=[],
            video_frame_policies=[],
            preprocess_latency_ms=max(0.0, (time.perf_counter() - started_at) * 1000.0),
            preprocess_input_bytes=len(prompt_text.encode("utf-8")),
            preprocess_peak_memory_bytes=0,
            chat_messages=chat_messages,
        )
        prepared = family_config.shape_request(prepared)
        prompt_hash_hex = hashlib.sha256(prepared.prompt_text.encode("utf-8")).hexdigest()
        return replace(
            prepared,
            prompt_hash_hex=prompt_hash_hex,
            multimodal_hash_hex=prompt_hash_hex,
        )

    @staticmethod
    def _chat_messages_for_text_only_template(messages) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "role": str(getattr(message, "role", "user") or "user"),
                "content": " ".join(
                    str(getattr(part, "text", "") or "").strip()
                    for part in getattr(message, "parts", ())
                    if str(getattr(part, "text", "") or "").strip()
                ),
            }
            for message in messages
        )

    @staticmethod
    def _text_backed_video_prompt(prepared_request: PreparedVisionRequest) -> str:
        prompt_text = prepared_request.prompt_text or "Describe the video."
        video_lines = [
            (
                f"Video {index + 1}: {video.filename};"
                f" format={video.format};"
                f" frames={policy.effective_frame_count};"
                f" start_ms={policy.clip_start_ms};"
                f" end_ms={policy.clip_end_ms}"
            )
            for index, (video, policy) in enumerate(
                zip(prepared_request.videos, prepared_request.video_frame_policies, strict=False)
            )
        ]
        video_lines.append(f"Prompt: {prompt_text}")
        return "\n".join(video_lines)
