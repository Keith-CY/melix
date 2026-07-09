# Issue 2601 Paged Cache Truthful Capabilities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the Swift Text Worker from advertising executed paged-cache support while its page and block tables remain metadata-only.

**Architecture:** Keep the existing hot-tier prefix cache, block-table metadata, disk metadata persistence, and cache snapshot surfaces intact. Change only the runtime capability and `CacheStats` truth flags so `supports_prefix_cache=true` remains accurate and `supports_paged_cache=false` until real block-pool KV ownership lands.

**Tech Stack:** Swift Text Worker, Melix worker protobuf Swift artifacts, Swift Testing/XCTest worker tests.

---

## Governing Issue

- GitHub issue: `#2601`
- Related plan: `docs/plans/2026-03-30-m2-2-text-worker-paged-cache-ownership.md`
- Related plan: `docs/plans/2026-03-28-p3-m2-hot-tier-cache-primitives.md`

## Scope

- Change `WorkerRuntimeRegistry.capabilities()` so the Swift Text Worker cache capability handshake reports `supportsPagedCache=false`.
- Change `HotCacheStore.buildStats(...)` so `CacheStats.supportsPagedCache=false` on the worker stats and snapshot summary.
- Add regression tests proving prefix-cache metadata remains available while paged-cache execution is no longer advertised.
- Preserve existing block/page metadata snapshots, `supportsPrefixCache`, supported cache modes, hot-prefix reuse, and control-plane forwarding behavior.

## Non-Goals

- No protobuf schema change.
- No real block-pool KV ownership implementation.
- No attention-over-block-table runtime implementation.
- No control-plane projection change beyond consuming the corrected worker stats.
- No cache metric renaming in this slice.

## Performance Probes

Measurement points:

- This slice does not change runtime cache lookups, prefill registration, decode, or block-table construction.
- The PR-scoped performance report may select no probes; if it does, accepted result is `status=ok`, regressions `0`, verification failures `0`.

Success metrics:

- Focused Swift worker cache tests pass.
- Changed-scope Swift coverage for touched files remains at or above 95 percent.
- Full local pre-commit gate passes before commit on this host.

## Implementation Steps

### Task 1: Add failing worker capability and stats tests

**Files:**

- Modify: `services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift`

- [x] **Step 1: Add a capability handshake assertion**

In the existing worker info/capability test near the `supportsPrefixCache` assertion, assert:

```swift
XCTAssertTrue(response.capabilities.cache.supportsPrefixCache)
XCTAssertFalse(response.capabilities.cache.supportsPagedCache)
```

- [x] **Step 2: Add a cache stats assertion**

In `testRuntimeRegistryStoresPrefillContextsForLoadedModel`, after `let cacheResponse = await registry.cacheStatsResponse()`, assert:

```swift
XCTAssertTrue(cacheResponse.stats.supportsPrefixCache)
XCTAssertFalse(cacheResponse.stats.supportsPagedCache)
XCTAssertTrue(cacheResponse.snapshot.stats.supportsPrefixCache)
XCTAssertFalse(cacheResponse.snapshot.stats.supportsPagedCache)
```

- [x] **Step 3: Verify red**

Run:

```bash
xcrun swift test --package-path services/mlx-text-worker-swift --filter WorkerScaffoldTests/testHandshakeReturnsExpectedRuntimeMetadata
xcrun swift test --package-path services/mlx-text-worker-swift --filter WorkerScaffoldTests/testRuntimeRegistryStoresPrefillContextsForLoadedModel
```

Expected result: the two new `supportsPagedCache` assertions fail because current `main` still reports `true`.

### Task 2: Correct the worker capability and stats flags

**Files:**

- Modify: `services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift`
- Modify: `services/mlx-text-worker-swift/Sources/Core/HotCacheStore.swift`

- [x] **Step 1: Change the worker capability handshake**

In `WorkerRuntimeRegistry.capabilities()`, set:

```swift
cache.supportsPrefixCache = true
cache.supportsPagedCache = false
```

- [x] **Step 2: Change cache stats**

In `HotCacheStore.buildStats(...)`, set:

```swift
stats.supportsPrefixCache = true
stats.supportsPagedCache = false
```

- [x] **Step 3: Verify green**

Run:

```bash
xcrun swift test --package-path services/mlx-text-worker-swift --filter WorkerScaffoldTests/testHandshakeReturnsExpectedRuntimeMetadata
xcrun swift test --package-path services/mlx-text-worker-swift --filter WorkerScaffoldTests/testRuntimeRegistryStoresPrefillContextsForLoadedModel
```

Expected result: both focused tests pass.

### Task 3: Verify changed scope and local gate

**Files:**

- Modify: `docs/plans/2026-07-09-issue-2601-paged-cache-truthful-capabilities.md`

- [x] **Step 1: Run focused Swift worker tests**

```bash
xcrun swift test --package-path services/mlx-text-worker-swift --filter WorkerScaffoldTests/testHandshakeReturnsExpectedRuntimeMetadata
xcrun swift test --package-path services/mlx-text-worker-swift --filter WorkerScaffoldTests/testRuntimeRegistryStoresPrefillContextsForLoadedModel
xcrun swift test --package-path services/mlx-text-worker-swift --filter WorkerScaffoldTests/testCacheManagementRpcsExposeHotAndDiskTierMetadata
xcrun swift test --package-path services/mlx-text-worker-swift --filter WorkerScaffoldTests/testWorkerCacheStatsExposeRuntimeFingerprintAndMemoryBudgetDiagnostics
```

- [x] **Step 2: Run changed-scope coverage**

```bash
xcrun swift test --package-path services/mlx-text-worker-swift --enable-code-coverage --filter WorkerScaffoldTests
UV_PYTHON=3.12 uv run --python 3.12 python3 scripts/swift_changed_line_coverage.py \
  --binary services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/MelixTextWorkerSwiftPackageTests.xctest/Contents/MacOS/MelixTextWorkerSwiftPackageTests \
  --profdata services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata \
  services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift \
  services/mlx-text-worker-swift/Sources/Core/HotCacheStore.swift \
  services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift
```

- [x] **Step 3: Run repository gate before commit**

```bash
git diff --check
.githooks/pre-commit
```

Expected result: pre-commit runs `make swift-test`, `make py-test`, `make integration-test`, and writes an acceptable PR-scoped performance report.

## Verification Results

- Red test:
  `xcrun swift test --package-path services/mlx-text-worker-swift --filter 'WorkerScaffoldTests/testHandshakeReturnsExpectedRuntimeMetadata|WorkerScaffoldTests/testRuntimeRegistryPrefillRegistersHotCacheMetadata'`
  failed as expected before implementation on
  `WorkerScaffoldTests.swift:685: XCTAssertFalse failed`, proving current
  `main` advertised paged-cache support through the handshake. The second name
  in that red command was stale and matched no test after the first assertion
  failed; the corrected cache-stats test name is
  `WorkerScaffoldTests/testRuntimeRegistryStoresPrefillContextsForLoadedModel`
  and passed after implementation.
- Focused handshake test:
  `xcrun swift test --package-path services/mlx-text-worker-swift --filter WorkerScaffoldTests/testHandshakeReturnsExpectedRuntimeMetadata`
  passed with `1 test, 0 failures`.
- Focused cache-stats test:
  `xcrun swift test --package-path services/mlx-text-worker-swift --filter WorkerScaffoldTests/testRuntimeRegistryStoresPrefillContextsForLoadedModel`
  passed with `1 test, 0 failures`.
- Adjacent cache RPC test:
  `xcrun swift test --package-path services/mlx-text-worker-swift --filter WorkerScaffoldTests/testCacheManagementRpcsExposeHotAndDiskTierMetadata`
  passed with `1 test, 0 failures`.
- Adjacent runtime-cache diagnostics test:
  `xcrun swift test --package-path services/mlx-text-worker-swift --filter WorkerScaffoldTests/testWorkerCacheStatsExposeRuntimeFingerprintAndMemoryBudgetDiagnostics`
  passed with `1 test, 0 failures`.
- Coverage suite:
  `xcrun swift test --package-path services/mlx-text-worker-swift --enable-code-coverage --filter WorkerScaffoldTests`
  passed with `245 tests`, `55 skipped`, and `0 failures`.
- Changed-scope coverage:
  `UV_PYTHON=3.12 uv run --python 3.12 python3 scripts/swift_changed_line_coverage.py ...`
  passed with `TOTAL 100.00% 7/7`.
- `git diff --check` passed.
