"""Unit tests for the Phase 3B long-context chunker (milestone #43).

These tests exercise ``chunk_long_samples`` with a fake tokenizer so they
stay hermetic — no MLX-LM, no HF weights. The fake renders the chat template
by concatenating message contents with per-message overhead and returns one
integer token per word, which is enough to drive the chunker's branching.
"""

from __future__ import annotations

from typing import Any

import pytest

from worker.model_ops.errors import ModelOperationError
from worker.model_ops.training_dataset_chunker import (
    ChunkStats,
    chunk_long_samples,
)


class _FakeTokenizer:
    """Deterministic stand-in for an HF chat tokenizer.

    Each message contributes ``overhead_per_message`` tokens (role
    delimiters, newlines) plus one token per whitespace-separated word of
    content. ``apply_chat_template`` returns a list of opaque integers —
    only the length is inspected by the chunker.
    """

    def __init__(self, *, overhead_per_message: int = 5) -> None:
        self.overhead_per_message = overhead_per_message

    def apply_chat_template(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]] | None = None,
        add_generation_prompt: bool = False,
        return_dict: bool = False,
    ) -> list[int]:
        total = 0
        for msg in messages:
            content = msg.get("content", "") or ""
            total += self.overhead_per_message + len(content.split())
        if add_generation_prompt:
            total += self.overhead_per_message
        return list(range(total))


def _words(count: int) -> str:
    return " ".join(f"w{i}" for i in range(count))


def test_short_single_turn_sample_passes_through_unchanged() -> None:
    tokenizer = _FakeTokenizer()
    sample = {
        "id": "short",
        "messages": [
            {"role": "system", "content": "You help."},
            {"role": "user", "content": _words(20)},
            {"role": "assistant", "content": "ok"},
        ],
    }

    chunked, stats = chunk_long_samples(
        [sample], chunk_size=200, tokenizer=tokenizer
    )

    assert len(chunked) == 1
    assert chunked[0]["messages"] == sample["messages"]
    assert chunked[0]["id"] == "short"
    assert stats == ChunkStats(
        enabled=True, chunk_size=200, chunk_count=1, source_sample_count=1
    )


def test_long_single_turn_splits_into_multiple_chunks() -> None:
    tokenizer = _FakeTokenizer()  # 5 overhead/msg, 1 token/word
    # ~200 user words + 3-token assistant + overhead — full render ≈ 215 tokens.
    sample = {
        "id": "long",
        "messages": [
            {"role": "user", "content": _words(200)},
            {"role": "assistant", "content": "ack ack ack"},
        ],
    }

    chunked, stats = chunk_long_samples(
        [sample], chunk_size=80, tokenizer=tokenizer
    )

    # Each chunk should be ≤ 80 tokens rendered; all end in assistant.
    assert stats.chunk_count >= 3
    assert stats.chunk_count == len(chunked)
    assert stats.source_sample_count == 1
    for idx, chunk in enumerate(chunked):
        rendered = tokenizer.apply_chat_template(
            chunk["messages"], add_generation_prompt=False, return_dict=False
        )
        assert len(rendered) <= 80, f"chunk {idx} over budget: {len(rendered)}"
        assert chunk["messages"][-1]["role"] == "assistant"
        assert chunk["messages"][-1]["content"] == "ack ack ack"
        assert chunk["id"] == f"long#chunk-{idx}"


def test_multi_turn_within_chunk_size_passes_through_unchanged() -> None:
    tokenizer = _FakeTokenizer()
    sample = {
        "id": "multi-fits",
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": _words(10)},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": _words(10)},
            {"role": "assistant", "content": "a2"},
        ],
    }

    chunked, stats = chunk_long_samples(
        [sample], chunk_size=200, tokenizer=tokenizer
    )

    assert len(chunked) == 1
    assert chunked[0]["messages"] == sample["messages"]
    assert stats.chunk_count == 1


def test_multi_turn_exceeding_chunk_size_splits_at_message_boundaries() -> None:
    tokenizer = _FakeTokenizer()
    # Two turns, each ~70 user words. With fake-tokenizer overhead of 5/msg
    # and 1 token/word, a per-pair render is 5*3 + 1 + 70 + 1 = 87 tokens;
    # both pairs together are 168. Choose chunk_size=100 so each pair fits
    # intact but the combined sample does not.
    sample = {
        "id": "multi-over",
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": _words(70)},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": _words(70)},
            {"role": "assistant", "content": "a2"},
        ],
    }

    chunked, stats = chunk_long_samples(
        [sample], chunk_size=100, tokenizer=tokenizer
    )

    assert stats.chunk_count == 2
    # Both chunks keep the system prefix and each own user/assistant pair.
    for chunk in chunked:
        roles = [m["role"] for m in chunk["messages"]]
        assert roles == ["system", "user", "assistant"]
    assert chunked[0]["messages"][2]["content"] == "a1"
    assert chunked[1]["messages"][2]["content"] == "a2"
    # Ids are suffixed.
    assert chunked[0]["id"] == "multi-over#chunk-0"
    assert chunked[1]["id"] == "multi-over#chunk-1"


def test_multi_turn_single_pair_exceeds_chunk_size_falls_through_to_segmentation() -> None:
    tokenizer = _FakeTokenizer()
    # Two turns; the first pair alone (200 words) exceeds the chunk_size,
    # forcing fallthrough to single-turn segmentation. The second pair fits.
    sample = {
        "id": "multi-fallthrough",
        "messages": [
            {"role": "user", "content": _words(200)},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": _words(10)},
            {"role": "assistant", "content": "a2"},
        ],
    }

    chunked, stats = chunk_long_samples(
        [sample], chunk_size=80, tokenizer=tokenizer
    )

    # First pair splits into ≥3 chunks; second pair emits one chunk.
    assert stats.chunk_count >= 4
    rendered = [
        len(
            tokenizer.apply_chat_template(
                c["messages"], add_generation_prompt=False, return_dict=False
            )
        )
        for c in chunked
    ]
    assert all(r <= 80 for r in rendered)
    # Last chunk should be the second-turn pair unchanged (one user msg).
    last = chunked[-1]
    assert last["messages"][-1]["content"] == "a2"


def test_assistant_only_exceeding_chunk_size_raises_explicit_error() -> None:
    tokenizer = _FakeTokenizer()
    sample = {
        "id": "giant-asst",
        "messages": [
            {"role": "user", "content": "hi"},
            # 200-word assistant alone blows any reasonable chunk_size.
            {"role": "assistant", "content": _words(200)},
        ],
    }

    with pytest.raises(ModelOperationError) as exc:
        chunk_long_samples([sample], chunk_size=50, tokenizer=tokenizer)

    assert exc.value.code == "chunk_size_too_small"
    assert "giant-asst" in (exc.value.message or "")


def test_non_assistant_terminated_sample_passes_through_unchanged() -> None:
    """Chunker does not invent assistant messages.

    Malformed samples (e.g. user-terminated) are left to the dataset
    normalizer's existing rejection path. The chunker guarantees that
    structurally valid input flows through; structurally invalid input is
    forwarded unchanged so the caller sees the same error it would have seen
    without chunking.
    """
    tokenizer = _FakeTokenizer()
    sample = {
        "id": "no-asst",
        "messages": [
            {"role": "user", "content": _words(50)},
        ],
    }

    chunked, stats = chunk_long_samples(
        [sample], chunk_size=30, tokenizer=tokenizer
    )

    assert len(chunked) == 1
    assert chunked[0]["messages"] == sample["messages"]
    assert stats.chunk_count == 1


def test_chunking_is_idempotent() -> None:
    tokenizer = _FakeTokenizer()
    sample = {
        "id": "idempotent",
        "messages": [
            {"role": "user", "content": _words(200)},
            {"role": "assistant", "content": "ok"},
        ],
    }

    first, first_stats = chunk_long_samples(
        [sample], chunk_size=80, tokenizer=tokenizer
    )
    second, second_stats = chunk_long_samples(
        first, chunk_size=80, tokenizer=tokenizer
    )

    # The second pass must not re-chunk anything already ≤ chunk_size.
    assert second_stats.chunk_count == first_stats.chunk_count
    # Message payloads are bit-identical.
    assert [c["messages"] for c in second] == [c["messages"] for c in first]


def test_aggregate_stats_sum_across_multiple_inputs() -> None:
    tokenizer = _FakeTokenizer()
    short = {
        "id": "short",
        "messages": [
            {"role": "user", "content": _words(10)},
            {"role": "assistant", "content": "ok"},
        ],
    }
    long_sample = {
        "id": "long",
        "messages": [
            {"role": "user", "content": _words(200)},
            {"role": "assistant", "content": "ok"},
        ],
    }

    chunked, stats = chunk_long_samples(
        [short, long_sample], chunk_size=80, tokenizer=tokenizer
    )

    assert stats.source_sample_count == 2
    assert stats.chunk_count == len(chunked)
    assert stats.chunk_count > 2  # long sample contributed multiple chunks
    # Short sample appears unchanged at index 0.
    assert chunked[0]["id"] == "short"
    # Long sample chunks have suffixed ids and all end in assistant.
    long_chunks = [c for c in chunked if c["id"].startswith("long")]
    assert len(long_chunks) == stats.chunk_count - 1
    for chunk in long_chunks:
        assert chunk["messages"][-1]["role"] == "assistant"


def test_manifest_fields_exposes_all_stats() -> None:
    stats = ChunkStats(
        enabled=True, chunk_size=2048, chunk_count=22, source_sample_count=10
    )

    assert stats.to_manifest_fields() == {
        "enabled": True,
        "chunk_size": 2048,
        "chunk_count": 22,
        "source_sample_count": 10,
    }
