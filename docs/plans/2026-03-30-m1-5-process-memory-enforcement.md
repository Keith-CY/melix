# M1.5 Process Memory Enforcement

## Goal

Add process-level memory budgeting and model-load headroom enforcement so Melix can reject unsafe loads before the runtime becomes unstable.

## Scope

- define process-level memory budgets
- reserve configurable headroom during model load
- reject unsafe loads with explicit operator-visible failures

## Files

- update `services/control-plane-swift/Sources/XPCService/`
- update `services/control-plane-swift/Sources/WorkerClient/`
- update `services/mlx-text-worker-swift/Sources/Core/`
- update `services/mlx-worker-python/worker/registry.py`
- update `services/mlx-worker-python/worker/grpc_server.py`

## Implementation Notes

- model-load enforcement should run before expensive warmup begins
- budget failures should be explicit structured errors rather than fallback behavior
- the enforcement contract should support later platform-specific budget tuning
- worker-specific environment toggles are:
  - `MELIX_SWIFT_TEXT_WORKER_PROCESS_MEMORY_BUDGET_BYTES`
  - `MELIX_SWIFT_TEXT_WORKER_MODEL_LOAD_HEADROOM_BYTES`
  - `MELIX_PYTHON_WORKER_PROCESS_MEMORY_BUDGET_BYTES`
  - `MELIX_PYTHON_WORKER_MODEL_LOAD_HEADROOM_BYTES`
- the first slice reuses the existing worker load request budget field and does not require protocol changes
- request-level `memory_budget_bytes` keeps its existing per-load meaning; the new environment toggles provide process-level total-memory enforcement

## Verification

- `swift test --package-path services/mlx-text-worker-swift --filter WorkerScaffoldTests`
- `swift test --package-path services/control-plane-swift --filter OnDemandModelLoaderTests`
- `swift test --package-path services/control-plane-swift --filter executeSurfacesExplicitMemoryBudgetRejectionsFromWorkerBackedModelLoad`
- `make py-test`
- `git diff --check`

## Acceptance

- model loads can be rejected because of process-level memory limits
- control-plane and desktop surfaces can explain the rejection reason to operators
