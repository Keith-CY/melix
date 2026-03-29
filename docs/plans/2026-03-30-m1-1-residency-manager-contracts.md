# M1.1 Residency Manager Contracts

## Goal

Define shared residency contracts for model load, unload, pin, TTL, and eviction across the control plane, the Swift text worker, and the Python worker families.

## Scope

- add explicit residency states and transitions
- carry residency metadata through control-plane and worker protocols
- preserve the current manual load and unload flows during migration

## Files

- update `packages/protocol/schema/controlplane/v1/`
- update `packages/protocol/schema/worker/v1/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `services/control-plane-swift/Sources/WorkerClient/`
- update `services/mlx-worker-python/worker/registry.py`

## Implementation Notes

- keep residency truth in the control plane and capability reporting in the workers
- define enough metadata for later TTL, LRU, memory-guard, and pin-aware admission work
- avoid coupling the residency model to a single capability family

## Verification

- `make proto`
- `make swift-test`
- `make py-test`

## Acceptance

- shared residency semantics exist in the protocol and control-plane state model
- text and Python-routed model families can report and consume the same residency contract
