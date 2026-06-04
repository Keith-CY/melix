from __future__ import annotations

import threading
from typing import Any

import pytest

from worker.runtime.prefix_block_store import (
    PrefixBlockStore,
    LCPResult,
    _split_blocks,
    _count_matching_blocks,
    clone_cache_snapshot,
    get_store,
    reset_store,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_snapshot(value: Any = "snapshot") -> Any:
    return {"data": value}


def _put(store: PrefixBlockStore, session_id: str, tokens: list[int], **kwargs: Any) -> None:
    store.put(
        session_id=session_id,
        token_ids=tokens,
        cache_snapshot=_make_snapshot(session_id),
        cache_mode="CACHE_MODE_TIERED",
        model_id=kwargs.get("model_id", "m1"),
        model_revision=kwargs.get("model_revision", "r1"),
        block_size=kwargs.get("block_size", 4),
        total_bytes=kwargs.get("total_bytes", 1024),
        acceleration_mode=kwargs.get("acceleration_mode", ""),
    )


# ---------------------------------------------------------------------------
# _split_blocks
# ---------------------------------------------------------------------------


def test_split_blocks_empty() -> None:
    assert _split_blocks([], 4) == []


def test_split_blocks_less_than_one_block() -> None:
    assert _split_blocks([1, 2, 3], 4) == []


def test_split_blocks_exact() -> None:
    result = _split_blocks([1, 2, 3, 4], 4)
    assert result == [(1, 2, 3, 4)]


def test_split_blocks_two_complete_plus_partial() -> None:
    result = _split_blocks(list(range(9)), 4)
    assert result == [(0, 1, 2, 3), (4, 5, 6, 7)]


# ---------------------------------------------------------------------------
# _count_matching_blocks
# ---------------------------------------------------------------------------


def test_count_matching_blocks_empty() -> None:
    assert _count_matching_blocks([], []) == 0


def test_count_matching_blocks_all_match() -> None:
    blocks = [(1, 2), (3, 4)]
    assert _count_matching_blocks(blocks, blocks) == 2


def test_count_matching_blocks_first_differs() -> None:
    a = [(1, 2), (3, 4)]
    b = [(9, 9), (3, 4)]
    assert _count_matching_blocks(a, b) == 0


def test_count_matching_blocks_partial() -> None:
    a = [(1, 2), (3, 4), (5, 6)]
    b = [(1, 2), (3, 4), (9, 9)]
    assert _count_matching_blocks(a, b) == 2


# ---------------------------------------------------------------------------
# PrefixBlockStore.put / session_count / total_bytes
# ---------------------------------------------------------------------------


def test_put_and_retrieve() -> None:
    store = PrefixBlockStore()
    _put(store, "s1", list(range(8)))
    assert store.session_count() == 1


def test_put_replaces_existing() -> None:
    store = PrefixBlockStore()
    _put(store, "s1", list(range(8)), total_bytes=100)
    _put(store, "s1", list(range(12)), total_bytes=200)
    assert store.session_count() == 1
    assert store.total_bytes() == 200


def test_put_empty_session_id_is_ignored() -> None:
    store = PrefixBlockStore()
    _put(store, "", list(range(8)))
    assert store.session_count() == 0


# ---------------------------------------------------------------------------
# acquire / release — two-level ownership
# ---------------------------------------------------------------------------


def test_acquire_returns_entry_with_incremented_active_ref() -> None:
    store = PrefixBlockStore()
    _put(store, "s1", list(range(8)))
    entry = store.acquire("s1")
    assert entry is not None
    assert entry._active_refs == 1


def test_acquire_missing_returns_none() -> None:
    store = PrefixBlockStore()
    assert store.acquire("missing") is None


def test_release_after_acquire_clears_active_ref() -> None:
    store = PrefixBlockStore()
    _put(store, "s1", list(range(8)))
    entry = store.acquire("s1")
    assert entry is not None
    store.release(entry)
    assert entry._active_refs == 0


def test_release_with_pinned_does_not_free() -> None:
    store = PrefixBlockStore()
    _put(store, "s1", list(range(8)))
    entry = store.acquire("s1")
    assert entry is not None
    store.release(entry)
    assert entry.cache_snapshot is not None  # still alive — LRU pin holds it


def test_cleanup_called_only_after_both_refs_zero() -> None:
    cleaned: list[str] = []

    def on_cleanup(e: Any) -> None:
        cleaned.append(e.session_id)

    store = PrefixBlockStore(on_cleanup=on_cleanup)
    _put(store, "s1", list(range(8)))
    entry = store.acquire("s1")
    assert entry is not None

    # Evict (drop pinned ref) while active ref is still held
    with store._lock:
        existing = store._sessions.pop("s1", None)
        if existing:
            store._total_bytes = max(0, store._total_bytes - existing.total_bytes)
            existing.unpin()
    assert "s1" not in cleaned  # active ref still held

    # Release active ref → cleanup fires
    store.release(entry)
    store.flush_deferred_clear()
    assert "s1" in cleaned


def test_cleanup_entry_is_idempotent_under_double_release() -> None:
    cleaned: list[str] = []

    def on_cleanup(e: Any) -> None:
        cleaned.append(e.session_id)

    store = PrefixBlockStore(min_session_count=0, on_cleanup=on_cleanup)
    _put(store, "s1", list(range(8)))
    entry = store.acquire("s1")
    assert entry is not None

    # Unpin so the entry is fully owned by the single active ref.
    with store._lock:
        store._sessions.pop("s1", None)
        entry.unpin()

    # First release finalizes; a buggy double-release must not fire cleanup twice.
    store.release(entry)
    store.release(entry)
    store.flush_deferred_clear()
    assert cleaned == ["s1"]


# ---------------------------------------------------------------------------
# find_lcp — basic matching
# ---------------------------------------------------------------------------


def test_find_lcp_no_match_when_store_empty() -> None:
    store = PrefixBlockStore()
    result = store.find_lcp([1, 2, 3, 4, 5, 6, 7, 8], "m1", "r1", 4)
    assert result.mode == "none"
    assert result.recovered_prefix_tokens == 0
    assert result.entry is None


def test_find_lcp_shorter_prompt_fully_covered_is_exact() -> None:
    # New prompt is a full block-aligned prefix of a longer stored prompt: every
    # token of the request is cached, so the hit is "exact" with an empty suffix.
    store = PrefixBlockStore()
    _put(store, "s1", [1, 2, 3, 4, 5, 6, 7, 8])
    result = store.find_lcp([1, 2, 3, 4], "m1", "r1", 4)
    assert result.mode == "exact"
    assert result.recovered_prefix_tokens == 4
    assert result.suffix_token_ids == []
    assert result.entry is not None
    store.release(result.entry)


def test_find_lcp_partial_match() -> None:
    store = PrefixBlockStore()
    # stored: 8 tokens (2 blocks of 4)
    _put(store, "s1", [1, 2, 3, 4, 5, 6, 7, 8])
    # new prompt shares first block, differs in second
    result = store.find_lcp([1, 2, 3, 4, 9, 9, 9, 9], "m1", "r1", 4)
    assert result.mode == "partial"
    assert result.recovered_prefix_tokens == 4
    assert result.suffix_token_ids == [9, 9, 9, 9]
    assert result.entry is not None
    store.release(result.entry)


def test_find_lcp_exact_match() -> None:
    store = PrefixBlockStore()
    tokens = [1, 2, 3, 4, 5, 6, 7, 8]
    _put(store, "s1", tokens)
    result = store.find_lcp(tokens, "m1", "r1", 4)
    assert result.mode == "exact"
    assert result.recovered_prefix_tokens == 8
    assert result.suffix_token_ids == []
    assert result.entry is not None
    store.release(result.entry)


def test_find_lcp_too_short_returns_none() -> None:
    store = PrefixBlockStore()
    _put(store, "s1", [1, 2, 3, 4])
    # new prompt only matches 3 tokens — less than one block of 4
    result = store.find_lcp([1, 2, 3, 9, 9, 9, 9, 9], "m1", "r1", 4)
    assert result.mode == "none"
    assert result.fallback_reason == "no_reusable_prefix"


def test_find_lcp_model_mismatch_skipped() -> None:
    store = PrefixBlockStore()
    _put(store, "s1", [1, 2, 3, 4, 5, 6, 7, 8], model_id="m1", model_revision="r1")
    result = store.find_lcp([1, 2, 3, 4, 5, 6, 7, 8], "m2", "r1", 4)
    assert result.mode == "none"


def test_find_lcp_revision_mismatch_skipped() -> None:
    store = PrefixBlockStore()
    _put(store, "s1", [1, 2, 3, 4, 5, 6, 7, 8], model_id="m1", model_revision="r1")
    result = store.find_lcp([1, 2, 3, 4, 5, 6, 7, 8], "m1", "r2", 4)
    assert result.mode == "none"


# ---------------------------------------------------------------------------
# find_lcp — exclusion gates
# ---------------------------------------------------------------------------


def test_find_lcp_rotating_cache_excluded() -> None:
    store = PrefixBlockStore()
    store.put(
        session_id="s1",
        token_ids=[1, 2, 3, 4, 5, 6, 7, 8],
        cache_snapshot=_make_snapshot(),
        cache_mode="CACHE_MODE_ROTATING",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        total_bytes=1024,
    )
    result = store.find_lcp([1, 2, 3, 4, 5, 6, 7, 8], "m1", "r1", 4)
    assert result.mode == "none"


def test_find_lcp_active_kv_excluded_in_stored_entry() -> None:
    store = PrefixBlockStore()
    store.put(
        session_id="s1",
        token_ids=[1, 2, 3, 4, 5, 6, 7, 8],
        cache_snapshot=_make_snapshot(),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        total_bytes=1024,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
    )
    result = store.find_lcp([1, 2, 3, 4, 5, 6, 7, 8], "m1", "r1", 4)
    assert result.mode == "none"


def test_find_lcp_active_kv_excluded_in_request() -> None:
    store = PrefixBlockStore()
    _put(store, "s1", [1, 2, 3, 4, 5, 6, 7, 8])
    result = store.find_lcp(
        [1, 2, 3, 4, 5, 6, 7, 8],
        "m1",
        "r1",
        4,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
    )
    assert result.mode == "none"
    assert result.fallback_reason == "active_kv_excluded"


def test_find_lcp_active_kv_excluded_via_integer_string() -> None:
    store = PrefixBlockStore()
    _put(store, "s1", [1, 2, 3, 4, 5, 6, 7, 8])
    result = store.find_lcp([1, 2, 3, 4, 5, 6, 7, 8], "m1", "r1", 4, acceleration_mode="4")
    assert result.mode == "none"
    assert result.fallback_reason == "active_kv_excluded"


def test_find_lcp_rotating_cache_excluded_via_integer_string() -> None:
    store = PrefixBlockStore()
    store.put(
        session_id="s1",
        token_ids=[1, 2, 3, 4, 5, 6, 7, 8],
        cache_snapshot=_make_snapshot(),
        cache_mode="2",  # integer string form of CACHE_MODE_ROTATING
        model_id="m1",
        model_revision="r1",
        block_size=4,
        total_bytes=1024,
    )
    result = store.find_lcp([1, 2, 3, 4, 5, 6, 7, 8], "m1", "r1", 4)
    assert result.mode == "none"


def test_find_lcp_force_fallback() -> None:
    store = PrefixBlockStore()
    _put(store, "s1", [1, 2, 3, 4, 5, 6, 7, 8])
    result = store.find_lcp(
        [1, 2, 3, 4, 5, 6, 7, 8], "m1", "r1", 4, force_fallback=True
    )
    assert result.mode == "none"
    assert result.fallback_reason == "force_cache_fallback"


# ---------------------------------------------------------------------------
# LRU eviction — memory budget
# ---------------------------------------------------------------------------


def test_eviction_respects_memory_budget() -> None:
    store = PrefixBlockStore(max_memory_bytes=1500, min_session_count=1)
    _put(store, "s1", list(range(8)), total_bytes=1000)
    _put(store, "s2", list(range(8, 16)), total_bytes=1000)
    # s2 adding triggers eviction of s1 (exceeds 1500 budget, floor=1)
    assert store.session_count() == 1
    assert store.acquire("s1") is None
    entry = store.acquire("s2")
    assert entry is not None
    store.release(entry)


def test_eviction_respects_session_floor() -> None:
    store = PrefixBlockStore(max_memory_bytes=100, min_session_count=2)
    _put(store, "s1", list(range(8)), total_bytes=200)
    _put(store, "s2", list(range(8, 16)), total_bytes=200)
    # floor=2 prevents eviction even though both exceed budget
    assert store.session_count() == 2


# ---------------------------------------------------------------------------
# Refcount safety — eviction while active ref is held
# ---------------------------------------------------------------------------


def test_evict_while_active_ref_held_defers_cleanup() -> None:
    cleaned: list[str] = []

    def on_cleanup(e: Any) -> None:
        cleaned.append(e.session_id)

    store = PrefixBlockStore(max_memory_bytes=500, min_session_count=1, on_cleanup=on_cleanup)
    _put(store, "s1", list(range(8)), total_bytes=400)
    entry = store.acquire("s1")
    assert entry is not None

    # Evict s1 by inserting a session that exceeds budget
    _put(store, "s2", list(range(8, 16)), total_bytes=400)
    store.flush_deferred_clear()
    assert "s1" not in cleaned  # active ref still held

    # Release active ref → cleanup fires
    store.release(entry)
    store.flush_deferred_clear()
    assert "s1" in cleaned


# ---------------------------------------------------------------------------
# Deferred clear queue
# ---------------------------------------------------------------------------


def test_flush_deferred_clear_calls_callbacks() -> None:
    store = PrefixBlockStore()
    calls: list[int] = []
    store.enqueue_deferred_clear(lambda: calls.append(1))
    store.enqueue_deferred_clear(lambda: calls.append(2))
    store.flush_deferred_clear()
    assert calls == [1, 2]


def test_flush_deferred_clear_is_idempotent() -> None:
    store = PrefixBlockStore()
    calls: list[int] = []
    store.enqueue_deferred_clear(lambda: calls.append(1))
    store.flush_deferred_clear()
    store.flush_deferred_clear()
    assert calls == [1]


# ---------------------------------------------------------------------------
# Thread safety — concurrent acquire/release
# ---------------------------------------------------------------------------


def test_concurrent_acquire_release_no_leak() -> None:
    store = PrefixBlockStore()
    _put(store, "s1", list(range(64)))
    errors: list[Exception] = []
    iterations = 50

    def worker() -> None:
        for _ in range(iterations):
            entry = store.acquire("s1")
            if entry is None:
                return
            try:
                pass  # simulate work
            finally:
                store.release(entry)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if errors:
        raise errors[0]
    # After all threads complete, the entry should still exist (LRU pin holds it)
    entry = store.acquire("s1")
    assert entry is not None
    store.release(entry)


# ---------------------------------------------------------------------------
# Singleton get_store / reset_store
# ---------------------------------------------------------------------------


def test_get_store_returns_same_instance() -> None:
    reset_store()
    a = get_store()
    b = get_store()
    assert a is b


def test_reset_store_creates_fresh_instance() -> None:
    reset_store()
    a = get_store()
    reset_store()
    b = get_store()
    assert a is not b


# ---------------------------------------------------------------------------
# clone_cache_snapshot
# ---------------------------------------------------------------------------


def test_clone_cache_snapshot_none() -> None:
    assert clone_cache_snapshot(None) is None


def test_clone_cache_snapshot_returns_copy() -> None:
    from types import SimpleNamespace
    layer = SimpleNamespace(state=[1, 2, 3])
    original = [layer]
    cloned = clone_cache_snapshot(original)
    assert cloned is not None
    assert cloned is not original
    assert len(cloned) == 1


def test_clone_cache_snapshot_mutation_is_independent() -> None:
    from types import SimpleNamespace
    layer = SimpleNamespace(value=42)
    original = [layer]
    cloned = clone_cache_snapshot(original)
    assert cloned is not None
    assert cloned is not original
    assert cloned[0] is not layer
