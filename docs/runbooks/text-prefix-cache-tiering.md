# Text Prefix KV Cache Tiering

_Last updated: 2026-07-06_

This runbook describes session-scoped prefix KV reuse for the Python text
worker, including the hot (in-memory) tier and the opt-in cold (disk) tier.

## What it does

Every text request that carries a `_melix.session_id` stores its prompt-only
KV state in the worker-local `PrefixBlockStore` after prefill. The next
request in the same session (or any session with a block-aligned common
prefix on the same model + revision) recovers that state and replays only the
new token suffix instead of re-prefilling the whole conversation.

Two decode paths share the store:

- the native-MTP batch path (Qwen3.5 family), which introduced the store
- the standard `stream_generate` path, which now passes an explicit
  `prompt_cache` and reuses/stores prefix state the same way

The reuse contract is identical for both paths: entries hold prompt-only
state keyed by session, LCP hits are block-aligned, rotating-cache and
active-KV-quantized sessions are excluded, and a failed trim falls back to a
full prefill rather than reusing misaligned state.

## Hot tier

- In-memory, process-wide singleton (`worker/runtime/prefix_block_store.py`)
- Default budget 4 GiB with a 2-session floor, LRU eviction
- Two-level ownership (LRU pin + active request refs) so an entry evicted
  mid-decode is cleaned up only after its last borrower releases it

## Cold tier (opt-in)

When `MELIX_PREFIX_CACHE_COLD_DIR` names a directory, hot-tier budget
evictions demote the snapshot to disk instead of dropping it:

- serialization uses mlx-lm's prompt-cache safetensors format plus a JSON
  sidecar (token ids, model id/revision, cache mode, acceleration mode)
- demotions run through the deferred-clear queue, so they execute after
  active requests finish — never during a decode
- a hot-tier miss consults the cold index; a strictly longer block-aligned
  cold match is restored, promoted back into the hot tier, and served as a
  warm hit; ties prefer the hot tier
- the directory is budgeted (default 8 GiB, override with
  `MELIX_PREFIX_CACHE_COLD_MAX_BYTES`), oldest-first eviction; corrupt or
  unreadable entries are dropped and counted, never served
- same-session replacement (the normal every-turn store update) does not
  demote — only budget evictions do

| Environment variable | Meaning | Default |
|---|---|---|
| `MELIX_PREFIX_CACHE_COLD_DIR` | Cold-tier directory; empty disables the tier | disabled |
| `MELIX_PREFIX_CACHE_COLD_MAX_BYTES` | Cold-tier disk budget in bytes | `8589934592` (8 GiB) |

## Receipts and observability

Terminal token events carry:

- `cache_hit_mode` — `exact`, `partial`, or `none`
- `cache_hit_tier` — `hot` or `cold` on a hit
- `recovered_prefix_tokens` — prompt tokens served from reused state
- `cache_fallback_reason` — why reuse did not happen (`no_reusable_prefix`,
  `active_kv_excluded`, `cache_reuse_unavailable`, …)

`PrefixBlockStore.stats()` exposes advisory counters: hot/cold hits, misses,
promotions, demotions, demotion failures, cold restore failures, cold entry
count and bytes.

## Boundaries

- KV-quantized (`ACCELERATION_MODE_ACTIVE_KV_QUANTIZED`) sessions are still
  excluded from both tiers (#2607 tracks lifting this).
- The Swift text worker's L1/L2 cache stores remain metadata-level (#2601).
- Cold entries are keyed by exact model id + revision; a model update
  invalidates them naturally via LCP mismatch.
