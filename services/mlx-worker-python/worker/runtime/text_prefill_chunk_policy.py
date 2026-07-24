"""Guarded chunked-prefill policy for the text-only multimodal lane.

When a resolved multimodal request carries no media, no sequence-aligned extra
inputs, and either no attention mask or an all-valid mask, the text-backed
VLM/MTP decode path can reuse the language-model KV contract instead of issuing
a single full-sequence forward. Prefilling the prefix in bounded chunks lets the
runtime materialize only cache state between chunks and run the final token
separately, so only one ``[batch, 1, vocab]`` projection is needed for the first
sampled token. Any partial mask, media input, missing cache, or unknown
sequence-aligned argument must keep the original single-forward path.

This module owns the *decision* half of that behavior: it resolves an effective
prefill step size, decides whether chunking is admissible, and produces a
machine-readable receipt. It deliberately performs no model forward work so the
policy stays cheap and unit-testable without an Apple Silicon backend.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


TEXT_PREFILL_SINGLE_FORWARD = "single_forward"
TEXT_PREFILL_CHUNKED_PREFIX = "chunked_prefix"

TEXT_PREFILL_FALLBACK_MEDIA_PRESENT = "media_present"
TEXT_PREFILL_FALLBACK_SEQUENCE_ALIGNED_EXTRA_INPUTS = "sequence_aligned_extra_inputs"
TEXT_PREFILL_FALLBACK_PARTIAL_ATTENTION_MASK = "partial_attention_mask"
TEXT_PREFILL_FALLBACK_CACHE_UNAVAILABLE = "cache_unavailable"
TEXT_PREFILL_FALLBACK_PROMPT_WITHIN_SINGLE_CHUNK = "prompt_within_single_chunk"

# Matches the VLM text-only batch generator defaults so the standalone policy
# and the batch generator resolve identical effective step sizes.
_DEFAULT_TEXT_PREFILL_STEP_SIZE = 512
_MIN_TEXT_PREFILL_STEP_SIZE = 1
_MAX_TEXT_PREFILL_STEP_SIZE = 8192
_FINAL_LOGITS_POSITIONS = 1

_TEXT_PREFILL_STEP_SIZE_METADATA_KEYS = (
    "melix.vlm.text_prefill_step_size",
    "melix.vlm.text_prefill_chunk_tokens",
)


@dataclass(frozen=True, slots=True)
class TextPrefillChunkDecision:
    prompt_tokens: int
    effective_prefill_step_size: int
    prefill_mode: str
    prefill_chunk_tokens: int
    prefix_chunks: int
    final_logits_positions: int
    fallback_reason: str


def normalize_text_prefill_step_size(value: object | None) -> int:
    """Resolve the effective prefill step size, defaulting an unset request.

    The text-backed VLM/MTP path passes ``prefill_step_size=None`` today; this
    turns that into a bounded, deterministic value clamped to the same range the
    batch generator accepts.
    """

    if value is None:
        return _DEFAULT_TEXT_PREFILL_STEP_SIZE
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return _DEFAULT_TEXT_PREFILL_STEP_SIZE
    if parsed <= 0:
        return _DEFAULT_TEXT_PREFILL_STEP_SIZE
    return min(_MAX_TEXT_PREFILL_STEP_SIZE, max(_MIN_TEXT_PREFILL_STEP_SIZE, parsed))


def resolve_text_prefill_chunk_policy(
    *,
    prompt_tokens: int,
    requested_prefill_step_size: object | None = None,
    has_media: bool = False,
    has_sequence_aligned_extra_inputs: bool = False,
    attention_mask_all_valid: bool = True,
    cache_present: bool = True,
) -> TextPrefillChunkDecision:
    """Decide whether the prompt prefix should be chunked before the final token.

    Guards mirror the correctness contract: media inputs, sequence-aligned extra
    inputs, a partial attention mask, or a missing cache each force the original
    single-forward path with a typed ``fallback_reason``. A prompt whose prefix
    fits inside one step keeps the single forward too, so ordinary short-prompt
    latency is unchanged.
    """

    normalized_prompt_tokens = max(0, _coerce_int(prompt_tokens))
    step_size = normalize_text_prefill_step_size(requested_prefill_step_size)

    fallback_reason = _guard_fallback_reason(
        has_media=has_media,
        has_sequence_aligned_extra_inputs=has_sequence_aligned_extra_inputs,
        attention_mask_all_valid=attention_mask_all_valid,
        cache_present=cache_present,
    )
    if fallback_reason:
        return _single_forward_decision(
            prompt_tokens=normalized_prompt_tokens,
            step_size=step_size,
            fallback_reason=fallback_reason,
        )

    prefix_tokens = max(0, normalized_prompt_tokens - _FINAL_LOGITS_POSITIONS)
    if prefix_tokens <= step_size:
        return _single_forward_decision(
            prompt_tokens=normalized_prompt_tokens,
            step_size=step_size,
            fallback_reason=TEXT_PREFILL_FALLBACK_PROMPT_WITHIN_SINGLE_CHUNK,
        )

    prefix_chunks = (prefix_tokens + step_size - 1) // step_size
    return TextPrefillChunkDecision(
        prompt_tokens=normalized_prompt_tokens,
        effective_prefill_step_size=step_size,
        prefill_mode=TEXT_PREFILL_CHUNKED_PREFIX,
        prefill_chunk_tokens=step_size,
        prefix_chunks=prefix_chunks,
        final_logits_positions=_FINAL_LOGITS_POSITIONS,
        fallback_reason="",
    )


def resolve_configured_text_prefill_chunk_policy(
    *,
    loaded_model: object,
    prepared_request: object,
    seq_len: int | None,
    execution_ext: object | None = None,
    has_sequence_aligned_extra_inputs: bool = False,
    attention_mask_all_valid: bool = True,
    cache_present: bool = True,
) -> TextPrefillChunkDecision | None:
    """Resolve the policy when a text prefill step size is configured.

    Returns ``None`` when no step size is configured so callers keep an empty
    receipt and unchanged default behavior, mirroring the attention-budget
    policy's opt-in shape.

    ``has_media`` is derived from the prepared request. The remaining guard
    signals — ``has_sequence_aligned_extra_inputs``, ``attention_mask_all_valid``,
    and ``cache_present`` — are decode-loop facts that the receipt-only probe
    sites cannot observe before the first forward, so they default to the
    eligible values. They are forwarded explicitly (not silently dropped) so the
    follow-up that drives real chunked execution can pass the observed values and
    have the guards fire.
    """

    configured = _configured_text_prefill_step_size(loaded_model, execution_ext)
    if configured is None:
        return None
    has_media = bool(
        getattr(prepared_request, "images", None)
        or getattr(prepared_request, "videos", None)
    )
    return resolve_text_prefill_chunk_policy(
        prompt_tokens=seq_len if seq_len is not None else 0,
        requested_prefill_step_size=configured,
        has_media=has_media,
        has_sequence_aligned_extra_inputs=has_sequence_aligned_extra_inputs,
        attention_mask_all_valid=attention_mask_all_valid,
        cache_present=cache_present,
    )


def text_prefill_chunk_configured(
    loaded_model: object,
    execution_ext: object | None = None,
) -> bool:
    return _configured_text_prefill_step_size(loaded_model, execution_ext) is not None


def build_text_prefill_chunk_receipt(
    decision: TextPrefillChunkDecision | None,
) -> dict[str, object]:
    if decision is None:
        return {}
    return {
        "prefill_mode": decision.prefill_mode,
        "prompt_tokens": decision.prompt_tokens,
        "effective_prefill_step_size": decision.effective_prefill_step_size,
        "prefill_chunk_tokens": decision.prefill_chunk_tokens,
        "prefix_chunks": decision.prefix_chunks,
        "final_logits_positions": decision.final_logits_positions,
        "fallback_reason": decision.fallback_reason,
    }


def _single_forward_decision(
    *,
    prompt_tokens: int,
    step_size: int,
    fallback_reason: str,
) -> TextPrefillChunkDecision:
    has_tokens = prompt_tokens > 0
    return TextPrefillChunkDecision(
        prompt_tokens=prompt_tokens,
        effective_prefill_step_size=step_size,
        prefill_mode=TEXT_PREFILL_SINGLE_FORWARD,
        prefill_chunk_tokens=prompt_tokens,
        prefix_chunks=1 if has_tokens else 0,
        final_logits_positions=_FINAL_LOGITS_POSITIONS if has_tokens else 0,
        fallback_reason=fallback_reason,
    )


def _guard_fallback_reason(
    *,
    has_media: bool,
    has_sequence_aligned_extra_inputs: bool,
    attention_mask_all_valid: bool,
    cache_present: bool,
) -> str:
    if has_media:
        return TEXT_PREFILL_FALLBACK_MEDIA_PRESENT
    if has_sequence_aligned_extra_inputs:
        return TEXT_PREFILL_FALLBACK_SEQUENCE_ALIGNED_EXTRA_INPUTS
    if not attention_mask_all_valid:
        return TEXT_PREFILL_FALLBACK_PARTIAL_ATTENTION_MASK
    if not cache_present:
        return TEXT_PREFILL_FALLBACK_CACHE_UNAVAILABLE
    return ""


def _configured_text_prefill_step_size(
    loaded_model: object,
    execution_ext: object | None,
) -> str | None:
    if isinstance(execution_ext, Mapping):
        value = _first_configured_value(execution_ext)
        if value is not None:
            return value
    if isinstance(loaded_model, dict):
        value = _first_configured_value(loaded_model)
        if value is not None:
            return value
        metadata = loaded_model.get("metadata")
        if isinstance(metadata, Mapping):
            value = _first_configured_value(metadata)
            if value is not None:
                return value
    return None


def _first_configured_value(source: Mapping[str, object]) -> str | None:
    for key in _TEXT_PREFILL_STEP_SIZE_METADATA_KEYS:
        raw_value = source.get(key)
        if raw_value is None:
            continue
        normalized = str(raw_value).strip()
        if normalized:
            return normalized
    return None


def _coerce_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
