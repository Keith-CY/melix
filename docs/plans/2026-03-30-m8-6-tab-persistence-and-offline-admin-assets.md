# M8.6 Tab Persistence And Offline Admin Assets

Status: completed. Admin-surface tool-section state now persists across restart through
product-owned operator-session storage, a repository-owned smoke command verifies persistence
and secure file ownership, and the offline admin-assets contract is documented in the runbook.

## Goal

Persist admin-surface navigation state and ensure the operator experience does not depend on external CDN-hosted assets where offline packaging matters.

## Scope

- persist tab and view state
- support offline asset ownership where applicable
- keep product behavior deterministic across restarts

## Files

- update `apps/macos-menubar/Sources/AppMain/`
- update `apps/macos-menubar/Tests/MenuBarTests/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `docs/runbooks/`

## Implementation Notes

- persistence should use product-owned state rather than fragile UI-local hacks
- offline asset ownership should remain explicit in packaging and documentation
- keep navigation-state behavior consistent with later install and update flows

## Verification

- `python3 scripts/m8_admin_state_smoke.py --json`
- `make proto`
- `make py-test`
- `make swift-test`
- `make integration-test`

## Acceptance

- admin navigation state survives restart where intended
- offline-owned assets and persistence behavior are documented and test-covered
