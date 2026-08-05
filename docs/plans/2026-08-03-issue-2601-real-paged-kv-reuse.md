# Issue 2601 Real Paged KV Reuse Completion Plan

## Goal

Replace the Swift text worker's metadata-only paged-cache bookkeeping with a
real, block-owned L1 KV execution path for compatible append-only text caches.
Capability flags, block bytes, reuse receipts, runtime memory statistics, and
warm-prefill claims must all derive from the same executed tensor state.

## Governing Contracts

- GitHub issue `#2601`, including all comments through 2026-07-31
- `docs/architecture-spec.md`, especially the L1 shared paged-cache contract
- `docs/decisions/2026-03-27-swift-text-runtime.md`
- `docs/decisions/2026-03-28-product-scope-and-runtime-priorities.md`
- `docs/adr/0001-homogeneous-batch-decode-cache-compatibility.md`
- `docs/plans/2026-03-30-m2-2-text-worker-paged-cache-ownership.md`
- `docs/plans/2026-07-09-issue-2601-paged-cache-truthful-capabilities.md`

PR `#2691` correctly disabled the capability while the tables were metadata
only. It did not complete the parent issue.

## Supported End State

The first executed paged-cache contract is deliberately narrow and complete:

- Swift MLX text models whose every cache layer is an append-only
  `KVCacheSimple`-compatible layer are admitted.
- Prompt state is materialized in fixed token blocks. Each logical block owns
  the real per-layer key and value arrays, and reports the sum of their actual
  allocated tensor bytes.
- Prefix snapshots share immutable block objects across sessions. A divergent
  suffix appends private blocks; trimming or mutation never modifies a shared
  block in place.
- Attention consumes a `KVCache` implementation backed by the block table. It
  gathers the shared blocks and the request-private tail for the model call,
  rather than rebuilding the prefix with a full prefill.
- Paged prefill advances by a block-aligned multi-block chunk derived from the
  effective prefill window. The configured chunk and actual model-call count
  are part of compatibility and execution evidence, so a larger prefill window
  cannot be reported while the runtime still forwards one block at a time.
- Homogeneous decode cohorts retain each row's original paged cache and lease.
  A batch cache adapter splits incoming K/V by row, updates those row caches,
  concatenates the resulting attention state for the batch model call, and
  returns the same row caches when the cohort is materialized or shrinks.
- Reuse is block-aligned and keyed by the exact production-rendered token
  blocks plus model residency epoch, cache scope, layout, acceleration mode,
  backend-derived prefill shape, and block size. Request metadata cannot supply
  or override the prefill-shape identity.
- Reuse extension stores accept only the still-current atomic lookup-and-pin
  result and validate its signature, block size, layer count, digest boundary,
  generation, lease, and pool membership while holding the pool lock.
- A lookup result transfers its lease into one cache set exactly once. Repeated
  materialization returns no caches, so divergent cache aliases cannot share one
  private-allocation owner and under-report live tensor bytes.
- Successful stores pin the committed generation under the same lock and use a
  one-shot lease transfer to construct decode caches; snapshots alone cannot
  bypass pool membership or budget accounting.
- The L1 pool is bounded by the effective request/model cache byte budget.
  Admission that cannot remain within the bound fails closed to ordinary
  contiguous prefill.
- Cache identity includes the full scope identifier and the exact creating MLX
  stream. A decode that resumes under another stream materializes the computed
  state once into contiguous caches and records the typed fallback; batch
  admission rejects the cross-stream paged row before model evaluation.
- Variable identity fields use UTF-8 byte-length-prefixed encoding, so embedded
  delimiters cannot make two distinct full cache scopes share a signature.
- Prefill cache statistics report the same tightest request/model/process byte
  budget used for admission, rather than a process-headroom approximation.
- Private-owner publication and private-to-shared transfer use one owner-to-pool
  lock order, so no live tensor bytes can appear between accounting removal and
  committed shared ownership. LRU eviction never selects an entry whose blocks
  still have an active decode lease, and a shared block is released after every
  layer view has trimmed or replaced it.
- The registry resolves the effective `CacheScope`, `CacheKey`, and logical
  prefix ID before entering the model runtime. Each committed L1 entry owns that
  logical identity together with its tensor snapshot. The pool lock is the
  authoritative transaction boundary for operator pin state, LRU selection,
  logical purge, and the L1 prefix/block projection. Metadata and disk records
  may mirror this state, but they cannot override or independently represent a
  live L1 entry.
- Logical purge removes an entry from lookup and L1 projection atomically.
  Active decode leases may retain its physical blocks until release, but the
  purged generation cannot hit again. Operator-pinned entries are ineligible for
  LRU eviction until the same logical prefix is unpinned.
- Physical entry identity includes the complete resolved logical scope and
  cache key in addition to execution compatibility and token-block digests.
  Distinct logical prefixes that tokenize identically may share immutable
  tensor blocks through lookup, but cannot overwrite each other's operator
  pin, purge, or projection identity.
- Paged admission accepts only the production `MLXLLM.LLMModel` text-model
  contract with an all-`KVCacheSimple` layout. Composite or otherwise
  state-carrying generic language models fail closed before lookup, paged cache
  allocation, or a paged model call. Their fallback evidence describes one
  ordinary contiguous prepare and no discarded paged work.

## Fail-Closed Boundaries

The worker must not claim executed paged reuse for:

- rotating or moving-window caches;
- recurrent, hybrid, composite, or otherwise non-`KVCacheSimple` state;
- active-KV-quantized cache state until its packed layout has a block-native
  attention implementation;
- a different loaded model/container epoch, cache compatibility signature,
  prefill boundary, block size, or engine owner;
- metadata-only disk records or boundary snapshots.

Those paths keep their existing correct execution behavior and return a typed
fallback reason. `supportsDiskCache` and `supportsBoundarySnapshots` remain
false. No L2 metadata restore may be credited as saved prefill work.

## Work Plan

1. Add a worker-owned paged KV module with immutable logical block payloads,
   append-only layer cache views, exact byte accounting, block-aligned lookup,
   atomic lookup-and-pin semantics, copy-on-write divergence, bounded eviction,
   and an inspectable snapshot.
2. Integrate the module into Swift MLX prefill. Prepare input through the
   production renderer, restore the longest compatible block prefix, execute
   only the uncached suffix up to the stored boundary, and return a decode
   context whose cache still references the shared blocks.
3. Carry executed paged evidence through `RuntimePrefillResult` and
   `WorkerPrefillResult`. Build protocol block tables from the real block IDs,
   token spans, and bytes. Populate `recovered_prefix_tokens`,
   `cache_hit_mode`, and typed fallback evidence on the Prefill RPC.
4. Make handshake, cache statistics, runtime KV bytes, hit rate, and dedup ratio
   use the executed pool/real block tables. Remove the fixed 1024-byte-per-token
   estimate from the executed path and keep metadata-only fallback tables
   visibly non-executed.
5. Update the architecture and cache runbook to document supported families,
   byte-budget behavior, persistence boundaries, and refusal reasons.
6. Add focused correctness, compatibility, lifetime, byte-accounting, and
   performance tests. Run the complete repository gate and record the final
   metrics before handoff.
7. Preserve the homogeneous decode contract for paged sessions with a
   lease-preserving batch adapter and prove actual model-eval batch size and
   per-batch throughput for concurrent shared-prefix sessions.
8. Run a same-load paired contiguous-versus-paged probe with the same loaded
   model, prompt, four sessions, and output-token count. Poll both MLX allocator
   memory and process RSS concurrently across the complete prefill and batched
   decode interval, then archive peak and steady deltas for both modes.
9. Track each active request-private tail as one pool-owned allocation owner.
   Publish exact per-layer tensor bytes after append, trim, copy-on-write, and
   release; include those bytes in physical resident, logical ownership, peak,
   and store-admission budget calculations without double-counting a successful
   private-to-shared ownership transfer.
10. When atomic store validation or budget admission fails after model prefill,
    materialize the already-computed paged state once into ordinary
    `KVCacheSimple` caches, evaluate that state, and release all paged leases and
    private allocation owners. This fallback must not invoke model prefill a
    second time and must preserve decode parity.
11. Register a dedicated PR-scoped Paged KV probe whose watch set includes the
    pool, Swift backend, runtime registry/cache projection, focused tests, probe
    implementation, and this plan. The probe must emit numeric ownership,
    fallback, correctness, batching, and paired-memory acceptance metrics.
12. Make lookup cache materialization a one-shot lease transfer. Keep only a
    weak post-transfer reference for atomic store validation, and prove a second
    `makeCaches()` call returns no caches and creates no additional private owner.
13. Close independent-review findings by applying the minimum non-zero
    request/model budget, including `scope_id` in compatibility, carrying and
    validating stream ownership through decode, making owner accounting a
    single lock-ordered transaction, protecting leased LRU entries, and
    releasing shared blocks at per-layer trim boundaries.
14. Make compatibility components collision-free with length-prefixed encoding,
    project the exact admission budget into each prefill response, and derive
    behavioral acceptance metrics from passing Swift test logs plus the real
    paired-memory artifact.
15. Resolve one logical cache identity before runtime entry and attach it to the
    committed tensor snapshot. Route registry pin, unpin, and purge through the
    real pool transaction, derive exposed L1 prefix/block/statistics projections
    from the pool, and treat metadata/disk mutation as secondary bookkeeping.
16. Add a pre-model-call text-model capability gate for composite runtime state.
    Prove with a model-call counter that fallback performs exactly one
    contiguous prepare and zero paged model calls, and include that test in the
    `fallback_second_prefill_count` acceptance probe.
17. Derive scope IDs, runtime compatibility, and pool logical keys from one
    complete field list. Return pool statistics and operator projection from one
    lock generation, and keep failed paged pin/unpin operations from mutating the
    metadata mirror.
18. Use that complete logical key for HotCache and DiskCache indexing, exact
    purge, and persisted prefix filenames. Migrate legacy prefix-ID filenames on
    load, fail ambiguous CacheKey-only L2 restore closed, and require typed
    execution identity before an exact purge can delete one of several boundary
    snapshots. Legacy snapshots without typed execution identity always remain
    fail-closed under exact purge, even after only one matching prefix remains.

## Performance Probes

### Measurement points

- pool lookup-and-pin latency;
- cache restore/view construction latency;
- cold prefill model-call token count versus warm suffix model-call token count;
- configured prefill forward chunk, actual call count, and min/max call shape;
- physical resident block bytes versus logical per-request KV bytes;
- paired MLX active/peak allocator bytes and sampled process RSS while the same
  `N` concurrent sessions remain live through a real batched decode update;
- shared block count, restored block count, and copy-on-write block count;
- attention gather latency for one decode update;
- paged-session decode model-eval batch size and per-batch tokens per second;
- fallback count and reason by cache layout/compatibility class.

### Success metrics

- Two sessions with a shared block-aligned prompt reference the same block IDs.
- `physical_kv_bytes < logical_kv_bytes` for the shared-prefix fixture, with the
  saved byte count exactly equal to the shared real tensor payload.
- Warm prefill executes zero model work for restored full blocks and processes
  only the uncached suffix boundary.
- With an effective prefill window larger than one block, cold prefill uses the
  block-aligned window chunk and performs `ceil(boundary / chunk)` model calls,
  not one call per block; the signature and execution evidence agree.
- Compatible paged sessions execute one homogeneous model batch, keep their
  original row cache/lease identities after split, and report model-eval batch
  size greater than one with non-zero batch throughput.
- Paged and contiguous cache fixtures produce byte-identical gathered K/V
  arrays and identical next-token logits for the deterministic model fixture.
- Model epoch, scope, layout, stream owner, block-size, and prefill-shape
  mismatches produce zero restored tokens.
- Identical token IDs with different production input shapes cannot cross-hit,
  and stale or structurally mismatched lookup handles cannot extend an entry.
- Rotating, hybrid/recurrent, active-KV-quantized, and metadata-only L2 paths
  never set an executed paged-cache hit.
- The synthetic lookup-and-restore probe has zero leaked references, zero
  negative reference counts, p95 warm lookup plus view construction below
  1 ms, and p95 single-layer attention gather for one decode update below 1 ms
  on the local Apple Silicon host. These latency budgets are enforced by the
  non-instrumented focused test on local and controlled self-hosted runners.
  The GitHub-hosted and changed-line coverage runs still execute the measurement
  and correctness paths, but do not enforce wall-clock microbenchmark budgets:
  shared-runner scheduling and coverage instrumentation are not valid absolute
  latency environments.
- The paired probe starts contiguous and paged measurement from MLX active
  baselines within 64 KiB, reports more than one concurrent sample for each
  mode, and covers at least four live sessions through prefill and batched
  decode.
- Under the same model, prompt, session count, and output-token count, paged MLX
  active peak delta and allocator-reported peak delta are both strictly lower
  than the contiguous deltas. Process RSS peak and steady deltas are recorded
  as corroborating host-level evidence, not substituted for allocator truth.
- Changed-scope automated coverage is at least 95 percent and the PR-scoped
  performance report has zero unexplained regression or verification failure.
- A block-aligned prefill plus a non-empty prompt tail and multi-token decode
  reports every live private K/V tensor byte, then returns private resident
  bytes and owner count to zero after context release.
- A lookup lease can materialize only one cache set; repeated materialization
  returns no caches, and a live private tail is attributed to exactly one owner.
- Budget rejection and stale-snapshot races use ordinary `KVCacheSimple`
  decode state after exactly one model-prefill pass, preserve contiguous output
  parity, and leave no paged block lease or private allocation owner alive.
- With the real Swift backend behind `WorkerRuntimeRegistry`, pinning a logical
  prefix prevents budget LRU eviction, unpinning permits eviction, and purging
  removes the tensor entry so the next identical request cannot report an exact
  hit. Cache statistics, scope summaries, hot-prefix projection, pinned-prefix
  projection, and the real block table agree after every mutation.
- Concurrent store or purge cannot split `GetCacheStats` across two pool
  generations; its statistics and logical projection come from one locked
  snapshot.
- A composite-state model is rejected before paged lookup, allocation, or model
  evaluation. Its evidence records one contiguous prepare, zero paged model
  calls, and zero second-prefill fallbacks.
- Changes to any Paged KV execution or projection file select the dedicated
  Paged KV PR-scoped probe, whose final report has zero regression and zero
  verification failure.
- The probe emits numeric zero-count acceptance for owner leaks, correctness
  mismatches, second-prefill fallbacks, row-cache identity mismatches, scope
  cross-hits, leased-entry eviction, retained bytes after full-layer trim, and
  tightest-budget violations. It also requires at least one proven cross-stream
  contiguous fallback.

## Paired memory result

The 2026-08-04 local Apple Silicon probe used the same loaded deterministic
model, 33-token prompt, four sessions, and two output tokens per session. Both
modes started from `600336` MLX active bytes. Contiguous execution reached a
`2249888`-byte MLX active peak delta and a `2916352`-byte RSS peak delta. Paged
execution reached a `173116`-byte MLX active peak delta and a `311296`-byte RSS
peak delta. The paged reductions were therefore `2076772` MLX active bytes and
`2605056` RSS bytes. The allocator-reported peak reduction was `2224216` bytes.
Pool accounting reported `40960` real resident bytes, including active private
tails, versus `172032` logical session bytes.

The registered focused gate captures passing XCTest cases in four Swift test
logs and merges them with the raw paired-memory output. The generated artifact
records the focused behavioral acceptance results:
zero owner leaks, cache mismatches, second-prefill fallbacks, batch row-cache
identity mismatches, scope cross-hits, leased-entry evictions, retained bytes
after all layer views trim a block, and tightest-budget violations. Three
cross-stream decode fallbacks, one direct and two from rejected batch rows, are
retained as positive evidence that both stream-owner guards executed.

The tiny-fixture batched decode throughput was `1402.28` tokens/second for
contiguous execution and `860.03` tokens/second for paged execution. This probe
is a memory acceptance gate, not a representative serving-throughput benchmark;
the throughput values are retained so the gather cost remains visible. The
versioned acceptance artifact, including the focused test-derived counters, is
`docs/metrics/issue-2601-paired-contiguous-paged-memory.json`.

Sampling adequacy remains an absolute acceptance condition: both modes must
produce more than one concurrent watermark sample, and the probe fails closed
when either mode does not. The raw minimum sample count remains visible as an
informational metric because it varies with host speed and scheduler timing; it
is not a relative performance score against a historical artifact.

The complete changed-line coverage run for the seven changed production files
reported `97.01%` (`2238/2307`). The complete `WorkerScaffoldTests` suite passed
all `349` tests with coverage enabled. Per-file coverage was `97.14%` for the
paged pool, `96.44%` for the backend, `97.96%` for disk-cache identity,
`96.18%` for hot-cache identity, `99.19%` for the registry, and `100%` for the
prefill engine. `TextRuntime.swift` reported `92.21%` (`71/77`) while the
measured changed scope remained above the repository's 95 percent gate.
When the PR-scoped runner evaluates a staged follow-up that changes only tests,
registry metadata, or documentation, the coverage command treats the exact
`100% (0/0)` result as N/A for that filtered scope. Unfiltered runs and filtered
runs with measurable production lines remain fail-closed and must satisfy the
95 percent threshold.

Independent Standards and Spec review found no P0 or P1 issue. The remaining
identity finding was resolved by sharing one complete logical-prefix key between
the paged pool and the hot-cache metadata mirror. Metadata indexing, pinning,
ownership, lookup, and exact purge no longer select entries by the externally
visible prefix ID or CacheKey alone. A regression test covers two prefixes with
the same explicit scope ID, CacheKey, and prefix ID but different reasoning
scope: both remain visible, and pin or purge of one cannot mutate the other. The
affected HotCache/paged-pool group passed `21/21` tests, and the real-pool
registry pin/purge integration passed `1/1`.

A follow-up Standards review found that L2 metadata still used the old short
prefix index. Disk records now use the shared complete key in memory and on disk;
exact purge isolates both prefix records and typed boundary snapshots, while a
legacy untyped snapshot always remains fail-closed under exact purge. Regression
tests persist colliding explicit scope variants, restart the store, purge each
variant in turn, and verify typed snapshot isolation, legacy snapshot retention,
and legacy-filename migration.

The final independent review found two remaining operator-identity gaps. The
worker's automatic cache-key derivation now encodes the exact structured
messages and complete resolved scope with versioned length-prefixed fields,
rather than trimming and joining text fragments. Hot, disk, and real-pool
operator summaries now group by complete `CacheScope` identity instead of the
external `scope_id`; colliding low/high reasoning variants remain separate in
all three projections. The obsolete CacheKey-only disk comparison helper was
removed. Focused regressions for all four paths passed `4/4`; the registered
performance gate passed its `26 + 11 + 9 + 1` Swift groups, and the versioned
artifact now asserts all 26 required acceptance tests by name.

## Verification

The registered focused command must provision the locked Python `mlx` extra
before launching the Swift live-bridge tests. PR-scoped performance runs verify
the head in an isolated worktree, so they cannot depend on a developer's
pre-existing `mlx.metallib` outside that worktree.

The PR-scoped workflow must also pass the immutable pull-request base SHA as
`MELIX_PAGED_KV_COVERAGE_DIFF_FROM`. The head checkout fetches that exact commit
object before the gate runs; coverage must not assume that a mutable
`origin/main` remote-tracking ref exists in the isolated checkout.

Focused checks:

```bash
jq -r '.[] | select(.id == "paged-kv-cache-ownership-memory") | .test_command' \
  infra/perf/pr_scoped_probes.json | bash
python3 scripts/paged_kv_cache_probe.py \
  --artifact .runtime/metrics/paged-kv-cache-ownership-memory.json
bash scripts/paged_kv_cache_coverage.sh
```

Repository gate:

```bash
make bootstrap
make proto
make swift-test
make py-test
make integration-test
.githooks/pre-commit
```

## Acceptance Criteria

- `supportsPagedCache` is true only in a worker build/runtime that executes the
  block-backed Swift MLX path.
- Every admitted block has real tensor payload and measured bytes.
- Cross-session prefix reuse reduces retained physical KV bytes and prefill
  model work, with observable hit/restore evidence.
- Divergence is copy-on-write and decode correctness matches contiguous cache.
- Unsupported compatibility classes fail closed without saved-work credit.
- L2 remains explicitly metadata-only until real payload persistence lands.
- Documentation, coverage, metrics, and full verification evidence are current.

## Rollback or Safe Exit

The paged module remains behind strict runtime admission. Removing the runtime
admission call and restoring `supportsPagedCache=false` returns all requests to
the existing contiguous prefill/decode path without changing protocol data or
persisted metadata envelope formats.
