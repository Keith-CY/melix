# M2.9 Prefill Progress And Cache Pressure Metrics

## Goal

Expose prefill progress, waiting and active counts, restore-stage visibility, and cache-pressure signals as first-class metrics for operators and release gates.

## Scope

- add prefill progress counters and progress-state reporting
- expose cache pressure and restore-stage metrics
- make the metrics usable from desktop, HTTP, and release-gate flows

## Files

- update `services/control-plane-swift/Sources/Requests/`
- update `services/control-plane-swift/Sources/Metrics/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `services/mlx-worker-python/worker/productization/`

## Implementation Notes

- progress reporting must remain stable under batching and chunked prefill
- cache pressure should be defined so it can feed admission and release-gate decisions later
- avoid metrics that are visible only in a single operator surface

## Verification

- `make swift-test`
- `make integration-test`
- touched-scope metrics report command for the scheduler slice

## Acceptance

- prefill progress and cache pressure are visible and machine-readable
- operator surfaces can display live progress without inventing UI-local state
