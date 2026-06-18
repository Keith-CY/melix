# Issue 1759 Companion Status Endpoint

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a scoped, read-only companion status endpoint that returns a redacted mobile-friendly runtime summary for issue #1759.

**Architecture:** Build on the companion auth scope delivered in PR #2068. The HTTP gateway owns route admission, collects already-available runtime read models, and emits a dedicated companion payload that excludes prompt text, raw logs, artifact URIs, local paths, and request bodies.

**Tech Stack:** Swift control plane HTTP gateway, `PersistentAuthSessionStore`, `SchedulerReadModel`, `ImageJobReadModel`, `CacheMetadataStore`, Swift Testing.

---

## Context

Issue #1759 asks for a paired read-only companion/mobile surface. PR #2068 already delivered durable `companion_read_only` sessions, read-only route enforcement, mutation denial, and self-revocation. The next safe server-side slice is a single aggregate status endpoint that future QR/mobile UI can call without stitching several operator routes together.

The best end-state architecture is a companion API layer with deliberately narrow DTOs. It should not reuse internal operator payloads if those payloads include raw prompts, recipes, local artifact URIs, request bodies, or logs. Later UI slices can render this endpoint directly, and later receipt/log work can add redacted read models behind the same endpoint without expanding companion permissions.

## Slice Boundary

This transaction adds `GET /v1/melix/companion/status` only. It includes:

- runtime health route readiness;
- loaded model summary with model id, state, and supported modalities;
- cache summary numeric counters;
- scheduler queue summary;
- redacted image job summaries;
- current session status for the presented companion token;
- browser preflight support for the `x-melix-session` header used by companion clients;
- a redaction policy block documenting intentionally omitted private surfaces.

This transaction does not add QR pairing UI, desktop token management UI, mobile HTML/CSS, receipt history, or log tail UI. Receipt and log-tail content stay omitted until a redacted read model exists.

## Performance Probes and Metrics

- Runtime metric: `companion.status_latency_ms` records endpoint assembly latency.
- The endpoint reads in-memory control-plane models only and does not call model workers.
- Observability mode: `minimal`, one latency metric on the HTTP gateway path.
- Success metric: focused Swift tests cover the new route and redaction contract; changed-line coverage for touched Swift files remains at least 95 percent.
- PR merge gate: scoped performance report must stay `Status: ok` with zero regressions.

## Implementation Plan

### Task 1: Add the Failing Companion Status Contract Test

**Files:**
- Modify: `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`

- [x] **Step 1: Write the failing test**

Add a Swift test near the existing companion auth session test:

```swift
@Test("companion status endpoint returns redacted runtime queue job and session summary")
func companionStatusEndpointReturnsRedactedRuntimeQueueJobAndSessionSummary() async throws {
    // Create a companion_read_only session, seed queue and image job state with
    // private prompt material, call GET /v1/melix/companion/status, then assert:
    // - status code is 200;
    // - schema_version is melix.companion.status.v1;
    // - authorization.scope is companion_read_only;
    // - runtime/model/cache/queue/job summaries are present;
    // - private prompt text, negative prompts, artifact URIs, and local paths are absent;
    // - companion.status_latency_ms is recorded.
}
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests/companionStatusEndpointReturnsRedactedRuntimeQueueJobAndSessionSummary'
```

Expected: FAIL because `GET /v1/melix/companion/status` is not implemented or not allowlisted for companion sessions.

### Task 2: Implement the Companion Status Route

**Files:**
- Modify: `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`

- [x] **Step 1: Allow the route for companion read-only sessions**

Add `GET /v1/melix/companion/status` to `authorizationRoute(for:)` under `.companionReadOnly`.

- [x] **Step 2: Route requests to a new handler**

Add a route case in `handle(_:)`:

```swift
case (.get, "/v1/melix/companion/status"):
    response = try await handleCompanionStatus(authorization: authorizationContext)
```

- [x] **Step 3: Assemble a redacted companion payload**

Add `handleCompanionStatus(authorization:)` that gathers:

- `healthRoutes()`;
- user-visible model summaries;
- `CacheMetadataStore` summary or empty summary;
- `schedulerReadModel?.snapshot()`;
- `imageJobReadModel?.snapshot()`.

Use new `Codable` DTOs instead of reusing `OpenAIImageJobPayload`, because the existing image job payload includes recipe prompts, prompt deltas, and artifact URIs.

- [x] **Step 4: Record the latency metric**

Set `companion.status_latency_ms` before returning the encoded JSON response.

- [x] **Step 5: Admit browser companion session headers**

Add `x-melix-session` to the local-server-security CORS preflight
`access-control-allow-headers` value so paired browser/mobile clients can call
the companion status endpoint from an allowed origin.

### Task 3: Verify Green and Adjacent Auth Behavior

**Files:**
- Test: `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`

- [x] **Step 1: Run focused green test**

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests/companionStatusEndpointReturnsRedactedRuntimeQueueJobAndSessionSummary'
```

Expected: PASS.

- [x] **Step 2: Run adjacent auth and health tests**

Run:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests/(companion|gatewayAuthSession|HealthDiagnostics|CacheStats)'
```

Expected: PASS.

### Task 4: Coverage, Metrics, Commit, and PR

**Files:**
- Modify: `.github/pull_request_template.md` only if the template itself changed, which is not expected.

- [x] **Step 1: Run changed-scope coverage**

Use the repository Swift coverage tooling for the touched control-plane gateway scope. Record the changed-line percentage and keep it at least 95 percent.

- [x] **Step 2: Run full local gate**

Run:

```bash
make swift-test
make py-test
make integration-test
```

Expected: all pass.

- [x] **Step 3: Commit and use the pre-commit performance report**

Run `make git-hooks-install` if needed, commit the plan/test/code changes, and let the pre-commit hook produce the scoped performance report. The report must show no performance regressions before pushing.

- [ ] **Step 4: Open and monitor the PR**

Fill `.github/pull_request_template.md` exactly. Include `docs/plans/2026-06-14-issue-1759-companion-status-endpoint.md` under `## Plan or Spec`, all command results under `## Commands Run`, coverage/performance under `## Coverage and Metrics`, and deferred UI/receipt/log work under `## Known Gaps`.

Monitor CI, review threads, conflicts, and the PR performance report. Fix any in-scope failure or regression before squash merging.

## Verification Results

- Red contract test:
  - `HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests/companionStatusEndpointReturnsRedactedRuntimeQueueJobAndSessionSummary'`
  - Result before implementation: expected failure because `GET /v1/melix/companion/status` did not yet return the `authorization` status payload.
- Red CORS contract test:
  - `HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests/localServerSecurityAllowsExplicitBrowserPreflightWithExactCORSEcho'`
  - Result before implementation: expected failure because `access-control-allow-headers` did not yet include `x-melix-session`.
- Focused green tests:
  - `HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests/(companionStatusEndpointReturnsRedactedRuntimeQueueJobAndSessionSummary|localServerSecurityAllowsExplicitBrowserPreflightWithExactCORSEcho)'` passed 2 tests.
  - `HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests/(companion|gatewayAuthSession|HealthDiagnostics|CacheStats|localServerSecurityAllowsExplicitBrowserPreflightWithExactCORSEcho)'` passed 6 tests.
  - `HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests/(getHealthDiagnostics|getCacheStats)'` passed 6 tests.
  - `HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests/companionStatusEndpointSupportsLocalTrustedEmptyStoresAndDeterministicJobOrdering'` passed.
  - `HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests/companionStatusEndpointSupportsCredentialAuthAndNewestJobOrdering'` passed.
  - `HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests|PersistentAuthSessionStoreTests'` passed 219 tests.
- Changed-line coverage:
  - `HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'OpenAIHandlerTests/(companionStatusEndpoint|companionAuthSessionsCanReadStatusAndRevokeThemselvesButCannotMutateRuntime|localServerSecurityAllowsExplicitBrowserPreflightWithExactCORSEcho|getHealthDiagnostics|getCacheStats)'` passed.
  - `UV_PYTHON=3.12 uv run python scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata --diff-from origin/main services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift` reported `TOTAL 99.75% (395/396)`, production `OpenAIHandler.swift 99.30% (141/142)`, and tests `OpenAIHandlerTests.swift 100.00% (254/254)`.
- Full local gate and pre-commit performance report:
  - `make swift-test` passed.
  - `make py-test` passed with `4005 passed, 14 skipped, 2 warnings`.
  - `make integration-test` passed with `120 passed, 1 skipped`.
  - Pre-commit hook passed `make swift-test`, `make py-test`, and `make integration-test`.
  - Pre-commit performance report reported `Status: ok`, `Regressions: 0`,
    `Context regressions: 0`, `Verification failures: 0`, and `Selected probes: 0`.

## Deferred Work

- QR/code pairing UX.
- Desktop companion-token issuance and revocation controls.
- Mobile/narrow viewport dashboard smoke.
- Redacted recent receipt read model.
- Redacted log-tail read model and UI.
