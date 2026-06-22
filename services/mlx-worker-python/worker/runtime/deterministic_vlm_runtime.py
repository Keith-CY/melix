from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import json
from pathlib import Path
from threading import Event
from typing import Callable

from packages.protocol.python.worker.v1 import cache_pb2, common_pb2

from worker.runtime.multimodal_attention_policy import (
    AttentionPrefillPolicyDecision,
    build_attention_budget_receipt,
    enforce_attention_prefill_policy,
    int_metadata as _int_metadata,
    resolve_configured_attention_prefill_policy,
)
from worker.runtime.deterministic_delay import sleep_if_configured
from worker.runtime.deterministic_probe_mixin import DeterministicProbeMixin
from worker.runtime.mlx_text_runtime import RuntimeTokenEvent, RuntimeToolCallEvent
from worker.runtime.multimodal_fast_paths import MultimodalFastPathController, fast_path_probe_signature
from worker.runtime.multimodal_position_receipts import (
    NO_MEDIA_HYBRID_STATE_PATCH_RECEIPT,
    build_hybrid_state_patch_receipt,
    build_position_metadata_receipt,
    empty_hybrid_state_patch_receipt,
    empty_quantized_kv_mask_receipt,
)
from worker.runtime.multimodal_preprocessing import PreparedVisionRequest, prepare_vision_request
from worker.runtime.temp_media_lifecycle import TempMediaSession
from worker.runtime.token_counting import whitespace_token_count as _whitespace_token_count
from worker.runtime.vision_family_adapters import (
    resolve_vision_family_config,
    vision_processor_capability_metadata,
)

_EMPTY_PROCESSOR_SHAPE_RECEIPT: dict[str, object] = {}
_TEXT_ONLY_EMPTY_MODEL_FAST_PATH_SIGNATURE = (
    "(('model_id', ''), ('quant_profile_id', ''), "
    "('revision', ''), ('tokenizer_hash', ''))"
)


def _has_only_internal_fast_path_signature_metadata(loaded_model) -> bool:
    return isinstance(loaded_model, dict) and (
        not loaded_model
        or (len(loaded_model) == 1 and "_vision_family_config" in loaded_model)
    )


@dataclass(frozen=True, slots=True)
class VisionProbeSnapshot:
    preprocess_latency_ms: float
    preprocess_input_bytes: int
    preprocess_peak_memory_bytes: int
    first_token_latency_ms: float
    video_effective_frame_count: int = 0
    video_requested_frame_budget: int = 0
    video_window_ms: int = 0
    temp_media_artifact_count: int = 0
    temp_media_artifact_bytes: int = 0
    temp_media_cleanup_latency_ms: float = 0.0
    temp_media_cleanup_failure_count: int = 0
    cache_identity: str = ""
    cache_scope_id: str = ""
    cache_hit: bool = False
    image_feature_cache_hits: int = 0
    image_feature_cache_misses: int = 0
    multimodal_decode_mode: str = "baseline"
    multimodal_fallback_reason: str = "not_reported"
    multimodal_decode_sync_mode: str = "baseline"
    multi_image_scatter_mode: str = "none"
    multimodal_position_slice_fallback_count: int = 0
    quantized_load_mode: str = "fallback"
    quantized_load_fallback_reason: str = "not_reported"
    hybrid_state_patch_mode: str = "not_reported"
    hybrid_state_advance_count: int = 0
    family_fast_path_override_count: int = 0
    attention_budget_receipt: dict[str, object] = field(default_factory=dict)
    position_metadata_receipt: dict[str, object] = field(
        default_factory=lambda: build_position_metadata_receipt()
    )
    quantized_kv_mask_receipt: dict[str, object] = field(
        default_factory=empty_quantized_kv_mask_receipt
    )
    hybrid_state_patch_receipt: dict[str, object] = field(
        default_factory=empty_hybrid_state_patch_receipt
    )
    text_batch_generator_submitted_request_count: int = 0
    text_batch_generator_completed_request_count: int = 0
    text_batch_generator_step_count: int = 0
    text_batch_generator_generated_token_count: int = 0
    text_batch_generator_peak_active_batch_size: int = 0
    text_batch_generator_queue_wait_ms_total: float = 0.0
    text_batch_generator_insert_ms_total: float = 0.0
    text_batch_generator_executor_step_ms_total: float = 0.0
    text_batch_generator_next_ms_total: float = 0.0
    text_batch_generator_emit_ms_total: float = 0.0
    text_batch_generator_active_batch_size: int = 0
    text_batch_generator_generated_response_count: int = 0
    text_batch_generator_failed_request_count: int = 0
    text_batch_generator_prepare_ms_total: float = 0.0
    text_batch_generator_first_response_ms_total: float = 0.0
    text_batch_generator_first_visible_ms_total: float = 0.0
    text_batch_generator_first_visible_token_index_total: int = 0
    text_batch_generator_first_empty_segment_count: int = 0
    text_batch_generator_prefill_response_count: int = 0
    text_batch_generator_prefill_step_count: int = 0
    text_batch_generator_prefill_processed_token_count: int = 0
    text_batch_generator_prefill_total_token_count: int = 0
    text_batch_generator_prefill_completed_request_count: int = 0
    text_batch_generator_prefill_step_size: int = 0
    text_batch_generator_speculative_cycle_count_total: int = 0
    text_batch_generator_speculative_accepted_count_total: int = 0
    text_batch_generator_speculative_rejected_count_total: int = 0
    text_batch_generator_speculative_backbone_ms_total: float = 0.0
    text_batch_generator_speculative_mtp_head_ms_total: float = 0.0
    text_batch_generator_speculative_sample_ms_total: float = 0.0
    text_batch_generator_speculative_cache_ops_ms_total: float = 0.0


@dataclass(frozen=True, slots=True)
class VisionCacheEntry:
    cache_identity: str
    scope_id: str
    model_id: str
    revision: str
    tokenizer_hash: str
    quant_profile_id: str
    parser_mode: str
    reasoning_mode: str
    multimodal_adapter_hash: str
    prompt_hash_hex: str
    fingerprint_hash_hex: str
    bytes_used: int
    token_length: int


@dataclass(frozen=True, slots=True)
class VisionProbeSnapshotView:
    snapshot: VisionProbeSnapshot
    processor_shape_receipt: dict[str, object]

    def __getattr__(self, name: str) -> object:
        return getattr(self.snapshot, name)


@dataclass(frozen=True)
class VisionPrefillSession:
    decode_handle: str
    prepared_request: PreparedVisionRequest
    prompt_tokens: int
    response_text: str
    completion_tokens: int
    tool_call_event: RuntimeToolCallEvent | None
    cache_identity: str
    scope_id: str
    cache_hit: bool
    block_table_id: str
    block_table: common_pb2.BlockTable


@dataclass(frozen=True)
class PreparedVisionPrompt:
    prepared_request: PreparedVisionRequest
    family_config: object
    prompt_tokens: int
    cache_identity: str
    scope_id: str
    attention_policy: AttentionPrefillPolicyDecision | None


class DeterministicVLMRuntime(DeterministicProbeMixin[VisionProbeSnapshot]):
    runtime_name = "deterministic-vlm"

    def __init__(
        self,
        temp_root: Path | str | None = None,
        temp_media_session_factory: Callable[..., TempMediaSession] | None = None,
    ) -> None:
        self._temp_root = Path(temp_root) if temp_root is not None else None
        self._temp_media_session_factory = temp_media_session_factory or TempMediaSession
        self._last_probe = VisionProbeSnapshot(0.0, 0, 0, 0.0)
        self._last_processor_shape_receipt = _EMPTY_PROCESSOR_SHAPE_RECEIPT
        self._cache_entries: dict[str, VisionCacheEntry] = {}
        self._decode_sessions: dict[str, VisionPrefillSession] = {}
        self._cache_lookups = 0
        self._cache_hits = 0
        self._cache_l1_bytes = 0
        self._cache_snapshot: cache_pb2.CacheSnapshot | None = None
        self._fast_path_controller = MultimodalFastPathController()
        self._last_fast_path_signature: tuple[str, ...] | None = None
        self._last_attention_policy_signature: tuple[str, ...] | None = None
        self._last_attention_policy: AttentionPrefillPolicyDecision | None = None
        self._last_completion_token_text = ""
        self._last_completion_token_count = 0

    def last_probe_snapshot(self) -> VisionProbeSnapshot | VisionProbeSnapshotView:
        if self._last_processor_shape_receipt:
            return VisionProbeSnapshotView(
                self._last_probe,
                self._last_processor_shape_receipt,
            )
        return self._last_probe

    def load_model(self, model_spec):
        ext = dict(model_spec.ext)
        family_config = resolve_vision_family_config(ext)
        metadata = {
            **ext,
            **family_config.capability_metadata(),
            **vision_processor_capability_metadata(ext),
            "melix.vlm.execution_mode": ext.get(
                "melix.vlm.execution_mode",
                "multimodal",
            ).strip()
            or "multimodal",
        }
        return {
            "model_id": model_spec.model_id,
            "model_kind": model_spec.model_kind,
            "revision": model_spec.revision,
            "tokenizer_hash": model_spec.tokenizer_hash,
            "quant_profile_id": model_spec.quant_profile_id,
            "parser_mode": model_spec.parser_mode,
            "reasoning_mode": model_spec.reasoning_mode,
            "metadata": metadata,
            **metadata,
        }

    def estimate_resident_bytes(self, model_spec):
        return 4096

    def close_loaded_model(self, loaded_model) -> None:
        model_id = self._metadata_value(loaded_model, "model_id", "")
        if not model_id:
            self._clear_cache_entries(tuple(self._cache_entries))
            return

        evicted_identities = tuple(
            cache_identity
            for cache_identity, entry in self._cache_entries.items()
            if entry.model_id == model_id
            and entry.revision == self._metadata_value(loaded_model, "revision", entry.revision)
            and entry.tokenizer_hash
            == self._metadata_value(loaded_model, "tokenizer_hash", entry.tokenizer_hash)
            and entry.quant_profile_id
            == self._metadata_value(loaded_model, "quant_profile_id", entry.quant_profile_id)
        )
        self._clear_cache_entries(evicted_identities)

    def render_prompt(
        self,
        messages,
        loaded_model=None,
        template_kwargs=None,
        execution_ext: dict[str, str] | None = None,
    ) -> PreparedVisionRequest:
        _ = template_kwargs
        prompt = self._prepare_prompt(
            messages,
            loaded_model=loaded_model,
            execution_ext=execution_ext,
        )
        self._record_fast_path_probe(
            loaded_model,
            prompt.prepared_request,
            seq_len=prompt.prompt_tokens,
            attention_policy=prompt.attention_policy,
        )
        self._last_probe = replace(
            self._last_probe,
            cache_identity=prompt.cache_identity,
            cache_scope_id=prompt.scope_id,
            cache_hit=prompt.cache_identity in self._cache_entries,
        )
        return prompt.prepared_request

    def prompt_token_count(
        self,
        prepared_request: PreparedVisionRequest,
        loaded_model=None,
        family_config: object | None = None,
    ) -> int:
        config = family_config if family_config is not None else self._family_config(loaded_model)
        return config.prompt_token_count(prepared_request)

    def prefill(
        self,
        request_id: str,
        loaded_model,
        messages,
        prefill_step_size: int = 0,
        execution_ext: dict[str, str] | None = None,
    ) -> VisionPrefillSession:
        prompt = self._prepare_prompt(
            messages,
            loaded_model=loaded_model,
            requested_prefill_step_size=prefill_step_size,
            execution_ext=execution_ext,
        )
        prepared_request = prompt.prepared_request
        prompt_tokens = prompt.prompt_tokens
        cache_identity = prompt.cache_identity
        scope_id = prompt.scope_id
        self._ensure_fast_path_probe(
            loaded_model,
            prepared_request,
            seq_len=prompt_tokens,
            attention_policy=prompt.attention_policy,
        )
        enforce_attention_prefill_policy(prompt.attention_policy)
        self._cache_lookups += 1
        cache_hit = cache_identity in self._cache_entries
        if cache_hit:
            self._cache_hits += 1
        else:
            self._record_cache_entry(
                self._cache_entry(
                    loaded_model=loaded_model,
                    prepared_request=prepared_request,
                    cache_identity=cache_identity,
                    scope_id=scope_id,
                    fingerprint_hash_hex=self._cache_identity_fingerprint_hash_hex(
                        cache_identity=cache_identity,
                        prepared_request=prepared_request,
                    ),
                    token_length=prompt_tokens,
                    execution_ext=execution_ext,
                )
            )
        block_table_id = f"vlm-block:{cache_identity[:16]}"
        block_table = self._block_table_for(
            prepared_request=prepared_request,
            cache_identity=cache_identity,
            scope_id=scope_id,
            prompt_tokens=prompt_tokens,
        )
        decode_handle = f"vlm:{request_id}"
        response_text = self._response_text(prepared_request)
        tool_call_event = self._tool_call_event(
            prepared_request,
            loaded_model,
            execution_ext,
        )
        session = VisionPrefillSession(
            decode_handle=decode_handle,
            prepared_request=prepared_request,
            prompt_tokens=prompt_tokens,
            response_text=response_text,
            completion_tokens=self._completion_token_count(response_text),
            tool_call_event=tool_call_event,
            cache_identity=cache_identity,
            scope_id=scope_id,
            cache_hit=cache_hit,
            block_table_id=block_table_id,
            block_table=block_table,
        )
        self._decode_sessions[decode_handle] = session
        self._last_probe = replace(
            self._last_probe,
            preprocess_latency_ms=prepared_request.preprocess_latency_ms,
            preprocess_input_bytes=prepared_request.preprocess_input_bytes,
            preprocess_peak_memory_bytes=prepared_request.preprocess_peak_memory_bytes,
            first_token_latency_ms=0.0,
            video_effective_frame_count=prepared_request.effective_video_frame_count,
            video_requested_frame_budget=prepared_request.requested_video_frame_budget,
            video_window_ms=prepared_request.effective_video_window_ms,
            cache_identity=cache_identity,
            cache_scope_id=scope_id,
            cache_hit=cache_hit,
        )
        return session

    def decode_tokens(
        self,
        loaded_model,
        decode_handle: str,
        sampling,
        cancel_event: Event,
        execution_ext: dict[str, str] | None = None,
    ):
        _ = sampling
        _ = execution_ext
        session = self._decode_sessions.pop(decode_handle, None)
        if session is None:
            raise KeyError(f"Unknown decode handle: {decode_handle}")
        self._last_probe = replace(
            self._last_probe,
            preprocess_latency_ms=session.prepared_request.preprocess_latency_ms,
            preprocess_input_bytes=session.prepared_request.preprocess_input_bytes,
            preprocess_peak_memory_bytes=session.prepared_request.preprocess_peak_memory_bytes,
            first_token_latency_ms=(
                max(0.0, session.prepared_request.preprocess_latency_ms / 4.0)
                if session.cache_hit
                else max(0.0, session.prepared_request.preprocess_latency_ms / 2.0)
            ),
            video_effective_frame_count=session.prepared_request.effective_video_frame_count,
            video_requested_frame_budget=session.prepared_request.requested_video_frame_budget,
            video_window_ms=session.prepared_request.effective_video_window_ms,
            cache_identity=session.cache_identity,
            cache_scope_id=session.scope_id,
            cache_hit=session.cache_hit,
        )
        sleep_if_configured("vlm")
        if cancel_event.is_set():
            return
        if session.tool_call_event is not None:
            yield session.tool_call_event
            if cancel_event.is_set():
                return
        yield RuntimeTokenEvent(
            text=session.response_text,
            prompt_tokens=session.prompt_tokens,
            completion_tokens=session.completion_tokens,
            finish_reason="stop",
        )

    def generate_tokens(
        self,
        loaded_model,
        prepared_request: PreparedVisionRequest,
        sampling,
        cancel_event: Event,
        execution_ext: dict[str, str] | None = None,
    ):
        (
            attention_policy,
            self._last_attention_policy_signature,
            self._last_attention_policy,
        ) = resolve_configured_attention_prefill_policy(
            loaded_model=loaded_model,
            prepared_request=prepared_request,
            family_config_resolver=self._family_config,
            prompt_token_counter=self.prompt_token_count,
            cached_signature=self._last_attention_policy_signature,
            cached_decision=self._last_attention_policy,
            execution_ext=execution_ext,
        )
        enforce_attention_prefill_policy(attention_policy)
        prompt_tokens = (
            attention_policy.prompt_tokens
            if attention_policy is not None
            else self.prompt_token_count(prepared_request, loaded_model=loaded_model)
        )
        self._ensure_fast_path_probe(
            loaded_model,
            prepared_request,
            seq_len=prompt_tokens,
            attention_policy=attention_policy,
        )
        response = self._response_text(prepared_request)
        cache_identity, scope_id = self._cache_identity(
            prepared_request,
            loaded_model,
            execution_ext=execution_ext,
        )
        self._cache_lookups += 1
        cache_hit = cache_identity in self._cache_entries
        if cache_hit:
            self._cache_hits += 1
        else:
            self._record_cache_entry(
                self._cache_entry(
                    loaded_model=loaded_model,
                    prepared_request=prepared_request,
                    cache_identity=cache_identity,
                    scope_id=scope_id,
                    fingerprint_hash_hex=self._cache_identity_fingerprint_hash_hex(
                        cache_identity=cache_identity,
                        prepared_request=prepared_request,
                    ),
                    token_length=prompt_tokens,
                    execution_ext=execution_ext,
                )
            )
        self._last_probe = replace(
            self._last_probe,
            preprocess_latency_ms=prepared_request.preprocess_latency_ms,
            preprocess_input_bytes=prepared_request.preprocess_input_bytes,
            preprocess_peak_memory_bytes=prepared_request.preprocess_peak_memory_bytes,
            first_token_latency_ms=(
                max(0.0, prepared_request.preprocess_latency_ms / 4.0)
                if cache_hit
                else max(0.0, prepared_request.preprocess_latency_ms / 2.0)
            ),
            video_effective_frame_count=prepared_request.effective_video_frame_count,
            video_requested_frame_budget=prepared_request.requested_video_frame_budget,
            video_window_ms=prepared_request.effective_video_window_ms,
            cache_identity=cache_identity,
            cache_scope_id=scope_id,
            cache_hit=cache_hit,
        )
        if not prepared_request.images and not prepared_request.videos:
            sleep_if_configured("vlm")
            if cancel_event.is_set():
                return
            tool_call_event = self._tool_call_event(
                prepared_request,
                loaded_model,
                execution_ext,
            )
            if tool_call_event is not None:
                yield tool_call_event
                if cancel_event.is_set():
                    return
            yield RuntimeTokenEvent(
                text=response,
                prompt_tokens=prompt_tokens,
                completion_tokens=self._completion_token_count(response),
                finish_reason="stop",
            )
            return
        temp_media_session = self._temp_media_session_factory(
            temp_root=self._temp_root,
            prefix="melix-vlm-",
        )
        self._stage_temp_media(prepared_request, temp_media_session)
        try:
            sleep_if_configured("vlm")
            if cancel_event.is_set():
                return
            tool_call_event = self._tool_call_event(
                prepared_request,
                loaded_model,
                execution_ext,
            )
            if tool_call_event is not None:
                yield tool_call_event
                if cancel_event.is_set():
                    return
            yield RuntimeTokenEvent(
                text=response,
                prompt_tokens=prompt_tokens,
                completion_tokens=self._completion_token_count(response),
                finish_reason="stop",
            )
        finally:
            cleanup_report = temp_media_session.cleanup()
            self._last_probe = replace(
                self._last_probe,
                temp_media_artifact_count=cleanup_report.artifact_count,
                temp_media_artifact_bytes=cleanup_report.artifact_bytes,
                temp_media_cleanup_latency_ms=cleanup_report.cleanup_latency_ms,
                temp_media_cleanup_failure_count=cleanup_report.cleanup_failure_count,
            )

    def _completion_token_count(self, response_text: str) -> int:
        if response_text == self._last_completion_token_text:
            return self._last_completion_token_count
        token_count = max(1, _whitespace_token_count(response_text))
        self._last_completion_token_text = response_text
        self._last_completion_token_count = token_count
        return token_count

    def _ensure_fast_path_probe(
        self,
        loaded_model,
        prepared_request: PreparedVisionRequest,
        *,
        seq_len: int | None = None,
        attention_policy: AttentionPrefillPolicyDecision | None = None,
    ) -> None:
        signature = self._fast_path_probe_signature(loaded_model, prepared_request)
        if self._last_fast_path_signature == signature:
            return
        self._record_fast_path_probe(
            loaded_model,
            prepared_request,
            signature=signature,
            seq_len=seq_len,
            attention_policy=attention_policy,
        )

    def _record_fast_path_probe(
        self,
        loaded_model,
        prepared_request: PreparedVisionRequest,
        *,
        signature: tuple[str, ...] | None = None,
        seq_len: int | None = None,
        attention_policy: AttentionPrefillPolicyDecision | None = None,
    ) -> None:
        fast_path = self._fast_path_controller.plan(loaded_model, prepared_request)
        attention_decision = attention_policy
        if attention_decision is None:
            (
                attention_decision,
                self._last_attention_policy_signature,
                self._last_attention_policy,
            ) = resolve_configured_attention_prefill_policy(
                loaded_model=loaded_model,
                prepared_request=prepared_request,
                seq_len=seq_len,
                family_config_resolver=self._family_config,
                prompt_token_counter=self.prompt_token_count,
                cached_signature=self._last_attention_policy_signature,
                cached_decision=self._last_attention_policy,
                execution_ext=None,
            )
        attention_budget_receipt = build_attention_budget_receipt(attention_decision)
        position_metadata_receipt = self._position_metadata_receipt(
            loaded_model=loaded_model,
            prepared_request=prepared_request,
            fallback_reason=fast_path.multimodal_fallback_reason,
            seq_len=seq_len,
        )
        hybrid_seq_len = int(position_metadata_receipt["seq_len"])
        if fast_path.hybrid_state_patch_mode == "not_applicable" and not (
            prepared_request.images or prepared_request.videos
        ):
            hybrid_state_patch_receipt = NO_MEDIA_HYBRID_STATE_PATCH_RECEIPT
        else:
            hybrid_state_patch_receipt = self._hybrid_state_patch_receipt(
                loaded_model=loaded_model,
                prepared_request=prepared_request,
                patch_mode=fast_path.hybrid_state_patch_mode,
                fallback_reason=fast_path.multimodal_fallback_reason,
                family_fast_path_override_count=fast_path.family_fast_path_override_count,
                seq_len=hybrid_seq_len,
            )
        self._last_fast_path_signature = signature or self._fast_path_probe_signature(
            loaded_model,
            prepared_request,
        )
        processor_shape_receipt = (
            self._processor_shape_receipt(
                loaded_model=loaded_model,
                prepared_request=prepared_request,
            )
            if prepared_request.images or prepared_request.videos
            else _EMPTY_PROCESSOR_SHAPE_RECEIPT
        )
        self._last_processor_shape_receipt = processor_shape_receipt
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
            hybrid_state_patch_mode=fast_path.hybrid_state_patch_mode,
            hybrid_state_advance_count=(
                0
                if fast_path.hybrid_state_patch_mode == "not_applicable"
                else int(hybrid_state_patch_receipt["cache_advance_count"])
            ),
            family_fast_path_override_count=fast_path.family_fast_path_override_count,
            attention_budget_receipt=attention_budget_receipt,
            position_metadata_receipt=position_metadata_receipt,
            quantized_kv_mask_receipt=empty_quantized_kv_mask_receipt(),
            hybrid_state_patch_receipt=hybrid_state_patch_receipt,
        )

    @staticmethod
    def _fast_path_probe_signature(
        loaded_model,
        prepared_request: PreparedVisionRequest,
    ) -> tuple[str, ...]:
        if (
            not prepared_request.images
            and not prepared_request.videos
            and _has_only_internal_fast_path_signature_metadata(loaded_model)
        ):
            return (
                prepared_request.multimodal_hash_hex,
                _TEXT_ONLY_EMPTY_MODEL_FAST_PATH_SIGNATURE,
                "()",
            )
        return fast_path_probe_signature(loaded_model, prepared_request)

    def _processor_shape_receipt(
        self,
        *,
        loaded_model,
        prepared_request: PreparedVisionRequest,
    ) -> dict[str, object]:
        image_count = len(prepared_request.images)
        video_count = len(prepared_request.videos)
        return {
            "processor_policy": self._metadata_value(loaded_model, "vision_processor_policy", ""),
            "media_count": image_count + video_count,
            "image_count": image_count,
            "video_count": video_count,
            "crop_grid": self._metadata_value(loaded_model, "vision_processor_crop_grid", ""),
            "patch_size": self._metadata_value(loaded_model, "vision_processor_patch_size", ""),
            "max_crop_count": self._metadata_int_value(
                loaded_model,
                "vision_processor_max_crop_count",
                0,
            ),
            "prompt_format": self._metadata_value(loaded_model, "vision_prompt_format", ""),
            "projected_feature_shape": self._metadata_value(
                loaded_model,
                "vision_projected_feature_shape",
                "",
            ),
        }

    def _position_metadata_receipt(
        self,
        *,
        loaded_model,
        prepared_request: PreparedVisionRequest,
        fallback_reason: str,
        seq_len: int | None = None,
    ) -> dict[str, object]:
        if seq_len is None:
            seq_len = self.prompt_token_count(prepared_request, loaded_model=loaded_model)
        return build_position_metadata_receipt(
            prepared_request=prepared_request,
            seq_len=seq_len,
            fallback_reason=fallback_reason,
        )

    def _hybrid_state_patch_receipt(
        self,
        *,
        loaded_model,
        prepared_request: PreparedVisionRequest,
        patch_mode: str,
        fallback_reason: str,
        family_fast_path_override_count: int,
        seq_len: int,
    ) -> dict[str, object]:
        media_count = (
            len(prepared_request.images)
            + prepared_request.effective_video_frame_count
            + (
                len(prepared_request.videos)
                if prepared_request.videos and prepared_request.effective_video_frame_count <= 0
                else 0
            )
        )
        cache_advance = (
            max(0, int(seq_len or 0))
            if patch_mode not in {"fallback", "not_applicable"}
            else 0
        )
        expected_cache_advance = 0 if patch_mode == "not_applicable" else seq_len
        expected_contiguous_state_end = (
            0 if patch_mode == "not_applicable" else seq_len
        )
        row = {
            "row_index": 0,
            "seq_len": seq_len,
            "cache_offset": 0,
            "cache_advance": cache_advance,
            "expected_cache_advance": expected_cache_advance,
            "media_count": media_count,
            "contiguous_state_start": 0,
            "contiguous_state_end": cache_advance,
            "expected_contiguous_state_start": 0,
            "expected_contiguous_state_end": expected_contiguous_state_end,
            "text_only_rope_mode": "multimodal" if media_count else "text_only",
        }
        return build_hybrid_state_patch_receipt(
            family_id=self._metadata_value(loaded_model, "vision_family_id", "llava-v1"),
            patch_mode=patch_mode,
            fallback_reason=fallback_reason,
            family_fast_path_override_count=family_fast_path_override_count,
            rows=[row],
        )

    def cache_stats_response(self) -> cache_pb2.GetCacheStatsResponse:
        response = cache_pb2.GetCacheStatsResponse()
        lookup_count = max(1, self._cache_lookups)
        response.stats.l1_bytes = self._cache_l1_bytes
        response.stats.block_count = len(self._cache_entries)
        response.stats.l1_hit_rate = self._cache_hits / lookup_count
        response.stats.dedup_ratio = 1.0 - (response.stats.block_count / lookup_count)
        response.stats.active_mode = common_pb2.CACHE_MODE_TIERED
        response.snapshot.stats.CopyFrom(response.stats)
        snapshot = self._cache_snapshot_message()
        response.snapshot.hot_prefixes.extend(snapshot.hot_prefixes)
        response.snapshot.scopes.extend(snapshot.scopes)
        return response

    def _record_cache_entry(self, entry: VisionCacheEntry) -> None:
        self._cache_entries[entry.cache_identity] = entry
        self._cache_l1_bytes += entry.bytes_used
        self._cache_snapshot = None

    def _clear_cache_entries(self, cache_identities: tuple[str, ...]) -> None:
        if not cache_identities:
            return
        evicted = set(cache_identities)
        for cache_identity in evicted:
            self._cache_entries.pop(cache_identity, None)
        self._decode_sessions = {
            decode_handle: session
            for decode_handle, session in self._decode_sessions.items()
            if session.cache_identity not in evicted
        }
        self._cache_l1_bytes = sum(entry.bytes_used for entry in self._cache_entries.values())
        self._cache_snapshot = None

    def _cache_snapshot_message(self) -> cache_pb2.CacheSnapshot:
        if self._cache_snapshot is None:
            self._cache_snapshot = self._build_cache_snapshot()
        return self._cache_snapshot

    def _build_cache_snapshot(self) -> cache_pb2.CacheSnapshot:
        snapshot = cache_pb2.CacheSnapshot()
        scopes: dict[str, cache_pb2.CacheScopeSummary] = {}
        for entry in self._cache_entries.values():
            prefix = common_pb2.PrefixRef()
            prefix.prefix_id = entry.cache_identity[:16]
            prefix.token_length = entry.token_length
            prefix.tier = "ram"
            prefix.cache_key.prefix_hash = bytes.fromhex(entry.prompt_hash_hex)
            prefix.cache_key.fingerprint_hash = bytes.fromhex(entry.fingerprint_hash_hex)
            prefix.cache_key.scope_id = entry.scope_id
            prefix.scope.model_id = entry.model_id
            prefix.scope.revision = entry.revision
            prefix.scope.tokenizer_hash = entry.tokenizer_hash
            prefix.scope.quant_profile_id = entry.quant_profile_id
            prefix.scope.parser_mode = entry.parser_mode
            prefix.scope.reasoning_mode = entry.reasoning_mode
            prefix.scope.multimodal_adapter_hash = entry.multimodal_adapter_hash
            prefix.scope.scope_id = entry.scope_id
            snapshot.hot_prefixes.append(prefix)

            if entry.scope_id not in scopes:
                scope_summary = cache_pb2.CacheScopeSummary()
                scope_summary.scope_id = entry.scope_id
                scope_summary.scope.model_id = entry.model_id
                scope_summary.scope.revision = entry.revision
                scope_summary.scope.tokenizer_hash = entry.tokenizer_hash
                scope_summary.scope.quant_profile_id = entry.quant_profile_id
                scope_summary.scope.parser_mode = entry.parser_mode
                scope_summary.scope.reasoning_mode = entry.reasoning_mode
                scope_summary.scope.multimodal_adapter_hash = entry.multimodal_adapter_hash
                scope_summary.scope.scope_id = entry.scope_id
                scopes[entry.scope_id] = scope_summary
            scopes[entry.scope_id].l1_bytes += entry.bytes_used
            scopes[entry.scope_id].block_count += 1
            scopes[entry.scope_id].prefix_count += 1
            block = common_pb2.BlockRef(
                block_id=entry.cache_identity[:16],
                token_start=0,
                token_end=entry.token_length,
                bytes=entry.bytes_used,
            )
            scopes[entry.scope_id].hot_blocks.append(block)

        snapshot.scopes.extend(scopes.values())
        return snapshot

    def has_decode_session(self, decode_handle: str) -> bool:
        return decode_handle in self._decode_sessions

    def _cache_identity(
        self,
        prepared_request: PreparedVisionRequest,
        loaded_model,
        execution_ext: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        model_id = self._metadata_value(loaded_model, "model_id", "melix-dev-vlm")
        revision = self._metadata_value(loaded_model, "revision", "dev")
        quant_profile_id = self._metadata_value(loaded_model, "quant_profile_id", "q8")
        parser_mode = self._effective_parser_mode(loaded_model, execution_ext)
        reasoning_mode = self._metadata_value(loaded_model, "reasoning_mode", "off")
        if prepared_request.images or prepared_request.videos:
            fingerprint_hash_hex = self._cache_fingerprint_hash_hex(
                loaded_model=loaded_model,
                prepared_request=prepared_request,
            )
        else:
            fingerprint_hash_hex = prepared_request.multimodal_hash_hex
        identity = ":".join(
            [
                model_id,
                revision,
                quant_profile_id,
                parser_mode,
                reasoning_mode,
                fingerprint_hash_hex,
            ]
        )
        return identity, f"{model_id}:{fingerprint_hash_hex[:16]}"

    @staticmethod
    def _cache_identity_fingerprint_hash_hex(
        *,
        cache_identity: str,
        prepared_request: PreparedVisionRequest,
    ) -> str:
        if prepared_request.images or prepared_request.videos:
            return cache_identity.split(":")[-1]
        return prepared_request.multimodal_hash_hex

    def _block_table_for(
        self,
        prepared_request: PreparedVisionRequest,
        cache_identity: str,
        scope_id: str,
        prompt_tokens: int,
    ) -> common_pb2.BlockTable:
        cache_entry = self._cache_entries[cache_identity]
        cache_key = common_pb2.CacheKey(
            prefix_hash=bytes.fromhex(prepared_request.prompt_hash_hex),
            fingerprint_hash=bytes.fromhex(cache_entry.fingerprint_hash_hex),
            scope_id=scope_id,
        )
        block = common_pb2.BlockRef(
            block_id=cache_identity[:16],
            token_start=0,
            token_end=prompt_tokens,
            bytes=cache_entry.bytes_used,
        )
        page = common_pb2.PageRef(
            page_id=f"page:{cache_identity[:16]}",
            block_ids=[block.block_id],
            token_start=0,
            token_end=prompt_tokens,
            bytes=cache_entry.bytes_used,
        )
        return common_pb2.BlockTable(
            blocks=[block],
            cache_key=cache_key,
            scope_id=scope_id,
            pages=[page],
            total_token_count=prompt_tokens,
        )

    def _cache_entry(
        self,
        loaded_model,
        prepared_request: PreparedVisionRequest,
        cache_identity: str,
        scope_id: str,
        fingerprint_hash_hex: str,
        token_length: int | None = None,
        execution_ext: dict[str, str] | None = None,
    ) -> VisionCacheEntry:
        prompt_bytes = len(prepared_request.prompt_text.encode("utf-8"))
        token_length = token_length if token_length is not None else self.prompt_token_count(prepared_request)
        bytes_used = max(
            64,
            prepared_request.preprocess_input_bytes + prompt_bytes + (token_length * 8),
        )
        return VisionCacheEntry(
            cache_identity=cache_identity,
            scope_id=scope_id,
            model_id=self._metadata_value(loaded_model, "model_id", "melix-dev-vlm"),
            revision=self._metadata_value(loaded_model, "revision", "dev"),
            tokenizer_hash=self._metadata_value(loaded_model, "tokenizer_hash", "tok-vlm-dev"),
            quant_profile_id=self._metadata_value(loaded_model, "quant_profile_id", "q8"),
            parser_mode=self._effective_parser_mode(loaded_model, execution_ext),
            reasoning_mode=self._metadata_value(loaded_model, "reasoning_mode", "off"),
            multimodal_adapter_hash=self._metadata_value(loaded_model, "multimodal_adapter_hash", ""),
            prompt_hash_hex=prepared_request.prompt_hash_hex,
            fingerprint_hash_hex=fingerprint_hash_hex,
            bytes_used=bytes_used,
            token_length=token_length,
        )

    def _cache_fingerprint_hash_hex(
        self,
        *,
        loaded_model,
        prepared_request: PreparedVisionRequest,
    ) -> str:
        digest = hashlib.sha256()
        for value in (
            prepared_request.multimodal_hash_hex,
            self._metadata_value(loaded_model, "vision_processor_policy", ""),
            self._metadata_value(loaded_model, "vision_processor_crop_grid", ""),
            self._metadata_value(loaded_model, "vision_processor_patch_size", ""),
            str(self._metadata_int_value(loaded_model, "vision_processor_max_crop_count", 0)),
            self._metadata_value(loaded_model, "vision_prompt_format", ""),
            self._metadata_value(loaded_model, "vision_projected_feature_shape", ""),
        ):
            digest.update(value.encode("utf-8"))
            digest.update(b"\0")
        return digest.hexdigest()

    @staticmethod
    def _response_text(prepared_request: PreparedVisionRequest) -> str:
        prompt_text = prepared_request.prompt_text or "Describe the image."
        if prepared_request.videos and not prepared_request.images:
            if len(prepared_request.videos) == 1:
                video = prepared_request.videos[0]
                policy = prepared_request.video_frame_policies[0]
                return (
                    f"Video content: {video.filename}\n"
                    f"Frame policy: {policy.sampling_strategy} {policy.effective_frame_count} frame(s)"
                    f" from {policy.clip_start_ms}ms to {policy.clip_end_ms}ms\n"
                    f"Prompt: {prompt_text}"
                )

            video_lines = [
                (
                    f"Video {index + 1}: {video.filename} "
                    f"[frames={policy.effective_frame_count};start_ms={policy.clip_start_ms};end_ms={policy.clip_end_ms}]"
                )
                for index, (video, policy) in enumerate(
                    zip(prepared_request.videos, prepared_request.video_frame_policies, strict=False)
                )
            ]
            video_lines.append(f"Prompt: {prompt_text}")
            return "\n".join(video_lines)

        if len(prepared_request.images) == 1:
            return f"Image content: {prepared_request.images[0].decoded_text()}\nPrompt: {prompt_text}"

        image_lines = [
            f"Image {index + 1} content: {image.decoded_text()}"
            for index, image in enumerate(prepared_request.images)
        ]
        for index, (video, policy) in enumerate(
            zip(prepared_request.videos, prepared_request.video_frame_policies, strict=False)
        ):
            image_lines.append(
                f"Video {index + 1}: {video.filename} "
                f"[frames={policy.effective_frame_count};start_ms={policy.clip_start_ms};end_ms={policy.clip_end_ms}]"
            )
        image_lines.append(f"Prompt: {prompt_text}")
        return "\n".join(image_lines)

    @staticmethod
    def _stage_temp_media(
        prepared_request: PreparedVisionRequest,
        temp_media_session: TempMediaSession,
    ) -> None:
        for index, image in enumerate(prepared_request.images):
            suffix = DeterministicVLMRuntime._media_suffix(image.filename, image.format)
            temp_media_session.write_bytes(f"image-{index}.{suffix}", image.bytes_data)
        for index, video in enumerate(prepared_request.videos):
            if not video.bytes_data:
                continue
            suffix = DeterministicVLMRuntime._media_suffix(video.filename, video.format)
            temp_media_session.write_bytes(f"video-{index}.{suffix}", video.bytes_data)

    @staticmethod
    def _media_suffix(filename: str, format_name: str) -> str:
        if format_name:
            return format_name
        if "." in filename:
            return filename.rsplit(".", 1)[-1]
        return "bin"

    def _tool_call_event(
        self,
        prepared_request: PreparedVisionRequest,
        loaded_model,
        execution_ext: dict[str, str] | None,
    ) -> RuntimeToolCallEvent | None:
        if not self._family_config(loaded_model).supports_tool_calls:
            return None
        parser_mode = (execution_ext or {}).get("melix.tool_parser.mode", "").strip()
        if not parser_mode:
            return None

        prompt_text = prepared_request.prompt_text or "Describe the image."
        if "tool" not in prompt_text.lower():
            return None

        namespaces = [
            item.strip()
            for item in (execution_ext or {}).get("melix.tool_parser.namespaces", "").split(",")
            if item.strip()
        ]
        tool_name = namespaces[0] if namespaces else "vision.inspect"
        arguments_json = json.dumps(
            {
                "prompt": prompt_text,
                "image_count": len(prepared_request.images),
            },
            separators=(",", ":"),
        )
        return RuntimeToolCallEvent(
            call_id=f"tool:{prepared_request.multimodal_hash_hex[:12]}",
            tool_name=tool_name,
            arguments_json_fragment=arguments_json,
        )

    def _effective_parser_mode(
        self,
        loaded_model,
        execution_ext: dict[str, str] | None,
    ) -> str:
        if execution_ext is not None:
            mode = execution_ext.get("melix.tool_parser.mode", "").strip()
            if mode:
                return mode
        return self._metadata_value(loaded_model, "parser_mode", "text")

    @staticmethod
    def _metadata_value(loaded_model, key: str, default: str) -> str:
        if isinstance(loaded_model, dict):
            value = loaded_model.get(key)
            if isinstance(value, str) and value:
                return value
        return default

    @staticmethod
    def _metadata_int_value(loaded_model, key: str, default: int) -> int:
        if isinstance(loaded_model, dict):
            value = _int_metadata(loaded_model, key)
            if value:
                return value
        return max(0, default)

    def _family_config(self, loaded_model) -> object:
        metadata: dict[str, str] = {}
        if isinstance(loaded_model, dict):
            cached_config = loaded_model.get("_vision_family_config")
            if cached_config is not None:
                return cached_config
            metadata = {
                key: value
                for key, value in loaded_model.items()
                if isinstance(value, str) and value
            }
        config = resolve_vision_family_config(metadata)
        if isinstance(loaded_model, dict):
            loaded_model["_vision_family_config"] = config
        return config

    def _prepare_prompt(
        self,
        messages,
        loaded_model=None,
        requested_prefill_step_size: int = 0,
        execution_ext: dict[str, str] | None = None,
    ) -> PreparedVisionPrompt:
        family_config = self._family_config(loaded_model)
        prepared_request = family_config.shape_request(prepare_vision_request(messages))
        cache_identity, scope_id = self._cache_identity(
            prepared_request,
            loaded_model,
            execution_ext=execution_ext,
        )
        prompt_tokens = self.prompt_token_count(
            prepared_request,
            loaded_model=loaded_model,
            family_config=family_config,
        )
        (
            attention_policy,
            self._last_attention_policy_signature,
            self._last_attention_policy,
        ) = resolve_configured_attention_prefill_policy(
            loaded_model=loaded_model,
            prepared_request=prepared_request,
            seq_len=prompt_tokens,
            requested_prefill_step_size=requested_prefill_step_size,
            family_config=family_config,
            family_config_resolver=self._family_config,
            prompt_token_counter=self.prompt_token_count,
            cached_signature=self._last_attention_policy_signature,
            cached_decision=self._last_attention_policy,
            execution_ext=execution_ext,
        )
        return PreparedVisionPrompt(
            prepared_request=prepared_request,
            family_config=family_config,
            prompt_tokens=prompt_tokens,
            cache_identity=cache_identity,
            scope_id=scope_id,
            attention_policy=attention_policy,
        )
