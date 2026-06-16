# Issue 1759 Companion Pairing Code

## Goal

Add a compact desktop pairing-code path for the existing read-only companion
token controls, and prove the companion pairing panel stays usable at a narrow
mobile-sized width.

## Best End-State Architecture

Companion pairing remains gateway-scoped and read-only. The desktop app issues a
`companion_read_only` session through the existing auth-session endpoint, keeps
the raw token only in transient process memory, and can render either:

- the full JSON pairing bundle for copy/paste integrations; or
- a compact `melix-companion:` pairing code that URL-safe-base64 encodes the
  same transient bundle for future QR/code transfer surfaces.

The pairing code is not persisted and does not change gateway authorization.
Gateway read-only scope, self-revocation, and redaction remain the source of
truth.

## Slice Boundary

Included:

- add `RuntimeViewModel.companionPairingCodeText()` for active companion tokens;
- add a `Copy Code` desktop pairing action beside the existing bundle copy and
  revoke actions;
- keep the companion pairing panel compact enough for a 360 px hosted smoke
  surface by truncating long URL/route text and stacking actions vertically;
- update the persistent-session runbook with the code format and token handling
  boundary;
- focused Swift tests for code generation, token revocation cleanup, control
  labels, and narrow-width rendering.

Excluded:

- QR image rendering;
- a companion web/PWA client;
- public internet exposure;
- changing the companion route allowlist or redaction policy.

## Performance Probes and Metrics

- Runtime metrics: existing `companion.pairing_issue_ms` and
  `companion.pairing_revoke_ms` continue to measure gateway calls.
- New code path: fixed-size JSON encoding plus base64 encoding of the existing
  transient pairing bundle when the operator asks to copy a code.
- PR merge gate: scoped performance report must remain `Status: ok` with zero
  regressions.

## Implementation Plan

1. Add failing menu-bar tests proving an active companion pairing exposes a
   `melix-companion:` code, the code has no whitespace, the raw token is not
   visible in the code string, and revocation clears the code.
2. Add a desktop presentation test proving the Authentication companion panel
   exposes the `Copy Code` action and can host at 360 px without a wide
   intrinsic-size regression.
3. Implement `RuntimeViewModel.companionPairingCodeText()` by URL-safe-base64
   encoding the same JSON returned by `companionPairingBundleText()` and
   prefixing it with `melix-companion:`.
4. Add the `Copy Code` button and narrow the panel layout by truncating long
   URL/route text and stacking actions vertically.
5. Update `docs/runbooks/persistent-sessions.md`.
6. Run focused Swift tests, changed-line coverage, full local gate, and PR
   scoped performance before merge.

## Verification

Focused Swift tests:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" xcrun swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests/issuesCompanionPairingWithStoredPrimaryKey|DesktopFoundationViewTests/companionPairingPanelRendersIdleActiveAndFailureStates|DesktopFoundationViewTests/apiAuthenticationSurfaceIncludesCompanionPairingTokenControls'
```

Changed-line coverage:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" xcrun swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests/issuesCompanionPairingWithStoredPrimaryKey|RuntimeViewModelTests/revokesActiveCompanionPairingToken|DesktopFoundationViewTests/companionPairingPanelRendersIdleActiveAndFailureStates|DesktopFoundationViewTests/apiAuthenticationSurfaceIncludesCompanionPairingTokenControls'
uv run --python 3.12 python scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata --diff-from origin/main apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift
```

## Deferred Work

- QR image rendering for the `melix-companion:` code.
- Mobile or PWA companion client import flow.
- Companion status page smoke in a real browser viewport.
