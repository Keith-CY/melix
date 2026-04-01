# Tools And API Migration

## Goal

Reorganize tooling and API surfaces so operators can find model management, diagnostics, and API reference material without abstract grouping names.

## Scope

- Tools left-sidebar reorganization
- default Tools landing section
- migration of model, download, training, diagnostics, logs, and settings surfaces
- API reference, auth explanation, and quick-start layout

## Non-Goals

- a try-it console
- keeping abstract tool-group names such as `Runtime`, `Operations`, `Assets`, `Jobs`, or `Admin`

## Tools Rules

The Tools sidebar must use these direct names:

- `Models Library`
- `Downloads`
- `Training`
- `Diagnostics`
- `Logs`
- `Settings`

Default landing section is `Models Library`.

## API Rules

The API page remains documentation-only and must include:

- base URL
- auth explanation
- endpoint reference
- curl quick start
- Python quick start
- JavaScript quick start

## Required Interfaces

- `DesktopToolSection` selection model
- API-page section model for overview, auth, quick starts, and endpoints
- inspector copy actions for base URL and current server metadata

## Files

- modify `apps/macos-menubar/Sources/AppMain/Dashboard/` and or shared shell views
- reuse or adapt existing tooling views under `apps/macos-menubar/Sources/AppMain/`
- update tests that assert default tool selection or API rendering

## Performance Probes

- `menu.foundation_refresh_ms`
- tool-refresh latency for diagnostics or model-ops refresh actions

## Verification

- `swift test --package-path apps/macos-menubar --filter DesktopFoundationViewTests`
- `make swift-test`

## Acceptance

- Tools defaults to `Models Library`
- all five remaining tool sections are directly discoverable from the left sidebar
- the API page contains base URL, auth, endpoint reference, and three quick starts
- the API page does not offer a try-it console
