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
from worker.model_ops import training_dataset_chunker as chunker
from worker.model_ops.training_dataset_chunker import (
    ChunkStats,
    _split_messages_into_turns,
    _split_words_into_k,
    _split_user_content_into_k,
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


class _TrackingStr(str):
    """String subclass that fails if the chunker deep-copies message payloads."""

    def __deepcopy__(self, memo: dict[int, object]) -> "_TrackingStr":
        raise AssertionError("message payload should not be deep-copied")


class _ItemsCountingDict(dict):
    """Dict that records how often top-level item filtering is requested."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.items_calls = 0

    def items(self):  # type: ignore[override]
        self.items_calls += 1
        return super().items()


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


def test_short_single_turn_passthrough_reuses_top_level_metadata_but_copies_messages() -> None:
    tokenizer = _FakeTokenizer()
    metadata = {"tags": ["short"]}
    tools = [{"type": "function", "function": {"name": "lookup"}}]
    sample = {
        "id": "short-copy-contract",
        "metadata": metadata,
        "tools": tools,
        "messages": [
            {"role": "user", "content": _words(5)},
            {"role": "assistant", "content": "ok"},
        ],
    }

    chunked, _ = chunk_long_samples([sample], chunk_size=200, tokenizer=tokenizer)

    emitted = chunked[0]
    assert emitted["metadata"] is metadata
    assert emitted["tools"] is tools
    assert emitted["messages"] == sample["messages"]
    assert emitted["messages"] is not sample["messages"]
    assert emitted["messages"][0] is not sample["messages"][0]


def test_passthrough_without_extractable_pairs_reuses_top_level_metadata_but_copies_messages() -> None:
    tokenizer = _FakeTokenizer()
    metadata = {"tags": ["malformed"]}
    sample = {
        "id": "no-pairs-copy-contract",
        "metadata": metadata,
        "messages": [
            {"role": "assistant", "content": "leading assistant"},
        ],
    }

    chunked, _ = chunk_long_samples([sample], chunk_size=1, tokenizer=tokenizer)

    emitted = chunked[0]
    assert emitted["metadata"] is metadata
    assert emitted["messages"] == sample["messages"]
    assert emitted["messages"] is not sample["messages"]
    assert emitted["messages"][0] is not sample["messages"][0]


def test_passthrough_without_extractable_pairs_skips_rendering() -> None:
    tokenizer = _CountingTokenizer()
    sample = {
        "id": "no-pairs-no-render",
        "messages": [
            {"role": "assistant", "content": _words(200)},
        ],
    }

    chunked, stats = chunk_long_samples([sample], chunk_size=1, tokenizer=tokenizer)

    assert stats.chunk_count == len(chunked) == 1
    assert chunked[0]["messages"] == sample["messages"]
    assert tokenizer.render_calls == 0


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


def test_single_turn_search_stops_candidate_rendering_after_first_oversized_segment() -> None:
    tokenizer = _CountingTokenizer()
    sample = {
        "id": "early-exit",
        "messages": [
            {"role": "user", "content": _words(200)},
            {"role": "assistant", "content": _words(50)},
        ],
    }

    chunked, stats = chunk_long_samples([sample], chunk_size=80, tokenizer=tokenizer)

    assert stats.chunk_count == len(chunked) == 10
    assert tokenizer.render_calls <= 18
    for idx, chunk in enumerate(chunked):
        rendered = tokenizer.apply_chat_template(
            chunk["messages"], add_generation_prompt=False, return_dict=False
        )
        assert len(rendered) <= 80, f"chunk {idx} over budget: {len(rendered)}"


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



def test_chunked_outputs_copy_message_dicts_without_deepcopying_string_payloads() -> None:
    tokenizer = _FakeTokenizer()
    metadata = {"tags": ["chunked"]}
    user_content = _TrackingStr(_words(200))
    sample = {
        "id": "chunked-copy-contract",
        "metadata": metadata,
        "messages": [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": _TrackingStr("ack")},
        ],
    }

    chunked, stats = chunk_long_samples(
        [sample], chunk_size=80, tokenizer=tokenizer
    )

    assert stats.chunk_count == len(chunked) >= 2
    for idx, emitted in enumerate(chunked):
        assert emitted["id"] == f"chunked-copy-contract#chunk-{idx}"
        assert emitted["metadata"] is metadata
        assert emitted["messages"] is not sample["messages"]
        for message, source_message in zip(
            emitted["messages"], sample["messages"], strict=False
        ):
            assert message is not source_message
    chunked[0]["messages"][0]["content"] = "mutated"
    assert sample["messages"][0]["content"] == user_content


def test_chunked_outputs_filter_top_level_keys_once_per_source_sample() -> None:
    tokenizer = _FakeTokenizer()
    metadata = {f"tag-{idx}": idx for idx in range(80)}
    tools = [{"type": "function", "function": {"name": "lookup"}}]
    sample = _ItemsCountingDict(
        {
            "id": "chunked-top-level-scan",
            "metadata": metadata,
            "tools": tools,
            "messages": [
                {"role": "user", "content": _words(600)},
                {"role": "assistant", "content": "ack"},
            ],
        }
    )

    chunked, stats = chunk_long_samples([sample], chunk_size=80, tokenizer=tokenizer)

    assert stats.chunk_count == len(chunked) >= 8
    assert sample.items_calls == 1
    for idx, emitted in enumerate(chunked):
        assert emitted["id"] == f"chunked-top-level-scan#chunk-{idx}"
        assert emitted["metadata"] is metadata
        assert emitted["tools"] is tools
        assert emitted["messages"] is not sample["messages"]


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


class _CountingTokenizer(_FakeTokenizer):
    def __init__(self, *, overhead_per_message: int = 5) -> None:
        super().__init__(overhead_per_message=overhead_per_message)
        self.render_calls = 0

    def apply_chat_template(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]] | None = None,
        add_generation_prompt: bool = False,
        return_dict: bool = False,
    ) -> list[int]:
        self.render_calls += 1
        return super().apply_chat_template(
            messages,
            tools=tools,
            add_generation_prompt=add_generation_prompt,
            return_dict=return_dict,
        )


def test_impossible_single_turn_short_circuits_before_trying_many_segment_counts() -> None:
    tokenizer = _CountingTokenizer()
    sample = {
        "id": "impossible-short-circuit",
        "messages": [
            {"role": "user", "content": _words(100)},
            {"role": "assistant", "content": _words(200)},
        ],
    }

    with pytest.raises(ModelOperationError) as exc:
        chunk_long_samples([sample], chunk_size=205, tokenizer=tokenizer)

    assert exc.value.code == "chunk_size_too_small"
    assert tokenizer.render_calls == 2


def test_single_turn_chunking_reuses_full_render_length() -> None:
    tokenizer = _CountingTokenizer()
    sample = {
        "id": "single-turn-render-reuse",
        "messages": [
            {"role": "user", "content": _words(200)},
            {"role": "assistant", "content": "ack ack ack"},
        ],
    }

    chunked, stats = chunk_long_samples([sample], chunk_size=80, tokenizer=tokenizer)

    assert stats.chunk_count == len(chunked) >= 3
    assert tokenizer.render_calls == 5


def test_single_pair_with_trailing_malformed_messages_uses_pair_local_render_length() -> None:
    tokenizer = _FakeTokenizer()
    clean_sample = {
        "id": "clean-single-pair",
        "messages": [
            {"role": "user", "content": _words(150)},
            {"role": "assistant", "content": "ack ack ack"},
        ],
    }
    malformed_sample = {
        "id": "trailing-malformed-extra",
        "messages": [
            *clean_sample["messages"],
            {"role": "tool", "content": _words(100)},
        ],
    }

    clean_chunked, clean_stats = chunk_long_samples(
        [clean_sample], chunk_size=80, tokenizer=tokenizer
    )
    malformed_chunked, malformed_stats = chunk_long_samples(
        [malformed_sample], chunk_size=80, tokenizer=tokenizer
    )

    assert clean_stats.chunk_count == len(clean_chunked) == 3
    assert malformed_stats.chunk_count == len(malformed_chunked) == 3
    assert [chunk["messages"] for chunk in malformed_chunked] == [
        chunk["messages"] for chunk in clean_chunked
    ]


class _NoSplitTokenizer:
    """Tokenizer stub that avoids calling ``content.split()`` itself."""

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
            total += 5 + len(content)
        if add_generation_prompt:
            total += 5
        return list(range(total))


class _CountingContent(str):
    def __new__(cls, value: str) -> "_CountingContent":
        instance = super().__new__(cls, value)
        instance.split_calls = 0
        return instance

    def split(self, *args: Any, **kwargs: Any) -> list[str]:
        self.split_calls += 1
        return super().split(*args, **kwargs)


def test_split_words_into_k_matches_string_helper_output() -> None:
    content = "alpha beta gamma delta epsilon zeta"

    assert _split_words_into_k(content.split(), 3) == _split_user_content_into_k(content, 3)
    assert _split_words_into_k(["alpha", "beta"], 1) == ["alpha beta"]


def test_single_turn_chunking_streams_candidate_segments_without_list_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tokenizer = _FakeTokenizer()
    sample = {
        "id": "streamed-candidate-segments",
        "messages": [
            {"role": "user", "content": _words(240)},
            {"role": "assistant", "content": "ack"},
        ],
    }

    monkeypatch.setattr(chunker, "_split_words_into_k", pytest.fail)

    chunked, stats = chunk_long_samples([sample], chunk_size=80, tokenizer=tokenizer)

    assert stats.chunk_count == len(chunked) >= 3
    assert all(
        len(
            tokenizer.apply_chat_template(
                emitted["messages"], add_generation_prompt=False, return_dict=False
            )
        )
        <= 80
        for emitted in chunked
    )


def test_chunking_reuses_presplit_user_words_across_k_attempts() -> None:
    tokenizer = _NoSplitTokenizer()
    user_content = _CountingContent("alpha beta gamma delta epsilon zeta eta theta iota kappa")
    sample = {
        "id": "presplit-reuse",
        "messages": [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": "reply"},
        ],
    }

    chunked, stats = chunk_long_samples([sample], chunk_size=35, tokenizer=tokenizer)

    assert stats.chunk_count == len(chunked) >= 2
    assert user_content.split_calls == 1


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


class _ToolsTrackingTokenizer(_FakeTokenizer):
    """Same as _FakeTokenizer but records every ``tools`` value it saw.

    Used to prove that the chunker forwards ``tools`` into every
    ``apply_chat_template`` call — not just the full-sample length check.
    If the chunker dropped ``tools`` in the segmentation loop, the recorded
    list would contain a ``None`` entry and the assertion would fail.
    """

    def __init__(self, *, overhead_per_message: int = 5) -> None:
        super().__init__(overhead_per_message=overhead_per_message)
        self.tools_calls: list[Any] = []

    def apply_chat_template(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]] | None = None,
        add_generation_prompt: bool = False,
        return_dict: bool = False,
    ) -> list[int]:
        self.tools_calls.append(tools)
        return super().apply_chat_template(
            messages,
            tools=tools,
            add_generation_prompt=add_generation_prompt,
            return_dict=return_dict,
        )


def test_tools_are_forwarded_into_every_render_call() -> None:
    tokenizer = _ToolsTrackingTokenizer()
    tool_schema = [{"type": "function", "function": {"name": "lookup"}}]
    sample = {
        "id": "with-tools",
        "tools": tool_schema,
        "messages": [
            {"role": "user", "content": _words(200)},
            {"role": "assistant", "content": "ack"},
        ],
    }

    chunked, _ = chunk_long_samples(
        [sample], chunk_size=80, tokenizer=tokenizer
    )

    # The chunker made at least 2 render calls (initial fit check + K probes).
    # Every one must have received the tools schema.
    assert tokenizer.tools_calls, "chunker must render at least once"
    assert all(
        tools == tool_schema for tools in tokenizer.tools_calls
    ), f"tools was dropped on some render: {tokenizer.tools_calls}"
    # Tools survive on every emitted chunk.
    assert all(chunk.get("tools") == tool_schema for chunk in chunked)


def test_chunk_size_too_small_message_distinguishes_word_shortage() -> None:
    """When user content has too few words for the required K, the error
    names the word shortage rather than blaming the assistant prefix."""

    tokenizer = _FakeTokenizer()
    # 10 words of user content, long assistant, tiny chunk_size. K_floor
    # will exceed the 10-word budget.
    sample = {
        "id": "few-words",
        "messages": [
            {"role": "user", "content": _words(10)},
            {"role": "assistant", "content": _words(60)},
        ],
    }

    with pytest.raises(ModelOperationError) as exc:
        chunk_long_samples([sample], chunk_size=30, tokenizer=tokenizer)

    assert exc.value.code == "chunk_size_too_small"
    assert "few-words" in (exc.value.message or "")


def test_invalid_messages_list_raises_invalid_dataset_package() -> None:
    tokenizer = _FakeTokenizer()

    with pytest.raises(ModelOperationError) as exc:
        chunk_long_samples([{"id": "bad-messages", "messages": None}], chunk_size=10, tokenizer=tokenizer)

    assert exc.value.code == "invalid_dataset_package"
    assert "non-empty 'messages' list" in (exc.value.message or "")


def test_invalid_tools_type_raises_invalid_dataset_package() -> None:
    tokenizer = _FakeTokenizer()
    sample = {
        "id": "bad-tools",
        "tools": {"name": "lookup"},
        "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "ok"},
        ],
    }

    with pytest.raises(ModelOperationError) as exc:
        chunk_long_samples([sample], chunk_size=10, tokenizer=tokenizer)

    assert exc.value.code == "invalid_dataset_package"
    assert "'tools' to be a list" in (exc.value.message or "")


def test_non_string_user_content_raises_invalid_dataset_package() -> None:
    class _ConstantLengthTokenizer(_FakeTokenizer):
        def apply_chat_template(
            self,
            messages: list[dict[str, str]],
            *,
            tools: list[dict[str, Any]] | None = None,
            add_generation_prompt: bool = False,
            return_dict: bool = False,
        ) -> list[int]:
            return list(range(50))

    tokenizer = _ConstantLengthTokenizer()
    sample = {
        "id": "bad-user-content",
        "messages": [
            {"role": "user", "content": ["not", "a", "string"]},
            {"role": "assistant", "content": "ok"},
        ],
    }

    with pytest.raises(ModelOperationError) as exc:
        chunk_long_samples([sample], chunk_size=20, tokenizer=tokenizer)

    assert exc.value.code == "invalid_dataset_package"
    assert "bad-user-content" in (exc.value.message or "")
    assert "list" in (exc.value.message or "")


def test_chunk_size_must_be_positive() -> None:
    tokenizer = _FakeTokenizer()

    with pytest.raises(ModelOperationError) as exc:
        chunk_long_samples([], chunk_size=0, tokenizer=tokenizer)

    assert exc.value.code == "invalid_argument"
    assert "chunk_size must be >= 1" in (exc.value.message or "")


def test_malformed_multi_turn_stops_pair_extraction_at_first_non_user_assistant_pair() -> None:
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": _words(20)},
        {"role": "assistant", "content": "a1"},
        {"role": "tool", "content": "unexpected"},
        {"role": "assistant", "content": "a2"},
    ]

    system_prefix, pairs = _split_messages_into_turns(messages)

    assert system_prefix == [messages[0]]
    assert pairs == [(messages[1], messages[2])]


def test_split_user_content_into_k_handles_trivial_and_word_shortage_cases() -> None:
    assert _split_user_content_into_k("alpha beta", 1) == ["alpha beta"]
    assert _split_user_content_into_k("alpha beta", 3) == ["alpha", "beta"]
