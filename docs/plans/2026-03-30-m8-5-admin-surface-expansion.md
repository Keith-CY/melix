# M8.5 Admin Surface Expansion

## Status

Completed. The native operator shell now exposes the planned runtime, model, chat, benchmark,
tooling, agent-integration, logs, and settings workflows through one control-plane-backed desktop
surface, and the menu bar package carries repository-owned coverage for the expanded shell.

## Goal

Expand the operator-facing admin surface to cover runtime, models, chat, benchmark, tooling, and logs in one coherent product shell.

## Scope

- broaden the operator dashboard surface
- keep all displayed state sourced from control-plane truth
- preserve the menu bar app as an operator shell rather than a second control plane

## Files

- update `apps/macos-menubar/Sources/AppMain/`
- update `apps/macos-menubar/Tests/MenuBarTests/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `docs/runbooks/`

## Implementation Notes

- surface expansion should reuse existing runtime and productization data rather than inventing parallel state models
- keep each tab or panel independently testable
- avoid adding product views that have no backend truth

## Verification

- `make swift-test`
- `make integration-test`

Final close-out verification:

- `make swift-test`
- `make integration-test`

## Acceptance

- the admin shell covers the planned runtime, model, benchmark, tooling, and log workflows
- UI behavior is backed by control-plane state and test-covered
