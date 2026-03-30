# M10.2 Power Policy And Lifecycle Controls

## Goal

Implement the control-plane lifecycle controls and idle-power policy that drive pause, sleep, wake, and stop behavior.

## Scope

- add pause, resume, stop, and wake command paths
- add idle timers and auto-sleep policy handling
- preserve cache and residency integrity during transitions

## Files

- update `services/control-plane-swift/Sources/Requests/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `tests/integration/`

## Implementation Notes

- Lifecycle policy should remain control-plane-driven rather than worker-local.
- Idle timers must not race active requests or warmup flows.
- Wake behavior should reuse existing residency truth instead of rebuilding state heuristically.

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- Pause, sleep, wake, and stop controls are explicit and measurable.
- Idle-to-sleep behavior is test-covered and safe for warm sessions.
