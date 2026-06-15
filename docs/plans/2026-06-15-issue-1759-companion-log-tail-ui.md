# Issue 1759 Companion Log Tail UI

## Goal

Render the existing redacted companion status log tail in the desktop API
workspace so the operator can verify what a read-only companion session would
show before the mobile surface lands.

## Best End-State Architecture

The desktop app should treat companion status as read-only remote data fetched
through the already-issued companion session token. AppMain must not read raw
log files, persist companion tokens, or gain new mutation rights. It should call
the gateway `GET /v1/melix/companion/status` route with the transient companion
session token, decode only the safe status/log-tail fields, and render those
fields next to the existing companion pairing controls.

The gateway remains the source of truth for companion authorization, redaction,
and status payload shape. The desktop view model owns only transient fetch
state, latency/failure metrics, and a small presentation state.

## Slice Boundary

Included:

- AppMain companion status client for `GET /v1/melix/companion/status`;
- transient view-model state for status fetch phase, safe log-tail entries,
  redaction labels, errors, and refresh metrics;
- API Authentication workspace panel that renders the redacted log-tail summary
  and refresh control;
- focused AppMain tests for request shape, token handling, payload decoding,
  error handling, and UI presentation.

Excluded:

- changing the gateway companion status endpoint or route allowlist;
- QR image rendering;
- mobile/PWA companion status page implementation;
- narrow viewport smoke automation;
- raw OSLog/stdout/stderr/file log tailing;
- persisting companion tokens or fetched companion status payloads.

## Performance Probes and Metrics

- Runtime metric: record `companion.status_refresh_ms` around the desktop HTTP
  fetch.
- Failure metric: record `companion.status_refresh_failures` when local
  validation or HTTP/decoding fails.
- Probe overhead: one local read-only HTTP call per operator refresh action; no
  polling loop in this slice.
- PR merge gate: scoped performance report must remain `Status: ok` with zero
  regressions.

## Implementation Plan

1. Add failing `RuntimeViewModelTests` proving `refreshCompanionStatus()` uses
   the active companion pairing `status_url`, resume header, and transient token
   to fetch a redacted log-tail payload.
2. Add failing `RuntimeViewModelTests` for missing active companion token and
   live client decoding/HTTP errors.
3. Add failing `DesktopFoundationViewTests` proving the API authentication
   surface contains the companion status/log-tail panel and that its presentation
   renders idle, loaded, and failure states without exposing raw log content.
4. Implement `CompanionStatusClient`, `LiveCompanionStatusClient`, DTOs, and
   safe state structs under `apps/macos-menubar/Sources/AppMain/Models/`.
5. Inject the companion status client into `RuntimeViewModel`, add
   `companionStatus`, `refreshCompanionStatus()`, metrics, and clear status on
   token issue/revoke boundaries.
6. Add `DesktopAPICompanionStatusPanel` to the API Authentication section using
   existing AppMain card/button patterns.
7. Update `docs/runbooks/persistent-sessions.md` with the desktop companion
   status refresh boundary.
8. Run focused tests, changed-line coverage, full local gate, scoped
   performance, PR evidence, remote CI/performance monitoring, review cleanup,
   and squash merge.

## Verification

Focused AppMain tests:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests/(refreshesCompanionStatusLogTailWithActiveReadOnlyToken|companionStatusRefreshRequiresActivePairing|companionStatusRefreshSurfacesTransportFailures|liveCompanionStatusClientFetchesRedactedLogTailAndReportsErrors)|DesktopFoundationViewTests/(apiAuthenticationSurfaceIncludesCompanionStatusLogTailPanel|companionStatusPanelRendersIdleLoadedAndFailureStates)'
```

Changed-line coverage:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests/(refreshesCompanionStatusLogTailWithActiveReadOnlyToken|companionStatusRefreshRequiresActivePairing|companionStatusRefreshSurfacesTransportFailures|liveCompanionStatusClientFetchesRedactedLogTailAndReportsErrors)|DesktopFoundationViewTests/(apiAuthenticationSurfaceIncludesCompanionStatusLogTailPanel|companionStatusPanelRendersIdleLoadedAndFailureStates)'
UV_PYTHON=3.12 uv run python scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata --diff-from origin/main apps/macos-menubar/Sources/AppMain/Models/CompanionStatusClient.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift
```

Full gate before commit:

```bash
make swift-test
make py-test
make integration-test
```
