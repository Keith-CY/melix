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
        kv_quant_profile=kwargs.get("kv_quant_profile", ""),
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
    assert _put(store, "", list(range(8))) is None
    assert store.session_count() == 0


def test_put_returns_none_when_new_entry_is_immediately_evicted() -> None:
    store = PrefixBlockStore(max_memory_bytes=0, min_session_count=0)
    inserted = store.put(
        session_id="s1",
        token_ids=[1, 2, 3, 4],
        cache_snapshot=_make_snapshot("s1"),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        total_bytes=1,
        acceleration_mode="",
    )
    assert inserted is None
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


def test_find_lcp_baseline_request_skips_active_kv_entry_without_profile() -> None:
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


def test_find_lcp_active_kv_hits_when_quant_profiles_match() -> None:
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
        kv_quant_profile="q4:g64",
    )

    result = store.find_lcp(
        [1, 2, 3, 4, 5, 6, 7, 8],
        "m1",
        "r1",
        4,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
        kv_quant_profile="q4:g64",
    )

    assert result.mode == "exact"
    assert result.recovered_prefix_tokens == 8
    assert result.fallback_reason == ""
    assert result.tier == "hot"
    assert result.entry is not None
    store.release(result.entry)


def test_find_lcp_active_kv_profile_mismatch_returns_precise_reason() -> None:
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
        kv_quant_profile="q4:g64",
    )

    result = store.find_lcp(
        [1, 2, 3, 4, 5, 6, 7, 8],
        "m1",
        "r1",
        4,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
        kv_quant_profile="q8:g64",
    )

    assert result.mode == "none"
    assert result.fallback_reason == "kv_quant_profile_mismatch"
    assert result.entry is None


def test_find_lcp_active_kv_missing_profile_returns_precise_reason() -> None:
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
    assert result.fallback_reason == "kv_quant_profile_missing"


def test_find_lcp_active_kv_missing_profile_via_integer_string() -> None:
    store = PrefixBlockStore()
    _put(store, "s1", [1, 2, 3, 4, 5, 6, 7, 8])
    result = store.find_lcp([1, 2, 3, 4, 5, 6, 7, 8], "m1", "r1", 4, acceleration_mode="4")
    assert result.mode == "none"
    assert result.fallback_reason == "kv_quant_profile_missing"


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


def test_active_kv_quantized_hot_occupancy_probe_tracks_snapshot_bytes() -> None:
    def fill_store(*, profile: str, bytes_per_session: int) -> PrefixBlockStore:
        store = PrefixBlockStore(max_memory_bytes=2048, min_session_count=0)
        for idx in range(8):
            _put(
                store,
                f"{profile}-{idx}",
                [idx, idx, idx, idx],
                total_bytes=bytes_per_session,
                acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
                kv_quant_profile=profile,
            )
        return store

    fp16 = fill_store(profile="fp16:g64", bytes_per_session=1024)
    q8 = fill_store(profile="q8:g64", bytes_per_session=512)
    q4 = fill_store(profile="q4:g64", bytes_per_session=256)

    assert fp16.session_count() == 2
    assert q8.session_count() == 4
    assert q4.session_count() == 8
    assert fp16.total_bytes() == q8.total_bytes() == q4.total_bytes() == 2048


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


def test_clone_cache_snapshot_copies_mutable_kv_buffers() -> None:
    from types import SimpleNamespace

    layer = SimpleNamespace(keys=[["k0"]], values=[["v0"]], offset=1)

    cloned = clone_cache_snapshot([layer])

    assert cloned is not None
    assert cloned[0] is not layer
    cloned[0].keys[0].append("k1")
    cloned[0].values[0].append("v1")
    assert layer.keys == [["k0"]]
    assert layer.values == [["v0"]]


def test_clone_cache_snapshot_copies_quantized_kv_buffers_and_preserves_profile_attrs() -> None:
    from types import SimpleNamespace

    layer = SimpleNamespace(
        keys=[bytearray(b"k0")],
        values=[bytearray(b"v0")],
        bits=4,
        group_size=64,
        quant_profile="q4:g64",
        offset=1,
    )

    cloned = clone_cache_snapshot([layer])

    assert cloned is not None
    assert cloned[0] is not layer
    assert cloned[0].bits == 4
    assert cloned[0].group_size == 64
    assert cloned[0].quant_profile == "q4:g64"
    cloned[0].keys[0].extend(b"k1")
    cloned[0].values[0].extend(b"v1")
    assert layer.keys == [bytearray(b"k0")]
    assert layer.values == [bytearray(b"v0")]


def test_clone_cache_snapshot_copies_mlx_array_buffers_when_available() -> None:
    from types import SimpleNamespace

    mx = pytest.importorskip("mlx.core")
    layer = SimpleNamespace(keys=mx.array([1, 2, 3]), values=mx.array([4, 5, 6]), offset=1)

    cloned = clone_cache_snapshot([layer])

    assert cloned is not None
    layer.keys[0] = 9
    cloned[0].values[0] = 8
    mx.eval(layer.keys, layer.values, cloned[0].keys, cloned[0].values)
    assert layer.keys.tolist() == [9, 2, 3]
    assert cloned[0].keys.tolist() == [1, 2, 3]
    assert layer.values.tolist() == [4, 5, 6]
    assert cloned[0].values.tolist() == [8, 5, 6]


def test_clone_cache_snapshot_copies_container_layers() -> None:
    original = [(["t0"],), {"s0"}, bytearray(b"ab")]

    cloned = clone_cache_snapshot(original)

    assert cloned is not None
    cloned[0][0].append("t1")
    cloned[1].add("s1")
    cloned[2][0] = ord("z")
    assert original == [(["t0"],), {"s0"}, bytearray(b"ab")]


def test_clone_cache_snapshot_uses_copy_method_for_buffer_values() -> None:
    from types import SimpleNamespace

    class CopyableBuffer:
        def __init__(self, values: list[str]) -> None:
            self.values = values

        def copy(self) -> "CopyableBuffer":
            return CopyableBuffer(list(self.values))

    layer = SimpleNamespace(keys=CopyableBuffer(["k0"]), values=None)

    cloned = clone_cache_snapshot([layer])

    assert cloned is not None
    cloned[0].keys.values.append("k1")
    assert layer.keys.values == ["k0"]


def test_clone_cache_snapshot_falls_back_after_copy_method_failure() -> None:
    from types import SimpleNamespace

    class CopyRaisesBuffer:
        def __init__(self, values: list[str]) -> None:
            self.values = values

        def copy(self) -> Any:
            raise RuntimeError("copy failed")

        def __deepcopy__(self, memo: dict[int, Any]) -> "CopyRaisesBuffer":
            return CopyRaisesBuffer(list(self.values))

    layer = SimpleNamespace(keys=CopyRaisesBuffer(["k0"]), values=None)

    cloned = clone_cache_snapshot([layer])

    assert cloned is not None
    cloned[0].keys.values.append("k1")
    assert layer.keys.values == ["k0"]


def test_clone_cache_snapshot_keeps_value_when_all_copy_paths_fail() -> None:
    from types import SimpleNamespace

    class UncopyableBuffer:
        def copy(self) -> "UncopyableBuffer":
            return self

        def __deepcopy__(self, memo: dict[int, Any]) -> Any:
            raise RuntimeError("deepcopy failed")

    buffer = UncopyableBuffer()
    layer = SimpleNamespace(keys=buffer, values=None)

    cloned = clone_cache_snapshot([layer])

    assert cloned is not None
    assert cloned[0].keys is buffer


def test_clone_cache_snapshot_tolerates_unreadable_and_readonly_layer_attrs() -> None:
    class ReadOnlyLayer:
        keys = None

        @property
        def state(self) -> Any:
            raise RuntimeError("state unavailable")

        @property
        def values(self) -> list[list[str]]:
            return [["v0"]]

    cloned = clone_cache_snapshot([ReadOnlyLayer()])

    assert cloned is not None
    assert len(cloned) == 1


def test_clone_cache_snapshot_returns_none_when_layer_copy_fails() -> None:
    class UncopyableLayer:
        def __reduce_ex__(self, protocol: int) -> Any:
            raise RuntimeError("copy failed")

    assert clone_cache_snapshot([UncopyableLayer()]) is None
