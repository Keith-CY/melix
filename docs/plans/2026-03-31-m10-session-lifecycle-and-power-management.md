# M10 Session Lifecycle And Power Management

## Goal

Add sessionized local serving with explicit lifecycle and power-state behavior so Melix can distinguish loading, ready, paused, sleeping, and stopped states without forcing operators to infer them from logs.

## Scope

- define a shared server-session state model
- add explicit pause, resume, stop, and wake behavior
- add operator-visible power-state configuration and status surfaces
- preserve cache and model integrity during sleep and wake transitions

## Coverage

- `loading`, `ready`, `paused`, `sleeping`, and `stopped` session states
- `start`, `pause`, `resume`, `stop`, `auto_sleep`, `light_sleep_after`, and `deep_sleep_after`
- desktop and chat status banners for lifecycle and power state
- wake reasons, idle timers, and session-state metrics
- lifecycle-safe resume behavior for warm and sleeping sessions

## Execution Slices

- `M10.1` Session state protocol and snapshots
- `M10.2` Power policy and lifecycle controls
- `M10.3` Desktop status banners and operator surfaces
- `M10.4` Session lifecycle integration evidence

## Files

- update `packages/protocol/schema/controlplane/v1/`
- update `services/control-plane-swift/Sources/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `docs/runbooks/`
- update `tests/integration/`

## Implementation Notes

- The control plane should remain the single source of truth for session and power state.
- `sleeping` must remain distinct from `paused`; it represents an auto-managed low-activity state, not an operator-forced hold state.
- Resume and wake flows must not corrupt cache metadata, model residency state, or request read models.
- Desktop status banners should derive from live session-state events rather than local timers or inference.

## Verification

- `make swift-test`
- `make integration-test`
- session-lifecycle smoke command for the touched scope

## Acceptance

- Session lifecycle and power-state transitions are explicit, operator-visible, and test-covered.
- Idle-to-sleep and wake-to-ready flows are measurable and stable.
- Desktop surfaces, XPC clients, and API-facing status views agree on current session state.
