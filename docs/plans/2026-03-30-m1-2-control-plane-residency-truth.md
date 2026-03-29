# M1.2 Control-Plane Residency Truth

## Goal

Move model residency truth into the control plane so load state, eviction state, and operator-visible residency transitions are coordinated in one place.

## Scope

- replace scattered residency decisions with control-plane-owned state transitions
- keep worker-specific runtime details behind the worker boundary
- preserve existing operator model actions while the migration is in progress

## Files

- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- update `services/control-plane-swift/Sources/WorkerClient/WorkerRegistry.swift`
- update `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`

## Implementation Notes

- state transitions should distinguish discovered, warm, pinned, evicting, and failed residency states
- operator actions should read the same residency truth that HTTP and XPC surfaces expose
- do not allow worker-local shortcuts to bypass control-plane state updates

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- control-plane snapshots and model listings reflect residency transitions consistently
- load, unload, and eviction state are no longer inferred indirectly from dispatch-handle presence alone
