from __future__ import annotations

import copy
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any


# Accept both enum name and integer string (proto Python gives ints, e.g. str(4) = "4")
_ACTIVE_KV_QUANT_MODES = frozenset({"ACCELERATION_MODE_ACTIVE_KV_QUANTIZED", "4"})
_ROTATING_CACHE_MODES = frozenset({"CACHE_MODE_ROTATING", "2"})
_MIN_SESSION_FLOOR = 2
_DEFAULT_MAX_MEMORY_BYTES = 4 * 1024 ** 3  # 4 GiB


@dataclass
class LCPResult:
    mode: str  # "none", "partial", "exact"
    recovered_prefix_tokens: int
    fallback_reason: str
    entry: "_BlockEntry | None"
    suffix_token_ids: list[int]


@dataclass
class _BlockEntry:
    session_id: str
    token_ids: list[int]
    cache_snapshot: Any  # shallow clone of prompt_cache layer list after prefill
    cache_mode: str  # CacheMode enum name or integer string (e.g. "2")
    model_id: str
    model_revision: str
    block_size: int
    total_bytes: int
    acceleration_mode: str  # AccelerationMode enum name or integer string
    _active_refs: int = field(default=0, repr=False)
    _pinned: bool = field(default=True, repr=False)
    _cleaned: bool = field(default=False, repr=False)

    def acquire(self) -> None:
        self._active_refs += 1

    def release(self) -> bool:
        """Decrement active refs. Returns True when both pinned and active refs are zero."""
        if self._active_refs > 0:
            self._active_refs -= 1
        return not self._pinned and self._active_refs == 0

    def unpin(self) -> bool:
        """Drop the LRU pinned reference. Returns True when both refs are now zero."""
        self._pinned = False
        return self._active_refs == 0


class PrefixBlockStore:
    """Worker-local session block table store with two-level ownership and memory-bounded LRU.

    Lifecycle:
      put()     — stores entry with pinned ref=1, active refs=0
      acquire() — increments active refs, returns entry (or None if evicted/absent)
      release() — decrements active refs; if both pinned and active drop to 0, schedules cleanup
      evict_lru() — unpins LRU entry; cleanup deferred until all active refs also drop
    """

    def __init__(
        self,
        max_memory_bytes: int = _DEFAULT_MAX_MEMORY_BYTES,
        min_session_count: int = _MIN_SESSION_FLOOR,
        on_cleanup: Any = None,
    ) -> None:
        self._max_memory_bytes = max_memory_bytes
        self._min_session_count = min_session_count
        self._on_cleanup = on_cleanup  # callable(entry) invoked on final cleanup
        self._lock = threading.Lock()
        self._sessions: OrderedDict[str, _BlockEntry] = OrderedDict()
        self._total_bytes = 0
        self._deferred_clear_queue: list[Any] = []  # list of zero-arg callables

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def put(
        self,
        session_id: str,
        token_ids: list[int],
        cache_snapshot: Any,
        cache_mode: str,
        model_id: str,
        model_revision: str,
        block_size: int,
        total_bytes: int,
        acceleration_mode: str = "",
    ) -> None:
        """Store a prefill result. Replaces any existing entry for session_id."""
        if not session_id:
            return
        entry = _BlockEntry(
            session_id=session_id,
            token_ids=list(token_ids),
            cache_snapshot=cache_snapshot,
            cache_mode=cache_mode,
            model_id=model_id,
            model_revision=model_revision,
            block_size=max(1, block_size),
            total_bytes=total_bytes,
            acceleration_mode=acceleration_mode,
        )
        with self._lock:
            self._evict_session(session_id)
            self._sessions[session_id] = entry
            self._total_bytes += total_bytes
            self._evict_if_needed()

    def acquire(self, session_id: str) -> _BlockEntry | None:
        """Return the entry and increment its active refcount, or None if absent/evicted."""
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return None
            self._sessions.move_to_end(session_id)
            entry.acquire()
            return entry

    def release(self, entry: _BlockEntry) -> None:
        """Decrement active refcount. Triggers cleanup if both levels reach zero."""
        with self._lock:
            fully_released = entry.release()
        if fully_released:
            self._cleanup_entry(entry)

    def find_lcp(
        self,
        token_ids: list[int],
        model_id: str,
        model_revision: str,
        block_size: int,
        acceleration_mode: str = "",
        force_fallback: bool = False,
    ) -> LCPResult:
        """Find the longest common block-aligned prefix among stored sessions.

        Returns an LCPResult. If mode != "none", the matched entry has its active
        refcount incremented — the caller MUST call release() when done.
        """
        if force_fallback:
            return LCPResult(
                mode="none",
                recovered_prefix_tokens=0,
                fallback_reason="force_cache_fallback",
                entry=None,
                suffix_token_ids=list(token_ids),
            )

        if acceleration_mode in _ACTIVE_KV_QUANT_MODES:
            return LCPResult(
                mode="none",
                recovered_prefix_tokens=0,
                fallback_reason="active_kv_excluded",
                entry=None,
                suffix_token_ids=list(token_ids),
            )

        bs = max(1, block_size)
        new_blocks = _split_blocks(token_ids, bs)
        if not new_blocks:
            return LCPResult(
                mode="none",
                recovered_prefix_tokens=0,
                fallback_reason="empty_prompt",
                entry=None,
                suffix_token_ids=list(token_ids),
            )

        best_entry: _BlockEntry | None = None
        best_len = 0

        with self._lock:
            candidates = list(self._sessions.values())

        for entry in candidates:
            if entry.model_id != model_id or entry.model_revision != model_revision:
                continue
            if entry.cache_mode in _ROTATING_CACHE_MODES:
                continue
            if entry.acceleration_mode in _ACTIVE_KV_QUANT_MODES:
                continue

            stored_blocks = _split_blocks(entry.token_ids, bs)
            match_len = _count_matching_blocks(new_blocks, stored_blocks) * bs
            if match_len > best_len:
                best_len = match_len
                best_entry = entry

        if best_entry is None or best_len < bs:
            return LCPResult(
                mode="none",
                recovered_prefix_tokens=0,
                fallback_reason="no_reusable_prefix",
                entry=None,
                suffix_token_ids=list(token_ids),
            )

        with self._lock:
            live = self._sessions.get(best_entry.session_id)
            if live is None or live is not best_entry:
                return LCPResult(
                    mode="none",
                    recovered_prefix_tokens=0,
                    fallback_reason="entry_evicted",
                    entry=None,
                    suffix_token_ids=list(token_ids),
                )
            live.acquire()

        # "exact" means every token of THIS request is already cached (empty
        # suffix to replay). A shorter request that is a full prefix of a longer
        # stored prompt still counts as exact for the request — the stale stored
        # tail is trimmed by the caller before reuse.
        is_exact = best_len >= len(token_ids)
        mode = "exact" if is_exact else "partial"
        suffix = list(token_ids[best_len:])

        return LCPResult(
            mode=mode,
            recovered_prefix_tokens=best_len,
            fallback_reason="",
            entry=live,
            suffix_token_ids=suffix,
        )

    def enqueue_deferred_clear(self, callback: Any) -> None:
        """Enqueue a deferred cleanup callback (e.g. mx.clear_cache) for idle-time flush."""
        with self._lock:
            self._deferred_clear_queue.append(callback)

    def flush_deferred_clear(self) -> None:
        """Flush all enqueued deferred cleanup callbacks. Call when no requests are active."""
        with self._lock:
            queue = self._deferred_clear_queue[:]
            self._deferred_clear_queue.clear()
        for cb in queue:
            try:
                cb()
            except Exception:
                pass

    def session_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def total_bytes(self) -> int:
        with self._lock:
            return self._total_bytes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evict_session(self, session_id: str) -> None:
        """Remove and unpin an existing entry for session_id (called under lock)."""
        existing = self._sessions.pop(session_id, None)
        if existing is not None:
            self._total_bytes = max(0, self._total_bytes - existing.total_bytes)
            fully_released = existing.unpin()
            if fully_released:
                self._deferred_clear_queue.append(lambda e=existing: self._cleanup_entry(e))

    def _evict_if_needed(self) -> None:
        """Evict LRU entries until memory budget or session floor is satisfied (under lock)."""
        while (
            len(self._sessions) > self._min_session_count
            and self._total_bytes > self._max_memory_bytes
        ):
            session_id, entry = next(iter(self._sessions.items()))
            self._sessions.pop(session_id)
            self._total_bytes = max(0, self._total_bytes - entry.total_bytes)
            fully_released = entry.unpin()
            if fully_released:
                self._deferred_clear_queue.append(lambda e=entry: self._cleanup_entry(e))

    def _cleanup_entry(self, entry: _BlockEntry) -> None:
        """Final cleanup for an entry whose both reference levels have dropped to zero.

        Idempotent: a `_cleaned` flag (checked and set under the lock) guarantees
        the cleanup callback fires at most once even if release() and a deferred
        eviction race to finalize the same entry.

        The on_cleanup callback and the `cache_snapshot = None` drop run outside
        the lock, which is safe because finalization implies exclusive ownership:
        the entry has already been removed from `_sessions` (so acquire() can no
        longer hand it out), both reference levels are zero, and the `_cleaned`
        guard admits exactly one thread here. No other thread can observe or
        mutate this entry once it reaches this point, so the unsynchronized write
        cannot race.
        """
        with self._lock:
            if entry._cleaned:
                return
            entry._cleaned = True
        if self._on_cleanup is not None:
            try:
                self._on_cleanup(entry)
            except Exception:
                pass
        entry.cache_snapshot = None


# ------------------------------------------------------------------
# Module-level singleton (runtime uses this)
# ------------------------------------------------------------------

_store: PrefixBlockStore | None = None
_store_lock = threading.Lock()


def get_store(
    max_memory_bytes: int = _DEFAULT_MAX_MEMORY_BYTES,
    min_session_count: int = _MIN_SESSION_FLOOR,
) -> PrefixBlockStore:
    """Return the process-wide store singleton.

    The size parameters only take effect on the first call that constructs the
    singleton; later calls ignore them and return the existing instance. Call
    reset_store() first (e.g. in tests) to rebuild with different limits.
    """
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = PrefixBlockStore(
                    max_memory_bytes=max_memory_bytes,
                    min_session_count=min_session_count,
                )
    return _store


def reset_store() -> None:
    """Replace the singleton — used in tests."""
    global _store
    with _store_lock:
        _store = None


# ------------------------------------------------------------------
# LCP utilities
# ------------------------------------------------------------------

def _split_blocks(token_ids: list[int], block_size: int) -> list[tuple[int, ...]]:
    """Split token_ids into complete block-size chunks; trailing partial block is dropped."""
    bs = max(1, block_size)
    return [
        tuple(token_ids[i : i + bs])
        for i in range(0, len(token_ids) - bs + 1, bs)
    ]


def _count_matching_blocks(
    a: list[tuple[int, ...]], b: list[tuple[int, ...]]
) -> int:
    """Count the length of the longest common prefix of two block sequences."""
    count = 0
    for x, y in zip(a, b):
        if x == y:
            count += 1
        else:
            break
    return count


def clone_cache_snapshot(cache_snapshot: Any) -> Any:
    """Shallow-copy the prompt_cache list so the clone can be mutated independently.

    mx.array objects are immutable; only the list container needs copying.
    The cache layer objects themselves (KVCache instances) are copied shallowly —
    mlx-lm's cache contract allows independent use of cloned layer objects
    because state tensors are copy-on-write at the MLX level.
    """
    if cache_snapshot is None:
        return None
    if not isinstance(cache_snapshot, list):
        return None
    try:
        return [copy.copy(layer) for layer in cache_snapshot]
    except Exception:
        return None
