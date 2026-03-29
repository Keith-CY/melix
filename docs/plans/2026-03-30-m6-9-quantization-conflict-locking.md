# M6.9 Quantization Conflict Locking

## Goal

Prevent active quantization work from racing incompatible inference and artifact operations on the same model family.

## Scope

- add operation-level locking or leasing for quantize workflows
- preserve operator visibility into blocked work
- avoid deadlocks across maintenance and serving actions

## Files

- update `services/mlx-worker-python/worker/model_ops/`
- update `services/mlx-worker-python/worker/engine/maintenance_core.py`
- update `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- update `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`

## Implementation Notes

- locks should be scoped narrowly enough to preserve safe concurrency where possible
- blocked work should return structured operator-visible state rather than hanging
- lock state should be inspectable for diagnostics and release gates

## Verification

- `make py-test`
- `make integration-test`

## Acceptance

- incompatible quantize and inference work cannot run concurrently on the same protected scope
- blocked operations are explicit and test-covered
