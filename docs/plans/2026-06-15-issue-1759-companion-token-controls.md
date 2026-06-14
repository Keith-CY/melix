# Issue 1759 Companion Token Controls

## Goal

Add desktop API-surface controls that let the operator issue, copy, and revoke a
single read-only companion session token for the selected local server session.

## Best End-State Architecture

The desktop app should not become a second auth-session authority. It should use
the selected server session's stored primary gateway API key to call
`POST /v1/melix/auth/session` with `scope = companion_read_only`, render the
safe pairing descriptor returned by the gateway, and keep the raw
`resume.token` only in transient view-model memory so the same desktop session
can copy or revoke it.

Revocation should call the existing self-revocation route with
`X-Melix-Session: <token>` and then clear the transient token state. Operator
state persistence continues to store server-session settings and primary API
keys only; it must not write companion session tokens or companion pairing
bundles.

## Slice Boundary

This slice adds native desktop companion-token management in the API workspace.

Included:

- a desktop companion-pairing client for create and revoke calls;
- view-model state for issue/revoke phases, safe descriptor fields, errors, and
  a copyable one-time pairing bundle;
- API workspace controls for issuing, copying, and revoking the active
  companion token;
- focused AppMain tests proving request shape, revocation, missing-key errors,
  and token non-persistence.

Excluded:

- QR image rendering;
- companion/mobile status page implementation;
- mobile or narrow viewport smoke;
- LAN discovery or public internet exposure;
- changing the gateway companion route allowlist.

## Performance Probes and Metrics

- Runtime metrics: record `companion.pairing_issue_ms` and
  `companion.pairing_revoke_ms` from the desktop view model around the HTTP
  calls.
- Failure metrics: record `companion.pairing_issue_failures` and
  `companion.pairing_revoke_failures` as monotonically increasing desktop
  counters when local validation or HTTP calls fail.
- Probe overhead: bounded to two local HTTP calls and one metrics write per
  operator action.
- PR merge gate: scoped performance report must remain `Status: ok` with zero
  regressions.

## Implementation Plan

1. Add failing `RuntimeViewModelTests` for issuing a companion pairing from the
   selected server session. The test stores a primary key, injects a fake
   companion client, calls `issueCompanionPairing()`, and asserts the client saw
   `http://127.0.0.1:<port>` plus the primary key, the state exposes descriptor
   fields, and the raw token does not appear in `String(describing: state)`.
2. Add failing `RuntimeViewModelTests` for revoking the active companion token.
   The test issues a fake token, calls `revokeCompanionPairing()`, asserts the
   fake client saw the token, and asserts the visible state returns to idle.
3. Add failing `RuntimeViewModelTests` for missing primary key validation. The
   test calls `issueCompanionPairing()` without a stored key and expects a
   visible error, zero client calls, and an issue-failure metric.
4. Implement `CompanionPairingClient`, `LiveCompanionPairingClient`, and compact
   DTO/state types under `apps/macos-menubar/Sources/AppMain/Models/`.
5. Inject the companion client into `RuntimeViewModel`, add
   `companionPairing`, `issueCompanionPairing()`,
   `companionPairingBundleText()`, and `revokeCompanionPairing()` methods, and
   keep the raw token in a private in-memory field only.
6. Add a compact `Companion Pairing` panel to `DesktopAPIWorkspaceView` under
   the Authentication section, using existing AppMain card/button patterns.
7. Update `docs/runbooks/persistent-sessions.md` with the desktop control
   boundary and token handling rule.
8. Run focused tests, changed-line coverage, scoped performance, pre-commit
   gate, PR creation, remote CI/performance monitoring, review-thread cleanup,
   and squash merge.

## Verification

Focused AppMain tests:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests/(issuesCompanionPairingWithStoredPrimaryKey|revokesActiveCompanionPairingToken|companionPairingRequiresStoredPrimaryKey|companionPairingSurfacesKeyStoreAndTransportFailures|liveCompanionPairingClientIssuesAndRevokesGatewaySessions|liveCompanionPairingClientReportsGatewayErrorsAndNormalizesRouteDisplayText)|DesktopFoundationViewTests/(apiAuthenticationSurfaceIncludesCompanionPairingTokenControls|companionPairingPanelRendersIdleActiveAndFailureStates)'
```

Result: passed, 8 tests in 2 suites.

Changed-line coverage:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests/(issuesCompanionPairingWithStoredPrimaryKey|revokesActiveCompanionPairingToken|companionPairingRequiresStoredPrimaryKey|companionPairingSurfacesKeyStoreAndTransportFailures|liveCompanionPairingClientIssuesAndRevokesGatewaySessions|liveCompanionPairingClientReportsGatewayErrorsAndNormalizesRouteDisplayText)|DesktopFoundationViewTests/(apiAuthenticationSurfaceIncludesCompanionPairingTokenControls|companionPairingPanelRendersIdleActiveAndFailureStates)'
UV_PYTHON=3.12 uv run python scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata --diff-from origin/main apps/macos-menubar/Sources/AppMain/Models/CompanionPairingClient.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift
```

Result: changed-line coverage `96.08%` (`907/944`).

Full gate before commit:

```bash
make swift-test
make py-test
make integration-test
```

## Deferred Work

- QR/code rendering.
- Companion/mobile status UI.
- Mobile/narrow viewport smoke for the companion status flow.
- Multi-token session list management.
