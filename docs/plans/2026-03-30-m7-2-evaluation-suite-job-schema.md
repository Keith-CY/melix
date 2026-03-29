# M7.2 Evaluation-Suite Job Schema

## Goal

Define repository-owned job and result schemas for offline evaluation suites so benchmarking and evaluation can evolve independently.

## Scope

- define evaluation-suite job identity and result schema
- keep evaluation outputs compatible with offline datasets and persistence
- preserve later comparison and release-gate integration

## Files

- update `packages/protocol/schema/controlplane/v1/`
- update `services/mlx-worker-python/worker/productization/`
- update `services/control-plane-swift/Sources/XPCService/`

## Implementation Notes

- evaluation results should capture dataset, sample size, mode, and scoring outcomes explicitly
- keep evaluation schema separate from serving-benchmark schema to avoid semantic drift
- support offline packaging and repeatable reruns from the start

## Verification

- `make proto`
- `make py-test`
- `make swift-test`

## Acceptance

- evaluation-suite jobs and results have dedicated schema support
- evaluation outputs are machine-readable and persistence-ready
