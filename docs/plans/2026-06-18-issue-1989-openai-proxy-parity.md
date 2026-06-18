# Issue 1989 OpenAI Proxy Parity Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for implementation. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a runnable proxy parity row set that proves local and configured remote OpenAI-compatible targets preserve the same normalized request contract and response shapes for the same fixture requests.

**Architecture:** Keep `OpenAIConformanceReport` as the single artifact schema from issue #1986. Add a parity harness beside `OpenAIConformanceHarness` that runs the existing chat/completions fixture rows against a local target and a remote Server Profile target, records sanitized normalized request receipts for each side, evaluates each response shape, and emits one report row per parity case. The row passes only when both sides have equivalent normalized request receipts and equivalent response-shape classifications; named receipt or response divergences become row failure reasons.

**Tech Stack:** Swift Package executable target, Swift Testing, `RemoteProviderHTTPTransport`, `URLRequest`, `HTTPURLResponse`, `JSONSerialization`, `OpenAIConformanceReport`.

---

## Scope

This PR implements issue #1989 as a child slice of #1384:

- Add a reusable `OpenAIProxyParityHarness` under the Swift control-plane core.
- Reuse `OpenAIConformanceReport` and `OpenAIConformanceRow` without changing the report schema.
- Cover these parity rows:
  - non-streaming `/v1/chat/completions` response shape,
  - streaming tool-call SSE response shape,
  - typed error-path shape that names field and phase.
- Compare sanitized normalized request receipts:
  - method,
  - normalized route path,
  - accept header,
  - content type,
  - request fixture kind,
  - sorted body field names,
  - stream flag,
  - tool declaration names,
  - tool-choice name,
  - unsupported field name for the error fixture,
  - model field presence, without leaking model IDs or API keys.
- Compare normalized response-shape receipts instead of model text:
  - non-streaming assistant message shape,
  - streaming tool-call delta plus `[DONE]` shape,
  - OpenAI-style error envelope with field and phase.
- Extend `melix-openai-conformance` with a `proxy-parity` mode so operators can write the same JSON artifact from two live endpoints.

This PR does not persist Server Profiles, add UI, replace remote-provider health/capability probes from #1757, require real model weights in CI, or compare generated semantic content.

## Success Metrics

- Mock parity mode produces `schema_version = melix.openai_conformance_report.v1`, `total = 3`, and all rows passing.
- Receipt divergences identify the mismatched key, for example `request_receipt.body_fields local=[...] remote=[...]`.
- Response divergences identify the side and shape reason, for example `remote_response=status=200 missing=tool_call_chunk`.
- CLI argument validation names missing local and remote target fields.
- Changed-line coverage for touched Swift scope is at least 95 percent.
- PR-scoped performance report is `Status: ok` with no direct/gated regression.

## Implementation Tasks

- [x] Add failing Swift tests in `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIConformanceHarnessTests.swift`.
  - Mock local/remote parity emits three passing rows using `OpenAIConformanceReport`.
  - The parity transport captures two requests per fixture and compares sanitized request receipts.
  - Request receipt mismatches fail with a named key.
  - Response shape mismatches fail with a named side and shape reason.
  - CLI parser accepts `--mode proxy-parity` and rejects missing local or remote fields with named usage errors.
- [x] Add `OpenAIProxyParityHarness` in `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIConformanceHarness.swift`.
  - Introduce `OpenAIProxyParityTarget` for local and remote endpoint metadata.
  - Execute each existing `HarnessRow` once for local and once for remote.
  - Build sanitized `OpenAIProxyParityRequestReceipt` values from the actual `URLRequest`.
  - Convert each response into a comparable response-shape receipt.
  - Emit `OpenAIConformanceRow` values with explicit failure reasons when request or response receipts differ.
- [x] Extend CLI parsing and execution.
  - Support `--mode proxy-parity`.
  - Add `--local-base-url`, `--local-model`, `--local-api-key`, `--remote-base-url`, `--remote-model`, and `--remote-api-key`.
  - Preserve existing `mock-backend-ci` and `real-backend-smoke` behavior.
- [x] Document usage and evidence.
  - Update this plan with verification receipts.
  - Keep ADR 0002 unchanged because it already defines Proxy Parity as additive evidence on top of the control-plane boundary.
- [x] Verify focused scope.
  - Run focused harness tests.
  - Run focused conformance matrix tests to prove the authoritative boundary proof still passes.
  - Run changed-line coverage for touched Swift files.
  - Run full local gate and PR-scoped performance before PR creation.

## Verification Receipts

- Baseline: `HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'OpenAIConformanceHarnessTests|OpenAIConformanceMatrixTests'` passed with 26 tests in 2 suites before issue #1989 changes.
- RED: `HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter OpenAIConformanceHarnessTests` failed because `OpenAIProxyParityHarness`, `OpenAIProxyParityTarget`, and `proxyParityTarget` did not exist.
- RED follow-up: `HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter OpenAIConformanceHarnessTests/cliParserCoversProxyParityModeAndNamedMissingFields` failed because mode-specific CLI options were being silently ignored.
- GREEN: `HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter OpenAIConformanceHarnessTests` passed with 13 tests in 1 suite after adding proxy parity mode.
- Boundary proof: `HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter OpenAIConformanceMatrixTests` passed with 17 tests in 1 suite.
- CLI mock smoke: `swift run --package-path services/control-plane-swift melix-openai-conformance --mode mock-backend-ci --output .runtime/issue1989/mock-report.json` wrote a report with `passed=3 failed=0 skipped=0`.
- CLI proxy-parity unreachable smoke: `swift run --package-path services/control-plane-swift melix-openai-conformance --mode proxy-parity --local-base-url http://127.0.0.1:9/v1 --local-model local-model --remote-base-url http://127.0.0.1:10/v1 --remote-model remote-model --timeout-seconds 1 --output .runtime/issue1989/proxy-parity-unreachable-report.json` wrote schema `melix.openai_conformance_report.v1` with `passed=0 failed=3 skipped=0` and exited 1 because rows failed.
- RED base-path normalization: `swift test --package-path services/control-plane-swift --filter 'OpenAIConformanceHarnessTests/proxyParityHarnessEmitsExistingReportSchemaForLocalAndRemoteTargets'` failed when the remote target used `/openai/v1/`, proving receipt comparison was treating provider base path as a parity mismatch.
- GREEN base-path normalization: `swift test --package-path services/control-plane-swift --filter 'OpenAIConformanceHarnessTests/proxyParityHarnessEmitsExistingReportSchemaForLocalAndRemoteTargets'` passed after request receipts began comparing the normalized endpoint path while still dispatching to the configured remote base path.
- Focused final: `swift test --package-path services/control-plane-swift --filter 'OpenAIConformanceHarnessTests|OpenAIConformanceMatrixTests'` passed with 33 tests in 2 suites.
- Coverage GREEN: `HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'OpenAIConformanceHarnessTests|OpenAIConformanceMatrixTests'` passed with 33 tests in 2 suites.
- Changed-line coverage: `UV_PYTHON=3.12 uv run python scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata --diff-from origin/main services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIConformanceHarness.swift services/control-plane-swift/Sources/OpenAIConformanceHarnessCLI/main.swift services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIConformanceHarnessTests.swift` reported `99.12%` total changed-line coverage (`561/566`).
- Full Swift gate: `make swift-test` passed.
- Python gate: `make py-test` passed with `4075 passed, 14 skipped, 2 warnings`.
- Integration gate: `make integration-test` passed with `120 passed, 1 skipped`.
- PR review fix: `makeNormalizedChatCompletionsURL` now accepts base URLs that already end in `/chat/completions`, and request receipt mismatch checks compare arrays directly instead of comparing `.description` strings.
- Review-focused verification: `HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter OpenAIConformanceHarnessTests` passed with 17 tests in 1 suite after the review fix.
- Review boundary verification: `HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'OpenAIConformanceHarnessTests|OpenAIConformanceMatrixTests'` passed with 34 tests in 2 suites after the review fix.
- Review coverage verification: `HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'OpenAIConformanceHarnessTests|OpenAIConformanceMatrixTests'` passed with 34 tests in 2 suites after the review fix.
- Review changed-line coverage: `UV_PYTHON=3.12 uv run python scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata --diff-from origin/main services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIConformanceHarness.swift services/control-plane-swift/Sources/OpenAIConformanceHarnessCLI/main.swift services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIConformanceHarnessTests.swift` reported `97.55%` total changed-line coverage (`598/613`).

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
