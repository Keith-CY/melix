# Issue 1759 Companion Log Tail

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or inline TDD execution to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a redacted companion log-tail summary to the read-only companion status endpoint for issue #1759.

**Architecture:** Extend `ImageJobReadModel` with a small in-memory, redacted state-event tail, then expose it through the existing companion status DTO. The HTTP payload carries safe event metadata only and keeps prompts, prompt deltas, request bodies, artifact URIs, local paths, and error messages omitted by construction.

**Tech Stack:** Swift control plane HTTP gateway, `ImageJobReadModel`, Swift Testing, changed-line coverage tooling, pre-commit performance report.

---

## Context

Issue #1759 asks for a read-only companion/mobile surface with runtime status,
recent receipts, and log-tail redaction. Previous slices added companion
read-only auth, `GET /v1/melix/companion/status`, and redacted recent image-job
receipt summaries. The remaining safe server-side slice is a redacted log tail
that future mobile UI can render without reading raw log files or exposing
private prompt/session content.

## Slice Boundary

This transaction adds:

- a bounded in-memory image-job state event tail on `ImageJobReadModel`;
- a top-level `logs` object in `melix.companion.status.v1`;
- safe log fields: source, event type, job id, request id, model id, operation,
  state, lane, worker id, progress stage, timestamp, and failure code;
- redaction metadata for raw log line, prompt text, request body, artifact URIs,
  local paths, and error messages;
- tests proving private prompts, prompt deltas, artifact URIs, local paths, and
  error messages do not appear in companion log payloads.

This transaction does not add:

- QR/code pairing UX;
- desktop companion-token issuance or revocation controls;
- mobile/narrow viewport UI smoke;
- generic filesystem log tailing;
- raw OSLog, worker stdout/stderr, or arbitrary runtime log reads.

## Performance Probes And Metrics

- Runtime metric remains `companion.status_latency_ms` on the aggregate endpoint.
- The new read model appends one small value per image-job state update and caps
  retained entries at 50.
- The companion status endpoint sorts and returns at most 20 visible log entries.
- Success metric: focused Swift tests cover the log-tail payload and redaction
  contract; changed-line coverage for touched Swift files remains at least 95
  percent.
- PR merge gate: scoped performance report must stay `Status: ok` with zero
  regressions.

## Implementation Plan

### Task 1: Add RED Tests

**Files:**
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/ImageJobReadModelTests.swift`
- Modify: `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`

- [x] **Step 1: Add image job log-tail read model test**

Assert that queued/running/failed state updates append bounded redacted entries,
newest-first ordering is deterministic, and only failure code, not failure
message, is exposed.

- [x] **Step 2: Add companion status payload test**

Seed image jobs with private prompt, prompt delta, artifact URI, local path, and
private error message. Call `GET /v1/melix/companion/status` and assert:

- `logs.source == "image_jobs"`;
- visible entries are newest-first;
- each entry contains safe metadata and redaction flags;
- raw private fields are absent from the JSON body;
- `redaction.logs == "redacted_tail"`.

- [x] **Step 3: Run focused tests to verify RED**

Run:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'ImageJobReadModelTests/imageJobLogTailPreservesRedactedStateEvents|OpenAIHandlerTests/companionStatusEndpointReturnsRedactedLogTail'
```

Result: failed as expected because `ImageJobReadModel` had no
`logTailSnapshot` member.

### Task 2: Implement The Read Model And DTO

**Files:**
- Modify: `services/control-plane-swift/Sources/ImageJobs/ImageJobReadModel.swift`
- Modify: `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`

- [x] **Step 1: Add `ImageJobLogEntry`**

Add a public value type with safe fields only:

- `eventType`
- `source`
- `jobID`
- `requestID`
- `modelID`
- `operation`
- `state`
- `lane`
- `workerID`
- `progressStage`
- `createdAtUnixMs`
- `updatedAtUnixMs`
- `failureCode`

- [x] **Step 2: Record bounded entries**

Append one entry after each successful image-job state mutation. Retain the most
recent 50 entries, and expose `logTailSnapshot(limit:)` newest-first with
`updatedAtUnixMs` descending, then `jobID` ascending, then insertion order
descending.

- [x] **Step 3: Expose companion logs**

Read `logTailSnapshot(limit: 20)` in `handleCompanionStatus`, add a
`CompanionLogTailStatusPayload`, and change `CompanionRedactionStatusPayload`
`logs` to `redacted_tail`.

### Task 3: Verify Green, Coverage, Metrics, Commit, And PR

- [x] **Step 1: Run focused green tests**

Run the RED command again and then the adjacent companion status tests:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests/(companionStatusEndpointReturnsRedactedLogTail|companionStatusEndpointReturnsRedactedRecentReceiptSummaries|companionStatusEndpointReturnsRedactedRuntimeQueueJobAndSessionSummary|companionStatusEndpointSupportsLocalTrustedEmptyStoresAndDeterministicJobOrdering|companionStatusEndpointSupportsCredentialAuthAndNewestJobOrdering)'
```

- [x] **Step 2: Run changed-line coverage**

Run Swift coverage for the focused tests, then:

```bash
UV_PYTHON=3.12 uv run python scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata --diff-from origin/main services/control-plane-swift/Sources/ImageJobs/ImageJobReadModel.swift services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift services/control-plane-swift/Tests/ControlPlaneTests/ImageJobReadModelTests.swift services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift
```

Result: changed-line coverage is 99.27 percent total for touched Swift files;
`ImageJobReadModel.swift` is 96.15 percent, with only defensive enum fallback
branches uncovered.

- [ ] **Step 3: Run full local gate and PR lifecycle**

Run `make swift-test`, `make py-test`, `make integration-test`, commit with the
pre-commit hook enabled, open the PR with the repository template, monitor CI,
performance report, review threads, and merge only after all gates are green.
