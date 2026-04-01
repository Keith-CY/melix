# Server-Session-Centered Desktop Shell Migration

## Goal

Migrate the macOS desktop shell from a mixed dashboard or gateway-default layout to a server-session-centered product model with the fixed top-level order `Chat / Image / Server / Tools / API`.

## Scope

- remove the `Dashboard` tab from the main shell
- add a `Command Center` independent window
- introduce typed desktop `Server Session` and `Chat Session` state
- rebind Chat to `Server Session`
- keep Image model and job oriented
- reorganize Tools into direct object names
- constrain API to reference and quick-start material only

## Non-Goals

- claiming that true multi-listener control-plane truth already exists
- shipping a try-it API console
- moving Image onto server-session routing
- using abstract tool-group names such as `Runtime` or `Operations`

## Derived Interface Changes

This migration requires explicit contract work:

- add typed `Server Session` lifecycle and state modeling
- evolve the current single gateway configuration toward per-server listener configuration
- add explicit `Chat Session -> Server Session` binding rules
- add an independent `Command Center` window contract and view model

## Execution Order

1. shell and command-center foundation
2. server-session product model and control-plane read model
3. chat and image rebinding
4. tools and API migration

## Dependencies

### Upstream Dependencies

- existing control-plane snapshot and event truth for models, queues, logs, image jobs, and resources
- existing native chat and image panels
- existing model-tooling and API-reference surfaces

### New Work Items

- desktop typed state for server-session and chat-session collections
- control-plane schema and read-model extensions for multi-listener evolution
- command-center-specific summary model
- migration path from gateway defaults to per-server listener settings

## Protocol And State Evolution

### Current Constraint

The repository currently exposes a single gateway-style mental model and does not yet provide complete backend truth for independent listener instances.

### Required Evolution

- add server-session identifiers and lifecycle states to control-plane truth
- represent listener configuration per server session
- expose chat-session binding to server-session identifiers
- surface command-center summaries without making the app a second control plane

## Desktop Migration Slices

- `2026-04-01-shell-command-center.md`
- `2026-04-01-server-session-product-model.md`
- `2026-04-01-chat-image-rebinding.md`
- `2026-04-01-tools-api-migration.md`

## Files

- modify `apps/macos-menubar/Sources/AppMain/`
- update or add relevant test files under `apps/macos-menubar/Tests/MenuBarTests/`
- add architecture and plan documents under `docs/architecture/` and `docs/plans/`
- update control-plane protocol and desktop-state documents if protocol work begins in the same slice

## Performance Probes

- `menu.console_open_ms`
- `menu.command_center_open_ms`
- `menu.foundation_refresh_ms`
- `menu.chat_submit_ms`
- `desktop.image_action_latency_ms`
- typed server-session lifecycle transition timings when protocol support lands

## Verification

- `swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests`
- `swift test --package-path apps/macos-menubar --filter DesktopFoundationPresenterTests`
- `swift test --package-path apps/macos-menubar --filter DesktopFoundationViewTests`
- `make swift-test`
- `git diff --check`

## Acceptance

- the top-level shell order is `Chat / Image / Server / Tools / API`
- `Dashboard` no longer appears as a main tab
- `Command Center` opens as an independent window and shows global health, pressure, recovery items, and recent activity
- Chat blocks when no running `Server Session` is available
- Image remains model and job based
- Tools defaults to `Models Library`
- API stays reference only
