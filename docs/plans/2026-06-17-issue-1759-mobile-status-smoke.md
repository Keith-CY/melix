# Issue 1759 Mobile Companion Status Smoke Plan

## Goal

Add deterministic narrow-viewport coverage for the read-only companion status surface so issue #1759 has a mobile-oriented smoke for the primary paired status flow.

## Scope

- Cover the existing macOS API Authentication `Companion Status` panel at a phone-like width.
- Assert the status title, redacted log-tail row, redaction summary, and panel width remain usable in the narrow layout.
- Document the smoke expectation in the persistent sessions runbook.

## Out Of Scope

- New companion endpoints.
- A real mobile/PWA client.
- New mutating actions or companion-token scope changes.
- Real desktop-window screenshot capture.

## Implementation Steps

1. Add a failing Swift test in `DesktopFoundationViewTests.swift` that renders `DesktopAPICompanionStatusPanel` at `360x640` after issuing a read-only companion token and refreshing status through the fake client.
2. If the failing test exposes layout overflow, adjust only `DesktopAPICompanionStatusPanel` layout constraints to keep the loaded status/log-tail content within the narrow width.
3. Update `docs/runbooks/persistent-sessions.md` with the deterministic narrow-viewport companion status smoke expectation.
4. Run focused tests, changed-line coverage for the touched Swift files, `make swift-test-menubar`, and a scoped performance report.

## Success Metrics

- Focused companion status tests pass.
- Changed-line coverage for touched Swift scope is at least 95 percent.
- Scoped performance report status is `ok` with 0 regressions.
- PR evidence records the mobile/narrow smoke and notes no protocol or generated artifact changes.
