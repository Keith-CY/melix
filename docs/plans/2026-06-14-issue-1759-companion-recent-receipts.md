# Issue 1759 Companion Recent Receipts

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a redacted recent-receipts summary to the read-only companion status endpoint for issue #1759.

**Architecture:** Keep companion status as a narrow HTTP DTO owned by `OpenAIHandler`. Derive recent receipt rows from the existing `ImageJobReadModel` snapshot, expose only identifiers, state, timing, digest, progress, artifact count, and failure code, and keep raw prompts, request bodies, local paths, artifact URIs, error messages, and log text out of the companion payload.

**Tech Stack:** Swift control plane HTTP gateway, `ImageJobReadModel`, Swift Testing, changed-line coverage tooling, pre-commit performance report.

---

## Context

Issue #1759 still needs read-only companion views for active jobs, recent receipts, and redacted log tail. PR #2074 added `GET /v1/melix/companion/status` with runtime, model, queue, cache, image-job, and authorization summaries, but intentionally kept receipt and log content omitted until a redacted read model existed.

This slice adds the first redacted receipt read model to the existing status endpoint. It intentionally derives from image jobs only because that read model already exists and already tracks long-running companion-relevant operations. It does not introduce a general log-tail reader.

## Slice Boundary

This transaction adds:

- a top-level `recent_receipts` object in `melix.companion.status.v1`;
- newest-first image-job receipt summaries with deterministic tie-breaking;
- per-receipt redaction metadata;
- redaction status `recent_receipts: "redacted_summary"`;
- tests proving private prompts, prompt deltas, source artifact IDs, storage URIs, local paths, and error messages do not appear.

This transaction does not add:

- QR/code pairing UX;
- desktop companion-token issuance or revocation controls;
- mobile/narrow viewport UI smoke;
- a generic receipt store for non-image operations;
- redacted log-tail read models or UI.

## Performance Probes and Metrics

- Runtime metric remains `companion.status_latency_ms` on the aggregate endpoint.
- The new receipt section reuses the already-loaded `ImageJobReadModel` snapshot and performs one in-memory sort with a visible limit of 10 rows.
- Success metric: focused Swift tests cover the new receipt payload and redaction contract; changed-line coverage for touched Swift files remains at least 95 percent.
- PR merge gate: scoped performance report must stay `Status: ok` with zero regressions.

## Implementation Plan

### Task 1: Add the Failing Recent Receipts Contract Test

**Files:**
- Modify: `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`

- [x] **Step 1: Write the failing test**

Add a Swift test near the companion status endpoint tests:

```swift
@Test("companion status endpoint returns redacted recent receipt summaries")
func companionStatusEndpointReturnsRedactedRecentReceiptSummaries() async throws {
    // Seed two image jobs with private prompts, prompt deltas, local artifact
    // URIs, and a private error message.
    // Call GET /v1/melix/companion/status.
    // Assert recent_receipts exists, orders newest first, includes only safe
    // receipt fields, marks raw fields as omitted, and excludes private text.
}
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests/companionStatusEndpointReturnsRedactedRecentReceiptSummaries'
```

Expected: FAIL because the companion status response has no top-level `recent_receipts` object yet.

### Task 2: Implement the Recent Receipts DTO

**Files:**
- Modify: `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`

- [x] **Step 1: Add `recentReceipts` to `CompanionStatusResponse`**

Populate it from the same `imageJobsSnapshot` already read by `handleCompanionStatus`.

- [x] **Step 2: Add receipt payload types**

Add `CompanionRecentReceiptStatusPayload`, `CompanionRecentReceiptPayload`, and `CompanionRecentReceiptRedactionPayload`. Sort by `updated_at_unix_ms` descending, then `job_id` ascending, and cap visible rows at 10.

- [x] **Step 3: Keep fields redacted by construction**

Expose only:

- `receipt_type`
- `source`
- `job_id`
- `request_id`
- `model_id`
- `operation`
- `state`
- `lane`
- `worker_id`
- `progress`
- `created_at_unix_ms`
- `updated_at_unix_ms`
- `prompt_digest`
- `artifact_count`
- `failure_code`
- `redaction`

Do not expose recipe fields, raw error messages, prompt deltas, artifact IDs, artifact storage URIs, local paths, request bodies, or log lines.

- [x] **Step 4: Update the redaction block**

Change `recent_receipts` from `omitted` to `redacted_summary`; keep `logs` as `omitted` until a log-tail read model exists.

### Task 3: Verify Green, Coverage, Metrics, Commit, and PR

**Files:**
- Test: `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`

- [x] **Step 1: Run focused green tests**

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests/(companionStatusEndpointReturnsRedactedRecentReceiptSummaries|companionStatusEndpointReturnsRedactedRuntimeQueueJobAndSessionSummary|companionStatusEndpointSupportsLocalTrustedEmptyStoresAndDeterministicJobOrdering|companionStatusEndpointSupportsCredentialAuthAndNewestJobOrdering)'
```

Expected: PASS.

- [x] **Step 2: Run changed-line coverage**

Run Swift coverage for the touched companion status tests, then:

```bash
UV_PYTHON=3.12 uv run python scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata --diff-from origin/main services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift
```

Expected: changed-line coverage is at least 95 percent.

- [x] **Step 3: Run full local gate**

Run:

```bash
make swift-test
make py-test
make integration-test
```

Expected: all pass.

- [ ] **Step 4: Commit and use the pre-commit performance report**

Run `make git-hooks-install` if needed, commit the plan/test/code changes, and let the pre-commit hook produce the scoped performance report. The report must show no performance regressions before pushing.

- [ ] **Step 5: Open and monitor the PR**

Fill `.github/pull_request_template.md` exactly. Include this plan under `## Plan or Spec`, all command results under `## Commands Run`, coverage/performance under `## Coverage and Metrics`, and deferred QR/UI/log-tail work under `## Known Gaps`.

Monitor CI, review threads, conflicts, and the PR performance report. Fix any in-scope failure or regression before squash merging.

## Verification Results

- Red contract test:
  - `HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests/companionStatusEndpointReturnsRedactedRecentReceiptSummaries'`
  - Result before implementation: expected failure because `payload["recent_receipts"]` was `nil`.
- Focused green tests:
  - `HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests/companionStatusEndpointReturnsRedactedRecentReceiptSummaries'` passed 1 test.
  - `HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests/(companionStatusEndpointReturnsRedactedRecentReceiptSummaries|companionStatusEndpointReturnsRedactedRuntimeQueueJobAndSessionSummary|companionStatusEndpointSupportsLocalTrustedEmptyStoresAndDeterministicJobOrdering|companionStatusEndpointSupportsCredentialAuthAndNewestJobOrdering)'` passed 4 tests.
- Changed-line coverage:
  - `HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'OpenAIHandlerTests/(companionStatusEndpointReturnsRedactedRecentReceiptSummaries|companionStatusEndpointReturnsRedactedRuntimeQueueJobAndSessionSummary|companionStatusEndpointSupportsLocalTrustedEmptyStoresAndDeterministicJobOrdering|companionStatusEndpointSupportsCredentialAuthAndNewestJobOrdering)'` passed 4 tests.
  - `UV_PYTHON=3.12 uv run python scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata --diff-from origin/main services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift` reported `TOTAL 100.00% (162/162)`.
- Full local gate:
  - `make swift-test` passed. The final macOS menubar stage reported `796 tests in 25 suites passed`.
  - `make py-test` passed with `4014 passed, 14 skipped, 2 warnings`.
  - `make integration-test` passed with `120 passed, 1 skipped`.
