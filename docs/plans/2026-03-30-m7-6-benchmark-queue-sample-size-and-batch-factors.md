# M7.6 Benchmark Queue, Sample Size, And Batch Factors

## Goal

Add queueing and parameterization controls for benchmark and evaluation jobs so operators can run repeatable comparison workloads.

## Scope

- add queue semantics for benchmark and eval jobs
- support sample-size selection and batch-factor selection
- keep queue state visible to operators

## Files

- update `services/control-plane-swift/Sources/XPCService/`
- update `services/mlx-worker-python/worker/productization/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `tests/integration/`

## Implementation Notes

- queue state should remain visible through both desktop and machine-readable surfaces
- parameter choices should be stored with the result for reproducibility
- avoid benchmark execution that cannot be replayed because parameters were implicit

## Verification

- `make swift-test`
- `make py-test`
- benchmark-queue integration smoke command

## Acceptance

- benchmark and eval jobs can queue with explicit sample-size and batch-factor settings
- queue state and parameter choices are test-covered and operator-visible
