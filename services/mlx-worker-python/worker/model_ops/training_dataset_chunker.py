"""Melix-side long-context pre-chunking (milestone #43 Phase 3B).

When ``LoRATrainingConfig.chunked_training`` is True, long chat samples are
split into shorter training examples at dataset-normalization time so each
chunk fits inside the configured ``chunk_size`` token window. This is the
lever the Phase 3 quantitative gate relies on: reducing the per-step
attention-matrix footprint (which scales ~quadratically with sequence
length) in exchange for more, smaller training examples.

The chunker is a pure function over normalized chat-messages samples and a
tokenizer. It does NOT tokenize the output itself — MLX-LM's ``ChatDataset``
tokenizes at training time. The chunker only uses the tokenizer to **measure**
the rendered length of candidate chunks so it can choose a correct segmentation.

Invariant: every emitted chunk ends with an assistant message so
``compute_response_only_boundary`` (Phase 2) can derive the prompt boundary
for every chunk. Chunks that would violate the invariant raise
``ModelOperationError(code="chunk_size_too_small", ...)``.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Iterable

from worker.model_ops.errors import ModelOperationError
from worker.model_ops.response_only_boundary import _ChatTemplateTokenizer


@dataclass(frozen=True)
class ChunkStats:
    """Aggregate chunking stats surfaced in the snapshot manifest + metrics.

    ``source_sample_count`` is the number of samples passed in;
    ``chunk_count`` is the number of samples emitted (always ≥
    source_sample_count when chunking is enabled).
    """

    enabled: bool
    chunk_size: int
    chunk_count: int
    source_sample_count: int

    def to_manifest_fields(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "chunk_size": self.chunk_size,
            "chunk_count": self.chunk_count,
            "source_sample_count": self.source_sample_count,
        }


def _render_len(
    messages: list[dict[str, str]],
    tokenizer: _ChatTemplateTokenizer,
    *,
    tools: list[dict[str, Any]] | None = None,
) -> int:
    """Render the chat template and return the token count.

    Uses the same ``apply_chat_template(return_dict=False)`` call pattern as
    ``response_only_boundary.py`` and MLX-LM's ``ChatDataset.process`` so the
    measurement stays bit-exact with what training sees.
    """

    tokens = tokenizer.apply_chat_template(
        messages,
        tools=tools,
        add_generation_prompt=False,
        return_dict=False,
    )
    return len(tokens)


def _extract_messages(sample: dict) -> list[dict[str, str]]:
    messages = sample.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="Chunker requires samples with a non-empty 'messages' list.",
        )
    return messages


def _split_messages_into_turns(
    messages: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[tuple[dict[str, str], dict[str, str]]]]:
    """Return (system_prefix, [(user, assistant), ...]).

    Non-alternating / malformed messages (trailing user without assistant,
    assistant without preceding user, non-system leading message that isn't a
    user, etc.) are returned with whatever pairs we could extract; the caller
    is responsible for the final assistant-terminated check.
    """

    system_prefix: list[dict[str, str]] = []
    idx = 0
    if messages and messages[0].get("role") == "system":
        system_prefix.append(messages[0])
        idx = 1

    pairs: list[tuple[dict[str, str], dict[str, str]]] = []
    while idx + 1 < len(messages):
        user = messages[idx]
        assistant = messages[idx + 1]
        if user.get("role") != "user" or assistant.get("role") != "assistant":
            break
        pairs.append((user, assistant))
        idx += 2

    return system_prefix, pairs


def _split_user_content_into_k(content: str, k: int) -> list[str]:
    """Split ``content`` into ``k`` roughly equal word-boundary segments.

    Splitting on whitespace preserves word integrity; empty segments are
    dropped (can happen when content has fewer words than ``k``, in which case
    we return as many segments as we have words).
    """

    if k <= 1:
        return [content]
    words = content.split()
    if len(words) <= k:
        return words[:]  # degenerate: fewer words than buckets
    bucket_size = len(words) // k
    extras = len(words) % k
    segments: list[str] = []
    start = 0
    for bucket_idx in range(k):
        length = bucket_size + (1 if bucket_idx < extras else 0)
        segments.append(" ".join(words[start : start + length]))
        start += length
    return [s for s in segments if s]


def _chunk_single_turn(
    system_prefix: list[dict[str, str]],
    user: dict[str, str],
    assistant: dict[str, str],
    *,
    chunk_size: int,
    tokenizer: _ChatTemplateTokenizer,
    sample_id: str,
) -> list[list[dict[str, str]]]:
    """Segment a single (user, assistant) pair so each chunk fits chunk_size.

    Holds ``system_prefix`` and ``assistant`` constant; splits the user
    content by word boundaries into the smallest K for which every rendered
    chunk is ≤ chunk_size. Raises if no K in [1, 64] satisfies the bound —
    which means even an empty-user chunk exceeds chunk_size (assistant text
    alone too long).
    """

    full = system_prefix + [user, assistant]
    full_len = _render_len(full, tokenizer)
    if full_len <= chunk_size:
        return [full]

    user_content = user.get("content", "")
    if not isinstance(user_content, str):
        raise ModelOperationError(
            code="invalid_dataset_package",
            message=(
                f"Chunker requires string user content; sample {sample_id!r} "
                f"has content of type {type(user_content).__name__}."
            ),
        )

    # Floor estimate: at least ceil(full_len / chunk_size). Start there,
    # increment until every emitted chunk fits. Bounded by 64 to catch
    # degenerate cases fast.
    k_floor = max(2, -(-full_len // chunk_size))
    for k in range(k_floor, 65):
        segments = _split_user_content_into_k(user_content, k)
        if len(segments) < k:
            # Ran out of splittable words — user content too short for this K.
            # That means the overhead (system + assistant) itself breaks the
            # budget.
            continue
        chunks = [
            system_prefix + [{"role": "user", "content": seg}, assistant]
            for seg in segments
        ]
        if all(_render_len(chunk, tokenizer) <= chunk_size for chunk in chunks):
            return chunks

    raise ModelOperationError(
        code="chunk_size_too_small",
        message=(
            f"Cannot chunk sample {sample_id!r} within chunk_size={chunk_size}"
            f" (full rendering is {full_len} tokens). The assistant message or"
            " system prefix likely exceeds chunk_size on its own."
        ),
    )


def _chunk_sample(
    sample: dict,
    *,
    chunk_size: int,
    tokenizer: _ChatTemplateTokenizer,
) -> list[dict]:
    """Return one or more output samples for a single normalized input sample.

    The returned samples are deep-copied from the input so the caller's
    original data is not mutated.
    """

    messages = _extract_messages(sample)
    if _render_len(messages, tokenizer) <= chunk_size:
        return [copy.deepcopy(sample)]

    sample_id = str(sample.get("id", ""))
    system_prefix, pairs = _split_messages_into_turns(messages)

    if not pairs:
        # No (user, assistant) pair we could extract. Preserve the original
        # sample unchanged — the dataset loader will reject it downstream if
        # it is malformed, and the chunker should not silently drop it.
        return [copy.deepcopy(sample)]

    # Multi-turn: emit each (user, assistant) pair as its own chunk first.
    # If any chunk still overflows, fall through to single-turn segmentation
    # for that chunk.
    chunked_messages: list[list[dict[str, str]]] = []
    if len(pairs) > 1:
        for user, assistant in pairs:
            chunked_messages.extend(
                _chunk_single_turn(
                    system_prefix,
                    user,
                    assistant,
                    chunk_size=chunk_size,
                    tokenizer=tokenizer,
                    sample_id=sample_id,
                )
            )
    else:
        user, assistant = pairs[0]
        chunked_messages.extend(
            _chunk_single_turn(
                system_prefix,
                user,
                assistant,
                chunk_size=chunk_size,
                tokenizer=tokenizer,
                sample_id=sample_id,
            )
        )

    chunks: list[dict] = []
    for idx, chunk in enumerate(chunked_messages):
        # Preserve any non-messages keys from the source sample (e.g. id,
        # metadata) but suffix the id so each chunk is individually traceable.
        out = copy.deepcopy(sample)
        out["messages"] = copy.deepcopy(chunk)
        if sample_id:
            out["id"] = f"{sample_id}#chunk-{idx}"
        chunks.append(out)
    return chunks


def chunk_long_samples(
    samples: Iterable[dict],
    *,
    chunk_size: int,
    tokenizer: _ChatTemplateTokenizer,
) -> tuple[list[dict], ChunkStats]:
    """Chunk every sample in ``samples`` that exceeds ``chunk_size`` tokens.

    Returns ``(chunked_samples, stats)``. Samples that already fit pass
    through as one chunk each (deep-copied so downstream mutations can't leak
    back to the caller).
    """

    if chunk_size < 1:
        raise ModelOperationError(
            code="invalid_argument",
            message=f"chunk_size must be >= 1, got {chunk_size}.",
        )

    source_samples = list(samples)
    chunked: list[dict] = []
    for sample in source_samples:
        chunked.extend(
            _chunk_sample(sample, chunk_size=chunk_size, tokenizer=tokenizer)
        )

    return chunked, ChunkStats(
        enabled=True,
        chunk_size=chunk_size,
        chunk_count=len(chunked),
        source_sample_count=len(source_samples),
    )
