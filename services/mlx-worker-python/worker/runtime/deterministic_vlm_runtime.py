from __future__ import annotations

from dataclasses import dataclass
from threading import Event

from packages.protocol.python.worker.v1 import cache_pb2, common_pb2

from worker.runtime.deterministic_delay import sleep_if_configured
from worker.runtime.mlx_text_runtime import RuntimeTokenEvent
from worker.runtime.multimodal_preprocessing import PreparedVisionRequest, prepare_vision_request


@dataclass(frozen=True)
class VisionProbeSnapshot:
    preprocess_latency_ms: float
    preprocess_input_bytes: int
    preprocess_peak_memory_bytes: int
    first_token_latency_ms: float
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


class DeterministicVLMRuntime:
    runtime_name = "deterministic-vlm"

    def __init__(self) -> None:
        self._last_probe = VisionProbeSnapshot(0.0, 0, 0, 0.0)
        self._cache_entries: dict[str, VisionCacheEntry] = {}
        self._cache_lookups = 0
        self._cache_hits = 0

    def load_model(self, model_spec):
        return {
            "model_id": model_spec.model_id,
            "model_kind": model_spec.model_kind,
            "revision": model_spec.revision,
            "tokenizer_hash": model_spec.tokenizer_hash,
            "quant_profile_id": model_spec.quant_profile_id,
            "parser_mode": model_spec.parser_mode,
            "reasoning_mode": model_spec.reasoning_mode,
            "multimodal_adapter_hash": model_spec.ext.get("melix.multimodal_adapter_hash", ""),
        }

    def estimate_resident_bytes(self, model_spec):
        return 4096

    def render_prompt(self, messages, loaded_model=None) -> PreparedVisionRequest:
        prepared = prepare_vision_request(messages)
        cache_identity, scope_id = self._cache_identity(prepared, loaded_model)
        self._last_probe = VisionProbeSnapshot(
            preprocess_latency_ms=prepared.preprocess_latency_ms,
            preprocess_input_bytes=prepared.preprocess_input_bytes,
            preprocess_peak_memory_bytes=prepared.preprocess_peak_memory_bytes,
            first_token_latency_ms=0.0,
            cache_identity=cache_identity,
            cache_scope_id=scope_id,
            cache_hit=cache_identity in self._cache_entries,
        )
        return prepared

    def prompt_token_count(self, prepared_request: PreparedVisionRequest) -> int:
        prompt_tokens = len(prepared_request.prompt_text.split())
        image_tokens = sum(max(1, image.byte_length // 8) for image in prepared_request.images)
        return max(1, prompt_tokens + image_tokens)

    def generate_tokens(
        self,
        loaded_model,
        prepared_request: PreparedVisionRequest,
        sampling,
        cancel_event: Event,
    ):
        image_text = prepared_request.images[0].decoded_text()
        prompt_text = prepared_request.prompt_text or "Describe the image."
        response = f"Image content: {image_text}\nPrompt: {prompt_text}"
        cache_identity, scope_id = self._cache_identity(prepared_request, loaded_model)
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
            cache_identity=cache_identity,
            cache_scope_id=scope_id,
            cache_hit=cache_hit,
        )
        sleep_if_configured("vlm")
        if cancel_event.is_set():
            return
        yield RuntimeTokenEvent(
            text=response,
            prompt_tokens=self.prompt_token_count(prepared_request),
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

    def _cache_identity(
        self,
        prepared_request: PreparedVisionRequest,
        loaded_model,
    ) -> tuple[str, str]:
        model_id = self._metadata_value(loaded_model, "model_id", "melix-dev-vlm")
        revision = self._metadata_value(loaded_model, "revision", "dev")
        quant_profile_id = self._metadata_value(loaded_model, "quant_profile_id", "q8")
        parser_mode = self._metadata_value(loaded_model, "parser_mode", "text")
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

    def _cache_entry(
        self,
        loaded_model,
        prepared_request: PreparedVisionRequest,
        cache_identity: str,
        scope_id: str,
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
            parser_mode=self._metadata_value(loaded_model, "parser_mode", "text"),
            reasoning_mode=self._metadata_value(loaded_model, "reasoning_mode", "off"),
            multimodal_adapter_hash=self._metadata_value(loaded_model, "multimodal_adapter_hash", ""),
            prompt_hash_hex=prepared_request.prompt_hash_hex,
            fingerprint_hash_hex=prepared_request.multimodal_hash_hex,
            bytes_used=bytes_used,
            token_length=token_length,
        )

    @staticmethod
    def _metadata_value(loaded_model, key: str, default: str) -> str:
        if isinstance(loaded_model, dict):
            value = loaded_model.get(key)
            if isinstance(value, str) and value:
                return value
        return default
