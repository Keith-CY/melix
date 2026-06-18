# Issue 1986 OpenAI Conformance Harness Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for implementation. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a runnable OpenAI conformance harness that emits the existing `OpenAIConformanceReport` schema for live local endpoints, configured remote server profiles, and deterministic CI mock mode.

**Architecture:** Keep the in-process conformance matrix as the authoritative compatibility proof from ADR 0002, and add a client-side harness as an evidence layer. The harness shares Swift report types, runs a small row set through an injectable HTTP transport, and exposes a CLI executable that can use deterministic mock responses or a real OpenAI-compatible base URL.

**Tech Stack:** Swift Package executable target, Swift Testing, `RemoteProviderHTTPTransport`, `URLRequest`, `HTTPURLResponse`, `JSONSerialization`, `OpenAIConformanceReport`.

---

## Scope

This PR implements issue #1986 as a child slice of #1384:

- Add a reusable `OpenAIConformanceHarness` under the Swift control-plane core.
- Reuse `OpenAIConformanceReport` rows and summary without adding a parallel schema.
- Cover these runnable rows:
  - non-streaming `/v1/chat/completions` response shape,
  - streaming tool-call SSE response shape,
  - typed error-path shape that names an incompatible field and phase.
- Add deterministic mock-backend CI mode with no model weights or live socket.
- Add real-backend smoke mode for live local endpoints or configured remote server profile fields supplied as `base_url`, `model`, and optional API key.
- Add a `melix-openai-conformance` executable that writes the report JSON artifact.

This PR does not replace `OpenAIConformanceMatrixTests`, implement local-vs-remote proxy parity (#1989), add provider profile persistence, or require real model weights in CI.

## Success Metrics

- Mock-backend mode produces a report with `schema_version = melix.openai_conformance_report.v1` and all rows passing.
- Real-backend mode uses the same row definitions and writes an artifact even when rows fail or skip.
- Error row `observed_reason` includes HTTP status plus incompatible `field` and `phase` when the backend reports them.
- CLI argument validation returns field-specific usage errors instead of generic crashes.
- Changed-line coverage for touched Swift scope is at least 95 percent.
- PR-scoped performance report is `Status: ok` with no direct/gated regression.

## Implementation Tasks

- [x] Add failing Swift tests in `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIConformanceHarnessTests.swift`.
  - Mock mode report has three passing rows and uses the existing schema.
  - Live transport requests normalize `base_url`, include auth only when supplied, and carry the requested model.
  - Error-path row records `status`, `field`, and `phase` in `observed_reason`.
  - CLI parser rejects missing real-backend `base_url`, `model`, and output path with named errors.
- [x] Add `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIConformanceHarness.swift`.
  - Define `OpenAIConformanceHarnessTarget`, `OpenAIConformanceHarness`, and `MockOpenAIConformanceTransport`.
  - Build rows once and execute them through `RemoteProviderHTTPTransport`.
  - Convert request/response mismatches into `OpenAIConformanceRow` failures with specific reasons.
- [x] Add the executable target.
  - Add product `melix-openai-conformance` and target `OpenAIConformanceHarnessCLI` in `Package.swift`.
  - Add `services/control-plane-swift/Sources/OpenAIConformanceHarnessCLI/main.swift`.
  - Support `--mode mock-backend-ci|real-backend-smoke`, `--base-url`, `--model`, `--api-key`, and `--output`.
- [x] Document usage.
  - Update this plan with verification receipts.
  - Keep ADR 0002 unchanged because the harness is already described there as additive evidence.
- [x] Verify focused scope.
  - Run focused harness tests.
  - Run focused conformance matrix tests to prove the authoritative boundary proof still passes.
  - Run changed-line coverage for touched Swift files.
  - Full local gate and PR-scoped performance are still required before PR creation.

## Verification Receipts

- RED: `swift test --package-path services/control-plane-swift --filter OpenAIConformanceHarnessTests` failed because `OpenAIConformanceHarness` and `OpenAIConformanceHarnessCLI` did not exist.
- GREEN: `swift test --package-path services/control-plane-swift --filter OpenAIConformanceHarnessTests` passed with 8 tests in 1 suite.
- Boundary proof: `swift test --package-path services/control-plane-swift --filter OpenAIConformanceMatrixTests` passed with 17 tests in 1 suite.
- CLI smoke: `swift run --package-path services/control-plane-swift melix-openai-conformance --mode mock-backend-ci --output .runtime/issue1986/mock-report.json` wrote a report with `passed=3 failed=0 skipped=0`.
- Focused coverage: `OpenAIConformanceHarnessTests|OpenAIConformanceMatrixTests` passed with 25 tests in 2 suites; changed-line coverage was `99.71%` (`699/701`) for touched Swift source/test files.
- Review RED: `swift test --package-path services/control-plane-swift --filter OpenAIConformanceHarnessTests` failed on real-backend CLI fallback-to-mock, whitespace-sensitive SSE validation, `URLError.cancelled` handling, and silent `--model-id` option typos.
- Review GREEN: `swift test --package-path services/control-plane-swift --filter OpenAIConformanceHarnessTests` passed with 9 tests in 1 suite after defaulting real-backend smoke to `URLSessionRemoteProviderHTTPTransport`, parsing SSE JSON events, propagating URLSession cancellations, and validating CLI option names.
- Review boundary proof: `swift test --package-path services/control-plane-swift --filter OpenAIConformanceMatrixTests` passed with 17 tests in 1 suite after the review fixes.
- Review CLI smoke: `swift run --package-path services/control-plane-swift melix-openai-conformance --mode mock-backend-ci --output .runtime/issue1986/mock-report-after-review.json` wrote a report with `passed=3 failed=0 skipped=0`.
- Review focused coverage: `OpenAIConformanceHarnessTests|OpenAIConformanceMatrixTests` passed with 26 tests in 2 suites; changed-line coverage was `99.62%` (`794/797`) for touched Swift source/test files.

## Verification Commands

Focused:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter OpenAIConformanceHarnessTests
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter OpenAIConformanceMatrixTests
git diff --check
```

Changed-line coverage:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'OpenAIConformanceHarnessTests|OpenAIConformanceMatrixTests'
UV_PYTHON=3.12 uv run python scripts/swift_changed_line_coverage.py \
  --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests \
  --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata \
  --diff-from origin/main \
  services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIConformanceHarness.swift \
  services/control-plane-swift/Sources/OpenAIConformanceHarnessCLI/main.swift \
  services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIConformanceHarnessTests.swift
```

Pre-PR local gate:

```bash
make swift-test
make py-test
make integration-test
```

Metrics:

```bash
UV_PYTHON="${MELIX_PRE_COMMIT_UV_PYTHON:-${UV_PYTHON:-3.12}}" uv run --frozen --project services/mlx-worker-python --extra mlx python scripts/pre_commit_gate.py
```
