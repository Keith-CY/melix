# M7.1 Serving Benchmark Job Schema

## Goal

Define repository-owned job and result schemas for serving benchmarks so benchmark execution becomes a first-class product capability.

## Scope

- define serving-benchmark job identity and result shape
- keep the schema compatible with queueing, persistence, and export
- preserve later release-gate consumption

## Files

- update `packages/protocol/schema/controlplane/v1/`
- update `services/mlx-worker-python/worker/productization/`
- update `services/control-plane-swift/Sources/XPCService/`

## Implementation Notes

- benchmark jobs should represent suites, parameters, artifacts, and metrics explicitly
- result schema should remain machine-readable for comparison and release-gate use
- avoid ad hoc markdown-only outputs as the sole benchmark result shape

## Verification

- `make proto`
- `make py-test`
- `make swift-test`

## Acceptance

- serving-benchmark jobs and results are represented in repository-owned protocol and productization code
- benchmark data can be queued and persisted without bespoke parsing
