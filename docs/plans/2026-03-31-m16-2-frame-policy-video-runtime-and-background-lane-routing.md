# M16.2 Frame Policy, Video Runtime, And Background-Lane Routing

## Goal

Make frame selection, runtime shaping, and scheduler behavior explicit for video analysis so video requests can coexist with text and image workloads predictably.

## Scope

- add frame-sampling and frame-budget policy
- route video workloads through explicit background lanes
- expose queue, pressure, and first-token metrics for video analysis

## Files

- update `services/control-plane-swift/Sources/EnginePool/`
- update `services/mlx-worker-python/worker/runtime/`
- update `services/mlx-worker-python/worker/engine/`
- update `tests/integration/`

## Implementation Notes

- Video frame policy should remain configuration-driven and visible in effective request state.
- Video analysis must not reuse interactive text lanes implicitly.

## Verification

- `make swift-test`
- `make py-test`
- `make integration-test`

## Acceptance

- Video requests use explicit frame policy and background-lane routing.
- Queue and latency behavior are measurable under concurrent text load.
