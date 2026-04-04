# M10.2 Power Policy And Lifecycle Controls

Status: completed.

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

- `make proto`
- `swift test --filter MelixCLITests`
- `swift test --package-path services/control-plane-swift --filter ControlPlaneTests`
- `swift test --enable-code-coverage --filter MelixCLITests`
- `swift test --package-path services/control-plane-swift --enable-code-coverage --filter ControlPlaneTests`
- `make swift-test`
- `make py-test`
- `make integration-test`
- focused Swift changed-line coverage for the touched handwritten executable scope is `96.58%`
  (`1781/1844`)

## Acceptance

- Pause, sleep, wake, and stop controls are explicit and measurable.
- Idle-to-sleep behavior is test-covered and safe for warm sessions.

## Outcome

- the control-plane protocol now exposes explicit `pause`, `resume`, `wake`, `stop`, and
  `set_idle_policy` server commands with session-scoped payloads instead of relying on snapshot-only
  lifecycle metadata
- `ServerSessionRuntimeStore` now owns authoritative lifecycle transitions, idle inhibition, and
  auto-sleep threshold handling for live server sessions, while `ServerSnapshotBuilder` derives the
  aggregate server-state read model from runtime-session truth
- the local XPC client and `melix` CLI now expose session-scoped lifecycle controls and snapshot
  rendering so operator flows can start, pause, resume, wake, stop, and reconfigure idle policy
  without mutating worker-local state out of band
