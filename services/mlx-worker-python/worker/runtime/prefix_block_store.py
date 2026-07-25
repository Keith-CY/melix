from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
import time
from builtins import open as _OPEN
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Accept both enum name and integer string (proto Python gives ints, e.g. str(4) = "4")
_ACTIVE_KV_QUANT_MODES = frozenset({"ACCELERATION_MODE_ACTIVE_KV_QUANTIZED", "4"})
_ROTATING_CACHE_MODES = frozenset({"CACHE_MODE_ROTATING", "2"})
_MIN_SESSION_FLOOR = 2
_DEFAULT_MAX_MEMORY_BYTES = 4 * 1024 ** 3  # 4 GiB
_DEFAULT_COLD_MAX_BYTES = 8 * 1024 ** 3  # 8 GiB
_COLD_DIR_ENV = "MELIX_PREFIX_CACHE_COLD_DIR"
_COLD_MAX_BYTES_ENV = "MELIX_PREFIX_CACHE_COLD_MAX_BYTES"
_CACHE_STATE_SEQUENCE_TYPES = (list, tuple)


def _is_active_kv_quant_mode(acceleration_mode: str) -> bool:
    return str(acceleration_mode or "") in _ACTIVE_KV_QUANT_MODES


def _normalize_kv_quant_profile(kv_quant_profile: str) -> str:
    return str(kv_quant_profile or "").strip()


@dataclass
class LCPResult:
    mode: str  # "none", "partial", "exact"
    recovered_prefix_tokens: int
    fallback_reason: str
    entry: "_BlockEntry | None"
    suffix_token_ids: list[int]
    tier: str = ""  # "hot", "cold", or "" when mode == "none"


@dataclass
class _BlockEntry:
    session_id: str
    token_ids: list[int]
    cache_snapshot: Any  # stable clone of prompt_cache layer list after prefill
    cache_mode: str  # CacheMode enum name or integer string (e.g. "2")
    model_id: str
    model_revision: str
    block_size: int
    total_bytes: int
    acceleration_mode: str  # AccelerationMode enum name or integer string
    kv_quant_profile: str = ""
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


@dataclass
class ColdEntryMeta:
    """Index record for one demoted session snapshot on disk."""

    session_id: str
    token_ids: list[int]
    cache_mode: str
    model_id: str
    model_revision: str
    block_size: int
    total_bytes: int
    acceleration_mode: str
    kv_quant_profile: str
    stored_at: float
    snapshot_path: Path
    meta_path: Path


def _default_cold_serializer(cache_snapshot: Any, path: Path) -> None:
    """Persist a prompt-cache layer list as safetensors via mlx-lm."""
    from mlx_lm.models.cache import save_prompt_cache

    save_prompt_cache(str(path), cache_snapshot)


def _default_cold_deserializer(path: Path) -> Any:
    """Restore a prompt-cache layer list persisted by the default serializer."""
    from mlx_lm.models.cache import load_prompt_cache

    restored = load_prompt_cache(str(path))
    # Newer mlx-lm versions may return (cache, metadata) when asked; the
    # plain call returns the cache list. Unwrap defensively.
    if isinstance(restored, tuple) and restored and isinstance(restored[0], list):
        return restored[0]
    return restored


class ColdPrefixStore:
    """Disk (L2) tier for demoted prefix KV snapshots.

    Hot-tier evictions are demoted here instead of being dropped, and hot-tier
    misses consult this index before falling back to a full re-prefill. Each
    session keeps at most one cold entry (newest wins). Files are a
    `<digest>.kv.safetensors` snapshot plus a `<digest>.meta.json` sidecar; the
    sidecar is written last so a crash mid-demotion leaves no indexed entry.

    The serializer/deserializer default to mlx-lm's prompt-cache persistence
    and are injectable so the tier is unit-testable without MLX installed.
    """

    def __init__(
        self,
        root_dir: Path | str,
        max_bytes: int = _DEFAULT_COLD_MAX_BYTES,
        serializer: Any = None,
        deserializer: Any = None,
    ) -> None:
        self._root = Path(root_dir)
        self._max_bytes = max(0, int(max_bytes))
        self._serializer = serializer or _default_cold_serializer
        self._deserializer = deserializer or _default_cold_deserializer
        self._lock = threading.Lock()
        self._index: dict[str, ColdEntryMeta] = {}
        self._loaded = False
        self.demotion_count = 0
        self.demotion_failure_count = 0
        self.hit_count = 0
        self.restore_failure_count = 0
        self.eviction_count = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store(
        self,
        *,
        session_id: str,
        token_ids: list[int],
        cache_snapshot: Any,
        cache_mode: str,
        model_id: str,
        model_revision: str,
        block_size: int,
        acceleration_mode: str,
        kv_quant_profile: str = "",
    ) -> bool:
        """Demote one snapshot to disk. Returns True when the entry was indexed."""
        if not session_id or cache_snapshot is None:
            return False
        normalized_profile = _normalize_kv_quant_profile(kv_quant_profile)
        if _is_active_kv_quant_mode(acceleration_mode) and not normalized_profile:
            return False
        if cache_mode in _ROTATING_CACHE_MODES:
            return False
        with self._lock:
            self._ensure_loaded_locked()
        digest = _session_digest(session_id)
        snapshot_path = self._root / f"{digest}.kv.safetensors"
        meta_path = self._root / f"{digest}.meta.json"
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            self._serializer(cache_snapshot, snapshot_path)
            total_bytes = snapshot_path.stat().st_size
            meta = ColdEntryMeta(
                session_id=session_id,
                token_ids=list(token_ids),
                cache_mode=cache_mode,
                model_id=model_id,
                model_revision=model_revision,
                block_size=max(1, block_size),
                total_bytes=int(total_bytes),
                acceleration_mode=acceleration_mode,
                kv_quant_profile=normalized_profile,
                stored_at=time.time(),
                snapshot_path=snapshot_path,
                meta_path=meta_path,
            )
            meta_path.write_text(
                json.dumps(
                    {
                        "schema_version": "melix.prefix_cache_cold_entry.v1",
                        "session_id": meta.session_id,
                        "token_ids": meta.token_ids,
                        "cache_mode": meta.cache_mode,
                        "model_id": meta.model_id,
                        "model_revision": meta.model_revision,
                        "block_size": meta.block_size,
                        "total_bytes": meta.total_bytes,
                        "acceleration_mode": meta.acceleration_mode,
                        "kv_quant_profile": meta.kv_quant_profile,
                        "stored_at": meta.stored_at,
                    }
                ),
                encoding="utf-8",
            )
        except Exception:
            with self._lock:
                self.demotion_failure_count += 1
            _remove_quietly(snapshot_path)
            _remove_quietly(meta_path)
            return False
        with self._lock:
            self._index[session_id] = meta
            self.demotion_count += 1
            self._evict_over_budget_locked(keep_session_id=session_id)
        return True

    def match(
        self,
        token_ids: list[int],
        model_id: str,
        model_revision: str,
        block_size: int,
        acceleration_mode: str = "",
        kv_quant_profile: str = "",
    ) -> tuple[ColdEntryMeta | None, int]:
        """Best block-aligned LCP candidate (metadata only — no deserialization)."""
        request_active_kv = _is_active_kv_quant_mode(acceleration_mode)
        request_kv_quant_profile = _normalize_kv_quant_profile(kv_quant_profile)
        if request_active_kv and not request_kv_quant_profile:
            return None, 0
        bs = max(1, block_size)
        new_blocks = _split_blocks(token_ids, bs)
        if not new_blocks:
            return None, 0
        with self._lock:
            self._ensure_loaded_locked()
            candidates = list(self._index.values())
        best: ColdEntryMeta | None = None
        best_len = 0
        for meta in candidates:
            if meta.model_id != model_id or meta.model_revision != model_revision:
                continue
            if meta.cache_mode in _ROTATING_CACHE_MODES:
                continue
            meta_active_kv = _is_active_kv_quant_mode(meta.acceleration_mode)
            if meta_active_kv != request_active_kv:
                continue
            if meta_active_kv and meta.kv_quant_profile != request_kv_quant_profile:
                continue
            stored_blocks = _split_blocks(meta.token_ids, bs)
            match_len = _count_matching_blocks(new_blocks, stored_blocks) * bs
            if match_len > best_len:
                best_len = match_len
                best = meta
        if best is None or best_len < bs:
            return None, 0
        return best, best_len

    def has_kv_quant_profile_mismatch(
        self,
        token_ids: list[int],
        model_id: str,
        model_revision: str,
        block_size: int,
        acceleration_mode: str = "",
        kv_quant_profile: str = "",
    ) -> bool:
        """Return True when an otherwise reusable active-KV prefix has a different profile."""
        request_active_kv = _is_active_kv_quant_mode(acceleration_mode)
        request_kv_quant_profile = _normalize_kv_quant_profile(kv_quant_profile)
        if not request_active_kv or not request_kv_quant_profile:
            return False
        bs = max(1, block_size)
        new_blocks = _split_blocks(token_ids, bs)
        if not new_blocks:
            return False
        with self._lock:
            self._ensure_loaded_locked()
            candidates = list(self._index.values())
        for meta in candidates:
            if meta.model_id != model_id or meta.model_revision != model_revision:
                continue
            if meta.cache_mode in _ROTATING_CACHE_MODES:
                continue
            if not _is_active_kv_quant_mode(meta.acceleration_mode):
                continue
            if meta.kv_quant_profile == request_kv_quant_profile:
                continue
            stored_blocks = _split_blocks(meta.token_ids, bs)
            if _count_matching_blocks(new_blocks, stored_blocks) * bs >= bs:
                return True
        return False

    def restore(self, meta: ColdEntryMeta) -> Any:
        """Deserialize one entry. A failed restore drops the entry and returns None."""
        try:
            snapshot = self._deserializer(meta.snapshot_path)
        except Exception:
            snapshot = None
        if not isinstance(snapshot, list) or not snapshot:
            with self._lock:
                self.restore_failure_count += 1
            self.remove(meta.session_id)
            return None
        with self._lock:
            self.hit_count += 1
        return snapshot

    def remove(self, session_id: str) -> None:
        with self._lock:
            meta = self._index.pop(session_id, None)
        if meta is not None:
            _remove_quietly(meta.snapshot_path)
            _remove_quietly(meta.meta_path)

    def entry_count(self) -> int:
        with self._lock:
            self._ensure_loaded_locked()
            return len(self._index)

    def total_bytes(self) -> int:
        with self._lock:
            self._ensure_loaded_locked()
            return sum(meta.total_bytes for meta in self._index.values())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_loaded_locked(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._root.is_dir():
            return
        meta_paths: list[tuple[str, str]] = []
        snapshot_file_names: set[str] = set()
        try:
            with os.scandir(self._root) as entries:
                for entry in entries:
                    entry_name = entry.name
                    try:
                        if entry_name.endswith(".meta.json") and entry.is_file(
                            follow_symlinks=False
                        ):
                            meta_paths.append((entry.path, entry_name))
                        elif entry_name.endswith(".kv.safetensors") and entry.is_file(
                            follow_symlinks=False
                        ):
                            snapshot_file_names.add(entry_name)
                    except OSError:
                        continue
        except OSError:
            return
        precheck_orphan_names = len(snapshot_file_names) < len(meta_paths)
        meta_suffix_length = len(".meta.json")
        root = self._root
        index = self._index
        session_digest = _session_digest
        normalize_kv_quant_profile = _normalize_kv_quant_profile
        entry_meta_cls = ColdEntryMeta
        remove_path_string_quietly = _remove_path_string_quietly
        open_file = _OPEN
        json_loads = json.loads
        for meta_path_string, meta_file_name in meta_paths:
            if precheck_orphan_names:
                snapshot_name_from_sidecar = f"{meta_file_name[:-meta_suffix_length]}.kv.safetensors"
                if snapshot_name_from_sidecar not in snapshot_file_names:
                    # Orphaned sidecar (crash between snapshot write and meta
                    # write, or manual snapshot deletion) — drop it before parsing
                    # JSON so orphan-heavy cold dirs do not pay per-sidecar decode
                    # cost on every restart.
                    remove_path_string_quietly(meta_path_string)
                    continue
            try:
                with open_file(meta_path_string, "rb") as meta_file:
                    payload = json_loads(meta_file.read())
                payload_get = payload.get
                session_id = str(payload["session_id"])
                snapshot_name = f"{session_digest(session_id)}.kv.safetensors"
                if snapshot_name not in snapshot_file_names:
                    # Orphaned sidecar (crash between snapshot write and meta
                    # write, or manual snapshot deletion) — drop it so restarts
                    # stop rescanning it.
                    remove_path_string_quietly(meta_path_string)
                    continue
                raw_token_ids = payload["token_ids"]
                if raw_token_ids and type(raw_token_ids[0]) is int:
                    token_ids = list(raw_token_ids)
                else:
                    token_ids = [int(t) for t in raw_token_ids]
                meta_path = Path(meta_path_string)
                index[session_id] = entry_meta_cls(
                    session_id=session_id,
                    token_ids=token_ids,
                    cache_mode=str(payload_get("cache_mode", "")),
                    model_id=str(payload_get("model_id", "")),
                    model_revision=str(payload_get("model_revision", "")),
                    block_size=max(1, int(payload_get("block_size", 1))),
                    total_bytes=int(payload_get("total_bytes", 0)),
                    acceleration_mode=str(payload_get("acceleration_mode", "")),
                    kv_quant_profile=normalize_kv_quant_profile(
                        str(payload_get("kv_quant_profile", ""))
                    ),
                    stored_at=float(payload_get("stored_at", 0.0)),
                    snapshot_path=root / snapshot_name,
                    meta_path=meta_path,
                )
            except Exception:
                remove_path_string_quietly(meta_path_string)

    def _evict_over_budget_locked(self, keep_session_id: str) -> None:
        if self._max_bytes <= 0:
            return
        total = sum(meta.total_bytes for meta in self._index.values())
        if total <= self._max_bytes:
            return
        removable = sorted(
            (meta for meta in self._index.values() if meta.session_id != keep_session_id),
            key=lambda meta: meta.stored_at,
        )
        for meta in removable:
            if total <= self._max_bytes:
                break
            self._index.pop(meta.session_id, None)
            total -= meta.total_bytes
            self.eviction_count += 1
            _remove_quietly(meta.snapshot_path)
            _remove_quietly(meta.meta_path)


def _tensor_nbytes(tensor: Any, get_attr: Any = getattr) -> Any:
    nbytes = get_attr(tensor, "nbytes", None)
    if nbytes is not None:
        return nbytes
    size = get_attr(tensor, "size", None)
    if size is None:
        return 0
    itemsize = get_attr(tensor, "itemsize", None)
    if itemsize is None:
        return 0
    return size * itemsize


def _tensor_pair_nbytes(first_tensor: Any, second_tensor: Any, get_attr: Any = getattr) -> Any:
    first_nbytes = get_attr(first_tensor, "nbytes", None)
    if first_nbytes is None:
        first_size = get_attr(first_tensor, "size", None)
        if first_size is None:
            first_nbytes = 0
        else:
            first_itemsize = get_attr(first_tensor, "itemsize", None)
            first_nbytes = 0 if first_itemsize is None else first_size * first_itemsize
    second_nbytes = get_attr(second_tensor, "nbytes", None)
    if second_nbytes is None:
        second_size = get_attr(second_tensor, "size", None)
        if second_size is None:
            second_nbytes = 0
        else:
            second_itemsize = get_attr(second_tensor, "itemsize", None)
            second_nbytes = (
                0 if second_itemsize is None else second_size * second_itemsize
            )
    return first_nbytes + second_nbytes


def estimate_cache_snapshot_bytes(cache_snapshot: Any) -> int:
    """Estimate the live in-memory bytes of a prompt-cache layer list.

    Supports both .state (older mlx-lm) and .keys/.values (newer KVCache)
    layer shapes; tensors report via .nbytes or size*itemsize.
    """
    if not isinstance(cache_snapshot, list):
        return 0
    total = 0
    tensor_nbytes = _tensor_nbytes
    tensor_pair_nbytes = _tensor_pair_nbytes
    get_attr = getattr
    type_of = type
    for layer_cache in cache_snapshot:
        state = get_attr(layer_cache, "state", None)
        state_type = type_of(state)
        if state_type is list or state_type is tuple:
            try:
                first_state, second_state = state  # type: ignore[misc]
            except ValueError:
                for tensor in state:  # type: ignore[misc]
                    total += tensor_nbytes(tensor, get_attr)
            else:
                total += tensor_pair_nbytes(first_state, second_state, get_attr)
        elif state is None:
            keys = get_attr(layer_cache, "keys", None)
            values = get_attr(layer_cache, "values", None)
            if keys is not None and values is not None:
                total += tensor_pair_nbytes(keys, values, get_attr)
            elif keys is not None:
                total += tensor_nbytes(keys, get_attr)
            elif values is not None:
                total += tensor_nbytes(values, get_attr)
        else:
            total += tensor_nbytes(state, get_attr)
    return total if type(total) is int else int(total)


def _session_digest(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]


def _remove_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _remove_path_string_quietly(path: str) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError:
        pass


class PrefixBlockStore:
    """Worker-local session block table store with two-level ownership and memory-bounded LRU.

    Lifecycle:
      put()     — stores entry with pinned ref=1, active refs=0
      acquire() — increments active refs, returns entry (or None if evicted/absent)
      release() — decrements active refs; if both pinned and active drop to 0, schedules cleanup
      evict_lru() — unpins LRU entry; cleanup deferred until all active refs also drop

    When a cold store is attached, budget evictions demote the snapshot to disk
    (via the deferred-clear queue, so serialization runs after active requests
    finish) and find_lcp falls back to the cold tier on a hot miss.
    """

    def __init__(
        self,
        max_memory_bytes: int = _DEFAULT_MAX_MEMORY_BYTES,
        min_session_count: int = _MIN_SESSION_FLOOR,
        on_cleanup: Any = None,
        cold_store: ColdPrefixStore | None = None,
        bytes_estimator: Any = None,
    ) -> None:
        self._max_memory_bytes = max_memory_bytes
        self._min_session_count = min_session_count
        self._on_cleanup = on_cleanup  # callable(entry) invoked on final cleanup
        self._cold_store = cold_store
        self._bytes_estimator = bytes_estimator or estimate_cache_snapshot_bytes
        self._lock = threading.Lock()
        self._sessions: OrderedDict[str, _BlockEntry] = OrderedDict()
        self._total_bytes = 0
        self._deferred_clear_queue: list[Any] = []  # list of zero-arg callables
        self.hot_hit_count = 0
        self.cold_hit_count = 0
        self.miss_count = 0
        self.promotion_count = 0

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
        kv_quant_profile: str = "",
    ) -> _BlockEntry | None:
        """Store a prefill result. Replaces any existing entry for session_id."""
        if not session_id:
            return None
        normalized_profile = _normalize_kv_quant_profile(kv_quant_profile)
        if _is_active_kv_quant_mode(acceleration_mode) and not normalized_profile:
            return None
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
            kv_quant_profile=normalized_profile,
        )
        with self._lock:
            return self._store_entry_locked(entry, acquire=False)

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
        kv_quant_profile: str = "",
        force_fallback: bool = False,
    ) -> LCPResult:
        """Find the longest common block-aligned prefix among stored sessions.

        Returns an LCPResult. If mode != "none", the matched entry has its active
        refcount incremented — the caller MUST call release() when done.
        """
        if force_fallback:
            self.miss_count += 1
            return LCPResult(
                mode="none",
                recovered_prefix_tokens=0,
                fallback_reason="force_cache_fallback",
                entry=None,
                suffix_token_ids=list(token_ids),
            )

        request_active_kv = _is_active_kv_quant_mode(acceleration_mode)
        request_kv_quant_profile = _normalize_kv_quant_profile(kv_quant_profile)
        if request_active_kv and not request_kv_quant_profile:
            self.miss_count += 1
            return LCPResult(
                mode="none",
                recovered_prefix_tokens=0,
                fallback_reason="kv_quant_profile_missing",
                entry=None,
                suffix_token_ids=list(token_ids),
            )

        bs = max(1, block_size)
        new_blocks = _split_blocks(token_ids, bs)
        if not new_blocks:
            self.miss_count += 1
            return LCPResult(
                mode="none",
                recovered_prefix_tokens=0,
                fallback_reason="empty_prompt",
                entry=None,
                suffix_token_ids=list(token_ids),
            )

        best_entry: _BlockEntry | None = None
        best_len = 0
        kv_quant_profile_mismatch = False

        with self._lock:
            candidates = list(self._sessions.values())

        for entry in candidates:
            if entry.model_id != model_id or entry.model_revision != model_revision:
                continue
            if entry.cache_mode in _ROTATING_CACHE_MODES:
                continue
            entry_active_kv = _is_active_kv_quant_mode(entry.acceleration_mode)
            if entry_active_kv != request_active_kv:
                continue

            stored_blocks = _split_blocks(entry.token_ids, bs)
            match_len = _count_matching_blocks(new_blocks, stored_blocks) * bs
            if entry_active_kv and entry.kv_quant_profile != request_kv_quant_profile:
                if match_len >= bs:
                    kv_quant_profile_mismatch = True
                continue
            if match_len > best_len:
                best_len = match_len
                best_entry = entry

        # A strictly longer cold-tier prefix beats a shorter (or absent) hot hit;
        # ties prefer the hot tier so a disk restore never displaces equal work
        # already resident in memory.
        if self._cold_store is not None:
            cold_meta, cold_len = self._cold_store.match(
                token_ids,
                model_id,
                model_revision,
                bs,
                acceleration_mode=acceleration_mode,
                kv_quant_profile=request_kv_quant_profile,
            )
            if cold_meta is not None and cold_len > best_len:
                promoted = self._promote_cold_entry(cold_meta, token_ids, cold_len)
                if promoted is not None:
                    return promoted
            if not kv_quant_profile_mismatch:
                kv_quant_profile_mismatch = self._cold_store.has_kv_quant_profile_mismatch(
                    token_ids,
                    model_id,
                    model_revision,
                    bs,
                    acceleration_mode=acceleration_mode,
                    kv_quant_profile=request_kv_quant_profile,
                )

        if best_entry is None or best_len < bs:
            self.miss_count += 1
            return LCPResult(
                mode="none",
                recovered_prefix_tokens=0,
                fallback_reason=(
                    "kv_quant_profile_mismatch"
                    if kv_quant_profile_mismatch
                    else "no_reusable_prefix"
                ),
                entry=None,
                suffix_token_ids=list(token_ids),
            )

        with self._lock:
            live = self._sessions.get(best_entry.session_id)
            if live is None or live is not best_entry:
                self.miss_count += 1
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

        self.hot_hit_count += 1
        return LCPResult(
            mode=mode,
            recovered_prefix_tokens=best_len,
            fallback_reason="",
            entry=live,
            suffix_token_ids=suffix,
            tier="hot",
        )

    def _promote_cold_entry(
        self,
        meta: ColdEntryMeta,
        token_ids: list[int],
        cold_len: int,
    ) -> LCPResult | None:
        """Restore a cold entry into the hot tier and return an acquired result.

        Returns None when the restore fails or the promoted entry is evicted
        before it can be acquired; the caller falls back to its hot result.
        """
        assert self._cold_store is not None
        snapshot = self._cold_store.restore(meta)
        if snapshot is None:
            return None
        # The hot tier budgets live memory: account the promoted entry by its
        # restored in-memory footprint, not the serialized file size recorded
        # in the cold sidecar (safetensors on disk is usually smaller than the
        # resident MLX arrays, which would under-count and under-evict).
        try:
            live_bytes = int(self._bytes_estimator(snapshot))
        except Exception:
            live_bytes = 0
        if live_bytes <= 0:
            live_bytes = meta.total_bytes
        entry = _BlockEntry(
            session_id=meta.session_id,
            token_ids=list(meta.token_ids),
            cache_snapshot=snapshot,
            cache_mode=meta.cache_mode,
            model_id=meta.model_id,
            model_revision=meta.model_revision,
            block_size=meta.block_size,
            total_bytes=live_bytes,
            acceleration_mode=meta.acceleration_mode,
            kv_quant_profile=meta.kv_quant_profile,
        )
        with self._lock:
            entry = self._store_entry_locked(entry, acquire=True)
        if entry is None:
            return None
        self._cold_store.remove(meta.session_id)
        self.cold_hit_count += 1
        self.promotion_count += 1
        is_exact = cold_len >= len(token_ids)
        return LCPResult(
            mode="exact" if is_exact else "partial",
            recovered_prefix_tokens=cold_len,
            fallback_reason="",
            entry=entry,
            suffix_token_ids=list(token_ids[cold_len:]),
            tier="cold",
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

    def stats(self) -> dict[str, int]:
        """Advisory tiered-cache counters for receipts and diagnostics."""
        cold = self._cold_store
        return {
            "hot_hit_count": self.hot_hit_count,
            "cold_hit_count": self.cold_hit_count,
            "miss_count": self.miss_count,
            "promotion_count": self.promotion_count,
            "cold_demotion_count": cold.demotion_count if cold else 0,
            "cold_demotion_failure_count": cold.demotion_failure_count if cold else 0,
            "cold_restore_failure_count": cold.restore_failure_count if cold else 0,
            "cold_eviction_count": cold.eviction_count if cold else 0,
            "cold_entry_count": cold.entry_count() if cold else 0,
            "cold_total_bytes": cold.total_bytes() if cold else 0,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _store_entry_locked(self, entry: _BlockEntry, *, acquire: bool) -> _BlockEntry | None:
        """Insert entry under the store lock and optionally acquire that exact entry."""
        self._evict_session(entry.session_id)
        self._sessions[entry.session_id] = entry
        self._total_bytes += entry.total_bytes
        self._evict_if_needed()
        live = self._sessions.get(entry.session_id)
        if live is not entry:
            return None
        if acquire:
            live.acquire()
        return live

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
            self._enqueue_demotion_locked(entry)
            fully_released = entry.unpin()
            if fully_released:
                self._deferred_clear_queue.append(lambda e=entry: self._cleanup_entry(e))

    def _enqueue_demotion_locked(self, entry: _BlockEntry) -> None:
        """Queue a cold-tier demotion for a budget-evicted entry (under lock).

        The closure captures only cheap metadata while the store lock is held.
        The expensive prompt-cache clone runs later in `flush_deferred_clear()`,
        outside the global store lock and before the queued cleanup callback can
        null `entry.cache_snapshot`.
        Same-session replacement via put() intentionally does not demote — the
        fresh hot entry supersedes the old snapshot, and demoting every turn
        would serialize on each conversation update.
        """
        if self._cold_store is None:
            return
        snapshot_ref = entry.cache_snapshot
        if snapshot_ref is None or not isinstance(snapshot_ref, list):
            return
        cold = self._cold_store
        session_id = entry.session_id
        token_ids = list(entry.token_ids)
        cache_mode = entry.cache_mode
        model_id = entry.model_id
        model_revision = entry.model_revision
        block_size = entry.block_size
        acceleration_mode = entry.acceleration_mode
        kv_quant_profile = entry.kv_quant_profile

        def demote() -> None:
            snapshot = clone_cache_snapshot(snapshot_ref)
            if snapshot is None:
                return
            cold.store(
                session_id=session_id,
                token_ids=token_ids,
                cache_snapshot=snapshot,
                cache_mode=cache_mode,
                model_id=model_id,
                model_revision=model_revision,
                block_size=block_size,
                acceleration_mode=acceleration_mode,
                kv_quant_profile=kv_quant_profile,
            )

        self._deferred_clear_queue.append(demote)

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


def _cold_store_from_env() -> ColdPrefixStore | None:
    """Build the opt-in cold tier from environment configuration.

    The cold tier activates only when MELIX_PREFIX_CACHE_COLD_DIR names a
    directory; MELIX_PREFIX_CACHE_COLD_MAX_BYTES overrides the 8 GiB default.
    """
    root = str(os.environ.get(_COLD_DIR_ENV, "") or "").strip()
    if not root:
        return None
    raw_budget = str(os.environ.get(_COLD_MAX_BYTES_ENV, "") or "").strip()
    max_bytes = _DEFAULT_COLD_MAX_BYTES
    if raw_budget:
        try:
            max_bytes = max(0, int(raw_budget))
        except ValueError:
            max_bytes = _DEFAULT_COLD_MAX_BYTES
    return ColdPrefixStore(Path(root).expanduser(), max_bytes=max_bytes)


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
                    cold_store=_cold_store_from_env(),
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


def _clone_cache_value(value: Any) -> Any:
    """Clone mutable tensor/container values held by a prompt-cache layer."""
    if value is None or isinstance(value, str | bytes | int | float | bool):
        return value
    if isinstance(value, list):
        return [_clone_cache_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_clone_cache_value(item) for item in value)
    if isinstance(value, dict):
        return {copy.deepcopy(key): _clone_cache_value(item) for key, item in value.items()}
    if isinstance(value, set):
        return {_clone_cache_value(item) for item in value}
    if isinstance(value, bytearray):
        return bytearray(value)

    copy_method = getattr(value, "copy", None)
    if callable(copy_method):
        try:
            copied = copy_method()
            if copied is not value:
                return copied
        except Exception:
            pass

    try:
        import mlx.core as mx

        return mx.array(value)
    except Exception:
        pass

    try:
        return copy.deepcopy(value)
    except Exception:
        return value


def _clone_cache_layer(layer: Any) -> Any:
    if isinstance(layer, list | tuple | dict | set | bytearray):
        return _clone_cache_value(layer)
    cloned = copy.copy(layer)
    for attr in ("state", "keys", "values"):
        try:
            value = getattr(layer, attr)
        except Exception:
            continue
        if value is None:
            continue
        try:
            setattr(cloned, attr, _clone_cache_value(value))
        except Exception:
            continue
    return cloned


def clone_cache_snapshot(cache_snapshot: Any) -> Any:
    """Clone a prompt_cache list so decode and demotion mutate independent buffers."""
    if cache_snapshot is None:
        return None
    if not isinstance(cache_snapshot, list):
        return None
    try:
        return [_clone_cache_layer(layer) for layer in cache_snapshot]
    except Exception:
        return None
