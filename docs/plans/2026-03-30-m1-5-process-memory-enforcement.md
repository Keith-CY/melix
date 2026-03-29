# M1.5 Process Memory Enforcement

## Goal

Add process-level memory budgeting and model-load headroom enforcement so Melix can reject unsafe loads before the runtime becomes unstable.

## Scope

- define process-level memory budgets
- reserve configurable headroom during model load
- reject unsafe loads with explicit operator-visible failures

## Files

- update `packages/protocol/schema/controlplane/v1/`
- update `packages/protocol/schema/worker/v1/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `services/control-plane-swift/Sources/WorkerClient/`
- update `services/mlx-worker-python/worker/registry.py`

## Implementation Notes

- model-load enforcement should run before expensive warmup begins
- budget failures should be explicit structured errors rather than fallback behavior
- the enforcement contract should support later platform-specific budget tuning

## Verification

- `make proto`
- `make swift-test`
- `make py-test`
- `make integration-test`

## Acceptance

- model loads can be rejected because of process-level memory limits
- control-plane and desktop surfaces can explain the rejection reason to operators
