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

Invariant: every chunk the chunker *transforms* ends with an assistant
message so ``compute_response_only_boundary`` (Phase 2) can derive the
prompt boundary for every chunk. Samples whose shape the chunker does not
transform (non-assistant-terminated, pair-extraction returns empty) pass
through unchanged so the downstream dataset loader sees the same
rejection it would without chunking. Chunks that *would* be transformed
but cannot be made to fit raise ``ModelOperationError(code="chunk_size_too_small", ...)``.
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
    measurement stays bit-exact with what training sees. ``tools`` is
    forwarded so samples that carry tool schemas produce a length estimate
    that matches the real training pass.
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


def _extract_tools(sample: dict) -> list[dict[str, Any]] | None:
    tools = sample.get("tools")
    if tools is None:
        return None
    if not isinstance(tools, list):
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="Chunker requires 'tools' to be a list when present.",
        )
    return tools


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

    Splitting on whitespace preserves word integrity but normalizes internal
    whitespace — tabs, newlines, and multi-spaces collapse to single spaces.
    Acceptable for prose (the committed 3B fixtures are Alice in Wonderland
    repetitions) but destructive for semantically-whitespace-sensitive
    content (code, poetry, structured logs). A follow-on can substitute a
    regex split that preserves delimiters if production datasets surface the
    need.

    Empty segments are dropped — when ``len(words) < k`` the caller's loop
    detects the short return via ``len(segments) < k`` and moves on to the
    next ``k`` candidate.
    """

    if k <= 1:
        return [content]
    words = content.split()
    if len(words) < k:
        return words[:]  # caller detects len(segments) < k and retries
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
    tools: list[dict[str, Any]] | None,
    sample_id: str,
) -> list[list[dict[str, str]]]:
    """Segment a single (user, assistant) pair so each chunk fits chunk_size.

    Holds ``system_prefix`` and ``assistant`` constant; splits the user
    content by word boundaries into the smallest K for which every rendered
    chunk is ≤ chunk_size. Search strategy is linear increment from
    ``K_floor = ceil(full_len / chunk_size)`` — the token-count function is
    monotonic in K and ``K_floor`` is almost always the answer (or
    off-by-one), so binary search adds complexity without meaningful latency
    savings at typical 2k–8k context sizes.

    Raises ``chunk_size_too_small`` when no valid K can be found — either
    because the assistant / system prefix alone exceeds chunk_size, or
    because the user content has too few words to form K non-empty segments.
    The error message distinguishes the two cases so the operator gets
    actionable guidance.
    """

    full = system_prefix + [user, assistant]
    full_len = _render_len(full, tokenizer, tools=tools)
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

    # True ceiling: we can never split ``user_content`` into more segments
    # than it has words. Above that, no K can possibly produce a non-empty
    # segment per bucket.
    word_count = len(user_content.split())
    k_floor = max(2, -(-full_len // chunk_size))
    if k_floor > word_count:
        raise ModelOperationError(
            code="chunk_size_too_small",
            message=(
                f"Cannot chunk sample {sample_id!r} within chunk_size="
                f"{chunk_size}: user content has only {word_count} words but "
                f"at least {k_floor} segments are needed. Either raise "
                "chunk_size or pre-reduce the assistant/system prefix."
            ),
        )
    for k in range(k_floor, word_count + 1):
        segments = _split_user_content_into_k(user_content, k)
        if len(segments) < k:
            # User content has fewer words than buckets — caller must try a
            # smaller K. In practice this only fires when k > word_count,
            # which the guard above already rejects.
            continue
        chunks = [
            system_prefix + [{"role": "user", "content": seg}, assistant]
            for seg in segments
        ]
        if all(
            _render_len(chunk, tokenizer, tools=tools) <= chunk_size
            for chunk in chunks
        ):
            return chunks

    raise ModelOperationError(
        code="chunk_size_too_small",
        message=(
            f"Cannot chunk sample {sample_id!r} within chunk_size={chunk_size}"
            f" (full rendering is {full_len} tokens). The assistant message or"
            " system prefix alone likely exceeds chunk_size."
        ),
    )


def _chunk_sample(
    sample: dict,
    *,
    chunk_size: int,
    tokenizer: _ChatTemplateTokenizer,
) -> list[dict]:
    """Return one or more output samples for a single normalized input sample.

    The returned samples deep-copy only the new messages list; non-messages
    top-level keys (id, metadata, tools, …) are shallow-copied into each
    chunk because they are immutable-by-convention inputs the caller does
    not expect the chunker to mutate.

    Samples that lack any (user, assistant) pair (malformed shape or
    non-assistant-terminated) pass through unchanged so the downstream
    dataset loader sees the same rejection it would have seen without
    chunking — the chunker's assistant-terminated invariant applies only to
    samples whose shape the chunker actually transforms.
    """

    tools = _extract_tools(sample)
    messages = _extract_messages(sample)
    if _render_len(messages, tokenizer, tools=tools) <= chunk_size:
        return [copy.deepcopy(sample)]

    sample_id = str(sample.get("id", ""))
    system_prefix, pairs = _split_messages_into_turns(messages)

    if not pairs:
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
                    tools=tools,
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
                tools=tools,
                sample_id=sample_id,
            )
        )

    chunks: list[dict] = []
    for idx, chunk in enumerate(chunked_messages):
        # Preserve any non-messages keys from the source sample (id, tools,
        # metadata) via a shallow top-level copy, then deep-copy only the
        # new messages so each chunk has an independent message list.
        out = {k: v for k, v in sample.items() if k != "messages"}
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
    back to the caller). Iterates ``samples`` exactly once so the caller can
    pass a generator over a large JSONL file without materializing it.
    """

    if chunk_size < 1:
        raise ModelOperationError(
            code="invalid_argument",
            message=f"chunk_size must be >= 1, got {chunk_size}.",
        )

    source_sample_count = 0
    chunked: list[dict] = []
    for sample in samples:
        source_sample_count += 1
        chunked.extend(
            _chunk_sample(sample, chunk_size=chunk_size, tokenizer=tokenizer)
        )

    return chunked, ChunkStats(
        enabled=True,
        chunk_size=chunk_size,
        chunk_count=len(chunked),
        source_sample_count=source_sample_count,
    )
