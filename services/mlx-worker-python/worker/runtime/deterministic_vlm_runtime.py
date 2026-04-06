from __future__ import annotations

from dataclasses import dataclass
import json
from threading import Event

from packages.protocol.python.worker.v1 import cache_pb2, common_pb2

from worker.runtime.deterministic_delay import sleep_if_configured
from worker.runtime.mlx_text_runtime import RuntimeTokenEvent, RuntimeToolCallEvent
from worker.runtime.multimodal_preprocessing import PreparedVisionRequest, prepare_vision_request
from worker.runtime.vision_family_adapters import resolve_vision_family_config


@dataclass(frozen=True)
class VisionProbeSnapshot:
    preprocess_latency_ms: float
    preprocess_input_bytes: int
    preprocess_peak_memory_bytes: int
    first_token_latency_ms: float
    video_effective_frame_count: int = 0
    video_requested_frame_budget: int = 0
    video_window_ms: int = 0
    cache_identity: str = ""
    cache_scope_id: str = ""
    cache_hit: bool = False


@dataclass(frozen=True)
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


class DeterministicVLMRuntime:
    runtime_name = "deterministic-vlm"

    def __init__(self) -> None:
        self._last_probe = VisionProbeSnapshot(0.0, 0, 0, 0.0)
        self._cache_entries: dict[str, VisionCacheEntry] = {}
        self._decode_sessions: dict[str, VisionPrefillSession] = {}
        self._cache_lookups = 0
        self._cache_hits = 0

    def load_model(self, model_spec):
        family_config = resolve_vision_family_config(dict(model_spec.ext))
        return {
            "model_id": model_spec.model_id,
            "model_kind": model_spec.model_kind,
            "revision": model_spec.revision,
            "tokenizer_hash": model_spec.tokenizer_hash,
            "quant_profile_id": model_spec.quant_profile_id,
            "parser_mode": model_spec.parser_mode,
            "reasoning_mode": model_spec.reasoning_mode,
            **family_config.capability_metadata(),
        }

    def estimate_resident_bytes(self, model_spec):
        return 4096

    def render_prompt(
        self,
        messages,
        loaded_model=None,
        template_kwargs=None,
        execution_ext: dict[str, str] | None = None,
    ) -> PreparedVisionRequest:
        _ = template_kwargs
        prepared = self._family_config(loaded_model).shape_request(prepare_vision_request(messages))
        cache_identity, scope_id = self._cache_identity(
            prepared,
            loaded_model,
            execution_ext=execution_ext,
        )
        self._last_probe = VisionProbeSnapshot(
            preprocess_latency_ms=prepared.preprocess_latency_ms,
            preprocess_input_bytes=prepared.preprocess_input_bytes,
            preprocess_peak_memory_bytes=prepared.preprocess_peak_memory_bytes,
            first_token_latency_ms=0.0,
            video_effective_frame_count=prepared.effective_video_frame_count,
            video_requested_frame_budget=prepared.requested_video_frame_budget,
            video_window_ms=prepared.effective_video_window_ms,
            cache_identity=cache_identity,
            cache_scope_id=scope_id,
            cache_hit=cache_identity in self._cache_entries,
        )
        return prepared

    def prompt_token_count(
        self,
        prepared_request: PreparedVisionRequest,
        loaded_model=None,
    ) -> int:
        return self._family_config(loaded_model).prompt_token_count(prepared_request)

    def prefill(
        self,
        request_id: str,
        loaded_model,
        messages,
        execution_ext: dict[str, str] | None = None,
    ) -> VisionPrefillSession:
        prepared_request = self.render_prompt(
            messages,
            loaded_model=loaded_model,
            execution_ext=execution_ext,
        )
        prompt_tokens = self.prompt_token_count(prepared_request, loaded_model=loaded_model)
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
            self._cache_entries[cache_identity] = self._cache_entry(
                loaded_model=loaded_model,
                prepared_request=prepared_request,
                cache_identity=cache_identity,
                scope_id=scope_id,
                execution_ext=execution_ext,
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
            completion_tokens=max(1, len(response_text.split())),
            tool_call_event=tool_call_event,
            cache_identity=cache_identity,
            scope_id=scope_id,
            cache_hit=cache_hit,
            block_table_id=block_table_id,
            block_table=block_table,
        )
        self._decode_sessions[decode_handle] = session
        self._last_probe = VisionProbeSnapshot(
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
        self._last_probe = VisionProbeSnapshot(
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
            entry = self._cache_entry(
                loaded_model=loaded_model,
                prepared_request=prepared_request,
                cache_identity=cache_identity,
                scope_id=scope_id,
                execution_ext=execution_ext,
            )
            self._cache_entries[cache_identity] = entry
        self._last_probe = VisionProbeSnapshot(
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
            prompt_tokens=self.prompt_token_count(prepared_request, loaded_model=loaded_model),
            completion_tokens=max(1, len(response.split())),
            finish_reason="stop",
        )

    def last_probe_snapshot(self) -> VisionProbeSnapshot:
        return self._last_probe

    def cache_stats_response(self) -> cache_pb2.GetCacheStatsResponse:
        response = cache_pb2.GetCacheStatsResponse()
        total_l1_bytes = sum(entry.bytes_used for entry in self._cache_entries.values())
        total_block_count = len(self._cache_entries)
        lookup_count = max(1, self._cache_lookups)
        response.stats.l1_bytes = total_l1_bytes
        response.stats.block_count = total_block_count
        response.stats.l1_hit_rate = self._cache_hits / lookup_count
        response.stats.dedup_ratio = 1.0 - (total_block_count / lookup_count)
        response.stats.active_mode = common_pb2.CACHE_MODE_TIERED
        response.snapshot.stats.CopyFrom(response.stats)

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
            response.snapshot.hot_prefixes.append(prefix)

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

        response.snapshot.scopes.extend(scopes.values())
        return response

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
        identity = ":".join(
            [
                model_id,
                revision,
                quant_profile_id,
                parser_mode,
                reasoning_mode,
                prepared_request.multimodal_hash_hex,
            ]
        )
        return identity, f"{model_id}:{prepared_request.multimodal_hash_hex[:16]}"

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
            fingerprint_hash=bytes.fromhex(prepared_request.multimodal_hash_hex),
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
        execution_ext: dict[str, str] | None = None,
    ) -> VisionCacheEntry:
        prompt_bytes = len(prepared_request.prompt_text.encode("utf-8"))
        token_length = self.prompt_token_count(prepared_request)
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
            fingerprint_hash_hex=prepared_request.multimodal_hash_hex,
            bytes_used=bytes_used,
            token_length=token_length,
        )

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

    def _family_config(self, loaded_model) -> object:
        metadata: dict[str, str] = {}
        if isinstance(loaded_model, dict):
            metadata = {
                key: value
                for key, value in loaded_model.items()
                if isinstance(value, str) and value
            }
        return resolve_vision_family_config(metadata)
