from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worker.runtime.prefix_block_store import (
    ColdPrefixStore,
    PrefixBlockStore,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_serializer(cache_snapshot: Any, path: Path) -> None:
    path.write_text(json.dumps(cache_snapshot), encoding="utf-8")


def _fake_deserializer(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _failing_deserializer(path: Path) -> Any:
    raise RuntimeError("corrupt snapshot")


def _make_cold(tmp_path: Path, **kwargs: Any) -> ColdPrefixStore:
    kwargs.setdefault("serializer", _fake_serializer)
    kwargs.setdefault("deserializer", _fake_deserializer)
    return ColdPrefixStore(tmp_path / "cold", **kwargs)


def _make_snapshot(value: str = "snapshot") -> list[dict[str, str]]:
    # List-shaped like a prompt-cache layer list; restore() requires a list.
    return [{"data": value}]


def _put(store: PrefixBlockStore, session_id: str, tokens: list[int], **kwargs: Any) -> None:
    store.put(
        session_id=session_id,
        token_ids=tokens,
        cache_snapshot=_make_snapshot(session_id),
        cache_mode=kwargs.get("cache_mode", "CACHE_MODE_TIERED"),
        model_id=kwargs.get("model_id", "m1"),
        model_revision=kwargs.get("model_revision", "r1"),
        block_size=kwargs.get("block_size", 4),
        total_bytes=kwargs.get("total_bytes", 1024),
        acceleration_mode=kwargs.get("acceleration_mode", ""),
    )


# ---------------------------------------------------------------------------
# ColdPrefixStore — direct behavior
# ---------------------------------------------------------------------------


def test_cold_store_roundtrip(tmp_path: Path) -> None:
    cold = _make_cold(tmp_path)
    ok = cold.store(
        session_id="s1",
        token_ids=[1, 2, 3, 4],
        cache_snapshot=_make_snapshot("s1"),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="",
    )
    assert ok is True
    assert cold.entry_count() == 1
    meta, matched = cold.match([1, 2, 3, 4], "m1", "r1", 4)
    assert meta is not None
    assert matched == 4
    restored = cold.restore(meta)
    assert restored == [{"data": "s1"}]
    assert cold.hit_count == 1


def test_cold_store_rejects_active_kv_and_rotating(tmp_path: Path) -> None:
    cold = _make_cold(tmp_path)
    assert not cold.store(
        session_id="s1",
        token_ids=[1, 2, 3, 4],
        cache_snapshot=_make_snapshot(),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
    )
    assert not cold.store(
        session_id="s2",
        token_ids=[1, 2, 3, 4],
        cache_snapshot=_make_snapshot(),
        cache_mode="CACHE_MODE_ROTATING",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="",
    )
    assert cold.entry_count() == 0


def test_cold_store_serializer_failure_counts_and_leaves_no_entry(tmp_path: Path) -> None:
    def broken(cache_snapshot: Any, path: Path) -> None:
        raise OSError("disk full")

    cold = _make_cold(tmp_path, serializer=broken)
    ok = cold.store(
        session_id="s1",
        token_ids=[1, 2, 3, 4],
        cache_snapshot=_make_snapshot(),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="",
    )
    assert ok is False
    assert cold.demotion_failure_count == 1
    assert cold.entry_count() == 0


def test_cold_store_restore_failure_drops_entry(tmp_path: Path) -> None:
    cold = _make_cold(tmp_path, deserializer=_failing_deserializer)
    cold.store(
        session_id="s1",
        token_ids=[1, 2, 3, 4],
        cache_snapshot=_make_snapshot(),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="",
    )
    meta, matched = cold.match([1, 2, 3, 4], "m1", "r1", 4)
    assert meta is not None and matched == 4
    assert cold.restore(meta) is None
    assert cold.restore_failure_count == 1
    assert cold.entry_count() == 0


def test_cold_store_budget_evicts_oldest(tmp_path: Path) -> None:
    cold = _make_cold(tmp_path, max_bytes=64)
    big_snapshot = [{"data": "x" * 64}]
    cold.store(
        session_id="old",
        token_ids=[1, 2, 3, 4],
        cache_snapshot=big_snapshot,
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="",
    )
    cold.store(
        session_id="new",
        token_ids=[5, 6, 7, 8],
        cache_snapshot=big_snapshot,
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="",
    )
    assert cold.eviction_count >= 1
    meta, _ = cold.match([1, 2, 3, 4], "m1", "r1", 4)
    assert meta is None  # oldest evicted
    meta, matched = cold.match([5, 6, 7, 8], "m1", "r1", 4)
    assert meta is not None and matched == 4  # newest kept


def test_cold_store_index_reload_drops_orphaned_meta(tmp_path: Path) -> None:
    first = _make_cold(tmp_path)
    first.store(
        session_id="s1",
        token_ids=[1, 2, 3, 4],
        cache_snapshot=_make_snapshot("s1"),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="",
    )
    snapshot_files = list((tmp_path / "cold").glob("*.kv.safetensors"))
    assert len(snapshot_files) == 1
    snapshot_files[0].unlink()

    second = _make_cold(tmp_path)
    meta, _ = second.match([1, 2, 3, 4], "m1", "r1", 4)
    assert meta is None
    # The orphaned sidecar is removed so restarts stop rescanning it.
    assert list((tmp_path / "cold").glob("*.meta.json")) == []


def test_promotion_accounts_live_bytes_not_file_size(tmp_path: Path) -> None:
    cold = _make_cold(tmp_path)
    estimated: list[Any] = []

    def estimator(snapshot: Any) -> int:
        estimated.append(snapshot)
        return 4096

    store = PrefixBlockStore(
        max_memory_bytes=1500,
        min_session_count=1,
        cold_store=cold,
        bytes_estimator=estimator,
    )
    _put(store, "s1", [1, 2, 3, 4, 5, 6, 7, 8], total_bytes=1000)
    _put(store, "s2", [9] * 8, total_bytes=1000)  # evicts + demotes s1
    store.flush_deferred_clear()

    result = store.find_lcp([1, 2, 3, 4, 5, 6, 7, 8], "m1", "r1", 4)
    assert result.tier == "cold"
    assert result.entry is not None
    assert estimated  # the estimator ran on the restored snapshot
    # Hot budget accounts the estimated live footprint, not the tiny JSON
    # file size the fake serializer produced.
    assert result.entry.total_bytes == 4096
    assert store.total_bytes() >= 4096
    store.release(result.entry)


def test_promotion_falls_back_to_file_size_when_estimate_is_zero(tmp_path: Path) -> None:
    cold = _make_cold(tmp_path)
    store = PrefixBlockStore(
        max_memory_bytes=1500,
        min_session_count=1,
        cold_store=cold,
        bytes_estimator=lambda snapshot: 0,
    )
    _put(store, "s1", [1, 2, 3, 4, 5, 6, 7, 8], total_bytes=1000)
    _put(store, "s2", [9] * 8, total_bytes=1000)
    store.flush_deferred_clear()

    result = store.find_lcp([1, 2, 3, 4, 5, 6, 7, 8], "m1", "r1", 4)
    assert result.tier == "cold"
    assert result.entry is not None
    assert result.entry.total_bytes > 0  # serialized size, better than zero
    store.release(result.entry)


def test_cold_store_reloads_index_from_disk(tmp_path: Path) -> None:
    first = _make_cold(tmp_path)
    first.store(
        session_id="s1",
        token_ids=[1, 2, 3, 4],
        cache_snapshot=_make_snapshot("s1"),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="",
    )
    second = _make_cold(tmp_path)
    meta, matched = second.match([1, 2, 3, 4, 9, 9, 9, 9], "m1", "r1", 4)
    assert meta is not None
    assert matched == 4
    assert second.restore(meta) == [{"data": "s1"}]


# ---------------------------------------------------------------------------
# PrefixBlockStore + cold tier — demotion and promotion
# ---------------------------------------------------------------------------


def test_budget_eviction_demotes_to_cold_tier(tmp_path: Path) -> None:
    cold = _make_cold(tmp_path)
    store = PrefixBlockStore(max_memory_bytes=1500, min_session_count=1, cold_store=cold)
    _put(store, "s1", [1, 2, 3, 4, 5, 6, 7, 8], total_bytes=1000)
    _put(store, "s2", [9] * 8, total_bytes=1000)  # evicts s1
    assert store.session_count() == 1
    assert cold.entry_count() == 0  # demotion is deferred
    store.flush_deferred_clear()
    assert cold.entry_count() == 1
    assert cold.demotion_count == 1


def test_same_session_replacement_does_not_demote(tmp_path: Path) -> None:
    cold = _make_cold(tmp_path)
    store = PrefixBlockStore(cold_store=cold)
    _put(store, "s1", [1, 2, 3, 4], total_bytes=100)
    _put(store, "s1", [1, 2, 3, 4, 5, 6, 7, 8], total_bytes=200)
    store.flush_deferred_clear()
    assert cold.entry_count() == 0
    assert cold.demotion_count == 0


def test_cold_hit_promotes_back_to_hot(tmp_path: Path) -> None:
    cold = _make_cold(tmp_path)
    store = PrefixBlockStore(max_memory_bytes=1500, min_session_count=1, cold_store=cold)
    _put(store, "s1", [1, 2, 3, 4, 5, 6, 7, 8], total_bytes=1000)
    _put(store, "s2", [9] * 8, total_bytes=1000)  # evicts + demotes s1
    store.flush_deferred_clear()
    assert cold.entry_count() == 1

    result = store.find_lcp([1, 2, 3, 4, 5, 6, 7, 8, 11, 12, 13, 14], "m1", "r1", 4)
    assert result.mode == "partial"
    assert result.tier == "cold"
    assert result.recovered_prefix_tokens == 8
    assert result.suffix_token_ids == [11, 12, 13, 14]
    assert result.entry is not None
    assert result.entry.cache_snapshot == [{"data": "s1"}]
    store.release(result.entry)

    # Promotion moved the entry: cold copy removed, hot copy resident.
    assert cold.entry_count() == 0
    assert store.promotion_count == 1
    assert store.cold_hit_count == 1
    acquired = store.acquire("s1")
    assert acquired is not None
    store.release(acquired)


def test_cold_restore_failure_falls_back_to_miss(tmp_path: Path) -> None:
    cold = _make_cold(tmp_path, deserializer=_failing_deserializer)
    store = PrefixBlockStore(max_memory_bytes=1500, min_session_count=1, cold_store=cold)
    _put(store, "s1", [1, 2, 3, 4, 5, 6, 7, 8], total_bytes=1000)
    _put(store, "s2", [9] * 8, total_bytes=1000)
    store.flush_deferred_clear()

    result = store.find_lcp([1, 2, 3, 4, 5, 6, 7, 8], "m1", "r1", 4)
    assert result.mode == "none"
    assert result.fallback_reason == "no_reusable_prefix"
    assert cold.restore_failure_count == 1
    assert cold.entry_count() == 0  # corrupt entry dropped


def test_hot_hit_preferred_over_equal_cold_match(tmp_path: Path) -> None:
    cold = _make_cold(tmp_path)
    store = PrefixBlockStore(cold_store=cold)
    tokens = [1, 2, 3, 4, 5, 6, 7, 8]
    cold.store(
        session_id="cold-session",
        token_ids=tokens,
        cache_snapshot=_make_snapshot("cold"),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="",
    )
    _put(store, "hot-session", tokens)
    result = store.find_lcp(tokens, "m1", "r1", 4)
    assert result.mode == "exact"
    assert result.tier == "hot"
    assert result.entry is not None
    store.release(result.entry)
    assert store.cold_hit_count == 0


def test_longer_cold_match_beats_shorter_hot_match(tmp_path: Path) -> None:
    cold = _make_cold(tmp_path)
    store = PrefixBlockStore(cold_store=cold)
    request = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    _put(store, "hot-session", [1, 2, 3, 4, 99, 99, 99, 99])  # 1 block match
    cold.store(
        session_id="cold-session",
        token_ids=[1, 2, 3, 4, 5, 6, 7, 8],  # 2 block match
        cache_snapshot=_make_snapshot("cold"),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="",
    )
    result = store.find_lcp(request, "m1", "r1", 4)
    assert result.tier == "cold"
    assert result.recovered_prefix_tokens == 8
    assert result.entry is not None
    store.release(result.entry)


def test_stats_reports_tiered_counters(tmp_path: Path) -> None:
    cold = _make_cold(tmp_path)
    store = PrefixBlockStore(max_memory_bytes=1500, min_session_count=1, cold_store=cold)
    _put(store, "s1", [1, 2, 3, 4, 5, 6, 7, 8], total_bytes=1000)

    hit = store.find_lcp([1, 2, 3, 4, 5, 6, 7, 8], "m1", "r1", 4)
    assert hit.entry is not None
    store.release(hit.entry)
    miss = store.find_lcp([70, 71, 72, 73], "m1", "r1", 4)
    assert miss.mode == "none"

    _put(store, "s2", [9] * 8, total_bytes=1000)
    store.flush_deferred_clear()
    promoted = store.find_lcp([1, 2, 3, 4, 5, 6, 7, 8], "m1", "r1", 4)
    assert promoted.tier == "cold"
    assert promoted.entry is not None
    store.release(promoted.entry)

    stats = store.stats()
    assert stats["hot_hit_count"] == 1
    assert stats["miss_count"] == 1
    assert stats["cold_hit_count"] == 1
    assert stats["promotion_count"] == 1
    assert stats["cold_demotion_count"] == 1
    assert stats["cold_entry_count"] == 0


def test_stats_without_cold_store_zeroes_cold_counters() -> None:
    store = PrefixBlockStore()
    stats = store.stats()
    assert stats["cold_demotion_count"] == 0
    assert stats["cold_entry_count"] == 0
    assert stats["cold_total_bytes"] == 0
