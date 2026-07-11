from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from worker.runtime.prefix_block_store import (
    ColdPrefixStore,
    PrefixBlockStore,
    estimate_cache_snapshot_bytes,
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


def test_estimate_cache_snapshot_bytes_sums_state_and_key_value_layers() -> None:
    class TensorWithNbytes:
        def __init__(self, nbytes: int) -> None:
            self.nbytes = nbytes

    class TensorWithSize:
        size = 7
        itemsize = 8

    cache_snapshot = [
        SimpleNamespace(state=[TensorWithNbytes(10), TensorWithSize()]),
        SimpleNamespace(keys=TensorWithNbytes(20), values=TensorWithSize()),
        SimpleNamespace(state=TensorWithNbytes(30)),
        SimpleNamespace(state=TensorWithSize()),
        SimpleNamespace(keys=TensorWithSize(), values=TensorWithNbytes(40)),
        SimpleNamespace(),
    ]

    assert (
        estimate_cache_snapshot_bytes(cache_snapshot)
        == 10 + 56 + 20 + 56 + 30 + 56 + 56 + 40
    )


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
        kv_quant_profile=kwargs.get("kv_quant_profile", ""),
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


def test_cold_store_allows_active_kv_when_quant_profile_present(tmp_path: Path) -> None:
    cold = _make_cold(tmp_path)
    ok = cold.store(
        session_id="s1",
        token_ids=[1, 2, 3, 4],
        cache_snapshot=_make_snapshot("s1"),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
        kv_quant_profile="q4:g64",
    )

    assert ok is True
    assert cold.entry_count() == 1
    meta, matched = cold.match(
        [1, 2, 3, 4],
        "m1",
        "r1",
        4,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
        kv_quant_profile="q4:g64",
    )
    assert meta is not None
    assert matched == 4
    assert meta.kv_quant_profile == "q4:g64"


def test_cold_match_isolates_active_kv_quant_profiles(tmp_path: Path) -> None:
    cold = _make_cold(tmp_path)
    assert cold.store(
        session_id="s1",
        token_ids=[1, 2, 3, 4],
        cache_snapshot=_make_snapshot("s1"),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
        kv_quant_profile="q4:g64",
    )

    mismatch, mismatch_len = cold.match(
        [1, 2, 3, 4],
        "m1",
        "r1",
        4,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
        kv_quant_profile="q8:g64",
    )
    assert mismatch is None
    assert mismatch_len == 0

    match, match_len = cold.match(
        [1, 2, 3, 4],
        "m1",
        "r1",
        4,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
        kv_quant_profile="q4:g64",
    )
    assert match is not None
    assert match_len == 4


def test_cold_match_baseline_request_skips_active_kv_entry(tmp_path: Path) -> None:
    cold = _make_cold(tmp_path)
    assert cold.store(
        session_id="s1",
        token_ids=[1, 2, 3, 4],
        cache_snapshot=_make_snapshot("s1"),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
        kv_quant_profile="q4:g64",
    )

    match, match_len = cold.match([1, 2, 3, 4], "m1", "r1", 4)

    assert match is None
    assert match_len == 0


def test_find_lcp_cold_active_kv_profile_mismatch_returns_precise_reason(tmp_path: Path) -> None:
    cold = _make_cold(tmp_path)
    assert cold.store(
        session_id="s1",
        token_ids=[1, 2, 3, 4],
        cache_snapshot=_make_snapshot("s1"),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
        kv_quant_profile="q4:g64",
    )
    store = PrefixBlockStore(cold_store=cold)

    result = store.find_lcp(
        [1, 2, 3, 4],
        "m1",
        "r1",
        4,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
        kv_quant_profile="q8:g64",
    )

    assert result.mode == "none"
    assert result.fallback_reason == "kv_quant_profile_mismatch"


def test_cold_kv_quant_profile_mismatch_helper_ignores_non_candidates(tmp_path: Path) -> None:
    cold = _make_cold(tmp_path)
    assert cold.store(
        session_id="model-mismatch",
        token_ids=[1, 2, 3, 4],
        cache_snapshot=_make_snapshot("model-mismatch"),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m2",
        model_revision="r1",
        block_size=4,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
        kv_quant_profile="q4:g64",
    )
    assert cold.store(
        session_id="baseline",
        token_ids=[1, 2, 3, 4],
        cache_snapshot=_make_snapshot("baseline"),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="",
    )
    assert cold.store(
        session_id="same-profile",
        token_ids=[1, 2, 3, 4],
        cache_snapshot=_make_snapshot("same-profile"),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
        kv_quant_profile="q8:g64",
    )

    assert not cold.has_kv_quant_profile_mismatch(
        [1, 2, 3],
        "m1",
        "r1",
        4,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
        kv_quant_profile="q8:g64",
    )
    assert not cold.has_kv_quant_profile_mismatch(
        [1, 2, 3, 4],
        "m1",
        "r1",
        4,
        acceleration_mode="ACCELERATION_MODE_ACTIVE_KV_QUANTIZED",
        kv_quant_profile="q8:g64",
    )


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


def test_cold_store_index_reload_skips_json_decode_for_filename_orphans(
    monkeypatch,
    tmp_path: Path,
) -> None:
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

    def fail_json_load(*args, **kwargs):  # pragma: no cover - regression guard
        raise AssertionError("orphaned cold-prefix sidecars should be pruned before JSON decode")

    monkeypatch.setattr("worker.runtime.prefix_block_store.json.load", fail_json_load)

    second = _make_cold(tmp_path)
    assert second.entry_count() == 0
    assert list((tmp_path / "cold").glob("*.meta.json")) == []


def test_cold_store_index_load_uses_scandir_without_path_glob(
    monkeypatch,
    tmp_path: Path,
) -> None:
    cold = _make_cold(tmp_path)
    assert cold.store(
        session_id="s1",
        token_ids=[1, 2, 3, 4],
        cache_snapshot=_make_snapshot("s1"),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="",
    )

    def fail_glob(self: Path, pattern: str):  # pragma: no cover - regression guard
        raise AssertionError(
            f"ColdPrefixStore index load should use os.scandir, not Path.glob({pattern!r})"
        )

    monkeypatch.setattr(Path, "glob", fail_glob)
    original_scandir = os.scandir
    scandir_calls = 0

    def counted_scandir(path: str | os.PathLike[str]):
        nonlocal scandir_calls
        scandir_calls += 1
        return original_scandir(path)

    monkeypatch.setattr("worker.runtime.prefix_block_store.os.scandir", counted_scandir)

    reloaded = ColdPrefixStore(
        tmp_path / "cold",
        serializer=_fake_serializer,
        deserializer=_fake_deserializer,
    )
    assert reloaded.entry_count() == 1
    assert scandir_calls == 1


def test_cold_store_index_load_filters_relevant_suffixes_before_file_stat(
    monkeypatch,
    tmp_path: Path,
) -> None:
    cold_root = tmp_path / "cold"
    cold_root.mkdir()

    class IrrelevantEntry:
        name = "ignored.tmp"
        path = str(cold_root / name)

        def is_file(self, *, follow_symlinks: bool = True) -> bool:
            raise AssertionError(  # pragma: no cover - regression guard
                "irrelevant entries should skip file stat"
            )

    class FakeScandir:
        def __enter__(self):
            return [IrrelevantEntry()]

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr(
        "worker.runtime.prefix_block_store.os.scandir",
        lambda path: FakeScandir(),
    )

    reloaded = ColdPrefixStore(
        cold_root,
        serializer=_fake_serializer,
        deserializer=_fake_deserializer,
    )
    assert reloaded.entry_count() == 0


def test_cold_store_index_load_reuses_scandir_snapshot_names(
    monkeypatch,
    tmp_path: Path,
) -> None:
    cold = _make_cold(tmp_path)
    assert cold.store(
        session_id="s1",
        token_ids=[1, 2, 3, 4],
        cache_snapshot=_make_snapshot("s1"),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="",
    )

    original_is_file = Path.is_file

    def fail_snapshot_path_is_file(self: Path) -> bool:
        if self.name.endswith(".kv.safetensors"):  # pragma: no cover - regression guard
            raise AssertionError(
                "ColdPrefixStore index load should use scandir snapshot names, "
                "not per-meta Path.is_file() probes"
            )
        return original_is_file(self)  # pragma: no cover - defensive fallback

    monkeypatch.setattr(Path, "is_file", fail_snapshot_path_is_file)
    reloaded = ColdPrefixStore(
        tmp_path / "cold",
        serializer=_fake_serializer,
        deserializer=_fake_deserializer,
    )
    assert reloaded.entry_count() == 1


def test_cold_store_index_load_tolerates_scandir_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    cold = _make_cold(tmp_path)
    assert cold.store(
        session_id="s1",
        token_ids=[1, 2, 3, 4],
        cache_snapshot=_make_snapshot("s1"),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="",
    )

    def fail_scandir(path: Path):  # pragma: no cover - regression guard
        raise OSError(f"scan denied: {path!s}")

    monkeypatch.setattr("worker.runtime.prefix_block_store.os.scandir", fail_scandir)

    reloaded = ColdPrefixStore(
        tmp_path / "cold",
        serializer=_fake_serializer,
        deserializer=_fake_deserializer,
    )
    assert reloaded.entry_count() == 0


def test_cold_store_index_load_skips_entries_with_metadata_errors(
    monkeypatch,
    tmp_path: Path,
) -> None:
    cold = _make_cold(tmp_path)
    assert cold.store(
        session_id="s1",
        token_ids=[1, 2, 3, 4],
        cache_snapshot=_make_snapshot("s1"),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="",
    )

    class BadEntry:
        name = "bad.meta.json"
        path = str(tmp_path / "cold" / "bad.meta.json")

        def is_file(self, *, follow_symlinks: bool = True) -> bool:
            raise OSError("metadata denied")

    original_scandir = os.scandir

    class FakeScandir:
        def __enter__(self):
            with original_scandir(tmp_path / "cold") as entries:
                return [BadEntry(), *list(entries)]

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr(
        "worker.runtime.prefix_block_store.os.scandir",
        lambda path: FakeScandir(),
    )

    reloaded = ColdPrefixStore(
        tmp_path / "cold",
        serializer=_fake_serializer,
        deserializer=_fake_deserializer,
    )
    assert reloaded.entry_count() == 1


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


def test_cold_promotion_returns_promoted_entry_when_session_is_replaced(
    tmp_path: Path,
) -> None:
    cold = _make_cold(tmp_path)
    cold.store(
        session_id="s1",
        token_ids=[1, 2, 3, 4, 5, 6, 7, 8],
        cache_snapshot=_make_snapshot("cold"),
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        acceleration_mode="",
    )

    class RacingAcquireStore(PrefixBlockStore):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.replaced_before_acquire = False

        def acquire(self, session_id: str) -> Any:
            if session_id == "s1" and not self.replaced_before_acquire:
                self.replaced_before_acquire = True
                self.put(
                    session_id="s1",
                    token_ids=[99, 98, 97, 96],
                    cache_snapshot=_make_snapshot("replacement"),
                    cache_mode="CACHE_MODE_TIERED",
                    model_id="m1",
                    model_revision="r1",
                    block_size=4,
                    total_bytes=512,
                    acceleration_mode="",
                )
            return super().acquire(session_id)

    store = RacingAcquireStore(cold_store=cold)

    result = store.find_lcp([1, 2, 3, 4, 5, 6, 7, 8], "m1", "r1", 4)

    assert result.tier == "cold"
    assert result.entry is not None
    assert result.entry.cache_snapshot == [{"data": "cold"}]
    assert store.replaced_before_acquire is False
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


def test_budget_eviction_demotes_a_stable_snapshot(tmp_path: Path) -> None:
    serialized: list[Any] = []

    def recording_serializer(cache_snapshot: Any, path: Path) -> None:
        serialized.append(cache_snapshot)
        _fake_serializer(cache_snapshot, path)

    cold = _make_cold(tmp_path, serializer=recording_serializer)
    store = PrefixBlockStore(max_memory_bytes=1500, min_session_count=1, cold_store=cold)
    evicted_snapshot = [{"data": ["stable"]}]
    entry = store.put(
        session_id="s1",
        token_ids=[1, 2, 3, 4, 5, 6, 7, 8],
        cache_snapshot=evicted_snapshot,
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        total_bytes=1000,
        acceleration_mode="",
    )
    assert entry is not None
    _put(store, "s2", [9] * 8, total_bytes=1000)  # evicts s1

    store.flush_deferred_clear()
    evicted_snapshot[0]["data"].append("mutated-after-flush")

    assert serialized == [[{"data": ["stable"]}]]
    assert entry.cache_snapshot is None
    assert cold.entry_count() == 1


def test_budget_eviction_clones_snapshot_outside_store_lock(tmp_path: Path) -> None:
    lock_states: list[bool] = []

    class LockAwareValue:
        def __init__(self, value: str) -> None:
            self.value = value

        def copy(self) -> "LockAwareValue":
            lock_states.append(store._lock.locked())
            return LockAwareValue(self.value)

    def recording_serializer(cache_snapshot: Any, path: Path) -> None:
        path.write_text("snapshot", encoding="utf-8")

    cold = _make_cold(tmp_path, serializer=recording_serializer)
    store = PrefixBlockStore(max_memory_bytes=1500, min_session_count=1, cold_store=cold)
    store.put(
        session_id="s1",
        token_ids=[1, 2, 3, 4, 5, 6, 7, 8],
        cache_snapshot=[{"data": LockAwareValue("stable")}],
        cache_mode="CACHE_MODE_TIERED",
        model_id="m1",
        model_revision="r1",
        block_size=4,
        total_bytes=1000,
        acceleration_mode="",
    )
    _put(store, "s2", [9] * 8, total_bytes=1000)  # evicts s1

    assert lock_states == []
    store.flush_deferred_clear()

    assert lock_states == [False]
    assert cold.entry_count() == 1


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
