# Text Prefix KV Cache Tiering

_Last updated: 2026-08-03_

This runbook describes session-scoped prefix KV reuse for both text workers.
The Python worker has hot and opt-in cold payload tiers. The Swift worker has a
real in-memory block tier for a narrower cache layout and metadata-only disk
records.

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
state keyed by session, LCP hits are block-aligned, rotating-cache sessions
are excluded, active-KV-quantized sessions are keyed by an exact active KV
quantization profile, and a failed trim falls back to a full prefill rather
than reusing misaligned state.

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
  `kv_quant_profile_missing`, `kv_quant_profile_mismatch`,
  `cache_reuse_unavailable`, …)

`PrefixBlockStore.stats()` exposes advisory counters: hot/cold hits, misses,
promotions, demotions, demotion failures, cold restore failures, cold entry
count and bytes.

## Swift text worker L1

The Swift MLX worker admits paged reuse only when all model layers expose an
append-only, unquantized `KVCacheSimple` layout and cache mode is `tiered`.
Production-rendered token IDs are divided into fixed blocks. Each block owns
the evaluated key/value tensors for every layer and reports actual tensor
bytes. A warm prefill atomically pins the longest compatible block prefix,
runs the model only for missing full blocks, and leaves the final prompt tail
for the normal generation iterator.

The backend derives compatibility from the prepared production input, including
tensor rank, dtype, non-token dimensions, mask and multimodal presence, and the
block-aligned maximum forward chunk derived from the effective prefill window.
A request extension cannot provide that identity. Reuse writes validate the
current generation, pool membership, digest boundary, layout, and pinned lease
together under the pool lock. Cold prefill advances by that multi-block chunk,
not one model call per block. A lookup result materializes its pinned lease into
one cache set only once; a repeated materialization returns no caches and cannot
create a second aliasing private owner.

Shared blocks are immutable. A divergent suffix remains request-private, and
trimming through a shared block creates a private partial copy. Each request's
private layers share one allocation owner; append, prompt-tail, multi-token
decode, trim, copy-on-write, and release update its exact tensor bytes. Those
bytes are included in physical resident, logical ownership, L1, runtime
`kv_cache_bytes`, peak, and admission-budget statistics.

The byte budget is the minimum applicable request/model/process budget. Store
admission includes other active private owners and excludes double-counting the
submitting owner only while those same tensors transfer into shared blocks.
LRU eviction skips active decode leases; if the candidate still cannot fit,
the prior pool contents remain unchanged.

When memory admission or atomic snapshot validation fails after model prefill,
the worker evaluates the already-computed paged state once into ordinary
`KVCacheSimple` caches. It does not invoke model prefill again. The old paged
owner and block lease are released before the returned decode context can run,
and the response carries `admitted=false` plus the typed fallback reason.

Swift prefill responses expose `cache_hit_mode`, `recovered_prefix_tokens`, and
`fallback_reason`. Runtime metrics additionally expose lookup and restore
microseconds, computed prefix tokens, model prefill microseconds, block-table
bytes, stream-owner match, copy-on-write block count, configured model-prefill
chunk tokens, model-prefill call count, and actual min/max call token counts.
`GetCacheStats` and runtime statistics source L1 bytes, block count, hit rate,
and dedup ratio from the real tensor pool.

Compatible paged decode sessions remain eligible for homogeneous batching. The
batch adapter keeps each row's original cache and lease, applies incoming K/V
updates to each row, and concatenates the resulting K/V only for the attention
call. Batch split returns the same row caches. A paged cohort with mismatched
offsets, block layout, tensor shape, dtype, or metadata fails closed with the
normal typed `not_batchable` reason.

Common Swift fallback reasons include:

- `cache_mode_unsupported`
- `prompt_below_block_boundary`
- `active_kv_layout_unsupported`
- `prefill_shape_unsupported`
- `cache_layout_unsupported`
- `composite_runtime_state_unsupported`
- `cache_block_shape_mismatch`
- `cache_snapshot_validation_failed`
- `cache_memory_budget_exceeded`

The Swift `DiskCacheStore` persists identity and block-table metadata only. It
does not serialize KV payloads, so an L2 metadata match is reported as
`metadata-only-l2` with zero recovered tokens. The Swift handshake must keep
`supportsDiskCache=false` and `supportsBoundarySnapshots=false` until payload
restore is implemented and verified.

### Swift operator checks

For an exact warm request, verify that recovered prefix tokens are positive,
computed prefix tokens are zero for all restored full blocks, block IDs match
the cold request, and every block reports non-zero bytes. Verify that runtime
`kv_cache_bytes` equals L1 resident bytes and that logical bytes exceed physical
bytes while blocks are shared.

For a compatibility fallback before paged execution, verify that
`cache_hit_mode=none`, recovered prefix tokens are zero, and the typed fallback
reason matches the refused class. For post-prefill store rejection, additionally
verify one model-prefill pass, ordinary `KVCacheSimple` decode state, output
parity, and zero paged private owners or block leases after context release. A
snapshot race may retain audit evidence for a prefix that was actually used,
but it must not return an admitted paged decode context. An L2 metadata record
by itself is never proof of saved model work.

Run the same-load paired physical-watermark probe from the repository root:

```bash
MELIX_PAGED_KV_PAIRED_MEMORY_PROBE_OUTPUT=.runtime/metrics/issue-2601-paired-memory.json \
  xcrun swift test --package-path services/mlx-text-worker-swift \
  --filter WorkerScaffoldTests/testAutoSwiftMLXBackendPairedContiguousAndPagedMemoryWatermarks
```

The probe warms both cache paths, then compares contiguous and paged execution
with the same loaded model, prompt, four sessions, and output-token count. Each
mode starts from a quiesced MLX allocator baseline. A concurrent sampler polls
MLX active and reported peak bytes plus process RSS across the complete prefill
and real homogeneous decode interval, including concatenated attention K/V
temporaries. The JSON must report comparable MLX baselines, more than one sample
per mode, model-eval batch size four, identical output-token counts, non-zero
throughput, and logical session bytes greater than resident block bytes. Paged
MLX active and allocator-reported peak deltas must both be strictly lower than
contiguous; otherwise the test fails and the paged path is not ready.

The checked-in 2026-08-03 result is
`docs/metrics/issue-2601-paired-contiguous-paged-memory.json`. It reports a
`2059968`-byte MLX active peak-delta reduction and a `2686976`-byte RSS
peak-delta reduction for paged execution. Its `40960` resident bytes include
active private tails and remain below the `172032` logical session bytes. The
artifact also retains both throughput values so attention-gather cost is
visible rather than hidden by the memory result.

## Boundaries

- KV-quantized (`ACCELERATION_MODE_ACTIVE_KV_QUANTIZED`) sessions are eligible
  in both tiers only when the request and stored snapshot carry the same
  active KV quantization profile. Missing profiles fall back with
  `kv_quant_profile_missing`; profile mismatches fall back with
  `kv_quant_profile_mismatch`.
- The Swift worker supports only the append-only dense L1 contract above; its
  L2 records remain metadata-only.
- Cold entries are keyed by exact model id + revision; a model update
  invalidates them naturally via LCP mismatch.
