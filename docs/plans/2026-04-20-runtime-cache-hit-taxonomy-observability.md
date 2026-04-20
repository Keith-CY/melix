# Milestone #40 · Phase 1 — Runtime Cache Hit Taxonomy Observability

## Context

Issue [#40](https://github.com/Keith-CY/melix/issues/40) is a four-phase milestone for runtime cache reuse and scheduler stability. The quantitative goals (25% p50 / 20% p95 TTFT on repeated prompts; 10 000-request soak with zero leaked cache references) belong to Phases 2–4 which depend on architectural work on prefix-boundary reuse, partial-prefix resume, and deferred cleanup.

Phase 1 is the observability foundation — **instrumentation and safety envelope** — explicitly scoped in the issue as:

> - runtime counters for exact-hit, partial-hit, and fallback paths
> - deterministic tests that prove cache references are released on reconstruction failure
> - thread new metrics into existing runtime probes and release-evidence reports

Current state (`main @ 6d9ad62b`):

- Cache logic lives in `services/mlx-text-worker-swift/Sources/Core/` (Swift text worker, not Python).
- `HotCacheStore.registerPrefill()` has three structurally distinct paths — **L1 exact hit**, **L2 restore**, **cold registration** — but only the L1 path increments `totalHits`. L2-restore hit and cold-fallback are unlabelled.
- `WorkerRuntimeRegistry.performPrefill` layers a **walked-back boundary snapshot restore** above `registerPrefill`; this is the "partial hit" pathway Phase 1 should expose. When the restore plan is nil and a snapshot ID was requested, today the runtime silently falls through to cold registration — a reconstruction failure with no telemetry.
- `MetricsStore` already carries cache rates (`cache_l1_hit_rate`, `cache_l2_restore_hit_rate`, `cache_block_reuse_ratio`). Adding four aggregate counters fits the existing pattern.
- Issue #35 active-KV guard behaviour is orthogonal; no feature flag to preserve.

## Slices

### 1A — Hit taxonomy counters in `HotCacheStore`

- Add `totalExactHits`, `totalPartialHits`, `totalFallbacks`, `totalReconstructionFailures` as `UInt64` state on the actor.
- Increment `totalExactHits` at both L1 hit and L2 restore exit paths in `registerPrefill()`; increment `totalFallbacks` at the cold-registration exit.
- Expose `recordPartialHit()` and `recordReconstructionFailure()` methods for the registry-level caller.
- Expose a new `hitTaxonomy()` accessor returning a `HotCacheHitTaxonomy` struct with the four counts.
- Keep existing `totalHits` / `l1HitRate` behaviour unchanged.

### 1B — Registry-level partial hit + reconstruction failure hooks

`services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift` — `performPrefill`:

- When `makeWalkedBackCacheRestorePlan` returns non-nil → call `cacheStore.recordPartialHit()` before the return.
- When the if-let fails **and** `cacheHints.restoreSnapshotID` was set → call `cacheStore.recordReconstructionFailure()` before falling through to cold path.

### 1C — Metrics emission

- `MetricsStore`: add four default-zero keys — `swift_text.cache_exact_hit_count`, `..._partial_hit_count`, `..._fallback_count`, `..._reconstruction_failure_count`.
- `TextPrefillEngine`: after prefill, pull `hitTaxonomy()` from the cache store and `metrics.set(...)` each key. Absolute cumulative counters, same style as existing `cache_l2_writeback_count`.

### 1D — Deterministic tests

`services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift` (new `// MARK: - Hit taxonomy` section — placed alongside the existing `HotCacheStore` suite so the file-private helpers stay reusable):

- Cold registration then repeat same-key prefill → exact hit increments on the repeat.
- Two distinct keys → fallback == 2, exact == 0.
- Invalid `restoreSnapshotID` → reconstruction failure increments, no partial hit.
- Valid walked-back restore plan → partial hit increments.
- **Reference invariant** — after a reconstruction failure, `HotCacheOwnershipSnapshot.pageRefCountByPageID` and `blockRefCountByBlockID` are unchanged vs. the pre-attempt snapshot. This is the explicit "cache references released on reconstruction failure" safety test the issue requires.

### 1E — Runtime probe integration

`scripts/phase8_runtime_probes.py`: read the four new metric keys from the worker metrics export after a probe run; include them in the evidence report. Presence + monotonicity only — Phase 1 does not assert ratios or absolute magnitudes (those are Phase 2+ targets).

## Critical files

```
services/mlx-text-worker-swift/Sources/Core/HotCacheStore.swift
services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift
services/mlx-text-worker-swift/Sources/Core/MetricsStore.swift
services/mlx-text-worker-swift/Sources/Core/Inference/TextPrefillEngine.swift
services/mlx-text-worker-swift/Tests/CoreTests/HotCacheHitTaxonomyTests.swift
scripts/phase8_runtime_probes.py
```

## Verification

1. `cd services/mlx-text-worker-swift && xcrun swift build`
2. `cd services/mlx-text-worker-swift && xcrun swift test --filter "testHotCacheHitTaxonomy|testPrefillRecordsHitTaxonomy"`
3. `cd services/mlx-text-worker-swift && xcrun swift test` — full worker regression.
4. `xcrun swift test --filter MelixCLI` — orthogonal sanity.
5. `make py-test` — orthogonal sanity.
6. Optional: start dev stack + run `scripts/phase8_runtime_probes.py`, confirm new keys surface in metrics JSON.

## Evidence to report

- New test count / total worker-Swift test count.
- Diff size per file.
- Sample metrics JSON showing the four keys after a single prefill.
- Sample showing `cache_exact_hit_count == 1` / `cache_fallback_count == 1` after two identical-key prefills.
- Explicit statement that Phase 1 ships observability only; Phases 2-4 use these counters to prove throughput / leak targets.

## Out of scope

- Prefix-boundary reuse (Phase 2).
- Partial-prefix resume with multimodal safety (Phase 3).
- Deferred cleanup + 10 000-request soak (Phase 4).
- Memory pressure rejection / batched KV quantization (collaborator comment on #40).
- Proto-level `CacheStats` extension — MetricsStore suffices for Phase 1.
- Per-request streamed event labels (`cache_hit_mode`, `fallback_reason`); aggregate counters land first.

## Risks

- Walked-back partial restore does not go through `HotCacheStore.registerPrefill`; mitigation — explicit `recordPartialHit()` call from `WorkerRuntimeRegistry` at the plan-success site.
- L2 restore could double-count if both branches increment; mitigation — only the exact-hit branch increments per call.
- Ref-invariant test requires exposing `HotCacheOwnershipSnapshot`; `snapshot()` already returns it publicly within the package, so no new accessor is expected.
- Keeping `totalHits` / `l1HitRate` unchanged is an explicit non-goal to preserve existing `CacheStats.l1HitRate` consumers.
